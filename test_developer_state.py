# test_developer_state.py
"""
Unit tests for the V3 Developer State Engine.

Run:  python test_developer_state.py
Time is injected as `now` so flow/fatigue are tested in milliseconds, not hours.
"""

import random

from modules.developer_state import DeveloperState, Signal
from modules.developer_state.state_engine import (
    DeveloperStateEngine,
    FLOW_ENTER_SECONDS,
    LONG_FLOW_SECONDS,
    FATIGUE_SECONDS,
    IDLE_SECONDS,
)

PASS = 0
FAIL = 0
T0 = 1_000_000.0  # arbitrary base timestamp


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ FAIL: {name}")


def _eng(personality="companion", seed=0):
    e = DeveloperStateEngine(personality=personality, rng=random.Random(seed))
    e.start(now=T0)
    return e


# ── 1. Flow: quiet until 30 min clean, then one line ────────────────────────
def test_flow():
    print("\n[flow state]")
    e = _eng()
    # Activity + a couple clean builds early on.
    e.on_activity(lines_added=10, now=T0 + 60)
    e.on_build(success=True, now=T0 + 120)

    # A tick at 10 min in: not flow yet, should stay quiet.
    a = e.tick(now=T0 + 10 * 60)
    check("no flow announcement at 10 min", a is None)
    check("state at 10 min is not FLOW", e.state(now=T0 + 10 * 60) != DeveloperState.FLOW)

    # Keep activity recent, tick past 30 min clean.
    e.on_activity(now=T0 + FLOW_ENTER_SECONDS - 30)
    a = e.tick(now=T0 + FLOW_ENTER_SECONDS + 5)
    check("flow announced after 30 min clean", a is not None and a.signal == Signal.FLOW_ENTER)
    check("state is FLOW", e.state(now=T0 + FLOW_ENTER_SECONDS + 5) == DeveloperState.FLOW)

    # It only says it once.
    e.on_activity(now=T0 + FLOW_ENTER_SECONDS + 60)
    a2 = e.tick(now=T0 + FLOW_ENTER_SECONDS + 120)
    check("flow line is once-per-session", a2 is None)


# ── 2. Long flow (2h) produces the 'locked in' nudge ────────────────────────
def test_long_flow():
    print("\n[long flow]")
    e = _eng()
    e.on_activity(now=T0 + 30)
    e.on_build(success=True, now=T0 + 60)
    e.on_activity(now=T0 + LONG_FLOW_SECONDS - 30)
    a = e.tick(now=T0 + LONG_FLOW_SECONDS + 5)
    check("long-flow announced at 2h", a is not None and a.signal == Signal.LONG_FLOW)
    check("state LONG_FLOW", e.state(now=T0 + LONG_FLOW_SECONDS + 5) == DeveloperState.LONG_FLOW)
    check("long-flow text mentions two hours", "two hours" in a.text.lower() or "two hours of" in a.text.lower())


# ── 3. Bug killer: fail, fail, fail, success ────────────────────────────────
def test_bug_killer():
    print("\n[bug killer]")
    e = _eng()
    e.on_build(success=False, now=T0 + 10)
    e.on_build(success=False, now=T0 + 20)
    e.on_build(success=False, now=T0 + 30)
    check("3 fails -> STRUGGLING or DEBUGGING", e.state(now=T0 + 31) in (DeveloperState.STRUGGLING, DeveloperState.DEBUGGING))
    a = e.on_build(success=True, now=T0 + 40)
    check("success after fails -> BUG_KILLER", a is not None and a.signal == Signal.BUG_KILLER)


# ── 4. Celebration: big error count collapses to zero ───────────────────────
def test_celebration():
    print("\n[celebration]")
    e = _eng()
    e.on_errors(count=427, now=T0 + 10)
    check("427 errors -> DEBUGGING", e.state(now=T0 + 11) == DeveloperState.DEBUGGING)
    a = e.on_errors(count=0, now=T0 + 300)
    check("427 -> 0 triggers CELEBRATION", a is not None and a.signal == Signal.CELEBRATION)

    # Small clear (below threshold) is a bug_killer, not a celebration.
    e2 = _eng()
    e2.on_errors(count=2, now=T0 + 10)
    a2 = e2.on_errors(count=0, now=T0 + 40)
    check("2 -> 0 is BUG_KILLER not celebration", a2 is not None and a2.signal == Signal.BUG_KILLER)


# ── 5. Momentum: 5 clean builds ─────────────────────────────────────────────
def test_momentum():
    print("\n[momentum]")
    e = _eng()
    ann = None
    for i in range(5):
        ann = e.on_build(success=True, now=T0 + 10 + i)
    check("5 clean builds -> MOMENTUM signal", ann is not None and ann.signal == Signal.MOMENTUM)
    check("state MOMENTUM", e.state(now=T0 + 20) == DeveloperState.MOMENTUM)


# ── 6. Idle detection ───────────────────────────────────────────────────────
def test_idle():
    print("\n[idle]")
    e = _eng()
    e.on_activity(now=T0 + 60)
    check("active -> not idle", e.state(now=T0 + 120) != DeveloperState.IDLE)
    check("no activity past threshold -> IDLE", e.state(now=T0 + 60 + IDLE_SECONDS + 5) == DeveloperState.IDLE)


# ── 7. Fatigue after a very long session ────────────────────────────────────
def test_fatigue():
    print("\n[fatigue]")
    e = _eng()
    e.on_activity(now=T0 + 30)
    e.on_build(success=True, now=T0 + 60)
    e.on_activity(now=T0 + FATIGUE_SECONDS - 30)
    a = e.tick(now=T0 + FATIGUE_SECONDS + 5)
    check("fatigue nudge after 3h", a is not None and a.signal in (Signal.FATIGUE, Signal.LONG_FLOW))
    check("state FATIGUE at 3h+", e.state(now=T0 + FATIGUE_SECONDS + 5) == DeveloperState.FATIGUE)


# ── 8. Confidence range + 'cooking' ─────────────────────────────────────────
def test_confidence():
    print("\n[confidence]")
    e = _eng()
    # All green builds -> high confidence.
    for i in range(8):
        e.on_build(success=True, now=T0 + 10 + i)
    hi = e.confidence(now=T0 + 30)
    check("all-green confidence >= 88", hi >= 88)
    check("confidence within 0..100", 0 <= hi <= 100)

    e2 = _eng()
    for i in range(6):
        e2.on_build(success=False, now=T0 + 10 + i)
    e2.on_errors(count=20, now=T0 + 20)
    lo = e2.confidence(now=T0 + 30)
    check("struggling confidence < steady", lo < hi)


# ── 9. Engineer personality is quiet/professional ───────────────────────────
def test_engineer_persona():
    print("\n[engineer persona]")
    e = _eng(personality="engineer")
    e.on_build(success=False, now=T0 + 10)
    e.on_build(success=False, now=T0 + 20)
    a = e.on_build(success=True, now=T0 + 30)
    check("engineer bug-killer speaks", a is not None)
    check("engineer tone terse", a.text in ("There it is.", "Resolved."))

    e2 = _eng(personality="engineer")
    for i in range(5):
        m = e2.on_build(success=True, now=T0 + 10 + i)
    check("engineer momentum = 'Good pace.'", m is not None and m.text == "Good pace.")


# ── 10. Quiet policy: global gap keeps ambient chatter down ─────────────────
def test_quiet_policy():
    print("\n[quiet policy]")
    e = _eng()
    # Trigger a milestone (ambient, gap-respecting).
    e.on_activity(lines_added=100, now=T0 + 60)
    a1 = e.on_activity(lines_added=0, now=T0 + 61)  # milestone already consumed
    # Now push another 100 lines immediately -> should be suppressed by cooldown.
    a2 = e.on_activity(lines_added=100, now=T0 + 120)
    check("second milestone within cooldown suppressed", a2 is None)


if __name__ == "__main__":
    test_flow()
    test_long_flow()
    test_bug_killer()
    test_celebration()
    test_momentum()
    test_idle()
    test_fatigue()
    test_confidence()
    test_engineer_persona()
    test_quiet_policy()
    print(f"\n{'='*40}\n{PASS} passed, {FAIL} failed\n{'='*40}")
    raise SystemExit(1 if FAIL else 0)
