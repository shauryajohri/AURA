import sys
from PyQt6.QtWidgets import QApplication
from core.brain import process, start_proactive
from modules.voice_output import speak
from ui.app import AuraApp

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AuraApp(brain_process=process, speak_fn=speak)
    window.show()
    start_proactive(
        speak_fn=speak,
        on_suggestion_fn=lambda text: window.add_msg_signal.emit(text, False)
    )
    sys.exit(app.exec())
