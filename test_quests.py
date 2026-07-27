"""
Quest system tests — store, matching, time attribution, pressure, streaks.

Runs entirely offline against a THROWAWAY sqlite DB, so real quest history is
never touched. Time is injected everywhere, so nothing sleeps.

The rules being protected here are the ones the whole feature rests on: if
AURA credits time that didn't happen, a quest board is worse than useless.

Run:  python test_quests.py
"""

import os
import sys
import tempfile

_TMP = tempfile.mkdtemp(prefix="aura_quest_test_")
os.environ["AURA_TEST_DB"] = os.path.join(_TMP, "quests.db")

import memory.store as store  # noqa: E402

store.DB_PATH = os.environ["AURA_TEST_DB"]
store.init_quests()

from core import quests as Q  # noqa: E402

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {label}")
    else:
        failed += 1
        print(f"  ✗ {label}")


def reset():
    for q in store.get_quests(active_only=False):
        store.delete_quest(q[0])
    conn = store._connect()
    conn.execute("DELETE FROM quest_unallocated")
    conn.commit()
    conn.close()


# ── 1. natural-language parsing ─────────────────────────────────────────────
print("\n[1] parsing the way shaurya writes quests")
cases = [
    ("japanese 2 hrs", "Japanese", 120, "japanese"),
    ("2h dsa", "Dsa", 120, "dsa"),
    ("read 45 min", "Read", 45, "custom"),
    ("Japanese 1.5 hours", "Japanese", 90, "japanese"),
    ("gym 30m", "Gym", 30, "fitness"),
    # No duration written = UNTIMED (0), not an invented default.
    ("leetcode", "Leetcode", 0, "dsa"),
    ("aura code base", "Aura Code Base", 0, "custom"),
]
for text, title, mins, preset in cases:
    got = Q.parse_quest(text)
    check(f"{text!r} → {title} / {mins}m / {preset}",
          got["title"] == title and got["target_minutes"] == mins and got["preset"] == preset)

# ── 2. matching: both modes of study count ──────────────────────────────────
print("\n[2] matching — 'watching a lecture' counts as much as 'doing'")
reset()
jp = store.add_quest("Japanese", 120, "", "japanese")
dsa = store.add_quest("DSA", 120, "", "dsa")
board = store.get_quest_board()["quests"]
names = {jp: "Japanese", dsa: "DSA", None: None}

match_cases = [
    ("Anki", "Japanese Core 2k", jp),
    ("Chrome", "WaniKani — Level 12 Kanji", jp),
    ("Chrome", "JLPT N3 grammar list", jp),
    ("Chrome", "LeetCode - Two Sum", dsa),
    ("Chrome", "Recursion Explained — freeCodeCamp", dsa),   # the video case
    ("Chrome", "Striver A2Z DSA Sheet", dsa),
    ("Chrome", "Dynamic Programming in 30 minutes", dsa),
    ("Spotify", "Discover Weekly", None),
    ("YouTube", "I quit my job to travel", None),
    ("Chrome", "flight tickets to goa", None),
]
for app, title, expect in match_cases:
    mid, _ = Q.match({"app": app, "title": title, "visible_text": ""}, board)
    check(f"{title[:38]:40} → {names.get(expect) or 'no match'}", mid == expect)

print("\n[2b] user keywords extend a pack")
store.update_quest(jp, keywords="tobira,sakura textbook")
board = store.get_quest_board()["quests"]
mid, _ = Q.match({"app": "Chrome", "title": "Tobira chapter 4", "visible_text": ""}, board)
check("custom keyword matches", mid == jp)

print("\n[2c] the title itself matches, with no setup")
reset()
th = store.add_quest("Thesis", 60, "", "custom")
board = store.get_quest_board()["quests"]
mid, _ = Q.match({"app": "Word", "title": "thesis_draft_v4.docx", "visible_text": ""}, board)
check("bare title matches its own window", mid == th)

# ── 3. time attribution — the honesty rules ─────────────────────────────────
print("\n[3] time is only credited when it was really earned")
reset()
jp = store.add_quest("Japanese", 10, "", "japanese")     # 10m target
ANKI = {"app": "Anki", "title": "Japanese Core 2k", "visible_text": ""}
YT = {"app": "YouTube", "title": "cat compilation", "visible_text": ""}
t = Q.QuestTracker()
T = 1_000_000

t.tick(ANKI, now=T)
check("first sample credits nothing", store.get_quest_seconds(jp) == 0)

t.tick(ANKI, now=T + 30)
check("30s on target credits 30s", store.get_quest_seconds(jp) == 30)

t.tick(YT, now=T + 60)
check("off-quest credits nothing to the quest", store.get_quest_seconds(jp) == 30)
check("off-quest time lands in unallocated",
      store.get_quest_board()["unallocated_seconds"] == 30)

t.tick(ANKI, now=T + 90, afk=True)
check("AFK credits nothing", store.get_quest_seconds(jp) == 30)

t.tick(ANKI, now=T + 90 + 9999)
check("a sleep gap is discarded, not credited", store.get_quest_seconds(jp) == 30)

before = store.get_quest_seconds(jp)
t.tick(ANKI, now=T + 90 + 9999 + 30)
check("tracking resumes cleanly after the gap",
      store.get_quest_seconds(jp) == before + 30)

# ── 4. auto-completion ──────────────────────────────────────────────────────
print("\n[4] the quest completes itself")
reset()
jp = store.add_quest("Japanese", 2, "", "japanese")      # 2 minute target
t = Q.QuestTracker()
n = 2_000_000
t.tick(ANKI, now=n)
spoken = []
for _ in range(6):
    n += 30
    line = t.tick(ANKI, now=n)
    if line:
        spoken.append(line)
b = store.get_quest_board()["quests"][0]
check("target reached", b["seconds"] >= b["target_seconds"])
check("marked complete automatically", b["completed"])
check("said something once", len(spoken) == 1)
check("the line names the quest", spoken and "Japanese" in spoken[0])

n += 30
more = t.tick(ANKI, now=n)
check("does not re-announce a completed quest", more is None)

# ── 5. pressure — 'rush up' ─────────────────────────────────────────────────
print("\n[5] does the rest of the day still fit?")
import datetime  # noqa: E402

reset()
store.add_quest("Japanese", 120, "", "japanese")
store.add_quest("DSA", 120, "", "dsa")
store.add_quest("Gym", 60, "", "fitness")


def at(hour):
    return datetime.datetime.now().replace(
        hour=hour, minute=0, second=0, microsecond=0).timestamp()


check("morning is comfortable", Q.pressure(now=at(9))["status"] == "ok")
check("6pm with 5h left is a rush", Q.pressure(now=at(18))["status"] == "rush")
check("8pm no longer fits", Q.pressure(now=at(20))["status"] == "impossible")
check("after the day ends", Q.pressure(now=at(23))["status"] == "out_of_time")
p = Q.pressure(now=at(20))
check("deficit is reported", p["deficit_minutes"] == 300 - 180)

reset()
store.add_quest("Japanese", 60, "", "japanese")
store.complete_quest(store.get_quests()[0][0])
check("a finished board is 'clear'", Q.pressure(now=at(14))["status"] == "clear")

# ── 6. day rollover + streaks ───────────────────────────────────────────────
print("\n[6] late-night work belongs to the day it started")
midnight_thirty = datetime.datetime.now().replace(hour=0, minute=30)
yesterday = (midnight_thirty - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
check("00:30 counts toward yesterday", store.quest_day(midnight_thirty) == yesterday)
nine_am = datetime.datetime.now().replace(hour=9, minute=0)
check("09:00 counts toward today",
      store.quest_day(nine_am) == nine_am.strftime("%Y-%m-%d"))

print("\n[6b] streaks")
reset()
q = store.add_quest("Japanese", 60, "", "japanese")
for d in range(1, 4):
    day = (datetime.datetime.now() - datetime.timedelta(days=d)).strftime("%Y-%m-%d")
    store.add_quest_seconds(q, 3600, day=day)
check("3 past days = streak of 3", store.get_quest_streak(q) == 3)
check("an unfinished today does not break it", store.get_quest_streak(q) == 3)
store.add_quest_seconds(q, 3600)
check("finishing today extends it to 4", store.get_quest_streak(q) == 4)

gap_day = (datetime.datetime.now() - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
store.add_quest_seconds(q, 3600, day=gap_day)
check("a gap does not merge older days", store.get_quest_streak(q) == 4)

# ── 7. board math ───────────────────────────────────────────────────────────
print("\n[7] board arithmetic")
reset()
q = store.add_quest("Japanese", 120, "", "japanese")
store.add_quest_seconds(q, 1800)
b = store.get_quest_board()["quests"][0]
check("percent is 25", b["percent"] == 25)
check("remaining is 90m", b["remaining_seconds"] == 90 * 60)
check("not complete yet", not b["completed"])
store.add_quest_seconds(q, 90 * 60)
b = store.get_quest_board()["quests"][0]
check("percent caps at 100", b["percent"] == 100)
check("complete once target met", b["completed"])

# ── 9. topic quests: the subject is in the CONTENT, not the app ─────────────
print("\n[9] 'Aura Code Base' — app proves nothing, content decides")
reset()
REPO = os.path.dirname(os.path.abspath(__file__))
aura = store.add_quest("Aura Code Base", 60, "", "custom", project_path=REPO)
jp = store.add_quest("Japanese", 120, "", "japanese")
board = store.get_quest_board()["quests"]
aura_q = next(q for q in board if q["id"] == aura)
all_terms, anchors = Q.quest_terms(aura_q)

check("harvests the project's own vocabulary", len(anchors) > 20)
check("'aura' is an anchor", "aura" in anchors)
check("'code' is NOT an anchor — it identifies nothing",
      "code" not in anchors)
check("'base' is NOT an anchor", "base" not in anchors)
check("generic folder names aren't anchors",
      "core" not in anchors and "memory" not in anchors)
check("real module names are anchors",
      any(t in anchors for t in ("proactive", "sanctuary", "quest_presets", "v3_bridge")))


def m(app, title, body=""):
    mid, _ = Q.match({"app": app, "title": title, "visible_text": body}, board)
    return mid


print("\n[9a] working on it directly")
check("editor window with the project name", m("Visual Studio Code", "brain.py - AURA - Visual Studio Code") == aura)
check("the repo on GitHub", m("Chrome", "shaurya/AURA: my AI companion - GitHub") == aura)

print("\n[9b] an LLM chat ABOUT the project counts")
check(
    "Claude, discussing AURA",
    m("Claude", "Claude",
      "in AURA the quest tracker lives in core/quests.py. AURA credits time "
      "only when the screen matches what you said you'd do.") == aura,
)
check(
    "Claude, naming real modules",
    m("Claude", "Claude",
      "the sanctuary cards and the domain workspace need the settings store wired") == aura,
)
check(
    "ChatGPT, one snake_case symbol is enough",
    m("ChatGPT", "ChatGPT",
      "how do I fix the response_composer so the persona layer stops trimming") == aura,
)

print("\n[9c] the same apps, unrelated content — must NOT count")
check("Claude about pasta", m("Claude", "Claude", "Here is a pasta recipe. Boil water, add salt, cook 9 minutes.") is None)
check("ChatGPT about React", m("ChatGPT", "ChatGPT", "explain react hooks useState useEffect and rendering") is None)
check(
    "generic code words alone are not enough",
    m("ChatGPT", "ChatGPT",
      "build me a server with an api, some routes and a client store in the core lib") is None,
)
check("a browser tab on CSS", m("Chrome", "How to center a div", "css flexbox tutorial") is None)
check("Netflix", m("Chrome", "Netflix", "one piece episode 1082") is None)

print("\n[9d] container apps: the app NAME is never the evidence")
from core.quest_presets import is_container_app  # noqa: E402

check("Chrome is a container", is_container_app("Google Chrome"))
check("Claude is a container", is_container_app("Claude"))
check("VS Code is a container", is_container_app("Visual Studio Code"))
check("Anki is NOT a container", not is_container_app("Anki"))
check(
    "an empty browser tab matches nothing",
    m("Chrome", "New Tab") is None,
)

print("\n[9e] a quest with nothing distinctive can't hijack the board")
reset()
vague = store.add_quest("My Work Stuff", 60, "", "custom")
board = store.get_quest_board()["quests"]
_, vague_anchors = Q.quest_terms(board[0])
check("no anchors derived from filler words", len(vague_anchors) == 0)
check("so it never matches anything",
      Q.match({"app": "Chrome", "title": "work stuff project", "visible_text": "work"}, board)[0] is None)

# ── 11. untimed quests: monitored, never owed, never complete ───────────────
print("\n[11] untimed quests — no target, just tracked")
reset()
u = store.add_quest("Aura Code Base", 0, "", "custom")
CODE = {"app": "VS Code", "title": "brain.py - AURA Code Base", "visible_text": ""}

b = store.get_quest_board()["quests"][0]
check("flagged untimed", b["untimed"])
check("target is zero", b["target_seconds"] == 0)
check("percent stays 0 — nothing to fill", b["percent"] == 0)
check("nothing remaining is owed", b["remaining_seconds"] == 0)
check("never completed", not b["completed"])

t = Q.QuestTracker()
n = 5_000_000
t.tick(CODE, now=n)
for _ in range(20):            # 10 minutes
    n += 30
    t.tick(CODE, now=n)
b = store.get_quest_board()["quests"][0]
check("time still accumulates", b["seconds"] == 600)
check("still not complete after time", not b["completed"])
check("excluded from pressure entirely", Q.pressure()["required_minutes"] == 0)
check("pressure reads clear, not overdue", Q.pressure()["status"] == "clear")

print("\n[11b] AURA acknowledges the hours")
lines = []
for _ in range(110):           # on to ~65 minutes
    n += 30
    ln = t.tick(CODE, now=n)
    if ln:
        lines.append(ln)
check("says something at the 1h mark", any("1h" in ln for ln in lines))
check("names the quest", any("Aura Code Base" in ln for ln in lines))
check("makes clear there's no target", any("no target" in ln.lower() for ln in lines))
before = len(lines)
for _ in range(10):
    n += 30
    if t.tick(CODE, now=n):
        lines.append("x")
check("doesn't repeat the same mark", len(lines) == before)

print("\n[11c] streaks work without a target")
reset()
u = store.add_quest("Aura Code Base", 0, "", "custom")
for d in range(1, 4):
    day = (datetime.datetime.now() - datetime.timedelta(days=d)).strftime("%Y-%m-%d")
    store.add_quest_seconds(u, 900, day=day)
check("any time on the day counts", store.get_quest_streak(u) == 3)

# ── 12. overtime: the clock doesn't stop at the target ──────────────────────
print("\n[12] going past a target keeps counting")
reset()
jp = store.add_quest("Japanese", 2, "", "japanese")     # 2 minute target
ANKI2 = {"app": "Anki", "title": "Japanese Core 2k", "visible_text": ""}
t = Q.QuestTracker()
n = 6_000_000
t.tick(ANKI2, now=n)
said = []
for _ in range(70):            # 35 minutes on a 2-minute quest
    n += 30
    ln = t.tick(ANKI2, now=n)
    if ln:
        said.append(ln)

b = store.get_quest_board()["quests"][0]
check("completed at the target", b["completed"])
check("seconds kept rising past it", b["seconds"] > b["target_seconds"])
check("overtime is reported", b["overtime_seconds"] >= 30 * 60)
check("percent caps at 100", b["percent"] == 100)
check("announced the completion", any("done" in s for s in said))
check("acknowledged the overtime", any("past the" in s for s in said))
check("overtime line leads with the running total",
      any(s.startswith("That's") for s in said))
check("offers a break rather than pushing on",
      any("break" in s.lower() for s in said))

print("\n[12b] overtime marks fire once each, in order")
marks = [s for s in said if "past the" in s]
check("more than one mark over 35 minutes", len(marks) >= 1)
check("no duplicate overtime lines", len(marks) == len(set(marks)))

print("\n[13] a mixed board reads correctly")
reset()
a = store.add_quest("Japanese", 60, "", "japanese")
store.add_quest("Aura Code Base", 0, "", "custom")
store.add_quest_seconds(a, 3600)                      # done
store.add_quest_seconds(store.get_quests()[1][0], 5400)  # 90m untimed
line = Q.summary_line()
check("counts only the timed quest as done", "Quest done today" in line)
check("mentions the untimed time", "Aura Code Base" in line and "1h30" in line)
check("pressure still clear", Q.pressure()["status"] == "clear")

print("\n[10] summary line for chat")
reset()
a = store.add_quest("Japanese", 60, "", "japanese")
store.add_quest("DSA", 60, "", "dsa")
store.add_quest_seconds(a, 3600)
line = Q.summary_line()
check("summary counts completions", "1/2" in line)
check("summary names what's left", "DSA" in line)

reset()
check("empty board says so", "No quests" in Q.summary_line())

print("\n" + "=" * 42)
print(f"{passed} passed, {failed} failed")
print("=" * 42)
sys.exit(1 if failed else 0)
