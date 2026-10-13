"""
Tests for core.habits — AURA learning which apps you use, and when.

Covered here:
  1. naming: process / title → a short, privacy-safe label (never a raw title)
  2. crediting: time between samples goes to the app that was in front
  3. honesty: AFK, sleep gaps, AURA's own window and ignored apps earn nothing
  4. pause: turning habits off keeps nothing, not even unsaved time
  5. the store round-trip, the summary, and the chat prompt block
  6. forget wipes saved AND unsaved time

Uses a fake clock and a fake window reader, and a THROWAWAY DB.

Run:  PYTHONPATH=. python test_habits.py
"""

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="aura_habits_")
os.environ["AURA_TEST_DB"] = os.path.join(_TMP, "test.db")

import memory.store as mstore  # noqa: E402
mstore.DB_PATH = os.environ["AURA_TEST_DB"]
mstore.init_db()

from core import habits as H  # noqa: E402

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {label}")
    else:
        failed += 1
        print(f"  ✗ {label}")


print("\n[naming what's in front]")
L = H.label_for
check("VS Code by process", L("Code.exe", "brain.py - AURA - Visual Studio Code") == "VS Code")
check("a known site in a browser", L("chrome.exe", "lofi beats - YouTube - Google Chrome") == "YouTube")
check("unread-count prefix is ignored", L("msedge.exe", "(3) YouTube - Microsoft Edge") == "YouTube")
check("Gmail, not the email subject",
      L("chrome.exe", "Inbox (4) - me@gmail.com - Gmail - Google Chrome") == "Gmail")
check("an unknown page is just the browser",
      L("chrome.exe", "My secret medical results - Google Chrome") == "Chrome")
check("AURA's own window is skipped", L("electron.exe", "AURA") is None)
check("the lock screen is skipped", L("LockApp.exe", "") is None)
check("an unknown exe becomes its name", L("obsidian2.exe", "notes") == "Obsidian2")
check("no exe: app from the title", L("", "notes.txt - Notepad") == "Notepad")
check("no exe: browser + known site", L("", "Pull requests - GitHub - Google Chrome") == "GitHub")
check("no exe: a bare long title is not an app",
      L("", "this is a very long single window title with no app name at all") is None)
check("nothing at all → skipped", L("", "") is None)


class Fake:
    def __init__(self, now=None):
        self.now = now or time.mktime((2026, 10, 13, 22, 0, 0, 0, 0, -1))
        self.window = ("Code.exe", "x - Visual Studio Code")
        self.idle = 0.0
        self.cfg = {"enabled": True, "ignore": set()}

    def tracker(self):
        return H.HabitTracker(read=lambda: self.window, idle=lambda: self.idle,
                              settings=lambda: dict(self.cfg), clock=lambda: self.now)


def run(f, t, seconds, step=H.SAMPLE_SECONDS):
    end = f.now + seconds
    while f.now < end:
        f.now += step
        t.sample()


def secs(t, app):
    return sum(r[3] for r in t.pending_rows() if r[2] == app)


print("\n[crediting time]")
f = Fake()
t = f.tracker()
t.sample()
run(f, t, 600)
check("10 minutes of VS Code", secs(t, "VS Code") == 600)
f.window = ("chrome.exe", "video - YouTube - Google Chrome")
t.sample()   # switch sample: the interval before it still belongs to VS Code
run(f, t, 300)
check("5 minutes of YouTube after switching", secs(t, "YouTube") == 300)
check("current stretch is YouTube", (t.current() or {}).get("app") == "YouTube")
check("current stretch length", (t.current() or {}).get("seconds") == 300)
check("credited to the right hour", all(r[1] == 22 for r in t.pending_rows()))


print("\n[honest numbers]")
f = Fake()
t = f.tracker()
t.sample()
run(f, t, 60)
f.idle = H.AFK_SECONDS + 1
run(f, t, 1200)
f.idle = 0
t.sample()
run(f, t, 60)
check("AFK time is not credited", secs(t, "VS Code") == 120)

f = Fake()
t = f.tracker()
t.sample()
run(f, t, 60)
f.now += 3600            # laptop slept for an hour
t.sample()
run(f, t, 60)
check("a sleep gap is not credited", secs(t, "VS Code") == 120)

f = Fake()
t = f.tracker()
f.window = ("electron.exe", "AURA")
t.sample()
run(f, t, 300)
check("time in AURA herself is not credited", t.pending_rows() == [])

f = Fake()
f.cfg["ignore"] = {"youtube"}
t = f.tracker()
f.window = ("chrome.exe", "x - YouTube - Google Chrome")
t.sample()
run(f, t, 300)
check("an ignored app is not credited", t.pending_rows() == [])


print("\n[pause keeps nothing]")
f = Fake()
t = f.tracker()
t.sample()
run(f, t, 120)
f.cfg["enabled"] = False
t.refresh_settings()
t.sample()
check("pausing drops unsaved time", t.pending_rows() == [])
run(f, t, 300)
check("nothing accrues while paused", t.pending_rows() == [])
check("no current app while paused", t.current() is None)


print("\n[store, summary, prompt]")
f = Fake()
t = f.tracker()
H._tracker = t           # the module helpers read the shared tracker
t.sample()
run(f, t, 2 * 3600)      # 22:00 → 00:00 in VS Code
f.window = ("excel.exe", "budget.xlsx - Excel")
t.sample()
run(f, t, 40 * 60)
check("flush writes rows", t.flush() > 0)
check("nothing pending after a flush", t.pending_rows() == [])
stored = mstore.get_habit_usage("2026-10-01")
check("stored totals add up", sum(r[3] for r in stored) == 2 * 3600 + 40 * 60)

s = H.summary(now=f.now)
apps = [x["app"] for x in s["top"]]
check("VS Code is the top app", apps[:1] == ["VS Code"])
check("Excel is listed", "Excel" in apps)
vs = s["top"][0]
check("VS Code is a late-night habit", vs["part_of_day"] in {"nights", "late night"})
check("hour histogram has 24 slots", len(s["hours"]) == 24)
check("right now is Excel", (s["current"] or {}).get("app") == "Excel")

H._prompt_cache["ts"] = 0.0
short = H.prompt_block("hey", now=f.now)
check("ordinary turn gets one line", short.count("\n") == 0 and "VS Code" in short)
full = H.prompt_block("how much time did i spend on excel today?", now=f.now)
check("habit question gets the full block", "Usually" in full and "Today so far" in full)
check("full block names Excel right now", "Right now: Excel" in full)
check("habit question recognised", H.is_habit_question("what apps do i use the most?"))
check("ordinary chat is not a habit question", not H.is_habit_question("write me a sort"))

f.cfg["enabled"] = False
t.refresh_settings()
check("paused habits add nothing to the prompt", H.prompt_block("my habits", now=f.now) == "")
f.cfg["enabled"] = True
t.refresh_settings()


print("\n[forget]")
t.sample()
run(f, t, 120)
H.forget("Excel")
check("forgetting one app drops its unsaved time", secs(t, "Excel") == 0)
check("forgetting one app drops its stored time",
      all(r[2] != "Excel" for r in mstore.get_habit_usage("2026-10-01")))
check("other apps are kept", any(r[2] == "VS Code" for r in mstore.get_habit_usage("2026-10-01")))
H.forget()
check("forget all empties the store", mstore.get_habit_usage("2026-10-01") == [])


print("\n[the chat prompt carries it]")
# build_context_prompt reads the real clock, so this usage has to be recent.
f2 = Fake(now=time.time() - 3700)
t2 = f2.tracker()
H._tracker = t2
t2.sample()
run(f2, t2, 3600)
t2.flush()
H._prompt_cache["ts"] = 0.0
from core import brain  # noqa: E402
prompt = brain.build_context_prompt("what are my habits?", "CASUAL", "")
check("habits reached the prompt", "HOW THEY USE THEIR COMPUTER" in prompt)


print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
