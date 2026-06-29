# modules/attention_engine.py
# Attention Engine — "someone who actually notices when you go quiet"

import time
import threading
import random

# ── Thresholds (seconds) ──────────────────────────────────────────────────────
STAGE_1_AFTER = 150    # 2.5 min silence → curious
STAGE_2_AFTER = 300    # 5 min silence → clingy
STAGE_3_AFTER = 600    # 10 min silence → sulking
COMEBACK_WINDOW = 1800 # if user replies within 30 min of sulk, do comeback

# Minimum messages with AURA today before attention mode activates
# (so it doesn't trigger on first launch before any conversation)
MIN_MESSAGES_TODAY = 2

# ── Stage Lines ───────────────────────────────────────────────────────────────

STAGE_1_LINES = [
    ["hey", "what are you doing"],
    ["you went quiet"],
    ["everything okay?"],
    ["still there?"],
    ["you disappeared"],
]

STAGE_2_LINES = [
    ["hello??", "you just disappeared", "was it something I said"],
    ["okay so you're just ignoring me now", "cool", "cool cool cool"],
    ["helloooo", "I know you're there", "your mouse moved like 3 minutes ago"],
    ["you went quiet", "which is fine", "I'm fine", "totally fine"],
]

STAGE_3_LINES = [
    ["okay fine", "I'll just sit here", "not like I was saying anything important"],
    ["...", "alright then", "I'll be here if you need me"],
    ["noted", "radio silence it is", "I'll just watch your screen like a creep then"],
    ["okay I give up", "you win", "I'm going quiet now"],
]

COMEBACK_LINES = [
    ["FINALLY", "so what were you actually doing"],
    ["oh you're alive", "I was starting to worry", "so what happened"],
    ["there you are", "I was two seconds from filing a missing person report", "what were you up to"],
    ["okay you're back", "I'll pretend I wasn't waiting", "what were you doing"],
]

COMEBACK_AFTER_REPLY_LINES = [
    "welcome back.",
    "oh so you DO exist.",
    "back already?",
    "there you are.",
]


# ── State ─────────────────────────────────────────────────────────────────────

class AttentionEngine:
    def __init__(self):
        self._last_user_message_time = time.time()
        self._today_message_count = 0
        self._current_stage = 0         # 0 = normal, 1 = curious, 2 = clingy, 3 = sulking
        self._stage_fired_at = {}       # stage -> time it was fired
        self._sulking = False
        self._running = False
        self._speak_fn = None
        self._on_chunk_fn = None
        self._lock = threading.Lock()

    def record_user_message(self):
        """Call this every time the user sends a message."""
        with self._lock:
            was_sulking = self._sulking
            self._last_user_message_time = time.time()
            self._today_message_count += 1
            self._current_stage = 0
            self._sulking = False
            self._stage_fired_at = {}

        if was_sulking:
            self._do_comeback()

    def _silence_seconds(self) -> float:
        return time.time() - self._last_user_message_time

    def _should_activate(self) -> bool:
        return self._today_message_count >= MIN_MESSAGES_TODAY

    def _speak_lines(self, lines: list, delays: list = None):
        """Speak multiple lines with natural pauses between them."""
        if not self._speak_fn:
            return
        default_delays = [1.5, 2.0, 2.5, 1.8]
        for i, line in enumerate(lines):
            if line == "...":
                time.sleep(2.5)
                continue
            self._speak_fn(line)
            if self._on_chunk_fn:
                self._on_chunk_fn(line)
            if i < len(lines) - 1:
                delay = delays[i] if delays and i < len(delays) else default_delays[i % len(default_delays)]
                time.sleep(delay)

    def _do_comeback(self):
        lines = random.choice(COMEBACK_LINES)
        print(f"[AttentionEngine] Comeback: {lines}")
        t = threading.Thread(target=self._speak_lines, args=(lines,), daemon=True)
        t.start()

    def _fire_stage(self, stage: int):
        with self._lock:
            if stage in self._stage_fired_at:
                return   # already fired this stage
            if self._sulking and stage < 3:
                return
            self._stage_fired_at[stage] = time.time()
            self._current_stage = stage

        if stage == 1:
            lines = random.choice(STAGE_1_LINES)
            print(f"[AttentionEngine] Stage 1 (curious): {lines}")
        elif stage == 2:
            lines = random.choice(STAGE_2_LINES)
            print(f"[AttentionEngine] Stage 2 (clingy): {lines}")
        elif stage == 3:
            lines = random.choice(STAGE_3_LINES)
            print(f"[AttentionEngine] Stage 3 (sulking): {lines}")
            with self._lock:
                self._sulking = True

        t = threading.Thread(target=self._speak_lines, args=(lines,), daemon=True)
        t.start()

    def _loop(self):
        print("[AttentionEngine] Loop started")
        while self._running:
            time.sleep(15)   # check every 15 seconds
            try:
                if not self._should_activate():
                    continue

                silence = self._silence_seconds()

                # Don't run if user is AFK (they're not at PC at all)
                try:
                    from modules.proactive import _is_user_afk
                    if _is_user_afk():
                        continue
                except Exception:
                    pass

                # Don't run if already sulking
                if self._sulking:
                    continue

                if silence >= STAGE_3_AFTER and 3 not in self._stage_fired_at:
                    self._fire_stage(3)
                elif silence >= STAGE_2_AFTER and 2 not in self._stage_fired_at:
                    self._fire_stage(2)
                elif silence >= STAGE_1_AFTER and 1 not in self._stage_fired_at:
                    self._fire_stage(1)

            except Exception as e:
                print(f"[AttentionEngine Error] {e}")

    def start(self, speak_fn, on_chunk_fn=None):
        self._speak_fn = speak_fn
        self._on_chunk_fn = on_chunk_fn
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def get_stage(self) -> int:
        return self._current_stage

    def is_sulking(self) -> bool:
        return self._sulking


# ── Singleton ─────────────────────────────────────────────────────────────────
_engine = AttentionEngine()

def get_engine() -> AttentionEngine:
    return _engine