"""
Remote control — you tell AURA something from your phone, she does it on the laptop.

    phone ──POST /remote/api/command──▶ presence gate ──▶ plan ──▶ (confirm?) ──▶ run
                                           │
                                           └─ laptop locked / unreachable desktop
                                              → she declines straight away

The presence gate is the "only on my active laptop" rule. A command is accepted
only when ALL of these hold:
    * remote control isn't paused from the laptop
    * this machine can actually be driven (pyautogui + a display)
    * the session is unlocked (Windows: the input desktop is the user's desktop;
      macOS: CGSession says unlocked)
    * optionally, the laptop was used in the last AURA_REMOTE_MAX_IDLE_MIN minutes
      (off by default — when you're on your phone you're usually away from it)
If the laptop is asleep or off, AURA isn't running, so the phone just can't
reach her, and the phone page shows that as "offline".

Planning turns the sentence into steps from core/actions. Obvious commands
("open spotify", "search for flights to goa") are parsed locally with no model
call. Anything else goes to the planner model. A plan with a risky step (or
any plan, when AURA_REMOTE_CONFIRM=all) is held until the phone approves it.

Steps run one at a time, under one lock, so two commands never type over each
other. The gate is checked again before every step, so locking the laptop
mid-job stops it. The phone's Stop button sets actions.STOP. Every job is
appended to memory/remote_actions.jsonl.
"""

from __future__ import annotations

import ctypes
import json
import os
import platform
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import quote_plus

from core import actions, vision_agent

_REPO = Path(__file__).resolve().parent.parent
LOG_PATH = _REPO / "memory" / "remote_actions.jsonl"

MAX_STEPS = 12
MAX_COMMAND_CHARS = 600
PENDING_TTL = 300          # an unapproved plan expires after 5 minutes
MAX_JOBS_KEPT = 30


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def confirm_mode() -> str:
    m = _env("AURA_REMOTE_CONFIRM", "risky").lower()
    return m if m in {"risky", "all", "none"} else "risky"


def shell_allowed() -> bool:
    return _env("AURA_REMOTE_ALLOW_SHELL", "0") == "1"


def max_idle_seconds() -> float:
    try:
        return max(0.0, float(_env("AURA_REMOTE_MAX_IDLE_MIN", "0")) * 60)
    except ValueError:
        return 0.0


_paused = threading.Event()


def set_paused(value: bool) -> None:
    (_paused.set if value else _paused.clear)()


def is_paused() -> bool:
    return _paused.is_set()


# ---------------------------------------------------------------------------
# Presence — is the laptop "active"?
# ---------------------------------------------------------------------------
def _session_locked() -> bool | None:
    """True locked / False unlocked / None can't tell on this OS."""
    system = platform.system()
    if system == "Windows":
        try:
            user32 = ctypes.windll.user32
            desk = user32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_SWITCHDESKTOP
            if not desk:
                return True        # input desktop is Winlogon / the lock screen
            switched = user32.SwitchDesktop(desk)
            user32.CloseDesktop(desk)
            return not switched
        except Exception:  # noqa: BLE001
            return None
    if system == "Darwin":
        try:
            import Quartz  # type: ignore
            info = Quartz.CGSessionCopyCurrentDictionary() or {}
            return bool(info.get("CGSSessionScreenIsLocked", False))
        except Exception:  # noqa: BLE001
            return None
    return None


def _idle_seconds() -> float | None:
    try:
        from modules.proactive import _get_windows_idle_seconds
        return _get_windows_idle_seconds()
    except Exception:  # noqa: BLE001
        return None


def presence() -> dict:
    """{'active': bool, 'reason': str, ...} — reason is what AURA tells the phone."""
    if is_paused():
        return {"active": False, "state": "paused",
                "reason": "Remote control is paused on the laptop, so I'm not touching it."}
    ok, why = actions.desktop_available()
    if not ok:
        return {"active": False, "state": "no_desktop",
                "reason": f"I can't control this machine's screen right now ({why})."}
    locked = _session_locked()
    if locked:
        return {"active": False, "state": "locked",
                "reason": "Your laptop is locked, so I can't do that. Unlock it and ask again."}
    idle = _idle_seconds()
    limit = max_idle_seconds()
    if limit and idle is not None and idle > limit:
        return {"active": False, "state": "idle", "idle_seconds": idle,
                "reason": f"Your laptop hasn't been used for {int(idle // 60)} minutes, so I'm treating it as inactive."}
    window = ""
    try:
        from modules import screen_reader
        window = screen_reader.get_active_window()
    except Exception:  # noqa: BLE001
        pass
    return {"active": True, "state": "active", "reason": "", "window": window,
            "idle_seconds": idle, "lock_detection": locked is not None}


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------
def _available() -> dict[str, dict]:
    return {n: a for n, a in actions.ACTIONS.items() if n != "run_shell" or shell_allowed()}


def _step(name: str, args: dict) -> dict:
    return {"name": name, "args": args, "desc": actions.describe(name, args),
            "risk": actions.risk_of(name, args)}


_URLISH = re.compile(r"(?i)^(https?://\S+|www\.\S+|[a-z0-9-]+(\.[a-z0-9-]+)*\.(com|org|net|io|dev|in|ai|co|app|me|tv)(/\S*)?)$")


def quick_plan(text: str) -> tuple[list[dict], str] | None:
    """Plans for obvious one-liners, no model call. None = not obvious."""
    t = re.sub(r"(?i)^(hey |ok |okay )?(aura[, ]+)?(please |can you |could you )?", "", text.strip()).strip(" .!?")
    t = re.sub(r"(?i)\s+(please|for me|on my laptop|on the laptop|on my pc)$", "", t).strip(" .!?")
    low = t.lower()

    m = re.match(r"(?i)^(?:search|google|look up)(?: for)? (.+)$", t)
    if m:
        q = m.group(1)
        url = f"https://www.google.com/search?q={quote_plus(q)}"
        return [_step("open_url", {"url": url})], f"Searching for {q}."

    m = re.match(r"(?i)^(?:play|search) (.+) on youtube$", t)
    if m:
        q = m.group(1)
        url = f"https://www.youtube.com/results?search_query={quote_plus(q)}"
        return [_step("open_url", {"url": url})], f"Pulling up {q} on YouTube."

    m = re.match(r"(?i)^(?:open|launch|start|run) (.+)$", t)
    if m:
        target = m.group(1).strip()
        if " and " in target.lower() or " then " in target.lower():
            return None
        if _URLISH.match(target):
            return [_step("open_url", {"url": target})], f"Opening {target}."
        return [_step("open_app", {"name": target})], f"Opening {target}."

    m = re.match(r"(?i)^(?:switch to|go to|focus) (.+)$", t)
    if m and not _URLISH.match(m.group(1)):
        return [_step("focus_window", {"title": m.group(1)})], f"Switching to {m.group(1)}."

    if low in {"what's on my screen", "what is on my screen", "what's on screen",
               "read my screen", "read the screen", "what am i looking at"}:
        return [_step("read_screen", {})], "Here's what's on your screen."

    if low in {"close this", "close this window", "close the window", "close window"}:
        return [_step("close_window", {})], "Closing the active window."

    if low in {"save", "save it", "save this", "save the file"}:
        return [_step("hotkey", {"keys": ["ctrl", "s"]})], "Saved."
    return None


_PLAN_SYS = """You are AURA, operating your user's laptop because he asked you from his phone.
Turn his request into steps. Reply ONLY with lines in this form, nothing else:
  DO: <action> <json-params>
and finish with exactly one line:
  SAY: <one short, friendly sentence telling him what you did>

Actions:
{catalogue}

Rules:
- At most {max_steps} DO lines, in order.
- After open_app or open_url, add DO: wait {{"seconds": 2}} before typing into it.
- To search the web use open_url with https://www.google.com/search?q=<words+joined+by+plus>.
- type_text never presses enter. Add DO: press {{"key": "enter"}} only when he asked to send, submit, search or run.
- Never click without exact coordinates. Prefer keyboard: hotkeys, tab, enter.
- If it can't be done with these actions, or it's harmful, write NO DO lines, only SAY: with the reason.
- Never write explanations or markdown. Only DO and SAY lines."""

_LINE_RE = re.compile(r"(?i)^(do|fetch|action|step)\s*:\s*(.+)$")
_SAY_RE = re.compile(r"(?i)^say\s*:\s*(.+)$")


def parse_plan(reply: str) -> tuple[list[dict], str]:
    """Model reply → (steps, say). Unknown action names are dropped."""
    steps: list[dict] = []
    say = ""
    avail = _available()
    for raw in (reply or "").splitlines():
        line = raw.strip().strip("`*> -").strip()
        if not line:
            continue
        m = _SAY_RE.match(line)
        if m:
            say = m.group(1).strip()
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        rest = m.group(2).strip()
        if rest.lower().startswith("none"):
            continue
        parts = rest.split(None, 1)
        name = parts[0].strip().strip('"`,').lower()
        args: dict = {}
        if len(parts) > 1:
            try:
                parsed = json.loads(parts[1])
                if isinstance(parsed, dict):
                    args = parsed
            except Exception:  # noqa: BLE001
                args = {}
        if name in avail and len(steps) < MAX_STEPS:
            steps.append(_step(name, args))
    return steps, say


def _laptop_snapshot() -> str:
    lines = [f"OS: {platform.system() or 'unknown'}"]
    try:
        from modules import screen_reader
        lines.append(f"Active window: {screen_reader.get_active_window()}")
        titles = [t for t in screen_reader.list_window_titles() if t][:15]
        if titles:
            lines.append("Open windows: " + " | ".join(titles))
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(lines)


def plan(text: str) -> tuple[list[dict], str]:
    quick = quick_plan(text)
    if quick:
        return quick
    try:
        from core.ai_router import call_planner
    except Exception:  # noqa: BLE001
        return [], "I can't reach my planning model right now. Try a simpler command like “open chrome”."
    catalogue = "\n".join(
        line for line in actions.catalogue().splitlines()
        if line.split()[0] in _available()
    )
    system = _PLAN_SYS.format(catalogue=catalogue, max_steps=MAX_STEPS)
    prompt = f"LAPTOP RIGHT NOW:\n{_laptop_snapshot()}\n\nHIS REQUEST: {text}"
    try:
        reply = call_planner(prompt, system=system, max_tokens=600)
    except Exception:  # noqa: BLE001
        reply = ""
    if not reply or reply in {"RATE_LIMIT", "CONNECTION_ERROR", "ERROR"}:
        return [], "I can't reach my planning model right now. Try a simpler command like “open chrome”."
    steps, say = parse_plan(reply)
    if not steps and not say:
        say = "I couldn't work out how to do that on the laptop."
    return steps, say


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------
@dataclass
class Job:
    id: str
    text: str
    steps: list[dict]
    say: str
    status: str = "planned"   # planned|pending|running|done|failed|stopped|cancelled|declined|expired
    reply: str = ""
    results: list[dict] = field(default_factory=list)
    created: float = field(default_factory=time.time)
    finished: float = 0.0
    mode: str = "plan"        # plan = steps decided up front | vision = look, act, look again
    question: str = ""        # what a pending job is waiting on the phone to answer
    screen_version: int = 0   # bumps each time the vision loop takes a new screenshot

    def needs_confirm(self) -> bool:
        # A confirm-level step always asks, whatever the mode — "none" only
        # skips approval for plans made entirely of safe steps.
        if any(s["risk"] == "confirm" for s in self.steps):
            return True
        return confirm_mode() == "all" and bool(self.steps)

    def public(self) -> dict:
        return asdict(self)


_JOBS: dict[str, Job] = {}
_JOBS_LOCK = threading.Lock()
_RUN_LOCK = threading.Lock()


def _remember(job: Job) -> None:
    with _JOBS_LOCK:
        _JOBS[job.id] = job
        if len(_JOBS) > MAX_JOBS_KEPT:
            for old in sorted(_JOBS.values(), key=lambda j: j.created)[: len(_JOBS) - MAX_JOBS_KEPT]:
                _JOBS.pop(old.id, None)


def get_job(job_id: str) -> Job | None:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if job and job.mode == "plan" and job.status == "pending" and time.time() - job.created > PENDING_TTL:
        job.status = "expired"
        job.reply = "That plan expired. Send the command again."
    return job


def recent_jobs(limit: int = 10) -> list[dict]:
    with _JOBS_LOCK:
        jobs = sorted(_JOBS.values(), key=lambda j: j.created, reverse=True)[:limit]
    return [j.public() for j in jobs]


def _log(job: Job) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"ts": job.created, "id": job.id, "text": job.text, "status": job.status,
                 "steps": [{"name": s["name"], "args": s["args"]} for s in job.steps],
                 "results": job.results, "reply": job.reply}
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _announce(text: str) -> None:
    try:
        from core import activity
        activity.emit(f"📱 {text}", "task")
    except Exception:  # noqa: BLE001
        pass


def submit(text: str) -> Job:
    """Phone command in → a Job that is declined, pending approval, or finished."""
    text = (text or "").strip()[:MAX_COMMAND_CHARS]
    job = Job(id=uuid.uuid4().hex[:12], text=text, steps=[], say="")
    _remember(job)
    if not text:
        job.status, job.reply = "declined", "Tell me what to do."
        return job

    gate = presence()
    if not gate["active"]:
        job.status, job.reply = "declined", gate["reason"]
        _log(job)
        return job

    quick = quick_plan(text)
    if quick is None and vision_agent.available()[0]:
        return _start_vision(job)
    job.steps, job.say = quick or plan(text)
    if not job.steps:
        job.status = "declined"
        job.reply = job.say or "I couldn't work out how to do that on the laptop."
        _log(job)
        return job

    if job.needs_confirm():
        job.status = "pending"
        job.reply = "Here's my plan. Approve it and I'll go."
        _announce(f"Waiting for approval: {text}")
        return job
    return execute(job)


def approve(job_id: str) -> Job | None:
    job = get_job(job_id)
    if job is None or job.status != "pending":
        return job
    if job.mode == "vision":
        return _answer_vision(job, True)
    gate = presence()
    if not gate["active"]:
        job.status, job.reply = "declined", gate["reason"]
        _log(job)
        return job
    return execute(job)


def cancel(job_id: str) -> Job | None:
    job = get_job(job_id)
    if job and job.mode == "vision" and job.status == "pending":
        return _answer_vision(job, False)
    if job and job.status == "pending":
        job.status, job.reply = "cancelled", "Okay, I won't do it."
        _log(job)
    return job


def stop() -> None:
    actions.STOP.set()


def execute(job: Job) -> Job:
    if not _RUN_LOCK.acquire(blocking=False):
        job.status, job.reply = "declined", "I'm still doing the last thing you asked. Give me a second."
        return job
    try:
        actions.STOP.clear()
        job.status = "running"
        _announce(f"Remote: {job.text}")
        for i, step in enumerate(job.steps):
            if i:
                gate = presence()
                if not gate["active"]:
                    job.status = "stopped"
                    job.reply = f"Stopped after {i} of {len(job.steps)} steps. {gate['reason']}"
                    break
            _announce(step["desc"])
            try:
                ok, result = actions.run_action(step["name"], step["args"])
            except actions.Stopped as e:
                job.results.append({"step": step["desc"], "ok": False, "result": str(e)})
                job.status = "stopped"
                job.reply = f"Stopped after {i} of {len(job.steps)} steps."
                break
            job.results.append({"step": step["desc"], "ok": ok, "result": result})
            if not ok:
                job.status = "failed"
                done = f"Did {i} of {len(job.steps)} steps, then " if i else ""
                job.reply = f"{done}{step['desc'].lower()} didn't work: {result}"
                break
        else:
            job.status = "done"
            job.reply = job.say or "Done."
            reads = [r["result"] for r in job.results if r["step"] == "Read the screen"]
            if reads:
                job.reply += "\n\n" + reads[-1]
        job.finished = time.time()
        _announce(f"Remote {job.status}: {job.text}")
        _log(job)
        return job
    finally:
        actions.STOP.clear()
        _RUN_LOCK.release()


# ---------------------------------------------------------------------------
# Vision jobs: run in the background, the phone polls GET /jobs/{id}
# ---------------------------------------------------------------------------
_VISION: dict[str, dict] = {}   # job id → {"event", "answer", "screen", "started"}


def latest_screen(job_id: str) -> bytes | None:
    st = _VISION.get(job_id)
    return st["screen"] if st and st["screen"] else None


def _start_vision(job: Job) -> Job:
    job.mode = "vision"
    _VISION[job.id] = {"event": threading.Event(), "answer": None, "screen": b"", "started": False}
    if confirm_mode() == "all":
        job.status, job.question = "pending", "Want me to start on this?"
        job.reply = "I'll work it out on the screen as I go. Approve and I'll start."
        _announce(f"Waiting for approval: {job.text}")
        return job
    return _launch_vision(job)


def _launch_vision(job: Job) -> Job:
    if not _RUN_LOCK.acquire(blocking=False):
        job.status, job.reply = "declined", "I'm still doing the last thing you asked. Give me a second."
        return job
    _VISION[job.id]["started"] = True
    job.status, job.question, job.reply = "running", "", "On it, watching the screen."
    threading.Thread(target=_run_vision, args=(job,), name=f"aura-vision-{job.id}", daemon=True).start()
    return job


def _answer_vision(job: Job, yes: bool) -> Job:
    st = _VISION.get(job.id)
    if st is None:
        return job
    if not st["started"]:               # the up-front "start?" under confirm=all
        if not yes:
            job.status, job.question, job.reply = "cancelled", "", "Okay, I won't do it."
            _log(job)
            return job
        gate = presence()
        if not gate["active"]:
            job.status, job.question, job.reply = "declined", "", gate["reason"]
            _log(job)
            return job
        return _launch_vision(job)
    st["answer"] = yes
    st["event"].set()
    return job


class _VisionCtx:
    def __init__(self, job: Job) -> None:
        self.job = job
        self.state = _VISION[job.id]

    def check(self) -> str | None:
        if actions.STOP.is_set():
            return "Stopped, like you asked."
        gate = presence()
        return None if gate["active"] else gate["reason"]

    def ask(self, question: str) -> bool:
        job, st = self.job, self.state
        st["answer"] = None
        st["event"].clear()
        job.status, job.question = "pending", question
        job.reply = question
        _announce(f"Asking: {question}")
        deadline = time.time() + PENDING_TTL
        while not st["event"].wait(0.25):
            if actions.STOP.is_set() or time.time() > deadline:
                break
        yes = bool(st["answer"])
        job.status, job.question = "running", ""
        job.reply = "On it, watching the screen."
        return yes

    def record(self, desc: str, ok: bool, result: str) -> None:
        step = {"name": "vision", "args": {}, "desc": desc, "risk": "safe"}
        self.job.steps.append(step)
        self.job.results.append({"step": desc, "ok": ok, "result": result})
        _announce(desc)

    def show(self, screen) -> None:
        self.state["screen"] = screen.phone_jpeg
        self.job.screen_version += 1


def _run_vision(job: Job) -> None:
    try:
        actions.STOP.clear()
        _announce(f"Remote: {job.text}")
        try:
            status, reply = vision_agent.run(job.text, _VisionCtx(job))
        except actions.Stopped as e:
            status, reply = "stopped", f"Stopped ({e})."
        except Exception as e:  # noqa: BLE001
            status, reply = "failed", f"Something broke while I was working: {e}"
        job.status, job.reply, job.question = status, reply, ""
        job.finished = time.time()
        _announce(f"Remote {job.status}: {job.text}")
        _log(job)
    finally:
        actions.STOP.clear()
        _RUN_LOCK.release()
