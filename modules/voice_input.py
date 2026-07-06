"""
modules/voice_input.py
----------------------
Speech-to-text. Mic + recognizer are initialized LAZILY (first use), not at
import time — importing this module can never crash the app on a machine
without a working microphone/PortAudio.
"""

import threading

recognizer = None
mic = None
_init_lock = threading.Lock()
_init_failed = False


def ensure_mic() -> bool:
    """Lazy-init the recognizer + microphone. Safe to call repeatedly.
    Returns True if the mic is usable."""
    global recognizer, mic, _init_failed
    with _init_lock:
        if mic is not None:
            return True
        if _init_failed:
            return False
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            mic = sr.Microphone()
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=1)
            return True
        except Exception as e:
            _init_failed = True
            print(f"[AURA Mic] init failed: {e}")
            return False


def mic_available() -> bool:
    return ensure_mic()


def listen_continuous(callback, stop_event: threading.Event = None):
    """
    Always-on listening — calls callback(text) with every sentence heard.
    Runs in a background daemon thread.

    Returns (thread, stop_event). Set stop_event to stop listening; the
    loop notices within ~2 s (listen timeout).
    """
    import speech_recognition as sr

    if stop_event is None:
        stop_event = threading.Event()

    def _listen():
        if not ensure_mic():
            print("[AURA Mic] No microphone — voice input disabled")
            return
        while not stop_event.is_set():
            try:
                with mic as source:
                    try:
                        audio = recognizer.listen(
                            source,
                            timeout=2,           # short so stop_event is honoured
                            phrase_time_limit=8,
                        )
                    except sr.WaitTimeoutError:
                        continue
                if stop_event.is_set():
                    break
                try:
                    text = recognizer.recognize_google(audio)
                    if text:
                        callback(text)
                except sr.UnknownValueError:
                    pass
                except sr.RequestError:
                    print("[AURA] Speech service unavailable")
            except Exception as e:
                print(f"[AURA Mic Error] {e}")
                if stop_event.wait(1.0):  # don't spin on a broken mic
                    break

    thread = threading.Thread(target=_listen, daemon=True)
    thread.start()
    return thread, stop_event


def listen(timeout: float = 1) -> str | None:
    """One-shot listen (used after wake word)."""
    import speech_recognition as sr

    if not ensure_mic():
        return None
    with mic as source:
        try:
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=10)
            return recognizer.recognize_google(audio)
        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            return None
        except sr.RequestError:
            print("[AURA] Speech service unavailable")
            return None
