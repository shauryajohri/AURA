import time
import threading
from modules.screen_reader import get_screen_context
from core.ai_router import call_ollama
from core.personality import DONNA_SYSTEM_PROMPT

# how often to check screen context (seconds)
CHECK_INTERVAL = 30

# apps where proactive help makes sense
TRIGGER_APPS = {
    "leetcode":   "User is solving a coding problem",
    "stackoverflow": "User is debugging or researching",
    "github":     "User is reviewing code",
    "youtube":    "User is watching a video",
    "docs":       "User is reading documentation",
    "pdf":        "User is reading a document",
    "error":      "User sees an error on screen",
    "exception":  "User has a code exception",
    "traceback":  "User has a Python traceback",
}

last_suggestion_time = 0
last_app = ""

def should_suggest(ctx: dict) -> tuple[bool, str]:
    global last_suggestion_time, last_app

    # don't suggest too frequently
    if time.time() - last_suggestion_time < CHECK_INTERVAL:
        return False, ""

    app = ctx["app"].lower()
    screen = ctx["visible_text"].lower()

    for trigger, reason in TRIGGER_APPS.items():
        if trigger in app or trigger in screen:
            # don't repeat for same app
            if app == last_app:
                return False, ""
            return True, reason

    return False, ""

def generate_suggestion(ctx: dict, reason: str) -> str:
    prompt = f"""
The user is currently: {reason}
App: {ctx['app']}
Screen: {ctx['visible_text'][:300]}

Generate ONE short, natural proactive suggestion AURA could make.
Maximum 15 words. Sound like a helpful friend, not a robot.
Examples:
- "Looks like you hit an error — want me to explain it?"
- "You've been on this problem a while. Want a hint?"
- "Want me to summarize what you're reading?"
"""
    return call_ollama(prompt)

def start_proactive_loop(speak_fn, on_suggestion_fn=None):
    def _loop():
        global last_suggestion_time, last_app
        while True:
            try:
                time.sleep(10)
                ctx = get_screen_context()
                should, reason = should_suggest(ctx)

                if should:
                    suggestion = generate_suggestion(ctx, reason)
                    if suggestion and len(suggestion) > 5:
                        last_suggestion_time = time.time()
                        last_app = ctx["app"].lower()
                        print(f"[AURA Proactive] {suggestion}")
                        if on_suggestion_fn:
                            on_suggestion_fn(suggestion)
                        speak_fn(suggestion)
            except Exception as e:
                print(f"[AURA Proactive Error] {e}")

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()