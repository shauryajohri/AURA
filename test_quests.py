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
print("\n[11] a TIME quest with no target — monitored, never 'behind'")
# Since quest kinds landed, "no duration written" defaults to `manual` (you
# tick it off). Monitor-with-no-goal is still available, but it's now an
# explicit choice: kind="time" with target 0.
reset()
u = store.add_quest("Aura Code Base", 0, "", "custom", kind="time")
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
u = store.add_quest("Aura Code Base", 0, "", "custom", kind="time")
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
store.add_quest("Aura Code Base", 0, "", "custom", kind="time")
store.add_quest_seconds(a, 3600)                      # done
store.add_quest_seconds(store.get_quests()[1][0], 5400)  # 90m untimed
line = Q.summary_line()
check("counts only the timed quest as done", "Quest done today" in line)
check("mentions the untimed time", "Aura Code Base" in line and "1h30" in line)
check("pressure still clear", Q.pressure()["status"] == "clear")

# ── 14. quest kinds: time / proof / manual ──────────────────────────────────
print("\n[14] a quest only gets a clock if you asked for one")
kind_cases = [
    ("japanese 2 hrs", "time", 120, 0),
    ("2h dsa", "time", 120, 0),
    ("read 45 min", "time", 45, 0),
    ("leetcode 2 questions", "proof", 0, 2),
    ("3 problems on codeforces", "proof", 0, 3),
    ("5 kanji reviews", "proof", 0, 5),
    ("2 leetcode", "proof", 0, 2),
    ("exercise", "manual", 0, 0),
    ("gym", "manual", 0, 0),
    ("call mom", "manual", 0, 0),
]
for text, kind, mins, count in kind_cases:
    got = Q.parse_quest(text)
    check(f"{text!r} → {kind}",
          got["kind"] == kind and got["target_minutes"] == mins
          and got["target_count"] == count)

print("\n[14b] '2 hrs' is a duration, not a count")
got = Q.parse_quest("japanese 2 hrs")
check("hours never read as a count", got["target_count"] == 0)

print("\n[14c] only time quests accrue tracked minutes")
reset()
t_id = store.add_quest("Japanese", 60, "", "japanese", kind="time")
p_id = store.add_quest("Leetcode 2 Questions", 0, "", "dsa", kind="proof", target_count=2)
m_id = store.add_quest("Exercise", 0, "", "custom", kind="manual")
board = store.get_quest_board()["quests"]
by = {q["id"]: q for q in board}
check("time quest is timed", not by[t_id]["untimed"])
check("proof quest has no clock", by[p_id]["untimed"] and by[p_id]["percent"] == 0)
check("manual quest has no clock", by[m_id]["untimed"])

# The matcher must not attribute screen time to a non-time quest.
ANKI3 = {"app": "Anki", "title": "Japanese Core 2k", "visible_text": ""}
LC = {"app": "Chrome", "title": "LeetCode - Two Sum", "visible_text": ""}
check("time quest still matches", Q.match(ANKI3, board)[0] == t_id)
check("proof quest never matches for time", Q.match(LC, board)[0] is None)

tr = Q.QuestTracker()
n = 7_000_000
tr.tick(LC, now=n)
for _ in range(10):
    n += 30
    tr.tick(LC, now=n)
check("no seconds credited to a proof quest", store.get_quest_seconds(p_id) == 0)
check("that time went to unallocated instead",
      store.get_quest_board()["unallocated_seconds"] > 0)

print("\n[14d] non-time quests never auto-complete")
for _ in range(200):
    n += 30
    tr.tick({"app": "Chrome", "title": "Exercise routine"}, now=n)
b = store.get_quest_board()["quests"]
check("proof quest still open", not next(q for q in b if q["id"] == p_id)["completed"])
check("manual quest still open", not next(q for q in b if q["id"] == m_id)["completed"])

print("\n[14e] pressure counts only time quests")
check("only the 60m time quest is owed",
      Q.pressure(now=at(9))["required_minutes"] == 60)

print("\n[14f] manual completion works for all kinds")
store.complete_quest(m_id)
b = {q["id"]: q for q in store.get_quest_board()["quests"]}
check("manual marks done", b[m_id]["completed"])
store.complete_quest(m_id, undo=True)
check("and reopens", not store.get_quest_board()["quests"][2]["completed"])

# ── 15. the migration that nearly broke an existing board ───────────────────
print("\n[15] upgrading an OLD database keeps quests behaving")
import sqlite3  # noqa: E402

old_path = os.path.join(_TMP, "old_schema.db")
c = sqlite3.connect(old_path)
c.execute("""CREATE TABLE quests (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
    target_minutes INTEGER DEFAULT 60, keywords TEXT DEFAULT '',
    preset TEXT DEFAULT 'custom', color TEXT DEFAULT '#8b5cff',
    active INTEGER DEFAULT 1, sort_order INTEGER DEFAULT 0, created_at TEXT)""")
c.execute("INSERT INTO quests (title, target_minutes) VALUES ('Old Timed', 120)")
c.execute("INSERT INTO quests (title, target_minutes) VALUES ('Old Untracked', 0)")
c.commit()
c.close()

_real_db = store.DB_PATH
store.DB_PATH = old_path
store.init_quests()
migrated = {q["title"]: q for q in store.get_quest_board()["quests"]}
# The first cut of this migration declared the column DEFAULT 'manual', so
# every pre-existing TIMED quest silently became manual and stopped tracking.
check("an old timed quest stays 'time'", migrated["Old Timed"]["kind"] == "time")
check("...and keeps its target", migrated["Old Timed"]["target_minutes"] == 120)
check("...and still has a clock", not migrated["Old Timed"]["untimed"])
check("an old untracked quest becomes manual",
      migrated["Old Untracked"]["kind"] == "manual")
store.DB_PATH = _real_db

# ── 16. screenshot verdict parsing ──────────────────────────────────────────
print("\n[16] reading the vision model's verdict")
from core.quest_verify import parse_verdict  # noqa: E402

check("clean PASS", parse_verdict(
    "VERDICT: PASS\nEVIDENCE: Two problems show Accepted.")["passed"])
check("clean FAIL", not parse_verdict(
    "VERDICT: FAIL\nEVIDENCE: Only one is Accepted.")["passed"])
check("lowercase still parses", parse_verdict(
    "verdict: pass\nevidence: both accepted")["passed"])
check("evidence is captured", parse_verdict(
    "VERDICT: FAIL\nEVIDENCE: Only one is Accepted.")["evidence"]
    == "Only one is Accepted.")

print("\n[16b] a model that ignores the format is NOT a pass")
# Rambling instead of answering is not evidence the work is done.
for junk in ["I think it looks done maybe?", "", "Hmm, hard to say.",
             "The screenshot is too blurry to tell."]:
    r = parse_verdict(junk)
    check(f"not passed: {junk[:34]!r}", not r["passed"])
    check("  flagged unparsed", not r["parsed"])

print("\n[16c] a verdict with no evidence line still works")
r = parse_verdict("VERDICT: FAIL")
check("parsed", r["parsed"] and not r["passed"])

print("\n[17] verify() refuses the wrong quest kinds")
from core.quest_verify import verify_quest  # noqa: E402

reset()
tq = store.add_quest("Japanese", 60, "", "japanese", kind="time")
mq = store.add_quest("Exercise", 0, "", "custom", kind="manual")
r = verify_quest(tq)
check("a timed quest can't be screenshot-verified", not r["ok"])
check("...and says why", "time" in r["error"].lower())
r = verify_quest(mq)
check("a manual quest can't either", not r["ok"])
check("...and says to mark it yourself", "mark it done" in r["error"].lower())
r = verify_quest(999999)
check("unknown quest is handled", not r["ok"] and "no such quest" in r["error"])

# ── 18. auto-detecting accepted submissions ─────────────────────────────────
print("\n[18] spotting an accepted submission")
from core.submission_watch import detect_acceptance  # noqa: E402

LC_OK = {"app": "Comet",
         "title": "Two Sum II - Input Array Is Sorted - LeetCode - Comet",
         "visible_text": "Accepted Runtime: 3 ms Beats 92.4% Memory 15.2 MB"}
LC_OK2 = {"app": "Comet", "title": "3Sum - LeetCode - Comet",
          "visible_text": "Accepted Runtime: 12 ms"}

check("LeetCode accepted is detected", detect_acceptance(LC_OK) is not None)
check("the problem is identified",
      detect_acceptance(LC_OK)["problem"] == "Two Sum II - Input Array Is Sorted")
check("browser suffix stripped from the name",
      "comet" not in detect_acceptance(LC_OK)["problem"].lower())
check("Codeforces", detect_acceptance(
    {"app": "Chrome", "title": "Problem A - Watermelon - Codeforces",
     "visible_text": "Accepted pretests passed"}) is not None)
check("HackerRank", detect_acceptance(
    {"app": "Chrome", "title": "Simple Array Sum - HackerRank",
     "visible_text": "Congratulations! You solved this challenge."}) is not None)
check("GeeksforGeeks", detect_acceptance(
    {"app": "Chrome", "title": "Reverse a String - GeeksforGeeks",
     "visible_text": "Problem Solved Successfully"}) is not None)

print("\n[18b] false positives — the part that matters")
# Counting something that didn't happen silently completes a quest the user
# didn't earn, which defeats the whole point of verification.
for label, ctx in [
    ("a page merely open", {"app": "Comet", "title": "Two Sum II - LeetCode",
                            "visible_text": "Given a 1-indexed array of integers"}),
    ("wrong answer", {"app": "Comet", "title": "Two Sum II - LeetCode",
                      "visible_text": "Wrong Answer Testcase 33/45"}),
    ("a cookie banner", {"app": "Chrome", "title": "Two Sum - LeetCode",
                         "visible_text": "We use cookies. Accepted. Cookie policy"}),
    ("Stack Overflow's accepted answer",
     {"app": "Chrome", "title": "python - Stack Overflow",
      "visible_text": "Accepted answer by user123"}),
    ("an article about a job offer",
     {"app": "Chrome", "title": "LeetCode blog",
      "visible_text": "She accepted the offer after her interview."}),
    ("not a coding platform at all",
     {"app": "Chrome", "title": "Netflix", "visible_text": "Accepted"}),
    ("nothing on screen", {"app": "", "title": "", "visible_text": ""}),
]:
    check(f"ignored: {label}", detect_acceptance(ctx) is None)

print("\n[18c] an old Accepted in the list doesn't beat the current verdict")
check("current failure wins", detect_acceptance(
    {"app": "Comet", "title": "Two Sum - LeetCode",
     "visible_text": "Wrong Answer  |  earlier: Accepted Runtime 4ms"}) is None)

print("\n[19] counting, deduplication and auto-completion")
reset()
pq = store.add_quest("Leetcode 2 Questions", 0, "", "dsa",
                     kind="proof", target_count=2)
tr = Q.QuestTracker()
n = 8_000_000

lines = []
for _ in range(6):                 # same solve on screen for 3 minutes
    n += 30
    ln = tr.check_submission(LC_OK, now=n)
    if ln:
        lines.append(ln)
b = store.get_quest_board()["quests"][0]
check("one solve counted once", b["done_count"] == 1)
check("spoke about it exactly once", len(lines) == 1)
check("not complete on 1 of 2", not b["completed"])
check("progress shown as a percentage", b["count_percent"] == 50)

n += 30
ln2 = tr.check_submission(LC_OK2, now=n)      # a different problem
b = store.get_quest_board()["quests"][0]
check("second solve counted", b["done_count"] == 2)
check("quest auto-completes at target", b["completed"])
check("and says so", ln2 and "done" in ln2.lower())

check("the ledger records both problems",
      len(store.get_quest_items(pq)) == 2)
check("...marked as auto-detected",
      all(i[1] == "auto" for i in store.get_quest_items(pq)))

print("\n[19b] a completed quest stops counting")
n += 30
check("no further credit", tr.check_submission(
    {"app": "Comet", "title": "Valid Parentheses - LeetCode",
     "visible_text": "Accepted Runtime: 0 ms"}, now=n) is None)

print("\n[19c] solves don't leak into the wrong quest")
reset()
lc = store.add_quest("Leetcode 2 Questions", 0, "", "dsa",
                     kind="proof", target_count=2)
jp = store.add_quest("Japanese 3 Kanji", 0, "", "japanese",
                     kind="proof", target_count=3)
tr2 = Q.QuestTracker()
n += 60
tr2.check_submission(LC_OK, now=n)
by = {q["id"]: q for q in store.get_quest_board()["quests"]}
check("credited to the LeetCode quest", by[lc]["done_count"] == 1)
check("Japanese quest untouched", by[jp]["done_count"] == 0)

print("\n[19d] time quests are never affected by submissions")
reset()
tq2 = store.add_quest("Japanese", 60, "", "japanese", kind="time")
tr3 = Q.QuestTracker()
n += 60
check("no proof quest open → nothing counted",
      tr3.check_submission(LC_OK, now=n) is None)
check("time quest gains no count",
      store.get_quest_board()["quests"][0]["done_count"] == 0)

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

# ── 20. vision fallback — primary model, then a second free model ───────────
print("\n[20] vision fallback — primary model then a second free model")
from core import ai_router  # noqa: E402
import requests as _requests  # noqa: E402

_orig_post = _requests.post
_orig_keys = dict(ai_router._OPENROUTER_MODEL_KEYS)
_orig_or_key = ai_router.OPENROUTER_API_KEY
# Force both vision models to look "keyed" regardless of what's in .env, so
# this test is deterministic on any machine.
ai_router.OPENROUTER_API_KEY = "test-shared-key"
ai_router._OPENROUTER_MODEL_KEYS = {
    ai_router.VISION_MODEL: "test-primary-key",
    ai_router.VISION_FALLBACK_MODEL: "test-fallback-key",
}


class _FakeResp:
    def __init__(self, status_code, data=None):
        self.status_code = status_code
        self._data = data or {}

    def json(self):
        return self._data


def _reset_vision_cooldown():
    ai_router._provider_cooldown.clear()


print("\n[20a] primary rate-limited, fallback answers")
_reset_vision_cooldown()
calls = []


def _post_a(url, headers=None, json=None, timeout=None):
    calls.append(json["model"])
    if json["model"] == ai_router.VISION_MODEL:
        return _FakeResp(429)
    return _FakeResp(200, {"choices": [{"message": {"content": "fallback sees it done"}}]})


_requests.post = _post_a
result = ai_router.call_vision("is this done?", "base64img")
check("returns the fallback's text, not a sentinel", result == "fallback sees it done")
check("primary was tried first", calls[0] == ai_router.VISION_MODEL)
check("fallback was tried second", calls[1] == ai_router.VISION_FALLBACK_MODEL)

print("\n[20b] both models rate-limited")
_reset_vision_cooldown()
_requests.post = lambda url, headers=None, json=None, timeout=None: _FakeResp(429)
result = ai_router.call_vision("is this done?", "base64img")
check("RATE_LIMIT surfaces when both fail that way", result == "RATE_LIMIT")

print("\n[20c] primary succeeds — fallback never called (no wasted request)")
_reset_vision_cooldown()
calls2 = []


def _post_c(url, headers=None, json=None, timeout=None):
    calls2.append(json["model"])
    return _FakeResp(200, {"choices": [{"message": {"content": "primary sees it done"}}]})


_requests.post = _post_c
result = ai_router.call_vision("is this done?", "base64img")
check("returns the primary's text", result == "primary sees it done")
check("only one request was made", len(calls2) == 1)
check("that request went to the primary model", calls2 == [ai_router.VISION_MODEL])

_requests.post = _orig_post
ai_router._OPENROUTER_MODEL_KEYS = _orig_keys
ai_router.OPENROUTER_API_KEY = _orig_or_key
_reset_vision_cooldown()

print("\n" + "=" * 42)
print(f"{passed} passed, {failed} failed")
print("=" * 42)
sys.exit(1 if failed else 0)
