# ui/widgets.py
"""
Small shared building blocks: glass panels, waveform bars, status chips.
Kept dependency-light so every panel can pull from here without cycles.
"""

import math
import random

from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QBrush
from PySide6.QtWidgets import QFrame, QLabel, QWidget

from ui import theme


class GlassPanel(QFrame):
    """Rounded glassmorphism container used by every panel."""

    def __init__(self, radius: int = 16, parent=None):
        super().__init__(parent)
        self.setObjectName("glassPanel")
        self.setStyleSheet(
            f"QFrame#glassPanel {{ {theme.panel_stylesheet(radius)} }}"
        )


class StatusChip(QLabel):
    """Tiny pill label — ACTIVE / STANDBY / state names."""

    def __init__(self, text: str, color: str, parent=None):
        super().__init__(text, parent)
        self.set_chip(text, color)

    def set_chip(self, text: str, color: str):
        self.setText(text.upper())
        self.setFont(theme.mono_font(8))
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            f"""
            color: {color};
            background-color: rgba(26, 16, 51, 0.85);
            border: 1px solid {color};
            border-radius: 7px;
            padding: 1px 8px;
            """
        )


class WaveformWidget(QWidget):
    """
    Animated audio-style bars. `set_active(True)` makes them dance;
    inactive bars settle to a low flat line. Color follows presence state.
    """

    def __init__(self, bar_count: int = 24, height: int = 26, parent=None):
        super().__init__(parent)
        self._bars = bar_count
        self._phases = [random.uniform(0, math.tau) for _ in range(bar_count)]
        self._speeds = [random.uniform(0.15, 0.35) for _ in range(bar_count)]
        self._levels = [0.15] * bar_count
        self._active = True
        self._color = QColor(theme.ACCRETION_BLUE)
        self.setFixedHeight(height)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def set_active(self, active: bool):
        self._active = active

    def set_color(self, color: str):
        self._color = QColor(color)

    def _tick(self):
        if not self.isVisible():
            return
        for i in range(self._bars):
            self._phases[i] += self._speeds[i]
            target = (
                0.25 + 0.75 * abs(math.sin(self._phases[i]))
                if self._active else 0.12
            )
            # ease toward target so activity changes feel fluid, not snappy
            self._levels[i] += (target - self._levels[i]) * 0.25
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width() / self._bars
        bar_w = max(1.5, w * 0.55)
        mid = self.height() / 2
        for i, level in enumerate(self._levels):
            h = max(2.0, level * self.height())
            color = QColor(self._color)
            color.setAlphaF(0.35 + 0.65 * level)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            x = i * w + (w - bar_w) / 2
            painter.drawRoundedRect(
                QRectF(x, mid - h / 2, bar_w, h), bar_w / 2, bar_w / 2
            )
        painter.end()


class DotLabel(QWidget):
    """A colored status dot next to a text label (e.g. '● Active')."""

    def __init__(self, text: str, color: str, parent=None):
        super().__init__(parent)
        self._text = text
        self._color = QColor(color)
        self.setMinimumHeight(18)

    def set_dot(self, text: str, color: str):
        self._text = text
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(self._color))
        painter.setPen(Qt.NoPen)
        r = 3.5
        painter.drawEllipse(QRectF(2, self.height() / 2 - r, r * 2, r * 2))
        painter.setPen(QColor(theme.TEXT_SECONDARY))
        painter.setFont(theme.body_font(9))
        painter.drawText(
            QRectF(14, 0, self.width() - 14, self.height()),
            Qt.AlignVCenter | Qt.AlignLeft,
            self._text,
        )
        painter.end()
