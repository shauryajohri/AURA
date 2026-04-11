import sys
from PyQt6.QtWidgets import QApplication
from core.brain import process
from modules.voice_output import speak
from ui.app import AuraApp

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AuraApp(
        brain_process=process,
        speak_fn=speak
    )
    window.show()
    sys.exit(app.exec())