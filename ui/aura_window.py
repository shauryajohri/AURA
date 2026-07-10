# ui/aura_window.py
"""
The main AURA window — frameless, dark, three columns:
sidebar | center (cosmos) | chat — with a stats bar across the bottom.

Presence flows through one StateBus shared by every panel.
Hotkeys 1–6 switch states while we're running on mock data.
"""

import time

from PySide6.QtCore import Qt, QPoint, QSettings, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSplitter, QStackedWidget, QVBoxLayout,
    QWidget,
)

from ui import theme
from ui.center_panel import CenterPanel
from ui.chat_panel import ChatPanel
from ui.memory_panel import MemoryPanel
from ui.sidebar import Sidebar
from ui.state import AuraState, StateBus
from ui.stats_bar import StatsBar
from ui.tasks_panel import TasksPanel
from ui.workspace_panel import WorkspacePanel


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
        self.tasks_panel = TasksPanel()
        self.memory_panel = MemoryPanel()
        self.workspace_panel = WorkspacePanel()
        self.chat = ChatPanel(self.bus)
        # Was a fixed 320px; now a minimum, so the chat can be widened but
        # never shrinks to nothing.
        self.chat.setMinimumWidth(300)

        # Center area is a stack: Home (cosmos) ⇄ Tasks ⇄ Memory ⇄ Workspace.
        # Sidebar nav switches pages; so does the "Aura App" shortcut chip.
        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self.center)          # index 0 — Home
        self.center_stack.addWidget(self.tasks_panel)     # index 1 — Tasks
        self.center_stack.addWidget(self.memory_panel)    # index 2 — Memory
        self.center_stack.addWidget(self.workspace_panel) # index 3 — Workspace
        # The black hole can shrink as the chat grows, but only down to this
        # floor — below it the orbiting planets would clip, so we stop here.
        self.center_stack.setMinimumWidth(560)

        # Cosmos ⇄ chat share a draggable handle so the developer can widen the
        # chat; the split is saved, so the chat keeps its width next launch.
        self._main_splitter = QSplitter(Qt.Horizontal)
        self._main_splitter.setHandleWidth(8)
        self._main_splitter.setChildrenCollapsible(False)
        self._main_splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {theme.EVENT_VIOLET}; border-radius: 3px; }}")
        self._main_splitter.addWidget(self.center_stack)
        self._main_splitter.addWidget(self.chat)
        self._main_splitter.setStretchFactor(0, 1)
        self._main_splitter.setStretchFactor(1, 0)
        self._main_splitter.splitterMoved.connect(self._save_main_split)

        columns.addWidget(self.sidebar)
        columns.addWidget(self._main_splitter, 1)
        root.addLayout(columns, 1)

        self._settings = QSettings("AURA", "MainWindow")

        self.stats = StatsBar()
        root.addWidget(self.stats)

        self.sidebar.navSelected.connect(self._on_nav_selected)
        self.center.openWorkspaceRequested.connect(self._open_workspace)
        self.tasks_panel.countsChanged.connect(
            lambda done, total: self.stats.set_tasks(f"{done}/{total}")
        )
        self.tasks_panel.refresh()  # seed the Completed Tasks chip with real data

        # mock-phase hotkeys: 1..6 cycle presence states
        for i, state in enumerate(AuraState.ALL, start=1):
            sc = QShortcut(QKeySequence(str(i)), self)
            sc.activated.connect(lambda s=state: self.bus.set_state(s))

        # input wiring → controller
        self.chat.input.returnPressed.connect(self._on_send)
        self.chat.send_button.clicked.connect(self._on_send)
        self.chat.mic_button.clicked.connect(self._toggle_mic)

        self._restore_main_split()

    # ── resizable / persistent chat width ────────────────────────────────
    def _save_main_split(self, *args):
        self._settings.setValue("main_splitter", self._main_splitter.saveState())

    def _restore_main_split(self):
        state = self._settings.value("main_splitter")
        if state is not None:
            self._main_splitter.restoreState(state)
        else:
            self._main_splitter.setSizes([900, 320])  # default chat width

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

    # ── nav / views ──────────────────────────────────────────────────────
    def _on_nav_selected(self, name: str):
        if name == "Tasks":
            self.tasks_panel.refresh()
            self.center_stack.setCurrentWidget(self.tasks_panel)
        elif name == "Memory":
            self.memory_panel.refresh()
            self.center_stack.setCurrentWidget(self.memory_panel)
        elif name == "Workspace":
            self._open_workspace()
        elif name == "Workbench":
            self._open_workbench()
        else:
            # Home and everything not yet implemented → cosmos view
            self.center_stack.setCurrentWidget(self.center)

    def _open_workspace(self):
        self.workspace_panel.refresh()
        self.center_stack.setCurrentWidget(self.workspace_panel)

    def _open_workbench(self):
        """Open the AURA Workbench as a SEPARATE window above the companion.
        The companion (orb + this window) keeps running; Workbench becomes
        the active development environment. Shares our StateBus so orb, cosmos
        and workbench are one presence. Lazy-imported so the heavy engineering
        UI only loads when actually opened."""
        if getattr(self, "_workbench", None) is None:
            from ui.workbench_window import WorkbenchWindow
            self._workbench = WorkbenchWindow(bus=self.bus)
        self._workbench.showMaximized()
        self._workbench.raise_()
        self._workbench.activateWindow()

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

    def set_model_text(self, text: str):
        """Show which LLM is actually being used (fed by the controller)."""
        self.stats.set_model(text)

    # mode name → (chip color, input placeholder)
    _MODE_UI = {
        "NORMAL":     (theme.FOCUS_GREEN,   "Talk or type a message..."),
        "PROMPT":     (theme.IDLE_PURPLE,   "PROMPT MODE — buffering… /prompt_end to build"),
        "CODE":       (theme.ACCRETION_BLUE,"💻 CODE MODE — every message is a coding task · /code_end"),
        "RESEARCH":   (theme.ION_CYAN,      "🔍 RESEARCH MODE — structured reports · /research_end"),
        "DISCUSSION": (theme.IDLE_PURPLE,   "🧠 DISCUSSION MODE — I'll challenge ideas · /discussion_end"),
        "PLAN":       (theme.ALERT_ORANGE,  "📋 PLANNING MODE — idea → roadmap · /plan_end"),
        "STUDY":      (theme.ALERT_ORANGE,  "STUDY MODE — /study_end to finish"),
        "DEBUG":      (theme.ERROR_RED,     "DEBUG MODE — /debug_end to finish"),
    }

    def set_mode(self, mode: str):
        """Conversation Director mode → header chip + input placeholder."""
        color, placeholder = self._MODE_UI.get(
            mode, (theme.FOCUS_GREEN, "Talk or type a message..."))
        self.chat.set_mode(mode, color)
        self.chat.input.setPlaceholderText(placeholder)

    def set_plan_panel(self, panel: QWidget):
        """The approval panel floats as a centered overlay card on top of
        the window (docking it into the center column squeezed every row
        into invisible slivers — no visible text or buttons)."""
        panel.setParent(self)
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
