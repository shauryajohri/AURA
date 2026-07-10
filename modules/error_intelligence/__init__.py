# modules/error_intelligence/__init__.py
"""
Error Intelligence Engine — AURA V3 foundation.

A rule-based Error Knowledge Base that classifies compiler / runtime / traceback
text into 4 severity levels (😂 silly → 🔥 dangerous), tracks how often each
mistake happens for the "Today's Mistakes" + trend features, and picks a
relationship-aware reply. The LLM is only consulted when the KB can't classify
an error, keeping the common path instant and free.

Public surface:

    from modules.error_intelligence import get_engine
    resp = get_engine().process(raw_error_text)

    # or lower-level:
    from modules.error_intelligence import classify, Level, Category
"""

from .classifier import classify, infer_language
from .engine import ErrorIntelligenceEngine, get_engine
from .knowledge_base import all_entries, entry_by_id, match
from .mistake_tracker import MistakeTracker
from .models import (
    Category,
    Classification,
    EngineResponse,
    KBEntry,
    Level,
    CATEGORY_EMOJI,
    CATEGORY_LABEL,
    LEVEL_EMOJI,
)

__all__ = [
    "get_engine",
    "ErrorIntelligenceEngine",
    "classify",
    "infer_language",
    "match",
    "all_entries",
    "entry_by_id",
    "MistakeTracker",
    "Classification",
    "EngineResponse",
    "KBEntry",
    "Level",
    "Category",
    "LEVEL_EMOJI",
    "CATEGORY_EMOJI",
    "CATEGORY_LABEL",
]
