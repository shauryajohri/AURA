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


# The reference-look disk palette: violet → magenta → orange → blue sparks.
DISK_PALETTE = ("#8B3DFF", "#C44FFF", "#FF4FD8", "#FF8A3D", "#5B7FFF")


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    """Linear blend between two colors (ignores alpha)."""
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )


class _Planet:
    def __init__(self, name, role, color, rx, ry, speed, phase):
        self.name = name
        self.role = role
        self.color = QColor(color)
        # The tuple's rx/ry are the NEAR (unlocked) orbit. A locked model
        # drifts out to an edge orbit; rx/ry animate between the two so the
        # transition glides instead of snapping.
        self.near_rx = rx
        self.near_ry = ry
        self.edge_rx = rx + 0.24
        self.edge_ry = ry + 0.18
        self.rx = rx          # current animated orbit radii (fractions)
        self.ry = ry
        self.speed = speed
        self.angle = phase
        self.locked = False

    def target(self):
        return ((self.edge_rx, self.edge_ry) if self.locked
                else (self.near_rx, self.near_ry))


class _Dust:
    __slots__ = ("angle", "radius", "speed", "size", "alpha", "color")

    def __init__(self):
        self.angle = random.uniform(0, 360)
        self.radius = random.uniform(0.16, 0.34)   # fraction of min(w,h)
        self.speed = random.uniform(0.3, 1.1)
        self.size = random.uniform(1.0, 2.4)
        self.alpha = random.uniform(0.25, 0.8)
        self.color = QColor(random.choice(DISK_PALETTE))


class _Comet:
    """A shooting star: bright head, tapered trail, crosses the panel once."""

    def __init__(self, w: int, h: int):
        speed = random.uniform(6.0, 11.0)
        ang = math.radians(random.uniform(15, 40))
        if random.random() < 0.5:
            self.x, self.y = random.uniform(-0.1, 0.5) * w, -20.0
        else:
            self.x, self.y = -20.0, random.uniform(0.0, 0.45) * h
        self.vx = math.cos(ang) * speed
        self.vy = math.sin(ang) * speed
        self.color = QColor(random.choice(DISK_PALETTE))
        self.trail = []

    def step(self):
        self.x += self.vx
        self.y += self.vy
        self.trail.append((self.x, self.y))
        if len(self.trail) > 14:
            self.trail.pop(0)


class CosmosPanel(QWidget):
    """Animated cosmos canvas. Reads presence + active model from StateBus."""

    # The real models AURA routes to. Names MUST match core/model_router.MODELS
    # and the lock keys, so locking a planet actually parks that model.
    PLANETS = [
        # name                role                color                  rx     ry     speed  phase
        ("Laguna M.1",       "Coding",           theme.ACCRETION_BLUE,  0.38, 0.30, 0.30, 200),
        ("Nemotron 3 Super", "Research",         theme.FOCUS_GREEN,     0.44, 0.34, 0.22, 330),
        ("Gemma 4 31B",      "Everyday chat",    theme.EVENT_VIOLET,    0.42, 0.33, 0.26, 140),
        ("Llama 3.3 70B",    "Fallback · heavy", theme.ALERT_ORANGE,    0.33, 0.26, 0.36, 80),
        ("Llama 3.1 8B",     "Fast · light",     theme.ION_CYAN,        0.46, 0.36, 0.19, 30),
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

        # cinematic layers: nebula blobs + hero stars (built in resizeEvent),
        # comets and infalling sparks (spawned on countdowns in _tick)
        self._nebula = []
        self._hero_stars = []
        self._comets = []
        self._comet_timer = 180
        self._sparks = []
        self._spark_timer = 90

        # Apply persisted lock state — locked planets start already parked at
        # the edge (no fly-out animation on launch).
        try:
            from core.model_lock import is_locked
            for p in self._planets:
                p.locked = is_locked(p.name)
                p.rx, p.ry = p.target()
        except Exception:
            pass

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
        working_name = self._working_model()
        for p in self._planets:
            # Locked planets idle slower; the model currently doing the task
            # spins noticeably faster so the eye is drawn to it. All planets
            # ease their orbit radius toward the lock target for smooth drift.
            boost = 2.6 if p.name == working_name else 1.0
            p.angle = (p.angle + p.speed * (0.4 if p.locked else 1.0) * boost) % 360
            trx, try_ = p.target()
            p.rx += (trx - p.rx) * 0.06
            p.ry += (try_ - p.ry) * 0.06

        # comets: spawn on a countdown — never in FOCUS (minimal energy)
        self._comet_timer -= 1
        if (self._comet_timer <= 0 and state != AuraState.FOCUS
                and len(self._comets) < 2 and self.width() > 0):
            self._comets.append(_Comet(self.width(), self.height()))
            self._comet_timer = random.randint(120, 270)
        for c in self._comets:
            c.step()
        self._comets = [c for c in self._comets
                        if c.x < self.width() + 60 and c.y < self.height() + 60]

        # infalling sparks — matter spiraling into the horizon
        self._spark_timer -= 1
        if (self._spark_timer <= 0 and state != AuraState.FOCUS
                and len(self._sparks) < 3):
            self._sparks.append([
                random.uniform(0, 360),
                random.uniform(0.30, 0.36),
                random.choice((-1.0, 1.0)) * random.uniform(0.8, 1.4),
                random.choice(DISK_PALETTE),
            ])
            self._spark_timer = random.randint(60, 140)
        for s in self._sparks:
            s[0] = (s[0] + s[2] * (2.0 + 0.25 / max(s[1], 0.05))) % 360
            s[1] *= 0.9955
        self._sparks = [s for s in self._sparks if s[1] > 0.125]

        self.update()

    # ── active/working model ───────────────────────────────────────────────
    def _working_model(self):
        """Name of the planet AURA is actively using right now (a task is in
        flight), or None. Drives the speed boost + energy stream. Gated on the
        thinking/speaking state so it only fires during real work."""
        if self._bus.state in (AuraState.THINKING, AuraState.SPEAKING):
            return self._bus.active_model
        return None

    def set_locked(self, name: str, locked: bool):
        """Toggle a model's parked/edge state. Called by the ModelDock."""
        for p in self._planets:
            if p.name == name:
                p.locked = locked
        self.update()

    def resizeEvent(self, event):
        # regenerate the starfield to fill the new size
        rng = random.Random(42)  # stable field — stars don't jump on resize
        self._stars = [
            (rng.uniform(0, 1), rng.uniform(0, 1),
             rng.uniform(0.4, 1.4), rng.uniform(0, math.tau))
            for _ in range(140)
        ]
        # hero stars — bigger, with diffraction-cross sparkle
        self._hero_stars = [
            (rng.uniform(0.04, 0.96), rng.uniform(0.05, 0.95),
             rng.uniform(1.6, 3.0), rng.uniform(0, math.tau),
             rng.uniform(0.5, 1.3))
            for _ in range(14)
        ]
        # nebula blobs — (fx, fy, radius fraction, color, drift phase)
        self._nebula = [
            (0.50, 0.46, 0.60, "#3D1E7A", rng.uniform(0, math.tau)),
            (0.32, 0.34, 0.38, "#8B3DFF", rng.uniform(0, math.tau)),
            (0.66, 0.62, 0.36, "#FF4FD8", rng.uniform(0, math.tau)),
            (0.82, 0.22, 0.30, "#28418C", rng.uniform(0, math.tau)),
        ]
        super().resizeEvent(event)

    # ── painting ─────────────────────────────────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2 - 10
        base = min(w, h)

        self._paint_nebula(painter, w, h)
        self._paint_stars(painter, w, h)
        self._paint_hero_stars(painter, w, h)
        self._paint_comets(painter)

        # split planets into behind/in-front of the core for cheap depth
        back, front = [], []
        for p in self._planets:
            (back if math.sin(math.radians(p.angle)) < 0 else front).append(p)

        for p in back:
            self._paint_planet(painter, p, cx, cy, base)
        self._paint_core(painter, cx, cy, base)
        for p in front:
            self._paint_planet(painter, p, cx, cy, base)

        # Energy stream from the model doing the task → core, painted last so
        # the beam reads on top of the accretion disk.
        working_name = self._working_model()
        if working_name:
            for p in self._planets:
                if p.name == working_name:
                    self._paint_energy_stream(painter, p, cx, cy, base)

        self._paint_captions(painter, cx, cy, base)
        painter.end()

    def _planet_pos(self, p, cx, cy, base):
        rad = math.radians(p.angle)
        x = cx + p.rx * base * math.cos(rad)
        y = cy + p.ry * base * math.sin(rad) * 0.9
        depth = 0.75 + 0.25 * math.sin(rad)   # smaller when "behind"
        r = base * 0.032 * depth
        return x, y, r

    def _paint_energy_stream(self, painter, p, cx, cy, base):
        """A glowing beam of flowing particles from the active planet into the
        core — the 'this model is working' indicator."""
        x, y, _ = self._planet_pos(p, cx, cy, base)
        color = QColor(p.color)

        # soft continuous beam underneath
        line = QColor(color); line.setAlphaF(0.22)
        pen = QPen(line, max(1.5, base * 0.006))
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(QPointF(x, y), QPointF(cx, cy))

        # particles flowing inward (t: 0 at planet → 1 at core), animated by time
        painter.setPen(Qt.NoPen)
        n = 16
        flow = (self._rotation * 0.02)
        for i in range(n):
            t = ((i / n) + flow) % 1.0
            px = x + (cx - x) * t
            py = y + (cy - y) * t
            fade = 1.0 - t                      # brighter near the planet
            c = QColor(color); c.setAlphaF(max(0.0, 0.85 * fade))
            size = (0.6 + 2.4 * fade) * (base / 500.0) + 0.8
            painter.setBrush(QBrush(c))
            painter.drawEllipse(QPointF(px, py), size, size)

    def _paint_stars(self, painter, w, h):
        for fx, fy, size, phase in self._stars:
            twinkle = 0.4 + 0.6 * abs(math.sin(self._pulse * 0.7 + phase))
            c = QColor(theme.STARLIGHT_WHITE)
            c.setAlphaF(0.10 + 0.22 * twinkle)
            painter.setBrush(QBrush(c))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(fx * w, fy * h), size, size)

    def _scene_tint(self):
        """(accent, tint strength) for the current state — idle keeps the
        full reference palette, other states pull colors toward the accent."""
        state = self._bus.state
        accent = QColor(state_accent(state))
        return accent, (0.0 if state == AuraState.IDLE else 0.55)

    def _paint_nebula(self, painter, w, h):
        accent, tint = self._scene_tint()
        painter.setPen(Qt.NoPen)
        for fx, fy, rf, hex_str, phase in self._nebula:
            drift = math.sin(self._pulse * 0.15 + phase)
            x = (fx + 0.015 * drift) * w
            y = (fy + 0.012 * math.cos(self._pulse * 0.12 + phase)) * h
            radius = rf * min(w, h) * (1.0 + 0.06 * drift)
            c = _mix(QColor(hex_str), accent, tint)
            g = QRadialGradient(x, y, radius)
            c1 = QColor(c); c1.setAlphaF(0.13)
            c2 = QColor(c); c2.setAlphaF(0.0)
            g.setColorAt(0.0, c1)
            g.setColorAt(1.0, c2)
            painter.setBrush(QBrush(g))
            painter.drawEllipse(QPointF(x, y), radius, radius)

    def _paint_hero_stars(self, painter, w, h):
        focus = self._bus.state == AuraState.FOCUS
        for fx, fy, size, phase, fspeed in self._hero_stars:
            tw = 0.5 + 0.5 * math.sin(self._pulse * fspeed + phase)
            # rare bright flare: the sine only clears the threshold briefly
            flare = 0.0 if focus else max(
                0.0, math.sin(self._pulse * 0.23 + phase * 3.7) - 0.965) * 18
            s = size * (1.0 + 0.5 * tw + flare)
            x, y = fx * w, fy * h
            c = QColor(theme.STARLIGHT_WHITE)
            c.setAlphaF(min(1.0, 0.30 + 0.45 * tw + flare * 0.4))
            painter.setPen(QPen(c, 1.0))
            painter.drawLine(QPointF(x - s * 2.2, y), QPointF(x + s * 2.2, y))
            painter.drawLine(QPointF(x, y - s * 2.2), QPointF(x, y + s * 2.2))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(c))
            painter.drawEllipse(QPointF(x, y), s * 0.55, s * 0.55)

    def _paint_comets(self, painter):
        for c in self._comets:
            n = len(c.trail)
            for i in range(1, n):
                x1, y1 = c.trail[i - 1]
                x2, y2 = c.trail[i]
                t = i / n
                col = QColor(c.color)
                col.setAlphaF(0.05 + 0.45 * t * t)
                pen = QPen(col, 1.0 + 2.2 * t)
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            if c.trail:
                hx, hy = c.trail[-1]
                g = QRadialGradient(hx, hy, 6)
                g.setColorAt(0.0, QColor(255, 255, 255, 240))
                g.setColorAt(1.0, QColor(255, 255, 255, 0))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(g))
                painter.drawEllipse(QPointF(hx, hy), 6, 6)

    def _paint_core(self, painter, cx, cy, base):
        state = self._bus.state
        accent = QColor(state_accent(state))
        core_r = base * 0.115 * (1.0 + 0.04 * math.sin(self._pulse))

        # Non-idle states pull the disk's colors toward the state accent so
        # the black hole still *is* the emotion indicator; idle keeps the
        # full violet/magenta/orange reference look.
        tint = 0.0 if state == AuraState.IDLE else 0.55

        def disk_color(hex_str, alpha):
            c = _mix(QColor(hex_str), accent, tint)
            c.setAlphaF(alpha)
            return c

        # 1. wide violet bloom with an inner magenta warmth
        for hex_str, radius, alpha in (
            ("#8B3DFF", core_r * 4.0, 0.22),
            ("#FF4FD8", core_r * 2.2, 0.16),
        ):
            g = QRadialGradient(cx, cy, radius)
            g.setColorAt(0.15, disk_color(hex_str, alpha))
            g.setColorAt(1.0, disk_color(hex_str, 0.0))
            painter.setBrush(QBrush(g))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # 2. multicolor dust sparks swirling in the disk plane
        painter.setPen(Qt.NoPen)
        for d in self._dust:
            rad = math.radians(d.angle)
            r = d.radius * base
            x = cx + r * math.cos(rad)
            y = cy + r * 0.5 * math.sin(rad)
            c = _mix(d.color, accent, tint)
            c.setAlphaF(d.alpha * (0.45 + 0.35 * abs(math.sin(self._pulse + rad))))
            painter.setBrush(QBrush(c))
            painter.drawEllipse(QPointF(x, y), d.size, d.size)

        # 3. spiral arms — the swirling accretion disk. Drawn in a tilted,
        #    squashed plane; each arm is a log-spiral polyline whose
        #    segments fade and thin as they wind outward.
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-8)
        painter.scale(1.0, 0.55)
        arm_colors = ("#FF8A3D", "#FF4FD8", "#C44FFF", "#5B7FFF")
        n_arms = len(arm_colors)
        samples = 40
        max_theta = math.radians(340)
        k = 0.24
        for a_i, hex_str in enumerate(arm_colors):
            offset = (360.0 / n_arms) * a_i + self._rotation
            pts = []
            for s in range(samples + 1):
                t = s / samples
                theta = t * max_theta
                r = core_r * 1.12 * math.exp(k * theta)
                ang = math.radians(offset) + theta
                pts.append((r * math.cos(ang), r * math.sin(ang), t))
            for i in range(samples):
                x1, y1, t1 = pts[i]
                x2, y2, _ = pts[i + 1]
                fade = 1.0 - t1
                c = disk_color(hex_str, 0.08 + 0.70 * fade * fade)
                pen = QPen(c, core_r * (0.05 + 0.22 * fade))
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # 4. hot inner band hugging the horizon — conical gradient so one
        #    side flares brighter (doppler-boosted edge, like the reference)
        cone = QConicalGradient(0, 0, self._rotation * 1.6)
        cone.setColorAt(0.00, disk_color("#FFE7C4", 0.95))
        cone.setColorAt(0.18, disk_color("#FF8A3D", 0.80))
        cone.setColorAt(0.45, disk_color("#FF4FD8", 0.55))
        cone.setColorAt(0.72, disk_color("#8B3DFF", 0.65))
        cone.setColorAt(1.00, disk_color("#FFE7C4", 0.95))
        pen = QPen(QBrush(cone), core_r * 0.55)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(0, 0), core_r * 1.45, core_r * 1.45)
        painter.restore()

        # 4b. lensing filaments — thin arcs of bent light circling the hole
        #     at different radii/speeds, like wisps caught in the gravity well
        painter.setBrush(Qt.NoBrush)
        for rf, speed_mult, span, alpha_k, hex_str in (
            (1.75,  80.0, 210.0, 0.9, "#FFE7C4"),
            (2.05, -55.0, 150.0, 0.7, "#FF4FD8"),
            (2.35,  30.0, 120.0, 0.5, "#5B7FFF"),
        ):
            start = (self._rotation * speed_mult / 60.0) % 360
            pen = QPen(disk_color(hex_str, 0.30 * alpha_k),
                       max(1.0, core_r * 0.035))
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            rect = QRectF(cx - core_r * rf, cy - core_r * rf * 0.88,
                          core_r * rf * 2, core_r * rf * 0.88 * 2)
            painter.drawArc(rect, int(start * 16), int(span * 16))

        # 4c. infalling sparks — matter spiraling in until the horizon
        #     swallows it (AURA absorbing information)
        painter.setPen(Qt.NoPen)
        for ang, rf, _spin, col in self._sparks:
            rad = math.radians(ang)
            x = cx + rf * base * math.cos(rad)
            y = cy + rf * base * 0.5 * math.sin(rad)
            t = max(0.0, min(1.0, (rf - 0.125) / 0.24))  # 0 at horizon
            c = disk_color(col, 0.35 + 0.6 * (1.0 - t))
            painter.setBrush(QBrush(c))
            sz = 1.2 + 2.2 * (1.0 - t)
            painter.drawEllipse(QPointF(x, y), sz, sz)

        # 5. photon rim — thin, hot, unsquashed circle at the horizon
        rim = disk_color("#FFF2E0",
                         0.55 + 0.25 * abs(math.sin(self._pulse * 1.3)))
        pen = QPen(rim, max(1.2, core_r * 0.05))
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), core_r * 1.06, core_r * 1.06)

        # 6. the event horizon — pure black, swallowing everything behind it
        hole = QRadialGradient(cx, cy, core_r * 1.04)
        hole.setColorAt(0.0, QColor(0, 0, 0))
        hole.setColorAt(0.90, QColor(0, 0, 0))
        hole.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(hole))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), core_r * 1.04, core_r * 1.04)

    def _paint_planet(self, painter, p: _Planet, cx, cy, base):
        x, y, r = self._planet_pos(p, cx, cy, base)

        # A locked model is parked at the edge and not in play — render it
        # muted so the eye reads it as "idle out there", never as active.
        is_active = (not p.locked) and p.name == self._bus.active_model
        dim = 0.4 if p.locked else 1.0

        # faint orbit path
        pen = QPen(QColor(255, 255, 255, 8 if p.locked else 14))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), p.rx * base, p.ry * base * 0.9)

        # glow
        glow = QRadialGradient(x, y, r * 3.0)
        gc = QColor(p.color)
        gc.setAlphaF((0.45 if is_active else 0.18) * dim)
        ge = QColor(p.color); ge.setAlphaF(0.0)
        glow.setColorAt(0.0, gc)
        glow.setColorAt(1.0, ge)
        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(x, y), r * 3.0, r * 3.0)

        # body
        body = QRadialGradient(x - r * 0.35, y - r * 0.35, r * 1.7)
        lit = QColor(p.color).lighter(130 if not p.locked else 100)
        dark = QColor(p.color).darker(320 if not p.locked else 460)
        body.setColorAt(0.0, lit)
        body.setColorAt(1.0, dark)
        painter.setBrush(QBrush(body))
        painter.drawEllipse(QPointF(x, y), r, r)

        # label
        painter.setPen(QColor(theme.TEXT_SECONDARY if p.locked else theme.TEXT_PRIMARY))
        painter.setFont(theme.display_font(9))
        painter.drawText(QRectF(x - 70, y + r + 4, 140, 14),
                         Qt.AlignHCenter, p.name)
        painter.setPen(QColor(theme.TEXT_DIM))
        painter.setFont(theme.body_font(8))
        painter.drawText(QRectF(x - 70, y + r + 18, 140, 12),
                         Qt.AlignHCenter, p.role)

        if p.locked:
            chip, chip_color = "🔒 LOCKED", QColor(theme.TEXT_DIM)
        elif is_active:
            chip, chip_color = "ACTIVE", QColor(p.color)
        else:
            chip, chip_color = "STANDBY", QColor(theme.TEXT_DIM)
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
