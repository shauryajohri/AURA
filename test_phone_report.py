"""
Tests for core.phone_report — AURA ringing your phone with a progress report.

Covered here:
  1. the report is built from the real graph, tasks and quests
  2. what's waiting on you is spoken before anything else
  3. the TwiML stays under Twilio's limit and survives awkward titles
  4. nothing is dialled without credentials and a valid number
  5. the scheduler: daily once, milestones only for NEW events, quiet hours
     and the gap between automatic calls are respected

Runs on a THROWAWAY DB and a fake Twilio. Never places a real call.

Run:  PYTHONPATH=. python test_phone_report.py
"""

import datetime as dt
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="aura_phone_report_")

import memory.store as mstore  # noqa: E402
mstore.DB_PATH = os.path.join(_TMP, "test.db")
mstore.init_db()
mstore.init_tasks()

from core.domain import brain_store  # noqa: E402
brain_store.DB_PATH = mstore.DB_PATH
brain_store._connect = mstore._connect
brain_store.init_db()

from core import phone_report as pr  # noqa: E402
from core.domain import project_brain  # noqa: E402

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {label}")
    else:
        failed += 1
        print(f"  ✗ {label}")


# ── a fake Twilio, and no calendar ───────────────────────────────────────────
CALLS: list[dict] = []
TWILIO_OK = True


class _Res:
    def __init__(self, code, body):
        self.status_code, self._body = code, body

    def json(self):
        return self._body


def _fake_post(url, auth=None, data=None, timeout=None):
    CALLS.append({"url": url, "auth": auth, "data": data})
    if TWILIO_OK:
        return _Res(201, {"sid": "CA123", "status": "queued"})
    return _Res(401, {"message": "Authenticate"})


pr.requests.post = _fake_post
MEETINGS: list[dict] = []
pr._calendar = lambda now, hours=24: (MEETINGS, "ok")

for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER"):
    os.environ.pop(k, None)

NOW = dt.datetime(2026, 10, 13, 9, 5)


print("\n[asking for a call]")
for q in ["call me with my progress report", "ring my phone with an update",
          "send the progress report to my phone", "give me the briefing over a call"]:
    check(f"call request: {q!r}", pr.is_call_request(q))
for q in ["call the function twice", "what's my progress", "write a report on MVCC",
          "my phone is dead"]:
    check(f"not a call request: {q!r}", not pr.is_call_request(q))


print("\n[phone numbers]")
check("spaces and dashes are tidied", pr.normalize_number("+91 98765-43210") == "+919876543210")
check("no country code is refused", pr.normalize_number("9876543210") == "")
check("empty is refused", pr.normalize_number("") == "")


print("\n[quiet hours]")
quiet = {"phone.quiet_start": "22:00", "phone.quiet_end": "08:00"}
check("23:30 is quiet", pr.in_quiet_hours(NOW.replace(hour=23, minute=30), quiet))
check("07:59 is quiet", pr.in_quiet_hours(NOW.replace(hour=7, minute=59), quiet))
check("08:00 is not", not pr.in_quiet_hours(NOW.replace(hour=8, minute=0), quiet))
check("same start and end means never",
      not pr.in_quiet_hours(NOW, {"phone.quiet_start": "00:00", "phone.quiet_end": "00:00"}))


print("\n[an empty AURA still has something to say]")
rep = pr.gather(NOW, with_git=False)
say = pr.script(rep)
check("no projects, no crash", rep["projects"] == [])
check("opens by naming itself", say[0].startswith("Hi, this is AURA"))
check("says nothing is waiting", "Nothing is waiting" in say[1])
check("signs off", "Goodbye" in say[-1])


print("\n[a real project]")
p = project_brain.create_project("Portfolio *v2*")
pid = p["id"]
auth = project_brain.add_feature(pid, "Auth")
t1 = project_brain.add_task(pid, "Login form", feature_id=auth["id"], status="done")
t2 = project_brain.add_task(pid, "OAuth callback", feature_id=auth["id"], status="in_progress")
t3 = project_brain.add_task(pid, "Deploy pipeline", status="todo")
project_brain.add_feature(pid, "Dark mode", status="planning")
project_brain.set_task_status(pid, t3["id"], "blocked", reason="no hosting account yet")

mstore.add_task("Renew the domain", due="2026-10-10")
mstore.add_task("Send invoice", due="2026-10-13")
mstore.save_reminder("Dentist", NOW + dt.timedelta(hours=3))
MEETINGS.append({"id": "ev1", "title": "Design review",
                 "start": (NOW + dt.timedelta(hours=2)).isoformat(timespec="minutes")})

rep = pr.gather(NOW, with_git=False)
proj = rep["projects"][0]
check("progress matches the graph", (proj["completed"], proj["total"], proj["blocked"]) == (1, 3, 1))
check("the blocker is flagged with its reason",
      any("Deploy pipeline" in a and "no hosting account" in a for a in rep["attention"]))
check("overdue task is flagged", any("overdue" in a and "Renew the domain" in a for a in rep["attention"]))
check("planning feature is flagged", any("Dark mode" in a for a in rep["attention"]))
check("task due today is separate from overdue", rep["tasks"]["due_today"] == ["Send invoice"])

say = pr.script(rep)
text = " ".join(say)
check("what's waiting on you comes right after the greeting", "waiting on you" in say[1])
check("the meeting is read with its time", "Design review at 11:05 AM today" in text)
check("the reminder is read", "Dentist" in text)
check("project line has the numbers", "33 percent done: 1 of 3 tasks complete" in text)
check("markup is not read aloud", "*" not in text)

say = pr.script(rep, "The feature Auth is complete")
check("a milestone call says why it rang", "The feature Auth is complete" in say[0])


print("\n[TwiML]")
xml = pr.twiml(pr.script(rep))
check("is a single Response", xml.startswith("<Response>") and xml.endswith("</Response>"))
check("special characters are escaped", "&amp;" in pr.twiml(["a", "R&D <sync>", "z"]))
long = ["hello"] + [f"paragraph {i} " + "word " * 150 for i in range(12)] + ["bye"]
xml = pr.twiml(long)
check("long reports are trimmed under Twilio's limit", len(xml) <= pr.MAX_TWIML)
check("…keeping the opener and the sign-off", "hello" in xml and "bye" in xml)
check("…and the most urgent paragraph", "paragraph 0" in xml)
check("one giant paragraph is clipped, not rejected",
      len(pr.twiml(["hi", "x" * 9000, "bye"])) <= pr.MAX_TWIML)
check("a bad voice name can't break the XML",
      'voice="Polly.Joanna"' in pr.twiml(["a", "b", "c"], '"><Dial>'))


print("\n[nothing is dialled until it's set up]")
res = pr.place_call(now=NOW)
check("no Twilio credentials → refused", not res["ok"] and "TWILIO_ACCOUNT_SID" in res["error"])
os.environ.update({"TWILIO_ACCOUNT_SID": "ACtest", "TWILIO_AUTH_TOKEN": "tok",
                   "TWILIO_FROM_NUMBER": "+15005550006"})
res = pr.place_call(now=NOW)
check("no number saved → refused", not res["ok"] and "phone number" in res["error"])
check("…and Twilio was never contacted", CALLS == [])
check("status lists nothing missing but isn't ready", pr.status()["twilio_configured"]
      and not pr.status()["ready"])

mstore.set_settings({"phone.number": "+91 98765 43210"})
res = pr.place_call(now=NOW)
check("with both, the call is placed", res["ok"] and res["sid"] == "CA123")
check("to the saved number, from the Twilio one",
      CALLS[-1]["data"]["To"] == "+919876543210" and CALLS[-1]["data"]["From"] == "+15005550006")
check("the report rides inline as TwiML", "Portfolio" in CALLS[-1]["data"]["Twiml"])
check("the result never echoes the full number", "98765" not in str(res))
check("status never includes the token", "tok" not in str(pr.status().values()))


print("\n[the scheduler]")
mstore.set_settings({"phone.state": {}})
CALLS.clear()
check("disabled → no call, even at the daily time", pr.tick(NOW) is None and CALLS == [])

mstore.set_settings({"phone.enabled": True, "phone.daily_time": "09:00"})
r = pr.tick(NOW)
check("enabled at 09:05 → the daily call goes out", r and r["kind"] == "daily" and len(CALLS) == 1)
check("…once", pr.tick(NOW + dt.timedelta(minutes=1)) is None and len(CALLS) == 1)
check("…and not again that afternoon", pr.tick(NOW.replace(hour=15)) is None)

pr.MIN_GAP_MIN = 0
check("work that was already done doesn't ring the phone", pr.tick(NOW) is None)
project_brain.set_task_status(pid, t2["id"], "done")        # Auth: 2 of 2
r = pr.tick(NOW.replace(hour=11))
check("a feature finishing does", r and r["kind"] == "milestone")
check("…and the call says which", "The feature Auth is complete" in CALLS[-1]["data"]["Twiml"])
check("…once", pr.tick(NOW.replace(hour=11, minute=1)) is None)

t4 = project_brain.add_task(pid, "Write docs")
project_brain.set_task_status(pid, t4["id"], "blocked")
n = len(CALLS)
check("a block at 23:00 waits for morning", pr.tick(NOW.replace(hour=23)) is None and len(CALLS) == n)
r = pr.tick(NOW.replace(day=14, hour=10, minute=0, second=0) + dt.timedelta(hours=2))
check("…and is delivered after quiet hours", r and "Write docs" in CALLS[-1]["data"]["Twiml"])

pr.MIN_GAP_MIN = 30
t5 = project_brain.add_task(pid, "Fix footer")
project_brain.set_task_status(pid, t5["id"], "blocked")
check("two milestone calls are never back to back",
      pr.tick(NOW.replace(day=14, hour=12, minute=5)) is None)
pr.MIN_GAP_MIN = 0

mstore.set_settings({"phone.milestones": False})
t6 = project_brain.add_task(pid, "Polish hero")
project_brain.set_task_status(pid, t6["id"], "blocked")
check("milestones switched off → silence",
      pr.tick(NOW.replace(day=14, hour=13)) is None)
mstore.set_settings({"phone.milestones": True})
check("…and nothing is saved up for when they're switched back on",
      pr.tick(NOW.replace(day=14, hour=13, minute=1)) is None)

MEETINGS[:] = [{"id": "ev2", "title": "Standup",
                "start": NOW.replace(day=14, hour=14, minute=10).isoformat(timespec="minutes")}]
at = NOW.replace(day=14, hour=14, minute=0)
check("meeting heads-up is off unless asked for", pr.tick(at) is None)
mstore.set_settings({"phone.meeting_alert": True, "phone.meeting_lead": 15})
r = pr.tick(at)
check("switched on → rings before the meeting", r and r["kind"] == "meeting")
check("…saying how long is left", "Standup starts in 10 minutes" in CALLS[-1]["data"]["Twiml"])
check("…once per meeting", pr.tick(at + dt.timedelta(minutes=1)) is None)
mstore.set_settings({"phone.meeting_alert": False})

TWILIO_OK = False
mstore.set_settings({"phone.daily_time": "16:00"})
n = len(CALLS)
r = pr.tick(NOW.replace(day=14, hour=16, minute=0))
check("a failed daily call reports the error", r and not r["ok"] and "Authenticate" in r["error"])
check("…and is not hammered every minute",
      pr.tick(NOW.replace(day=14, hour=16, minute=1)) is None and len(CALLS) == n + 1)
check("…and the failure shows in status", pr.status()["last"]["ok"] is False)


print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
