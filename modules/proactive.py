# modules/proactive.py
import time
import random
import threading
import re
from modules.screen_reader import get_screen_context

# Cooldown between suggestions (long, unpredictable)
SUGGESTION_COOLDOWN = random.randint(180, 420)  # 3-7 minutes

_last_suggestion_time = 0
_last_app = ""
_error_count = 0
_boredom_timer = 0

# Simple patterns for frustration detection (no AI)
FRUSTRATION_KEYWORDS = ["error", "exception", "traceback", "failed", "bug", "crash"]
LONG_IDLE_THRESHOLD = 300  # 5 minutes same app

def should_suggest(ctx: dict) -> tuple:
    """Returns (should_speak, reason_tag)."""
    global _last_suggestion_time, _last_app, _error_count, _boredom_timer

    now = time.time()
    if now - _last_suggestion_time < SUGGESTION_COOLDOWN:
        return False, "cooldown"

    app = ctx.get("app", "").lower()
    text = ctx.get("visible_text", "")

    # 1. Frustration / errors
    if any(word in text.lower() for word in FRUSTRATION_KEYWORDS):
        _error_count += 1
        if _error_count >= 2:
            _error_count = 0
            _last_suggestion_time = now
            return True, "error_spotted"
    else:
        _error_count = max(0, _error_count - 1)

    # 2. App switch (low probability)
    if app and app != _last_app:
        _last_app = app
        if random.random() < 0.2:
            _last_suggestion_time = now
            return True, "app_switched"

    # 3. Long idle in same app
    if app == _last_app:
        _boredom_timer += 10  # called every ~30s in loop, but we'll adjust in _loop
        if _boredom_timer > LONG_IDLE_THRESHOLD:
            _boredom_timer = 0
            _last_suggestion_time = now
            return True, "long_idle"
    else:
        _boredom_timer = 0

    return False, ""

def generate_suggestion(ctx: dict, reason: str) -> str | None:
    """Generate a dry, teasing remark based on reason. Never mentions user activity."""
    app = ctx.get("app", "")
    text = ctx.get("visible_text", "")

    if reason == "error_spotted":
        lines = text.splitlines()
        error_line = next((l for l in lines if "error" in l.lower()), None)
        if error_line and len(error_line) < 60:
            snippet = error_line.strip()
            return f"that '{snippet}' looks personal."
        return random.choice([
            "still friends with that error message?",
            "want me to translate that gibberish?",
            "that bug's got you, huh.",
            "need a second pair of eyes or just a punching bag?"
        ])

    if reason == "app_switched":
        if app in ["terminal", "cmd"]:
            return random.choice([
                "ah, back to the dark side.",
                "typing commands like a movie hacker now?",
                "let me guess, 'git status' first?"
            ])
        elif app in ["code", "vscode", "sublime"]:
            return random.choice([
                "new feature or new bugs?",
                "try not to break production this time.",
                "your indentations better be consistent."
            ])
        else:
            return f"switched to {app}. productive or procrastinating?"

    if reason == "long_idle":
        return random.choice([
            "still there? blink twice if you need coffee.",
            "you've been quiet. stuck or just thinking?",
            "if you fell asleep, I'm not giving a eulogy.",
            "the code won't fix itself, but a nap might."
        ])

    return None

def _loop(speak_fn, on_suggestion_fn=None):
    global _last_suggestion_time, _last_app, _boredom_timer
    print("[AURA Proactive] Loop started (Donna mode)")
    while True:
        try:
            time.sleep(30)  # check every 30 seconds
            ctx = get_screen_context()
            if not ctx:
                continue

            should, reason = should_suggest(ctx)
            if should:
                suggestion = generate_suggestion(ctx, reason)
                if suggestion and len(suggestion) > 2:
                    _last_suggestion_time = time.time()
                    _last_app = ctx.get("app", "").lower()
                    _boredom_timer = 0
                    print(f"[AURA Proactive] ({reason}) {suggestion}")
                    if on_suggestion_fn:
                        on_suggestion_fn(suggestion)
                    speak_fn(suggestion)
        except Exception as e:
            print(f"[AURA Proactive Error] {e}")

def start_proactive_loop(speak_fn, on_suggestion_fn=None):
    """Start the proactive loop in a daemon thread."""
    t = threading.Thread(target=_loop, args=(speak_fn, on_suggestion_fn), daemon=True)
    t.start()