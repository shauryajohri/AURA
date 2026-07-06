# ui/cosmos_panel.py
"""
The hero of the main window: AURA Core rendered as a living black hole
with an accretion ring, cosmic dust, and five "model planets" orbiting
it (GPT / Claude / Gemini / Grok / Local). The active model glows and
carries an ACTIVE chip; the core's ring color follows presence state.

Pure QPainter on a timer — no assets, everything procedural, so state
transitions can interpolate instead of swapping sprites.
"""

import math
import random

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QRadialGradient, QConicalGradient, QPen, QBrush,
)
from PySide6.QtWidgets import QWidget

from ui import theme
from ui.state import AuraState, StateBus, state_accent


class _Planet:
    def __init__(self, name, role, color, rx, ry, speed, phase):
        self.name = name
        self.role = role
        self.color = QColor(color)
        self.rx = rx          # orbit radii as fractions of panel size
        self.ry = ry
        self.speed = speed
        self.angle = phase


class _Dust:
    __slots__ = ("angle", "radius", "speed", "size", "alpha")

    def __init__(self):
        self.angle = random.uniform(0, 360)
        self.radius = random.uniform(0.16, 0.34)   # fraction of min(w,h)
        self.speed = random.uniform(0.3, 1.1)
        self.size = random.uniform(1.0, 2.4)
        self.alpha = random.uniform(0.25, 0.8)


class CosmosPanel(QWidget):
    """Animated cosmos canvas. Reads presence + active model from StateBus."""

    PLANETS = [
        # name           role                    color                          rx     ry     speed  phase
        ("GPT-4o",       "General Intelligence", theme.MODEL_COLORS["GPT-4o"],       0.38, 0.30, 0.30, 200),
        ("Claude 3.5",   "Deep Reasoning",       theme.MODEL_COLORS["Claude 3.5"],   0.44, 0.34, 0.22, 330),
        ("Gemini 1.5",   "Research & Analysis",  theme.MODEL_COLORS["Gemini 1.5"],   0.42, 0.33, 0.26, 140),
        ("Grok 2",       "Real-time Intel",      theme.MODEL_COLORS["Grok 2"],       0.46, 0.36, 0.19, 30),
        ("Local (LLM)",  "Local Processing",     theme.MODEL_COLORS["Local (LLM)"],  0.33, 0.26, 0.36, 80),
    ]

    def __init__(self, bus: StateBus, parent=None):
        super().__init__(parent)
        self._bus = bus
        self._rotation = 0.0
        self._pulse = 0.0
        self._stars = []
        self._dust = [_Dust() for _ in range(70)]
        self._planets = [_Planet(*p) for p in self.PLANETS]
        self.setMinimumHeight(360)

        bus.stateChanged.connect(lambda *_: self.update())
        bus.activeModelChanged.connect(lambda *_: self.update())

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # ~30 fps: fluid, but kind to the CPU

    # ── animation ────────────────────────────────────────────────────────
    def _tick(self):
        if not self.isVisible():
            return
        state = self._bus.state
        speed = {
            AuraState.IDLE: 0.25,
            AuraState.LISTENING: 0.45,
            AuraState.THINKING: 1.1,
            AuraState.SPEAKING: 0.7,
            AuraState.FOCUS: 0.2,
            AuraState.ALERT: 1.5,
        }.get(state, 0.3)

        self._rotation = (self._rotation + speed) % 360
        self._pulse += 0.06 if state == AuraState.THINKING else 0.035
        for d in self._dust:
            d.angle = (d.angle + d.speed * speed) % 360
        for p in self._planets:
            p.angle = (p.angle + p.speed) % 360
        self.update()

    def resizeEvent(self, event):
        # regenerate the starfield to fill the new size
        rng = random.Random(42)  # stable field — stars don't jump on resize
        self._stars = [
            (rng.uniform(0, 1), rng.uniform(0, 1),
             rng.uniform(0.4, 1.4), rng.uniform(0, math.tau))
            for _ in range(110)
        ]
        super().resizeEvent(event)

    # ── painting ─────────────────────────────────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2 - 10
        base = min(w, h)

        self._paint_stars(painter, w, h)

        # split planets into behind/in-front of the core for cheap depth
        back, front = [], []
        for p in self._planets:
            (back if math.sin(math.radians(p.angle)) < 0 else front).append(p)

        for p in back:
            self._paint_planet(painter, p, cx, cy, base)
        self._paint_core(painter, cx, cy, base)
        for p in front:
            self._paint_planet(painter, p, cx, cy, base)

        self._paint_captions(painter, cx, cy, base)
        painter.end()

    def _paint_stars(self, painter, w, h):
        for fx, fy, size, phase in self._stars:
            twinkle = 0.4 + 0.6 * abs(math.sin(self._pulse * 0.7 + phase))
            c = QColor(theme.STARLIGHT_WHITE)
            c.setAlphaF(0.10 + 0.22 * twinkle)
            painter.setBrush(QBrush(c))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(fx * w, fy * h), size, size)

    def _paint_core(self, painter, cx, cy, base):
        state = self._bus.state
        accent = QColor(state_accent(state))
        core_r = base * 0.115
        breathe = 1.0 + 0.04 * math.sin(self._pulse)
        core_r *= breathe

        # 1. wide soft glow
        glow_r = core_r * 3.2
        g = QRadialGradient(cx, cy, glow_r)
        c1 = QColor(accent); c1.setAlphaF(0.20)
        c2 = QColor(accent); c2.setAlphaF(0.0)
        g.setColorAt(0.25, c1)
        g.setColorAt(1.0, c2)
        painter.setBrush(QBrush(g))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # 2. orbiting dust (accretion disk sparks), squashed elliptically
        for d in self._dust:
            rad = math.radians(d.angle)
            r = d.radius * base
            x = cx + r * math.cos(rad)
            y = cy + r * 0.42 * math.sin(rad)
            c = QColor(accent)
            c.setAlphaF(d.alpha * 0.7)
            painter.setBrush(QBrush(c))
            painter.drawEllipse(QPointF(x, y), d.size, d.size)

        # 3. accretion ring — conical gradient rotated by time, drawn as a
        #    squashed ellipse ring so the disk reads at an angle
        painter.save()
        painter.translate(cx, cy)
        painter.scale(1.0, 0.42)
        ring_outer = core_r * 2.1 / 0.42 * 0.42  # keep visual proportion
        ring_outer = core_r * 2.1
        cone = QConicalGradient(0, 0, self._rotation)
        bright = QColor(accent)
        mid = QColor(theme.EVENT_VIOLET)
        dimc = QColor(theme.NEBULA_PURPLE)
        bright.setAlphaF(0.95); mid.setAlphaF(0.55); dimc.setAlphaF(0.25)
        cone.setColorAt(0.00, bright)
        cone.setColorAt(0.25, mid)
        cone.setColorAt(0.50, dimc)
        cone.setColorAt(0.75, mid)
        cone.setColorAt(1.00, bright)
        pen = QPen(QBrush(cone), core_r * 0.38)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(0, 0), ring_outer, ring_outer)
        painter.restore()

        # 4. the event horizon — a truly black core with a thin bright rim
        hole = QRadialGradient(cx, cy, core_r * 1.15)
        hole.setColorAt(0.0, QColor(0, 0, 0))
        hole.setColorAt(0.86, QColor(0, 0, 0))
        rim = QColor(accent); rim.setAlphaF(0.9)
        hole.setColorAt(0.97, rim)
        hole.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(hole))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), core_r * 1.15, core_r * 1.15)

    def _paint_planet(self, painter, p: _Planet, cx, cy, base):
        rad = math.radians(p.angle)
        x = cx + p.rx * base * math.cos(rad)
        y = cy + p.ry * base * math.sin(rad) * 0.9
        depth = 0.75 + 0.25 * math.sin(rad)   # slightly smaller when "behind"
        r = base * 0.032 * depth

        is_active = p.name == self._bus.active_model

        # faint orbit path
        pen = QPen(QColor(255, 255, 255, 14))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), p.rx * base, p.ry * base * 0.9)

        # glow
        glow = QRadialGradient(x, y, r * 3.0)
        gc = QColor(p.color)
        gc.setAlphaF(0.45 if is_active else 0.18)
        ge = QColor(p.color); ge.setAlphaF(0.0)
        glow.setColorAt(0.0, gc)
        glow.setColorAt(1.0, ge)
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(x, y), r * 3.0, r * 3.0)

        # body
        body = QRadialGradient(x - r * 0.35, y - r * 0.35, r * 1.7)
        lit = QColor(p.color).lighter(130)
        dark = QColor(p.color).darker(320)
        body.setColorAt(0.0, lit)
        body.setColorAt(1.0, dark)
        painter.setBrush(QBrush(body))
        painter.drawEllipse(QPointF(x, y), r, r)

        # label
        painter.setPen(QColor(theme.TEXT_PRIMARY))
        painter.setFont(theme.display_font(9))
        painter.drawText(QRectF(x - 70, y + r + 4, 140, 14),
                         Qt.AlignHCenter, p.name)
        painter.setPen(QColor(theme.TEXT_DIM))
        painter.setFont(theme.body_font(8))
        painter.drawText(QRectF(x - 70, y + r + 18, 140, 12),
                         Qt.AlignHCenter, p.role)

        chip = "ACTIVE" if is_active else "STANDBY"
        chip_color = QColor(p.color) if is_active else QColor(theme.TEXT_DIM)
        painter.setPen(chip_color)
        painter.setFont(theme.mono_font(7))
        painter.drawText(QRectF(x - 70, y + r + 31, 140, 11),
                         Qt.AlignHCenter, chip)

    def _paint_captions(self, painter, cx, cy, base):
        state = self._bus.state
        accent = QColor(state_accent(state))
        core_r = base * 0.115

        painter.setPen(QColor(theme.TEXT_PRIMARY))
        painter.setFont(theme.display_font(12))
        painter.drawText(QRectF(cx - 120, cy - core_r * 2.6 - 34, 240, 18),
                         Qt.AlignHCenter, "AURA Core")
        painter.setPen(QColor(theme.TEXT_DIM))
        painter.setFont(theme.body_font(8))
        painter.drawText(QRectF(cx - 120, cy - core_r * 2.6 - 16, 240, 14),
                         Qt.AlignHCenter, "Consciousness Engine")

        # state chip under the caption
        label = AuraState.LABELS[state].rstrip(".").upper().replace("...", "")
        painter.setFont(theme.mono_font(8))
        painter.setPen(accent)
        painter.drawText(QRectF(cx - 120, cy - core_r * 2.6 - 2, 240, 14),
                         Qt.AlignHCenter, label)
