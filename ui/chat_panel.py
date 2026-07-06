# ui/chat_panel.py
"""
Right column: AURA Chat. Bubbles, a plan-checklist card, a focus-session
card, the input row, and a reminder toast pinned to the bottom.

Content is driven from outside (mock driver now, brain later) through
add_message / add_plan_card / add_focus_card / show_reminder.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from ui import theme
from ui.state import StateBus, state_accent
from ui.widgets import GlassPanel, WaveformWidget


class _Bubble(QFrame):
    def __init__(self, text: str, sender: str, timestamp: str, parent=None):
        super().__init__(parent)
        is_user = sender == "You"
        accent = theme.ACCRETION_BLUE if is_user else theme.IDLE_PURPLE
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {'rgba(61, 43, 122, 0.45)' if is_user
                                   else 'rgba(26, 16, 51, 0.75)'};
                border: 1px solid rgba(125, 127, 255, 0.20);
                border-radius: 12px;
            }}
            QLabel {{ background: transparent; border: none; }}
            """
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(3)

        head = QHBoxLayout()
        name = QLabel(sender)
        name.setFont(theme.display_font(9))
        name.setStyleSheet(f"color: {accent};")
        ts = QLabel(timestamp)
        ts.setFont(theme.body_font(8))
        ts.setStyleSheet(f"color: {theme.TEXT_DIM};")
        head.addWidget(name)
        head.addStretch()
        head.addWidget(ts)
        lay.addLayout(head)

        body = QLabel(text)
        body.setWordWrap(True)
        body.setFont(theme.body_font(10))
        body.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
        lay.addWidget(body)


class _PlanCard(QFrame):
    """Checklist card AURA drops into chat ('Here's your plan for today')."""

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            """
            QFrame {
                background-color: rgba(26, 16, 51, 0.75);
                border: 1px solid rgba(125, 127, 255, 0.20);
                border-radius: 12px;
            }
            QLabel { background: transparent; border: none; }
            """
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(5)
        for time_str, title, done in items:
            row = QLabel(
                f"{'✔' if done else '○'}  {time_str}   {title}"
            )
            row.setFont(theme.body_font(10))
            row.setStyleSheet(
                f"color: {theme.FOCUS_GREEN if done else theme.TEXT_SECONDARY};"
            )
            lay.addWidget(row)


class _FocusCard(QFrame):
    """'Focus Session Started — ends at 03:30 PM' inline confirmation."""

    def __init__(self, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: rgba(61, 220, 151, 0.08);
                border: 1px solid rgba(61, 220, 151, 0.35);
                border-radius: 12px;
            }}
            QLabel {{ background: transparent; border: none; }}
            """
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        t = QLabel(f"◎  {title}")
        t.setFont(theme.display_font(10))
        t.setStyleSheet(f"color: {theme.FOCUS_GREEN};")
        s = QLabel(subtitle)
        s.setFont(theme.body_font(9))
        s.setStyleSheet(f"color: {theme.TEXT_SECONDARY};")
        lay.addWidget(t)
        lay.addWidget(s)


class _CodeCard(QFrame):
    """Monospace code block dropped into the chat stream."""

    def __init__(self, lang: str, code: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            """
            QFrame {
                background-color: rgba(5, 3, 13, 0.9);
                border: 1px solid rgba(125, 127, 255, 0.25);
                border-radius: 10px;
            }
            QLabel { background: transparent; border: none; }
            """
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 10)
        lay.setSpacing(4)
        if lang:
            tag = QLabel(lang.upper())
            tag.setFont(theme.mono_font(8))
            tag.setStyleSheet(f"color: {theme.ION_CYAN};")
            lay.addWidget(tag)
        body = QLabel(code)
        body.setFont(theme.mono_font(9))
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
        lay.addWidget(body)


class ReminderToast(GlassPanel):
    def __init__(self, parent=None):
        super().__init__(radius=12, parent=parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 8, 8)
        icon = QLabel("🔔")
        icon.setStyleSheet("background: transparent; border: none;")
        text_col = QVBoxLayout()
        title = QLabel("Reminder")
        title.setFont(theme.display_font(9))
        title.setStyleSheet(
            f"color: {theme.ALERT_ORANGE}; background: transparent; border: none;")
        self.body = QLabel("")
        self.body.setWordWrap(True)
        self.body.setFont(theme.body_font(9))
        self.body.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; background: transparent; border: none;")
        text_col.addWidget(title)
        text_col.addWidget(self.body)
        close = QPushButton("✕")
        close.setFixedSize(20, 20)
        close.setCursor(Qt.PointingHandCursor)
        close.setStyleSheet(
            f"""
            QPushButton {{ color: {theme.TEXT_DIM}; background: transparent;
                           border: none; font-size: 11px; }}
            QPushButton:hover {{ color: {theme.TEXT_PRIMARY}; }}
            """
        )
        close.clicked.connect(self.hide)
        lay.addWidget(icon)
        lay.addLayout(text_col, 1)
        lay.addWidget(close, 0, Qt.AlignTop)
        self.hide()

    def show_reminder(self, text: str):
        self.body.setText(text)
        self.show()


class ChatPanel(QWidget):
    """The whole right column: chat card + reminder toast below it."""

    def __init__(self, bus: StateBus, parent=None):
        super().__init__(parent)
        self._bus = bus
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        card = GlassPanel(radius=16)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(14, 12, 14, 12)
        card_lay.setSpacing(8)

        # header
        head = QHBoxLayout()
        title = QLabel("AURA Chat")
        title.setFont(theme.display_font(12))
        title.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; background: transparent; border: none;")
        self._head_wave = WaveformWidget(bar_count=10, height=16)
        self._head_wave.setFixedWidth(70)
        head.addWidget(title)
        head.addStretch()
        head.addWidget(self._head_wave)
        card_lay.addLayout(head)

        # scrolling message area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet(
            """
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 6px; }
            QScrollBar::handle:vertical {
                background: rgba(125, 127, 255, 0.25); border-radius: 3px; }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
            """
        )
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        self._messages = QVBoxLayout(inner)
        self._messages.setContentsMargins(0, 0, 4, 0)
        self._messages.setSpacing(8)
        self._messages.addStretch()
        self._scroll.setWidget(inner)
        card_lay.addWidget(self._scroll, 1)

        # stay pinned to the newest message whenever content or viewport
        # size changes (new bubbles, toast appearing, window resize)
        bar = self._scroll.verticalScrollBar()
        bar.rangeChanged.connect(lambda _min, _max: bar.setValue(_max))

        # input row
        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Talk or type a message...")
        self.input.setFont(theme.body_font(10))
        self.input.setFixedHeight(36)
        self.input.setStyleSheet(
            f"""
            QLineEdit {{
                background-color: rgba(5, 3, 13, 0.7);
                border: 1px solid rgba(125, 127, 255, 0.25);
                border-radius: 10px;
                padding: 0 12px;
                color: {theme.TEXT_PRIMARY};
            }}
            QLineEdit:focus {{ border: 1px solid {theme.ACCRETION_BLUE}; }}
            """
        )
        mic = QPushButton("🎙")
        send = QPushButton("➤")
        for btn, accent in ((mic, theme.EVENT_VIOLET), (send, theme.ACCRETION_BLUE)):
            btn.setFixedSize(36, 36)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {accent};
                    border: none; border-radius: 10px;
                    color: {theme.TEXT_PRIMARY}; font-size: 14px;
                }}
                QPushButton:hover {{ background-color: {theme.ACCRETION_BLUE}; }}
                """
            )
        self.mic_button = mic
        self.send_button = send
        input_row.addWidget(self.input, 1)
        input_row.addWidget(mic)
        input_row.addWidget(send)
        card_lay.addLayout(input_row)

        self.toast = ReminderToast()

        outer.addWidget(card, 1)
        outer.addWidget(self.toast)

        bus.stateChanged.connect(self._on_state)

    # ── content API (mock driver now, brain later) ───────────────────────
    def _insert(self, widget):
        self._messages.insertWidget(self._messages.count() - 1, widget)

    def add_message(self, text: str, sender: str, timestamp: str = ""):
        self._insert(_Bubble(text, sender, timestamp))

    def add_plan_card(self, items):
        self._insert(_PlanCard(items))

    def add_code(self, lang: str, code: str):
        self._insert(_CodeCard(lang, code))

    def add_focus_card(self, title: str, subtitle: str):
        self._insert(_FocusCard(title, subtitle))

    def show_reminder(self, text: str):
        self.toast.show_reminder(text)

    def _on_state(self, state: str):
        self._head_wave.set_color(state_accent(state))
        self._head_wave.set_active(state in ("listening", "speaking", "thinking"))
