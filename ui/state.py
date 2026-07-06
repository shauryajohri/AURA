# ui/state.py
"""
Single source of truth for AURA's presence state.

One StateBus instance is shared by every widget; a state change here
propagates to the orb, the cosmos core, the sidebar chip and status
labels — so the whole UI always agrees on what AURA is doing.
"""

from PySide6.QtCore import QObject, Signal

from ui.theme import STATE_ACCENTS


class AuraState:
    IDLE      = "idle"
    LISTENING = "listening"
    THINKING  = "thinking"
    SPEAKING  = "speaking"
    FOCUS     = "focus"
    ALERT     = "alert"

    ALL = (IDLE, LISTENING, THINKING, SPEAKING, FOCUS, ALERT)

    LABELS = {
        IDLE:      "Idle",
        LISTENING: "Listening...",
        THINKING:  "Thinking...",
        SPEAKING:  "Speaking...",
        FOCUS:     "Focus Mode",
        ALERT:     "Alert",
    }

    TAGLINES = {
        IDLE:      "Calm and aware.",
        LISTENING: "AURA is present and aware.",
        THINKING:  "Processing information.",
        SPEAKING:  "Responding to you.",
        FOCUS:     "Distraction blocked.",
        ALERT:     "Important reminder.",
    }


def state_accent(state: str) -> str:
    return STATE_ACCENTS.get(state, STATE_ACCENTS[AuraState.IDLE])


class StateBus(QObject):
    """App-wide presence signal hub."""

    stateChanged = Signal(str)          # one of AuraState.ALL
    activeModelChanged = Signal(str)    # e.g. "GPT-4o"

    def __init__(self):
        super().__init__()
        self._state = AuraState.IDLE
        self._active_model = "Llama 3.3 70B"

    @property
    def state(self) -> str:
        return self._state

    @property
    def active_model(self) -> str:
        return self._active_model

    def set_state(self, state: str):
        if state in AuraState.ALL and state != self._state:
            self._state = state
            self.stateChanged.emit(state)

    def set_active_model(self, model: str):
        if model != self._active_model:
            self._active_model = model
            self.activeModelChanged.emit(model)
