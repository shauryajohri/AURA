# aura_ui/main_window.py

import time
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QLineEdit, QPushButton, QFrame, QSizePolicy, QSplitter, QTextEdit
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from ui.theme import (
    VOID_BLACK, NEBULA_PURPLE, EVENT_VIOLET, ACCRETION_BLUE, ION_CYAN,
    STARLIGHT_WHITE, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_DIM,
    panel_stylesheet, display_font, body_font, mono_font
)
from ui.orb import OrbWidget


class GlassPanel(QFrame):
    def __init__(self, radius=16, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QFrame {{ {panel_stylesheet(radius)} }}")


class ChatBubble(QFrame):
    def __init__(self, text: str, sender: str, parent=None):
        super().__init__(parent)
        is_user = sender.lower() == "you"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)

        label_sender = QLabel(sender)
        label_sender.setFont(mono_font(10))
        label_sender.setStyleSheet(
            f"color: {ION_CYAN if not is_user else TEXT_DIM}; letter-spacing: 1px;"
        )

        label_text = QLabel(text)
        label_text.setFont(body_font(13))
        label_text.setWordWrap(True)
        label_text.setStyleSheet(f"color: {TEXT_PRIMARY};")

        layout.addWidget(label_sender)
        layout.addWidget(label_text)

        bg = "rgba(91, 127, 255, 0.16)" if is_user else "rgba(127, 232, 255, 0.08)"
        border = ACCRETION_BLUE if is_user else EVENT_VIOLET
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 12px;
            }}
        """)
        self.setMaximumWidth(480)


# ── User presence states ───────────────────────────────────────────────────────
PRESENCE_WORKING = "working"
PRESENCE_IDLE    = "idle"
PRESENCE_AFK     = "afk"

PRESENCE_STYLES = {
    PRESENCE_WORKING: {
        "dot":   "#3ddc97",   # green
        "label": "Working",
        "color": "#3ddc97",
    },
    PRESENCE_IDLE: {
        "dot":   "#f0a500",   # amber
        "label": "Idle",
        "color": "#f0a500",
    },
    PRESENCE_AFK: {
        "dot":   "#ff5c6e",   # red
        "label": "AFK",
        "color": "#ff5c6e",
    },
}


class MainWindow(QWidget):
    sendMessage = Signal(str)
    micToggled = Signal(bool)

    def __init__(self, orb: OrbWidget, parent=None):
        super().__init__(parent)
        self._orb = orb
        self._mic_on = False
        self._presence = PRESENCE_IDLE
        self.setWindowTitle("AURA")
        self.resize(1380, 780)
        self.setStyleSheet(f"background-color: {VOID_BLACK};")
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_title_bar())

        body = QHBoxLayout()
        body.setContentsMargins(16, 12, 16, 16)
        body.setSpacing(14)

        body.addWidget(self._build_orb_panel(), stretch=3)
        body.addWidget(self._build_conversation_panel(), stretch=5)
        body.addWidget(self._build_code_panel(), stretch=4)
        body.addWidget(self._build_memory_panel(), stretch=3)

        root.addLayout(body)

    def _build_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(48)
        bar.setStyleSheet(f"background-color: {NEBULA_PURPLE};")

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 0, 16, 0)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {ION_CYAN}; font-size: 10px;")

        title = QLabel("AURA")
        title.setFont(display_font(16))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; letter-spacing: 2px;")

        self._status_label = QLabel("idle")
        self._status_label.setFont(mono_font(10))
        self._status_label.setStyleSheet(f"color: {TEXT_DIM};")

        layout.addWidget(dot)
        layout.addSpacing(8)
        layout.addWidget(title)
        layout.addSpacing(16)
        layout.addWidget(self._status_label)
        layout.addStretch()

        minimize_btn = self._titlebar_button("─", self.hide)
        layout.addWidget(minimize_btn)

        return bar

    def _titlebar_button(self, glyph: str, on_click) -> QPushButton:
        btn = QPushButton(glyph)
        btn.setFixedSize(32, 32)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: 6px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {EVENT_VIOLET};
                color: {TEXT_PRIMARY};
            }}
        """)
        btn.clicked.connect(on_click)
        return btn

    def _build_orb_panel(self) -> QWidget:
        panel = GlassPanel(radius=20)
        layout = QVBoxLayout(panel)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(18)
        self._orb_panel_layout = layout

        layout.addStretch()

        # ── Presence indicator ───────────────────────────────────────────
        presence_row = QHBoxLayout()
        presence_row.setAlignment(Qt.AlignCenter)
        presence_row.setSpacing(6)

        self._presence_dot = QLabel("●")
        self._presence_dot.setFont(mono_font(9))

        self._presence_label = QLabel("Idle")
        self._presence_label.setFont(mono_font(11))

        presence_row.addWidget(self._presence_dot)
        presence_row.addWidget(self._presence_label)

        presence_wrap = QWidget()
        presence_wrap.setLayout(presence_row)
        presence_wrap.setStyleSheet(f"""
            QWidget {{
                background-color: rgba(255,255,255,0.04);
                border: 1px solid {EVENT_VIOLET};
                border-radius: 8px;
                padding: 4px 10px;
            }}
        """)
        layout.addWidget(presence_wrap, alignment=Qt.AlignCenter)

        self._set_presence_style(PRESENCE_IDLE)
        # ────────────────────────────────────────────────────────────────

        floating_note = QLabel("Orb active")
        floating_note.setFont(mono_font(11))
        floating_note.setAlignment(Qt.AlignCenter)
        floating_note.setStyleSheet(f"color: {ION_CYAN};")
        layout.addWidget(floating_note)

        self._voice_status = QLabel("Listening for you")
        self._voice_status.setFont(body_font(13))
        self._voice_status.setAlignment(Qt.AlignCenter)
        self._voice_status.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(self._voice_status)

        self._mic_btn = QPushButton("🎤  Mic Off")
        self._mic_btn.setFixedHeight(38)
        self._mic_btn.setCursor(Qt.PointingHandCursor)
        self._mic_btn.setStyleSheet(self._mic_style(False))
        self._mic_btn.clicked.connect(self._toggle_mic)
        layout.addWidget(self._mic_btn, alignment=Qt.AlignCenter)

        layout.addStretch()
        return panel

    def _set_presence_style(self, state: str):
        s = PRESENCE_STYLES.get(state, PRESENCE_STYLES[PRESENCE_IDLE])
        self._presence_dot.setStyleSheet(f"color: {s['dot']}; font-size: 9px;")
        self._presence_label.setText(s["label"])
        self._presence_label.setStyleSheet(f"color: {s['color']}; font-weight: 600;")

    def set_presence(self, state: str):
        """
        Call this from app.py to update the presence badge.
        state: 'working' | 'idle' | 'afk'
        """
        if state == self._presence:
            return
        self._presence = state
        self._set_presence_style(state)

    def _mic_style(self, active: bool) -> str:
        if active:
            return f"""
                QPushButton {{
                    background-color: {ION_CYAN};
                    color: {VOID_BLACK};
                    border: none;
                    border-radius: 10px;
                    font-weight: 700;
                    padding: 0 18px;
                    font-size: 13px;
                }}
                QPushButton:hover {{ background-color: #a0f4ff; }}
            """
        else:
            return f"""
                QPushButton {{
                    background-color: rgba(255,255,255,0.06);
                    color: {TEXT_SECONDARY};
                    border: 1px solid {EVENT_VIOLET};
                    border-radius: 10px;
                    font-weight: 600;
                    padding: 0 18px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: {EVENT_VIOLET};
                    color: {TEXT_PRIMARY};
                }}
            """

    def _toggle_mic(self):
        self._mic_on = not self._mic_on
        self._mic_btn.setText("🎤  Mic On" if self._mic_on else "🎤  Mic Off")
        self._mic_btn.setStyleSheet(self._mic_style(self._mic_on))
        self.micToggled.emit(self._mic_on)

    def dock_orb(self):
        if self._orb.parent() is not None and self._orb.window() is self:
            return
        self._orb.setParent(None)
        self._orb.setWindowFlags(Qt.Widget)
        self._orb_panel_layout.insertWidget(1, self._orb, alignment=Qt.AlignCenter)
        self._orb.show()
        self._orb.update()

    def _build_conversation_panel(self) -> QWidget:
        panel = GlassPanel(radius=20)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        header = QLabel("Conversation")
        header.setFont(display_font(14))
        header.setStyleSheet(f"color: {TEXT_PRIMARY};")
        layout.addWidget(header)

        self._chat_scroll = QScrollArea()
        self._chat_scroll.setWidgetResizable(True)
        self._chat_scroll.setStyleSheet("background: transparent; border: none;")
        self._chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        chat_container = QWidget()
        chat_container.setStyleSheet("background: transparent;")
        self._chat_layout = QVBoxLayout(chat_container)
        self._chat_layout.setSpacing(10)
        self._chat_layout.addStretch()
        self._chat_scroll.setWidget(chat_container)

        layout.addWidget(self._chat_scroll, stretch=1)
        layout.addWidget(self._build_input_row())
        return panel

    def _build_input_row(self) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Type to AURA, or just speak...")
        self._input.setFont(body_font(13))
        self._input.setFixedHeight(40)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background-color: rgba(255,255,255,0.04);
                border: 1px solid {EVENT_VIOLET};
                border-radius: 10px;
                padding: 0 14px;
                color: {TEXT_PRIMARY};
            }}
            QLineEdit:focus {{ border: 1px solid {ACCRETION_BLUE}; }}
        """)
        self._input.returnPressed.connect(self._on_submit)

        send_btn = QPushButton("Send")
        send_btn.setFixedSize(72, 40)
        send_btn.setCursor(Qt.PointingHandCursor)
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCRETION_BLUE};
                color: {VOID_BLACK};
                border: none;
                border-radius: 10px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {ION_CYAN}; }}
        """)
        send_btn.clicked.connect(self._on_submit)

        row_layout.addWidget(self._input, stretch=1)
        row_layout.addWidget(send_btn)
        return row

    def _build_code_panel(self) -> QWidget:
        panel = GlassPanel(radius=20)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        header = QLabel("Code")
        header.setFont(display_font(14))
        header.setStyleSheet(f"color: {TEXT_PRIMARY};")
        header_row.addWidget(header)
        header_row.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedSize(52, 26)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_DIM};
                border: 1px solid {EVENT_VIOLET};
                border-radius: 6px;
                font-size: 11px;
            }}
            QPushButton:hover {{ color: {TEXT_PRIMARY}; border-color: {ACCRETION_BLUE}; }}
        """)
        clear_btn.clicked.connect(self._clear_code)
        header_row.addWidget(clear_btn)
        layout.addLayout(header_row)

        self._code_view = QTextEdit()
        self._code_view.setReadOnly(True)
        self._code_view.setFont(mono_font(12))
        self._code_view.setPlaceholderText("Code from AURA will appear here...")
        self._code_view.setStyleSheet(f"""
            QTextEdit {{
                background-color: rgba(0, 0, 0, 0.4);
                border: 1px solid {EVENT_VIOLET};
                border-radius: 10px;
                color: {ION_CYAN};
                padding: 10px;
            }}
            QScrollBar:vertical {{ width: 6px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {EVENT_VIOLET}; border-radius: 3px; }}
        """)
        layout.addWidget(self._code_view, stretch=1)
        return panel

    def _clear_code(self):
        self._code_view.clear()

    def _build_memory_panel(self) -> QWidget:
        panel = GlassPanel(radius=20)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel("Memory & Activity")
        header.setFont(display_font(13))
        header.setStyleSheet(f"color: {TEXT_PRIMARY};")
        layout.addWidget(header)

        self._activity_container = QVBoxLayout()
        self._activity_container.setSpacing(8)
        layout.addLayout(self._activity_container)
        layout.addStretch()
        return panel

    def set_plan_panel(self, panel: QWidget):
        panel.setParent(self)
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self._activity_container.insertWidget(0, panel)
        panel.hide()

    # ── Public API ────────────────────────────────────────────────────────
    def append_message(self, text: str, sender: str):
        bubble = ChatBubble(text, sender)
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, bubble)
        self._chat_scroll.verticalScrollBar().setValue(
            self._chat_scroll.verticalScrollBar().maximum()
        )

    def append_code(self, lang: str, code: str):
        header = f"# ── {lang.upper()} ──────────────────────\n" if lang else ""
        self._code_view.append(header + code + "\n")

    def add_activity_note(self, text: str):
        ts = time.strftime("%H:%M")
        note = QLabel(f"{ts}  ·  {text}")
        note.setFont(mono_font(10))
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self._activity_container.addWidget(note)

    def set_status_text(self, text: str):
        self._status_label.setText(text)

    def set_voice_status(self, text: str):
        self._voice_status.setText(text)

    def is_mic_on(self) -> bool:
        return self._mic_on

    # ── Internal ──────────────────────────────────────────────────────────
    def _on_submit(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self.append_message(text, "You")
        self.sendMessage.emit(text)

    def closeEvent(self, event):
        event.accept()
        QApplication.quit()