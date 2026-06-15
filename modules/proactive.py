# modules/proactive.py
import time
import threading
import re
import random

# ── Timing ────────────────────────────────────────────────────────────────────
CHECK_INTERVAL      = 30    # seconds between screen checks
SUGGESTION_COOLDOWN = 120   # min seconds between any suggestion
STUCK_THRESHOLD     = 4     # same-context checks before "stuck" fires
ERROR_THRESHOLD     = 2     # error-keyword checks before error fires
INTERACTION_INTERVAL = 180  # seconds between casual interaction pings

# ── State ─────────────────────────────────────────────────────────────────────
_last_suggestion_time  = 0
_last_interaction_time = 0
_last_signature        = ""
_last_task             = ""
_last_seen_task        = ""
_same_context_checks   = 0
_error_count           = 0
_screen_reader         = None
_screen_reader_error   = ""
_activity_log          = []   # rolling list of (timestamp, task) to detect flow vs stuck

FRUSTRATION_KEYWORDS = [
    "error", "exception", "traceback", "failed", "failure", "crash",
    "cannot", "can't", "stuck", "denied", "timeout", "not found",
    "undefined", "syntaxerror", "typeerror", "nameerror", "attributeerror"
]

WORK_APPS = [
    "code", "visual studio", "pycharm", "terminal", "powershell", "cmd",
    "chrome", "browser", "notepad", "word", "excel", "figma", "notion"
]

# Donna-style lines for each situation
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


def _extract_task(ctx: dict) -> str:
    app   = ctx.get("app", "")
    text  = ctx.get("visible_text", "").lower()
    combined = f"{app} {text}"

    # match against pending tasks first
    try:
        from memory.store import get_pending_tasks
        for task in get_pending_tasks():
            title = task[1]
            words = [w for w in re.findall(r"[a-z0-9]+", title.lower()) if len(w) > 2]
            if words and sum(1 for w in words if w in combined) >= min(2, len(words)):
                return title
    except Exception as e:
        print(f"[AURA Proactive] Task lookup error: {e}")

    # fallback: window title
    title = re.sub(r"\s+", " ", app).strip()
    for sep in [" - ", " | ", " — "]:
        if sep in title:
            return title.split(sep)[0].strip()[:80]
    return title[:80] or "this"


def _is_work(ctx: dict) -> bool:
    app  = ctx.get("app", "").lower()
    text = ctx.get("visible_text", "")
    return bool(text) or any(name in app for name in WORK_APPS)


def _has_errors(ctx: dict) -> bool:
    text = ctx.get("visible_text", "").lower()
    return any(kw in text for kw in FRUSTRATION_KEYWORDS)


# ── Flow detection ─────────────────────────────────────────────────────────────

def _is_in_flow() -> bool:
    """
    If the task has been changing regularly, user is in flow.
    If it's been the same for a long time, they might be stuck.
    """
    if len(_activity_log) < 3:
        return False
    recent = _activity_log[-4:]
    tasks  = [t for _, t in recent]
    # all same task = possibly stuck, not flow
    return len(set(tasks)) > 1


# ── Core decision ──────────────────────────────────────────────────────────────

def _decide(ctx: dict) -> tuple[str, str]:
    """
    Returns (action, task) where action is one of:
      'stuck'       → user seems stuck, offer help
      'error'       → error on screen, offer debug help
      'interaction' → user seems fine, casual check-in
      'silent'      → say nothing
    """
    global _last_suggestion_time, _last_interaction_time
    global _last_signature, _last_task, _last_seen_task
    global _same_context_checks, _error_count

    now  = time.time()
    task = _extract_task(ctx)
    sig  = _signature(ctx)

    # track activity
    _activity_log.append((now, task))
    if len(_activity_log) > 20:
        _activity_log.pop(0)

    # cooldown guard
    since_last = now - _last_suggestion_time
    if since_last < SUGGESTION_COOLDOWN:
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

    # stuck detection
    if _same_context_checks >= STUCK_THRESHOLD and task != _last_task:
        _same_context_checks = 0
        _last_task = task
        _last_suggestion_time = now
        return "stuck", task

    # casual interaction — if user is in flow and enough time has passed
    since_interaction = now - _last_interaction_time
    if (since_interaction > INTERACTION_INTERVAL
            and _is_in_flow()
            and _same_context_checks < 2):   # actively switching context = working fine
        _last_interaction_time = now
        return "interaction", task

    return "silent", task


def _pick_line(lines: list, task: str) -> str:
    line = random.choice(lines)
    return line.replace("{task}", task)


def generate_message(action: str, task: str, ctx: dict) -> str | None:
    if action == "error":
        return _pick_line(ERROR_LINES, task)

    if action == "stuck":
        return _pick_line(STUCK_LINES, task)

    if action == "interaction":
        return _pick_line(INTERACTION_LINES, task)

    return None


# ── Loop ──────────────────────────────────────────────────────────────────────

def _loop(speak_fn, on_suggestion_fn=None):
    print("[AURA Proactive] Loop started")
    while True:
        try:
            time.sleep(CHECK_INTERVAL)
            ctx = _get_screen_context()
            if not ctx:
                continue

            action, task = _decide(ctx)
            if action == "silent":
                continue

            msg = generate_message(action, task, ctx)
            if not msg:
                continue

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