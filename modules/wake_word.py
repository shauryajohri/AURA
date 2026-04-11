import pvporcupine
import keyboard
from pvrecorder import PvRecorder
from config.settings import PICOVOICE_KEY
ACCESS_KEY = PICOVOICE_KEY

ACCESS_KEY = "your_picovoice_key_here"

def wait_for_wake_word() -> bool:
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