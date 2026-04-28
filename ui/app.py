import sys
import threading
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLineEdit, QPushButton,
    QScrollArea, QLabel, QFrame
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QFont

class VoiceWorker(QThread):
    heard = pyqtSignal(str)

    def run(self):
        from modules.voice_input import listen
        while True:
            text = listen()
            if text:
                self.heard.emit(text)

class MessageBubble(QLabel):
    def __init__(self, text: str, is_user: bool):
        super().__init__(text)
        self.setWordWrap(True)
        self.setMaximumWidth(400)
        self.setFont(QFont("Segoe UI", 11))
        if is_user:
            self.setStyleSheet("""
                QLabel {
                    background-color: #005C4B;
                    color: #FFFFFF;
                    border-radius: 12px;
                    padding: 10px 14px;
                }
            """)
        else:
            self.setStyleSheet("""
                QLabel {
                    background-color: #1E2D45;
                    color: #E0E0E0;
                    border-radius: 12px;
                    padding: 10px 14px;
                }
            """)

class ChatArea(QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setStyleSheet("background-color: #0D1117; border: none;")
        self.container = QWidget()
        self.container.setStyleSheet("background-color: #0D1117;")
        self.layout = QVBoxLayout(self.container)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.layout.setSpacing(8)
        self.layout.setContentsMargins(16, 16, 16, 16)
        self.setWidget(self.container)

    def add_message(self, text: str, is_user: bool):
        row = QHBoxLayout()
        bubble = MessageBubble(text, is_user)
        if is_user:
            row.addStretch()
            row.addWidget(bubble)
        else:
            name = QLabel("AURA")
            name.setFont(QFont("Segoe UI", 9))
            name.setStyleSheet("color: #00E5FF; padding: 0 4px;")
            col = QVBoxLayout()
            col.addWidget(name)
            col.addWidget(bubble)
            col.setSpacing(2)
            wrapper = QWidget()
            wrapper.setLayout(col)
            row.addWidget(wrapper)
            row.addStretch()
        frame = QFrame()
        frame.setLayout(row)
        frame.setStyleSheet("background: transparent;")
        self.layout.addWidget(frame)
        QTimer.singleShot(100, lambda: self.verticalScrollBar().setValue(
            self.verticalScrollBar().maximum()
        ))

class AuraApp(QMainWindow):
    add_message_signal = pyqtSignal(str, bool)

    def __init__(self, brain_process, speak_fn):
        super().__init__()
        self.brain_process = brain_process
        self.speak_fn = speak_fn
        self.voice_enabled = True
        self.add_message_signal.connect(self._add_message)
        self._setup_ui()
        self._setup_voice()

        # start proactive suggestions
        from modules.proactive import start_proactive_loop
        start_proactive_loop(
            speak_fn=self.speak_fn,
            on_suggestion_fn=lambda text: self.add_message_signal.emit(text, False)
        )

    def _setup_ui(self):
        self.setWindowTitle("AURA")
        self.setMinimumSize(480, 700)
        self.setStyleSheet("background-color: #0D1117;")

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # header
        header = QWidget()
        header.setFixedHeight(60)
        header.setStyleSheet("background-color: #141D2B; border-bottom: 1px solid #1E2D45;")
        header_layout = QHBoxLayout(header)
        self.orb = QLabel("●")
        self.orb.setFont(QFont("Arial", 18))
        self.orb.setStyleSheet("color: #00E5FF;")
        title = QLabel("AURA")
        title.setFont(QFont("Arial Black", 16))
        title.setStyleSheet("color: #FFFFFF;")
        self.status = QLabel("Listening...")
        self.status.setFont(QFont("Segoe UI", 10))
        self.status.setStyleSheet("color: #8B949E;")
        header_layout.addWidget(self.orb)
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.status)
        header_layout.setContentsMargins(16, 0, 16, 0)
        main_layout.addWidget(header)

        # chat area
        self.chat = ChatArea()
        main_layout.addWidget(self.chat)

        # input area
        input_area = QWidget()
        input_area.setFixedHeight(70)
        input_area.setStyleSheet("background-color: #141D2B; border-top: 1px solid #1E2D45;")
        input_layout = QHBoxLayout(input_area)
        input_layout.setContentsMargins(12, 10, 12, 10)
        input_layout.setSpacing(8)

        self.voice_btn = QPushButton("🎤")
        self.voice_btn.setFixedSize(44, 44)
        self.voice_btn.setStyleSheet("""
            QPushButton {
                background-color: #00E5FF;
                border-radius: 22px;
                font-size: 18px;
            }
            QPushButton:hover { background-color: #00B8D9; }
        """)
        self.voice_btn.clicked.connect(self._toggle_voice)

        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Type a message...")
        self.text_input.setFont(QFont("Segoe UI", 11))
        self.text_input.setStyleSheet("""
            QLineEdit {
                background-color: #1E2D45;
                color: #FFFFFF;
                border: none;
                border-radius: 22px;
                padding: 10px 16px;
            }
        """)
        self.text_input.returnPressed.connect(self._send_text)

        send_btn = QPushButton("➤")
        send_btn.setFixedSize(44, 44)
        send_btn.setStyleSheet("""
            QPushButton {
                background-color: #005C4B;
                color: white;
                border-radius: 22px;
                font-size: 16px;
            }
            QPushButton:hover { background-color: #007A63; }
        """)
        send_btn.clicked.connect(self._send_text)

        input_layout.addWidget(self.voice_btn)
        input_layout.addWidget(self.text_input)
        input_layout.addWidget(send_btn)
        main_layout.addWidget(input_area)

        QTimer.singleShot(500, lambda: self._add_message(
            "Hey! I'm AURA. You can type or talk to me.", False
        ))

    def _setup_voice(self):
        self.voice_worker = VoiceWorker()
        self.voice_worker.heard.connect(self._on_voice_input)
        if self.voice_enabled:
            self.voice_worker.start()

    def _toggle_voice(self):
        self.voice_enabled = not self.voice_enabled
        if self.voice_enabled:
            self.voice_btn.setStyleSheet("""
                QPushButton {
                    background-color: #00E5FF;
                    border-radius: 22px;
                    font-size: 18px;
                }
            """)
            self.status.setText("Listening...")
            self.voice_worker.start()
        else:
            self.voice_btn.setStyleSheet("""
                QPushButton {
                    background-color: #333;
                    border-radius: 22px;
                    font-size: 18px;
                }
            """)
            self.status.setText("Voice off")
            self.voice_worker.terminate()

    def _send_text(self):
        text = self.text_input.text().strip()
        if not text:
            return
        self.text_input.clear()
        self._add_message(text, True)
        threading.Thread(
            target=self._process_and_reply,
            args=(text,),
            daemon=True
        ).start()

    def _on_voice_input(self, text: str):
        self._add_message(text, True)
        threading.Thread(
            target=self._process_and_reply,
            args=(text,),
            daemon=True
        ).start()

    def _process_and_reply(self, text: str):
        self.status.setText("Thinking...")
        self.orb.setStyleSheet("color: #A855F7;")
        response = self.brain_process(text)
        self.add_message_signal.emit(response, False)
        self.speak_fn(response)
        self.status.setText("Listening...")
        self.orb.setStyleSheet("color: #00E5FF;")

    def _add_message(self, text: str, is_user: bool):
        self.chat.add_message(text, is_user)