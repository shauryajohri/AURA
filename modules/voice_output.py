import asyncio
import tempfile
import os
import re
import random
import threading

try:
    import edge_tts
except ModuleNotFoundError:
    edge_tts = None

try:
    import pygame
except ModuleNotFoundError:
    pygame = None

# ── Voice map ─────────────────────────────────────────────────────────────────
VOICE_MAP = {
    "normal":  "en-US-AriaNeural",
    "tease":   "en-US-AriaNeural",
    "happy":   "en-US-AriaNeural",
    "serious": "en-US-AriaNeural",
}

# ── Tone detection ────────────────────────────────────────────────────────────
def detect_tone(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["error", "fail", "crash", "warning"]):
        return "serious"
    if any(w in t for w in ["great", "done", "saved", "added", "perfect"]):
        return "happy"
    if any(w in t for w in ["dumb", "stupid", "bruh"]):
        return "tease"
    return "normal"

# ── Rate/pitch per tone ───────────────────────────────────────────────────────
TONE_SETTINGS = {
    "normal":  {"rate": "+0%",  "pitch": "+0Hz"},
    "tease":   {"rate": "+8%",  "pitch": "+5Hz"},
    "happy":   {"rate": "+5%",  "pitch": "+8Hz"},
    "serious": {"rate": "-5%",  "pitch": "-3Hz"},
}

# ── Text cleaner ──────────────────────────────────────────────────────────────
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

# ── TTS generation ────────────────────────────────────────────────────────────
async def _generate(text: str, tone: str, path: str):
    if edge_tts is None:
        raise RuntimeError("edge_tts is not installed")

    voice = VOICE_MAP.get(tone, "en-US-AriaNeural")
    settings = TONE_SETTINGS.get(tone, TONE_SETTINGS["normal"])
    communicate = edge_tts.Communicate(
        text,
        voice=voice,
        rate=settings["rate"],
        pitch=settings["pitch"]
    )
    await communicate.save(path)

# ── Main speak function ───────────────────────────────────────────────────────
def speak(text: str):
    clean = clean_text(text)
    if not clean:
        return

    print(f"[AURA] {clean}")
    tone = detect_tone(clean)

    try:
        if pygame is None:
            print("[AURA TTS Error] pygame is not installed")
            return

        # generate audio
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            tmp_path = f.name

        asyncio.run(_generate(clean, tone, tmp_path))

        # play audio
        if not pygame.mixer.get_init():
            pygame.mixer.init()

        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            pygame.time.wait(50)

        pygame.mixer.music.unload()
        os.unlink(tmp_path)

    except Exception as e:
        print(f"[AURA TTS Error] {e}")
        # fallback to print only
        pass

# ── speak_chunks for speech planner ──────────────────────────────────────────
def speak_chunks(chunks):
    import time
    for chunk in chunks:
        if chunk.pause_before > 0:
            time.sleep(chunk.pause_before)
        speak(chunk.text)
        if chunk.pause_after > 0:
            time.sleep(chunk.pause_after)
