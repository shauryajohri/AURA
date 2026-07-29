"""
Engagement tests — "is he actually working, or just not talking to me?"

The bug these protect against, verbatim from a real session:

    AURAproactive  Still no response, Claude's been quiet for a while now.
    You            yes i am doing some work
    AURAproactive  You've been quiet for a while, what's going on over there?

He was working the whole time. AttentionEngine measures silence TOWARD AURA
and treated it as absence, so a focused session and ignoring her looked
identical. Interrupting the first one is the worst thing a companion can do.

Run:  python test_engagement.py
"""

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="aura_engagement_test_")
os.environ["AURA_TEST_DB"] = os.path.join(_TMP, "eng.db")

import memory.store as store  # noqa: E402

store.DB_PATH = os.environ["AURA_TEST_DB"]
store.init_db()
store.init_tasks()
store.init_quests()

from core import engagement as E  # noqa: E402

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {label}")
    else:
        failed += 1
        print(f"  ✗ {label}")


VSCODE = {"app": "Visual Studio Code", "title": "quests.py - AURA", "visible_text": ""}
YOUTUBE = {"app": "Chrome", "title": "YouTube - One Piece Episode 1082", "visible_text": ""}
NEWTAB = {"app": "Chrome", "title": "New Tab", "visible_text": ""}

# ── 1. classification ───────────────────────────────────────────────────────
print("\n[1] what counts as work")
# Deliberately a MANUAL quest: engagement must still count it as work.
# Only time-crediting is restricted to time quests; "is he working" is not.
store.add_quest("Aura Code Base", 0, "", "custom", kind="manual")

work_cases = [
    ("code editor", {"app": "Visual Studio Code", "title": "brain.py"}, True),
    ("GitHub", {"app": "Chrome", "title": "shaurya/AURA - GitHub"}, True),
    ("Stack Overflow", {"app": "Chrome", "title": "Stack Overflow - asyncio"}, True),
    ("terminal", {"app": "Windows Terminal", "title": "pytest"}, True),
    ("Notion", {"app": "Notion", "title": "Project notes"}, True),
    ("an LLM chat about the project",
     {"app": "Claude", "title": "Claude",
      "visible_text": "the aura quest tracker and aura matcher, aura scoring"}, True),
    ("YouTube", YOUTUBE, False),
    ("Netflix", {"app": "Chrome", "title": "Netflix"}, False),
    ("Spotify", {"app": "Spotify", "title": "Discover Weekly"}, False),
    ("Instagram", {"app": "Chrome", "title": "instagram reels"}, False),
    ("an LLM chat about nothing",
     {"app": "Claude", "title": "Claude", "visible_text": "best pasta recipe"}, False),
    ("an empty tab", NEWTAB, False),
]
for label, ctx, expect in work_cases:
    check(f"{label} → {'working' if expect else 'not working'}",
          E.classify(ctx)["working"] is expect)

print("\n[1b] leisure beats the generic app list")
# proactive.WORK_APPS contains "chrome", so without an explicit leisure check
# a browser playing an episode counted as work.
check("a browser is not work by itself", not E.classify(YOUTUBE)["working"])
check("...and is labelled leisure", E.classify(YOUTUBE)["kind"] == "leisure")

# ── 2. the stretch, and the grace period ────────────────────────────────────
print("\n[2] work stretches")
t = E.EngagementTracker()
T = 1_000_000

check("not working before anything is seen", not t.is_working(T))

for i in range(40):                       # 20 minutes of coding
    t.observe(VSCODE, now=T + i * 30)
T20 = T + 40 * 30
check("working after 20 minutes", t.is_working(T20))
check("reports the elapsed minutes", t.state(T20)["minutes"] >= 19)

# A glance at a browser must not instantly make it "safe" to interrupt.
t.observe(NEWTAB, now=T20 + 30)
check("one glance away is still 'working'", t.is_working(T20 + 30))
t.observe(NEWTAB, now=T20 + 120)
check("two minutes away is still 'working'", t.is_working(T20 + 120))

for i in range(12):                       # 6 minutes off-work
    t.observe(YOUTUBE, now=T20 + 150 + i * 30)
T26 = T20 + 150 + 12 * 30
check("six minutes away ends the stretch", not t.is_working(T26))

print("\n[2b] AFK is not work")
t2 = E.EngagementTracker()
t2.observe(VSCODE, now=T)
t2.observe({}, afk=True, now=T + 30)
check("AFK sample reports not working", not t2.observe({}, afk=True, now=T + 60)["working"])

# ── 3. the debrief ──────────────────────────────────────────────────────────
print("\n[3] the debrief — she says what she saw")
hint = t.take_debrief(T26)
check("a finished stretch is available", hint is not None)
check("it knows roughly how long", hint and 18 * 60 <= hint["seconds"] <= 21 * 60)
check("consumed once, not repeated", t.take_debrief(T26) is None)

print("\n[3b] short stretches aren't worth mentioning")
t3 = E.EngagementTracker()
t3.observe(VSCODE, now=T)
t3.observe(VSCODE, now=T + 120)           # 2 minutes
for i in range(12):
    t3.observe(YOUTUBE, now=T + 150 + i * 30)
check("a 2-minute blip produces no debrief", t3.take_debrief(T + 600) is None)

print("\n[3c] talking to AURA ends the stretch")
t4 = E.EngagementTracker()
for i in range(40):
    t4.observe(VSCODE, now=T + i * 30)
d = t4.take_debrief(T + 40 * 30)
check("turning to her closes the session", d is not None)
check("...and she's no longer 'working'", not t4.is_working(T + 40 * 30))

print("\n[3d] a stale debrief is dropped")
t5 = E.EngagementTracker()
for i in range(40):
    t5.observe(VSCODE, now=T + i * 30)
for i in range(12):
    t5.observe(YOUTUBE, now=T + 1200 + i * 30)
late = T + 1200 + 12 * 30 + (E.DEBRIEF_TTL + 60)
check("nobody wants asking about this morning at 9pm",
      t5.take_debrief(late) is None)

print("\n[3e] the hint tells the model what to do")
t6 = E.EngagementTracker()
for i in range(60):
    t6.observe(VSCODE, now=T + i * 30)
E._TRACKER = t6
for i in range(12):
    t6.observe(YOUTUBE, now=T + 1800 + i * 30)
text = E.debrief_hint(T + 1800 + 12 * 30)
check("a hint is produced", bool(text))
check("it states the duration", text and "minutes" in text)
check("it asks for ONE question", text and "single specific question" in text)
check("it tells her not to gush", text and "congratulate" in text)

# ── 4. the gate other modules call ──────────────────────────────────────────
print("\n[4] is_working() — the gate")
E._TRACKER = None
check("safe with no tracker yet", E.is_working() in (True, False))

t7 = E.EngagementTracker()
E._TRACKER = t7
for i in range(40):
    t7.observe(VSCODE, now=T + i * 30)
check("True during a coding stretch", E.is_working(T + 40 * 30))
for i in range(14):
    t7.observe(YOUTUBE, now=T + 1200 + i * 30)
check("False once they're watching anime", not E.is_working(T + 1200 + 14 * 30))

print("\n[5] formatting")
check("minutes", E.describe_minutes(25 * 60) == "25 minutes")
check("one hour", E.describe_minutes(60 * 60) == "1 hour")
check("hours", E.describe_minutes(120 * 60) == "2 hours")
check("mixed", E.describe_minutes(95 * 60) == "1h35")

# ── 6. tasks: now / later / done + promotion ────────────────────────────────
print("\n[6] tasks — the backlog")
for row in store.get_tasks():
    store.delete_task(row[0])

a = store.add_task("Finish the quest matcher", "high", "now")
b = store.add_task("Read the asyncio docs", "medium", "later")
rows = {r[0]: r for r in store.get_tasks()}
check("bucket is stored", rows[a][6] == "now" and rows[b][6] == "later")
check("priority still works", rows[a][2] == "high")

store.set_task_bucket(b, "now")
check("moves later → now", {r[0]: r for r in store.get_tasks()}[b][6] == "now")
store.set_task_bucket(b, "later")
check("moves now → later", {r[0]: r for r in store.get_tasks()}[b][6] == "later")
store.set_task_bucket(b, "nonsense")
check("rejects a bogus bucket", {r[0]: r for r in store.get_tasks()}[b][6] == "later")

store.complete_task(a)
check("completing works", {r[0]: r for r in store.get_tasks()}[a][3] == "done")

print("\n[6b] promotion keeps the title verbatim")
from core.quest_presets import guess_preset  # noqa: E402

# parse_quest would strip "the"/"quest" and yield "Finish Matcher" — a task
# title is already deliberate, so promotion must not rewrite it.
title = "Finish the quest matcher"
check("preset is still guessed", guess_preset("Japanese revision") == "japanese")
qid = store.add_quest(title, 90, "", guess_preset(title))
q = next(x for x in store.get_quest_board()["quests"] if x["id"] == qid)
check("title survives intact", q["title"] == title)
check("target applied", q["target_minutes"] == 90)

print("\n" + "=" * 44)
print(f"{passed} passed, {failed} failed")
print("=" * 44)
sys.exit(1 if failed else 0)
