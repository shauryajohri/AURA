"""
core.domain.idea_capture
------------------------
The heart of AURA Domain V2 — turn ordinary conversation into structured
project knowledge, automatically. This is the "Idea Capture" flow from the spec:

    Conversation -> idea detected -> structured feature -> tasks created
                 -> discussion linked -> decision extracted -> knowledge kept

One entry point, `capture(pid, text)`, classifies each utterance and routes it:

    feature   "we should have a real-time dashboard"  -> feature + auto tasks
    decision  "maybe use PostgreSQL because it scales" -> decision + reason
    edit      "actually make the map 3D"               -> rewrite matching task
    note      "why are we using websockets?"           -> discussion note

Plus `expand_task` (subtasks) and `ask` (Step-10 "ask anything" over the graph).

Every route has an LLM path (ai_router, strict JSON) AND a deterministic
heuristic fallback, so nothing here needs the network to work — it just works
*better* with it.
"""

from __future__ import annotations

import json
import re
from typing import Any

from core.domain import brain_store as store
from core.domain import project_brain, planning


# ── LLM helper ───────────────────────────────────────────────────────────────
def _llm_json(system: str, text: str, max_tokens: int = 600) -> dict | None:
    """Call the model and parse a single JSON object, or None on any failure."""
    try:
        from core.ai_router import call_groq_raw
        raw = call_groq_raw(text, system, max_tokens=max_tokens, temperature=0.2)
    except Exception:
        return None
    if not raw or raw in ("RATE_LIMIT", "CONNECTION_ERROR"):
        return None
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


# ── classification ───────────────────────────────────────────────────────────
_EDIT_RE = re.compile(
    r"^\s*(?:actually|instead|change|rename|make (?:it|the)|update|let'?s make|"
    r"scrap|replace|turn (?:it|the))\b", re.I,
)
_DECISION_RE = re.compile(
    r"\b(?:use|go with|switch to|prefer|choose|chose|decided|instead of|"
    r"rather than|because|since it|it scales|will scale)\b", re.I,
)
_FEATURE_RE = re.compile(
    r"\b(?:we should have|we need|need a|add|build|create|make a|implement|"
    r"support|feature|dashboard|page|screen|integration|system|api|auth"
    r"|authentication|login)\b", re.I,
)
# tech tokens that make a "decision" reading more likely
_TECH = re.compile(
    r"\b(postgres(?:ql)?|sqlite|mysql|mongo(?:db)?|redis|kafka|rabbitmq|"
    r"jwt|oauth|websocket|graphql|rest|cesium|three\.?js|docker|kubernetes|"
    r"react|vue|svelte|fastapi|flask|django|s3|nginx)\b", re.I,
)


def classify(text: str) -> str:
    """feature | decision | edit | note — heuristic; LLM refines in capture()."""
    t = text.strip()
    if _EDIT_RE.search(t):
        return "edit"
    has_tech = bool(_TECH.search(t))
    has_decision = bool(_DECISION_RE.search(t))
    has_feature = bool(_FEATURE_RE.search(t))
    # "use Kafka instead of RabbitMQ" / "PostgreSQL because it scales"
    if has_tech and has_decision and not has_feature:
        return "decision"
    if has_feature:
        return "feature"
    if has_tech and has_decision:
        return "decision"
    return "note"


# ── feature extraction ───────────────────────────────────────────────────────
_FEATURE_SYSTEM = (
    "Extract a software FEATURE from the user's note. Reply ONLY with JSON:\n"
    '{"title":"<3-6 word clean feature name>","description":"<one clear '
    'sentence>","priority":"High|Medium|Low","category":"Frontend|Backend|'
    'Infra|Auth|Data|Other","tasks":["<imperative task>", ...]}\n'
    "Clean up rambling into concise structure. 5-7 tasks. No prose."
)

_CATEGORY_HINTS = [
    ("Auth", r"auth|login|oauth|jwt|session|password|register"),
    ("Frontend", r"ui|dashboard|page|screen|map|animation|design|futuristic|frontend|button"),
    ("Data", r"database|postgres|sqlite|analytics|prediction|pollution|traffic|data|store"),
    ("Infra", r"kafka|rabbitmq|redis|docker|kubernetes|deploy|websocket|queue|scal"),
    ("Backend", r"api|endpoint|server|backend|service"),
]


def _guess_category(text: str) -> str:
    for cat, pat in _CATEGORY_HINTS:
        if re.search(pat, text, re.I):
            return cat
    return "Other"


def _guess_priority(text: str) -> str:
    if re.search(r"\b(critical|urgent|must|high priority|asap|core)\b", text, re.I):
        return "High"
    if re.search(r"\b(maybe|later|eventually|nice to have|someday)\b", text, re.I):
        return "Low"
    return "Medium"


def extract_feature(text: str, use_llm: bool = True) -> dict[str, Any]:
    """Turn a natural note into a clean, structured feature + tasks."""
    if use_llm:
        data = _llm_json(_FEATURE_SYSTEM, text)
        if data and data.get("title") and data.get("tasks"):
            tasks = [str(t).strip() for t in data["tasks"] if str(t).strip()][:7]
            return {
                "title": str(data["title"]).strip(),
                "description": str(data.get("description") or "").strip(),
                "priority": str(data.get("priority") or "Medium").capitalize(),
                "category": str(data.get("category") or _guess_category(text)).capitalize(),
                "tasks": tasks or planning.plan(text, use_llm=False)["tasks"],
                "source": "llm",
            }
    # heuristic: reuse the planner for title+tasks, add priority/category
    p = planning.plan(text, use_llm=False)
    return {
        "title": p["feature"],
        "description": p["description"],
        "priority": _guess_priority(text),
        "category": _guess_category(text),
        "tasks": [t["title"] for t in p["tasks"]],
        "source": "heuristic",
    }


# ── decision extraction ──────────────────────────────────────────────────────
_DECISION_SYSTEM = (
    "The user rambled about a technical choice. Extract the DECISION. Reply "
    'ONLY with JSON: {"topic":"<what is being decided, 1-3 words>","choice":'
    '"<what they chose>","reason":"<short why>"}. No prose.'
)


def extract_decision(text: str, use_llm: bool = True) -> dict[str, Any]:
    if use_llm:
        d = _llm_json(_DECISION_SYSTEM, text)
        if d and d.get("choice"):
            return {
                "topic": str(d.get("topic") or "Decision").strip(),
                "choice": str(d["choice"]).strip(),
                "reason": str(d.get("reason") or "").strip(),
                "source": "llm",
            }
    # heuristic: choice = first tech token; reason = clause after "because/since"
    tech = _TECH.search(text)
    choice = tech.group(0) if tech else ""
    reason = ""
    m = re.search(r"\b(?:because|since|so that|as)\b\s+(.*)", text, re.I)
    if m:
        reason = m.group(1).strip().rstrip(".")[:160]
    # topic guess from category
    topic = _guess_category(text)
    return {
        "topic": topic if topic != "Other" else "Decision",
        "choice": choice or "(unspecified)",
        "reason": reason,
        "source": "heuristic",
    }


# ── natural-language edit ─────────────────────────────────────────────────────
def _tokenize(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) > 2}


def _best_task_match(pid: str, text: str) -> dict[str, Any] | None:
    """Find the existing task an edit instruction is most likely about, by word
    overlap with the instruction."""
    words = _tokenize(_EDIT_RE.sub("", text))
    best, best_score = None, 0
    for t in store.nodes(pid, "task"):
        overlap = len(words & _tokenize(t["title"]))
        if overlap > best_score:
            best, best_score = t, overlap
    return best if best_score > 0 else None


_EDIT_SYSTEM = (
    "Rewrite the task title to reflect the user's change. Reply ONLY with JSON: "
    '{"title":"<new task title>"}. Keep it a short imperative task.'
)


def apply_edit(pid: str, text: str, task_id: str | None = None,
               use_llm: bool = True) -> dict[str, Any]:
    """'Actually make the map 3D' -> rewrite the matching task's title."""
    task = store.get_node(task_id) if task_id else _best_task_match(pid, text)
    if not task or task["type"] != "task":
        return {"ok": False, "error": "no matching task to edit"}

    new_title = None
    if use_llm:
        prompt = f"Current task: {task['title']}\nChange requested: {text}"
        d = _llm_json(_EDIT_SYSTEM, prompt, max_tokens=60)
        if d and d.get("title"):
            new_title = str(d["title"]).strip()
    if not new_title:
        # heuristic: fold the requested qualifier into the old title
        qualifier = _EDIT_RE.sub("", text).strip().rstrip(".")
        new_title = f"{qualifier[:1].upper()}{qualifier[1:]}" if qualifier else task["title"]

    old = task["title"]
    updated = store.update_node(task["id"], title=new_title,
                                meta={"edit_history": task["meta"].get("edit_history", []) + [old]})
    return {"ok": True, "task_id": task["id"], "old": old, "new": updated["title"]}


# ── subtask expansion ────────────────────────────────────────────────────────
_SUBTASK_SYSTEM = (
    "Break the task into concrete subtasks. Reply ONLY with JSON: "
    '{"subtasks":["<imperative subtask>", ...]}. 3-6 items, no prose.'
)

# canned expansions so common tasks work offline
_CANNED_SUBTASKS = {
    "authentication": ["Login", "Register", "OAuth", "Password Reset", "Session Management"],
    "auth": ["Login", "Register", "OAuth", "Password Reset", "Session Management"],
    "login": ["Login form UI", "Credential validation", "Error handling"],
    "testing": ["Unit tests", "Integration tests", "Edge cases"],
    "api endpoints": ["Define routes", "Request validation", "Responses", "Error handling"],
    "dashboard": ["Layout", "Data wiring", "Live updates", "Empty/error states"],
}


def expand_task(pid: str, task_id: str, use_llm: bool = True) -> dict[str, Any]:
    """Generate subtasks for a task and add them as tasks linked by belongs_to."""
    task = store.get_node(task_id)
    if not task or task["type"] != "task":
        return {"ok": False, "error": "task not found"}

    subs: list[str] = []
    if use_llm:
        d = _llm_json(_SUBTASK_SYSTEM, task["title"], max_tokens=200)
        if d and isinstance(d.get("subtasks"), list):
            subs = [str(s).strip() for s in d["subtasks"] if str(s).strip()][:6]
    if not subs:
        subs = _CANNED_SUBTASKS.get(task["title"].lower().strip(), [])
    if not subs:
        return {"ok": False, "error": "could not expand (offline + no canned match)"}

    created = []
    for s in subs:
        node = store.add_node(pid, "task", s, status="todo",
                              meta={"parent_task": task_id})
        store.add_edge(pid, node["id"], task_id, "belongs_to")
        created.append({"id": node["id"], "title": s})
    return {"ok": True, "parent": task_id, "subtasks": created}


# ── the router ───────────────────────────────────────────────────────────────
def capture(pid: str, text: str, feature_id: str | None = None,
            use_llm: bool = True) -> dict[str, Any]:
    """Classify one utterance and fold it into the project graph. Returns what
    was created so a UI can confirm ("Add these tasks?") or navigate to it.

    `feature_id` scopes notes/decisions/edits to a feature's conversation."""
    text = text.strip()
    if not text:
        return {"ok": False, "error": "empty"}

    kind = classify(text)

    if kind == "edit":
        res = apply_edit(pid, text, task_id=None, use_llm=use_llm)
        return {"ok": res["ok"], "kind": "edit", **res}

    if kind == "decision":
        d = extract_decision(text, use_llm=use_llm)
        title = f"{d['topic']}: {d['choice']}" if d["topic"] else d["choice"]
        node = project_brain.record_decision(
            pid, title, reason=d["reason"], from_node=feature_id)
        return {"ok": True, "kind": "decision", "decision": d,
                "node_id": node["id"]}

    if kind == "feature":
        f = extract_feature(text, use_llm=use_llm)
        discussion = project_brain.record_discussion(pid, f["title"], body=text)
        feature = project_brain.add_feature(
            pid, f["title"], description=f["description"], status="planning",
            from_node=discussion["id"])
        store.update_node(feature["id"], meta={
            "priority": f["priority"], "category": f["category"]})
        tasks = []
        for t in f["tasks"]:
            node = project_brain.add_task(pid, t, feature_id=feature["id"],
                                          status="todo")
            tasks.append({"id": node["id"], "title": t})
        return {
            "ok": True, "kind": "feature", "source": f["source"],
            "feature": {"id": feature["id"], "title": f["title"],
                        "priority": f["priority"], "category": f["category"],
                        "description": f["description"]},
            "tasks": tasks,           # UI shows these with an "Add these?" confirm
        }

    # note: attach to the feature's conversation (or project root)
    node = project_brain.record_discussion(pid, text[:60], body=text,
                                           from_idea=feature_id)
    return {"ok": True, "kind": "note", "node_id": node["id"]}


# ── ask anything (Step 10) ───────────────────────────────────────────────────
_ASK_SYSTEM = (
    "You are AURA answering a question about a software project. Use ONLY the "
    "CONTEXT provided (decisions, discussions, tasks, files, commits). Be "
    "concise and concrete. If the context doesn't contain the answer, say what "
    "IS known and note the gap. No markdown headers."
)


def _gather_context(pid: str, node_id: str) -> dict[str, Any]:
    """Everything the graph knows around a node: the causal chain (why it
    exists), one-hop neighbours grouped by relation, and any decisions/files."""
    target = store.get_node(node_id)
    if not target:
        return {}
    chain = store.trace_back(node_id)
    grouped: dict[str, list[dict]] = {}
    for e in store.edges_of(node_id, "both"):
        other_id = e["dst"] if e["src"] == node_id else e["src"]
        other = store.get_node(other_id)
        if other:
            grouped.setdefault(e["type"], []).append(other)
    # also pull decisions for the whole project (small graphs) so "why X" works
    decisions = store.nodes(pid, "decision")
    return {"target": target, "chain": chain, "related": grouped,
            "decisions": decisions}


def _context_text(ctx: dict[str, Any]) -> str:
    lines: list[str] = []
    t = ctx.get("target")
    if t:
        lines.append(f"FOCUS: {t['type']} — {t['title']}")
        if t.get("body"):
            lines.append(f"  note: {t['body']}")
    chain = ctx.get("chain") or []
    if len(chain) > 1:
        lines.append("ORIGIN CHAIN: " + " -> ".join(
            f"{n['type']}:{n['title']}" for n in chain))
    for rel, nodes in (ctx.get("related") or {}).items():
        for n in nodes[:8]:
            extra = f" ({n['meta'].get('reason')})" if n["meta"].get("reason") else ""
            lines.append(f"{rel}: {n['type']} — {n['title']}{extra}")
    for d in (ctx.get("decisions") or [])[:12]:
        if d.get("status") == "rejected":
            continue
        reason = d["meta"].get("reason", "")
        lines.append(f"decision: {d['title']}" + (f" — {reason}" if reason else ""))
    return "\n".join(lines)


def ask(pid: str, node_id: str, question: str,
        use_llm: bool = True) -> dict[str, Any]:
    """Step-10 'ask anything': answer a natural-language question about a
    feature/task using the graph as grounding. Falls back to returning the
    assembled context when offline so the caller always gets the facts."""
    ctx = _gather_context(pid, node_id)
    if not ctx:
        return {"ok": False, "error": "node not found"}
    context_text = _context_text(ctx)

    if use_llm:
        prompt = f"CONTEXT:\n{context_text}\n\nQUESTION: {question}"
        try:
            from core.ai_router import call_groq_raw
            answer = call_groq_raw(prompt, _ASK_SYSTEM, max_tokens=400,
                                   temperature=0.3)
        except Exception:
            answer = ""
        if answer and answer not in ("RATE_LIMIT", "CONNECTION_ERROR"):
            return {"ok": True, "answer": answer.strip(), "grounded_in": context_text,
                    "source": "llm"}

    # offline: return the grounding so the user still sees the relevant facts
    return {
        "ok": True,
        "answer": context_text or "No linked context yet for this item.",
        "grounded_in": context_text,
        "source": "context-only",
    }
