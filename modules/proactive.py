# modules/proactive.py
import time
import threading
import re
import random
_pending_offer      = None   # context behind the last spoken offer, so a "yes" can act on it
PENDING_OFFER_TTL    = 120    # seconds an offer stays valid for a response before it's considered stale

AFFIRMATIVE_PHRASES = ["yes", "yeah", "yep", "sure", "ok", "okay", "please", "go ahead", "help me", "do it"]

# ── Timing ────────────────────────────────────────────────────────────────────
CHECK_INTERVAL       = 30    # seconds between screen checks
SUGGESTION_COOLDOWN  = 120   # min seconds between any suggestion
STUCK_THRESHOLD      = 4     # same-context checks before "stuck" fires
ERROR_THRESHOLD      = 2     # error-keyword checks before error fires
INTERACTION_INTERVAL = 180   # seconds between casual interaction pings
USER_ACTIVE_SILENCE  = 90    # stay silent if user messaged within this window
CODE_INSIGHT_COOLDOWN = 100  # seconds between code-insight comments specifically
LOCKED_CHECKIN_INTERVAL = 90   # how often AURA comments while locked to one app
_locked_last_signature  = ""

# ── State ─────────────────────────────────────────────────────────────────────
_last_suggestion_time   = 0
_last_interaction_time  = 0
_last_signature         = ""
_last_task              = ""
_last_seen_task         = ""
_same_context_checks    = 0
_error_count            = 0
_screen_reader          = None
_screen_reader_error    = ""
_activity_log           = []
_last_code_signature    = ""
_last_code_insight_time = 0
_locked_app             = None   # if set, AURA only watches an app whose name contains this string


def get_pending_offer() -> dict | None:
    """Return the context behind Aura's last proactive offer, if it's still fresh and unanswered."""
    if _pending_offer and time.time() - _pending_offer["time"] < PENDING_OFFER_TTL:
        return _pending_offer
    return None


def clear_pending_offer():
    global _pending_offer
    _pending_offer = None


def is_affirmative(text: str) -> bool:
    t = text.lower().strip()
    return any(t == p or t.startswith(p + " ") or t.startswith(p + ",") for p in AFFIRMATIVE_PHRASES)


# ── App lock ──────────────────────────────────────────────────────────────────
# Lets the user say "aura see vs code" and have proactive monitoring focus on
# exactly that app, ignoring everything else, until they unlock it again.

APP_ALIASES = {
    "vs code":    "visual studio code",
    "vscode":     "visual studio code",
    "code":       "visual studio code",
    "pycharm":    "pycharm",
    "clion":      "clion",
    "chrome":     "chrome",
    "browser":    "chrome",
    "notepad":    "notepad",
    "word":       "winword",
    "excel":      "excel",
    "powerpoint": "powerpnt",
    "terminal":   "windows terminal",
    "powershell": "powershell",
    "cmd":        "command prompt",
    "spotify":    "spotify",
    "discord":    "discord",
    "youtube":    "youtube",
    "leetcode":   "leetcode",
}


def set_app_lock(app_phrase: str):
    global _locked_app
    phrase = app_phrase.lower().strip()
    _locked_app = APP_ALIASES.get(phrase, phrase)
    print(f"[AURA Proactive] Locked to app containing: '{_locked_app}'")


def clear_app_lock():
    global _locked_app
    if _locked_app:
        print(f"[AURA Proactive] Unlocked from: '{_locked_app}'")
    _locked_app = None


def get_app_lock() -> str | None:
    return _locked_app


FRUSTRATION_KEYWORDS = [
    "error", "exception", "traceback", "failed", "failure", "crash",
    "cannot", "can't", "stuck", "denied", "timeout", "not found",
    "undefined", "syntaxerror", "typeerror", "nameerror", "attributeerror"
]

WORK_APPS = [
    "code", "visual studio", "pycharm", "terminal", "powershell", "cmd",
    "chrome", "browser", "notepad", "word", "excel", "figma", "notion"
]

CODE_EDITOR_APPS = [
    "visual studio code", "vs code", "pycharm", "clion",
    "sublime", "intellij", "vim", "neovim", "code.exe"
]

STUCK_LINES = [
    "still on {task}? want a second pair of eyes?",
    "you've been on {task} for a while — stuck or just deep in it?",
    "that's a long stretch on {task}. need help or should I back off?",
    "{task} giving you grief? say the word.",
]

ERROR_LINES = [
    "seeing some errors there — want me to take a look?",
    "that doesn't look happy. want help debugging?",
    "errors on screen. want to paste it and sort this out?",
    "something's broken. want to fix it together?",
]

INTERACTION_LINES = [
    "what are you working on right now?",
    "how's {task} going?",
    "making progress on {task}?",
    "anything I can help with?",
    "you good, or do you need something?",
]


# ── Screen helpers ─────────────────────────────────────────────────────────────

def _get_screen_context() -> dict:
    global _screen_reader, _screen_reader_error
    if _screen_reader is None and not _screen_reader_error:
        try:
            from modules import screen_reader as sr
            _screen_reader = sr
        except Exception as e:
            _screen_reader_error = str(e)
            print(f"[AURA Proactive] Screen reader unavailable: {e}")
    if _screen_reader is None:
        return {"app": "unknown", "visible_text": "", "clipboard": ""}
    return _screen_reader.get_screen_context()


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()[:500]


def _signature(ctx: dict) -> str:
    return f"{_normalize(ctx.get('app',''))}|{_normalize(ctx.get('visible_text',''))[:220]}"


def _clean_task_name(task: str) -> str:
    """Clean up window titles into short readable task names."""
    # remove leading numbers like "(2678)" or "[2]"
    task = re.sub(r'^\(?\d+\)?\s*', '', task)
    # remove LIVE: or similar prefixes
    task = re.sub(r'^(LIVE|WATCH|NEW|HD|4K)\s*:\s*', '', task, flags=re.IGNORECASE)
    # truncate at separators
    for sep in [' | ', ' - ', ' — ', ' – ']:
        if sep in task:
            task = task.split(sep)[0].strip()
    # max 40 chars
    task = task.strip()
    if len(task) > 40:
        task = task[:37] + "..."
    return task or "this"


def _extract_task(ctx: dict) -> str:
    app      = ctx.get("app", "")
    text     = ctx.get("visible_text", "").lower()
    combined = f"{app} {text}"

    # match against pending tasks first
    try:
        from memory.store import get_pending_tasks
        for task in get_pending_tasks():
            title = task[1]
            words = [w for w in re.findall(r"[a-z0-9]+", title.lower()) if len(w) > 2]
            if words and sum(1 for w in words if w in combined) >= min(2, len(words)):
                return _clean_task_name(title)
    except Exception as e:
        print(f"[AURA Proactive] Task lookup error: {e}")

    # fallback: window title
    title = re.sub(r"\s+", " ", app).strip()
    return _clean_task_name(title)


def _is_work(ctx: dict) -> bool:
    app  = ctx.get("app", "").lower()
    text = ctx.get("visible_text", "")
    return bool(text) or any(name in app for name in WORK_APPS)


def _has_errors(ctx: dict) -> bool:
    text = ctx.get("visible_text", "").lower()
    return any(kw in text for kw in FRUSTRATION_KEYWORDS)


def _is_code_editor(ctx: dict) -> bool:
    app = ctx.get("app", "").lower()
    return any(name in app for name in CODE_EDITOR_APPS)


# ── Flow detection ─────────────────────────────────────────────────────────────

def _is_in_flow() -> bool:
    if len(_activity_log) < 3:
        return False
    recent = _activity_log[-4:]
    tasks  = [t for _, t in recent]
    return len(set(tasks)) > 1

# ── Core decision ──────────────────────────────────────────────────────────────
def _decide(ctx: dict) -> tuple[str, str]:
    global _last_suggestion_time, _last_interaction_time
    global _last_signature, _last_task, _last_seen_task
    global _same_context_checks, _error_count
    global _last_code_signature, _last_code_insight_time

    now  = time.time()
    task = _extract_task(ctx)
    sig  = _signature(ctx)

    _activity_log.append((now, task))
    if len(_activity_log) > 20:
        _activity_log.pop(0)

    # user is actively chatting — stay quiet
    try:
        from core.brain import get_last_user_message_time
        last_msg_time = get_last_user_message_time()
        if last_msg_time and (now - last_msg_time) < USER_ACTIVE_SILENCE:
            return "silent", task
    except Exception as e:
        print(f"[AURA Proactive] Active-check error: {e}")

    # cooldown guard
    if now - _last_suggestion_time < SUGGESTION_COOLDOWN:
        return "silent", task

    if not _is_work(ctx):
        _same_context_checks = 0
        return "silent", task

    # track same-context streak
    if sig == _last_signature:
        _same_context_checks += 1
    else:
        _same_context_checks = 1
        _last_signature = sig

    if task != _last_seen_task:
        _last_seen_task = task
        _same_context_checks = 1

    # error detection (highest priority)
    if _has_errors(ctx):
        _error_count += 1
        if _error_count >= ERROR_THRESHOLD:
            _error_count = 0
            _last_suggestion_time = now
            return "error", task
    else:
        _error_count = max(0, _error_count - 1)

    # code insight — editor open, no errors, fresh code, nothing alarming.
    # Fires on genuinely NEW code (signature changed) so it never repeats
    # the same comment, and it takes priority over "stuck" since the code
    # is fine — there's nothing to nudge about.
    if _is_code_editor(ctx) and not _has_errors(ctx):
        if (sig != _last_code_signature
                and _screen_text_is_usable(ctx.get("visible_text", ""))
                and now - _last_code_insight_time > CODE_INSIGHT_COOLDOWN):
            _last_code_signature    = sig
            _last_code_insight_time = now
            _last_suggestion_time   = now
            return "code_insight", task

    # stuck detection
    if _same_context_checks >= STUCK_THRESHOLD and task != _last_task:
        _same_context_checks = 0
        _last_task = task
        _last_suggestion_time = now
        return "stuck", task

    # casual interaction — only when user is in flow
    since_interaction = now - _last_interaction_time
    if (since_interaction > INTERACTION_INTERVAL
            and _is_in_flow()
            and _same_context_checks < 2):
        _last_interaction_time = now
        return "interaction", task

    return "silent", task

def _decide_locked(ctx: dict) -> tuple[str, str]:
    """Decision logic while locked onto a single app. Skips the normal
    flow/variety checks — there's only one app, so 'in flow' never applies."""
    global _last_suggestion_time, _locked_last_signature

    now  = time.time()
    task = _extract_task(ctx)
    sig  = _signature(ctx)

    try:
        from core.brain import get_last_user_message_time
        last_msg_time = get_last_user_message_time()
        if last_msg_time and (now - last_msg_time) < USER_ACTIVE_SILENCE:
            return "silent", task
    except Exception as e:
        print(f"[AURA Proactive] Active-check error: {e}")

    if now - _last_suggestion_time < LOCKED_CHECKIN_INTERVAL:
        return "silent", task

    if _has_errors(ctx):
        _last_suggestion_time = now
        return "error", task

    if _is_code_editor(ctx) and sig != _locked_last_signature:
        if _screen_text_is_usable(ctx.get("visible_text", "")):
            _locked_last_signature = sig
            _last_suggestion_time  = now
            return "code_insight", task

    _last_suggestion_time  = now
    _locked_last_signature = sig

    if not _screen_text_is_usable(ctx.get("visible_text", "")):
        return "locked_idle", task

    return "locked_activity", task


def _pick_line(lines: list, task: str) -> str:
    line = random.choice(lines)
    return line.replace("{task}", task)

_PROACTIVE_PROMPT = """You are AURA noticing something on the user's screen and deciding to say something.
Moment type: {moment}
Window/app: {app}
What's visible on screen: {screen}
Inferred task: {task}

Write ONE short line (max 2 sentences, no quotes around it).

CRITICAL RULE: Only reference a specific detail from "What's visible on screen" if it is clearly readable, coherent English/code and you are CERTAIN about it. NEVER guess, complete, or invent words, function names, error messages, or details that aren't clearly and fully present in the screen text. If the screen text says "(screen text unclear...)" or looks fragmented/garbled, do NOT mention any specific detail — instead make a short, generic but natural comment using only the task name and app name.

It is much better to be generic than to be specific and wrong. Fabricating a detail is the worst possible outcome.

Moment type guide:
- error: something looks broken or an error is visible. Be a bit dry/teasing but offer help.
- stuck: same screen for a while, no progress. Light nudge, not naggy.
- interaction: casual check-in during active work. Curious, not intrusive.

Stay in character: sharp, casual, dry humor, like a smart friend texting. No "I notice you..." or "I see that...". Just talk like you already know.
"""

CODE_INSIGHT_PROMPT = """You are AURA glancing at the user's screen while they code. There are no errors — the code looks fine. You're making ONE short, sharp, specific observation about what the code actually does, like a sharp dev friend reading over their shoulder.

App: {app}
Code/screen text: {screen}
Inferred task: {task}

CRITICAL RULE: Only name a specific function, pattern, or algorithm if it is clearly and fully readable in the screen text above. If the screen text says "(screen text unclear...)" or looks fragmented, do NOT invent or guess any detail — instead make a short, generic but natural comment using only the task name.

Rules:
- Max 2 sentences, no quotes around the line
- NEVER ask "need help debugging" or "is something wrong" — there is no problem, the code is fine
- Sound like a smart friend who just glanced at the screen — casual, dry, specific when you genuinely can be
- It is much better to be generic than to invent a detail that isn't really there
"""

LOCKED_IDLE_PROMPT = """You are AURA, locked onto watching {app} because the user asked you to focus only on it. Nothing substantial is happening there right now — blank, idle, or unreadable.

App: {app}

Write ONE short, dry, Donna-style line noticing the emptiness. Tease lightly — "you dragged me here and wandered off" energy.

Rules:
- Max 2 sentences, no quotes around the line
- Don't invent what they might be doing elsewhere — just call out the emptiness here
- Casual, dry, a little teasing — not annoyed
"""

LOCKED_ACTIVITY_PROMPT = """You are AURA, locked onto watching {app}. Something IS visible. Make ONE short, sharp observation about what they're doing, like a friend glancing over their shoulder.

App: {app}
Visible content: {screen}
Inferred task: {task}

CRITICAL RULE: Only reference a detail from "Visible content" if clearly readable and certain. If fragmented or unclear, stay generic using only task/app name.

Rules:
- Max 2 sentences, no quotes
- Observational, a little dry — not a question every time
- Generic beats invented and wrong
"""

LOCKED_IDLE_LINES = [
    "nothing's happening on {app}. off doing something else, Shaurya?",
    "{app}'s just sitting there. did you wander off on me?",
    "quiet over here on {app}. you still with me?",
    "you locked me onto {app} and then vanished. classic.",
]

def _screen_text_is_usable(text: str) -> bool:
    """Reject OCR text that's too short, fragmented, or noisy to safely reference."""
    if not text or len(text.strip()) < 25:
        return False
    words = re.findall(r"[a-zA-Z]{3,}", text)
    if len(words) < 6:
        return False
    # too many single/double-char tokens = garbled OCR
    tokens = text.split()
    junk_ratio = sum(1 for t in tokens if len(t) <= 2) / max(len(tokens), 1)
    if junk_ratio > 0.5:
        return False
    return True


def _ai_generate_message(action: str, task: str, ctx: dict, prompt_template: str) -> str | None:
    try:
        from core.ai_router import call_groq
        raw_text = ctx.get("visible_text", "")
        usable = _screen_text_is_usable(raw_text)
        screen_for_prompt = raw_text[:400] if usable else "(screen text unclear — do not reference specifics, talk about the task generally)"

        prompt = prompt_template.format(
            moment=action,
            app=ctx.get("app", "unknown"),
            screen=screen_for_prompt,
            task=task
        )
        result = call_groq(prompt, intent="CASUAL").strip()
        result = result.strip('"').strip("'").strip()
        if result and result.upper() not in {"CONNECTION_ERROR", "RATE_LIMIT", ""}:
            return result
    except Exception as e:
        print(f"[AURA Proactive] AI message error: {e}")
    return None


def generate_message(action: str, task: str, ctx: dict) -> str | None:
    # Only spend an AI call on higher-value moments — keep casual pings cheap
    if action in {"error", "stuck"}:
        ai_msg = _ai_generate_message(action, task, ctx, _PROACTIVE_PROMPT)
        if ai_msg:
            return ai_msg
    elif action == "code_insight":
        ai_msg = _ai_generate_message(action, task, ctx, CODE_INSIGHT_PROMPT)
        # No template fallback here on purpose — a wrong guess about code
        # logic is worse than staying silent this one cycle.
        return ai_msg

    # fallback to templates if AI call fails, or for interaction
    if action == "error":
        return _pick_line(ERROR_LINES, task)
    if action == "stuck":
        return _pick_line(STUCK_LINES, task)
    if action == "interaction":
        return _pick_line(INTERACTION_LINES, task)
    elif action == "locked_idle":
        ai_msg = _ai_generate_message(action, task, ctx, LOCKED_IDLE_PROMPT)
        return ai_msg or _pick_line(LOCKED_IDLE_LINES, task)
    elif action == "locked_activity":
        return _ai_generate_message(action, task, ctx, LOCKED_ACTIVITY_PROMPT)
    return None


# ── Loop ──────────────────────────────────────────────────────────────────────

def _loop(speak_fn, on_suggestion_fn=None):
    global _pending_offer
    print("[AURA Proactive] Loop started")
    while True:
        try:
            time.sleep(CHECK_INTERVAL)
            ctx = _get_screen_context()
            if not ctx:
                continue

            # app lock — if locked, completely skip cycles where the
            # active app isn't the locked one. No state changes happen
            # for ignored apps, so switching back picks up cleanly.
            if _locked_app and _locked_app not in ctx.get("app", "").lower():
                continue

            if _locked_app:
                action, task = _decide_locked(ctx)
            else:
                action, task = _decide(ctx)
            if action == "silent":
                continue

            msg = generate_message(action, task, ctx)
            if not msg:
                continue

            _pending_offer = {"action": action, "task": task, "ctx": ctx, "message": msg, "time": time.time()}

            print(f"[AURA Proactive] ({action}) {msg}")
            if on_suggestion_fn:
                on_suggestion_fn(msg)
            speak_fn(msg)

        except Exception as e:
            print(f"[AURA Proactive Error] {e}")


def start_proactive_loop(speak_fn, on_suggestion_fn=None):
    t = threading.Thread(target=_loop, args=(speak_fn, on_suggestion_fn), daemon=True)
    t.start()
    return t