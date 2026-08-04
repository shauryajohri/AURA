"""AI Task Assistant — turn conversation into a clean, estimated task list.

Three jobs, all of which degrade gracefully to rules when the model is
unavailable (locked, rate-limited, offline):

  extract(text)  → action items buried in a discussion, as real tasks
  rewrite(title) → one messy line ("fix that stupid bug in login lol")
                   rewritten as something you'd be happy to read next week
  estimate(...)  → complexity + rough hours, grouped by theme

Nothing here writes to the database. The caller shows the suggestions, the
user accepts them, and only then are they stored (with origin="aura") — a
task list that fills itself without asking is a task list people stop trusting.
"""
from __future__ import annotations

import json
import re
from typing import Any

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = """You extract ACTION ITEMS from a conversation or notes.

Return ONLY valid JSON, no prose, in exactly this shape:
{"tasks":[{"title":"...","group":"...","complexity":"low|medium|high","hours":2,"priority":"high|medium|low"}]}

RULES:
- title: imperative, specific, self-contained. "Add rate limiting to the login endpoint", NOT "rate limiting" or "we should probably look at rate limiting".
- Only real, actionable work. Ignore opinions, questions, greetings, and things already done.
- group: a 1-2 word theme shared by related tasks (e.g. "auth", "ui polish", "database").
- hours: your honest estimate of focused work, a number. Use 0.5 for trivial.
- Maximum 8 tasks. Fewer is better than padded.
- If there is no real work in the text, return {"tasks":[]}."""

_REWRITE_SYSTEM = """You rewrite a rough task title into a clear, professional one.

Return ONLY valid JSON: {"title":"...","complexity":"low|medium|high","hours":2}

RULES:
- Keep the original INTENT exactly. Never invent scope that wasn't there.
- Imperative mood, specific, no filler, no profanity, no "we should".
- Under 80 characters.
- hours: honest estimate of focused work."""


# ---------------------------------------------------------------------------
# Model plumbing
# ---------------------------------------------------------------------------

def _ask(prompt: str, system: str, max_tokens: int = 700) -> dict[str, Any] | None:
    """One JSON round-trip. Returns None on ANY failure so callers fall back."""
    try:
        from core.ai_router import call_groq_raw
    except Exception:  # noqa: BLE001
        return None
    try:
        raw = call_groq_raw(prompt, system, max_tokens=max_tokens, temperature=0.2)
    except Exception:  # noqa: BLE001
        return None
    if not raw or raw in ("RATE_LIMIT", "CONNECTION_ERROR"):
        return None
    m = re.search(r"\{.*\}", raw, re.S)   # tolerate fences / stray prose
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# Heuristic fallbacks — no model required
# ---------------------------------------------------------------------------

# Lines that sound like commitments. Deliberately conservative: a missed task
# is a small annoyance, a hallucinated one is noise the user has to clean up.
_CUE = re.compile(
    r"\b(need to|needs to|have to|should|must|todo|to-do|let'?s|i'?ll|we'?ll|"
    r"gonna|going to|next step|remember to|don'?t forget|fix|add|build|"
    r"implement|refactor|write|create|update|remove|test|deploy)\b",
    re.I,
)
_DONE = re.compile(r"\b(done|finished|completed|already|shipped|fixed it)\b", re.I)
_FILLER = re.compile(
    r"^\s*(ok(ay)?|so|well|hmm+|yeah|yep|nah|right|anyway|basically|like|"
    r"also|and|then|plus|oh|um+|actually|maybe|probably)\b[,\s]*",
    re.I,
)

_BIG = re.compile(r"\b(refactor|migrate|redesign|rewrite|architecture|integrat\w+|auth\w*|deploy\w*)\b", re.I)
_SMALL = re.compile(r"\b(typo|rename|tweak|bump|comment|log|color|colour|padding|spacing)\b", re.I)


def _clean_title(s: str) -> str:
    """Strip conversational scaffolding off a line so it reads like a task."""
    s = s.strip().strip("-*•+ \t")
    # Conversation stacks filler ("ok so also we should…"), so peel it in a
    # loop rather than assuming one word — and re-peel after each modal strip.
    for _ in range(6):
        before = s
        s = _FILLER.sub("", s)
        # "we need to add X" → "add X";  "i'll fix Y" → "fix Y"
        s = re.sub(r"^\s*(i|we|you)\s*(really\s+)?('ll|will|need to|needs to|have to|"
                   r"should|must|gotta|are gonna|am gonna)\s+", "", s, flags=re.I)
        s = re.sub(r"^\s*(let'?s|todo:?|to-do:?|remember to|don'?t forget to|"
                   r"next step:?|action item:?)\s+", "", s, flags=re.I)
        if s == before:
            break
    # Trailing editorialising: "…, its a mess" / "… lol"
    s = re.sub(r"\s*,\s*(it'?s|its|thats|that'?s)\s+\w+(\s+\w+)?\s*$", "", s, flags=re.I)
    s = re.sub(r"\s+\b(lol|lmao|haha|ugh|pls|plz)\b\s*$", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" .,;:")
    if not s:
        return ""
    return s[0].upper() + s[1:]


def _guess_complexity(title: str) -> tuple[str, float]:
    """(complexity, hours) from the words used. Crude but honest."""
    if _BIG.search(title):
        return "high", 6.0
    if _SMALL.search(title) or len(title) < 28:
        return "low", 0.5
    return "medium", 2.0


def _heuristic_extract(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    # Sentence-ish splitting: newlines and terminators both end an item.
    for chunk in re.split(r"[\n\r]+|(?<=[.!?])\s+", text or ""):
        chunk = chunk.strip()
        if len(chunk) < 8 or len(chunk) > 240:
            continue
        if _DONE.search(chunk) or not _CUE.search(chunk):
            continue
        title = _clean_title(chunk)
        if len(title) < 6:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        complexity, hours = _guess_complexity(title)
        out.append({
            "title": title[:120],
            "group": "general",
            "complexity": complexity,
            "hours": hours,
            "priority": "high" if complexity == "high" else "medium",
        })
        if len(out) >= 8:
            break
    return out


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_COMPLEXITY = {"low", "medium", "high"}
_PRIORITY = {"low", "medium", "high"}


def _norm_task(t: Any) -> dict[str, Any] | None:
    if isinstance(t, str):
        title = _clean_title(t)
        if not title:
            return None
        c, h = _guess_complexity(title)
        return {"title": title[:120], "group": "general", "complexity": c,
                "hours": h, "priority": "medium"}
    if not isinstance(t, dict):
        return None
    title = _clean_title(str(t.get("title") or ""))
    if len(title) < 4:
        return None
    complexity = str(t.get("complexity", "medium")).lower().strip()
    if complexity not in _COMPLEXITY:
        complexity = "medium"
    priority = str(t.get("priority", "medium")).lower().strip()
    if priority not in _PRIORITY:
        priority = "medium"
    try:
        hours = round(float(t.get("hours", 2)), 1)
    except Exception:  # noqa: BLE001
        hours = 2.0
    hours = max(0.25, min(80.0, hours))
    group = str(t.get("group") or "general").strip().lower()[:24] or "general"
    return {"title": title[:120], "group": group, "complexity": complexity,
            "hours": hours, "priority": priority}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract(text: str, use_llm: bool = True) -> dict[str, Any]:
    """Pull action items out of a conversation. Never writes anything."""
    text = (text or "").strip()
    if not text:
        return {"ok": True, "tasks": [], "source": "empty", "groups": []}

    try:
        from core import activity
        activity.emit("Extracting tasks…", "task")
    except Exception:  # noqa: BLE001
        pass

    tasks: list[dict[str, Any]] = []
    source = "heuristic"
    if use_llm:
        # Long conversations get trimmed to the tail — recent intent is what
        # people mean by "what did we just decide".
        payload = text[-6000:]
        data = _ask(payload, _EXTRACT_SYSTEM)
        if data and isinstance(data.get("tasks"), list):
            for raw in data["tasks"][:8]:
                n = _norm_task(raw)
                if n:
                    tasks.append(n)
            if tasks:
                source = "llm"

    if not tasks:
        tasks = _heuristic_extract(text)

    # Group similar tasks so the UI can show them together.
    groups: dict[str, list[str]] = {}
    for t in tasks:
        groups.setdefault(t["group"], []).append(t["title"])

    total_hours = round(sum(t["hours"] for t in tasks), 1)
    return {
        "ok": True,
        "source": source,
        "tasks": tasks,
        "groups": [{"name": g, "count": len(v)} for g, v in sorted(groups.items())],
        "total_hours": total_hours,
    }


def rewrite(title: str, use_llm: bool = True) -> dict[str, Any]:
    """Clean up one task title and estimate it."""
    original = (title or "").strip()
    if not original:
        return {"ok": False, "error": "title required"}

    if use_llm:
        data = _ask(original, _REWRITE_SYSTEM, max_tokens=200)
        if data and data.get("title"):
            n = _norm_task(data)
            if n:
                return {"ok": True, "source": "llm", "original": original, **n}

    cleaned = _clean_title(original) or original
    complexity, hours = _guess_complexity(cleaned)
    return {"ok": True, "source": "heuristic", "original": original,
            "title": cleaned[:120], "group": "general",
            "complexity": complexity, "hours": hours, "priority": "medium"}
