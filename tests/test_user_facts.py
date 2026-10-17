"""
Durable user facts: only plain statements become facts, and the user's name
stays in the prompt however many other facts pile up.

Regression for the full-app test's finding E-4: questions, hypotheticals,
quotes, sarcasm and code were saved as permanent "facts" ('call me later'
saved the name "later"), and only the newest 10 facts reached the prompt, so
the real name dropped out after a dozen of them. Offline, throwaway DB.

Run:  PYTHONPATH=. python3 tests/test_user_facts.py
"""

import os
import sys
import tempfile

import memory.store as mstore
mstore.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="aura_facts_test_"), "test.db")
mstore.init_db()

from modules import fact_extractor  # noqa: E402
from core import thinking  # noqa: E402

_fails = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'} — {label}")
    if not cond:
        _fails.append(label)


def _reset():
    conn = mstore._connect()
    conn.execute(mstore._USER_FACTS_DDL)
    conn.execute("DELETE FROM user_facts")
    conn.commit()
    conn.close()


def _new_facts(fn, text):
    before = set(mstore.get_user_facts(500))
    fn(text)
    return sorted(set(mstore.get_user_facts(500)) - before)


NOT_FACTS = [
    # questions
    "what's my name is it Bob?",
    "is the project called Helios or Atlas?",
    "am I learning anything useful lately?",
    "can you call me later when the build finishes?",
    # hypotheticals
    "if my name is ever leaked online what should I do?",
    "imagine I'm a senior engineer at Google, how would I answer?",
    "suppose I'm learning Haskell next year, is that dumb?",
    "what if I'm learning rust next year?",
    # quotes / reported speech
    "my friend said 'my name is Bond, James Bond'",
    "He told me: I'm working on a startup called Zeta",
    "she's learning French and I'm not",
    "the error message says: its name was already taken",
    "my boss keeps saying I'm a terrible developer",
    # sarcasm / jokes
    "oh sure, call me Einstein",
    "yeah right, call me an idiot why don't you",
    "lol I'm working on my sleep schedule",
    "I'm making dinner, brb",
    "I'm building a sandwich right now",
    # passing states
    "I'm working on it",
    "I'm working on the bug you mentioned",
    "I'm studying for tomorrow's exam",
    "preparing for the worst honestly",
    "I'm making progress",
    # code
    "name = 'x'  # my name is foo",
    "print('my name is ' + user.name)",
    "def call_me(cb): return cb()  # call me maybe",
    "class Project: pass  # project is called Demo",
    # negations and other non-names
    "nobody should call me before noon",
    "call me later",
    "it's called a monad, look it up",
    "its called a closure in javascript",
    "its name is unknown",
    "I'm preparing for nothing in particular",
    "I'm making a mistake aren't I",
    "my name is not important",
    "my name isn't Bob",
    "I'm not a doctor",
    "I'm not learning rust anymore",
    "I'm learning that patience matters",
    "Its called PTSD and it's not funny",
    "I'm building a case for why we shouldn't",
]

print("\n[1] questions, hypotheticals, quotes, sarcasm, code and negations save nothing")
_reset()
for s in NOT_FACTS:
    got = fact_extractor.capture_heuristic(s)
    check(got == [], f"{s!r} -> {got}")
check(mstore.get_user_facts(500) == [], "no facts stored at all")

print("\n[2] a question followed by an answer keeps the answer, not the question")
_reset()
got = fact_extractor.capture_heuristic("I want detailed answers? no, I like short responses")
check(got == ["they prefer short responses"], f"stated preference saved: {got}")

GENUINE = [
    ("my name is Shaurya", ["their name is Shaurya"]),
    ("my name is shaurya", ["their name is shaurya"]),
    ("hi, my name is Shaurya", ["their name is Shaurya"]),
    ("My name is Shaurya Johri", ["they are Shaurya Johri"]),
    ("my name is Shaurya, what's yours?", ["their name is Shaurya"]),
    ("hey my name is Shaurya and I'm learning Rust",
     ["their name is Shaurya", "they are learning Rust"]),
    ("call me Shaurya", ["their name is Shaurya"]),
    ("you can call me Sam", ["their name is Sam"]),
    ("I prefer short replies", ["they prefer short replies"]),
    ("I like short responses", ["they prefer short responses"]),
    ("I'm a backend developer", ["they are backend developer"]),
    ("I'm a CS student", ["they are CS student"]),
    ("I'm learning DSA for placements", ["they are learning DSA for placements"]),
    ("I'm learning Rust, not Go", ["they are learning Rust"]),
    ("I'm learning Rust but I'm not good at it", ["they are learning Rust"]),
    ("I am learning Go", ["they are learning Go"]),
    ("I’m learning Rust", ["they are learning Rust"]),
    ("I'm preparing for GATE", ["they are preparing for GATE"]),
    ("its name was AURA", ["their project is called AURA"]),
    ("it's called Wasabikiri", ["their project is called Wasabikiri"]),
    ("the project is called Wasabikiri", ["their project is called Wasabikiri"]),
    ("my project is called AURA", ["their project is called AURA"]),
    ("I'm building AURA", ["their project is called AURA"]),
    ("I'm working on a chess engine", ["their project is called chess engine"]),
    ("I'm making a todo app", ["their project is called todo app"]),
]

print("\n[3] plain statements are still captured")
for s, want in GENUINE:
    _reset()
    got = fact_extractor.capture_heuristic(s)
    check(got == want, f"{s!r} -> {got}")

print("\n[4] the passive extractor in core/thinking.py uses the same gate")
_reset()
for s in ["can you call me later when the build finishes?", "oh sure, call me Einstein",
          "I'm making dinner, brb", "I'm studying for tomorrow's exam",
          "my friend said 'my name is Bond'", "do you like pizza?", "I don't like python",
          "what if my goal is to get rich"]:
    got = _new_facts(thinking._extract_user_facts, s)
    check(got == [], f"thinking: {s!r} -> {got}")
for s, want in [("I love chess", ["likes: chess"]), ("I hate meetings", ["dislikes: meetings"]),
                ("my goal is to get into google", ["goals: get into google"]),
                ("my dog's name is bruno", ["names: dog bruno"])]:
    got = _new_facts(thinking._extract_user_facts, s)
    check(got == want, f"thinking: {s!r} -> {got}")

print("\n[5] the name stays in the prompt after a dozen newer facts")
_reset()
fact_extractor.capture_heuristic("my name is Shaurya")
mstore.save_user_fact("allergic to peanuts", "general")     # typed in the Memory panel
for i in range(12):
    fact_extractor.capture_heuristic(f"I'm learning topic{i}")
top = mstore.get_user_facts(10)
check(len(top) == 10, f"still capped at the limit ({len(top)})")
check("their name is Shaurya" in top, "name is in the top 10")
check(top[0] == "their name is Shaurya", "name is pinned first")
check("allergic to peanuts" in top, "a fact the user typed outranks passing ones")
check("they are learning topic11" in top and "they are learning topic0" not in top,
      "the rest are newest first")
mstore.save_user_fact("their name is Shaurya J", "llm")
check(mstore.get_user_facts(3)[0] == "their name is Shaurya J",
      "a name the LLM pass found is pinned too")
full = [r[1] for r in mstore.get_user_facts_full(300)]
check(full[0] == "their name is Shaurya J" and full[-1] == "their name is Shaurya",
      "Memory panel listing stays newest first")

print("\n[6] brain prompt block (if importable)")
try:
    from core import brain
    check("Shaurya" in brain._facts_block(), "_facts_block carries the name")
except Exception as e:
    print(f"  SKIP — brain import unavailable in this env ({e})")

print()
if _fails:
    print(f"FAILED: {len(_fails)}")
    sys.exit(1)
print("ALL PASS")
