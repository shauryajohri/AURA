# aura_ui/orb.py
"""
The floating AURA orb — a frameless, transparent, always-on-top widget
that persists independently of the main window. Lives for the whole
app session; closing the main window does NOT close this.

States: idle, listening, thinking, speaking — each with its own color
language and motion character, painted in real time via QPainter
rather than sprite frames, so transitions can interpolate smoothly.
"""

import math
import random
from PySide6.QtWidgets import QWidget, QMenu
from PySide6.QtCore import (
    Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve,
    Property, Signal, QRectF, QSettings
)
from PySide6.QtGui import (
    QPainter, QColor, QRadialGradient, QPen, QBrush, QAction, QPainterPath
)

# ── Palette ───────────────────────────────────────────────────────────────
VOID_BLACK      = QColor("#05030D")
NEBULA_PURPLE   = QColor("#1A1033")
EVENT_VIOLET    = QColor("#3D2B7A")
ACCRETION_BLUE  = QColor("#5B7FFF")
ION_CYAN        = QColor("#7FE8FF")
STARLIGHT_WHITE = QColor("#F5F3FF")

ORB_SIZE = 120  # default widget diameter in px, including glow margin

# Practical floor only — stops the orb from shrinking to literally zero
# and becoming impossible to grab again. Remove this clamp in
# _apply_resize_delta if you truly want no floor at all.
ORB_MIN_SIZE = 24

# All paint proportions below are expressed as fractions of ORB_SIZE so the
# orb keeps looking like itself (glow, particles, core all scale together)
# at any size instead of looking off-center or clipped.
_REFERENCE_SIZE = float(ORB_SIZE)


class Particle:
    """A single point orbiting the core at a given radius/speed/phase."""
    __slots__ = ("angle", "radius", "speed", "size", "brightness")

    def __init__(self, radius: float):
        self.angle = random.uniform(0, 360)
        self.radius = radius
        self.speed = random.uniform(0.4, 1.2)
        self.size = random.uniform(1.2, 2.8)
        self.brightness = random.uniform(0.5, 1.0)

    def step(self, speed_multiplier: float):
        self.angle = (self.angle + self.speed * speed_multiplier) % 360


class OrbWidget(QWidget):
    """
    Frameless, translucent, always-on-top floating orb.
    Emits signals so the main app can react to interactions without
    the orb needing to know anything about the rest of the app.
    """

    requestRestore   = Signal()   # double-click → bring back main window
    requestQuickPanel = Signal()  # single-click → quick controls popup
    requestQuit       = Signal()  # quit chosen from right-click menu
    requestUnlock      = Signal()  # "stop watching" chosen from right-click menu

    STATE_IDLE      = "idle"
    STATE_LISTENING = "listening"
    STATE_THINKING  = "thinking"
    STATE_SPEAKING  = "speaking"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool                # keeps it off the taskbar
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)

        self._settings = QSettings("AURA", "OrbWidget")
        saved_size = self._settings.value("orb_size", ORB_SIZE, type=int)
        self.resize(saved_size, saved_size)

        self._state = self.STATE_IDLE
        self._rotation = 0.0
        self._pulse_phase = 0.0
        self._glow_intensity = 0.55     # animatable 0..1, eased between states
        self._target_glow = 0.55
        self._drag_offset = None

        # Resize-mode: armed by the right-click menu, consumed by the next
        # drag gesture. While armed/active, mouse drags scale the orb
        # instead of moving it.
        self._resize_armed = False
        self._resizing = False
        self._resize_start_pos = None      # global cursor pos at press
        self._resize_start_size = None      # widget size at press

        # particles orbiting at a few different radii for depth
        self._particles = (
            [Particle(radius=r) for r in (28, 34, 40)] * 3
        )

        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._on_tick)
        self._tick_timer.start(16)  # ~60fps

        self._glow_anim = QPropertyAnimation(self, b"glowIntensity")
        self._glow_anim.setDuration(400)
        self._glow_anim.setEasingCurve(QEasingCurve.InOutCubic)

        # Distinguishes a deliberate single click from the first half of
        # a double click — Qt fires press+release for both, so without
        # this delay, quick-controls would flash open right before the
        # restore happens on every double-click.
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.timeout.connect(self._emit_single_click)
        self._click_pending = False
        self._dragged = False

    # ── Qt property plumbing for animating glow smoothly ─────────────────
    def getGlowIntensity(self):
        return self._glow_intensity

    def setGlowIntensity(self, value):
        self._glow_intensity = value
        self.update()

    glowIntensity = Property(float, getGlowIntensity, setGlowIntensity)

    # ── Public state API ──────────────────────────────────────────────────
    def set_state(self, state: str):
        if state not in (self.STATE_IDLE, self.STATE_LISTENING,
                          self.STATE_THINKING, self.STATE_SPEAKING):
            return
        self._state = state
        targets = {
            self.STATE_IDLE: 0.55,
            self.STATE_LISTENING: 0.75,
            self.STATE_THINKING: 0.85,
            self.STATE_SPEAKING: 1.0,
        }
        self._animate_glow_to(targets[state])

    def _animate_glow_to(self, target: float):
        self._glow_anim.stop()
        self._glow_anim.setStartValue(self._glow_intensity)
        self._glow_anim.setEndValue(target)
        self._glow_anim.start()

    # ── Animation tick ────────────────────────────────────────────────────
    def _on_tick(self):
        speed = {
            self.STATE_IDLE: 0.35,
            self.STATE_LISTENING: 0.6,
            self.STATE_THINKING: 1.6,
            self.STATE_SPEAKING: 0.9,
        }.get(self._state, 0.35)

        self._rotation = (self._rotation + speed) % 360
        self._pulse_phase += 0.05 if self._state != self.STATE_THINKING else 0.09

        for p in self._particles:
            p.step(speed)

        self.update()

    # ── Painting ──────────────────────────────────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        cx, cy = self.width() / 2, self.height() / 2
        scale = min(self.width(), self.height()) / _REFERENCE_SIZE

        core_r = (22 + 3 * math.sin(self._pulse_phase) * (
            1.4 if self._state == self.STATE_LISTENING else
            1.0 if self._state == self.STATE_SPEAKING else 0.5
        )) * scale

        self._paint_outer_glow(painter, cx, cy, scale)
        self._paint_particles(painter, cx, cy, scale)
        self._paint_core(painter, cx, cy, core_r, scale)

        painter.end()

    def _state_colors(self):
        """Returns (inner, mid, outer) colors for the current state."""
        if self._state == self.STATE_IDLE:
            return EVENT_VIOLET, ACCRETION_BLUE, NEBULA_PURPLE
        if self._state == self.STATE_LISTENING:
            return ACCRETION_BLUE, ION_CYAN, EVENT_VIOLET
        if self._state == self.STATE_THINKING:
            return EVENT_VIOLET, ACCRETION_BLUE, QColor("#2A1A55")
        if self._state == self.STATE_SPEAKING:
            return STARLIGHT_WHITE, ION_CYAN, ACCRETION_BLUE
        return EVENT_VIOLET, ACCRETION_BLUE, NEBULA_PURPLE

    def _paint_outer_glow(self, painter, cx, cy, scale):
        inner, mid, outer = self._state_colors()
        glow_r = 50 * (0.85 + 0.3 * self._glow_intensity) * scale

        gradient = QRadialGradient(cx, cy, glow_r)
        c1 = QColor(mid); c1.setAlphaF(0.35 * self._glow_intensity)
        c2 = QColor(outer); c2.setAlphaF(0.0)
        gradient.setColorAt(0.0, c1)
        gradient.setColorAt(1.0, c2)
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(cx - glow_r, cy - glow_r, glow_r * 2, glow_r * 2))

    def _paint_particles(self, painter, cx, cy, scale):
        _, mid, _ = self._state_colors()
        for p in self._particles:
            rad = math.radians(p.angle)
            # slight elliptical squash gives a disk-like orbital feel
            x = cx + p.radius * scale * math.cos(rad)
            y = cy + p.radius * scale * 0.55 * math.sin(rad)
            color = QColor(mid)
            color.setAlphaF(p.brightness * self._glow_intensity)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            size = p.size * scale
            painter.drawEllipse(QRectF(x - size / 2, y - size / 2, size, size))

    def _paint_core(self, painter, cx, cy, radius, scale):
        inner, mid, _ = self._state_colors()
        gradient = QRadialGradient(cx, cy, radius)
        c_in = QColor(inner); c_in.setAlphaF(min(1.0, 0.85 + 0.15 * self._glow_intensity))
        c_out = QColor(mid); c_out.setAlphaF(0.9 * self._glow_intensity)
        gradient.setColorAt(0.0, c_in)
        gradient.setColorAt(0.7, c_out)
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(cx - radius, cy - radius, radius * 2, radius * 2))

        # subtle event-horizon ring — a thin bright edge, more visible when thinking
        if self._state == self.STATE_THINKING:
            pen = QPen(QColor(ION_CYAN))
            pen.setWidthF(1.4 * scale)
            ring_alpha = 0.4 + 0.3 * math.sin(self._pulse_phase * 2)
            pen_color = QColor(ION_CYAN)
            pen_color.setAlphaF(max(0.0, ring_alpha))
            pen.setColor(pen_color)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            ring_offset = 4 * scale
            painter.drawEllipse(QRectF(cx - radius - ring_offset, cy - radius - ring_offset,
                                        (radius + ring_offset) * 2, (radius + ring_offset) * 2))

    # ── Mouse interaction ─────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._resize_armed:
                self._resizing = True
                self._resize_armed = False
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_size = self.width()
                self._dragged = True  # suppress the click/double-click path entirely
            else:
                self._drag_offset = event.globalPosition().toPoint() - self.pos()
                self._dragged = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing and event.buttons() & Qt.LeftButton:
            self._apply_resize_delta(event.globalPosition().toPoint())
        elif self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self._dragged = True
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._resizing:
                self._resizing = False
                self._save_size()
            elif not self._dragged:
                # don't fire yet — wait to see if a second click turns this
                # into a double-click instead
                self._click_pending = True
                self._click_timer.start(220)
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def _apply_resize_delta(self, current_global_pos):
        """Scales the orb based on drag distance from the press point.
        Dragging away from the orb's center grows it; dragging toward
        the center shrinks it — feels like pulling/squeezing the orb
        itself rather than dragging an edge handle."""
        center = self.pos() + QPoint(self._resize_start_size // 2, self._resize_start_size // 2)
        start_dist = max(1, (self._resize_start_pos - center).manhattanLength())
        current_dist = (current_global_pos - center).manhattanLength()

        delta = current_dist - start_dist
        new_size = self._resize_start_size + delta

        # Practical floor only (see ORB_MIN_SIZE comment up top) — no
        # upper limit, per the requirement that it can grow as large as
        # dragged.
        new_size = max(ORB_MIN_SIZE, int(new_size))

        if new_size == self.width():
            return

        # Resize around the same center point so the orb doesn't jump
        # across the screen as it grows/shrinks.
        old_center = self.pos() + QPoint(self.width() // 2, self.height() // 2)
        self.resize(new_size, new_size)
        self.move(old_center - QPoint(new_size // 2, new_size // 2))
        self.update()

    def _save_size(self):
        self._settings.setValue("orb_size", self.width())

    def _emit_single_click(self):
        if self._click_pending:
            self._click_pending = False
            self.requestQuickPanel.emit()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._click_pending = False
            self._click_timer.stop()
            self.requestRestore.emit()
        super().mouseDoubleClickEvent(event)

    def _arm_resize_mode(self):
        """Called from the right-click menu. The *next* press-and-drag on
        the orb will scale it instead of moving it; one resize gesture
        per menu pick, then it's back to normal drag-to-move.
        Only meaningful while floating — if the orb is docked into the
        main window's layout (see dock_orb), free resize/move doesn't
        apply, so this is a no-op in that state."""
        if not bool(self.windowFlags() & Qt.Tool):
            return
        self._resize_armed = True

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1A1033;
                color: #F5F3FF;
                border: 1px solid #3D2B7A;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #3D2B7A;
            }
        """)
        restore_action = QAction("Open AURA", self)
        restore_action.triggered.connect(self.requestRestore.emit)
        menu.addAction(restore_action)

        resize_action = QAction("Resize Orb (drag to scale)", self)
        resize_action.triggered.connect(self._arm_resize_mode)
        menu.addAction(resize_action)

        unlock_action = QAction("Stop watching locked app", self)
        unlock_action.triggered.connect(self.requestUnlock.emit)
        menu.addAction(unlock_action)

        menu.addSeparator()

        quit_action = QAction("Quit AURA", self)
        quit_action.triggered.connect(self.requestQuit.emit)
        menu.addAction(quit_action)

        menu.exec(event.globalPos())