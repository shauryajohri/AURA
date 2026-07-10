# test_error_intelligence.py
"""
Unit tests for the V3 Error Intelligence Engine.

Run:  python test_error_intelligence.py
No external test framework — plain asserts so it runs anywhere the app runs.
Uses a temp mistake-log so it never touches the real memory/mistake_log.json.
"""

import os
import random
import tempfile

from modules.error_intelligence import classify, get_engine
from modules.error_intelligence.engine import ErrorIntelligenceEngine
from modules.error_intelligence.mistake_tracker import MistakeTracker
from modules.error_intelligence.models import Category, Level

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ FAIL: {name}")


# ── 1. Classification across all 4 levels + 3 languages ────────────────────
def test_classification():
    print("\n[classification]")

    # SILLY
    c = classify("main.cpp:12:5: error: expected ';' before '}' token", "cpp")
    check("cpp missing ; -> SILLY/SYNTAX", c.matched and c.level == Level.SILLY and c.category == Category.SYNTAX)
    check("cpp missing ; -> correct entry", c.entry_id == "missing_semicolon")

    c = classify("NameError: name 'foo' is not defined", "python")
    check("py NameError -> SILLY", c.matched and c.level == Level.SILLY)

    c = classify("ReferenceError: bar is not defined", "javascript")
    check("js ReferenceError -> SILLY", c.matched and c.level == Level.SILLY)

    c = classify("IndentationError: expected an indented block", "python")
    check("py indentation -> SILLY", c.matched and c.entry_id == "py_indentation")

    # MEDIUM
    c = classify("TypeError: foo() takes 3 positional arguments but 2 were given", "python")
    check("py TypeError -> MEDIUM/TYPING", c.matched and c.level == Level.MEDIUM and c.category == Category.TYPING)

    c = classify("undefined reference to `compute'", "cpp")
    check("cpp linker -> MEDIUM", c.matched and c.entry_id == "cpp_linker_error")

    c = classify("TypeError: x is not a function", "javascript")
    check("js not-a-function -> MEDIUM", c.matched and c.level == Level.MEDIUM)

    # CONCEPTUAL
    c = classify("Segmentation fault (core dumped)", "cpp")
    check("segfault -> CONCEPTUAL", c.matched and c.level == Level.CONCEPTUAL)

    c = classify("RecursionError: maximum recursion depth exceeded", "python")
    check("infinite recursion -> CONCEPTUAL", c.matched and c.level == Level.CONCEPTUAL)

    c = classify("thread 1: resource deadlock avoided", None)
    check("deadlock -> CONCEPTUAL", c.matched and c.entry_id == "deadlock")

    # DANGEROUS
    c = classify("rm -rf /home/user/project", None)
    check("rm -rf -> DANGEROUS/CRITICAL", c.matched and c.level == Level.DANGEROUS and c.category == Category.CRITICAL)

    c = classify("git reset --hard HEAD~3", None)
    check("git reset --hard -> DANGEROUS", c.matched and c.level == Level.DANGEROUS)


# ── 2. Language inference when not supplied ─────────────────────────────────
def test_language_inference():
    print("\n[language inference]")
    c = classify('Traceback (most recent call last):\n  File "app.py", line 3\nNameError: name \'x\' is not defined')
    check("infers python from traceback", c.language == "python" and c.matched)

    c = classify("main.cpp:5: error: expected ';'")
    check("infers cpp from .cpp", c.language == "cpp")


# ── 3. Unmatched errors flag needs_llm ──────────────────────────────────────
def test_llm_fallback():
    print("\n[LLM fallback]")
    eng = _fresh_engine()
    resp = eng.process("some bizarre proprietary error nobody has ever seen 0xDEADBEEF")
    check("unknown error -> needs_llm", resp.needs_llm is True)
    check("unknown error -> not matched", resp.classification.matched is False)
    check("unknown error -> empty spoken text", resp.spoken_text == "")


# ── 4. Repeat escalation (the running gag) ──────────────────────────────────
def test_escalation():
    print("\n[escalation]")
    eng = _fresh_engine(seed=1)
    err = "error: expected ';' before '}'"

    r1 = eng.process(err, language="cpp")
    check("1st time -> count 1", r1.repeat_count == 1)

    for _ in range(2):
        eng.process(err, language="cpp")
    r3 = eng.process(err, language="cpp")  # 4th call, count 4 -> still 'again' tier? tier 'personal' starts at 5
    check("4th time -> count 4", r3.repeat_count == 4)

    # push to 5 -> 'personal' tier line mentions the noun
    r5 = eng.process(err, language="cpp")
    check("5th time -> count 5", r5.repeat_count == 5)

    # push to 20 -> legendary
    for _ in range(15):
        last = eng.process(err, language="cpp")
    check("20th time -> count 20", last.repeat_count == 20)
    check("20th time -> 'pocket' running gag", "pocket" in last.spoken_text.lower() or "record" in last.spoken_text.lower())


# ── 5. Serious errors never joke ────────────────────────────────────────────
def test_serious_no_jokes():
    print("\n[serious tone]")
    eng = _fresh_engine()
    resp = eng.process("Segmentation fault (core dumped)", language="cpp")
    check("segfault -> serious flag", resp.serious is True)
    check("segfault -> supportive language", "together" in resp.spoken_text.lower() or "walk" in resp.spoken_text.lower() or "figure" in resp.spoken_text.lower())

    resp = eng.process("rm -rf /", personality="roast")
    check("rm -rf -> serious even in roast pack", resp.serious is True)
    check("rm -rf -> protective language", "sure" in resp.spoken_text.lower() or "hold on" in resp.spoken_text.lower() or "undo" in resp.spoken_text.lower())


# ── 6. Mistake tracker: today summary + trend ───────────────────────────────
def test_tracker():
    print("\n[mistake tracker]")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "mistake_log.json")
        t = MistakeTracker(path)

        for _ in range(12):
            t.record("missing_semicolon", "Missing semicolon")
        for _ in range(3):
            t.record("missing_paren", "Missing parenthesis")

        check("count_today semicolons = 12", t.count_today("missing_semicolon") == 12)
        summary = t.today_summary()
        check("today_summary sorted, semicolon first", summary[0]["id"] == "missing_semicolon" and summary[0]["count"] == 12)
        check("today_summary has 2 rows", len(summary) == 2)

        # persistence: reload from disk
        t2 = MistakeTracker(path)
        check("persists across reload", t2.total("missing_semicolon") == 12)

        # trend with a synthetic history: 30 last week, 5 this week -> down ~83%
        from datetime import date, timedelta
        today = date.today()
        daily = t2._data["missing_semicolon"]["daily"]
        daily.clear()
        # this-week window (days 0..6): 5 total
        daily[today.isoformat()] = 5
        # previous window (days 7..13): 30 total
        daily[(today - timedelta(days=8)).isoformat()] = 30
        tr = t2.trend("missing_semicolon", window_days=7)
        check("trend recent=5 previous=30", tr["recent"] == 5 and tr["previous"] == 30)
        check("trend delta ~ -83%", tr["delta_pct"] is not None and -84 < tr["delta_pct"] < -82)
        check("trend direction down", tr["direction"] == "down")


# ── 7. record=False previews without polluting stats ────────────────────────
def test_preview_no_record():
    print("\n[preview mode]")
    eng = _fresh_engine()
    eng.process("error: expected ';'", language="cpp", record=False)
    check("record=False leaves tracker empty", eng.tracker.count_today("missing_semicolon") == 0)


# ── helpers ─────────────────────────────────────────────────────────────────
def _fresh_engine(seed=0):
    d = tempfile.mkdtemp()
    path = os.path.join(d, "mistake_log.json")
    return ErrorIntelligenceEngine(tracker=MistakeTracker(path), rng=random.Random(seed))


if __name__ == "__main__":
    test_classification()
    test_language_inference()
    test_llm_fallback()
    test_escalation()
    test_serious_no_jokes()
    test_tracker()
    test_preview_no_record()
    print(f"\n{'='*40}\n{PASS} passed, {FAIL} failed\n{'='*40}")
    raise SystemExit(1 if FAIL else 0)
