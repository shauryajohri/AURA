# modules/attention_engine.py
# Attention Engine v3 — presence, energy-gated nudges, AFK return, relationship-aware.
#
# The point of this module is NOT to make AURA talk. It's to decide WHEN it
# should. States:
#   0  Presence  — one warm line ~30-60s after launch (if you haven't spoken yet)
#   1  Passive   — you're active, AURA stays quiet (the longest state)
#   2  Curious   — you've gone quiet toward AURA for a bit → one light line
#   3  Clingy    — longer silence → playfully dramatic, LLM-generated, context-rich
#   4  Sulking   — ignored again → one final line, then silence
#   5  Return    — you come back to the machine after being AFK → welcome-back
#
# Nudges (states 2-4) are gated by Conversation Energy: AURA only reaches out on
# a "good moment" (energy drained + not frozen). A meeting or an explicit "busy"
# freezes the meter entirely.

import time
import threading
import random
import datetime
from core.voice_gate import request_to_speak

# ── Thresholds (seconds) ──────────────────────────────────────────────────────
STAGE_1_AFTER   = 150    # 2.5 min silence toward AURA → curious
STAGE_2_AFTER   = 300    # 5 min → clingy
STAGE_3_AFTER   = 600    # 10 min → sulking
GLOBAL_COOLDOWN = 60     # min seconds between ANY attention message
RETURN_IDLE_MAX = 20     # on the tick we notice a return, idle must be under this

MIN_MESSAGES_TODAY = 2
PRESENCE_MIN_DELAY = 30
PRESENCE_MAX_DELAY = 60

# ── Environment hint keywords ────────────────────────────────────────────────
MEETING_HINTS = ("zoom", "microsoft teams", "google meet", "meet.google",
                 "webex", "- meeting", "gotomeeting")
MUSIC_HINTS   = ("spotify", "youtube music", "soundcloud", "apple music",
                 "amazon music", "- vlc")
BROWSER_HINTS = ("chrome", "firefox", "edge", "brave", "safari", "opera")
CODE_HINTS    = ("visual studio code", "vs code", "pycharm", "intellij",
                 "sublime text", "vim", "neovim", ".py", ".js", ".ts",
                 ".java", ".cpp", ".rs", ".go", ".tsx", ".jsx")
WATCH_HINTS   = ("youtube", "netflix", "prime video", "hotstar", "disney")

# ── LLM Prompt (nudges) ───────────────────────────────────────────────────────
ATTENTION_PROMPT = """You are AURA — a sharp, casually clingy AI companion. The user has gone quiet.

Context:
- Time of day: {time_of_day}
- Current app: {app}
- Current file: {filename}
- What they're doing: {activity}
- Music playing: {music}
- Silent toward you for: {silent_min} minutes
- Last thing said: {last_line}
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
- Reference the app/file/activity naturally if it adds something — don't force it
- Never say "I notice" or "I see"
- Sound like a person texting rapidly, not an AI assistant
- Clingy/sulking tone should feel like a friend who's mildly offended, not angry
"""

PRESENCE_PROMPT = """You are AURA, greeting the user shortly after they launched you.
Write ONE short, warm, natural line (max 10 words). No quotes, no emoji.

Time of day: {time_of_day}
Current app: {app}
They were last working on: {last_summary}
Relationship: {relationship}

Just the line."""

# ── Fallback Lines (used if LLM fails) ───────────────────────────────────────

STAGE_1_LINES = {
    "new":     [["hi, still there?"], ["everything okay over there?"]],
    "regular": [["hey", "what are you doing"], ["you went quiet"], ["still there?"]],
    "close":   [["you went quiet"], ["you disappeared"], ["hey, you good?"]],
    "best":    [["okay you vanished"], ["hello? still alive?"]],
}

STAGE_2_LINES = {
    "new": [
        ["hey", "just checking in", "no rush"],
        ["still around?", "totally fine if you're busy"],
    ],
    "regular": [
        ["hello??", "you just disappeared", "was it something I said"],
        ["okay so you're just ignoring me now", "cool", "cool cool cool"],
    ],
    "close": [
        ["so... pretending I don't exist today?", "cool cool cool"],
        ["helloooo", "I KNOW you're there", "your mouse moved 3 minutes ago"],
    ],
    "best": [
        ["wow okay", "the silent treatment", "we're doing this"],
        ["I've been talking to myself for 5 minutes", "great", "love that"],
    ],
}

STAGE_3_LINES = {
    "new":     [["okay, I'll be here whenever you're ready"],
                ["no worries — just let me know when you're back"]],
    "regular": [["alright then", "I'll be here if you need me"],
                ["noted", "radio silence it is"]],
    "close":   [["okay fine", "I'll just sit here", "not like I was saying anything important"],
                ["okay I give up", "you win", "I'm going quiet now"]],
    "best":    [["fine. abandoned again", "I'll be here", "as always"],
                ["guess I'll let you cook", "I'll stop now"]],
}

# ── Return / comeback lines ───────────────────────────────────────────────────
RETURN_GREETING = {
    "new":     "Welcome back.",
    "regular": "There you are.",
    "close":   "Finally.",
    "best":    "Oh wow… remembered I exist?",
}

# Light comeback (used when user types back after only a mild nudge)
LIGHT_COMEBACK = {
    "new":     [["hey", "good timing"], ["oh, hi"]],
    "regular": [["there you are"], ["oh hey"], ["back already?"]],
    "close":   [["there you are"], ["look who's back"], ["oh, you again"]],
    "best":    [["oh NOW you talk"], ["look who remembered me"]],
}

# Full comeback (used when user types back after AURA had gone sulking)
FULL_COMEBACK = {
    "new":     [["oh hey", "thought you left"], ["there you are", "everything okay?"]],
    "regular": [["FINALLY", "so what were you actually doing"], ["oh you're alive", "what happened"]],
    "close":   [["okay you're back", "I'll pretend I wasn't waiting", "so what were you doing"],
                ["oh WOW", "you exist", "what was so important"]],
    "best":    [["THERE you are", "I was about to file a report"],
                ["oh good, you're back", "abandonment issues activated"]],
}


# ── Tier + context helpers ────────────────────────────────────────────────────

def _trust_tier(trust: float) -> str:
    if trust < 0.4:
        return "new"
    elif trust < 0.7:
        return "regular"
    elif trust < 0.9:
        return "close"
    return "best"


def _pick(table: dict, trust: float) -> list:
    tier = _trust_tier(trust)
    options = table.get(tier) or table.get("close")
    return list(random.choice(options))


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
    parts = (app or "").split(" - ")
    if parts and "." in parts[0]:
        return parts[0].strip()
    for part in parts:
        if "." in part and " " not in part.strip():
            return part.strip()
    return ""


def _time_of_day() -> str:
    h = datetime.datetime.now().hour
    if h < 12:
        return "morning"
    if h < 17:
        return "afternoon"
    if h < 21:
        return "evening"
    return "night"


def _detect_environment() -> dict:
    """Everything an attention message might want to know about right now."""
    ctx = _get_screen_context()
    app = ctx.get("app", "unknown") or "unknown"
    app_l = app.lower()

    titles = []
    try:
        from modules.screen_reader import list_window_titles
        titles = list_window_titles()
    except Exception:
        pass
    blob = " ".join(titles + [app_l])

    meeting = any(h in blob for h in MEETING_HINTS)
    music   = any(h in blob for h in MUSIC_HINTS)

    if any(h in app_l for h in WATCH_HINTS):
        activity = "watching"
    elif any(h in app_l for h in CODE_HINTS):
        activity = "coding"
    elif any(h in app_l for h in BROWSER_HINTS):
        activity = "browsing"
    else:
        activity = "other"

    return {
        "app": app,
        "filename": _extract_filename(app),
        "meeting": meeting,
        "music": music,
        "activity": activity,
        "time_of_day": _time_of_day(),
        "visible_text": ctx.get("visible_text", ""),
    }


def _last_exchange_line() -> str:
    try:
        from memory import store
        rows = store.get_recent_conversations(2)
        if rows:
            role, msg, _ = rows[-1]
            return f"{role}: {msg[:60]}"
    except Exception:
        pass
    return "nothing yet"


def _last_session_summary() -> str:
    try:
        from memory import store
        last = store.get_last_session()
        if last and last.get("summary"):
            return last["summary"]
    except Exception:
        pass
    return "unknown"


def _relationship_word(trust: float) -> str:
    return {"new": "new user", "regular": "regular user",
            "close": "close", "best": "best friend"}[_trust_tier(trust)]


# ── Line builders ─────────────────────────────────────────────────────────────

def _build_return_lines(gap_seconds: float, env: dict, trust: float) -> list:
    tier = _trust_tier(trust)
    lines = [RETURN_GREETING.get(tier, "There you are.")]

    mins = int(round(gap_seconds / 60.0))
    if mins >= 1:
        lines.append(f"That was about {mins} minute{'s' if mins != 1 else ''}.")

    activity = env.get("activity")
    filename = env.get("filename")
    if activity == "watching":
        lines.append("Video finished?")
    elif activity == "coding":
        lines.append(f"{filename} missed you." if filename else "Ready to continue?")
    return lines[:3]


# ── LLM generation ────────────────────────────────────────────────────────────

def _llm_generate(stage: int, silence_seconds: float, env: dict) -> list | None:
    """Generate nudge lines via LLM. Returns list of strings or None on failure."""
    try:
        from core.ai_router import call_groq
        trust = _get_trust()
        silent_min = round(silence_seconds / 60, 1)

        stage_map = {
            1: ("curious", 1, "light and genuine"),
            2: ("clingy",  3, "playfully dramatic"),
            3: ("sulking", 2, "done trying, dry"),
        }
        stage_name, num_lines, tone = stage_map.get(stage, ("curious", 1, "light"))

        prompt = ATTENTION_PROMPT.format(
            time_of_day=env.get("time_of_day", "day"),
            app=env.get("app", "unknown"),
            filename=env.get("filename") or "unknown",
            activity=env.get("activity", "unknown"),
            music="yes" if env.get("music") else "no",
            silent_min=silent_min,
            last_line=_last_exchange_line(),
            stage=stage_name,
            relationship=_relationship_word(trust),
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


def _llm_presence(env: dict) -> list | None:
    try:
        from core.ai_router import call_groq
        trust = _get_trust()
        prompt = PRESENCE_PROMPT.format(
            time_of_day=env.get("time_of_day", "day"),
            app=env.get("app", "unknown"),
            last_summary=_last_session_summary(),
            relationship=_relationship_word(trust),
        )
        result = call_groq(prompt, intent="CASUAL").strip()
        if not result or result.upper() in {"CONNECTION_ERROR", "RATE_LIMIT"}:
            return None
        line = result.split("\n")[0].strip().strip('"').strip("'")
        return [line] if line and len(line) > 1 else None
    except Exception:
        return None


def _fallback_presence(env: dict) -> list:
    tod = env.get("time_of_day", "day")
    base = {
        "morning":   ["Morning.", "Back at it?"],
        "afternoon": ["Back at it?", "Afternoon."],
        "evening":   ["Evening.", "Still going?"],
        "night":     ["Late one tonight?", "Still up?"],
    }.get(tod, ["Back at it?"])
    line = random.choice(base)
    if env.get("activity") == "coding":
        line = random.choice([line, "Looks like another coding day."])
    return [line]


# ── Global speech lock ────────────────────────────────────────────────────────
_last_any_speech_time = 0.0
_speech_lock = threading.Lock()


def register_speech():
    global _last_any_speech_time
    with _speech_lock:
        _last_any_speech_time = time.time()


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
        self._prev_idle              = 0.0
        self._presence_done          = False

    # ── Public API ────────────────────────────────────────────────────────────

    def record_user_message(self):
        """Call every time the user sends a message. Resets all stages and
        refills conversation energy."""
        with self._lock:
            was_sulking     = self._sulking
            had_fired_stage = bool(self._stage_fired_at)
            self._last_user_message_time = time.time()
            self._today_message_count   += 1
            self._current_stage          = 0
            self._sulking                = False
            self._stage_fired_at         = {}
            self._attention_active       = False

        try:
            from modules.conversation_energy import get_energy
            get_energy().record_interaction(meaningful=True)
        except Exception:
            pass

        if was_sulking:
            self._do_comeback(FULL_COMEBACK)
        elif had_fired_stage:
            self._do_comeback(LIGHT_COMEBACK)

    def is_attention_active(self) -> bool:
        return self._attention_active

    def get_stage(self) -> int:
        return self._current_stage

    def is_sulking(self) -> bool:
        return self._sulking

    def start(self, speak_fn, on_chunk_fn=None):
        self._speak_fn    = speak_fn
        self._on_chunk_fn = on_chunk_fn
        self._running     = True
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._presence_once, daemon=True).start()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _silence_seconds(self) -> float:
        return time.time() - self._last_user_message_time

    def _should_activate(self) -> bool:
        return self._today_message_count >= MIN_MESSAGES_TODAY

    def _speak_lines(self, lines: list, delays: list = None):
        if not self._speak_fn or not lines:
            return

        combined = " ".join(lines)
        if not request_to_speak("attention", combined):
            return

        self._attention_active = True
        register_speech()

        default_delays = [1.5, 2.0, 2.5, 1.8]
        for i, line in enumerate(lines):
            if line == "...":
                time.sleep(2.5)
                continue
            self._speak_fn(line)              # voice
            if self._on_chunk_fn:
                self._on_chunk_fn(line)       # UI display only
            if i < len(lines) - 1:
                delay = (delays[i] if delays and i < len(delays)
                         else default_delays[i % len(default_delays)])
                time.sleep(delay)

        self._attention_active = False

    # ── State 0 — Presence ──────────────────────────────────────────────────
    def _presence_once(self):
        time.sleep(random.uniform(PRESENCE_MIN_DELAY, PRESENCE_MAX_DELAY))
        if self._presence_done or self._today_message_count > 0:
            return
        self._presence_done = True
        if not can_speak_now():
            return
        try:
            env = _detect_environment()
            if env["meeting"]:
                return
            from modules.conversation_energy import get_energy
            if get_energy().is_frozen():
                return
        except Exception:
            env = {"app": "unknown", "activity": "other",
                   "time_of_day": _time_of_day(), "filename": ""}

        lines = _llm_presence(env) or _fallback_presence(env)
        print(f"[AttentionEngine] Presence: {lines}")
        self._speak_lines(lines)

    # ── State 5 — Return from AFK ────────────────────────────────────────────
    def _check_return(self, env: dict):
        try:
            from modules.proactive import _idle_seconds, AFK_THRESHOLD
            idle = _idle_seconds()
        except Exception:
            return
        prev = self._prev_idle
        self._prev_idle = idle

        if env.get("meeting"):
            return
        # Was away (prev idle over threshold), now clearly present again.
        if prev >= AFK_THRESHOLD and idle <= RETURN_IDLE_MAX:
            if not can_speak_now():
                return
            trust = _get_trust()
            lines = _build_return_lines(prev, env, trust)
            print(f"[AttentionEngine] Return after {int(prev)}s: {lines}")
            threading.Thread(target=self._speak_lines, args=(lines,), daemon=True).start()

    # ── Comebacks (user typed back) ──────────────────────────────────────────
    def _do_comeback(self, table: dict):
        trust = _get_trust()
        lines = _pick(table, trust)
        print(f"[AttentionEngine] Comeback (trust={trust:.2f}): {lines}")
        threading.Thread(target=self._speak_lines, args=(lines,), daemon=True).start()

    # ── Nudge stages ─────────────────────────────────────────────────────────
    def _fire_stage(self, stage: int, silence: float, env: dict):
        with self._lock:
            if stage in self._stage_fired_at:
                return
            if self._sulking and stage < 3:
                return
            self._stage_fired_at[stage] = time.time()
            self._current_stage = stage

        lines = _llm_generate(stage, silence, env)
        if lines is None:
            fallback = {1: STAGE_1_LINES, 2: STAGE_2_LINES, 3: STAGE_3_LINES}
            lines = _pick(fallback[stage], _get_trust())

        print(f"[AttentionEngine] Stage {stage}: {lines}")

        if stage == 3:
            with self._lock:
                self._sulking = True

        threading.Thread(target=self._speak_lines, args=(lines,), daemon=True).start()

    def _loop(self):
        print("[AttentionEngine] Loop started")
        while self._running:
            time.sleep(15)
            try:
                env = _detect_environment()

                # Energy: meetings freeze the meter completely.
                try:
                    from modules.conversation_energy import get_energy
                    energy = get_energy()
                    energy.set_environment_freeze(env["meeting"])
                except Exception:
                    energy = None

                # State 5 — physical return happens regardless of "talk" silence.
                self._check_return(env)

                if not self._should_activate():
                    continue
                if energy is not None and energy.is_frozen():
                    continue

                # Away from the machine → don't nag for attention.
                try:
                    from modules.proactive import _is_user_afk
                    if _is_user_afk():
                        continue
                except Exception:
                    pass

                if self._sulking:
                    continue
                if not can_speak_now():
                    continue
                # Master gate: only reach out on a genuine "good moment".
                if energy is not None and not energy.is_good_moment():
                    continue

                silence = self._silence_seconds()
                if silence >= STAGE_3_AFTER and 3 not in self._stage_fired_at:
                    self._fire_stage(3, silence, env)
                elif silence >= STAGE_2_AFTER and 2 not in self._stage_fired_at:
                    self._fire_stage(2, silence, env)
                elif silence >= STAGE_1_AFTER and 1 not in self._stage_fired_at:
                    self._fire_stage(1, silence, env)

            except Exception as e:
                print(f"[AttentionEngine Error] {e}")


# ── Singleton ─────────────────────────────────────────────────────────────────
_engine = AttentionEngine()

def get_engine() -> AttentionEngine:
    return _engine
