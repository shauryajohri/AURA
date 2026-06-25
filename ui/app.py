import threading

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot

from ui.orb import OrbWidget
from ui.main_window import MainWindow


class AuraAppController(QObject):
    responseChunk = Signal(str)
    codeBlock = Signal(str, str)
    taskFailed = Signal(str)
    taskFinished = Signal()

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        self._busy = False

        self.orb = OrbWidget()
        self.main_window = MainWindow(self.orb)

        self.orb.requestRestore.connect(self.show_main_window)
        self.orb.requestQuickPanel.connect(self._on_orb_single_click)
        self.orb.requestQuit.connect(self.app.quit)
        self.orb.requestUnlock.connect(self._on_unlock_requested)

        self.main_window.sendMessage.connect(self._on_user_message)
        self.responseChunk.connect(self._append_response_chunk)
        self.codeBlock.connect(self.main_window.append_code)
        self.taskFailed.connect(self._show_task_error)
        self.taskFinished.connect(self._on_task_finished)

        self.show_main_window()
        self.float_orb()
        self._keep_orb_visible_timer = QTimer(self)
        self._keep_orb_visible_timer.timeout.connect(self.ensure_orb_visible)
        self._keep_orb_visible_timer.start(1000)

    # ── Mode switching ───────────────────────────────────────────────────
    def float_orb(self):
        self.orb.setParent(None)
        self.orb.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        screen_geo = self.app.primaryScreen().availableGeometry()
        self.orb.move(
            screen_geo.right() - self.orb.width() - 40,
            screen_geo.bottom() - self.orb.height() - 60,
        )
        self.orb.show()
        self.orb.raise_()
        self.orb.activateWindow()
        self.orb.update()

    def show_main_window(self):
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()
        self.ensure_orb_visible()

    def ensure_orb_visible(self):
        if self.orb.parent() is not None:
            self.orb.setParent(None)
            self.orb.setWindowFlags(
                Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            )
        if not self.orb.isVisible():
            self.float_orb()
        else:
            self.orb.raise_()
            self.orb.update()

    # ── Orb interaction handlers ─────────────────────────────────────────
    def _on_orb_single_click(self):
        if self.main_window.isVisible():
            self.main_window.hide()
            self.ensure_orb_visible()
        else:
            self.show_main_window()

    def _on_unlock_requested(self):
        try:
            from modules.proactive import clear_app_lock
            clear_app_lock()
            self.main_window.add_activity_note("Unlocked from focused app (via orb menu)")
        except Exception as e:
            print(f"[AURA UI] Unlock error: {e}")

    # ── Wiring to AURA's actual brain ─────────────────────────────────────
    def _on_user_message(self, text: str):
        if self._busy:
            self.main_window.append_message("Still working on the last one.", "AURA")
            return

        self._busy = True
        self._pending_response = []
        self.orb.set_state(OrbWidget.STATE_THINKING)
        self.main_window.set_status_text("thinking")

        worker = threading.Thread(
            target=self._process_user_message,
            args=(text,),
            daemon=True,
        )
        worker.start()

    def _process_user_message(self, text: str):
        try:
            from core.brain import process_streaming

            def on_chunk(chunk: str):
                self.responseChunk.emit(chunk)

            def on_code(lang: str, code: str):
                self.codeBlock.emit(lang, code)

            process_streaming(text, on_chunk=on_chunk, on_code=on_code)
        except Exception as e:
            self.taskFailed.emit(str(e))
        finally:
            self.taskFinished.emit()

    @Slot(str)
    def _append_response_chunk(self, chunk: str):
        self._pending_response.append(chunk)

    @Slot(str)
    def _show_task_error(self, error: str):
        self.main_window.append_message(f"Error: {error}", "AURA")

    @Slot()
    def _on_task_finished(self):
        final = "".join(self._pending_response).strip()
        if final:
            self.main_window.append_message(final, "AURA")
        self._pending_response = []
        self._busy = False
        self.orb.set_state(OrbWidget.STATE_IDLE)
        self.main_window.set_status_text("idle")

    # ── External hooks ────────────────────────────────────────────────────
    def on_listening_start(self):
        self.orb.set_state(OrbWidget.STATE_LISTENING)
        self.main_window.set_voice_status("Listening...")
        self.main_window.set_status_text("listening")

    def on_thinking_start(self):
        self.orb.set_state(OrbWidget.STATE_THINKING)
        self.main_window.set_status_text("thinking")

    def on_speaking_start(self):
        self.orb.set_state(OrbWidget.STATE_SPEAKING)
        self.main_window.set_status_text("speaking")

    def on_idle(self):
        self.orb.set_state(OrbWidget.STATE_IDLE)
        self.main_window.set_voice_status("Listening for you")
        self.main_window.set_status_text("idle")
