# modules/developer_state/state_engine.py
"""
Developer State Engine — the orchestrator (AURA V3).

Feed it session events (builds, error counts, activity). It maintains
SessionMetrics, derives the current DeveloperState, computes a confidence
score, and — most importantly — decides *whether to say anything at all*.

The guiding principle from the V3 doc: staying quiet is the intelligence. So
every ambient signal is gated by:
  • once-per-session flags (you enter flow once, not every tick),
  • per-signal cooldowns,
  • a global minimum gap between any two spoken lines,
so AURA notices everything but speaks rarely. Win moments (bug killed, board
cleared) are allowed to bypass the gap because they're earned and instant.

Time is injected as `now` everywhere so the whole thing is deterministic and
unit-testable without real clocks. In the app, callers just omit `now`.

Wiring sketch (later):
    from modules.developer_state import get_state_engine
    eng = get_state_engine(personality="engineer")
    ann = eng.on_build(success=True)      # after a build finishes
    ann = eng.on_errors(count=0)          # from the Problems-panel gauge
    ann = eng.on_activity(lines_added=12) # from editor/file-watch
    ann = eng.tick()                      # call every ~30s from the watch loop
    if ann: speak(ann.text)
"""

from __future__ import annotations

import random
import time

from .confidence import (
    COOKING_THRESHOLD,
    MIN_BUILDS_FOR_COOKING,
    compute_confidence,
)
from .models import (
    STATE_EMOJI,
    Announcement,
    DeveloperState,
    SessionMetrics,
    Signal,
)
from .reply_lines import line_for

# ── Thresholds (seconds unless noted). Kept here so they're easy to tune. ──
STARTING_SECONDS = 5 * 60
FLOW_ENTER_SECONDS = 30 * 60
LONG_FLOW_SECONDS = 2 * 60 * 60
FATIGUE_SECONDS = 3 * 60 * 60
IDLE_SECONDS = 10 * 60
ACTIVITY_RECENT = 5 * 60          # flow requires activity within this window
MOMENTUM_STREAK = 5               # consecutive clean builds = momentum
CELEBRATION_MIN_PEAK = 10         # outstanding errors that cleared = celebration
MILESTONE_LINES = 100
GLOBAL_MIN_GAP = 8 * 60           # min seconds between any two ambient lines

# Per-signal speak rules: once/cooldown/priority/bypass_gap.
_RULES = {
    Signal.FIRST_BUILD:     dict(once=True,  cooldown=0,        priority=2, bypass=True),
    Signal.MOMENTUM:        dict(once=True,  cooldown=0,        priority=2, bypass=True),
    Signal.BUG_KILLER:      dict(once=False, cooldown=60,       priority=4, bypass=True),
    Signal.CELEBRATION:     dict(once=False, cooldown=60,       priority=5, bypass=True),
    Signal.MILESTONE:       dict(once=False, cooldown=20 * 60,  priority=2, bypass=False),
    Signal.FLOW_ENTER:      dict(once=True,  cooldown=0,        priority=3, bypass=False),
    Signal.LONG_FLOW:       dict(once=True,  cooldown=0,        priority=3, bypass=True),
    Signal.FATIGUE:         dict(once=False, cooldown=30 * 60,  priority=1, bypass=False),
    Signal.BREAK:           dict(once=True,  cooldown=0,        priority=1, bypass=False),
    Signal.HIGH_CONFIDENCE: dict(once=True,  cooldown=0,        priority=2, bypass=False),
}


class DeveloperStateEngine:
    def __init__(self, personality: str = "companion", rng: random.Random | None = None):
        self.personality = personality
        self._rng = rng
        self.m = SessionMetrics()
        self._emitted: dict[Signal, float] = {}
        self._once: set[Signal] = set()
        self._last_spoken: float = 0.0
        self._last_tick_ts: float = 0.0
        self._started = False

    # ── lifecycle ───────────────────────────────────────────────────────────
    def start(self, now: float | None = None) -> None:
        now = self._now(now)
        self.m = SessionMetrics(session_start=now, clean_since=now, last_activity_ts=now)
        self._emitted.clear()
        self._once.clear()
        self._last_spoken = 0.0
        self._last_tick_ts = now
        self._started = True

    def _ensure_started(self, now: float) -> None:
        if not self._started:
            self.start(now)

    # ── event: a build finished ─────────────────────────────────────────────
    def on_build(self, success: bool, now: float | None = None) -> Announcement | None:
        now = self._now(now)
        self._ensure_started(now)
        m = self.m
        m.builds_total += 1
        m.last_build_ts = now
        m.last_activity_ts = now

        if success:
            prior_fail_run = m.consecutive_fail
            m.builds_success += 1
            m.consecutive_success += 1
            m.consecutive_fail = 0
            m.last_success_ts = now
            # Recovering to a clean state re-opens the flow clock.
            if m.clean_since is None and m.error_count_now == 0:
                m.clean_since = now

            candidates: list[Signal] = []
            if m.builds_success == 1:
                candidates.append(Signal.FIRST_BUILD)
            if prior_fail_run >= 2:
                candidates.append(Signal.BUG_KILLER)
            if m.consecutive_success == MOMENTUM_STREAK:
                candidates.append(Signal.MOMENTUM)
            return self._emit(candidates, now)

        # failure
        m.builds_fail += 1
        m.consecutive_fail += 1
        m.consecutive_success = 0
        m.clean_since = None
        m.last_problem_ts = now
        # AURA stays quiet on a failure — the error engine handles the roast;
        # the state engine just absorbs it.
        return None

    # ── event: current outstanding problem count (a gauge) ──────────────────
    def on_errors(self, count: int, now: float | None = None) -> Announcement | None:
        now = self._now(now)
        self._ensure_started(now)
        m = self.m
        count = max(0, int(count))
        prev = m.error_count_now
        m.error_count_now = count
        m.last_activity_ts = now

        if count > 0:
            if prev == 0:
                m.peak_error_count = count      # new problem episode
            else:
                m.peak_error_count = max(m.peak_error_count, count)
            m.errors_total += max(0, count - prev)
            m.clean_since = None
            m.last_problem_ts = now
            return None

        # count == 0
        if prev > 0:
            magnitude = m.peak_error_count
            m.peak_error_count = 0
            m.clean_since = now                 # clean stretch begins now
            if magnitude >= CELEBRATION_MIN_PEAK:
                return self._emit([Signal.CELEBRATION], now, magnitude=magnitude)
            return self._emit([Signal.BUG_KILLER], now)
        return None

    # ── event: developer activity (typing, file saves) ──────────────────────
    def on_activity(self, lines_added: int = 0, now: float | None = None) -> Announcement | None:
        now = self._now(now)
        self._ensure_started(now)
        m = self.m
        m.last_activity_ts = now
        if lines_added:
            m.lines_added += max(0, lines_added)
            m.lines_since_milestone += max(0, lines_added)

        clean = m.error_count_now == 0 and m.consecutive_fail == 0
        if clean and m.clean_since is None:
            m.clean_since = now

        if clean and m.lines_since_milestone >= MILESTONE_LINES:
            m.lines_since_milestone = 0
            return self._emit([Signal.MILESTONE], now)
        return None

    # ── periodic tick: time-based state (flow / fatigue / confidence) ───────
    def tick(self, now: float | None = None) -> Announcement | None:
        now = self._now(now)
        self._ensure_started(now)
        m = self.m

        # Accumulate debug time while in a problem state.
        if self._last_tick_ts and (m.error_count_now > 0 or m.consecutive_fail > 0):
            m.debug_seconds += max(0.0, now - self._last_tick_ts)
        self._last_tick_ts = now

        st = self.state(now)
        fs = m.flow_seconds(now)
        recent = m.last_activity_ts == 0 or (now - m.last_activity_ts) <= ACTIVITY_RECENT

        candidates: list[Signal] = []
        if recent and m.error_count_now == 0 and m.consecutive_fail == 0:
            if fs >= LONG_FLOW_SECONDS:
                candidates.append(Signal.LONG_FLOW)
                candidates.append(Signal.BREAK)
            elif fs >= FLOW_ENTER_SECONDS:
                candidates.append(Signal.FLOW_ENTER)

        if m.session_seconds(now) >= FATIGUE_SECONDS:
            candidates.append(Signal.FATIGUE)

        conf = self.confidence(now)
        if conf >= COOKING_THRESHOLD and m.builds_total >= MIN_BUILDS_FOR_COOKING:
            candidates.append(Signal.HIGH_CONFIDENCE)

        return self._emit(candidates, now)

    # ── derived views ───────────────────────────────────────────────────────
    def state(self, now: float | None = None) -> DeveloperState:
        now = self._now(now)
        m = self.m
        if not self._started:
            return DeveloperState.STARTING

        if m.last_activity_ts and (now - m.last_activity_ts) > IDLE_SECONDS:
            return DeveloperState.IDLE
        if m.consecutive_fail >= 4:
            return DeveloperState.STRUGGLING
        if m.error_count_now > 0 or m.consecutive_fail > 0:
            return DeveloperState.DEBUGGING

        session = m.session_seconds(now)
        fs = m.flow_seconds(now)
        recent = m.last_activity_ts == 0 or (now - m.last_activity_ts) <= ACTIVITY_RECENT

        if session >= FATIGUE_SECONDS:
            return DeveloperState.FATIGUE
        if recent and fs >= LONG_FLOW_SECONDS:
            return DeveloperState.LONG_FLOW
        if recent and fs >= FLOW_ENTER_SECONDS:
            return DeveloperState.FLOW
        if m.consecutive_success >= MOMENTUM_STREAK:
            return DeveloperState.MOMENTUM
        if session < STARTING_SECONDS and m.builds_total < 2:
            return DeveloperState.STARTING
        return DeveloperState.NEUTRAL

    def confidence(self, now: float | None = None) -> int:
        return compute_confidence(self.m, self._now(now))

    def session_summary(self, now: float | None = None) -> dict:
        now = self._now(now)
        m = self.m
        st = self.state(now)
        return {
            "state": st.value,
            "state_emoji": STATE_EMOJI.get(st, "•"),
            "confidence": self.confidence(now),
            "session_minutes": round(m.session_seconds(now) / 60.0, 1),
            "flow_minutes": round(m.flow_seconds(now) / 60.0, 1),
            "builds_total": m.builds_total,
            "builds_success": m.builds_success,
            "success_rate": round(m.success_rate * 100),
            "errors_total": m.errors_total,
            "errors_now": m.error_count_now,
            "lines_added": m.lines_added,
            "debug_minutes": round(m.debug_seconds / 60.0, 1),
        }

    # ── internal: the quiet-speak gate ──────────────────────────────────────
    def _emit(self, candidates: list[Signal], now: float, magnitude: int = 0) -> Announcement | None:
        """Pick the highest-priority candidate that's allowed to speak right
        now under its once/cooldown/global-gap rules. Returns None (silence)
        if nothing clears the bar — which is the common, intended case."""
        if not candidates:
            return None
        # De-dup while keeping order, then sort by priority desc.
        seen = []
        for s in candidates:
            if s not in seen:
                seen.append(s)
        seen.sort(key=lambda s: _RULES[s]["priority"], reverse=True)

        for signal in seen:
            if self._allowed(signal, now):
                self._record(signal, now)
                text = line_for(signal, self.personality, self._rng)
                return Announcement(
                    signal=signal,
                    text=text,
                    state=self.state(now),
                    confidence=self.confidence(now),
                    emoji=STATE_EMOJI.get(self.state(now), ""),
                )
        return None

    def _allowed(self, signal: Signal, now: float) -> bool:
        rule = _RULES[signal]
        if rule["once"] and signal in self._once:
            return False
        last = self._emitted.get(signal)
        if last is not None and rule["cooldown"] and (now - last) < rule["cooldown"]:
            return False
        if not rule["bypass"] and self._last_spoken and (now - self._last_spoken) < GLOBAL_MIN_GAP:
            return False
        return True

    def _record(self, signal: Signal, now: float) -> None:
        self._emitted[signal] = now
        self._once.add(signal)
        self._last_spoken = now

    @staticmethod
    def _now(now: float | None) -> float:
        return time.time() if now is None else now


# ── module-level singleton ──────────────────────────────────────────────────
_ENGINE: DeveloperStateEngine | None = None


def get_state_engine(personality: str | None = None) -> DeveloperStateEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = DeveloperStateEngine(personality=personality or "companion")
    elif personality:
        _ENGINE.personality = personality
    return _ENGINE
