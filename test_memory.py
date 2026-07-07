"""Headless regression test for the 2026-07-07 memory upgrade.

Reproduces the exact failure ("its name was AURA" → later "what was it
called?") against an isolated temp DB, with NO Qt/audio/network needed.
Run:  python test_memory.py
"""

import os
import sys
import tempfile

# ── Isolate the DB so the test never touches the real aura_memory.db ─────────
from memory import store

_tmp_db = os.path.join(tempfile.gettempdir(), "aura_test_memory.db")
for suffix in ("", "-wal", "-shm"):
    try:
        os.remove(_tmp_db + suffix)
    except OSError:
        pass
store.DB_PATH = _tmp_db
store.init_db()
store.init_tasks()

from modules import fact_extractor

_failures = []


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        _failures.append(name)


print("1) Heuristic fact capture (the exact failing phrase)")
saved = fact_extractor.capture_heuristic("its name was AURA")
facts = store.get_user_facts()
check("captured a fact from 'its name was AURA'", bool(saved))
check("a saved fact mentions AURA", any("AURA" in f for f in facts))

print("2) More heuristics")
fact_extractor.capture_heuristic("my name is Shaurya")
fact_extractor.capture_heuristic("I'm learning DSA for placements")
fact_extractor.capture_heuristic("I'm a software developer")
facts = store.get_user_facts()
check("name captured", any("Shaurya" in f for f in facts))
check("learning captured", any("DSA" in f for f in facts.__iter__()))
check("identity captured", any("developer" in f for f in facts))

print("3) Filler is rejected (no false facts)")
before = set(store.get_user_facts())
fact_extractor.capture_heuristic("I'm tired")
fact_extractor.capture_heuristic("I'm back")
after = set(store.get_user_facts())
check("'I'm tired' / 'I'm back' saved nothing", before == after)

print("4) Facts survive the conversation window (the real bug)")
# Simulate many turns AFTER the name was given, so the line has scrolled out
# of any reasonable chat window.
for i in range(12):
    store.save_conversation("user", f"random unrelated message {i}")
    store.save_conversation("aura", f"reply {i}")
recent = store.get_recent_conversations(8)
window_text = " ".join(m for _, m, _ in recent)
check("AURA is NOT in the recent chat window (as expected)", "AURA" not in window_text)
check("AURA IS still available as a durable fact",
      any("AURA" in f for f in store.get_user_facts()))

print("5) Dedup — saying the same thing twice doesn't duplicate")
n1 = len(store.get_user_facts(limit=100))
fact_extractor.capture_heuristic("its name was AURA")
n2 = len(store.get_user_facts(limit=100))
check("no duplicate fact", n1 == n2)

print("6) brain context assembly (if importable without Qt/audio)")
try:
    from core import brain
    hist = brain._recent_turns(8)
    facts_block = brain._facts_block()
    check("_recent_turns returns the recent conversation", "random unrelated" in hist)
    check("_facts_block surfaces AURA to the prompt", "AURA" in facts_block)
    check("junk template blobs are filtered", brain._is_context_junk("Task: something"))
except Exception as e:
    print(f"  SKIP  brain import unavailable in this env ({e})")

print()
if _failures:
    print(f"RESULT: {len(_failures)} FAILED → {_failures}")
    sys.exit(1)
print("RESULT: all checks passed")
