import speech_recognition as sr
import threading

recognizer = sr.Recognizer()
mic = sr.Microphone()

# calibrate once at startup
with mic as source:
    recognizer.adjust_for_ambient_noise(source, duration=1)

def listen_continuous(callback):
    """
    Always-on listening — calls callback with every sentence heard
    Runs in background thread
    """
    def _listen():
        while True:
            try:
                with mic as source:
                    audio = recognizer.listen(
                        source,
                        timeout=None,
                        phrase_time_limit=8
                    )
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

    thread = threading.Thread(target=_listen, daemon=True)
    thread.start()
    return thread

def listen() -> str | None:
    with mic as source:
        print("[AURA] Listening...")
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
            text = recognizer.recognize_google(audio)
            print(f"[AURA] Heard: {text}")
            return text
        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            return None
        except sr.RequestError:
            print("[AURA] Speech service unavailable")
            return None