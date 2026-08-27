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

# ── Audio serialization ───────────────────────────────────────────────────────
# pygame's music channel is a SINGLE global stream. AURA drives TTS from three
# independent background threads (attention engine, proactive loop, chat reply),
# and two of them hitting mixer.load/play/unload at the same moment is a classic
# native segfault — a crash with NO Python traceback, exactly what happened on
# 2026-07-07. This lock guarantees only one utterance touches the mixer at a
# time; the others simply wait their turn.
_audio_lock = threading.Lock()

# ── Voice map ─────────────────────────────────────────────────────────────────
# edge-tts voices live on Microsoft's servers — there is no model to download
# and no file to manage, so the voice is just a name string and is therefore
# configurable rather than hard-coded.
#
# Default is Ava (en-US-AvaMultilingualNeural): the Multilingual generation is
# audibly smoother than en-US-AriaNeural, which is what AURA used to speak with
# and which is now several generations old.
#
# Override per install with AURA_TTS_VOICE in .env (see tools/voice_preview.py,
# which auditions the candidates and writes the winner for you). A single tone
# can be overridden on its own with AURA_TTS_VOICE_SERIOUS and friends, if you
# ever want her to sound different when something has actually broken.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv()
except Exception:  # noqa: BLE001 — .env is optional; the default still works
    pass

FALLBACK_VOICE = "en-US-AvaMultilingualNeural"
DEFAULT_VOICE = os.getenv("AURA_TTS_VOICE") or FALLBACK_VOICE

VOICE_MAP = {
    "normal":  os.getenv("AURA_TTS_VOICE_NORMAL")  or DEFAULT_VOICE,
    "tease":   os.getenv("AURA_TTS_VOICE_TEASE")   or DEFAULT_VOICE,
    "happy":   os.getenv("AURA_TTS_VOICE_HAPPY")   or DEFAULT_VOICE,
    "serious": os.getenv("AURA_TTS_VOICE_SERIOUS") or DEFAULT_VOICE,
}

# ── The roster the Settings picker shows ──────────────────────────────────────
# Curated, not the full 300+ edge-tts catalogue: a wall of names nobody can
# tell apart is worse than eight you can actually choose between. The
# *Multilingual* voices are Microsoft's newer generation and are audibly
# smoother than the older ones — Aria is kept only as the "what AURA used to
# sound like" reference.
#
# This list is the single source of truth: server.py serves it to the UI and
# tools/voice_preview.py imports it, so there is exactly one place to edit.
VOICES = [
    {"id": "en-US-AvaMultilingualNeural", "name": "Ava", "gender": "female",
     "accent": "American", "character": "Bright, expressive, lively"},
    {"id": "en-US-EmmaMultilingualNeural", "name": "Emma", "gender": "female",
     "accent": "American", "character": "Warm and even — the steady one"},
    {"id": "en-GB-SoniaNeural", "name": "Sonia", "gender": "female",
     "accent": "British", "character": "Composed, understated"},
    {"id": "en-US-JennyNeural", "name": "Jenny", "gender": "female",
     "accent": "American", "character": "Friendly, familiar, neutral"},
    {"id": "en-US-AndrewMultilingualNeural", "name": "Andrew", "gender": "male",
     "accent": "American", "character": "Relaxed, conversational, low-key"},
    {"id": "en-US-BrianMultilingualNeural", "name": "Brian", "gender": "male",
     "accent": "American", "character": "Casual, easy pacing"},
    {"id": "en-GB-RyanNeural", "name": "Ryan", "gender": "male",
     "accent": "British", "character": "Least robotic, occasionally over-stresses a word"},
    {"id": "en-US-AriaNeural", "name": "Aria", "gender": "female",
     "accent": "American", "character": "AURA's old voice — kept for comparison"},
]

VOICE_IDS = {v["id"] for v in VOICES}

# What a voice says when you press play in Settings — she introduces herself,
# so you're judging the voice as AURA rather than as a neutral sample.
PREVIEW_LINE = ("Hi, I'm AURA. This is how I'll sound when I talk to you.")


def resolve_voice(tone: str = "normal") -> str:
    """The voice AURA should speak with right now.

    Precedence, most specific first:
      1. `voice.name` in app_settings — what the Settings picker writes. It
         wins because it is the control the user can actually see.
      2. AURA_TTS_VOICE / AURA_TTS_VOICE_<TONE> in .env — for anyone who
         prefers configuring by file.
      3. FALLBACK_VOICE.

    Resolved per utterance rather than frozen at import, so changing the voice
    in Settings takes effect on the next thing she says — no restart.
    """
    # .strip() again here rather than trusting the caller: a settings row of
    # "   " must mean "not chosen", not a voice named three spaces (which
    # edge-tts would reject and AURA would go silent on).
    chosen = str(_voice_settings().get("name") or "").strip()
    if chosen:
        return chosen
    return (VOICE_MAP.get(tone) or DEFAULT_VOICE or FALLBACK_VOICE)

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

# ── User voice settings (Sanctuary → Voice) ───────────────────────────────────
# These live in the app_settings table and were previously saved but never
# read, so the sliders did nothing. Cached briefly because speak() can be
# called several times in quick succession and each read hits sqlite.
_settings_cache: tuple[float, dict] = (0.0, {})
# 2s, not 10s: this cache is what the chat dock's speak on/off switch has to
# get past, and a 10-second lag made the toggle feel broken.
_SETTINGS_TTL = 2.0  # seconds


def _voice_settings() -> dict:
    """{'enabled': bool, 'rate_pct': int, 'name': str}. Falls back to
    on/neutral/unset — an unset name means "fall through to .env or the
    default", never "go silent"."""
    import time as _t
    global _settings_cache
    now = _t.time()
    ts, cached = _settings_cache
    if cached and (now - ts) < _SETTINGS_TTL:
        return cached
    out = {"enabled": True, "rate_pct": 55, "name": ""}
    try:
        from memory import store
        s = store.get_settings()
        out["enabled"] = bool(s.get("voice.enabled", True))
        out["rate_pct"] = int(s.get("voice.rate", 55))
        name = s.get("voice.name") or ""
        out["name"] = str(name).strip()
    except Exception:  # noqa: BLE001
        pass  # settings unavailable → speak normally rather than going silent
    _settings_cache = (now, out)
    return out


def _rate_offset(rate_pct: int, tone_rate: str) -> str:
    """Fold the user's 0–100 speed preference into the tone's own rate shift.

    55 is the stored default and means "leave the tone alone"; the ends of the
    slider map to roughly -40%..+40% on top of it.
    """
    try:
        base = int(tone_rate.rstrip("%"))
    except ValueError:
        base = 0
    user = round((max(0, min(100, rate_pct)) - 55) * 0.8)
    total = max(-50, min(50, base + user))
    return f"{total:+d}%"


# ── TTS generation ────────────────────────────────────────────────────────────
async def _generate(text: str, tone: str, path: str, voice: str | None = None):
    if edge_tts is None:
        raise RuntimeError("edge_tts is not installed")

    # `voice` is only passed by the Settings preview, which has to render a
    # voice the user has NOT chosen yet. Everything else resolves live, so a
    # change in the picker applies to the very next thing AURA says.
    voice = voice or resolve_voice(tone)
    settings = TONE_SETTINGS.get(tone, TONE_SETTINGS["normal"])
    communicate = edge_tts.Communicate(
        text,
        voice=voice,
        rate=_rate_offset(_voice_settings()["rate_pct"], settings["rate"]),
        pitch=settings["pitch"]
    )
    await communicate.save(path)


def render_preview(voice: str, text: str | None = None) -> bytes:
    """Synthesise a sample of `voice` and return the mp3 bytes.

    Used by the Settings picker so you can hear a voice before committing to
    it. Returns the audio to the caller rather than playing it through pygame:
    the browser does the playing, which keeps the preview off the same mixer
    AURA speaks through (no fighting over the audio lock, no preview cutting
    off something she was mid-way through saying).
    """
    if voice not in VOICE_IDS:
        raise ValueError(f"unknown voice: {voice}")
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            tmp_path = f.name
        asyncio.run(_generate(text or PREVIEW_LINE, "normal", tmp_path, voice=voice))
        with open(tmp_path, "rb") as fh:
            return fh.read()
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

# ── Synthesis / playback, split ───────────────────────────────────────────────
# These used to be one function, which is what made AURA's voice lag so far
# behind her text. edge_tts is a NETWORK call to Microsoft — roughly half a
# second to two seconds per chunk — and speak_chunks ran it inline, so chunk 2
# only started synthesising after chunk 1 had finished *playing*. The text was
# on screen long before the audio caught up. Splitting them lets the next
# chunk render while the current one is still speaking (see speak_chunks).

def _synth(text: str) -> str | None:
    """Render `text` to a temp mp3 and return its path (None on failure).
    Safe to run concurrently — each call writes its own file and never
    touches the mixer."""
    if edge_tts is None:
        print("[AURA TTS Error] edge_tts is not installed")
        return None
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            tmp_path = f.name
        asyncio.run(_generate(text, detect_tone(text), tmp_path))
        return tmp_path
    except Exception as e:  # noqa: BLE001
        print(f"[AURA TTS Error] synth: {e}")
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return None


def _play(path: str) -> None:
    """Play a rendered mp3 and delete it. Serialized: the mixer's music
    channel is global, so only one thread may load/play/unload it at a
    time (see _audio_lock)."""
    if pygame is None:
        print("[AURA TTS Error] pygame is not installed")
        return
    try:
        with _audio_lock:
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                pygame.mixer.music.load(path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.time.wait(20)
                pygame.mixer.music.unload()
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass
    except Exception as e:  # noqa: BLE001
        print(f"[AURA TTS Error] play: {e}")


def prewarm() -> None:
    """Initialise the mixer up front. The first mixer.init() costs a few
    hundred ms on Windows, and paying it on the first spoken word made the
    opening line land noticeably late."""
    if pygame is None:
        return
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
    except Exception as e:  # noqa: BLE001
        print(f"[AURA TTS] mixer prewarm skipped: {e}")


# ── Main speak function ───────────────────────────────────────────────────────
def speak(text: str):
    clean = clean_text(text)
    if not clean:
        return

    # Voice off (Sanctuary → Voice) means don't synthesise — but still print,
    # so the console transcript and the chat window stay complete.
    if not _voice_settings()["enabled"]:
        print(f"[AURA] {clean}  (voice off)")
        return

    print(f"[AURA] {clean}")
    path = _synth(clean)
    if path:
        _play(path)


# ── speak_chunks for speech planner ──────────────────────────────────────────
def speak_chunks(chunks):
    """Speak planned chunks with the NEXT one already rendering.

    While chunk i plays, chunk i+1 is synthesised on a worker thread, so the
    only network wait the user ever hears is the one before the very first
    word. Pauses are honoured as before.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor

    chunks = list(chunks)
    if not chunks:
        return

    # Read the toggle ONCE per utterance: flipping voice off mid-sentence
    # shouldn't leave half the chunks rendered and half silent.
    if not _voice_settings()["enabled"]:
        for chunk in chunks:
            cleaned = clean_text(chunk.text)
            if cleaned:
                print(f"[AURA] {cleaned}  (voice off)")
        return

    with ThreadPoolExecutor(max_workers=2) as pool:
        cleaned = [clean_text(c.text) for c in chunks]
        # Kick the first render off immediately — nothing to overlap it with.
        pending = pool.submit(_synth, cleaned[0]) if cleaned[0] else None

        for i, chunk in enumerate(chunks):
            # Start the NEXT render before playing this one, so the network
            # round-trip overlaps the audio instead of following it.
            nxt = None
            if i + 1 < len(chunks) and cleaned[i + 1]:
                nxt = pool.submit(_synth, cleaned[i + 1])

            if chunk.pause_before > 0:
                time.sleep(chunk.pause_before)

            if cleaned[i]:
                print(f"[AURA] {cleaned[i]}")
                path = pending.result() if pending is not None else None
                if path:
                    _play(path)

            if chunk.pause_after > 0:
                time.sleep(chunk.pause_after)

            pending = nxt
