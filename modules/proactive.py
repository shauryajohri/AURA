import time
import threading
import re

CHECK_INTERVAL = 30
SUGGESTION_COOLDOWN = 180
STUCK_CHECKS = 4
ERROR_CHECKS = 2

_last_suggestion_time = 0
_last_signature = ""
_last_task = ""
_last_seen_task = ""
_same_context_checks = 0
_error_count = 0
_screen_reader = None
_screen_reader_error = ""

FRUSTRATION_KEYWORDS = [
    "error", "exception", "traceback", "failed", "failure", "crash",
    "cannot", "can't", "stuck", "denied", "timeout", "not found"
]
WORK_APPS = [
    "code", "visual studio", "pycharm", "terminal", "powershell", "cmd",
    "chrome", "browser", "notepad", "word", "excel"
]


def _get_screen_context() -> dict:
    global _screen_reader, _screen_reader_error

    if _screen_reader is None and not _screen_reader_error:
        try:
            from modules import screen_reader as _screen_reader_module
            _screen_reader = _screen_reader_module
        except Exception as e:
            _screen_reader_error = str(e)
            print(f"[AURA Proactive] Screen reader unavailable: {_screen_reader_error}")

    if _screen_reader is None:
        return {"app": "unknown", "visible_text": "", "clipboard": ""}

    return _screen_reader.get_screen_context()


def _normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text.lower()).strip()
    return text[:500]


def _signature(ctx: dict) -> str:
    app = _normalize_text(ctx.get("app", ""))
    text = _normalize_text(ctx.get("visible_text", ""))
    return f"{app}|{text[:220]}"


def _extract_task_from_title(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    if not title or title.lower() == "unknown":
        return ""

    for sep in [" - ", " | ", " — "]:
        if sep in title:
            parts = [p.strip() for p in title.split(sep) if p.strip()]
            if parts:
                return parts[0][:80]
    return title[:80]


def _infer_task(ctx: dict) -> str:
    app = ctx.get("app", "")
    visible_text = ctx.get("visible_text", "")
    combined = f"{app} {visible_text}".lower()

    try:
        from memory.store import get_pending_tasks
        for task in get_pending_tasks():
            title = task[1]
            words = [w for w in re.findall(r"[a-z0-9]+", title.lower()) if len(w) > 2]
            if words and sum(1 for word in words if word in combined) >= min(2, len(words)):
                return title
    except Exception as e:
        print(f"[AURA Proactive] Task lookup error: {e}")

    title_task = _extract_task_from_title(app)
    if title_task:
        return title_task

    return "this task"


def _looks_like_work(ctx: dict) -> bool:
    app = ctx.get("app", "").lower()
    text = ctx.get("visible_text", "").lower()
    return bool(text) or any(name in app for name in WORK_APPS)


def should_suggest(ctx: dict) -> tuple[bool, str, str]:
    global _last_suggestion_time, _last_signature, _last_task, _last_seen_task
    global _same_context_checks, _error_count

    now = time.time()
    if now - _last_suggestion_time < SUGGESTION_COOLDOWN:
        return False, "cooldown", ""

    if not _looks_like_work(ctx):
        _same_context_checks = 0
        return False, "no_work_context", ""

    task = _infer_task(ctx)
    sig = _signature(ctx)
    text = ctx.get("visible_text", "").lower()
    has_error = any(word in text for word in FRUSTRATION_KEYWORDS)

    if sig == _last_signature:
        _same_context_checks += 1
    else:
        _same_context_checks = 1
        _last_signature = sig

    if has_error:
        _error_count += 1
        if _error_count >= ERROR_CHECKS:
            _error_count = 0
            _last_task = task
            _last_suggestion_time = now
            return True, "error_spotted", task
    else:
        _error_count = max(0, _error_count - 1)

    if task != _last_seen_task:
        _last_seen_task = task
        _same_context_checks = 1

    if _same_context_checks >= STUCK_CHECKS and task != _last_task:
        _same_context_checks = 0
        _last_task = task
        _last_suggestion_time = now
        return True, "possibly_stuck", task

    return False, "", ""


def generate_suggestion(ctx: dict, reason: str, task: str) -> str | None:
    if reason == "error_spotted":
        lines = ctx.get("visible_text", "").splitlines()
        error_line = next(
            (line for line in lines if any(word in line.lower() for word in FRUSTRATION_KEYWORDS)),
            None
        )
        if error_line and len(error_line) < 60:
            return f"I keep seeing '{error_line.strip()}'. Want help with {task}?"
        return f"Looks like {task} is throwing errors. Want help?"

    if reason == "possibly_stuck":
        return f"You have been on {task} for a while. Stuck, or should I stay quiet?"

    return None


def _loop(speak_fn, on_suggestion_fn=None):
    print("[AURA Proactive] Loop started")
    while True:
        try:
            time.sleep(CHECK_INTERVAL)
            ctx = _get_screen_context()
            if not ctx:
                continue

            should, reason, task = should_suggest(ctx)
            if should:
                suggestion = generate_suggestion(ctx, reason, task)
                if suggestion and len(suggestion) > 2:
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
    return t
