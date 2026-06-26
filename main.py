import signal
import sys

from core.brain import _history, get_context, start_proactive
from modules.session_memory import get_greeting_with_memory, save_on_exit
from modules.voice_output import speak

from PySide6.QtCore import QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication
from ui.app import AuraAppController


class UiBridge(QObject):
    suggestionReceived = Signal(str)

    def __init__(self, controller):
        super().__init__()
        self.controller = controller

    @Slot(str)
    def show_suggestion(self, text: str):
        self.controller.main_window.append_message(text, "AURA")

greeting = get_greeting_with_memory()
if greeting:
    print(f"[AURA] {greeting}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    controller = AuraAppController(app)
    bridge = UiBridge(controller)
    bridge.suggestionReceived.connect(bridge.show_suggestion)

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    interrupt_timer = QTimer()
    interrupt_timer.timeout.connect(lambda: None)
    interrupt_timer.start(200)

    app.aboutToQuit.connect(
        lambda: save_on_exit(_history, get_context().get("app", "unknown"))
    )

    if greeting:
        controller.main_window.add_activity_note(greeting)

    start_proactive(
        speak_fn=speak,
        on_suggestion_fn=bridge.suggestionReceived.emit,
        on_presence_fn=controller.presenceChanged.emit,
    )
    sys.exit(app.exec())
