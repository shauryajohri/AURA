import pyttsx3
import threading
from config.settings import TTS_RATE, TTS_VOLUME

_engine = None
_lock = threading.Lock()


def _get_engine():
    global _engine
    if _engine is None:
        _engine = pyttsx3.init()
        _engine.setProperty('rate', TTS_RATE)
        _engine.setProperty('volume', TTS_VOLUME)

        # pick best available Windows voice
        voices = _engine.getProperty('voices')
        for voice in voices:
            if 'zira' in voice.name.lower() or 'david' in voice.name.lower():
                _engine.setProperty('voice', voice.id)
                break
    return _engine


def speak(text: str):
    with _lock:
        engine = _get_engine()
        print(f"[AURA] {text}")
        engine.say(text)
        engine.runAndWait()