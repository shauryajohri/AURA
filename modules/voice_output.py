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

# ── AURA's voices ─────────────────────────────────────────────────────────────
# edge-tts voices live on Microsoft's servers — there is no model to download
# and no file to manage, so the voice is just a name string.
#
# AURA has ONE character (flirty, strict, nerdy — see core/persona.py) and two
# voices that carry it, picked by ear from a wider audition: Ava for the
# playful side, Sonia for the strict side. Each comes with its own tuning — a
# touch slower and lower than stock, which is the difference between a
# newsreader and someone teasing you. The tuning belongs to the voice and
# never changes mid-reply: shifting pitch per line is what made her sound like
# several different robots taking turns.
#
# This list is the single source of truth: server.py serves it to the UI and
# tools/voice_preview.py imports it, so there is exactly one place to edit.
# Override per install with AURA_TTS_VOICE in .env; a voice outside this list
# speaks with stock tuning.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv()
except Exception:  # noqa: BLE001 — .env is optional; the default still works
    pass

VOICES = [
    {"id": "en-US-AvaMultilingualNeural", "name": "Ava", "gender": "female",
     "accent": "American", "character": "Playful and warm — the tease lands",
     "rate": "-6%", "pitch": "-6Hz"},
    {"id": "en-GB-SoniaNeural", "name": "Sonia", "gender": "female",
     "accent": "British", "character": "Crisp and composed — the strict one",
     "rate": "-4%", "pitch": "-2Hz"},
]

VOICE_IDS = {v["id"] for v in VOICES}

FALLBACK_VOICE = VOICES[0]["id"]
DEFAULT_VOICE = os.getenv("AURA_TTS_VOICE") or FALLBACK_VOICE

_STOCK = {"rate": "+0%", "pitch": "+0Hz"}

# What a voice says when you press play in Settings — she introduces herself,
# so you're judging the voice as AURA rather than as a neutral sample.
PREVIEW_LINE = ("Hi, I'm AURA. I'm sharp, I'm a little bit of a nerd, and I "
                "don't let you slack off. Lucky for you, I happen to like you.")


def prosody(voice: str) -> dict:
    """{'rate', 'pitch'} for `voice`: its own tuning, or stock if it's not
    one of AURA's."""
    for v in VOICES:
        if v["id"] == voice:
            return {"rate": v["rate"], "pitch": v["pitch"]}
    return dict(_STOCK)


def resolve_voice() -> str:
    """The voice AURA should speak with right now.

    Precedence, most specific first:
      1. `voice.name` in app_settings — what the Settings picker writes. It
         wins because it is the control the user can actually see.
      2. AURA_TTS_VOICE in .env — for anyone who prefers configuring by file.
      3. FALLBACK_VOICE.

    A saved name that isn't in VOICES (a pick from the old, longer roster) is
    ignored rather than honoured, so the picker always shows what she's
    actually using.

    Resolved per utterance rather than frozen at import, so changing the voice
    in Settings takes effect on the next thing she says — no restart.
    """
    # .strip() again here rather than trusting the caller: a settings row of
    # "   " must mean "not chosen", not a voice named three spaces.
    chosen = str(_voice_settings().get("name") or "").strip()
    if chosen in VOICE_IDS:
        return chosen
    return DEFAULT_VOICE or FALLBACK_VOICE

# ── Text cleaner ──────────────────────────────────────────────────────────────
# Sentence ends only — splitting on every "." read "Python 3.12" as "Python
# three. Twelve." and dropped the "?" off questions.
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
# The voice reads emoji out by name — a wink in the text became "smirking
# face" in her mouth. Same set web_api._speakable strips.
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")


def clean_text(text: str, max_sentences: int | None = 2) -> str:
    """Make `text` speakable. `max_sentences=None` keeps every sentence —
    speak_chunks uses that, since a chunk is already a slice of a reply the
    planner has sized."""
    text = re.sub(r'(?<=\w)_(?=\w)', ' ', text)   # snake_case → "snake case"
    text = re.sub(r'\*\*|__|\*|_|~~|`', '', text)
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'[#\[\]{}|<>]', '', text)
    text = re.sub(r'\[You might also.*?\]', '', text, flags=re.DOTALL)
    text = re.sub(r'Anticipated Follow-up.*', '', text, flags=re.DOTALL)
    text = re.sub(r'aura:', '', text, flags=re.IGNORECASE)
    text = re.sub(r'User asks:.*', '', text, flags=re.DOTALL)
    text = re.sub(r'Screen content:.*', '', text, flags=re.DOTALL)
    text = re.sub(r'"', '', text)
    text = _EMOJI.sub('', text)
    text = re.sub(r'\s+', ' ', text).strip()
    sentences = [s for s in _SENTENCE_END.split(text) if s]
    if max_sentences:
        sentences = sentences[:max_sentences]
    text = ' '.join(sentences).strip()
    # Close an open sentence so it lands, but leave a clause that ends on a
    # comma alone: a full stop there drops her voice mid-thought.
    if text and text[-1].isalnum():
        text += '.'
    return text

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


def _rate_offset(rate_pct: int, voice_rate: str) -> str:
    """Fold the user's 0–100 speed preference into the voice's own rate.

    55 is the stored default and means "leave the voice alone"; the ends of
    the slider map to roughly -40%..+40% on top of it.
    """
    try:
        base = int(voice_rate.rstrip("%"))
    except ValueError:
        base = 0
    user = round((max(0, min(100, rate_pct)) - 55) * 0.8)
    total = max(-50, min(50, base + user))
    return f"{total:+d}%"


# ── TTS generation ────────────────────────────────────────────────────────────
async def _generate(text: str, path: str, voice: str | None = None):
    if edge_tts is None:
        raise RuntimeError("edge_tts is not installed")

    # `voice` is only passed by the Settings preview, which has to render a
    # voice the user has NOT chosen yet. Everything else resolves live, so a
    # change in the picker applies to the very next thing AURA says.
    voice = voice or resolve_voice()
    tune = prosody(voice)
    communicate = edge_tts.Communicate(
        text,
        voice=voice,
        rate=_rate_offset(_voice_settings()["rate_pct"], tune["rate"]),
        pitch=tune["pitch"]
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
        asyncio.run(_generate(text or PREVIEW_LINE, tmp_path, voice=voice))
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
        asyncio.run(_generate(text, tmp_path))
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
            cleaned = clean_text(chunk.text, max_sentences=None)
            if cleaned:
                print(f"[AURA] {cleaned}  (voice off)")
        return

    with ThreadPoolExecutor(max_workers=2) as pool:
        cleaned = [clean_text(c.text, max_sentences=None) for c in chunks]
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
