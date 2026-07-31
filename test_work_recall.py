"""
Tests for core.work_recall — the Project Brain inside the conversation.

The bug: ask AURA "what project were we doing last time?" and she guessed. The
chat prompt carried recent turns, durable facts and the screen, but nothing from
the project graph — which was sitting in the same SQLite file the whole time.

Covered here:
  1. work questions are recognised, ordinary chat is not
  2. an empty brain produces NO block (a placeholder teaches the model to talk
     about having no projects)
  3. a real project shows up by name, with progress and what's open
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

from core.domain import brain_store  # noqa: E402
brain_store.DB_PATH = mstore.DB_PATH
brain_store._connect = mstore._connect
brain_store.init_db()

from core import work_recall  # noqa: E402
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


print("\n[recognising a question about the work]")
for q in [
    "what project were we doing last time?",
    "what were we working on?",
    "where did we leave off",
    "remind me what we decided",
    "which project is the auth thing in",
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


print("\n[an empty brain says nothing at all]")
check("compact block is empty", work_recall.context_block("hi") == "")
check("prompt_section is empty", work_recall.prompt_section("what were we doing?") == "")
check("answer_context is empty", work_recall.answer_context("what were we doing?") == "")


print("\n[a real project appears by name]")
proj = project_brain.create_project("AURA Domain", root="/tmp/aura")
pid = proj["id"]
feature = project_brain.add_feature(pid, "GitHub Authentication",
                                    description="Log in with GitHub OAuth")
t1 = project_brain.add_task(pid, "OAuth Flow", feature_id=feature["id"])
project_brain.add_task(pid, "Callback API", feature_id=feature["id"])
t3 = project_brain.add_task(pid, "Token Storage", feature_id=feature["id"])
project_brain.set_task_status(pid, t1["id"], "done")
project_brain.set_task_status(pid, t3["id"], "in_progress")
project_brain.record_decision(pid, "Auth: GitHub OAuth",
                              reason="developers already have accounts")

compact = work_recall.context_block("hey")
check("project named in the compact block", "AURA Domain" in compact)
check("compact block carries progress", "%" in compact)
check("compact block stays short", len(compact.splitlines()) <= 4)

expanded = work_recall.answer_context("what were we doing last time?")
check("expanded names the project", "AURA Domain" in expanded)
check("expanded lists what's open", "Token Storage" in expanded)
check("in-progress work comes first", expanded.index("Token Storage") < expanded.index("Callback API"))
check("expanded carries the decision", "GitHub OAuth" in expanded)
check("expanded carries the reason", "already have accounts" in expanded)
check("expanded mentions the folder", "/tmp/aura" in expanded)

section = work_recall.prompt_section("what project were we doing last time?")
check("work question gets the expanded section", "Token Storage" in section)
check("work question section tells her to be specific", "SPECIFIC" in section.upper())
check(
    "ordinary chat gets the compact section",
    "Token Storage" not in work_recall.prompt_section("afternoon"),
)


print("\n[most recently touched project leads]")
# updated_at has second resolution, so two projects created in the same second
# sort equal and the "newest first" assert would be a coin flip.
import time as _time  # noqa: E402
_time.sleep(1.1)
p2 = project_brain.create_project("Side Quest", root="/tmp/side")
project_brain.add_task(p2["id"], "Sketch the idea")
names = [p["name"] for p in work_recall.projects(5)]
check("both projects listed", {"AURA Domain", "Side Quest"} <= set(names))
check("newest first", names[0] == "Side Quest")


print("\n[nothing here may ever raise]")
# Point the readers at a dead DB: every helper must degrade, not explode.
_good = brain_store._connect


def _boom():
    raise RuntimeError("db is gone")


brain_store._connect = _boom
try:
    check("projects() survives a dead DB", work_recall.projects() == [])
    check("context_block survives a dead DB", work_recall.context_block("hi") == "")
    check("prompt_section survives a dead DB",
          isinstance(work_recall.prompt_section("what were we doing?"), str))
finally:
    brain_store._connect = _good

check("recovers once the DB is back", "AURA Domain" in work_recall.answer_context("recap"))


print("\n[the chat prompt actually carries it]")
# build_context_prompt is the single funnel every chat lane goes through.
from core import brain  # noqa: E402

prompt = brain.build_context_prompt("what project were we doing last time?", "CASUAL", "")
check("project memory reached the prompt", "AURA Domain" in prompt)
check("open work reached the prompt", "Token Storage" in prompt)
prompt_casual = brain.build_context_prompt("afternoon", "CASUAL", "")
check("ordinary turn still gets the compact block", "AURA Domain" in prompt_casual)
check("ordinary turn is not given the full dump", "Token Storage" not in prompt_casual)


print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
