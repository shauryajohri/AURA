"""
core/voice_gate.py
------------------
Tiny shared coordination point so two independent background loops
(modules.proactive and core.curiosity_engine) never both decide to
speak at the same time.

Each loop, right before it actually calls speak_fn(...), must:
    1. check can_speak()
    2. if True, call mark_spoken()
    3. then speak

This is intentionally dumb (no locks, no queue) — both loops run on a
multi-second cadence, so a plain timestamp + small buffer is enough.
"""

import time
import threading

_lock = threading.Lock()
_last_spoken_time = 0.0
MIN_GAP_SECONDS = 20  # don't let two proactive systems fire within 20s of each other


def can_speak() -> bool:
    with _lock:
        return (time.time() - _last_spoken_time) >= MIN_GAP_SECONDS


def mark_spoken():
    global _last_spoken_time
    with _lock:
        _last_spoken_time = time.time()


def seconds_since_last_spoken() -> float:
    with _lock:
        return time.time() - _last_spoken_time