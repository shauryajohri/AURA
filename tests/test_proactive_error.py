"""
Proactive "error" moment — does a traceback that stays on screen ever get an
offer of help?

The bug: the else that decays the error counter was paired with
`if _error_count >= ERROR_THRESHOLD` instead of `if _has_errors(ctx)`, so every
error cycle went 0 -> 1 -> 0 and _decide never returned "error" — the one kind
core.engagement lets through during real work.

Runs offline on a THROWAWAY sqlite DB, calling proactive._decide directly.

Run:  PYTHONPATH=. python3 tests/test_proactive_error.py
"""

import os
import sys
import tempfile

# point the shared store at a temp DB BEFORE importing anything that uses it
_TMP = tempfile.mkdtemp(prefix="aura_proactive_test_")
import memory.store as mstore  # noqa: E402
mstore.DB_PATH = os.path.join(_TMP, "test.db")
mstore.init_db()

import core.brain as brain  # noqa: E402
import modules.proactive as pro  # noqa: E402

# the user hasn't typed to AURA recently, and the task name is fixed so the
# "stuck"/"interaction" paths can't kick in and muddy the result
brain.get_last_user_message_time = lambda: 0
pro._extract_task = lambda ctx: "build"

_fails = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'} — {label}")
    if not cond:
        _fails.append(label)


ERROR = {"app": "Windows Terminal",
         "visible_text": "Traceback (most recent call last):\nNameError: name 'foo' is not defined"}
CLEAN = {"app": "Windows Terminal", "visible_text": "$ python main.py\nall good"}
QUIET = {"should_interrupt": False}
ERROR_THRESHOLD = pro.ERROR_THRESHOLD


def cycle(ctx):
    pro._last_suggestion_time = 0   # each cycle lands after the cooldown
    return pro._decide(ctx, ie_result=QUIET)[0]


def reset():
    pro._error_count = 0
    pro._same_context_checks = 0
    pro._last_signature = ""
    pro._activity_log.clear()


print("\n[1] an error that stays on screen")
check(pro._has_errors(ERROR) and not pro._has_errors(CLEAN), "fixtures: one has an error, one doesn't")
reset()
got = [cycle(ERROR) for _ in range(ERROR_THRESHOLD)]
check(got[-1] == "error", f"{ERROR_THRESHOLD} error cycles in a row -> 'error' (got {got})")
check(pro._error_count == 0, "counter resets once the offer fires")
got = [cycle(ERROR) for _ in range(ERROR_THRESHOLD)]
check(got[-1] == "error", f"still there later -> offered again after the cooldown (got {got})")

print("\n[2] clean cycles decay the count")
reset()
got = [cycle(ERROR), cycle(CLEAN), cycle(ERROR)]
check("error" not in got, f"a clean cycle in between knocks the count back (got {got})")
reset()
cycle(ERROR)
cycle(CLEAN)
check(pro._error_count == 0, "count decays on a clean cycle")
cycle(CLEAN)
check(pro._error_count == 0, "and never goes below zero")

print("\n" + ("ALL PASS ✅" if not _fails else f"FAILURES: {_fails}"))
sys.exit(1 if _fails else 0)
