"""
AURA's tool layer — the *pull* side of context.

Everything in build_context_prompt is PUSH: facts, room brief, screen text,
recent turns, all assembled whether the model wants them or not. A tool is the
other direction — the model asks for something and we go get it. That is what
lets AURA answer a question about her own codebase by actually looking at it
instead of guessing from eight lines of chat history.

Protocol (parse-and-loop, model-agnostic — see core/tool_loop):
    the model emits ONE line and nothing else:
        FETCH: <name> <json-args>
    we run it and hand back:
        RESULT: <name> -> <text>
    it then requests another lookup or writes the answer. When it needs
    nothing it emits `FETCH: none`.

    The verb is FETCH, not "tool" / "call" / "function": Groq's gpt-oss
    models treat that vocabulary as a cue to emit a NATIVE tool call, which
    the API then rejects because we send no tools array. FETCH keeps the
    model in plain-text completion where the shim can actually read it.

v1 is read-only on purpose. A tool that mutates state (switch room, save a
fact) could get the "wrong switch tears the conversation from its history"
failure the room router works hard to avoid — so those wait until the read
loop has proven itself. Every tool here degrades to a short string on
failure: a tool that raises would take the whole turn down, and the turn
matters more than the lookup.
"""

from __future__ import annotations

import json
import os
import re
import subprocess

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MAX_ARG_LEN = 400          # clamp a single string arg before it reaches a tool
MAX_RESULT_LEN = 1600      # clamp a tool's output before it reaches the model
_GIT_TIMEOUT = 4           # seconds — a slow repo must not stall the turn

_STOP = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "how", "does",
    "do", "did", "what", "where", "when", "why", "who", "which", "this", "that",
    "for", "with", "from", "into", "our", "we", "it", "its", "to", "of", "in",
    "on", "at", "be", "can", "you", "your", "i", "me", "my", "aura", "code",
}


def _git(*args: str) -> str:
    """Run a git command in the AURA repo. '' on any failure — never raises."""
    try:
        out = subprocess.run(
            ["git", *args], cwd=_REPO, capture_output=True, text=True,
            timeout=_GIT_TIMEOUT, check=False,
        )
        return (out.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


# ── tools ──────────────────────────────────────────────────────────────────

def _repo_state(**_) -> str:
    """Current git branch, uncommitted changes, and the last few commits."""
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "?"
    status = _git("status", "--porcelain")
    log = _git("log", "--oneline", "-5")
    changed = [ln for ln in status.splitlines() if ln.strip()][:20]
    parts = [f"repo: AURA   branch: {branch}"]
    if changed:
        parts.append("uncommitted:\n" + "\n".join("  " + c for c in changed))
    else:
        parts.append("working tree clean")
    if log:
        parts.append("recent commits:\n" + "\n".join("  " + l for l in log.splitlines()))
    return "\n".join(parts)


def _keywords(query: str, limit: int = 5) -> list[str]:
    words = [w for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", query or "")
             if w.lower() not in _STOP]
    seen, out = set(), []
    for w in words:
        k = w.lower()
        if k not in seen:
            seen.add(k)
            out.append(w)
    return out[:limit]


def _grep_frontend(query: str) -> str:
    """git grep across the TS/TSX frontend — project_context only indexes .py,
    and 'the room picker' lives entirely in .tsx."""
    terms = _keywords(query)
    if not terms:
        return ""
    args = ["grep", "-n", "-i", "-I"]
    for t in terms:
        args += ["-e", t]
    args += ["--", "frontend/src/*", "frontend/src/**/*"]
    raw = _git(*args)
    if not raw:
        return ""
    lines = raw.splitlines()[:14]
    return "\n".join(lines)


def _search_code(query: str = "", **_) -> str:
    """Semantic search over AURA's Python source, plus a literal grep over the
    TypeScript frontend. Use for 'how does X work', 'where is Y handled'."""
    query = (query or "").strip()
    if not query:
        return "search_code needs a query"
    blocks: list[str] = []
    try:
        from modules.project_context import get_relevant_context
        py = get_relevant_context(query)
        if py:
            blocks.append("— Python (semantic) —\n" + py)
    except Exception as e:  # noqa: BLE001
        blocks.append(f"(python search unavailable: {e})")
    fe = _grep_frontend(query)
    if fe:
        blocks.append("— frontend (literal matches) —\n" + fe)
    return "\n\n".join(blocks) if blocks else "(nothing matched)"


def _recall_project(query: str = "", **_) -> str:
    """What AURA knows about the project itself: features, open tasks, recent
    decisions, session recaps, where we left off."""
    try:
        from core import work_recall
        return work_recall.answer_context(query or "") or "(nothing recorded about the project yet)"
    except Exception as e:  # noqa: BLE001
        return f"project recall unavailable: {e}"


def _list_rooms(**_) -> str:
    """Every room, its topic, and which one is currently active."""
    try:
        from memory import store
        rooms = store.list_rooms()
        active = store.active_room()
        aid = active["id"] if active else None
        if not rooms:
            return "no rooms yet"
        out = []
        for r in rooms:
            mark = " (active)" if r["id"] == aid else ""
            out.append(f"- {r['name']}{mark}: {r.get('topic') or '—'} [{r.get('chats', 0)} chats]")
        return "\n".join(out)
    except Exception as e:  # noqa: BLE001
        return f"rooms unavailable: {e}"


TOOLS: dict[str, dict] = {
    "repo_state": {
        "fn": _repo_state, "args": "{}",
        "help": "git branch, uncommitted files and recent commits of the AURA codebase",
    },
    "search_code": {
        "fn": _search_code, "args": '{"query": "..."}',
        "help": "search AURA's own source (Python + the TS/TSX frontend)",
    },
    "recall_project": {
        "fn": _recall_project, "args": '{"query": "..."}',
        "help": "what AURA knows about the project: features, open tasks, decisions, where we left off",
    },
    "list_rooms": {
        "fn": _list_rooms, "args": "{}",
        "help": "every room and which one is active",
    },
}


def catalogue() -> str:
    return "\n".join(f"  {n} {t['args']}  — {t['help']}" for n, t in TOOLS.items())


_CALL_RE = re.compile(r"(?i)^(?:fetch|lookup|tool)\s*:\s*")


def parse_tool_call(text: str) -> tuple[str, dict] | None:
    """First `FETCH:`/`LOOKUP:`/`TOOL:` line of `text` → (name, args) or
    ("none", {}), or None if there is no lookup line at all. Tolerant: bad
    JSON falls back to treating the remainder as the single obvious arg, and
    the line may sit below a preamble the model wasn't supposed to write."""
    stripped = (text or "").strip()
    if not stripped:
        return None
    line = ""
    for raw in stripped.splitlines():
        cand = raw.strip().strip("`*> ").strip()
        if _CALL_RE.match(cand):
            line = cand
            break
    if not line:
        return None
    rest = _CALL_RE.sub("", line).strip()
    if not rest or rest.lower().startswith("none"):
        return ("none", {})
    parts = rest.split(None, 1)
    name = parts[0].strip().strip('"`,')
    raw = parts[1].strip() if len(parts) > 1 else ""
    if not raw:
        return (name, {})
    try:
        args = json.loads(raw)
        if not isinstance(args, dict):
            raise ValueError
    except Exception:  # noqa: BLE001
        val = raw.strip().strip('"`').strip()
        args = {"query": val}
    return (name, args)


def run_tool(name: str, args: dict) -> str:
    spec = TOOLS.get(name)
    if not spec:
        return f"no such tool '{name}'. available: {', '.join(TOOLS)}"
    clean = {}
    for k, v in (args or {}).items():
        clean[k] = v[:MAX_ARG_LEN] if isinstance(v, str) else v
    try:
        out = spec["fn"](**clean)
    except TypeError:
        # model passed an arg the tool doesn't take — retry with nothing
        try:
            out = spec["fn"]()
        except Exception as e:  # noqa: BLE001
            return f"{name} failed: {e}"
    except Exception as e:  # noqa: BLE001
        return f"{name} failed: {e}"
    out = (out or "").strip()
    return out[:MAX_RESULT_LEN] or "(nothing found)"
