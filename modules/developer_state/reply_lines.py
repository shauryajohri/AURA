# modules/developer_state/reply_lines.py
"""
What AURA says for each session Signal, per personality pack.

Two design rules from the V3 doc:
  1. Say less. Every line here is one sentence. The intelligence is in *when*
     AURA speaks, not how much.
  2. The new 'engineer' pack is quiet and professional — it says "Solid
     implementation" instead of "Good job", because for a developer that
     reads as higher praise.

Packs mirror modules/relationship_engine.py's names so the two systems can
share one active personality setting.
"""

from __future__ import annotations

import random

from .models import Signal

# personality -> { Signal -> [lines] }
_LINES: dict[str, dict[Signal, list[str]]] = {
    "companion": {
        Signal.FIRST_BUILD:     ["Nice.", "There's the first clean build."],
        Signal.MOMENTUM:        ["Nice pace.", "Good rhythm going."],
        Signal.BUG_KILLER:      ["There we go.", "There it is.", "Got it."],
        Signal.CELEBRATION:     ["LET'S GOOOO.", "Board's clear — that was a fight."],
        Signal.MILESTONE:       ["That was a productive stretch.", "Solid chunk of work just now."],
        Signal.FLOW_ENTER:      ["You're in a really good flow. I'll stay out of the way."],
        Signal.LONG_FLOW:       ["You've been locked in for two hours. Want a quick break, or keep pushing?"],
        Signal.FATIGUE:         ["You've been at this a while — might be worth a breather."],
        Signal.BREAK:           ["Good spot to stretch if you want one."],
        Signal.HIGH_CONFIDENCE: ["Honestly… you're cooking today."],
    },
    "engineer": {
        Signal.FIRST_BUILD:     ["Builds. Good."],
        Signal.MOMENTUM:        ["Good pace."],
        Signal.BUG_KILLER:      ["There it is.", "Resolved."],
        Signal.CELEBRATION:     ["Clean board. Well handled."],
        Signal.MILESTONE:       ["Solid implementation."],
        Signal.FLOW_ENTER:      ["Solid rhythm. I'll stay out of the way."],
        Signal.LONG_FLOW:       ["Two hours of clean work — keep going, or pause?"],
        Signal.FATIGUE:         ["Long session. A short break wouldn't hurt the work."],
        Signal.BREAK:           ["Reasonable point to pause."],
        Signal.HIGH_CONFIDENCE: ["You're operating at a high level today."],
    },
    "roast": {
        Signal.FIRST_BUILD:     ["It compiles. Low bar, but we'll take it."],
        Signal.MOMENTUM:        ["Okay, showing off now."],
        Signal.BUG_KILLER:      ["Finally.", "Only took a few tries."],
        Signal.CELEBRATION:     ["From a disaster to zero. Redemption arc."],
        Signal.MILESTONE:       ["Actually productive. Who are you."],
        Signal.FLOW_ENTER:      ["Oh, we're locked in now? I'll shut up then."],
        Signal.LONG_FLOW:       ["Two hours straight. Touch grass, or keep cooking?"],
        Signal.FATIGUE:         ["You're running on fumes. Maybe blink."],
        Signal.BREAK:           ["Take a break before you fight the compiler again."],
        Signal.HIGH_CONFIDENCE: ["You're cooking today. Don't let it go to your head."],
    },
    "professional": {
        Signal.FIRST_BUILD:     ["Build passing."],
        Signal.MOMENTUM:        ["Good progress."],
        Signal.BUG_KILLER:      ["Resolved."],
        Signal.CELEBRATION:     ["All issues cleared."],
        Signal.MILESTONE:       ["Productive session."],
        Signal.FLOW_ENTER:      ["You're in a good rhythm — I'll stay out of the way."],
        Signal.LONG_FLOW:       ["You've been focused for two hours. A break is available if you'd like one."],
        Signal.FATIGUE:         ["This has been a long session; consider a short break."],
        Signal.BREAK:           ["A natural break point, if useful."],
        Signal.HIGH_CONFIDENCE: ["Strong session so far."],
    },
}


def line_for(signal: Signal, personality: str = "companion", rng: random.Random | None = None) -> str:
    r = rng or random
    pack = _LINES.get(personality) or _LINES["companion"]
    options = pack.get(signal) or _LINES["companion"].get(signal) or [""]
    return r.choice(options)
