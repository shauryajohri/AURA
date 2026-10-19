"""
core/phone_report.py
--------------------
AURA rings your phone and reads you where things stand.

The report is spoken, so it is built as short paragraphs in the order you would
want to hear them if the call dropped halfway:

  1. what is waiting on YOU   uncommitted / unpushed work (commit and push both
                              need your confirm), features still in planning,
                              blockers, overdue tasks, quests awaiting proof
  2. what is coming up        calendar meetings (Microsoft 365, when connected),
                              reminders, tasks due today
  3. project progress         the same numbers the Domain dashboard shows
  4. tasks and quests         the companion side of the day

When it calls
-------------
  on demand    POST /api/phone-report/call, the Settings button, or just asking
               ("call me with my progress report")
  daily        once a day at `phone.daily_time`
  milestones   a feature or project reaching 100%, or a task becoming blocked
  meetings     optional heads-up `phone.meeting_lead` minutes before one starts

Automatic calls respect quiet hours and are never closer together than
MIN_GAP_MIN. Only a call you ask for ignores both.

Design notes
------------
* The call is placed through Twilio's REST API with the TwiML inline, so there
  is no webhook and nothing public to host — it works from 127.0.0.1. The cost
  of that: the call is one-way. Approving something still happens in AURA.
* Twilio credentials are read from .env (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
  TWILIO_FROM_NUMBER), like every other secret. The number to ring and the
  schedule live in app_settings under `phone.*`.
* Milestones are found by diffing a snapshot of the graph each tick rather than
  hooking every write path — commits, the board, Research capture and the chat
  can all move a task, and a diff catches all of them.
* Every reader is wrapped: a dead connector or a missing table shortens the
  report, it never stops the call.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import threading
import time
from typing import Any, Callable
from xml.sax.saxutils import escape

import requests

try:  # .env may not have been loaded yet if this is imported first
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # noqa: BLE001
    pass

TWILIO_API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
TIMEOUT = 20

# Twilio rejects inline TwiML over 4000 characters; leave room for escaping.
MAX_TWIML = 3800
MAX_PROJECTS = 5          # read from the brain
MAX_SPOKEN_PROJECTS = 3   # read out loud
MAX_ATTENTION = 6

TICK_SECONDS = 60
MIN_GAP_MIN = 30          # between two automatic calls
RETRY_AFTER_MIN = 10      # after a failed automatic call
DAILY_GRACE_MIN = 120     # how late the daily call may still go out
CALENDAR_TTL = 300

_E164 = re.compile(r"^\+[1-9]\d{7,14}$")

_CALL_RE = re.compile(
    r"\b(?:call|ring|phone)\s+(?:me|my\s+(?:phone|mobile|number))\b.*"
    r"\b(?:report|progress|update|status|brief(?:ing)?)\b"
    r"|\b(?:report|update|briefing)\b.*"
    r"\b(?:on|to|over)\s+(?:my\s+)?(?:phone|mobile|a\s+call)\b",
    re.I,
)


def is_call_request(text: str) -> bool:
    """True for "call me with my progress report" and its cousins."""
    return bool(text and _CALL_RE.search(text))


def _safe(fn: Callable[[], Any], default: Any) -> Any:
    try:
        return fn()
    except Exception:  # noqa: BLE001
        return default


# ── settings ─────────────────────────────────────────────────────────────────
def _settings() -> dict[str, Any]:
    from memory import store
    return store.get_settings()


def _save(patch: dict[str, Any]) -> None:
    from memory import store
    store.set_settings(patch)


def _twilio() -> tuple[str, str, str]:
    return (
        os.getenv("TWILIO_ACCOUNT_SID", "").strip(),
        os.getenv("TWILIO_AUTH_TOKEN", "").strip(),
        os.getenv("TWILIO_FROM_NUMBER", "").strip(),
    )


def normalize_number(raw: str) -> str:
    """'+91 98765-43210' -> '+919876543210'. '' when it isn't E.164."""
    n = re.sub(r"[\s\-().]", "", str(raw or ""))
    return n if _E164.match(n) else ""


def _mask(number: str) -> str:
    return f"{number[:3]}••••{number[-4:]}" if len(number) > 7 else number


def _minutes(hhmm: Any, fallback: int) -> int:
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", str(hhmm or ""))
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return fallback
    return int(m.group(1)) * 60 + int(m.group(2))


def in_quiet_hours(now: dt.datetime, s: dict[str, Any]) -> bool:
    start = _minutes(s.get("phone.quiet_start"), 22 * 60)
    end = _minutes(s.get("phone.quiet_end"), 8 * 60)
    if start == end:
        return False
    cur = now.hour * 60 + now.minute
    # 22:00 → 08:00 wraps midnight; 13:00 → 15:00 doesn't.
    return (start <= cur < end) if start < end else (cur >= start or cur < end)


# ── speech helpers ───────────────────────────────────────────────────────────
def _say(text: Any, limit: int = 90) -> str:
    """A title as something a voice can read: no markup, no paths, not endless."""
    t = re.sub(r"[`*_#>\[\]{}|\\]+", " ", str(text or ""))
    t = re.sub(r"\s+", " ", t).strip(" .")
    if len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0]
    return t


def _listing(items: list[str], n: int = 3) -> str:
    shown = [_say(i) for i in items[:n] if _say(i)]
    if not shown:
        return ""
    more = len(items) - len(shown)
    out = ", ".join(shown[:-1]) + (" and " if len(shown) > 1 else "") + shown[-1]
    return out + (f", plus {more} more" if more > 0 else "")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _clock(t: dt.datetime, now: dt.datetime) -> str:
    hour = t.strftime("%I").lstrip("0") or "12"
    stamp = f"{hour} {t.strftime('%p')}" if t.minute == 0 else f"{hour}:{t.strftime('%M %p')}"
    days = (t.date() - now.date()).days
    day = "today" if days == 0 else "tomorrow" if days == 1 else t.strftime("on %A")
    return f"{stamp} {day}"


# ── what the report is made of ───────────────────────────────────────────────
def _projects(now: dt.datetime, with_git: bool) -> list[dict[str, Any]]:
    from core.domain import brain_store, progress, project_brain
    today = now.strftime("%Y-%m-%d")
    out: list[dict[str, Any]] = []
    for p in brain_store.list_projects()[:MAX_PROJECTS]:
        pid = p["id"]
        prog = _safe(lambda: progress.overall(pid), {}) or {}
        events = _safe(lambda: project_brain.timeline(pid, 40), []) or []
        planning = _safe(lambda: brain_store.nodes(pid, "feature", "planning"), []) or []
        git: dict[str, Any] = {}
        root = p.get("root") or ""
        if with_git and root and os.path.isdir(root):
            from core import git_ops
            pre = _safe(lambda: git_ops.preview(root), {}) or {}
            if pre.get("ok"):
                git = {"branch": pre.get("branch", ""),
                       "uncommitted": pre.get("file_count", 0),
                       "unpushed": pre.get("ahead", 0)}
        out.append({
            "id": pid,
            "name": p.get("name") or "untitled project",
            "percent": prog.get("percent", 0),
            "total": prog.get("total", 0),
            "completed": prog.get("completed", 0),
            "in_progress": prog.get("in_progress", 0),
            "blocked": prog.get("blocked", 0),
            "remaining": prog.get("remaining", 0),
            "blocker": prog.get("biggest_blocker"),
            "features_done": [f["feature"] for f in prog.get("by_feature", [])
                              if f.get("total") and f.get("percent") == 100],
            "today": [e["title"] for e in events
                      if str(e.get("when") or "").startswith(today) and e.get("title")],
            "planning": [n["title"] for n in planning],
            "git": git,
        })
    return out


def _tasks(now: dt.datetime) -> dict[str, Any]:
    from memory import store
    today = now.strftime("%Y-%m-%d")
    rows = store.get_tasks()
    pending = [r for r in rows if r[3] == "pending"]
    due = lambda r: str(r[7] or "")[:10]  # noqa: E731
    return {
        "open": len(pending),
        "now": [r[1] for r in pending if r[6] == "now"],
        "done_today": [r[1] for r in rows
                       if r[3] == "done" and str(r[5] or "").startswith(today)],
        "due_today": [r[1] for r in pending if due(r) == today],
        "overdue": [r[1] for r in pending if due(r) and due(r) < today],
    }


def _quests() -> dict[str, Any]:
    from memory import store
    qs = store.get_quest_board().get("quests", [])
    return {
        "total": len(qs),
        "done": [q["title"] for q in qs if q["completed"]],
        "open": [q["title"] for q in qs if not q["completed"]],
        "needs_proof": [q["title"] for q in qs
                        if q["kind"] == "proof" and not q["completed"]],
    }


def _reminders(now: dt.datetime, hours: int = 24) -> list[dict[str, str]]:
    from memory.store import _connect
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT text, remind_at FROM reminders "
            "WHERE done = 0 AND remind_at >= ? AND remind_at <= ? ORDER BY remind_at",
            # a little way back too: one that just fired is still worth hearing
            ((now - dt.timedelta(hours=12)).isoformat(),
             (now + dt.timedelta(hours=hours)).isoformat()),
        ).fetchall()
    finally:
        conn.close()
    return [{"text": r[0], "at": r[1]} for r in rows]


_cal_cache: tuple[float, list[dict[str, Any]], str] = (0.0, [], "")


def _calendar(now: dt.datetime, hours: int = 24) -> tuple[list[dict[str, Any]], str]:
    """(meetings in the next `hours`, state). state is one of
    ok | not_connected | needs_reconnect | error."""
    global _cal_cache
    if time.time() - _cal_cache[0] < CALENDAR_TTL and _cal_cache[2]:
        return _cal_cache[1], _cal_cache[2]

    from core import connectors
    events: list[dict[str, Any]] = []
    state = "ok"
    try:
        if not connectors.status("microsoft").get("connected"):
            state = "not_connected"
        else:
            utc = dt.timezone.utc
            start = now.astimezone().astimezone(utc)
            end = start + dt.timedelta(hours=hours)
            fmt = "%Y-%m-%dT%H:%M:%SZ"
            data = connectors._get(
                "https://graph.microsoft.com/v1.0/me/calendarView", "microsoft",
                params={
                    "startDateTime": start.strftime(fmt),
                    "endDateTime": end.strftime(fmt),
                    "$orderby": "start/dateTime",
                    "$top": "15",
                    "$select": "id,subject,start,isAllDay,isCancelled",
                },
            )
            for ev in data.get("value", []):
                if ev.get("isCancelled") or ev.get("isAllDay"):
                    continue
                # Graph answers in UTC unless asked otherwise.
                raw = str((ev.get("start") or {}).get("dateTime") or "")[:19]
                when = dt.datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S")
                local = when.replace(tzinfo=utc).astimezone().replace(tzinfo=None)
                events.append({"id": ev.get("id", ""),
                               "title": ev.get("subject") or "a meeting",
                               "start": local.isoformat(timespec="minutes")})
    except requests.HTTPError as e:
        # Connected before the calendar scope was added: the token can't read it.
        code = getattr(e.response, "status_code", 0)
        state = "needs_reconnect" if code in (401, 403) else "error"
    except Exception:  # noqa: BLE001
        state = "error"
    _cal_cache = (time.time(), events, state)
    return events, state


def _attention(projects: list[dict[str, Any]], tasks: dict[str, Any],
               quests: dict[str, Any]) -> list[str]:
    """Everything that is stuck until you do something, most urgent first."""
    items: list[str] = []
    for p in projects:
        g = p.get("git") or {}
        bits = []
        if g.get("uncommitted"):
            bits.append(_plural(g["uncommitted"], "uncommitted file"))
        if g.get("unpushed"):
            bits.append(_plural(g["unpushed"], "commit") + " not pushed")
        if bits:
            items.append(f"{_say(p['name'])} has {' and '.join(bits)}, "
                         "waiting for your approval")
    for p in projects:
        b = p.get("blocker")
        if b:
            why = f", because {_say(b['reason'])}" if b.get("reason") else ""
            items.append(f"{_say(b['title'])} in {_say(p['name'])} is blocked{why}")
    if tasks.get("overdue"):
        items.append(f"{_plural(len(tasks['overdue']), 'task')} overdue: "
                     f"{_listing(tasks['overdue'])}")
    for p in projects:
        if p.get("planning"):
            n = len(p["planning"])
            items.append(f"{_plural(n, 'feature')} in {_say(p['name'])} "
                         f"{'is' if n == 1 else 'are'} still in planning: "
                         f"{_listing(p['planning'])}")
    if quests.get("needs_proof"):
        items.append("Still needing a screenshot to verify: "
                     f"{_listing(quests['needs_proof'])}")
    return items


def gather(now: dt.datetime | None = None, with_git: bool = True) -> dict[str, Any]:
    """The whole report as data. Never raises — a failed reader is just empty."""
    now = now or dt.datetime.now()
    projects = _safe(lambda: _projects(now, with_git), [])
    tasks = _safe(lambda: _tasks(now), {})
    quests = _safe(lambda: _quests(), {})
    meetings, calendar = _safe(lambda: _calendar(now), ([], "error"))
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "attention": _attention(projects, tasks, quests),
        "meetings": meetings,
        "calendar": calendar,
        "reminders": _safe(lambda: _reminders(now), []),
        "projects": projects,
        "tasks": tasks,
        "quests": quests,
    }


# ── the report, as something to say ──────────────────────────────────────────
def _project_line(p: dict[str, Any]) -> str:
    name = _say(p["name"])
    if not p.get("total"):
        line = f"{name} has no tasks planned yet."
    else:
        line = (f"{name} is {p['percent']} percent done: {p['completed']} of "
                f"{_plural(p['total'], 'task')} complete, {p['in_progress']} in "
                f"progress, {p['blocked']} blocked.")
    if p.get("today"):
        line += f" Today: {_listing(p['today'])}."
    return line


def script(report: dict[str, Any], reason: str = "") -> list[str]:
    """Paragraphs in speaking order. Each becomes one <Say> with a pause after."""
    now = _safe(lambda: dt.datetime.fromisoformat(report["generated_at"]),
                dt.datetime.now())
    out = ["Hi, this is AURA" + (f". {_say(reason, 200)}. Here is where things stand."
                                  if reason else " with your progress report.")]

    att = report.get("attention") or []
    if att:
        head = ("One thing is waiting on you." if len(att) == 1
                else f"{len(att)} things are waiting on you.")
        body = " ".join(f"{a}." for a in att[:MAX_ATTENTION])
        more = len(att) - MAX_ATTENTION
        out.append(f"{head} {body}" + (f" And {more} more in AURA." if more > 0 else ""))
    else:
        out.append("Nothing is waiting on your approval.")

    coming: list[str] = []
    meetings = report.get("meetings") or []
    if meetings:
        parts = []
        for m in meetings[:4]:
            when = _safe(lambda: _clock(dt.datetime.fromisoformat(m["start"]), now), "")
            parts.append(f"{_say(m['title'])} at {when}" if when else _say(m["title"]))
        more = len(meetings) - len(parts)
        coming.append(f"You have {_plural(len(meetings), 'meeting')} coming up: "
                      + "; ".join(parts) + (f"; and {more} more." if more > 0 else "."))
    elif report.get("calendar") == "ok":
        coming.append("No meetings in the next 24 hours.")
    reminders = report.get("reminders") or []
    if reminders:
        coming.append(f"Reminders: {_listing([r['text'] for r in reminders])}.")
    tasks = report.get("tasks") or {}
    if tasks.get("due_today"):
        coming.append(f"Due today: {_listing(tasks['due_today'])}.")
    if coming:
        out.append(" ".join(coming))

    projects = report.get("projects") or []
    if projects:
        lines = [_project_line(p) for p in projects[:MAX_SPOKEN_PROJECTS]]
        more = len(projects) - MAX_SPOKEN_PROJECTS
        if more > 0:
            lines.append(f"{_plural(more, 'other project')} unchanged.")
        out.append(" ".join(lines))

    day: list[str] = []
    if tasks.get("open") or tasks.get("done_today"):
        day.append(f"On your list: {_plural(tasks.get('open', 0), 'open task')}, "
                   f"{len(tasks.get('done_today', []))} finished today.")
    quests = report.get("quests") or {}
    if quests.get("total"):
        line = f"Quests: {len(quests['done'])} of {quests['total']} complete."
        if quests.get("open"):
            line += f" Still open: {_listing(quests['open'])}."
        day.append(line)
    if day:
        out.append(" ".join(day))

    out.append("That is everything. Open AURA to act on anything that needs "
               "your approval. Goodbye.")
    return out


def twiml(paragraphs: list[str], voice: str = "") -> str:
    """Inline TwiML. If it would be too long for Twilio, the least urgent
    paragraphs go first — the opener, what's waiting on you, and the sign-off
    always survive."""
    if not re.fullmatch(r"(?:Polly|Google)\.[A-Za-z0-9.\-]+|alice|man|woman", voice or ""):
        voice = "Polly.Joanna"
    parts = list(paragraphs)

    def build(ps: list[str]) -> str:
        says = "".join(f'<Say voice="{voice}">{escape(p)}</Say><Pause length="1"/>'
                       for p in ps if p)
        return f'<Response><Pause length="1"/>{says}</Response>'

    while len(build(parts)) > MAX_TWIML and len(parts) > 3:
        parts.pop(-2)
    xml = build(parts)
    if len(xml) > MAX_TWIML and len(parts) >= 3:  # one enormous paragraph — clip it
        room = MAX_TWIML - len(build([parts[0], "", parts[-1]]))
        xml = build([parts[0], parts[1][:max(0, room - 200)], parts[-1]])
    return xml


# ── placing the call ─────────────────────────────────────────────────────────
def status() -> dict[str, Any]:
    """What the Settings panel shows. Never includes a secret."""
    s = _settings()
    sid, token, sender = _twilio()
    missing = [name for name, v in (("TWILIO_ACCOUNT_SID", sid),
                                    ("TWILIO_AUTH_TOKEN", token),
                                    ("TWILIO_FROM_NUMBER", sender)) if not v]
    number = normalize_number(s.get("phone.number", ""))
    return {
        "enabled": bool(s.get("phone.enabled")),
        "twilio_configured": not missing,
        "missing_env": missing,
        "number_valid": bool(number),
        "number": _mask(number) if number else "",
        "ready": bool(number) and not missing,
        "quiet_now": in_quiet_hours(dt.datetime.now(), s),
        "last": s.get("phone.last") or None,
    }


def place_call(reason: str = "", kind: str = "manual",
               now: dt.datetime | None = None) -> dict[str, Any]:
    """Build the report and ring the phone. Returns {"ok", "sid" | "error"}."""
    now = now or dt.datetime.now()
    s = _settings()
    sid, token, sender = _twilio()
    number = normalize_number(s.get("phone.number", ""))
    if not (sid and token and sender):
        return {"ok": False, "error": "Twilio isn't configured — add TWILIO_ACCOUNT_SID, "
                                      "TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER to .env"}
    if not number:
        return {"ok": False, "error": "No valid phone number saved — use the "
                                      "international form, e.g. +919876543210"}

    report = gather(now)
    xml = twiml(script(report, reason), str(s.get("phone.voice") or ""))
    result: dict[str, Any]
    try:
        res = requests.post(
            TWILIO_API.format(sid=sid), auth=(sid, token), timeout=TIMEOUT,
            data={"To": number, "From": sender, "Twiml": xml},
        )
        body = _safe(res.json, {}) or {}
        if res.status_code >= 400:
            result = {"ok": False, "error": body.get("message")
                      or f"Twilio returned {res.status_code}"}
        else:
            result = {"ok": True, "sid": body.get("sid", ""),
                      "status": body.get("status", "queued")}
    except Exception as e:  # noqa: BLE001
        result = {"ok": False, "error": f"couldn't reach Twilio: {e}"}

    result.update({"kind": kind, "to": _mask(number)})
    _safe(lambda: _save({"phone.last": {
        "when": now.isoformat(timespec="seconds"), "kind": kind,
        "ok": result["ok"], "error": result.get("error", ""),
    }}), None)
    print(f"[AURA phone] {kind} call to {_mask(number)}: "
          f"{'placed' if result['ok'] else result.get('error')}")
    return result


# ── the scheduler ────────────────────────────────────────────────────────────
def _snapshot() -> dict[str, list[str]]:
    """Just enough of the graph to notice a milestone. No git, no network."""
    from core.domain import brain_store, progress
    feats: list[str] = []
    done: list[str] = []
    blocked: list[str] = []
    for p in brain_store.list_projects():
        prog = progress.overall(p["id"])
        if prog["total"] and prog["percent"] == 100:
            done.append(p["id"])
        feats += [f["feature_id"] for f in prog["by_feature"]
                  if f["total"] and f["percent"] == 100]
        blocked += [t["id"] for t in brain_store.nodes(p["id"], "task", "blocked")]
    return {"features": sorted(feats), "projects": sorted(done), "blocked": sorted(blocked)}


def _milestones(seen: dict[str, list[str]] | None,
                snap: dict[str, list[str]]) -> list[str]:
    """What became true since the last look, as sentences. [] on the first look
    — otherwise every finished feature would ring the phone on first run."""
    if not seen:
        return []
    from core.domain import brain_store

    def title(nid: str) -> str:
        n = _safe(lambda: brain_store.get_node(nid), None)
        return _say((n or {}).get("title") or "something")

    out: list[str] = []
    for pid in set(snap["projects"]) - set(seen.get("projects", [])):
        p = _safe(lambda: brain_store.get_project(pid), None) or {}
        out.append(f"{_say(p.get('name') or 'A project')} just reached 100 percent")
    for fid in set(snap["features"]) - set(seen.get("features", [])):
        out.append(f"The feature {title(fid)} is complete")
    for tid in set(snap["blocked"]) - set(seen.get("blocked", [])):
        out.append(f"The task {title(tid)} is now blocked")
    return out


def tick(now: dt.datetime | None = None) -> dict[str, Any] | None:
    """One scheduler pass. Returns the call result when it rang the phone."""
    now = now or dt.datetime.now()
    s = _settings()
    before = s.get("phone.state") or {}
    state = dict(before)

    snap = _safe(_snapshot, None)
    if snap is not None:
        pending = list(state.get("pending", [])) + _milestones(state.get("seen"), snap)
        state["seen"] = snap
        state["pending"] = pending[-8:]

    ready = bool(s.get("phone.enabled")) and status()["ready"]
    if not ready or not s.get("phone.milestones"):
        state["pending"] = []     # nothing queues up while calls are off

    result = None
    backoff = time.time() - float(state.get("failed_at") or 0) < RETRY_AFTER_MIN * 60
    if ready and not in_quiet_hours(now, s) and not backoff:
        today = now.strftime("%Y-%m-%d")
        cur = now.hour * 60 + now.minute
        daily_at = _minutes(s.get("phone.daily_time"), 9 * 60)
        gap_ok = time.time() - float(state.get("called_at") or 0) >= MIN_GAP_MIN * 60

        soon = None
        if s.get("phone.meeting_alert"):
            lead = max(1, int(s.get("phone.meeting_lead") or 15))
            for m in _safe(lambda: _calendar(now)[0], []):
                mins = (dt.datetime.fromisoformat(m["start"]) - now).total_seconds() / 60
                if 0 <= mins <= lead and m["id"] not in state.get("alerted", []):
                    soon = (m, round(mins))
                    break

        if soon:
            m, mins = soon
            state["alerted"] = (list(state.get("alerted", [])) + [m["id"]])[-30:]
            result = place_call(f"{_say(m['title'])} starts in "
                                f"{_plural(mins, 'minute')}", "meeting", now)
        elif (s.get("phone.daily") and state.get("daily") != today
              and daily_at <= cur < daily_at + DAILY_GRACE_MIN):
            result = place_call("", "daily", now)
            if result["ok"]:
                state["daily"] = today
        elif state.get("pending") and gap_ok:
            result = place_call(". ".join(state["pending"][:3]), "milestone", now)

        if result is not None:
            if result["ok"]:
                state["called_at"] = time.time()
                state["pending"] = []
                state.pop("failed_at", None)
            else:
                state["failed_at"] = time.time()

    if state != before:
        _safe(lambda: _save({"phone.state": state}), None)
    return result


_started = False


def start_loop() -> None:
    """Start the daily / milestone scheduler. Idempotent."""
    global _started
    if _started:
        return
    _started = True

    def _loop() -> None:
        while True:
            time.sleep(TICK_SECONDS)
            try:
                tick()
            except Exception as e:  # noqa: BLE001 — never let a report kill the loop
                print(f"[AURA phone] tick failed: {e}")

    threading.Thread(target=_loop, daemon=True, name="aura-phone-report").start()
