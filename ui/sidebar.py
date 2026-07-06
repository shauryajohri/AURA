# ui/sidebar.py
"""
Left column: logo, navigation, the embedded mini-orb presence panel
(orb = emotion, always visible even inside the window), and Voice Mode.
"""

import math
import random

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal
from PySide6.QtGui import QPainter, QColor, QRadialGradient, QBrush, QPen
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ui import theme
from ui.state import AuraState, StateBus, state_accent
from ui.widgets import GlassPanel, WaveformWidget, DotLabel

NAV_ITEMS = [
    ("⌂", "Home"),
    ("☑", "Tasks"),
    ("◈", "Memory"),
    ("✦", "Models"),
    ("♫", "Music"),
    ("⚙", "Automation"),
    ("⛭", "Settings"),
]


class MiniOrb(QWidget):
    """
    Small embedded orb that mirrors AURA's presence inside the window.
    Same visual language as the floating orb, simplified: dark core,
    accent ring, orbiting sparks. Follows all six states via StateBus.
    """

    def __init__(self, bus: StateBus, size: int = 110, parent=None):
        super().__init__(parent)
        self._bus = bus
        self._rotation = 0.0
        self._pulse = 0.0
        self._sparks = [
            (random.uniform(0, 360), random.uniform(0.62, 0.85),
             random.uniform(0.5, 1.3), random.uniform(0.4, 1.0))
            for _ in range(14)
        ]
        self.setFixedSize(size, size)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def _tick(self):
        if not self.isVisible():
            return
        speed = {
            AuraState.IDLE: 0.3,
            AuraState.LISTENING: 0.7,
            AuraState.THINKING: 1.6,
            AuraState.SPEAKING: 1.0,
            AuraState.FOCUS: 0.25,
            AuraState.ALERT: 2.2,
        }.get(self._bus.state, 0.3)
        self._rotation = (self._rotation + speed) % 360
        self._pulse += 0.08 if self._bus.state == AuraState.THINKING else 0.045
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx = cy = self.width() / 2
        accent = QColor(state_accent(self._bus.state))
        base = self.width()
        core_r = base * 0.24 * (1.0 + 0.05 * math.sin(self._pulse))

        # glow
        glow = QRadialGradient(cx, cy, base * 0.5)
        g1 = QColor(accent); g1.setAlphaF(0.30)
        g2 = QColor(accent); g2.setAlphaF(0.0)
        glow.setColorAt(0.2, g1)
        glow.setColorAt(1.0, g2)
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), base * 0.5, base * 0.5)

        # sparks
        for angle0, rf, speed, alpha in self._sparks:
            a = math.radians(angle0 + self._rotation * speed)
            x = cx + rf * base * 0.42 * math.cos(a)
            y = cy + rf * base * 0.42 * 0.6 * math.sin(a)
            c = QColor(accent); c.setAlphaF(alpha * 0.8)
            painter.setBrush(QBrush(c))
            painter.drawEllipse(QPointF(x, y), 1.6, 1.6)

        # ring
        pen = QPen(accent, 2.0)
        ring_alpha = 0.55 + 0.3 * math.sin(self._pulse * 1.5)
        rc = QColor(accent); rc.setAlphaF(max(0.2, ring_alpha))
        pen.setColor(rc)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.save()
        painter.translate(cx, cy)
        painter.scale(1.0, 0.62)
        painter.rotate(0)
        painter.drawEllipse(QPointF(0, 0), core_r * 1.55, core_r * 1.55)
        painter.restore()

        # black core
        hole = QRadialGradient(cx, cy, core_r * 1.1)
        hole.setColorAt(0.0, QColor(0, 0, 0))
        hole.setColorAt(0.85, QColor(0, 0, 0))
        rim = QColor(accent); rim.setAlphaF(0.85)
        hole.setColorAt(0.97, rim)
        hole.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(hole))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), core_r * 1.1, core_r * 1.1)
        painter.end()


class Sidebar(QWidget):
    navSelected = Signal(str)   # "Home", "Tasks", "Memory", ...

    def __init__(self, bus: StateBus, parent=None):
        super().__init__(parent)
        self._bus = bus
        self._nav_buttons = {}
        self._active_nav = "Home"
        self.setFixedWidth(200)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # ── logo ────────────────────────────────────────────────────────
        logo_panel = GlassPanel(radius=16)
        logo_lay = QHBoxLayout(logo_panel)
        logo_lay.setContentsMargins(14, 12, 14, 12)
        glyph = QLabel("◉")
        glyph.setFont(theme.display_font(18))
        glyph.setStyleSheet(
            f"color: {theme.IDLE_PURPLE}; background: transparent; border: none;")
        name_col = QVBoxLayout()
        name = QLabel("A U R A")
        name.setFont(theme.display_font(14))
        name.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; background: transparent; border: none;")
        tag = QLabel("Your AI Companion")
        tag.setFont(theme.body_font(8))
        tag.setStyleSheet(
            f"color: {theme.TEXT_DIM}; background: transparent; border: none;")
        name_col.addWidget(name)
        name_col.addWidget(tag)
        logo_lay.addWidget(glyph)
        logo_lay.addLayout(name_col)
        logo_lay.addStretch()
        lay.addWidget(logo_panel)

        # ── nav ─────────────────────────────────────────────────────────
        nav_panel = GlassPanel(radius=16)
        nav_lay = QVBoxLayout(nav_panel)
        nav_lay.setContentsMargins(8, 10, 8, 10)
        nav_lay.setSpacing(2)
        for icon, label in NAV_ITEMS:
            btn = QPushButton(f"{icon}   {label}")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(34)
            btn.clicked.connect(lambda _, n=label: self._set_active(n))
            self._nav_buttons[label] = btn
            nav_lay.addWidget(btn)
        self._refresh_nav()
        lay.addWidget(nav_panel)

        # ── orb presence panel ──────────────────────────────────────────
        orb_panel = GlassPanel(radius=16)
        orb_lay = QVBoxLayout(orb_panel)
        orb_lay.setContentsMargins(12, 10, 12, 12)
        orb_lay.setSpacing(6)

        head = QHBoxLayout()
        title = QLabel("AURA ORB")
        title.setFont(theme.display_font(9))
        title.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; background: transparent; border: none;")
        self._orb_dot = DotLabel("Active", theme.FOCUS_GREEN)
        self._orb_dot.setFixedWidth(88)
        head.addWidget(title)
        head.addStretch()
        head.addWidget(self._orb_dot)
        orb_lay.addLayout(head)

        self.mini_orb = MiniOrb(bus)
        orb_lay.addWidget(self.mini_orb, 0, Qt.AlignHCenter)

        self._state_label = QLabel(AuraState.LABELS[bus.state])
        self._state_label.setFont(theme.body_font(10))
        self._state_label.setAlignment(Qt.AlignHCenter)
        self._state_label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; background: transparent; border: none;")
        orb_lay.addWidget(self._state_label)

        self._wave = WaveformWidget(bar_count=20, height=22)
        orb_lay.addWidget(self._wave)
        lay.addWidget(orb_panel, 1)

        # ── voice mode button ───────────────────────────────────────────
        voice = QPushButton("🎙  Voice Mode\nTap to speak")
        voice.setCursor(Qt.PointingHandCursor)
        voice.setFixedHeight(52)
        voice.setFont(theme.display_font(10))
        voice.setStyleSheet(
            f"""
            QPushButton {{
                background-color: rgba(61, 43, 122, 0.5);
                border: 1px solid {theme.EVENT_VIOLET};
                border-radius: 14px;
                color: {theme.TEXT_PRIMARY};
            }}
            QPushButton:hover {{
                border: 1px solid {theme.ACCRETION_BLUE};
                background-color: rgba(91, 127, 255, 0.18);
            }}
            """
        )
        self.voice_button = voice
        lay.addWidget(voice)

        bus.stateChanged.connect(self._on_state)

    def _set_active(self, name: str):
        self._active_nav = name
        self._refresh_nav()
        self.navSelected.emit(name)

    def _refresh_nav(self):
        for label, btn in self._nav_buttons.items():
            active = label == self._active_nav
            btn.setFont(theme.display_font(10) if active else theme.body_font(10))
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    text-align: left; padding-left: 14px;
                    border-radius: 10px; border: none;
                    color: {theme.TEXT_PRIMARY if active else theme.TEXT_SECONDARY};
                    background-color: {'rgba(91, 127, 255, 0.18)' if active
                                       else 'transparent'};
                }}
                QPushButton:hover {{
                    background-color: rgba(125, 127, 255, 0.10);
                    color: {theme.TEXT_PRIMARY};
                }}
                """
            )

    # ── backend hooks ───────────────────────────────────────────────────
    def set_voice_status(self, text: str):
        self.voice_button.setText(f"🎙  Voice Mode\n{text}")

    def set_presence(self, presence: str):
        """presence: 'working' | 'idle' | 'afk' (from proactive engine)."""
        mapping = {
            "working": ("Working", theme.ACCRETION_BLUE),
            "idle":    ("Active", theme.FOCUS_GREEN),
            "afk":     ("Away", theme.TEXT_DIM),
        }
        text, color = mapping.get(presence, ("Active", theme.FOCUS_GREEN))
        self._orb_dot.set_dot(text, color)

    def _on_state(self, state: str):
        self._state_label.setText(AuraState.LABELS[state])
        accent = state_accent(state)
        self._wave.set_color(accent)
        self._wave.set_active(state in (AuraState.LISTENING,
                                        AuraState.SPEAKING,
                                        AuraState.THINKING))
