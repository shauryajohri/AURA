# core/model_lock.py
"""
Persistent per-model lock state — the single source of truth shared by the
backend router and the UI.

A LOCKED model is one AURA may NEVER use, no matter what: routing skips it
entirely (it just idles at the edge of the cosmos). An UNLOCKED model is
available for AURA to route to.

State lives in QSettings so it survives restarts. Lock keys are the model's
DISPLAY NAME (e.g. "Gemma 4 31B") — the same string the cosmos planet and the
dock chip use — so the UI toggle and the router agree on what's locked.
"""

from PySide6.QtCore import QSettings

_settings = QSettings("AURA", "Models")


def is_locked(name: str) -> bool:
    return bool(_settings.value(f"locked/{name}", False, type=bool))


def set_locked(name: str, locked: bool):
    _settings.setValue(f"locked/{name}", bool(locked))
    _settings.sync()


def toggle(name: str) -> bool:
    """Flip a model's lock and return the NEW locked state."""
    new_state = not is_locked(name)
    set_locked(name, new_state)
    return new_state


def locked_models(names) -> set:
    return {n for n in names if is_locked(n)}


def unlocked_models(names) -> set:
    return {n for n in names if not is_locked(n)}
