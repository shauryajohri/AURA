# ui/aura_window.py
"""
The main AURA window — frameless, dark, three columns:
sidebar | center (cosmos) | chat — with a stats bar across the bottom.

Presence flows through one StateBus shared by every panel.
Hotkeys 1–6 switch states while we're running on mock data.
"""

import time

from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ui import theme
from ui.center_panel import CenterPanel
from ui.chat_panel import ChatPanel
from ui.sidebar import Sidebar
from ui.state import AuraState, StateBus
from ui.stats_bar import StatsBar


class AuraWindow(QWidget):
    """
    Drop-in replacement for the old MainWindow: exposes the same signals
    and public API the controller (ui/app.py) and backend already use,
    so brain/proactive/voice plug in without changes.
    """

    sendMessage = Signal(str)
    micToggled = Signal(bool)

    # controller status strings → presence states
    _STATUS_TO_STATE = {
        "idle": AuraState.IDLE,
        "listening": AuraState.LISTENING,
        "thinking": AuraState.THINKING,
        "planning": AuraState.THINKING,
        "speaking": AuraState.SPEAKING,
        "awaiting approval": AuraState.IDLE,
    }

    def __init__(self, bus: StateBus = None, quit_on_close: bool = False,
                 parent=None):
        super().__init__(parent)
        self.bus = bus or StateBus()
        self._drag_pos = None
        self._quit_on_close = quit_on_close
        self._mic_on = False

        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setMinimumSize(1180, 720)
        self.setStyleSheet(f"background-color: {theme.VOID_BLACK};")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 12)
        root.setSpacing(8)

        root.addWidget(self._build_titlebar())

        columns = QHBoxLayout()
        columns.setSpacing(10)

        self.sidebar = Sidebar(self.bus)
        self.center = CenterPanel(self.bus)
        self.chat = ChatPanel(self.bus)
        self.chat.setFixedWidth(320)

        columns.addWidget(self.sidebar)
        columns.addWidget(self.center, 1)
        columns.addWidget(self.chat)
        root.addLayout(columns, 1)

        self.stats = StatsBar()
        root.addWidget(self.stats)

        # mock-phase hotkeys: 1..6 cycle presence states
        for i, state in enumerate(AuraState.ALL, start=1):
            sc = QShortcut(QKeySequence(str(i)), self)
            sc.activated.connect(lambda s=state: self.bus.set_state(s))

        # input wiring → controller
        self.chat.input.returnPressed.connect(self._on_send)
        self.chat.send_button.clicked.connect(self._on_send)
        self.chat.mic_button.clicked.connect(self._toggle_mic)

    # ── input handlers ───────────────────────────────────────────────────
    def _on_send(self):
        text = self.chat.input.text().strip()
        if not text:
            return
        self.chat.input.clear()
        self.append_message(text, "You")
        self.sendMessage.emit(text)

    def _toggle_mic(self):
        self._mic_on = not self._mic_on
        self.micToggled.emit(self._mic_on)

    def is_mic_on(self) -> bool:
        return self._mic_on

    # ── backend-compat public API (same surface as old MainWindow) ──────
    @staticmethod
    def _now() -> str:
        return time.strftime("%I:%M %p")

    def append_message(self, text: str, sender: str):
        self.chat.add_message(text, sender, self._now())

    def append_code(self, lang: str, code: str):
        self.chat.add_code(lang, code)

    def add_activity_note(self, text: str):
        self.stats.set_note(text)

    def set_status_text(self, text: str):
        state = self._STATUS_TO_STATE.get(text.strip().lower())
        if state:
            self.bus.set_state(state)

    def set_voice_status(self, text: str):
        self.sidebar.set_voice_status(text)

    def set_presence(self, presence: str):
        self.sidebar.set_presence(presence)

    def set_plan_panel(self, panel: QWidget):
        """Docks the execution-plan approval panel into the center column,
        between the cosmos and the routing bar. Panel shows itself when
        a plan is ready."""
        layout = self.center.layout()
        layout.insertWidget(2, panel)
        panel.hide()

    def closeEvent(self, event):
        # The window is a tool; AURA lives on in the orb. Closing hides
        # the window instead of killing the app — quit via the orb menu.
        if self._quit_on_close:
            event.accept()
            return
        event.ignore()
        self.hide()

    # ── titlebar ─────────────────────────────────────────────────────────
    def _build_titlebar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(30)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(4, 0, 0, 0)
        lay.setSpacing(6)

        title = QLabel("A U R A  ·  Prime Core Online")
        title.setFont(theme.mono_font(8))
        title.setStyleSheet(f"color: {theme.TEXT_DIM};")
        lay.addWidget(title)
        lay.addStretch()

        for glyph, handler in (
            ("—", self.showMinimized),
            ("□", self._toggle_max),
            ("✕", self.close),
        ):
            btn = QPushButton(glyph)
            btn.setFixedSize(30, 24)
            btn.setCursor(Qt.PointingHandCursor)
            hover = theme.ERROR_RED if glyph == "✕" else "rgba(125,127,255,0.2)"
            btn.setStyleSheet(
                f"""
                QPushButton {{ background: transparent; border: none;
                               color: {theme.TEXT_DIM}; font-size: 11px;
                               border-radius: 6px; }}
                QPushButton:hover {{ background-color: {hover};
                                     color: {theme.TEXT_PRIMARY}; }}
                """
            )
            btn.clicked.connect(handler)
            lay.addWidget(btn)

        self._titlebar = bar
        return bar

    def _toggle_max(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    # ── frameless drag (via titlebar area) ───────────────────────────────
    def mousePressEvent(self, event):
        if (event.button() == Qt.LeftButton
                and event.position().y() <= self._titlebar.height() + 8):
            self._drag_pos = (event.globalPosition().toPoint()
                              - self.frameGeometry().topLeft())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)
