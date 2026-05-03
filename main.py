import sys
from PyQt6.QtWidgets import QApplication
from core.brain import process
from modules.voice_output import speak
from ui.app import AuraMainWindow    # ← changed
import core.brain as brain

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = AuraMainWindow(         # ← changed
        brain_process=process,
        speak_fn=speak
    )
    window.show()

    # Start the proactive Donna loop
    brain.start_proactive(speak_fn=speak)
    sys.exit(app.exec())