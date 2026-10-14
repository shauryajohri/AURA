"""
core/guard — Buddy Lock.

AURA is a buddy, not a kiosk: she should know who she's talking to. Once the
owner enrolls (face + optional voice + backup PIN), every message is checked:

    voice message  → speaker ID; too short or unsure → camera
    typed message  → camera frame sent with the message
    guest          → only with the owner in frame, or after the owner said
                     "you can help him" (a pass bound to that person's face)

Nothing is enforced until enrollment, so a fresh checkout behaves exactly as
before. See policy.py for the rules and README "Buddy Lock" for the setup.
"""

from __future__ import annotations

import threading

from core.guard.policy import Decision, Guard  # noqa: F401 - public API

_guard: Guard | None = None
_lock = threading.Lock()


def get_guard() -> Guard:
    global _guard
    if _guard is None:
        with _lock:
            if _guard is None:
                from core.guard import face, voice
                from core.guard.vault import Vault
                _guard = Guard(Vault(), face.ENGINE, voice.ENGINE)
    return _guard


def owner_present() -> bool:
    """True when AURA may speak up on her own: the lock is off, or the owner
    is around. Never raises — a guard failure must not kill the proactive
    loops, it just keeps them quiet."""
    try:
        g = get_guard()
        return (not g.active) or g.owner_present()
    except Exception:  # noqa: BLE001
        return False
