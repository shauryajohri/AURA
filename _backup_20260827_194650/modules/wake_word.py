import pvporcupine
from pvrecorder import PvRecorder
from config.settings import PICOVOICE_KEY

# Real key from the environment. (Previously a placeholder string on the next
# line clobbered this, so wake-word auth always failed.)
ACCESS_KEY = PICOVOICE_KEY

def wait_for_wake_word(stop_check=None) -> bool | None:
    """Block until the wake word is heard.

    Returns True  → wake word detected
            False → wake word unavailable (bad key, no device, ...)
            None  → stop_check() turned True (caller wants the mic back)
    """
    if not ACCESS_KEY or "your_key" in str(ACCESS_KEY).lower() \
            or "your_picovoice" in str(ACCESS_KEY).lower():
        print("[AURA] No Picovoice key set (PICOVOICE_KEY in .env) — "
              "wake word disabled. Free key: https://console.picovoice.ai")
        return False

    porcupine = None
    recorder = None
    try:
        porcupine = pvporcupine.create(
            access_key=ACCESS_KEY,
            keywords=["jarvis"]
        )
        recorder = PvRecorder(frame_length=porcupine.frame_length)
        recorder.start()
        print("[AURA] Sleeping... say 'Jarvis' to wake me")

        while True:
            if stop_check is not None and stop_check():
                return None
            pcm = recorder.read()
            result = porcupine.process(pcm)
            if result >= 0:
                print("[AURA] Wake word detected!")
                return True

    except Exception as e:
        print(f"[AURA Wake Word Error] {e}")
        return False
    finally:
        if recorder is not None:
            recorder.stop()
            recorder.delete()
        if porcupine is not None:
            porcupine.delete()