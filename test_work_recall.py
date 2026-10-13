"""
Tests for core.work_recall — session memory inside the conversation.

The bug: ask AURA "what were we doing last time?" and she guessed. The chat
prompt carried recent turns, durable facts and the screen, but not the session
summaries sitting in the same SQLite file.

Covered here:
  1. work questions are recognised, ordinary chat is not
  2. an empty store produces NO block (a placeholder teaches the model to talk
     about having no memory)
  3. the last session and earlier recaps show up when asked
  4. every reader is failure-tolerant — a missing table must not break a turn

Runs on a THROWAWAY DB. Never touches real memory.

Run:  PYTHONPATH=. python test_work_recall.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TMP = tempfile.mkdtemp(prefix="aura_work_recall_")
os.environ["AURA_TEST_DB"] = os.path.join(_TMP, "test.db")

import memory.store as mstore  # noqa: E402
mstore.DB_PATH = os.environ["AURA_TEST_DB"]
mstore.init_db()

from core import work_recall  # noqa: E402

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {label}")
    else:
        failed += 1
        print(f"  ✗ {label}")


print("\n[recognising a question about past work]")
for q in [
    "what project were we doing last time?",
    "what were we working on?",
    "where did we leave off",
    "remind me what we decided",
    "what's left on it",
    "catch me up",
    "do you remember the graph thing",
]:
    check(f"work question: {q!r}", work_recall.is_work_question(q))

for q in [
    "afternoon",
    "write me a binary search in c++",
    "what's the weather like",
    "explain how MVCC works",
    "i'm stuck on this websocket bug",
]:
    check(f"NOT a work question: {q!r}", not work_recall.is_work_question(q))


print("\n[an empty store says nothing at all]")
check("prompt_section is empty", work_recall.prompt_section("what were we doing?") == "")
check("answer_context is empty", work_recall.answer_context("what were we doing?") == "")


print("\n[sessions appear when asked]")
mstore.save_session_snapshot("Excel", "Cleaning up the March budget sheet", ["budget"])
mstore.save_session_snapshot("VS Code", "Fixing the login form validation", ["login"])

expanded = work_recall.answer_context("what were we doing last time?")
check("last session is named", "login form" in expanded)
check("earlier recap is listed", "budget sheet" in expanded)

section = work_recall.prompt_section("what were we doing last time?")
check("work question gets the section", "login form" in section)
check("section tells her to be specific", "SPECIFIC" in section.upper())
check("ordinary chat gets nothing", work_recall.prompt_section("afternoon") == "")


print("\n[nothing here may ever raise]")
_good = mstore._connect


def _boom():
    raise RuntimeError("db is gone")


mstore._connect = _boom
try:
    check("answer_context survives a dead DB", work_recall.answer_context("recap") == "")
    check("prompt_section survives a dead DB",
          work_recall.prompt_section("what were we doing?") == "")
finally:
    mstore._connect = _good

check("recovers once the DB is back", "login form" in work_recall.answer_context("recap"))


print("\n[the chat prompt actually carries it]")
# build_context_prompt is the single funnel every chat lane goes through.
from core import brain  # noqa: E402

prompt = brain.build_context_prompt("what were we doing last time?", "CASUAL", "")
check("session memory reached the prompt", "login form" in prompt)


print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
