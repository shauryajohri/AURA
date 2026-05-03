import asyncio
import time
import edge_tts
import pygame
import tempfile
import os
import re
import random
import threading
import pyttsx3
_is_speaking = False
_muted       = False
_stop_flag   = False
_engine      = None
_lock        = threading.Lock()
_engine = None
TTS_RATE   = int(os.getenv("TTS_RATE", "175"))
TTS_VOLUME = float(os.getenv("TTS_VOLUME", "1.0"))
TTS_VOICE  = os.getenv("TTS_VOICE", "zira")

def _get_engine():
    global _engine
    if _engine is None:
        _engine = pyttsx3.init()
        _engine.setProperty("rate", TTS_RATE)
        _engine.setProperty("volume", TTS_VOLUME)
        
        voices = _engine.getProperty("voices")
        
        # print all available voices so you can see them
        print("[AURA TTS] Available voices:")
        for i, v in enumerate(voices):
            print(f"  [{i}] {v.name} — {v.id}")
        
        # lock to Zira only — ignore everything else
        zira = None
        for v in voices:
            if "zira" in v.name.lower():
                zira = v
                break
        
        if zira:
            _engine.setProperty("voice", zira.id)
            print(f"[AURA TTS] Voice locked: {zira.name}")
        else:
            print("[AURA TTS] Zira not found — using default")
            
    return _engine
# Voice map based on tone
VOICE_MAP = {
    "normal":  "en-US-AriaNeural",
    "tease":   "en-US-JennyNeural",
    "happy":   "en-US-AriaNeural",
    "serious": "en-US-GuyNeural"
}

# Micro reactions
TEASE_LINES = [
    "bro what was that",
    "nahh you kidding",
    "that was interesting",
    "okay then",
    "sure sure sure"
]

def detect_tone(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["dumb", "stupid", "bruh", "idiot", "wrong", "bad"]):
        return "tease"
    if any(w in t for w in ["great", "nice", "good", "perfect", "awesome", "saved", "done"]):
        return "happy"
    if any(w in t for w in ["error", "fail", "crash", "exception", "traceback", "warning"]):
        return "serious"
    return "normal"

def humanize(text: str, tone: str) -> str:
    # add natural filler occasionally
    fillers = {
        "tease":  ["hmm… ", "okay so… ", "wait— "],
        "happy":  ["oh nice! ", "okay! ", ""],
        "serious": ["alright, ", "so— ", ""],
        "normal": ["", "so ", ""]
    }
    filler = random.choice(fillers.get(tone, [""]))
    return filler + text

def style_text(text: str, tone: str) -> str:
    text = text.replace("&", "and").replace("<", "").replace(">", "")
    
    if tone == "tease":
        return f"""<speak>
            <prosody rate="115%" pitch="+8%">
                hmm… <break time="200ms"/> {text}
            </prosody>
        </speak>"""
    
    elif tone == "happy":
        return f"""<speak>
            <prosody rate="110%" pitch="+10%">
                {text}
            </prosody>
        </speak>"""
    
    elif tone == "serious":
        return f"""<speak>
            <prosody rate="90%" pitch="-5%">
                <break time="150ms"/> {text}
            </prosody>
        </speak>"""
    
    return f"<speak>{text}</speak>"

def clean_text(text: str) -> str:
    text = re.sub(r'\*\*|__|\*|_|~~|`', '', text)
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'[#\[\]{}|<>]', '', text)
    text = re.sub(r'\[You might also.*?\]', '', text, flags=re.DOTALL)
    text = re.sub(r'Anticipated Follow-up.*', '', text, flags=re.DOTALL)
    text = re.sub(r'aura:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'User asks:.*', '', text, flags=re.DOTALL)
    text = re.sub(r'Screen content:.*', '', text, flags=re.DOTALL)
    text = re.sub(r'"', '', text)
    # keep 2 sentences max
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    text = '. '.join(sentences[:2])
    if text and not text.endswith('.'):
        text += '.'
    return text.strip()

async def _generate(text: str, tone: str, path: str):
    voice = VOICE_MAP[tone]
    
    # tone settings without SSML
    settings = {
        "tease":   {"rate": "+15%", "pitch": "+8Hz"},
        "happy":   {"rate": "+10%", "pitch": "+10Hz"},
        "serious": {"rate": "-10%", "pitch": "-5Hz"},
        "normal":  {"rate": "+0%",  "pitch": "+0Hz"},
    }
    
    s = settings.get(tone, settings["normal"])
    communicate = edge_tts.Communicate(
        text, 
        voice=voice,
        rate=s["rate"],
        pitch=s["pitch"]
    )
    await communicate.save(path)

def speak(text: str):
    clean = clean_text(text)
    if not clean:
        return

    print(f"[AURA] {clean}")
    tone = detect_tone(clean)
    human = humanize(clean, tone)

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            tmp_path = f.name

        asyncio.run(_generate(human, tone, tmp_path))

        pygame.mixer.init()
        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            pygame.time.wait(50)

        pygame.mixer.music.unload()
        os.unlink(tmp_path)

    except Exception as e:
        print(f"[AURA TTS Error] {e}")
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.say(clean)
            engine.runAndWait()
            engine.stop()
        except:
            pass
    
def speak_chunk(chunk) -> bool:
    global _is_speaking
    if _muted or _stop_flag:
        return False
    if chunk.pause_before > 0:
        time.sleep(chunk.pause_before)
    if _stop_flag:
        return False
    _is_speaking = True
    print(f"[AURA] [{chunk.tone}] {chunk.text}")
    _speak_text(chunk.text)
    if chunk.pause_after > 0 and not _stop_flag:
        time.sleep(chunk.pause_after)
    _is_speaking = False
    return True


def speak_chunks(chunks: list):
    def _worker():
        global _is_speaking
        _is_speaking = True
        for chunk in chunks:
            if _stop_flag or _muted:
                break
            speak_chunk(chunk)
        _is_speaking = False
    threading.Thread(target=_worker, daemon=True).start()

def _speak_text(text: str):
    with _lock:
        engine = _get_engine()
        try:
            engine.say(text)
            engine.runAndWait()
        except RuntimeError:
            global _engine
            _engine = None

def speak_chunks(chunks):
    import time
    for chunk in chunks:
        if chunk.pause_before > 0:
            time.sleep(chunk.pause_before)
        speak(chunk.text)
        if chunk.pause_after > 0:
            time.sleep(chunk.pause_after)