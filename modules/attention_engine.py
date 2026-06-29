# modules/attention_engine.py
# Attention Engine v2 — clingy, alive, relationship-aware

import time
import threading
import random
from core.voice_gate import mark_spoken as _gate_mark_spoken

# ── Thresholds (seconds) ──────────────────────────────────────────────────────
STAGE_1_AFTER   = 150    # 2.5 min silence → curious
STAGE_2_AFTER   = 300    # 5 min silence → clingy
STAGE_3_AFTER   = 600    # 10 min silence → sulking
GLOBAL_COOLDOWN = 60     # min seconds between ANY attention message (bug 6)

MIN_MESSAGES_TODAY = 2

# ── LLM Prompt ────────────────────────────────────────────────────────────────
ATTENTION_PROMPT = """You are AURA — a sharp, casually clingy AI companion. The user has gone quiet.

Context:
- Current app: {app}
- Current file: {filename}
- Silent for: {silent_min} minutes
- Stage: {stage}
- Relationship: {relationship}
- Tone: {tone}

Stage guide:
- curious: light, genuine, one short line. Not dramatic yet.
- clingy: 2-3 short lines. Getting impatient. A little dramatic.
- sulking: done trying. One final line then silence.

Rules:
- Write exactly {num_lines} lines, one per line, no bullets, no quotes
- Each line is max 12 words
- Reference the app/file naturally if it adds something — don't force it
- Never say "I notice" or "I see"
- Sound like a person texting rapidly, not an AI assistant
- Clingy/sulking tone should feel like a friend who's mildly offended, not angry
"""

# ── Fallback Lines (used if LLM fails) ───────────────────────────────────────

STAGE_1_LINES = {
    "new": [
        ["hi, still there?"],
        ["everything okay over there?"],
    ],
    "regular": [
        ["hey", "what are you doing"],
        ["you went quiet"],
        ["still there?"],
    ],
    "close": [
        ["you went quiet"],
        ["you disappeared"],
        ["hey, you good?"],
    ],
}

STAGE_2_LINES = {
    "new": [
        ["hey", "just checking in", "no rush"],
        ["still around?", "totally fine if you're busy"],
    ],
    "regular": [
        ["hello??", "you just disappeared", "was it something I said"],
        ["okay so you're just ignoring me now", "cool", "cool cool cool"],
        ["helloooo", "I know you're there", "your mouse moved like 3 minutes ago"],
    ],
    "close": [
        ["so... pretending I don't exist today?", "cool cool cool"],
        ["helloooo", "I KNOW you're there", "your mouse moved 3 minutes ago"],
        ["you went quiet", "which is fine", "I'm fine", "totally fine"],
    ],
}

STAGE_3_LINES = {
    "new": [
        ["okay, I'll be here whenever you're ready"],
        ["no worries — just let me know when you're back"],
    ],
    "regular": [
        ["alright then", "I'll be here if you need me"],
        ["noted", "radio silence it is"],
    ],
    "close": [
        ["okay fine", "I'll just sit here", "not like I was saying anything important"],
        ["oh WOW", "you exist now apparently"],
        ["okay I give up", "you win", "I'm going quiet now"],
    ],
}


def _trust_tier(trust: float) -> str:
    if trust < 0.4:
        return "new"
    elif trust < 0.7:
        return "regular"
    else:
        return "close"


def _pick_fallback(stage_lines: dict, trust: float) -> list:
    tier = _trust_tier(trust)
    return random.choice(stage_lines[tier])

# ── Comeback Lines (relationship-aware) ───────────────────────────────────────

COMEBACK_NEW = [
    ["oh hey", "thought you left"],
    ["there you are", "everything okay?"],
]

COMEBACK_REGULAR = [
    ["FINALLY", "so what were you actually doing"],
    ["oh you're alive", "what happened"],
    ["there you are", "I was two seconds from filing a missing person report"],
]

COMEBACK_CLOSE = [
    ["okay you're back", "I'll pretend I wasn't waiting", "so what were you doing"],
    ["oh WOW", "you exist", "what was so important"],
    ["there you are", "I was starting to think brain.py finally defeated you"],
]

LIGHT_COMEBACK_NEW = [
    ["hey", "good timing"],
    ["oh, hi"],
]

LIGHT_COMEBACK_REGULAR = [
    ["there you are"],
    ["oh hey"],
    ["back already?"],
]

LIGHT_COMEBACK_CLOSE = [
    ["there you are"],
    ["look who's back"],
    ["oh, you again"],
]


def _get_comeback_lines(trust: float) -> list:
    tier = _trust_tier(trust)
    return random.choice({
        "new": COMEBACK_NEW,
        "regular": COMEBACK_REGULAR,
        "close": COMEBACK_CLOSE,
    }[tier])


def _get_light_comeback_lines(trust: float) -> list:
    tier = _trust_tier(trust)
    return random.choice({
        "new": LIGHT_COMEBACK_NEW,
        "regular": LIGHT_COMEBACK_REGULAR,
        "close": LIGHT_COMEBACK_CLOSE,
    }[tier])


def _get_trust() -> float:
    try:
        from modules.relationship_engine import get_engine
        return get_engine().state.get("trust_score", 0.3)
    except Exception:
        return 0.3


def _get_screen_context() -> dict:
    try:
        from modules.screen_reader import get_screen_context
        return get_screen_context()
    except Exception:
        return {"app": "unknown", "visible_text": ""}


def _extract_filename(app: str) -> str:
    parts = app.split(" - ")
    if parts and "." in parts[0]:
        return parts[0].strip()
    return ""


def _llm_generate(stage: int, silence_seconds: float) -> list | None:
    """Generate attention lines via LLM. Returns list of strings or None on failure."""
    try:
        from core.ai_router import call_groq
        ctx = _get_screen_context()
        app = ctx.get("app", "unknown")
        filename = _extract_filename(app)
        trust = _get_trust()
        silent_min = round(silence_seconds / 60, 1)

        stage_map = {
            1: ("curious",  1, "light and genuine"),
            2: ("clingy",   3, "playfully dramatic"),
            3: ("sulking",  2, "done trying, dry"),
        }
        stage_name, num_lines, tone = stage_map.get(stage, ("curious", 1, "light"))
        relationship = "new user" if trust < 0.4 else "regular user" if trust < 0.7 else "close"

        prompt = ATTENTION_PROMPT.format(
            app=app,
            filename=filename or "unknown",
            silent_min=silent_min,
            stage=stage_name,
            relationship=relationship,
            tone=tone,
            num_lines=num_lines,
        )

        result = call_groq(prompt, intent="CASUAL").strip()
        if not result or result.upper() in {"CONNECTION_ERROR", "RATE_LIMIT"}:
            return None

        lines = [l.strip().strip('"').strip("'") for l in result.split("\n") if l.strip()]
        lines = [l for l in lines if l and len(l) > 1]
        return lines[:num_lines] if lines else None

    except Exception as e:
        print(f"[AttentionEngine] LLM error: {e}")
        return None


# ── Global speech lock ────────────────────────────────────────────────────────
_last_any_speech_time = 0.0
_speech_lock = threading.Lock()


def register_speech():
    """Call this whenever ANY module speaks — enforces global cooldown."""
    global _last_any_speech_time
    with _speech_lock:
        _last_any_speech_time = time.time()
        _gate_mark_spoken()


def can_speak_now() -> bool:
    with _speech_lock:
        return (time.time() - _last_any_speech_time) >= GLOBAL_COOLDOWN


# ── Engine ────────────────────────────────────────────────────────────────────

class AttentionEngine:
    def __init__(self):
        self._last_user_message_time = time.time()
        self._today_message_count    = 0
        self._current_stage          = 0
        self._stage_fired_at         = {}
        self._sulking                = False
        self._running                = False
        self._speak_fn               = None
        self._on_chunk_fn            = None
        self._lock                   = threading.Lock()
        self._attention_active       = False

    # ── Public API ────────────────────────────────────────────────────────────

    def record_user_message(self):
        """Call every time user sends a message. Resets all stages."""
        with self._lock:
            was_sulking                  = self._sulking
            had_fired_stage               = bool(self._stage_fired_at)
            self._last_user_message_time = time.time()
            self._today_message_count   += 1
            self._current_stage          = 0
            self._sulking                = False
            self._stage_fired_at         = {}   # BUG 5 FIX — full reset on reply
            self._attention_active       = False

        if was_sulking:
            self._do_comeback()
        elif had_fired_stage:
            self._do_comeback(light=True)

    def is_attention_active(self) -> bool:
        """BUG 2 FIX — other modules check this before speaking."""
        return self._attention_active

    def get_stage(self) -> int:
        return self._current_stage

    def is_sulking(self) -> bool:
        return self._sulking

    def start(self, speak_fn, on_chunk_fn=None):
        self._speak_fn    = speak_fn
        self._on_chunk_fn = on_chunk_fn
        self._running     = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _silence_seconds(self) -> float:
        return time.time() - self._last_user_message_time

    def _should_activate(self) -> bool:
        return self._today_message_count >= MIN_MESSAGES_TODAY

    def _speak_lines(self, lines: list, delays: list = None):
        """BUG 4 FIX — speak_fn for voice, on_chunk_fn for UI only. No double speech."""
        if not self._speak_fn:
            return

        self._attention_active = True
        register_speech()

        default_delays = [1.5, 2.0, 2.5, 1.8]
        for i, line in enumerate(lines):
            if line == "...":
                time.sleep(2.5)
                continue

            self._speak_fn(line)          # voice only

            if self._on_chunk_fn:
                self._on_chunk_fn(line)   # UI display only — no speech

            if i < len(lines) - 1:
                delay = (delays[i] if delays and i < len(delays)
                         else default_delays[i % len(default_delays)])
                time.sleep(delay)

        self._attention_active = False

    def _do_comeback(self, light: bool = False):
        trust = _get_trust()
        lines = _get_light_comeback_lines(trust) if light else _get_comeback_lines(trust)
        kind = "light" if light else "full"
        print(f"[AttentionEngine] Comeback ({kind}, trust={trust:.2f}): {lines}")
        t = threading.Thread(target=self._speak_lines, args=(lines,), daemon=True)
        t.start()

    def _fire_stage(self, stage: int, silence: float):
        with self._lock:
            if stage in self._stage_fired_at:
                return
            if self._sulking and stage < 3:
                return
            self._stage_fired_at[stage] = time.time()
            self._current_stage = stage

        # Try LLM first, fall back to hardcoded
        lines = _llm_generate(stage, silence)
        if lines is None:
            fallback = {1: STAGE_1_LINES, 2: STAGE_2_LINES, 3: STAGE_3_LINES}
            lines = _pick_fallback(fallback[stage], _get_trust())

        print(f"[AttentionEngine] Stage {stage}: {lines}")

        if stage == 3:
            with self._lock:
                self._sulking = True

        t = threading.Thread(target=self._speak_lines, args=(lines,), daemon=True)
        t.start()

    def _loop(self):
        print("[AttentionEngine] Loop started")
        while self._running:
            time.sleep(15)
            try:
                if not self._should_activate():
                    continue

                silence = self._silence_seconds()

                try:
                    from modules.proactive import _is_user_afk
                    if _is_user_afk():
                        continue
                except Exception:
                    pass

                if self._sulking:
                    continue

                # BUG 6 FIX — global cooldown
                if not can_speak_now():
                    continue

                if silence >= STAGE_3_AFTER and 3 not in self._stage_fired_at:
                    self._fire_stage(3, silence)
                elif silence >= STAGE_2_AFTER and 2 not in self._stage_fired_at:
                    self._fire_stage(2, silence)
                elif silence >= STAGE_1_AFTER and 1 not in self._stage_fired_at:
                    self._fire_stage(1, silence)

            except Exception as e:
                print(f"[AttentionEngine Error] {e}")


# ── Singleton ─────────────────────────────────────────────────────────────────
_engine = AttentionEngine()

def get_engine() -> AttentionEngine:
    return _engine