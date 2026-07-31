"""
core.work_recall
----------------
What AURA knows about the WORK, assembled for a chat turn.

The gap this closes: the Domain's Project Brain has known the whole project
lifecycle since 2026-07-23 — projects, features, tasks, decisions, commits,
progress — and the chat could not see a single byte of it. Ask "what project
were we doing last time?" and the model got eight lines of recent conversation
and nothing else, so it guessed, hedged, or narrated the question back.

Two shapes of the same knowledge:

    context_block(query)   compact, injected into EVERY turn. One line per
                           recent project. Cheap enough to always include.
    answer_context(query)  expanded, for memory questions — open tasks, recent
                           decisions, session recaps, where you left off.

Design rules:
  · Never raise. A chat turn must not fail because a table is missing; every
    read is wrapped and every failure degrades to less context, never an error.
  · Never invent. If nothing is stored, return "" and let AURA say it's fuzzy —
    a confident wrong project name is worse than an honest blank.
  · Stay short. This is prompt budget shared with facts, screen and history, so
    the compact block is capped hard.
"""

from __future__ import annotations

import re
import time
from typing import Any, Callable

# Questions that are ASKING about the work rather than doing it. These get the
# expanded block; everything else gets the one-liner.
_RECALL_RE = re.compile(
    r"(?i)\b("
    r"what (?:were|was|are) we (?:doing|working on|building|on)|"
    r"what did we (?:do|decide|build|finish|discuss)|"
    r"where (?:did|do) we (?:leave off|stop|get to)|"
    r"last (?:time|session|night|week)|"
    r"remind me (?:what|where|about)|"
    r"which project|what project|whose project|"
    r"our (?:project|progress|plan|roadmap)|"
    r"how (?:far|much) (?:along|left|is left|have we)|"
    r"what'?s (?:left|next|pending|remaining|the status)|"
    r"catch me up|recap|do you remember|you remember"
    r")\b"
)

MAX_COMPACT_PROJECTS = 2
MAX_EXPANDED_PROJECTS = 3


def is_work_question(query: str) -> bool:
    """True when the message is asking about the work itself."""
    return bool(query and _RECALL_RE.search(query))


def _safe(fn: Callable[[], Any], default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


def _ago(stamp: str | None) -> str:
    """'2d ago' from a local-ISO or 'YYYY-MM-DD HH:MM:SS' timestamp."""
    if not stamp:
        return ""
    s = str(stamp).strip().replace(" ", "T")[:19]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            t = time.mktime(time.strptime(s, fmt))
            break
        except Exception:
            continue
    else:
        return ""
    diff = max(0, time.time() - t)
    if diff < 3600:
        return f"{int(diff // 60)}m ago"
    if diff < 86400:
        return f"{int(diff // 3600)}h ago"
    if diff < 30 * 86400:
        return f"{int(diff // 86400)}d ago"
    return time.strftime("%d %b", time.localtime(t))


# ── the brain's own view of each project ─────────────────────────────────────
def projects(limit: int = MAX_EXPANDED_PROJECTS) -> list[dict[str, Any]]:
    """Recently-touched projects with their vitals. [] when the brain is empty."""
    rows = _safe(lambda: _list_projects(), [])
    if not rows:
        return []
    rows = sorted(rows, key=lambda p: str(p.get("updated_at") or ""), reverse=True)
    out: list[dict[str, Any]] = []
    for p in rows[:limit]:
        pid = p.get("id") or ""
        prog = _safe(lambda: _progress(pid), {}) or {}
        events = _safe(lambda: _timeline(pid, 3), []) or []
        out.append({
            "id": pid,
            "name": p.get("name") or "untitled project",
            "root": p.get("root") or "",
            "updated": p.get("updated_at") or "",
            "percent": prog.get("percent"),
            "completed": prog.get("completed"),
            "total": prog.get("total"),
            "blocked": prog.get("blocked"),
            "blocker": (prog.get("biggest_blocker") or {}).get("title") if prog.get("biggest_blocker") else None,
            "recent": [e.get("title", "") for e in events if e.get("title")],
            "recent_when": _ago(events[0].get("when")) if events else "",
        })
    return out


def _list_projects() -> list[dict[str, Any]]:
    from core.domain import brain_store
    return brain_store.list_projects()


def _progress(pid: str) -> dict[str, Any]:
    from core.domain import progress
    return progress.overall(pid)


def _timeline(pid: str, limit: int) -> list[dict[str, Any]]:
    from core.domain import project_brain
    return project_brain.timeline(pid, limit)


def _open_tasks(pid: str, limit: int = 4) -> list[str]:
    # Through _nodes, not brain_store directly: one access point keeps the
    # focus/index/recall paths reading the same rows (and testable without a db).
    rows = [n for n in _nodes(pid, "task")
            if n.get("status") in {"in_progress", "todo", "blocked"}]
    # in-progress first: that's what "where were we" actually means
    rank = {"in_progress": 0, "blocked": 1, "todo": 2}
    rows.sort(key=lambda n: rank.get(n.get("status", "todo"), 3))
    return [f"{n['title']} [{n.get('status')}]" for n in rows[:limit]]


def _decisions(pid: str, limit: int = 3) -> list[str]:
    rows = _nodes(pid, "decision")[-limit:]
    out = []
    for n in rows:
        reason = (n.get("meta") or {}).get("reason") or ""
        out.append(f"{n['title']}" + (f" (because {reason})" if reason else ""))
    return out


# ── the companion's own view: recaps, last session ───────────────────────────
def _recaps(limit: int = 3) -> list[str]:
    from memory import store
    rows = store.get_all_snapshots(limit)
    return [f"{r[1]}: {str(r[2])[:160]}" for r in rows if r and r[2]]


def _last_session() -> str:
    from memory import store
    last = store.get_last_session()
    return (last or {}).get("summary") or ""


# ── the two blocks ───────────────────────────────────────────────────────────
def context_block(query: str = "") -> str:
    """One-liner per recent project — safe to inject on every single turn.

    Returns "" when there is nothing real to say, which matters: an empty
    "Projects: (none)" line teaches the model to talk about having no projects.
    """
    ps = projects(MAX_COMPACT_PROJECTS)
    if not ps:
        return ""
    lines = []
    for p in ps:
        bits = [p["name"]]
        if p.get("percent") is not None and p.get("total"):
            bits.append(f"{p['percent']}% ({p['completed']}/{p['total']} tasks)")
        if p.get("recent"):
            when = f", {p['recent_when']}" if p.get("recent_when") else ""
            bits.append(f"last: {p['recent'][0]}{when}")
        lines.append("- " + " — ".join(bits))
    return (
        "The projects you're both working on (you know this — speak about it "
        "naturally, don't list it back):\n" + "\n".join(lines)
    )


def answer_context(query: str = "") -> str:
    """Everything worth knowing when they ask ABOUT the work.

    Used by the RECALL path and injected in place of the compact block when
    `is_work_question(query)`. Still capped — this is a prompt, not a report.
    """
    chunks: list[str] = []

    for p in projects(MAX_EXPANDED_PROJECTS):
        head = p["name"]
        if p.get("percent") is not None and p.get("total"):
            head += f" — {p['percent']}% done, {p['completed']} of {p['total']} tasks"
        if p.get("updated"):
            head += f" (touched {_ago(p['updated'])})"
        body = [head]
        if p.get("root"):
            body.append(f"  folder: {p['root']}")
        tasks = _safe(lambda: _open_tasks(p["id"]), [])
        if tasks:
            body.append("  still open: " + "; ".join(tasks))
        if p.get("blocker"):
            body.append(f"  blocked on: {p['blocker']}")
        decisions = _safe(lambda: _decisions(p["id"]), [])
        if decisions:
            body.append("  decided: " + "; ".join(decisions))
        if p.get("recent"):
            body.append("  recently: " + "; ".join(p["recent"][:3]))
        chunks.append("\n".join(body))

    if chunks:
        chunks.insert(0, "PROJECTS (from your own project memory):")

    last = _safe(_last_session, "")
    if last:
        chunks.append(f"LAST SESSION: {last}")

    recaps = _safe(lambda: _recaps(3), [])
    if recaps:
        chunks.append("EARLIER SESSIONS:\n" + "\n".join(f"- {r}" for r in recaps))

    return "\n\n".join(chunks)


# ── which project is this about? ─────────────────────────────────────────────
# The gap this closes (asked for 2026-07-31): shaurya says "find me sites to
# design my portfolio" and AURA answers as if she'd never heard of the
# portfolio project sitting in the Domain. context_block only ever offered the
# two most RECENTLY TOUCHED projects, so anything he mentions by name — but
# hasn't opened this week — was invisible. Now the message itself picks the
# project, and only when nothing matches do we fall back to recency.

_STOP = {
    "the", "and", "for", "you", "your", "our", "with", "from", "that", "this",
    "what", "how", "why", "who", "can", "some", "more", "give", "get", "make",
    "want", "need", "should", "would", "could", "about", "into", "them", "they",
    "have", "has", "was", "were", "are", "its", "it's", "let", "lets", "any",
    "all", "one", "two", "new", "old", "not", "but", "out", "off", "there",
    "here", "then", "than", "now", "will", "just", "like", "also", "see",
    "show", "tell", "find", "help", "idea", "ideas", "better", "best", "good",
    "project", "projects", "work", "working", "thing", "things", "stuff",
    "please", "where", "when", "which", "and/or",
}
# NOTE: "aura" is deliberately NOT a stopword. It's the name of his main
# project as well as the name he calls her, so dropping it made the one
# project he talks about most the one project this could never find.

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#._-]{1,}")

# Asking to make something BETTER rather than asking what it is. These pull the
# heavier brief (stack, modules, what's already open) because generic advice is
# useless — "add tests" means nothing without knowing there are none.
_IMPROVE_RE = re.compile(
    r"(?i)\b("
    r"upgrade|improve|better|enhance|polish|refactor|optimi[sz]e|scale|"
    r"more ideas|new ideas|any ideas|ideas for|suggest|suggestions|"
    r"what (?:should|could) (?:i|we) (?:add|build|do|change|fix)|"
    r"how (?:do|can|should) (?:i|we) (?:make|improve|upgrade|extend|grow)|"
    r"next (?:step|steps|feature|features)|what'?s missing|"
    r"level (?:it )?up|take it further|make it (?:better|good|great|pro)"
    r")\b"
)

# Asking what a thing IS, not how it's going. Live 2026-07-31: "tell me info
# abt this project what it is doing?" — she had no description stored, so the
# model reasoned about the gap out loud instead of admitting it.
_DESCRIBE_RE = re.compile(
    r"(?i)\b("
    r"what (?:is|are|was) (?:it|this|that|the )|what'?s (?:it|this|that)\b|"
    r"what (?:is |it |this )?(?:it|this|the project) (?:is )?do(?:ing|es)|"
    r"what does (?:it|this|the project|that) do|"
    r"tell me (?:about|info|more|what)|info (?:about|abt|on)\b|"
    r"explain (?:this|it|the project|what)|"
    r"describe (?:this|it|the project)|"
    r"what kind of (?:project|app|thing)|what'?s it about|"
    r"remind me what (?:it|this|that)"
    r")"
)

# Index cache: rebuilding a project's searchable title list on every keystroke
# would hammer sqlite. Keyed by project id, invalidated by its updated_at.
_INDEX: dict[str, tuple[str, set[str], list[str]]] = {}


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall((text or "").lower())
            if t not in _STOP and len(t) > 2}


def improve_intent(query: str) -> bool:
    """True when they're asking how to make something better."""
    return bool(query and _IMPROVE_RE.search(query))


def describe_intent(query: str) -> bool:
    """True when they're asking what something IS / what it does."""
    return bool(query and _DESCRIBE_RE.search(query))


def _project_index(p: dict[str, Any]) -> tuple[set[str], list[str]]:
    """(searchable tokens, the titles those tokens came from) for one project.

    File and commit nodes are deliberately excluded from the token set — a repo
    scan writes hundreds of them and their paths ("src", "index", "main") match
    everything, which would make every project look relevant to every question.
    """
    pid = str(p.get("id") or "")
    stamp = str(p.get("updated_at") or "")
    hit = _INDEX.get(pid)
    if hit and hit[0] == stamp:
        return hit[1], hit[2]

    toks = _tokens(str(p.get("name") or ""))
    import os as _os
    root = str(p.get("root") or "")
    if root:
        toks |= _tokens(_os.path.basename(root.rstrip("/\\")))
    titles: list[str] = []
    for kind in ("feature", "idea", "milestone", "task", "decision"):
        for n in _safe(lambda k=kind: _nodes(pid, k), [])[:60]:
            title = str(n.get("title") or "")
            if title:
                titles.append(title)
                toks |= _tokens(title)

    _INDEX[pid] = (stamp, toks, titles)
    return toks, titles


def _nodes(pid: str, kind: str) -> list[dict[str, Any]]:
    from core.domain import brain_store
    return brain_store.nodes(pid, kind)


def find_project(query: str) -> dict[str, Any] | None:
    """The project this message is about, or None.

    None is a real answer and matters: answering "how do I improve it" against
    the wrong project is worse than answering it generically.
    """
    q = _tokens(query)
    if not q:
        return None
    rows = _safe(lambda: _list_projects(), []) or []
    best, best_score = None, 0.0
    for p in rows:
        name_toks = _tokens(str(p.get("name") or ""))
        toks, _titles = _project_index(p)
        # A hit on the project's own NAME is worth far more than a hit on some
        # task title inside it — "portfolio" naming the project beats
        # "portfolio" appearing in one of AURA's task titles.
        score = 3.0 * len(q & name_toks) + 1.0 * len(q & (toks - name_toks))
        if score > best_score:
            best, best_score = p, score
    if not best or best_score < 1.0:
        return None
    return best


def focus_block(project: dict[str, Any], query: str = "") -> str:
    """Everything AURA knows about ONE project, for a question about it.

    Deeper than answer_context's per-project summary: this is the block that
    lets "how do I upgrade it?" produce an answer about THIS codebase — the
    stack it's built on, what's already done, what's still open — instead of a
    listicle that would fit any project on earth.
    """
    pid = str(project.get("id") or "")
    name = project.get("name") or "the project"
    lines = [f"THE PROJECT THEY'RE ASKING ABOUT — {name}:"]

    root = str(project.get("root") or "")
    if root:
        lines.append(f"  folder: {root}")

    # WHAT IT IS. Without this, "tell me about this project, what is it doing?"
    # had nothing to answer from, and the model filled the hole out loud:
    # "likely a dashboard? Not given explicitly, but we can infer…" (seen live
    # 2026-07-31). Stored description first, then the README, then nothing —
    # and "nothing" is stated explicitly below so she says so instead of
    # guessing.
    about = _safe(lambda: _about(project), "")
    if about:
        lines.append(f"  what it is: {about}")

    prog = _safe(lambda: _progress(pid), {}) or {}
    if prog.get("total"):
        lines.append(
            f"  progress: {prog.get('percent')}% — "
            f"{prog.get('completed')} of {prog.get('total')} tasks done"
        )

    feats = _safe(lambda: _nodes(pid, "feature"), []) or []
    if feats:
        done = [f["title"] for f in feats if f.get("status") in {"done", "shipped", "complete"}]
        rest = [f["title"] for f in feats if f.get("status") not in {"done", "shipped", "complete"}]
        if done:
            lines.append("  already built: " + "; ".join(done[:8]))
        if rest:
            lines.append("  planned, not built: " + "; ".join(rest[:8]))

    tasks = _safe(lambda: _open_tasks(pid, 6), []) or []
    if tasks:
        lines.append("  still open: " + "; ".join(tasks))

    decisions = _safe(lambda: _decisions(pid, 4), []) or []
    if decisions:
        lines.append("  decided already (don't re-suggest these): " + "; ".join(decisions))

    events = _safe(lambda: _timeline(pid, 4), []) or []
    recent = [e.get("title", "") for e in events if e.get("title")]
    if recent:
        lines.append("  recently: " + "; ".join(recent))

    # The stack, for "what is this" as well as "how do I improve this" — both
    # are questions the languages and frameworks actually answer. analyze()
    # walks the folder, so it stays off the ordinary turn.
    if root and (improve_intent(query) or describe_intent(query)):
        tech = _safe(lambda: _stack(root), {}) or {}
        if tech.get("ok"):
            bits = []
            langs = ", ".join(list((tech.get("languages") or {}).keys())[:4])
            if langs:
                bits.append(f"languages: {langs}")
            if tech.get("frameworks"):
                bits.append("frameworks: " + ", ".join(tech["frameworks"][:6]))
            if tech.get("architecture"):
                bits.append(f"shape: {tech['architecture']}")
            if tech.get("file_count"):
                bits.append(f"{tech['file_count']} source files")
            if bits:
                lines.append("  codebase: " + " | ".join(bits))

    if improve_intent(query):
        lines.append(
            "\n(They want to make THIS project better. Ground every suggestion "
            "in what's above — build on what's already there, don't repeat "
            "what's built or already decided, and say WHY each one fits this "
            "project. Generic advice that would fit any project is a failure.)"
        )
    elif describe_intent(query) and not about:
        # The specific failure this prevents: with nothing stored, the model
        # reasoned about the gap out loud rather than admitting it.
        lines.append(
            f"\n(They're asking what {name} IS, and you have NO description of "
            "it stored — only the activity above. Do not guess from the task "
            "titles and do not speculate. Say plainly that you've been "
            "tracking the work but never got the summary, tell them the one or "
            "two things you DO know from the list above, and ask them to tell "
            "you in a line what it does.)"
        )
    else:
        lines.append(
            "\n(Answer about THIS project specifically, using the detail above.)"
        )
    return "\n".join(lines)


# ── what a project actually is ──────────────────────────────────────────────
_README_NAMES = ("README.md", "README.MD", "readme.md", "README", "README.txt",
                 "README.rst", "readme.txt")
_ABOUT_CHARS = 400
_READMES: dict[str, tuple[float, str]] = {}
_README_TTL = 10 * 60


def _about(project: dict[str, Any]) -> str:
    """One paragraph on what this project is, or "" if nobody ever said.

    "" is load-bearing — focus_block turns it into an explicit "you don't know
    this, say so" instruction, which is the whole point. Inventing a plausible
    description would be worse than admitting the gap.
    """
    meta = project.get("meta") or {}
    for key in ("description", "summary", "about", "pitch", "what"):
        val = str(meta.get(key) or "").strip()
        if val:
            return val[:_ABOUT_CHARS]
    return _readme_blurb(str(project.get("root") or ""))


def _readme_blurb(root: str) -> str:
    """The first real prose paragraph of the README. Cached; never raises."""
    if not root:
        return ""
    hit = _READMES.get(root)
    if hit and (time.time() - hit[0]) < _README_TTL:
        return hit[1]

    import os
    blurb = ""
    try:
        for fname in _README_NAMES:
            path = os.path.join(root, fname)
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read(8000)
            para: list[str] = []
            for raw in text.splitlines():
                line = raw.strip()
                # Skip the title, badges, images, code fences and rules — the
                # first PROSE is the description, and READMEs open with junk.
                if not line:
                    if para:
                        break
                    continue
                if (line.startswith(("#", ">", "```", "---", "===", "|", "!["))
                        or line.startswith("[!")):
                    continue
                para.append(line)
                if sum(len(x) for x in para) > _ABOUT_CHARS:
                    break
            blurb = " ".join(para)[:_ABOUT_CHARS].strip()
            if blurb:
                break
    except Exception:  # noqa: BLE001 — a missing README is not an error
        blurb = ""
    _READMES[root] = (time.time(), blurb)
    return blurb


# Cached because analyze() walks the whole folder tree.
_STACK: dict[str, tuple[float, dict[str, Any]]] = {}
_STACK_TTL = 10 * 60


def _stack(root: str) -> dict[str, Any]:
    hit = _STACK.get(root)
    if hit and (time.time() - hit[0]) < _STACK_TTL:
        return hit[1]
    from core.domain import analyzer
    out = analyzer.analyze(root)
    _STACK[root] = (time.time(), out)
    return out


def prompt_section(query: str) -> str:
    """What brain.build_context_prompt injects.

    Three tiers, most specific first:

      1. The message names a project she knows → that project's full detail.
         This is what makes the chat, the sanctuary and the Domain feel like
         one system instead of three that happen to share a window.
      2. They're asking about the work in general → the expanded recall block.
      3. Anything else → the compact one-liner per recent project.

    Empty when the brain has nothing — never a placeholder, because an empty
    "Projects: (none)" line teaches the model to talk about having no projects.
    """
    focused = _safe(lambda: find_project(query), None)
    if focused:
        block = _safe(lambda: focus_block(focused, query), "")
        if block:
            # Still worth one line of "what else exists" so she can connect it
            # to the rest of the work, but the focused project leads.
            other = context_block(query)
            return block + (("\n\n" + other) if other else "")

    if is_work_question(query):
        expanded = answer_context(query)
        if expanded:
            return (
                expanded
                + "\n\n(They asked about the work. Answer from the above with "
                "SPECIFICS — name the project and what's actually open. If it "
                "genuinely isn't in there, say you're not sure and ask them.)"
            )
    return context_block(query)
