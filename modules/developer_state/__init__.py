# modules/developer_state/__init__.py
"""
Developer State Engine — AURA V3.

The layer above error detection. It watches the whole coding session and
understands the *moment*: flow, momentum, debugging, struggling, fatigue, and
wins (bug killed, board cleared, milestone). Its main job is to know when to
stay quiet — it notices everything and speaks rarely.

Adds the 'engineer' personality: quiet, professional, says "Solid
implementation" instead of "Good job".

Public surface:

    from modules.developer_state import get_state_engine
    eng = get_state_engine(personality="engineer")
    ann = eng.on_build(success=True)   # -> Announcement | None
    ann = eng.on_errors(count=0)
    ann = eng.on_activity(lines_added=20)
    ann = eng.tick()
    summary = eng.session_summary()    # for the Session/Confidence UI panel
"""

from .confidence import compute_confidence, confidence_band
from .models import (
    Announcement,
    DeveloperState,
    STATE_EMOJI,
    SessionMetrics,
    Signal,
)
from .reply_lines import line_for
from .state_engine import DeveloperStateEngine, get_state_engine

__all__ = [
    "get_state_engine",
    "DeveloperStateEngine",
    "DeveloperState",
    "Signal",
    "Announcement",
    "SessionMetrics",
    "STATE_EMOJI",
    "compute_confidence",
    "confidence_band",
    "line_for",
]
