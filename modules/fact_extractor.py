"""AURA fact extraction — turn passing remarks into durable memory.

The visible failure on 2026-07-07 was AURA being *told* "its name was AURA"
and, a turn later, asking "can you remind me what it was?". The conversation
window alone can't fix that: once the line scrolls out, it's gone. Durable
facts are the fix — small, stable statements the user makes about themselves
or their work, saved once and injected into every future prompt.

Two capture paths, both best-effort and both writing to store.user_facts:

  * capture_heuristic(text) — instant, deterministic regex over the user's
    message. Cheap enough to run on every turn. Catches the obvious "my name
    is X", "the project is called X", "I'm learning X" statements.

  * capture_with_llm_async(...) — a throttled background pass that asks the
    light model to pull durable facts from the recent conversation. Runs in a
    daemon thread so it never adds latency to the reply, and only every few
    turns so it barely touches the rate limit.
"""

import re
import threading
import time

from memory import store

# ── Heuristic patterns ───────────────────────────────────────────────────────
# Each entry: (compiled regex, category). Group 1 is the captured value.
# Kept deliberately tight — a false "fact" is worse than a missed one because
# it gets injected into every prompt.
_STOP_VALUES = {
    "tired", "back", "here", "done", "good", "fine", "okay", "ok", "busy",
    "sorry", "sure", "ready", "trying", "working", "coding", "thinking",
    "not", "just", "still", "so", "also", "gonna", "going",
}

_PATTERNS = [
    # Project / thing names
    (re.compile(r"\bit'?s?\s+name\s+(?:is|was)\s+([A-Za-z0-9_\- ]{2,40})", re.I), "project"),
    (re.compile(r"\b(?:it'?s|its)\s+called\s+([A-Za-z0-9_\- ]{2,40})", re.I), "project"),
    (re.compile(r"\b(?:the\s+)?project\s+(?:is\s+)?(?:called|named)\s+([A-Za-z0-9_\- ]{2,40})", re.I), "project"),
    (re.compile(r"\bi'?m\s+(?:working on|building|making)\s+(?:a\s+|an\s+|my\s+)?([A-Za-z0-9_\- ]{2,40})", re.I), "project"),
    (re.compile(r"\bmy\s+project\s+is\s+(?:called\s+)?([A-Za-z0-9_\- ]{2,40})", re.I), "project"),
    # Identity
    (re.compile(r"\bmy\s+name\s+is\s+([A-Za-z0-9_\- ]{2,30})", re.I), "identity"),
    (re.compile(r"\bcall\s+me\s+([A-Za-z0-9_\- ]{2,30})", re.I), "identity"),
    (re.compile(r"\bi'?m\s+a\s+([A-Za-z ]{3,40}?\b(?:developer|engineer|student|dev|designer))", re.I), "identity"),
    # Learning / goals
    (re.compile(r"\bi'?m\s+(?:learning|studying)\s+([A-Za-z0-9_\-+ ]{2,40})", re.I), "learning"),
    (re.compile(r"\bpreparing\s+for\s+([A-Za-z0-9_\- ]{2,40})", re.I), "goal"),
    # Preferences
    (re.compile(r"\bi\s+(?:prefer|like|want)\s+([A-Za-z0-9_\- ]{3,40}\b(?:replies|responses|answers))", re.I), "preference"),
]


def _clean_value(value: str) -> str:
    v = value.strip().strip(".,!?;:'\"").strip()
    # Drop trailing filler clauses ("AURA and it's a mess" → "AURA")
    v = re.split(r"\b(?:and|but|because|so|which|that|when)\b", v, maxsplit=1)[0].strip()
    return v


def _is_meaningful(value: str) -> bool:
    if not value or len(value) < 2:
        return False
    low = value.lower()
    if low in _STOP_VALUES:
        return False
    # Reject values that are only stopword-ish filler.
    words = [w for w in re.split(r"\s+", low) if w]
    return any(w not in _STOP_VALUES for w in words)


def _phrase_for(category: str, value: str) -> str:
    return {
        "project": f"their project is called {value}",
        "identity": f"they are {value}" if " " in value else f"their name is {value}",
        "learning": f"they are learning {value}",
        "goal": f"they are preparing for {value}",
        "preference": f"they prefer {value}",
    }.get(category, f"{category}: {value}")


def capture_heuristic(text: str) -> list[str]:
    """Extract and persist obvious durable facts from one user message.
    Returns the list of fact strings saved (for logging/tests)."""
    if not text:
        return []
    saved = []
    for pattern, category in _PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        value = _clean_value(m.group(1))
        if not _is_meaningful(value):
            continue
        fact = _phrase_for(category, value)
        try:
            store.save_user_fact(fact, category)
            saved.append(fact)
        except Exception:
            pass
    if saved:
        print(f"[AURA Facts] captured: {saved}")
    return saved


# ── Throttled background LLM extraction ──────────────────────────────────────
_last_llm_run = 0.0
_turn_counter = 0
_LLM_EVERY_N_TURNS = 4
_LLM_MIN_INTERVAL_S = 90


def _llm_extract(recent_convo: str):
    try:
        from core.ai_router import call_groq_raw, GROQ_MODEL_LIGHT
    except Exception:
        return
    system = (
        "You extract durable facts about the user from a conversation — things "
        "worth remembering next week: their name, projects and project names, "
        "what they're learning, goals, strong preferences. Ignore momentary "
        "state (mood, what they're doing right now). Reply with 0-3 short facts, "
        "one per line, each phrased like 'their project is called X'. If nothing "
        "durable, reply with exactly NONE."
    )
    try:
        out = call_groq_raw(
            f"Conversation:\n{recent_convo}\n\nDurable facts:",
            system=system, max_tokens=120, temperature=0.2,
            model=GROQ_MODEL_LIGHT,
        )
    except Exception:
        return
    if not out or out.strip().upper().startswith("NONE"):
        return
    if out in ("RATE_LIMIT", "CONNECTION_ERROR"):
        return
    for line in out.splitlines():
        fact = line.strip().lstrip("-•* ").strip()
        if 4 <= len(fact) <= 120:
            try:
                store.save_user_fact(fact, "llm")
            except Exception:
                pass


def maybe_capture_with_llm():
    """Every few turns, kick a background thread that mines recent
    conversation for durable facts. Non-blocking and rate-limit friendly."""
    global _turn_counter, _last_llm_run
    _turn_counter += 1
    now = time.time()
    if _turn_counter % _LLM_EVERY_N_TURNS != 0:
        return
    if now - _last_llm_run < _LLM_MIN_INTERVAL_S:
        return
    _last_llm_run = now

    try:
        rows = store.get_recent_conversations(10)
    except Exception:
        return
    convo = "\n".join(
        f"{'User' if r == 'user' else 'AURA'}: {(m or '').strip()[:300]}"
        for r, m, _ in rows if (m or "").strip()
    )
    if not convo:
        return
    threading.Thread(target=_llm_extract, args=(convo,), daemon=True).start()


def capture(text: str):
    """Single entry point called on each real user message."""
    capture_heuristic(text)
    maybe_capture_with_llm()
