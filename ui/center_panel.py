# ui/center_panel.py
"""
Center column: greeting header, the cosmos hero panel, model-routing
waveform bar, shortcuts row, and the music player. Mock content for now.
"""

from PySide6.QtCore import Qt, QTime, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMenu, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from ui import theme
from ui.cosmos_panel import CosmosPanel
from ui.model_dock import ModelDock
from ui.state import StateBus, state_accent
from ui.widgets import GlassPanel, WaveformWidget

SHORTCUTS = [
    ("⧉", "Open VS Code", "Development"),
    ("🛠", "Aura App", "Coding Platform"),
    ("✎", "Notion", "Notes"),
    ("⌘", "LeetCode", "Practice"),
    ("＋", "Add Shortcut", ""),
]


class _Chip(GlassPanel):
    def __init__(self, top: str, bottom: str, parent=None):
        super().__init__(radius=12, parent=parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(1)
        self.top = QLabel(top)
        self.top.setFont(theme.display_font(11))
        self.top.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; background: transparent; border: none;")
        self.bottom = QLabel(bottom)
        self.bottom.setFont(theme.body_font(8))
        self.bottom.setStyleSheet(
            f"color: {theme.TEXT_DIM}; background: transparent; border: none;")
        lay.addWidget(self.top)
        lay.addWidget(self.bottom)


class _NatureChip(_Chip):
    """The top-bar chip is clickable → nature picker menu."""
    clicked = Signal()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class CenterPanel(QWidget):
    natureSelected = Signal(str)   # nature key, e.g. "chill"
    openWorkspaceRequested = Signal()   # "Aura App" chip → Developer Workspace

    def __init__(self, bus: StateBus, user_name: str = "Shaurya", parent=None):
        super().__init__(parent)
        self._bus = bus
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # ── greeting row ────────────────────────────────────────────────
        head = QHBoxLayout()
        head.setSpacing(10)
        greet_col = QVBoxLayout()
        greet_col.setSpacing(2)
        self.greeting = QLabel(f"Good Evening, {user_name} ✦")
        self.greeting.setFont(theme.display_font(20))
        self.greeting.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
        sub = QLabel("I'm here, ready to help you achieve more today.")
        sub.setFont(theme.body_font(10))
        sub.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        greet_col.addWidget(self.greeting)
        greet_col.addWidget(sub)
        head.addLayout(greet_col, 1)

        self._clock_chip = _Chip("--:--", "Today")
        head.addWidget(self._clock_chip)

        # V2.3: nature selector chip (was the static "Focus Mode Ready" chip)
        self.nature_chip = _NatureChip("🟢 Auto", "Nature · tap to change")
        self.nature_chip.setCursor(Qt.PointingHandCursor)
        self.nature_chip.top.setStyleSheet(
            f"color: {theme.FOCUS_GREEN}; background: transparent; border: none;")
        self.nature_chip.clicked.connect(self._show_nature_menu)
        head.addWidget(self.nature_chip)
        lay.addLayout(head)
        self._seed_nature_chip()

        clock_timer = QTimer(self)
        clock_timer.timeout.connect(self._update_clock)
        clock_timer.start(10_000)
        self._update_clock()

        # ── model lock/unlock dock ──────────────────────────────────────
        self.cosmos = CosmosPanel(bus)
        self.model_dock = ModelDock()
        self.model_dock.lockChanged.connect(self.cosmos.set_locked)
        lay.addWidget(self.model_dock)

        # ── cosmos hero ─────────────────────────────────────────────────
        cosmos_card = GlassPanel(radius=18)
        cc = QVBoxLayout(cosmos_card)
        cc.setContentsMargins(4, 4, 4, 4)
        cc.addWidget(self.cosmos)
        lay.addWidget(cosmos_card, 1)

        # ── model routing bar ───────────────────────────────────────────
        routing = GlassPanel(radius=12)
        r_lay = QHBoxLayout(routing)
        r_lay.setContentsMargins(14, 6, 14, 6)
        self._routing_label = QLabel(f"Model Routing: {bus.active_model}")
        self._routing_label.setFont(theme.mono_font(9))
        self._routing_label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; background: transparent; border: none;")
        self._routing_wave = WaveformWidget(bar_count=40, height=18)
        r_lay.addWidget(self._routing_label)
        r_lay.addWidget(self._routing_wave, 1)
        lay.addWidget(routing)

        # ── shortcuts row ───────────────────────────────────────────────
        sc_row = QHBoxLayout()
        sc_row.setSpacing(8)
        for icon, title, subtitle in SHORTCUTS:
            btn = QPushButton(
                f"{icon}  {title}" + (f"\n     {subtitle}" if subtitle else "")
            )
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(44)
            btn.setFont(theme.body_font(9))
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {theme.GLASS_BG};
                    border: 1px solid {theme.GLASS_BORDER};
                    border-radius: 12px;
                    color: {theme.TEXT_SECONDARY};
                    text-align: left; padding-left: 12px;
                }}
                QPushButton:hover {{
                    border: 1px solid {theme.ACCRETION_BLUE};
                    color: {theme.TEXT_PRIMARY};
                }}
                """
            )
            if title == "Aura App":
                btn.clicked.connect(self.openWorkspaceRequested.emit)
            sc_row.addWidget(btn, 1)
        lay.addLayout(sc_row)

        # ── music player (mock) ─────────────────────────────────────────
        music = GlassPanel(radius=14)
        m_lay = QHBoxLayout(music)
        m_lay.setContentsMargins(14, 8, 14, 8)
        m_lay.setSpacing(12)

        art = QLabel("♫")
        art.setFixedSize(40, 40)
        art.setAlignment(Qt.AlignCenter)
        art.setFont(theme.display_font(16))
        art.setStyleSheet(
            f"""
            color: {theme.ION_CYAN};
            background-color: rgba(61, 43, 122, 0.6);
            border-radius: 10px; border: none;
            """
        )
        m_lay.addWidget(art)

        song_col = QVBoxLayout()
        song_col.setSpacing(1)
        now = QLabel("Now Playing")
        now.setFont(theme.body_font(7))
        now.setStyleSheet(
            f"color: {theme.TEXT_DIM}; background: transparent; border: none;")
        song = QLabel("Interstellar Dreams")
        song.setFont(theme.display_font(10))
        song.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; background: transparent; border: none;")
        artist = QLabel("Hans Zimmer")
        artist.setFont(theme.body_font(8))
        artist.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; background: transparent; border: none;")
        song_col.addWidget(now)
        song_col.addWidget(song)
        song_col.addWidget(artist)
        m_lay.addLayout(song_col)

        m_lay.addStretch()
        for glyph, big in (("⏮", False), ("⏸", True), ("⏭", False)):
            b = QPushButton(glyph)
            size = 38 if big else 30
            b.setFixedSize(size, size)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {'rgba(91, 127, 255, 0.25)' if big
                                       else 'transparent'};
                    border: {'1px solid ' + theme.ACCRETION_BLUE if big else 'none'};
                    border-radius: {size // 2}px;
                    color: {theme.TEXT_PRIMARY}; font-size: {14 if big else 11}px;
                }}
                QPushButton:hover {{ background-color: rgba(91, 127, 255, 0.35); }}
                """
            )
            m_lay.addWidget(b)

        progress = QProgressBar()
        progress.setRange(0, 324)
        progress.setValue(102)
        progress.setTextVisible(False)
        progress.setFixedSize(160, 4)
        progress.setStyleSheet(
            f"""
            QProgressBar {{ background-color: rgba(125, 127, 255, 0.15);
                            border: none; border-radius: 2px; }}
            QProgressBar::chunk {{ background-color: {theme.ACCRETION_BLUE};
                                   border-radius: 2px; }}
            """
        )
        m_lay.addWidget(progress)
        lay.addWidget(music)

        bus.stateChanged.connect(self._on_state)
        bus.activeModelChanged.connect(
            lambda m: self._routing_label.setText(f"Model Routing: {m}"))

    # ── V2.3 nature picker ───────────────────────────────────────────────
    _NATURE_COLORS = {
        "auto": theme.FOCUS_GREEN,
        "chill": theme.ACCRETION_BLUE,
        "focus": theme.FOCUS_GREEN,
        "savage": theme.ERROR_RED,
        "professional": theme.TEXT_PRIMARY,
    }

    def _seed_nature_chip(self):
        try:
            from core.nature import NATURES, get_nature
            self._apply_nature_chip(get_nature(), NATURES)
        except Exception:
            pass   # UI preview without backend — chip stays on Auto

    def _apply_nature_chip(self, key: str, natures: dict):
        n = natures[key]
        color = self._NATURE_COLORS.get(key, theme.FOCUS_GREEN)
        self.nature_chip.top.setText(f"{n['icon']} {n['label']}")
        self.nature_chip.top.setStyleSheet(
            f"color: {color}; background: transparent; border: none;")
        self.nature_chip.bottom.setText(
            "Nature · auto-shifts" if key == "auto" else "Nature · locked")

    def _show_nature_menu(self):
        try:
            from core.nature import NATURES, get_nature
        except Exception:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            f"""
            QMenu {{ background-color: {theme.VOID_BLACK};
                     color: {theme.TEXT_PRIMARY};
                     border: 1px solid {theme.EVENT_VIOLET};
                     border-radius: 8px; padding: 6px; }}
            QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
            QMenu::item:selected {{ background-color: rgba(91, 127, 255, 0.18); }}
            """
        )
        current = get_nature()
        for key, n in NATURES.items():
            mark = "  ✓" if key == current else ""
            action = menu.addAction(f"{n['icon']}  {n['label']}{mark}")
            action.triggered.connect(lambda _=False, k=key: self._pick_nature(k))
        menu.exec(self.nature_chip.mapToGlobal(
            self.nature_chip.rect().bottomLeft()))

    def _pick_nature(self, key: str):
        try:
            from core.nature import NATURES, set_nature
            if set_nature(key):
                self._apply_nature_chip(key, NATURES)
                self.natureSelected.emit(key)
        except Exception as e:
            print(f"[AURA UI] nature pick error: {e}")

    def _update_clock(self):
        self._clock_chip.top.setText(QTime.currentTime().toString("hh:mm AP"))

    def _on_state(self, state: str):
        accent = state_accent(state)
        self._routing_wave.set_color(accent)
        self._routing_wave.set_active(state in ("listening", "speaking", "thinking"))
