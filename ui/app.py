import sys
import threading
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QFrame, QTextEdit
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from modules.session_memory import save_on_exit

BG     = "#0D1117"
BG2    = "#141D2B"
BORDER = "#1E2D45"
CYAN   = "#00E5FF"
WHITE  = "#FFFFFF"
MUTED  = "#8B949E"
GREEN  = "#1D9E75"

class VoiceWorker(QThread):
    heard = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._running = True

    def run(self):
        try:
            from modules.voice_input import listen
            while self._running:
                text = listen(timeout=1)
                if text and self._running:
                    self.heard.emit(text)
        except Exception as e:
            print(f"[Voice] {e}")

    def stop(self):
        self._running = False
    class CheckButton(QPushButton):
            doubleClicked = pyqtSignal()

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)

class CheckButton(QPushButton):
    doubleClicked = pyqtSignal()

    def mouseDoubleClickEvent(self, event):
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)


class Bubble(QFrame):
    def __init__(self, text: str, is_user: bool):
        super().__init__()
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        name = QLabel("You" if is_user else "AURA")
        name.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        name.setStyleSheet(f"color: {MUTED if is_user else CYAN};")
        layout.addWidget(name)
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setFont(QFont("Segoe UI", 11))
        bubble.setMaximumWidth(380)
        bubble.setStyleSheet(f"""
            QLabel {{
                background: {'#1E3A5F' if is_user else BG2};
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
        self.text_label = bubble

class CodeBubble(QFrame):
    def __init__(self, code: str, language: str = "text"):
        super().__init__()
        self.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        header_row = QHBoxLayout()
        name = QLabel(f"AURA · {language}")
        name.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        name.setStyleSheet(f"color: {CYAN};")
        copy_btn = QPushButton("Copy")
        copy_btn.setFixedHeight(22)
        copy_btn.setFont(QFont("Segoe UI", 8))
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: #1E2D45; color: {CYAN};
                border-radius: 4px; border: 1px solid {CYAN}; padding: 0 8px;
            }}
            QPushButton:hover {{ background: #243850; }}
        """)
        copy_btn.clicked.connect(lambda: self._copy_code(code))
        header_row.addWidget(name)
        header_row.addStretch()
        header_row.addWidget(copy_btn)
        layout.addLayout(header_row)

        code_box = QTextEdit()
        code_box.setPlainText(code)
        code_box.setReadOnly(True)
        code_box.setFont(QFont("Consolas", 10))
        code_box.setMinimumWidth(420)
        code_box.setMaximumHeight(min(400, 24 * (code.count("\n") + 3)))
        code_box.setStyleSheet(f"""
            QTextEdit {{
                background: #0A0E14; color: #D4D4D4;
                border-radius: 8px; padding: 10px;
                border: 1px solid {BORDER};
            }}
        """)
        layout.addWidget(code_box)
        self.code_box = code_box

    def _copy_code(self, code: str):
        QApplication.clipboard().setText(code)

class AuraApp(QMainWindow):
    add_msg_signal      = pyqtSignal(str, bool)
    set_status_signal   = pyqtSignal(str)
    refresh_tasks_signal = pyqtSignal()
    stream_chunk_signal = pyqtSignal(str)
    add_code_signal     = pyqtSignal(str, str)

    def __init__(self, brain_process=None, speak_fn=None):
        super().__init__()
        self.brain_process = brain_process
        self.speak_fn      = speak_fn
        self.voice_on      = True
        self.current_stream_bubble = None
        self.add_msg_signal.connect(self._add_bubble)
        self.set_status_signal.connect(self._set_status)
        self.refresh_tasks_signal.connect(self._refresh_tasks)
        self.stream_chunk_signal.connect(self._on_stream_chunk)
        self.add_code_signal.connect(self._add_code_bubble)
        self._build()
        self._setup_voice()
        QTimer.singleShot(400, lambda: self._add_bubble(
            "Hey! I'm AURA. Type or talk to me.", False))

    def _build(self):
        self.setWindowTitle("AURA")
        self.setMinimumSize(780, 700)
        self.setStyleSheet(f"background: {BG};")
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # header
        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet(f"background: {BG2}; border-bottom: 1px solid {BORDER};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 0, 16, 0)
        orb = QLabel("●")
        orb.setFont(QFont("Arial", 16))
        orb.setStyleSheet(f"color: {CYAN};")
        title = QLabel("AURA")
        title.setFont(QFont("Arial Black", 16))
        title.setStyleSheet(f"color: {WHITE};")
        self.status_lbl = QLabel("Listening...")
        self.status_lbl.setFont(QFont("Segoe UI", 10))
        self.status_lbl.setStyleSheet(f"color: {MUTED};")
        hl.addWidget(orb)
        hl.addSpacing(8)
        hl.addWidget(title)
        hl.addStretch()
        hl.addWidget(self.status_lbl)
        vbox.addWidget(header)

        # main row
# main row
        main_row = QHBoxLayout()
        main_row.setContentsMargins(0, 0, 0, 0)
        main_row.setSpacing(0)
        main_row.addWidget(self._build_chat(), 3)
        main_row.addWidget(self._build_code_panel(), 3)
        main_row.addWidget(self._build_task_panel(), 2)
        main_widget = QWidget()
        main_widget.setLayout(main_row)
        vbox.addWidget(main_widget, 1)

        # input bar
        bar = QWidget()
        bar.setFixedHeight(68)
        bar.setStyleSheet(f"background: {BG2}; border-top: 1px solid {BORDER};")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(12, 10, 12, 10)
        bl.setSpacing(8)
        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setFixedSize(44, 44)
        self.mic_btn.setStyleSheet(f"""
            QPushButton {{ background: {CYAN}; border-radius: 22px; font-size: 18px; }}
            QPushButton:hover {{ background: #00B8D9; }}
        """)
        self.mic_btn.clicked.connect(self._toggle_voice)
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Type a message...")
        self.text_input.setFont(QFont("Segoe UI", 11))
        self.text_input.setStyleSheet(f"""
            QLineEdit {{
                background: #1E2D45; color: {WHITE};
                border: none; border-radius: 22px; padding: 10px 16px;
            }}
        """)
        self.text_input.returnPressed.connect(self._send)
        send = QPushButton("➤")
        send.setFixedSize(44, 44)
        send.setStyleSheet(f"""
            QPushButton {{
                background: {GREEN}; color: white;
                border-radius: 22px; font-size: 16px; border: none;
            }}
            QPushButton:hover {{ background: #18856A; }}
        """)
        send.clicked.connect(self._send)
        bl.addWidget(self.mic_btn)
        bl.addWidget(self.text_input)
        bl.addWidget(send)
        vbox.addWidget(bar)

    def _build_chat(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: {BG};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{ background: {BG}; border: none; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 2px; }}
        """)
        self.chat_w = QWidget()
        self.chat_w.setStyleSheet(f"background: {BG};")
        self.chat_l = QVBoxLayout(self.chat_w)
        self.chat_l.setContentsMargins(14, 14, 14, 14)
        self.chat_l.setSpacing(6)
        self.chat_l.addStretch()
        self.scroll.setWidget(self.chat_w)
        layout.addWidget(self.scroll)
        return panel
    def _build_code_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: {BG}; border-left: 1px solid {BORDER}; border-right: 1px solid {BORDER};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet(f"background: {BG2}; border-bottom: 1px solid {BORDER};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 0, 14, 0)
        ttl = QLabel("💻  Code")
        ttl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        ttl.setStyleSheet(f"color: {WHITE};")
        hl.addWidget(ttl)
        hl.addStretch()
        layout.addWidget(header)

        self.code_scroll = QScrollArea()
        self.code_scroll.setWidgetResizable(True)
        self.code_scroll.setStyleSheet(f"""
            QScrollArea {{ background: {BG}; border: none; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 2px; }}
        """)
        self.code_w = QWidget()
        self.code_w.setStyleSheet(f"background: {BG};")
        self.code_l = QVBoxLayout(self.code_w)
        self.code_l.setContentsMargins(14, 14, 14, 14)
        self.code_l.setSpacing(10)

        self.code_panel_placeholder = QLabel("Code will show up here when AURA writes some.")
        self.code_panel_placeholder.setWordWrap(True)
        self.code_panel_placeholder.setFont(QFont("Segoe UI", 10))
        self.code_panel_placeholder.setStyleSheet(f"color: {MUTED};")
        self.code_l.addWidget(self.code_panel_placeholder)
        self.code_l.addStretch()

        self.code_scroll.setWidget(self.code_w)
        layout.addWidget(self.code_scroll)
        return panel

    def _build_task_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background: {BG2}; border-left: 1px solid {BORDER};")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet(f"background: {BG2}; border-bottom: 1px solid {BORDER};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 0, 14, 0)
        ttl = QLabel("📋  Today's Tasks")
        ttl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        ttl.setStyleSheet(f"color: {WHITE};")
        add_btn = QPushButton("+ Add")
        add_btn.setFont(QFont("Segoe UI", 9))
        add_btn.setFixedHeight(26)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: #1E2D45; color: {CYAN};
                border-radius: 6px; border: 1px solid {CYAN}; padding: 0 10px;
            }}
            QPushButton:hover {{ background: #243850; }}
        """)
        add_btn.clicked.connect(self._prompt_add_task)
        hl.addWidget(ttl)
        hl.addStretch()
        hl.addWidget(add_btn)
        layout.addWidget(header)
        self.task_scroll = QScrollArea()
        self.task_scroll.setWidgetResizable(True)
        self.task_scroll.setStyleSheet(f"""
            QScrollArea {{ background: {BG2}; border: none; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 2px; }}
        """)
        self.task_w = QWidget()
        self.task_w.setStyleSheet(f"background: {BG2};")
        self.task_l = QVBoxLayout(self.task_w)
        self.task_l.setContentsMargins(10, 10, 10, 10)
        self.task_l.setSpacing(6)
        self.task_l.addStretch()
        self.task_scroll.setWidget(self.task_w)
        layout.addWidget(self.task_scroll)
        self._refresh_tasks()
        return panel
    
    def _setup_voice(self):
        self._start_voice_worker()

    def _toggle_voice(self):
        self.voice_on = not self.voice_on
        if self.voice_on:
            self.mic_btn.setStyleSheet(f"""QPushButton {{ background: {CYAN}; border-radius: 22px; font-size: 18px; }}""")
            self.status_lbl.setText("Listening...")
            self._start_voice_worker()
        else:
            self.mic_btn.setStyleSheet(f"""QPushButton {{ background: #333; border-radius: 22px; font-size: 18px; }}""")
            self.status_lbl.setText("Voice off")
            self.voice_worker.stop()

    def _start_voice_worker(self):
        if hasattr(self, "voice_worker") and self.voice_worker.isRunning():
            self.voice_worker.finished.connect(self._start_voice_worker_now)
            return
        self._start_voice_worker_now()

    def _start_voice_worker_now(self):
        self.voice_worker = VoiceWorker()
        self.voice_worker.heard.connect(self._on_voice)
        self.voice_worker.start()

    def _on_voice(self, text: str):
        if not self.voice_on:
            return
        self._add_bubble(text, True)
        threading.Thread(target=self._process, args=(text,), daemon=True).start()

    def _send(self):
        text = self.text_input.text().strip()
        if not text:
            return
        self.text_input.clear()
        self._add_bubble(text, True)
        threading.Thread(target=self._process, args=(text,), daemon=True).start()

    def closeEvent(self, event):
        from modules.session_memory import save_on_exit
        from core.brain import _history, get_context
        save_on_exit(_history, get_context().get("app", "unknown"))
        event.accept()
    def _process(self, text: str):
        self.set_status_signal.emit("Thinking...")
        self.current_stream_bubble = None
        streamed = False

        def on_chunk(chunk: str):
            nonlocal streamed
            streamed = True
            self.stream_chunk_signal.emit(chunk)

        def on_code(lang: str, code: str):
            self.add_code_signal.emit(lang, code)

        def worker():
            try:
                from core.brain import process_streaming
                response = process_streaming(text, on_chunk=on_chunk, on_code=on_code)
            except Exception as e:
                response = f"Error: {e}"
                self.add_msg_signal.emit(response, False)
                self.set_status_signal.emit("Listening..." if self.voice_on else "Voice off")
                return

            self.current_stream_bubble = None
            self.set_status_signal.emit("Listening..." if self.voice_on else "Voice off")
            if response and not streamed:
                self.add_msg_signal.emit(response, False)
            if self.speak_fn:
                threading.Thread(
                    target=self.speak_fn,
                    args=(response,),
                    daemon=True).start()
            self.refresh_tasks_signal.emit()

        threading.Thread(target=worker, daemon=True).start()

    def _add_bubble(self, text: str, is_user: bool):
        w = Bubble(text, is_user)
        self.chat_l.insertWidget(self.chat_l.count() - 1, w)
        QTimer.singleShot(100, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))
    def _add_code_bubble(self, language: str, code: str):
        self.code_panel_placeholder.hide()
        w = CodeBubble(code, language)
        self.code_l.insertWidget(self.code_l.count() - 1, w)
        QTimer.singleShot(100, lambda: self.code_scroll.verticalScrollBar().setValue(
            self.code_scroll.verticalScrollBar().maximum()))

    def _set_status(self, text: str):
        self.status_lbl.setText(text)

    def _on_stream_chunk(self, chunk: str):
        if not self.current_stream_bubble:
            self.current_stream_bubble = Bubble("", False)
            self.chat_l.insertWidget(self.chat_l.count() - 1, self.current_stream_bubble)

        label = self.current_stream_bubble.text_label
        label.setText(label.text() + chunk)

        QTimer.singleShot(50, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    def _prompt_add_task(self):
        self.text_input.setText("add task ")
        self.text_input.setFocus()

    def _refresh_tasks(self):
        while self.task_l.count() > 1:
            item = self.task_l.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        from memory.store import get_tasks
        tasks = get_tasks()
        for task in tasks:
            self._add_task_widget(task[0], task[1], task[3])

    def _add_task_widget(self, task_id: int, title: str, status: str):
        row = QFrame()
        row.setStyleSheet(f"""
            QFrame {{
                background: {'#1A2F1A' if status == 'done' else '#0F1923'};
                border-radius: 8px;
                border: 1px solid {'#2A4A2A' if status == 'done' else BORDER};
            }}
        """)
        rl = QHBoxLayout(row)
        rl.setContentsMargins(10, 8, 10, 8)
        rl.setSpacing(8)
        check = CheckButton("✓" if status == "done" else "○")
        check.setFixedSize(24, 24)
        check.setStyleSheet(f"""
            QPushButton {{
                background: {'#22C55E' if status == 'done' else 'transparent'};
                color: {'white' if status == 'done' else MUTED};
                border-radius: 12px;
                border: 2px solid {'#22C55E' if status == 'done' else BORDER};
                font-size: 11px;
            }}
        """)
        if status != 'done':
            check.clicked.connect(
                lambda _, tid=task_id, t=title: self._mark_done(tid, t))
        else:
            check.setToolTip("Double-click to mark as pending")
            check.doubleClicked.connect(
                lambda tid=task_id, t=title: self._unmark_done(tid, t))
        lbl = QLabel(title)
        lbl.setFont(QFont("Segoe UI", 10))
        lbl.setStyleSheet(f"""
            color: {'#4A7A4A' if status == 'done' else WHITE};
            text-decoration: {'line-through' if status == 'done' else 'none'};
            background: transparent;
        """)
        lbl.setWordWrap(True)
        delete = QPushButton("✕")
        delete.setFixedSize(20, 20)
        delete.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {MUTED};
                border: none; font-size: 11px;
            }}
            QPushButton:hover {{ color: #EF4444; }}
        """)
        delete.clicked.connect(lambda _, tid=task_id: self._delete_task(tid))
        rl.addWidget(check)
        rl.addWidget(lbl, 1)
        rl.addWidget(delete)
        self.task_l.insertWidget(self.task_l.count() - 1, row)

    def _mark_done(self, task_id: int, title: str):
        from memory.store import complete_task
        complete_task(task_id)
        self._refresh_tasks()
        self._add_bubble(f"'{title}' marked done.", False)
        if self.speak_fn:
            threading.Thread(
                target=self.speak_fn,
                args=(f"Done. '{title}' checked off.",),
                daemon=True).start()

    def _unmark_done(self, task_id: int, title: str):
        from memory.store import uncomplete_task
        uncomplete_task(task_id)
        self._refresh_tasks()
        self._add_bubble(f"'{title}' moved back to pending.", False)
        if self.speak_fn:
            threading.Thread(
                target=self.speak_fn,
                args=(f"Got it, '{title}' is back on your list.",),
                daemon=True).start()

    def _delete_task(self, task_id: int):
        from memory.store import delete_task
        delete_task(task_id)
        self._refresh_tasks()
