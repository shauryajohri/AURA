# modules/developer_state/confidence.py
"""
Confidence engine — the "you're cooking today" number.

Turns raw session metrics into a single 0–100 score. The score blends four
things a real pair-programmer would feel:

  • build success rate   — are things compiling/passing?
  • momentum             — a run of clean builds feels good
  • error pressure       — lots of outstanding errors right now drags it down
  • struggle penalty     — a long failure streak means "today's fighting back"

It's intentionally forgiving early (neutral prior) so AURA doesn't declare
low confidence in the first two minutes before there's any real signal.

Pure and side-effect-free: metrics in, number out.
"""

from __future__ import annotations

from .models import SessionMetrics


def compute_confidence(m: SessionMetrics, now: float) -> int:
    """Return an integer 0–100."""
    # Start from success rate mapped onto 40–90 so a perfect record isn't a
    # flat 100 and a rough one isn't a demoralising 0.
    base = 40 + m.success_rate * 50  # 40..90

    # Momentum bonus: up to +10 for a run of clean builds (caps at 5).
    momentum = min(m.consecutive_success, 5) / 5.0
    base += momentum * 10

    # Error pressure: outstanding problems right now pull it down, with
    # diminishing effect (log-ish) so 3 errors hurts, 300 doesn't nuke to zero.
    if m.error_count_now > 0:
        base -= min(25, 6 * (m.error_count_now ** 0.5))

    # Struggle penalty: a long consecutive failure streak.
    if m.consecutive_fail >= 3:
        base -= min(20, (m.consecutive_fail - 2) * 5)

    # Reward a sustained clean stretch (flow) a little.
    flow_min = m.flow_seconds(now) / 60.0
    if flow_min >= 10:
        base += min(8, flow_min / 15.0)

    return int(max(0, min(100, round(base))))


def confidence_band(score: int) -> str:
    """Coarse label for UI/logic branching."""
    if score >= 85:
        return "cooking"
    if score >= 65:
        return "solid"
    if score >= 45:
        return "steady"
    return "grinding"


# Threshold above which AURA may drop a "you're cooking" line (once/session,
# and only when it has enough builds behind it to mean something).
COOKING_THRESHOLD = 88
MIN_BUILDS_FOR_COOKING = 5
