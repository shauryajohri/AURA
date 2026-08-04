"""Live activity bus — one line describing what AURA is doing RIGHT NOW.

The server registers a sink that broadcasts {"type": "activity"} over the
websocket; core modules call emit() at interesting moments ("Routing to
Claude…", "Searching memory…"). Everything is best-effort: if no sink is
registered or the sink raises, emit() is a no-op — activity must never be
able to break an answer.
"""
from __future__ import annotations

import time
from typing import Callable, Optional

_sink: Optional[Callable[[dict], None]] = None


def set_sink(fn: Callable[[dict], None]) -> None:
    global _sink
    _sink = fn


def emit(text: str, kind: str = "info") -> None:
    """Announce what AURA is doing. kind: info | route | memory | task | done."""
    if _sink is None or not text:
        return
    try:
        _sink({"text": str(text)[:200], "kind": kind, "ts": time.time()})
    except Exception:  # noqa: BLE001 — never let telemetry break the brain
        pass
