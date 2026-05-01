import time
import threading
from modules.screen_reader import get_screen_context
from core.ai_router import call_ollama
from core.personality import DONNA_SYSTEM_PROMPT

CHECK_INTERVAL = 30

TRIGGER_APPS = {
    "leetcode":      "User is solving a coding problem",
    "stackoverflow": "User is debugging or researching",
    "github":        "User is reviewing code",
    "youtube":       "User is watching a video",
    "docs":          "User is reading documentation",
    "pdf":           "User is reading a document",
    "error":         "User sees an error on screen",
    "exception":     "User has a code exception",
    "traceback":     "User has a Python traceback",
}

last_suggestion_time = 0
last_app = ""

def should_suggest(ctx: dict) -> tuple[bool, str]:
    global last_suggestion_time, last_app
    if time.time() - last_suggestion_time < CHECK_INTERVAL:
        return False, ""
    app    = ctx["app"].lower()
    screen = ctx["visible_text"].lower()
    for trigger, reason in TRIGGER_APPS.items():
        if trigger in app or trigger in screen:
            if app == last_app:
                return False, ""
            return True, reason
    return False, ""

def generate_suggestion(ctx: dict, reason: str) -> str:
    prompt = f"""
The user is currently: {reason}
App: {ctx['app']}
Screen: {ctx['visible_text'][:300]}

Generate ONE short proactive suggestion. Max 10 words. Casual tone.
"""
    return call_ollama(prompt)

def start_proactive_loop(speak_fn, on_suggestion_fn=None):
    # DISABLED — causing double voice + screen context leaks
    # re-enable after output guard is fully stable
    print("[AURA Proactive] Disabled for now.")
    return
    
    # ── dead code below — kept for when we re-enable ──
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

    threading.Thread(target=_loop, daemon=True).start()