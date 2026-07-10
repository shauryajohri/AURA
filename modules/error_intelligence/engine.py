# modules/error_intelligence/engine.py
"""
Error Intelligence Engine — the orchestrator (AURA V3 foundation).

Pipeline (from the V3 doc):

    raw error text
        │
        ▼
    classify  ── no KB match ──▶  needs_llm=True  (caller asks Groq/OpenRouter)
        │ match
        ▼
    record in mistake tracker  ──▶  count_today, total
        │
        ▼
    reply selection (level + repeat count + personality)
        │
        ▼
    EngineResponse

The engine is deliberately synchronous, instant, and free for the common case:
it only sets `needs_llm` when the KB genuinely can't classify the error. The
caller owns the LLM call, so this package has zero network/model dependencies
and stays fully unit-testable.

Typical use from core/brain.py or modules/proactive.py:

    from modules.error_intelligence import get_engine
    resp = get_engine().process(raw_error_text, personality="companion")
    if resp.needs_llm:
        detail = ask_llm(f"Explain this error briefly:\\n{raw_error_text}")
        speak(detail)
    else:
        speak(resp.spoken_text)
"""

from __future__ import annotations

import random

from . import reply_pools
from .classifier import classify
from .knowledge_base import entry_by_id
from .mistake_tracker import MistakeTracker
from .models import Classification, EngineResponse, Level


class ErrorIntelligenceEngine:
    def __init__(self, tracker: MistakeTracker | None = None, rng: random.Random | None = None):
        self.tracker = tracker or MistakeTracker()
        self._rng = rng

    def process(
        self,
        raw_error: str,
        language: str | None = None,
        personality: str = "companion",
        record: bool = True,
    ) -> EngineResponse:
        """Run one error through the full pipeline.

        `record=False` lets callers preview a classification (e.g. the on-demand
        'is there an error?' check) without polluting the mistake stats.
        """
        classification: Classification = classify(raw_error, language)

        # ── Unmatched → hand off to the LLM ─────────────────────────────────
        if not classification.matched:
            return EngineResponse(
                classification=classification,
                spoken_text="",           # caller fills this from the LLM
                needs_llm=True,
                serious=False,
            )

        entry = entry_by_id(classification.entry_id)  # guaranteed to exist
        assert entry is not None

        # ── Track the occurrence ────────────────────────────────────────────
        if record:
            count_today, total = self.tracker.record(entry.id, entry.label)
        else:
            count_today = self.tracker.count_today(entry.id) + 1
            total = self.tracker.total(entry.id) + 1

        # ── Pick the line ───────────────────────────────────────────────────
        spoken = reply_pools.select_reply(
            entry, count_today, personality=personality, rng=self._rng
        )

        return EngineResponse(
            classification=classification,
            spoken_text=spoken,
            repeat_count=count_today,
            total_count=total,
            needs_llm=False,
            serious=entry.level >= Level.CONCEPTUAL,
        )

    # ── Convenience passthroughs for the UI panels ──────────────────────────
    def todays_mistakes(self) -> list[dict]:
        """Rows for the 'Today's Mistakes' panel: [{id, label, count}, ...]."""
        return self.tracker.today_summary()

    def trends(self, window_days: int = 7) -> list[dict]:
        """Rows for the trend view, e.g. 'semicolon errors down 83%'."""
        return self.tracker.all_trends(window_days)

    def on_cleared(self, personality: str = "companion") -> str:
        """A victory line for when the error state flips back to clean."""
        return reply_pools.victory_line(personality=personality)


# ── Module-level singleton so every caller shares one tracker/log ───────────
_ENGINE: ErrorIntelligenceEngine | None = None


def get_engine() -> ErrorIntelligenceEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = ErrorIntelligenceEngine()
    return _ENGINE
