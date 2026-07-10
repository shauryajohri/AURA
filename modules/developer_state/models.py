# modules/developer_state/models.py
"""
Data model for the Developer State Engine (AURA V3).

This is the layer *above* the Error Intelligence Engine: instead of reacting to
a single error, it watches the whole session and understands what kind of
moment the developer is in — flow, momentum, debugging, fatigue, a win.

Dependency-free by design (no siblings imported here) so it stays trivially
testable and can't cause import cycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DeveloperState(Enum):
    """The developer's current session state. Derived, not stored — the engine
    recomputes it from metrics each tick."""
    STARTING = "starting"        # session just began, not much signal yet
    DEBUGGING = "debugging"      # errors/failed builds present, actively fixing
    STRUGGLING = "struggling"    # a long run of failures — extra care, no jokes
    MOMENTUM = "momentum"        # several clean builds in a row, steady changes
    FLOW = "flow"                # sustained clean stretch + steady activity
    LONG_FLOW = "long_flow"      # flow that's lasted a couple hours
    FATIGUE = "fatigue"          # very long session / late — a break might help
    IDLE = "idle"                # no activity for a while
    NEUTRAL = "neutral"          # nothing notable


# Which states are "positive" (AURA should mostly stay quiet and just enjoy it).
POSITIVE_STATES = {DeveloperState.MOMENTUM, DeveloperState.FLOW, DeveloperState.LONG_FLOW}


class Signal(Enum):
    """One-off things worth (maybe) saying something about. These are events,
    not states — a bug_killer happens at an instant; FLOW is a condition."""
    FIRST_BUILD = "first_build"          # first successful build of the session
    MOMENTUM = "momentum"                # crossed N consecutive clean builds
    BUG_KILLER = "bug_killer"            # fail, fail, fail… success
    CELEBRATION = "celebration"          # big error count collapsed to zero
    MILESTONE = "milestone"              # productive stretch (lines, clean)
    FLOW_ENTER = "flow_enter"            # entered flow after a clean stretch
    LONG_FLOW = "long_flow"              # flow passed the long threshold
    FATIGUE = "fatigue"                  # long session — gentle nudge
    BREAK = "break"                      # natural break opportunity
    HIGH_CONFIDENCE = "high_confidence"  # "you're cooking today"


@dataclass
class SessionMetrics:
    """Raw, accumulated numbers for the current session. The confidence engine
    and state resolver read from this; nothing here makes decisions."""
    session_start: float = 0.0

    builds_total: int = 0
    builds_success: int = 0
    builds_fail: int = 0
    consecutive_success: int = 0
    consecutive_fail: int = 0

    errors_total: int = 0                 # all error occurrences seen
    error_count_now: int = 0              # current outstanding problem count (gauge)
    peak_error_count: int = 0             # highest outstanding count this "problem episode"

    lines_added: int = 0
    lines_since_milestone: int = 0

    debug_seconds: float = 0.0            # time accumulated while in a problem state

    last_activity_ts: float = 0.0
    last_build_ts: float = 0.0
    last_success_ts: float = 0.0
    last_problem_ts: float = 0.0          # last time an error/failed build occurred
    clean_since: float | None = None      # when the current clean stretch began (None = not clean)

    @property
    def success_rate(self) -> float:
        if self.builds_total == 0:
            return 0.7  # neutral prior before we have data
        return self.builds_success / self.builds_total

    def session_seconds(self, now: float) -> float:
        return max(0.0, now - self.session_start)

    def flow_seconds(self, now: float) -> float:
        if self.clean_since is None:
            return 0.0
        return max(0.0, now - self.clean_since)


@dataclass
class Announcement:
    """What the engine decides to actually say (or None if it stays quiet)."""
    signal: Signal
    text: str
    state: DeveloperState
    confidence: int
    emoji: str = ""


# Emoji per state, for a status chip in the UI.
STATE_EMOJI = {
    DeveloperState.STARTING: "🌱",
    DeveloperState.DEBUGGING: "🔧",
    DeveloperState.STRUGGLING: "🪫",
    DeveloperState.MOMENTUM: "🟢",
    DeveloperState.FLOW: "🚀",
    DeveloperState.LONG_FLOW: "🔥",
    DeveloperState.FATIGUE: "😴",
    DeveloperState.IDLE: "☕",
    DeveloperState.NEUTRAL: "•",
}
