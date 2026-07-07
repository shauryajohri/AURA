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
from PySide6.QtWidgets import QWidget, QMenu, QToolTip
from PySide6.QtCore import (
    Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve,
    Property, Signal, QRectF, QSettings
)
from PySide6.QtGui import (
    QPainter, QColor, QRadialGradient, QConicalGradient, QPen, QBrush,
    QAction, QPainterPath, QGuiApplication
)

from ui.state import AuraState

# ── Palette ───────────────────────────────────────────────────────────────
VOID_BLACK      = QColor("#05030D")
NEBULA_PURPLE   = QColor("#1A1033")
EVENT_VIOLET    = QColor("#3D2B7A")
ACCRETION_BLUE  = QColor("#5B7FFF")
ION_CYAN        = QColor("#7FE8FF")
STARLIGHT_WHITE = QColor("#F5F3FF")
FOCUS_GREEN     = QColor("#3DDC97")
ALERT_ORANGE    = QColor("#FF7A3D")

SNAP_DISTANCE = 90   # px from a screen edge that triggers snapping
SNAP_MARGIN = 14     # resting gap between orb and the edge
SIZE_PRESETS = (("Small", 80), ("Medium", 100), ("Large", 120), ("XL", 160))
OPACITY_PRESETS = (("100%", 1.0), ("85%", 0.85), ("70%", 0.70))

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
    STATE_FOCUS     = "focus"
    STATE_ALERT     = "alert"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._always_on_top = True
        self.setWindowFlags(self._window_flags())
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)

        self._settings = QSettings("AURA", "OrbWidget")
        saved_size = self._settings.value("orb_size", ORB_SIZE, type=int)
        self.resize(saved_size, saved_size)
        self.setWindowOpacity(
            self._settings.value("orb_opacity", 1.0, type=float))
        self._locked = self._settings.value("orb_locked", False, type=bool)
        self._status_task = ""   # optional "Task: ..." tooltip line

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

        # eased glide to the nearest screen edge after a drag
        self._snap_anim = QPropertyAnimation(self, b"pos")
        self._snap_anim.setDuration(320)
        self._snap_anim.setEasingCurve(QEasingCurve.OutCubic)

    def _window_flags(self):
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self._always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        return flags

    # ── Qt property plumbing for animating glow smoothly ─────────────────
    def getGlowIntensity(self):
        return self._glow_intensity

    def setGlowIntensity(self, value):
        self._glow_intensity = value
        self.update()

    glowIntensity = Property(float, getGlowIntensity, setGlowIntensity)

    # ── Public state API ──────────────────────────────────────────────────
    def set_state(self, state: str):
        targets = {
            self.STATE_IDLE: 0.55,
            self.STATE_LISTENING: 0.75,
            self.STATE_THINKING: 0.85,
            self.STATE_SPEAKING: 1.0,
            self.STATE_FOCUS: 0.42,
            self.STATE_ALERT: 1.0,
        }
        if state not in targets:
            return
        self._state = state
        self._animate_glow_to(targets[state])

    def set_status_task(self, text: str):
        """Optional task line for the hover tooltip."""
        self._status_task = text

    def attach_bus(self, bus):
        """Follow the app-wide StateBus so orb + window are one presence."""
        bus.stateChanged.connect(self.set_state)

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
            self.STATE_FOCUS: 0.2,
            self.STATE_ALERT: 2.4,
        }.get(self._state, 0.35)

        self._rotation = (self._rotation + speed) % 360
        self._pulse_phase += 0.05 if self._state != self.STATE_THINKING else 0.09

        for p in self._particles:
            p.step(speed)

        self.update()

    # ── Painting ──────────────────────────────────────────────────────────
    # The floating orb is now a true black hole, matching the cosmos core and
    # the sidebar mini-orb: a genuinely BLACK event horizon with a bright
    # accretion ring and orbiting disk sparks, rather than the old glowing
    # violet blob. State drives the accent color, ring speed, and glow.
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        cx, cy = self.width() / 2, self.height() / 2
        base = min(self.width(), self.height())

        # breathing core; listening/speaking pulse a little harder
        amp = (0.09 if self._state == self.STATE_LISTENING else
               0.06 if self._state == self.STATE_SPEAKING else 0.035)
        breathe = 1.0 + amp * math.sin(self._pulse_phase)
        core_r = base * 0.17 * breathe

        self._paint_outer_glow(painter, cx, cy, core_r)
        self._paint_disk_sparks(painter, cx, cy, base)
        self._paint_accretion_ring(painter, cx, cy, core_r)
        self._paint_event_horizon(painter, cx, cy, core_r)

        painter.end()

    def _state_colors(self):
        """Returns (accent, mid, outer) colors for the current state.
        `accent` is the bright ring/rim color that reads the state."""
        if self._state == self.STATE_IDLE:
            return EVENT_VIOLET, ACCRETION_BLUE, NEBULA_PURPLE
        if self._state == self.STATE_LISTENING:
            return ACCRETION_BLUE, ION_CYAN, EVENT_VIOLET
        if self._state == self.STATE_THINKING:
            # white hole — "I'm working." without a word
            return STARLIGHT_WHITE, QColor("#C9CCD8"), QColor("#4A4A5E")
        if self._state == self.STATE_SPEAKING:
            return ION_CYAN, STARLIGHT_WHITE, ACCRETION_BLUE
        if self._state == self.STATE_FOCUS:
            return FOCUS_GREEN, FOCUS_GREEN, QColor("#0F3D2B")
        if self._state == self.STATE_ALERT:
            return ALERT_ORANGE, ALERT_ORANGE, QColor("#552B1A")
        return EVENT_VIOLET, ACCRETION_BLUE, NEBULA_PURPLE

    def _paint_outer_glow(self, painter, cx, cy, core_r):
        accent, _, _ = self._state_colors()
        glow_r = core_r * 3.2
        gradient = QRadialGradient(cx, cy, glow_r)
        c1 = QColor(accent); c1.setAlphaF(0.22 * (0.6 + 0.4 * self._glow_intensity))
        c2 = QColor(accent); c2.setAlphaF(0.0)
        gradient.setColorAt(0.25, c1)
        gradient.setColorAt(1.0, c2)
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(cx - glow_r, cy - glow_r, glow_r * 2, glow_r * 2))

    def _paint_disk_sparks(self, painter, cx, cy, base):
        """Orbiting motes, squashed into a tilted disk around the hole."""
        accent, _, _ = self._state_colors()
        scale = base / _REFERENCE_SIZE
        for p in self._particles:
            rad = math.radians(p.angle)
            x = cx + p.radius * scale * math.cos(rad)
            y = cy + p.radius * scale * 0.42 * math.sin(rad)   # disk tilt
            color = QColor(accent)
            color.setAlphaF(min(1.0, p.brightness * (0.5 + 0.5 * self._glow_intensity)))
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            size = p.size * scale
            painter.drawEllipse(QRectF(x - size / 2, y - size / 2, size, size))

    def _paint_accretion_ring(self, painter, cx, cy, core_r):
        """Bright conical-gradient ring, rotating, squashed to read as a disk
        seen at an angle — the signature black-hole accretion disk."""
        accent, _, _ = self._state_colors()
        painter.save()
        painter.translate(cx, cy)
        painter.scale(1.0, 0.42)

        cone = QConicalGradient(0, 0, self._rotation)
        bright = QColor(accent); bright.setAlphaF(0.95)
        mid = QColor(EVENT_VIOLET); mid.setAlphaF(0.55)
        dim = QColor(NEBULA_PURPLE); dim.setAlphaF(0.25)
        cone.setColorAt(0.00, bright)
        cone.setColorAt(0.25, mid)
        cone.setColorAt(0.50, dim)
        cone.setColorAt(0.75, mid)
        cone.setColorAt(1.00, bright)

        ring_r = core_r * 2.0
        pen = QPen(QBrush(cone), core_r * 0.36)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(-ring_r, -ring_r, ring_r * 2, ring_r * 2))
        painter.restore()

    def _paint_event_horizon(self, painter, cx, cy, core_r):
        """A truly black core with a thin bright rim — the event horizon."""
        accent, _, _ = self._state_colors()
        r = core_r * 1.15
        hole = QRadialGradient(cx, cy, r)
        hole.setColorAt(0.0, QColor(0, 0, 0))
        hole.setColorAt(0.86, QColor(0, 0, 0))
        rim = QColor(accent)
        rim.setAlphaF(min(1.0, 0.7 + 0.3 * self._glow_intensity))
        hole.setColorAt(0.97, rim)
        hole.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(hole))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

    # ── Hover tooltip ─────────────────────────────────────────────────────
    def enterEvent(self, event):
        lines = ["AURA ✦", f"Mode: {AuraState.LABELS.get(self._state, '—')}"]
        if self._status_task:
            lines.append(f"Task: {self._status_task}")
        QToolTip.showText(self.mapToGlobal(QPoint(self.width(), 0)),
                          "\n".join(lines), self)
        super().enterEvent(event)

    # ── Mouse interaction ─────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._resize_armed:
                self._resizing = True
                self._resize_armed = False
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_size = self.width()
                self._dragged = True  # suppress the click/double-click path entirely
            elif not self._locked:
                self._drag_offset = event.globalPosition().toPoint() - self.pos()
                self._dragged = False
            else:
                self._drag_offset = None
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
            elif self._dragged:
                self._snap_to_edge()
            else:
                # don't fire yet — wait to see if a second click turns this
                # into a double-click instead
                self._click_pending = True
                self._click_timer.start(220)
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    # ── Snap to edges ─────────────────────────────────────────────────────
    def _snap_to_edge(self):
        """After a drag, glide to the nearest screen edge if close enough —
        the orb prefers to rest at the sides, out of the way."""
        screen = QGuiApplication.screenAt(self.geometry().center())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()

        x, y, w = self.x(), self.y(), self.width()
        candidates = (
            (x - geo.left(), "left"),
            (geo.right() - (x + w), "right"),
            (y - geo.top(), "top"),
            (geo.bottom() - (y + w), "bottom"),
        )
        dist, edge = min(candidates)
        if dist > SNAP_DISTANCE:
            return  # nowhere near an edge — rest where dropped

        tx, ty = x, y
        if edge == "left":
            tx = geo.left() + SNAP_MARGIN
        elif edge == "right":
            tx = geo.right() - w - SNAP_MARGIN
        elif edge == "top":
            ty = geo.top() + SNAP_MARGIN
        else:
            ty = geo.bottom() - w - SNAP_MARGIN
        # clamp the free axis so the orb never rests off-screen
        tx = max(geo.left() + 2, min(tx, geo.right() - w - 2))
        ty = max(geo.top() + 2, min(ty, geo.bottom() - w - 2))

        self._snap_anim.stop()
        self._snap_anim.setStartValue(self.pos())
        self._snap_anim.setEndValue(QPoint(int(tx), int(ty)))
        self._snap_anim.start()

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

    # ── Menu actions ──────────────────────────────────────────────────────
    def _set_size_preset(self, size: int):
        old_center = self.pos() + QPoint(self.width() // 2, self.height() // 2)
        self.resize(size, size)
        self.move(old_center - QPoint(size // 2, size // 2))
        self._save_size()

    def _toggle_lock(self):
        self._locked = not self._locked
        self._settings.setValue("orb_locked", self._locked)

    def _set_opacity(self, value: float):
        self.setWindowOpacity(value)
        self._settings.setValue("orb_opacity", value)

    def _toggle_always_on_top(self):
        self._always_on_top = not self._always_on_top
        pos = self.pos()
        self.setWindowFlags(self._window_flags())
        self.move(pos)
        self.show()

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
        menu.addSeparator()

        size_menu = menu.addMenu("Size")
        size_menu.setStyleSheet(menu.styleSheet())
        for label, px in SIZE_PRESETS:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(abs(self.width() - px) < 8)
            act.triggered.connect(lambda _, s=px: self._set_size_preset(s))
            size_menu.addAction(act)
        free_resize = QAction("Free resize (drag to scale)", self)
        free_resize.triggered.connect(self._arm_resize_mode)
        size_menu.addAction(free_resize)

        opacity_menu = menu.addMenu("Opacity")
        opacity_menu.setStyleSheet(menu.styleSheet())
        for label, val in OPACITY_PRESETS:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(abs(self.windowOpacity() - val) < 0.03)
            act.triggered.connect(lambda _, v=val: self._set_opacity(v))
            opacity_menu.addAction(act)

        lock_action = QAction("Lock Position", self)
        lock_action.setCheckable(True)
        lock_action.setChecked(self._locked)
        lock_action.triggered.connect(self._toggle_lock)
        menu.addAction(lock_action)

        on_top_action = QAction("Always on Top", self)
        on_top_action.setCheckable(True)
        on_top_action.setChecked(self._always_on_top)
        on_top_action.triggered.connect(self._toggle_always_on_top)
        menu.addAction(on_top_action)

        menu.addSeparator()
        unlock_action = QAction("Stop watching locked app", self)
        unlock_action.triggered.connect(self.requestUnlock.emit)
        menu.addAction(unlock_action)

        menu.addSeparator()
        quit_action = QAction("Quit AURA", self)
        quit_action.triggered.connect(self.requestQuit.emit)
        menu.addAction(quit_action)

        menu.exec(event.globalPos())