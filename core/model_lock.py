# core/model_lock.py
"""
Persistent per-model lock state — the single source of truth shared by the
backend router and the UI.

A LOCKED model is one AURA may NEVER use, no matter what: routing skips it
entirely (it just idles at the edge of the cosmos). An UNLOCKED model is
available for AURA to route to.

State lives in the app_settings table (memory/store.py) under "models.locked",
a list of locked names, so it survives restarts and the backend needs no GUI
toolkit. Lock keys are the model's DISPLAY NAME (e.g. "Gemma 4 31B") — the
same string the cosmos planet and the dock chip use — so the UI toggle and the
router agree on what's locked.

Older builds kept this in PySide6's QSettings. If PySide6 is installed and
those values exist, they are carried over once, on the first read.
"""

import threading

from memory import store

_KEY = "models.locked"
# toggle() is read-modify-write on one list; two at once must not lose one.
_WRITE = threading.RLock()


def _from_qsettings() -> list:
    """Names the old QSettings store had locked. [] without PySide6."""
    try:
        from PySide6.QtCore import QSettings
    except ImportError:
        return []
    try:
        qs = QSettings("AURA", "Models")
        qs.beginGroup("locked")
        names = [k for k in qs.childKeys() if qs.value(k, False, type=bool)]
        qs.endGroup()
        return names
    except Exception as e:  # noqa: BLE001
        print(f"[AURA] old model locks not carried over: {e}")
        return []


def _locked() -> set:
    saved = store.get_settings()
    if _KEY not in saved:
        # First read on this database: adopt the old QSettings locks, and
        # store the list even when it's empty so this only ever runs once.
        with _WRITE:
            saved = store.get_settings()
            if _KEY not in saved:
                saved[_KEY] = sorted(set(_from_qsettings()))
                store.set_settings({_KEY: saved[_KEY]})
    value = saved[_KEY]
    return {n for n in value if isinstance(n, str)} if isinstance(value, list) else set()


def is_locked(name: str) -> bool:
    return name in _locked()


def set_locked(name: str, locked: bool):
    with _WRITE:
        names = _locked()
        if locked:
            names.add(name)
        else:
            names.discard(name)
        store.set_settings({_KEY: sorted(names)})


def toggle(name: str) -> bool:
    """Flip a model's lock and return the NEW locked state."""
    with _WRITE:
        new_state = not is_locked(name)
        set_locked(name, new_state)
    return new_state


def locked_models(names) -> set:
    locked = _locked()
    return {n for n in names if n in locked}


def unlocked_models(names) -> set:
    locked = _locked()
    return {n for n in names if n not in locked}
