import sys
from PyQt6.QtWidgets import QApplication
from core.brain import process, start_proactive
from modules.voice_output import speak
from ui.app import AuraApp

from modules.session_memory import get_greeting_with_memory

greeting = get_greeting_with_memory()
if greeting:
    print(f"[AURA] {greeting}")
    # pass to UI / TTS however you normally do it
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AuraApp(brain_process=process, speak_fn=speak)
    window.show()
    start_proactive(
        speak_fn=speak,
        on_suggestion_fn=lambda text: window.add_msg_signal.emit(text, False)
    )
    sys.exit(app.exec())
from modules.session_memory import save_on_exit
from core.brain import _history, get_context

save_on_exit(_history, get_context().get("app", "unknown"))