"""
core.domain.planning
--------------------
Phase-3/4 "AI Planning" for AURA Domain V2 — turn a plain conversation into a
structured feature plus tasks, then record the whole thing into the project
graph so it's linked from day one.

Two paths, same output shape:

    LLM path       ai_router produces strict JSON {feature, description, tasks[]}
    heuristic path deterministic split of the text into a feature + tasks

The heuristic runs whenever the model is unavailable or returns junk, so this
module is fully testable offline and never leaves the caller empty-handed.
"""

from __future__ import annotations

import json
import re
from typing import Any

from core.domain import project_brain

_PLAN_SYSTEM = (
    "You are a software planning engine. Convert the user's note into a single "
    "feature and its concrete engineering tasks. Reply with ONLY valid JSON, no "
    "prose, no markdown fences, in exactly this shape:\n"
    '{"feature": "<short title>", "description": "<one sentence>", '
    '"tasks": [{"title": "<imperative task>", "effort": "S|M|L"}]}\n'
    "6 tasks max. Tasks must be real build steps, not restatements."
)

# lines that look like an explicit task ("- OAuth", "□ Commit Parser", "1. Foo")
_BULLET = re.compile(r"^\s*(?:[-*•▢□☐]|\d+[.)])\s+(.*\S)")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
# leading filler we strip when turning a sentence into a task title
_FILLER = re.compile(
    r"^(?:we should|we need to|need to|let'?s|i want to|i think we should|"
    r"maybe|also|and|so|then|please)\s+", re.I,
)


def _clean_title(s: str) -> str:
    s = _FILLER.sub("", s.strip()).strip(" .,-–—")
    return s[:1].upper() + s[1:] if s else s


def _heuristic_plan(text: str) -> dict[str, Any]:
    """Deterministic fallback. Explicit bullet lines become tasks; otherwise
    each actionable sentence does. The feature title is the first line/sentence."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    bullets = [m.group(1).strip() for ln in lines if (m := _BULLET.match(ln))]

    if bullets:
        feature = _clean_title(lines[0]) if not _BULLET.match(lines[0]) else "New feature"
        task_titles = bullets
    else:
        sentences = [s.strip() for s in _SENT_SPLIT.split(text.replace("\n", " ")) if s.strip()]
        feature = _clean_title(sentences[0]) if sentences else "New feature"
        task_titles = sentences

    tasks = []
    seen = set()
    for t in task_titles:
        title = _clean_title(t)
        key = title.lower()
        if title and key not in seen and len(title) > 2:
            seen.add(key)
            tasks.append({"title": title, "effort": "M"})
        if len(tasks) >= 6:
            break
    if not tasks:  # single vague note — still give one task
        tasks = [{"title": feature, "effort": "M"}]
    return {"feature": feature or "New feature",
            "description": text.strip()[:200], "tasks": tasks}


def _llm_plan(text: str) -> dict[str, Any] | None:
    """Ask the model for a structured plan. Returns None on any failure so the
    caller falls back to the heuristic."""
    try:
        from core.ai_router import call_groq_raw
    except Exception:
        return None
    try:
        raw = call_groq_raw(text, _PLAN_SYSTEM, max_tokens=700, temperature=0.3)
    except Exception:
        return None
    if not raw or raw in ("RATE_LIMIT", "CONNECTION_ERROR"):
        return None
    # tolerate stray prose / fences around the JSON
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("tasks"):
        return None
    # normalize
    tasks = []
    for t in data["tasks"][:6]:
        if isinstance(t, str):
            tasks.append({"title": _clean_title(t), "effort": "M"})
        elif isinstance(t, dict) and t.get("title"):
            tasks.append({"title": str(t["title"]).strip(),
                          "effort": str(t.get("effort", "M")).upper()[:1] or "M"})
    if not tasks:
        return None
    return {
        "feature": str(data.get("feature") or "New feature").strip(),
        "description": str(data.get("description") or "").strip(),
        "tasks": tasks,
    }


def plan(text: str, use_llm: bool = True) -> dict[str, Any]:
    """Produce a structured plan from free text WITHOUT touching the graph.
    Useful for preview/confirm before committing tasks."""
    result = (_llm_plan(text) if use_llm else None) or _heuristic_plan(text)
    result["source"] = "llm" if (use_llm and _looks_llm(result)) else "heuristic"
    return result


def _looks_llm(result: dict) -> bool:
    # cheap marker so the caller/UI can tell which path produced the plan
    return bool(result.get("_llm"))


def plan_and_record(pid: str, text: str, from_node: str | None = None,
                    use_llm: bool = True) -> dict[str, Any]:
    """Phase-3+4: plan the text AND write it into the project graph. Records a
    discussion node for the raw text, a feature, and each task (belonging to the
    feature). Returns the created ids so a UI can navigate straight to them."""
    parsed = plan(text, use_llm=use_llm)

    discussion = project_brain.record_discussion(
        pid, parsed["feature"], body=text, from_idea=from_node)
    feature = project_brain.add_feature(
        pid, parsed["feature"], description=parsed["description"],
        status="planning", from_node=discussion["id"])

    task_nodes = []
    for t in parsed["tasks"]:
        node = project_brain.add_task(
            pid, t["title"], feature_id=feature["id"],
            status="todo", effort=t.get("effort", "M"))
        task_nodes.append({"id": node["id"], "title": node["title"],
                           "effort": t.get("effort", "M")})

    return {
        "ok": True,
        "source": parsed["source"],
        "discussion_id": discussion["id"],
        "feature": {"id": feature["id"], "title": feature["title"]},
        "tasks": task_nodes,
    }
