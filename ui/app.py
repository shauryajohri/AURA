#!/usr/bin/env python3
"""
AURA Desktop UI — matches the mockup design
3-panel layout: Chat | Orb | Tasks
"""

import sys
import math
import time
import random
import threading
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QFrame, QProgressBar,
    QGraphicsDropShadowEffect, QSizePolicy, QCheckBox
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QPropertyAnimation,
    QEasingCurve, QRect, QPoint, QSize, pyqtProperty
)
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QFontDatabase, QPen, QBrush,
    QLinearGradient, QRadialGradient, QConicalGradient,
    QPainterPath, QPixmap, QPalette
)

# ── Color palette ─────────────────────────────────────────────────────────────
BG_DEEP      = "#07090F"
BG_PANEL     = "#0D1120"
BG_CARD      = "#111827"
BG_INPUT     = "#1A2035"
BORDER       = "#1E2D4A"
CYAN         = "#00C8FF"
PURPLE       = "#8B5CF6"
CYAN_DIM     = "#0090BB"
WHITE        = "#F0F4FF"
MUTED        = "#5A6A85"
GREEN        = "#22C55E"
AURA_BLUE    = "#3B82F6"
ORB_GLOW1    = "#00C8FF"
ORB_GLOW2    = "#7C3AED"
ORB_INNER    = "#1A0A3A"

# ── Animated Orb ──────────────────────────────────────────────────────────────
class OrbWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(340, 340)
        self._phase     = 0.0
        self._wave_phase= 0.0
        self._pulse     = 0.0
        self._state     = "idle"   # idle | listening | thinking | speaking

        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)  # ~60fps

    def set_state(self, state: str):
        self._state = state
        self.update()

    def _tick(self):
        self._phase      += 0.018
        self._wave_phase += 0.035
        self._pulse = 0.5 + 0.5 * math.sin(self._phase * 2)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy, r = 170, 170, 120

        # ── outer glow rings ──────────────────────────────────────────────────
        for i, (radius, alpha) in enumerate([(148, 18), (132, 28), (118, 40)]):
            ring_color = QColor(ORB_GLOW1)
            if self._state == "listening":
                ring_color = QColor(CYAN)
                alpha = int(alpha * (0.7 + 0.3 * self._pulse))
                radius = int(radius * (1 + 0.04 * self._pulse))
            elif self._state == "thinking":
                ring_color = QColor(PURPLE)
                alpha = int(alpha * 0.8)
            elif self._state == "speaking":
                ring_color = QColor(ORB_GLOW2)
                alpha = int(alpha * (0.6 + 0.4 * self._pulse))

            ring_color.setAlpha(alpha)
            pen = QPen(ring_color, 1.5)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(int(cx - radius), int(cy - radius),
                          int(radius * 2), int(radius * 2))

        # ── main orb body ─────────────────────────────────────────────────────
        grad = QRadialGradient(cx, cy - 20, r)
        grad.setColorAt(0.0,  QColor("#2A1060"))
        grad.setColorAt(0.4,  QColor("#150830"))
        grad.setColorAt(0.85, QColor("#0A0520"))
        grad.setColorAt(1.0,  QColor("#050210"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))

        # ── wave lines (the squiggly lines in the orb) ────────────────────────
        wave_color = QColor(CYAN)
        wave_color.setAlpha(180)
        pen = QPen(wave_color, 2.5, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)

        num_waves = 3
        for w in range(num_waves):
            path = QPainterPath()
            offset_y = cy - 15 + w * 15
            amp = 14 + w * 5
            if self._state == "speaking":
                amp *= (1 + 0.6 * self._pulse)
            elif self._state == "listening":
                amp *= (1 + 0.3 * self._pulse)
            elif self._state == "idle":
                amp *= 0.6

            phase_offset = w * 1.1
            steps = 60
            first = True
            for i in range(steps + 1):
                t   = i / steps
                x   = cx - 70 + t * 140
                y_  = offset_y + amp * math.sin(
                    self._wave_phase * 2.2 + t * math.pi * 3 + phase_offset
                )
                # clip to circle
                dx, dy = x - cx, y_ - cy
                if dx * dx + dy * dy > (r - 12) ** 2:
                    first = True
                    continue
                if first:
                    path.moveTo(x, y_)
                    first = False
                else:
                    path.lineTo(x, y_)

            alpha_wave = 200 - w * 40
            wave_c = QColor(ORB_GLOW1 if w == 0 else ORB_GLOW2)
            wave_c.setAlpha(alpha_wave)
            pen.setColor(wave_c)
            p.setPen(pen)
            p.drawPath(path)

        # ── glint highlight ───────────────────────────────────────────────────
        glint = QRadialGradient(cx - 30, cy - 45, 35)
        glint.setColorAt(0.0, QColor(255, 255, 255, 35))
        glint.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(glint))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(int(cx - 65), int(cy - 80), 70, 60)

        p.end()


# ── Message Bubble ────────────────────────────────────────────────────────────
class Bubble(QFrame):
    def __init__(self, sender: str, text: str, timestamp: str, is_user: bool):
        super().__init__()
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(3)

        # sender + time
        meta_row = QHBoxLayout()
        sender_lbl = QLabel(sender)
        sender_lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        sender_lbl.setStyleSheet(f"color: {'#8B9DBB' if is_user else CYAN};")
        time_lbl = QLabel(timestamp)
        time_lbl.setFont(QFont("Segoe UI", 8))
        time_lbl.setStyleSheet(f"color: {MUTED};")
        meta_row.addWidget(sender_lbl)
        meta_row.addSpacing(8)
        meta_row.addWidget(time_lbl)
        meta_row.addStretch()
        layout.addLayout(meta_row)

        # bubble
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setFont(QFont("Segoe UI", 11))
        bubble.setMaximumWidth(320)
        bubble.setStyleSheet(f"""
            QLabel {{
                background: {'#1E3A5F' if is_user else '#111827'};
                color: {WHITE};
                border-radius: 12px;
                padding: 10px 14px;
                border: 1px solid {'#2A4A70' if is_user else BORDER};
            }}
        """)

        row = QHBoxLayout()
        if is_user:
            row.addStretch()
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch()
        layout.addLayout(row)


# ── Code Bubble ───────────────────────────────────────────────────────────────
class CodeBubble(QFrame):
    def __init__(self, label: str, code: str):
        super().__init__()
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)

        lbl = QLabel(label)
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {CYAN};")
        layout.addWidget(lbl)

        code_frame = QFrame()
        code_frame.setStyleSheet(f"""
            QFrame {{
                background: #0D1A2E;
                border-radius: 10px;
                border: 1px solid {BORDER};
            }}
        """)
        cf_layout = QVBoxLayout(code_frame)
        cf_layout.setContentsMargins(14, 10, 14, 10)

        # header bar
        header = QHBoxLayout()
        for color in ["#FF5F57", "#FFBD2E", "#28C840"]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color}; font-size: 10px;")
            header.addWidget(dot)
        header.addStretch()
        copy_btn = QPushButton("⎘")
        copy_btn.setFixedSize(24, 24)
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_INPUT}; color: {MUTED};
                border-radius: 4px; border: none; font-size: 12px;
            }}
            QPushButton:hover {{ color: {WHITE}; }}
        """)
        header.addWidget(copy_btn)
        cf_layout.addLayout(header)

        code_lbl = QLabel(code)
        code_lbl.setFont(QFont("Consolas", 10))
        code_lbl.setStyleSheet(f"color: #C9D1D9; background: transparent;")
        code_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        cf_layout.addWidget(code_lbl)
        layout.addWidget(code_frame)


# ── Action Button Bubble ──────────────────────────────────────────────────────
class ActionBubble(QFrame):
    def __init__(self, text: str, buttons: list):
        super().__init__()
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(6)

        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setFont(QFont("Segoe UI", 11))
        lbl.setStyleSheet(f"""
            color: {WHITE};
            background: #111827;
            border-radius: 10px;
            padding: 10px 14px;
            border: 1px solid {BORDER};
        """)
        layout.addWidget(lbl)

        btn_row = QHBoxLayout()
        for label, primary in buttons:
            btn = QPushButton(label)
            btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            btn.setFixedHeight(32)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {'#3B82F6' if primary else BG_INPUT};
                    color: {WHITE};
                    border-radius: 8px;
                    border: {'none' if primary else f'1px solid {BORDER}'};
                    padding: 0 16px;
                }}
                QPushButton:hover {{
                    background: {'#2563EB' if primary else '#1E2D45'};
                }}
            """)
            btn_row.addWidget(btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)


# ── Task Item ─────────────────────────────────────────────────────────────────
class TaskItem(QFrame):
    def __init__(self, title: str, subtitle: str, status: str, time_str: str = ""):
        super().__init__()
        self.setStyleSheet(f"""
            QFrame {{
                background: {BG_CARD};
                border-radius: 10px;
                border: 1px solid {BORDER};
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        # status indicator
        if status == "done":
            icon = QLabel("✓")
            icon.setFixedSize(22, 22)
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon.setStyleSheet(f"""
                background: {GREEN}; color: white;
                border-radius: 11px; font-size: 11px; font-weight: bold;
            """)
        elif status == "active":
            icon = QLabel("")
            icon.setFixedSize(22, 22)
            icon.setStyleSheet(f"""
                border-radius: 11px;
                border: 2px solid {AURA_BLUE};
                background: {BG_INPUT};
            """)
            # inner dot
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {AURA_BLUE}; font-size: 8px;")
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_layout = QVBoxLayout(icon)
            icon_layout.setContentsMargins(0, 0, 0, 0)
            icon_layout.addWidget(dot)
        else:
            icon = QLabel("")
            icon.setFixedSize(22, 22)
            icon.setStyleSheet(f"""
                border-radius: 11px;
                border: 2px solid {BORDER};
                background: transparent;
            """)

        layout.addWidget(icon)

        # text
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
        color = f"color: {WHITE};" if status != "pending" else f"color: {MUTED};"
        title_lbl.setStyleSheet(color + " background: transparent;")
        sub_lbl = QLabel(subtitle + (f" • {time_str}" if time_str else ""))
        sub_lbl.setFont(QFont("Segoe UI", 9))
        sub_lbl.setStyleSheet(f"color: {MUTED}; background: transparent;")
        text_col.addWidget(title_lbl)
        text_col.addWidget(sub_lbl)
        layout.addLayout(text_col)
        layout.addStretch()

        # right widget
        if status == "active":
            play = QPushButton("▶")
            play.setFixedSize(32, 32)
            play.setStyleSheet(f"""
                QPushButton {{
                    background: {AURA_BLUE}; color: white;
                    border-radius: 16px; border: none; font-size: 11px;
                }}
                QPushButton:hover {{ background: #2563EB; }}
            """)
            layout.addWidget(play)
        elif status == "pending":
            clock = QLabel("⏱")
            clock.setStyleSheet(f"color: {MUTED}; font-size: 14px; background: transparent;")
            layout.addWidget(clock)


# ── Quick Action Button ───────────────────────────────────────────────────────
class QuickAction(QPushButton):
    def __init__(self, icon: str, label: str):
        super().__init__()
        self.setFixedSize(90, 80)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 10)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel(icon)
        icon_lbl.setFont(QFont("Segoe UI", 18))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("color: white; background: transparent;")

        text_lbl = QLabel(label)
        text_lbl.setFont(QFont("Segoe UI", 9))
        text_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_lbl.setStyleSheet(f"color: {MUTED}; background: transparent;")

        layout.addWidget(icon_lbl)
        layout.addWidget(text_lbl)

        self.setStyleSheet(f"""
            QPushButton {{
                background: {BG_CARD};
                border-radius: 14px;
                border: 1px solid {BORDER};
            }}
            QPushButton:hover {{
                background: {BG_INPUT};
                border: 1px solid {CYAN_DIM};
            }}
        """)
        actions = [
    ("🔍", "Search",   "search the web for "),
    ("🔔", "Remind",   "remind me to "),
    ("⚡", "Automate", "automate "),
    ("📊", "Analyze",  "analyze "),
]
for icon, label, prefix in actions:
    btn = QuickAction(icon, label)
    btn.clicked.connect(lambda checked, p=prefix: self.text_input.setText(p))
    actions_row.addWidget(btn)


# ── Thinking Indicator ────────────────────────────────────────────────────────
class ThinkingDots(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(30)
        self._dots = 0
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(400)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._lbl = QLabel("● ● ●   AURA is thinking...")
        self._lbl.setFont(QFont("Segoe UI", 10))
        self._lbl.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(self._lbl)
        layout.addStretch()

    def _tick(self):
        self._dots = (self._dots + 1) % 4
        dots = "● " * self._dots + "○ " * (3 - self._dots)
        self._lbl.setText(f"{dots.strip()}   AURA is thinking...")


# ── Main Window ───────────────────────────────────────────────────────────────
class AuraMainWindow(QMainWindow):
    add_message_signal = pyqtSignal(str, str, bool)  # sender, text, is_user
    set_thinking_signal = pyqtSignal(bool)
    set_orb_state_signal = pyqtSignal(str)

    def __init__(self, brain_process=None, speak_fn=None):
        super().__init__()
        self.brain_process = brain_process
        self.speak_fn      = speak_fn
        self.add_message_signal.connect(self._add_message)
        self.set_thinking_signal.connect(self._set_thinking)
        self.set_orb_state_signal.connect(self._set_orb_state)
        self._thinking_widget = None
        self._setup_window()
        self._build_ui()
        self._load_sample_data()
        self._setup_voice()

    def _setup_window(self):
        self.setWindowTitle("AURA — Your AI Companion")
        self.setMinimumSize(1200, 760)
        self.setStyleSheet(f"background-color: {BG_DEEP};")

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Top bar ───────────────────────────────────────────────────────────
        topbar = self._build_topbar()
        root_layout.addWidget(topbar)

        # ── Main 3-column area ────────────────────────────────────────────────
        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(0)

        left  = self._build_left_panel()
        center= self._build_center_panel()
        right = self._build_right_panel()

        columns.addWidget(left,   3)
        columns.addWidget(center, 4)
        columns.addWidget(right,  3)

        main_widget = QWidget()
        main_widget.setLayout(columns)
        root_layout.addWidget(main_widget, 1)

        # ── Bottom input bar ──────────────────────────────────────────────────
        bottom = self._build_bottom_bar()
        root_layout.addWidget(bottom)

    # ── Top bar ───────────────────────────────────────────────────────────────
    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(56)
        bar.setStyleSheet(f"""
            background: {BG_PANEL};
            border-bottom: 1px solid {BORDER};
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 20, 0)

        # logo
        logo_row = QHBoxLayout()
        logo_icon = QLabel("✦")
        logo_icon.setFont(QFont("Segoe UI", 16))
        logo_icon.setStyleSheet(f"color: {CYAN};")
        logo_text = QLabel("AURA")
        logo_text.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        logo_text.setStyleSheet(f"color: {WHITE};")
        sub_text = QLabel("Your AI Companion")
        sub_text.setFont(QFont("Segoe UI", 10))
        sub_text.setStyleSheet(f"color: {MUTED};")
        logo_row.addWidget(logo_icon)
        logo_row.addSpacing(6)
        logo_row.addWidget(logo_text)
        logo_row.addSpacing(10)
        logo_row.addWidget(sub_text)
        layout.addLayout(logo_row)
        layout.addStretch()

        # mic status pill
        self.mic_pill = QPushButton("🎙  Mic is ON")
        self.mic_pill.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.mic_pill.setFixedHeight(36)
        self.mic_pill.setStyleSheet(f"""
            QPushButton {{
                background: #1A2A3A;
                color: {WHITE};
                border-radius: 18px;
                border: 1px solid {CYAN_DIM};
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background: #1E3048;
            }}
        """)
        self.mic_pill.clicked.connect(self._toggle_mic)
        layout.addWidget(self.mic_pill)
        layout.addSpacing(8)

        # wave indicator (static visual)
        wave_lbl = QLabel("▮▯▮▮▯▮")
        wave_lbl.setFont(QFont("Segoe UI", 12))
        wave_lbl.setStyleSheet(f"color: {CYAN};")
        layout.addWidget(wave_lbl)
        layout.addSpacing(16)

        # right icons
        return bar

    # ── Left panel (Chat) ─────────────────────────────────────────────────────
    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"""
            background: {BG_PANEL};
            border-right: 1px solid {BORDER};
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # chat header
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet(f"background: {BG_PANEL}; border-bottom: 1px solid {BORDER};")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 0, 16, 0)
        star = QLabel("✦")
        star.setStyleSheet(f"color: {CYAN};")
        title = QLabel("AURA Chat")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {WHITE};")
        h_layout.addWidget(star)
        h_layout.addSpacing(6)
        h_layout.addWidget(title)
        h_layout.addStretch()
        menu_btn = QPushButton("≡")
        menu_btn.setFixedSize(28, 28)
        menu_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {MUTED};
            border: none; font-size: 16px; }}
        """)
        h_layout.addWidget(menu_btn)
        layout.addWidget(header)

        # scroll area
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet(f"""
            QScrollArea {{ background: {BG_PANEL}; border: none; }}
            QScrollBar:vertical {{
                width: 4px; background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER}; border-radius: 2px;
            }}
        """)
        self.chat_container = QWidget()
        self.chat_container.setStyleSheet(f"background: {BG_PANEL};")
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setContentsMargins(14, 12, 14, 12)
        self.chat_layout.setSpacing(4)
        self.chat_layout.addStretch()
        self.chat_scroll.setWidget(self.chat_container)
        layout.addWidget(self.chat_scroll)

        return panel

    # ── Center panel (Orb) ────────────────────────────────────────────────────
    def _build_center_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: {BG_DEEP};")
        layout = QVBoxLayout(panel)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(0)
        layout.setContentsMargins(20, 20, 20, 20)

        # AURA title
        title = QLabel("AURA")
        title.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"""
            background: transparent;
            qproperty-alignment: AlignCenter;
        """)
        # gradient text via stylesheet hack
        title.setStyleSheet(f"color: {CYAN}; background: transparent; letter-spacing: 4px;")
        layout.addWidget(title)
        layout.addSpacing(4)

        # orb
        self.orb = OrbWidget()
        layout.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(8)

        # status label
        self.orb_status = QLabel("Listening...")
        self.orb_status.setFont(QFont("Segoe UI", 13))
        self.orb_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.orb_status.setStyleSheet(f"color: {MUTED}; background: transparent;")
        layout.addWidget(self.orb_status)
        layout.addSpacing(20)

        # focus mode indicator
        focus_row = QHBoxLayout()
        focus_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        focus_icon = QLabel("⊙")
        focus_icon.setStyleSheet(f"color: {CYAN}; font-size: 13px; background: transparent;")
        focus_text = QLabel("Focus Mode Active")
        focus_text.setFont(QFont("Segoe UI", 10))
        focus_text.setStyleSheet(f"color: {MUTED}; background: transparent;")
        focus_dot = QLabel("●")
        focus_dot.setStyleSheet(f"color: {GREEN}; font-size: 8px; background: transparent;")
        focus_row.addWidget(focus_icon)
        focus_row.addSpacing(4)
        focus_row.addWidget(focus_text)
        focus_row.addSpacing(6)
        focus_row.addWidget(focus_dot)
        layout.addLayout(focus_row)
        layout.addSpacing(20)

        # quick action buttons
        actions_row = QHBoxLayout()
        actions_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        actions_row.setSpacing(10)
        for icon, label in [("🔍", "Search"), ("🔔", "Remind"), ("⚡", "Automate"), ("📊", "Analyze")]:
            btn = QuickAction(icon, label)
            actions_row.addWidget(btn)
        layout.addLayout(actions_row)

        layout.addStretch()
        return panel

    # ── Right panel (Tasks) ───────────────────────────────────────────────────
    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"""
            background: {BG_PANEL};
            border-left: 1px solid {BORDER};
        """)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 0, 16, 16)
        layout.setSpacing(0)

        # header
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet(f"background: transparent; border-bottom: 1px solid {BORDER};")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)
        cal_icon = QLabel("📅")
        cal_icon.setFont(QFont("Segoe UI", 13))
        tasks_title = QLabel("Today's Tasks")
        tasks_title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        tasks_title.setStyleSheet(f"color: {WHITE};")
        add_btn = QPushButton("+ Add Task")
        add_btn.setFont(QFont("Segoe UI", 9))
        add_btn.setFixedHeight(28)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_INPUT}; color: {CYAN};
                border-radius: 8px; border: 1px solid {CYAN_DIM};
                padding: 0 10px;
            }}
            QPushButton:hover {{ background: #1A2A3A; }}
        """)
        h_layout.addWidget(cal_icon)
        h_layout.addSpacing(6)
        h_layout.addWidget(tasks_title)
        h_layout.addStretch()
        h_layout.addWidget(add_btn)
        layout.addWidget(header)
        layout.addSpacing(12)

        # date + progress
        today_str = datetime.now().strftime("%d %b, %A")
        date_row = QHBoxLayout()
        date_lbl = QLabel(today_str)
        date_lbl.setFont(QFont("Segoe UI", 10))
        date_lbl.setStyleSheet(f"color: {MUTED};")
        progress_lbl = QLabel("4/6 Completed")
        progress_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        progress_lbl.setStyleSheet(f"color: {WHITE};")
        date_row.addWidget(date_lbl)
        date_row.addStretch()
        date_row.addWidget(progress_lbl)
        layout.addLayout(date_row)
        layout.addSpacing(6)

        # progress bar
        prog = QProgressBar()
        prog.setValue(67)
        prog.setFixedHeight(6)
        prog.setTextVisible(False)
        prog.setStyleSheet(f"""
            QProgressBar {{
                background: {BG_INPUT};
                border-radius: 3px;
                border: none;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {AURA_BLUE}, stop:1 {PURPLE});
                border-radius: 3px;
            }}
        """)
        layout.addWidget(prog)
        layout.addSpacing(14)
        # replace the hardcoded tasks list with:
        self.task_layout = QVBoxLayout()
        self.task_layout.setContentsMargins(0, 0, 0, 0)
        self.task_layout.setSpacing(8)
        self.task_layout.addStretch()

        self.task_container = QWidget()
        self.task_container.setStyleSheet("background: transparent;")
        self.task_container.setLayout(self.task_layout)

        task_scroll = QScrollArea()
        task_scroll.setWidgetResizable(True)
        task_scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 2px; }}
        """)
        task_scroll.setWidget(self.task_container)
        layout.addWidget(task_scroll, 1)
        # quote
        layout.addSpacing(10)
        quote = QLabel("❝  Discipline today, success tomorrow.")
        quote.setFont(QFont("Segoe UI", 10))
        quote.setStyleSheet(f"color: {CYAN}; background: transparent;")
        quote.setWordWrap(True)
        layout.addWidget(quote)

        return panel

    # ── Bottom input bar ──────────────────────────────────────────────────────
    def _build_bottom_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(80)
        bar.setStyleSheet(f"""
            background: {BG_PANEL};
            border-top: 1px solid {BORDER};
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(12)

        # keyboard icon
        kbd = QPushButton("⌨")
        kbd.setFixedSize(40, 40)
        kbd.setStyleSheet(f"""
            QPushButton {{
                background: {BG_INPUT}; color: {MUTED};
                border-radius: 10px; border: 1px solid {BORDER}; font-size: 16px;
            }}
            QPushButton:hover {{ color: {WHITE}; }}
        """)
        layout.addWidget(kbd)

        # text input
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Type your message...")
        self.text_input.setFont(QFont("Segoe UI", 12))
        self.text_input.setFixedHeight(48)
        self.text_input.setStyleSheet(f"""
            QLineEdit {{
                background: {BG_INPUT};
                color: {WHITE};
                border-radius: 24px;
                border: 1px solid {BORDER};
                padding: 0 20px;
            }}
            QLineEdit:focus {{
                border: 1px solid {CYAN_DIM};
            }}
        """)
        self.text_input.returnPressed.connect(self._send_text)
        layout.addWidget(self.text_input, 1)

        # send
        send_btn = QPushButton("➤")
        send_btn.setFixedSize(48, 48)
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 {AURA_BLUE}, stop:1 {PURPLE});
                color: white; border-radius: 24px;
                border: none; font-size: 16px;
            }}
            QPushButton:hover {{ opacity: 0.9; }}
        """)
        send_btn.clicked.connect(self._send_text)
        layout.addWidget(send_btn)

        # mic
        self.mic_btn = QPushButton("🎙")
        self.mic_btn.setFixedSize(48, 48)
        self.mic_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_INPUT}; color: {WHITE};
                border-radius: 24px; border: 1px solid {CYAN_DIM};
                font-size: 18px;
            }}
            QPushButton:hover {{ background: #1A2A3A; }}
        """)
        layout.addWidget(self.mic_btn)

        # tip
        tip = QLabel("Tip: You can also use voice commands")
        tip.setFont(QFont("Segoe UI", 9))
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tip.setStyleSheet(f"color: {MUTED};")

        # wrap input + tip in a column
        col_widget = QWidget()
        col_widget.setStyleSheet("background: transparent;")
        col = QVBoxLayout(col_widget)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)

        input_row = QHBoxLayout()
        input_row.addWidget(kbd)
        input_row.addWidget(self.text_input)
        input_row.addWidget(send_btn)
        input_row.addWidget(self.mic_btn)
        col.addLayout(input_row)
        col.addWidget(tip)

        # rebuild bar layout
        for i in reversed(range(layout.count())):
            layout.itemAt(i).widget()
        bar2 = QWidget()
        bar2.setFixedHeight(80)
        bar2.setStyleSheet(f"background: {BG_PANEL}; border-top: 1px solid {BORDER};")
        b_layout = QVBoxLayout(bar2)
        b_layout.setContentsMargins(24, 8, 24, 4)
        b_layout.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(10)

        kbd2 = QPushButton("⌨")
        kbd2.setFixedSize(40, 40)
        kbd2.setStyleSheet(f"""
            QPushButton {{
                background: {BG_INPUT}; color: {MUTED};
                border-radius: 10px; border: 1px solid {BORDER}; font-size: 16px;
            }}
        """)

        ti = QLineEdit()
        ti.setPlaceholderText("Type your message...")
        ti.setFont(QFont("Segoe UI", 12))
        ti.setFixedHeight(44)
        ti.setStyleSheet(f"""
            QLineEdit {{
                background: {BG_INPUT}; color: {WHITE};
                border-radius: 22px; border: 1px solid {BORDER};
                padding: 0 20px;
            }}
            QLineEdit:focus {{ border: 1px solid {CYAN_DIM}; }}
        """)
        self.text_input = ti
        ti.returnPressed.connect(self._send_text)

        sb = QPushButton("➤")
        sb.setFixedSize(44, 44)
        sb.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 {AURA_BLUE}, stop:1 {PURPLE});
                color: white; border-radius: 22px; border: none; font-size: 16px;
            }}
        """)
        sb.clicked.connect(self._send_text)

        mb = QPushButton("🎙")
        mb.setFixedSize(44, 44)
        mb.setStyleSheet(f"""
            QPushButton {{
                background: {BG_INPUT}; color: white;
                border-radius: 22px; border: 1px solid {CYAN_DIM}; font-size: 16px;
            }}
        """)

        row.addWidget(kbd2)
        row.addWidget(ti)
        row.addWidget(sb)
        row.addWidget(mb)
        b_layout.addLayout(row)

        tip2 = QLabel("Tip: You can also use voice commands")
        tip2.setFont(QFont("Segoe UI", 9))
        tip2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tip2.setStyleSheet(f"color: {MUTED};")
        b_layout.addWidget(tip2)

        return bar2

    # ── Load sample chat ──────────────────────────────────────────────────────
    def _load_sample_data(self):
        now = datetime.now().strftime("%I:%M %p")
        self._add_message(
            "AURA",
            f"Good evening, Shaurya! 👋\nHow can I assist you today?",
            False
        )

    # ── Add message ───────────────────────────────────────────────────────────
    def _add_message(self, sender: str, text: str, is_user: bool):
        now = datetime.now().strftime("%I:%M %p")
        # remove thinking widget if exists
        if self._thinking_widget:
            self.chat_layout.removeWidget(self._thinking_widget)
            self._thinking_widget.deleteLater()
            self._thinking_widget = None

        # detect code
        if "def " in text and "return" in text:
            lines = text.strip().split("\n")
            label_line = lines[0] if lines else sender
            code_text  = "\n".join(lines[1:]) if len(lines) > 1 else text
            w = CodeBubble(label_line, code_text)
        else:
            w = Bubble(sender, text, now, is_user)

        # insert before stretch
        count = self.chat_layout.count()
        self.chat_layout.insertWidget(count - 1, w)

        # scroll down
        QTimer.singleShot(100, lambda: self.chat_scroll.verticalScrollBar().setValue(
            self.chat_scroll.verticalScrollBar().maximum()
        ))

    def _set_thinking(self, thinking: bool):
        if thinking and not self._thinking_widget:
            self._thinking_widget = ThinkingDots()
            count = self.chat_layout.count()
            self.chat_layout.insertWidget(count - 1, self._thinking_widget)
            QTimer.singleShot(100, lambda: self.chat_scroll.verticalScrollBar().setValue(
                self.chat_scroll.verticalScrollBar().maximum()
            ))
        elif not thinking and self._thinking_widget:
            self.chat_layout.removeWidget(self._thinking_widget)
            self._thinking_widget.deleteLater()
            self._thinking_widget = None

    def _set_orb_state(self, state: str):
        self.orb.set_state(state)
        labels = {
            "idle":      "Idle",
            "listening": "Listening...",
            "thinking":  "Thinking...",
            "speaking":  "Speaking...",
        }
        self.orb_status.setText(labels.get(state, ""))

    # ── Send text ─────────────────────────────────────────────────────────────
    def _send_text(self):
        text = self.text_input.text().strip()
        if not text:
            return
        self.text_input.clear()
        self._add_message("You", text, True)
        threading.Thread(target=self._process, args=(text,), daemon=True).start()

    def _process(self, text: str):
        self.set_thinking_signal.emit(True)
        self.set_orb_state_signal.emit("thinking")
        try:
            if self.brain_process:
                response = self.brain_process(text)
            else:
                response = f"[Demo] You said: {text}"
        except Exception as e:
            response = f"Error: {e}"
        self.set_thinking_signal.emit(False)
        self.add_message_signal.emit("AURA", response, False)
        self.set_orb_state_signal.emit("speaking")
        if self.speak_fn:
            self.speak_fn(response)
        self.set_orb_state_signal.emit("listening")

    # ── Voice setup ───────────────────────────────────────────────────────────
def _setup_voice(self):
    self.voice_active = True
    self.voice_worker = VoiceWorker()
    self.voice_worker.heard.connect(self._on_voice_input)
    self.voice_worker.start()
    self.set_orb_state_signal.emit("listening")
    
    # connect mic button
    self.mic_btn.clicked.connect(self._toggle_mic)

def _toggle_mic(self):
    self.voice_active = not self.voice_active
    if self.voice_active:
        self.mic_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BG_INPUT}; color: white;
                border-radius: 22px; border: 1px solid {CYAN_DIM}; font-size: 16px;
            }}
        """)
        self.mic_pill.setText("🎙  Mic is ON")
        self.voice_worker.start()
        self.set_orb_state_signal.emit("listening")
    else:
        self.mic_btn.setStyleSheet(f"""
            QPushButton {{
                background: #8B0000; color: white;
                border-radius: 22px; border: none; font-size: 16px;
            }}
        """)
        self.mic_pill.setText("🎙  Mic is OFF")
        self.voice_worker.terminate()
        self.set_orb_state_signal.emit("idle")

def _on_voice_input(self, text: str):
    if not self.voice_active:
        return
    self._add_message("You", text, True)
    threading.Thread(target=self._process, args=(text,), daemon=True).start()

    def _toggle_mic(self):
        pass


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = AuraMainWindow()
    window.show()
    sys.exit(app.exec())

def add_task(self, title: str, status: str = "pending", time_str: str = ""):
    item = TaskItem(title, "", status, time_str)
    count = self.task_layout.count()
    self.task_layout.insertWidget(count - 1, item)
    self._update_task_count()

def _update_task_count(self):
    # update progress label if needed
    pass