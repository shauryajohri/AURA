"""
core.work_recall
----------------
What AURA remembers about your recent sessions, assembled for a chat turn.

Ask "what were we doing last time?" and the model should answer from the
stored session summary and recaps, not guess from eight lines of history.

    answer_context(query)  last session + earlier recaps, for memory questions.
    prompt_section(query)  what brain.build_context_prompt injects — only when
                           the message is actually asking about past work.

(This used to read the AURA Domain project graph too. Domain was removed when
AURA became a companion rather than a dev workspace; the graph is still in
git history at commit c752187.)

Design rules:
  · Never raise. A chat turn must not fail because a table is missing; every
    read is wrapped and every failure degrades to less context, never an error.
  · Never invent. If nothing is stored, return "" and let AURA say it's fuzzy.
  · Stay short. This is prompt budget shared with facts, screen and history.
"""

from __future__ import annotations

import re
from typing import Any, Callable

# Questions that are ASKING about past work rather than doing it.
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


def is_work_question(query: str) -> bool:
    """True when the message is asking about the work itself."""
    return bool(query and _RECALL_RE.search(query))


def _safe(fn: Callable[[], Any], default: Any) -> Any:
    try:
        return fn()
    except Exception:
        return default


# ── the companion's own view: recaps, last session ───────────────────────────
def _recaps(limit: int = 3) -> list[str]:
    from memory import store
    rows = store.get_all_snapshots(limit)
    return [f"{r[1]}: {str(r[2])[:160]}" for r in rows if r and r[2]]


def _last_session() -> str:
    from memory import store
    last = store.get_last_session()
    return (last or {}).get("summary") or ""


# ── the blocks ───────────────────────────────────────────────────────────────
def answer_context(query: str = "") -> str:
    """Everything worth knowing when they ask about past work.

    Used by the RECALL path and by prompt_section. Still capped — this is a
    prompt, not a report.
    """
    chunks: list[str] = []

    last = _safe(_last_session, "")
    if last:
        chunks.append(f"LAST SESSION: {last}")

    recaps = _safe(lambda: _recaps(3), [])
    if recaps:
        chunks.append("EARLIER SESSIONS:\n" + "\n".join(f"- {r}" for r in recaps))

    return "\n\n".join(chunks)


def prompt_section(query: str) -> str:
    """What brain.build_context_prompt injects.

    Empty unless they're asking about past work, and empty when nothing is
    stored — never a placeholder, because an empty "Sessions: (none)" line
    teaches the model to talk about having no memory.
    """
    if not is_work_question(query):
        return ""
    expanded = answer_context(query)
    if not expanded:
        return ""
    return (
        expanded
        + "\n\n(They asked about past work. Answer from the above with "
        "SPECIFICS. If it genuinely isn't in there, say you're not sure and "
        "ask them.)"
    )
