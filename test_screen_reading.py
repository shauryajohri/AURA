"""
Three bugs from one live LeetCode session (2026-07-27), all screen-reading.

  1. AURA narrated shaurya to himself in the third person:
       "They're on the Two Sum II problem... they should be thinking about..."
     Proactive output never passed through any sanitiser.

  2. She answered "how do I fix this error?" by quoting garbled OCR back:
       "The visible content is garbled: '© choy | Undetectabie © & 3 ...'"
     The old readability gate accepted that mush.

  3. She wrote Python for a C++ session — the language selector was on screen
     the entire time and nothing looked at it.

Run:  python test_screen_reading.py
"""

import sys

from core.ai_router import (
    clean_proactive_line,
    is_addressed_to_user,
    sanitize_text,
)
from core.code_language import detect_label, detect_language
from core.screen_text import is_readable, readability

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {label}")
    else:
        failed += 1
        print(f"  ✗ {label}")


# The exact strings from the transcript.
LEAK_1 = ("They're on the Two Sum II problem on LeetCode, which is a fairly "
          "standard coding challenge. The input array being sorted is the key "
          "detail here, so they should be thinking about how to leverage that "
          "for an efficient solution.")
LEAK_2 = ("You're tackling the Two Sum II problem on LeetCode. The input array "
          "being sorted is a good constraint to work with.")
LEAK_3 = ("They are viewing a LeetCode problem with some weird visible content "
          "(maybe an error).")
GARBLED = ("© choy | Undetectabie © & 3 taateodecom / Two Sum Int ray le Sorted "
           "M Gait Youtube BM Translate Anendx-Smart_ [The Best river © "
           "Problemtist < > >¢ |B Description | Editorial Solutions | > "
           "Submissions tov. 1wo sum. = input Array 1s D0rvea, etm © To")

# ── 1. third-person narration ───────────────────────────────────────────────
print("\n[1] she talks TO him, not ABOUT him")
check("the real leak is rejected", clean_proactive_line(LEAK_1) is None)
check("'They are viewing...' is rejected", clean_proactive_line(LEAK_3) is None)
check("'the user' is rejected", clean_proactive_line("The user is on LeetCode.") is None)
check("'their screen' is rejected", clean_proactive_line("Something's up on their screen.") is None)
check("'I notice you're...' is rejected", clean_proactive_line("I notice you're on LeetCode.") is None)

print("\n[1b] the SECOND-person version of the same line survives")
check("second person passes", clean_proactive_line(LEAK_2) == LEAK_2)
for good in [
    "Two Sum II — the sorted array is the whole trick.",
    "Still on that two-pointer? Want a hand?",
    "That traceback's been sitting there a while.",
    "You've been fighting that function for a bit.",
]:
    check(f"kept: {good[:38]}...", clean_proactive_line(good) == good)

print("\n[1c] 'they' about THINGS is still allowed in chat")
# sanitize_text must not become so blunt that ordinary explanations break.
for legit in [
    "Threads are cheap, but they should be joined before exit.",
    "Two pointers work here because they move inward from both ends.",
]:
    check(f"chat keeps: {legit[:38]}...", sanitize_text(legit) == legit)

print("\n[1d] the gate itself")
check("plain address is fine", is_addressed_to_user("You're on Two Sum II."))
check("third person is not", not is_addressed_to_user("They're on Two Sum II."))
check("empty is not addressed", not is_addressed_to_user(""))

print("\n[1e] every contraction of 'they' — the second live leak")
# An earlier fix enumerated "they're / they are / they've" and the alternation
# had leading spaces on some branches, so `they've` sailed straight through:
#   "The code area is a mess, looks like they've got a mix of notes..."
LEAK_4 = ("The code area is a mess, looks like they've got a mix of notes and "
          "potential solutions scattered around.")
check("the second real leak is rejected", clean_proactive_line(LEAK_4) is None)
for bad in ["They've been at this a while.", "Looks like they'd rather not.",
            "They seem stuck.", "They have a lot of tabs open.",
            "Their screen is a mess.", "They’re on it."]:
    check(f"rejected: {bad[:34]}", clean_proactive_line(bad) is None)

print("\n[1f] 'they' is fine when she's also talking TO him")
# "your tests — they've been red a while" is a good line; the rule is a
# third-person pronoun with NO direct address anywhere.
for good in ["Your tests are failing — they've been red for a while.",
             "Those imports? They're unused."]:
    check(f"kept: {good[:38]}", clean_proactive_line(good) == good)

# ── 2. OCR readability ──────────────────────────────────────────────────────
print("\n[2] unreadable screen text is refused, not quoted")
check("the real garbled capture is rejected", not is_readable(GARBLED))
check("it scores near zero", readability(GARBLED) < 0.3)

print("\n[2b] real content still gets through")
for label, text in [
    ("leetcode prose", "Given a 1-indexed array of integers numbers that is "
                       "already sorted in non-decreasing order, find two numbers "
                       "such that they add up to a specific target number."),
    ("python", "def two_sum(numbers, target):\n    left, right = 0, len(numbers) - 1"),
    ("c++", "#include <vector>\nvector<int> twoSum(vector<int>& nums, int target) {"),
    ("traceback", "Traceback (most recent call last):\n  File \"a.py\", line 3\n"
                  "NameError: name 'x' is not defined"),
    ("problems bar", "2 Errors, 1 Warning. main.py line 42 undefined variable"),
]:
    check(f"readable: {label}", is_readable(text))

print("\n[2c] the error detector ignores mush")
from modules.error_detector import ErrorState, detect_error_state  # noqa: E402

r = detect_error_state(visible_text=GARBLED, terminal_text="")
check("no verdict invented from garbage", r.state is ErrorState.UNKNOWN)
r2 = detect_error_state(visible_text="2 Errors, 1 Warning", terminal_text="")
check("a real problems bar still reads", r2.state is ErrorState.HAS_ERRORS)
r3 = detect_error_state(visible_text="0 Problems", terminal_text="")
check("a clean bar still reads", r3.state is ErrorState.CLEAN)

# ── 3. language detection ───────────────────────────────────────────────────
print("\n[3] she can tell C++ from Python")
LEETCODE_CPP = {
    "app": "Comet",
    "title": "Two Sum II - Input Array Is Sorted - LeetCode - Comet",
    "visible_text": "C++ Auto Run Code Submit class Solution { public: "
                    "vector<int> twoSum(vector<int>& numbers, int target) {",
}
LEETCODE_PY = {
    "app": "Comet",
    "title": "Two Sum II - Input Array Is Sorted - LeetCode - Comet",
    "visible_text": "Python3 Auto Run Code Submit class Solution: "
                    "def twoSum(self, numbers: List[int], target: int) -> List[int]:",
}
check("the exact C++ session is detected", detect_language(LEETCODE_CPP) == "cpp")
check("...and labelled 'C++'", detect_label(LEETCODE_CPP) == "C++")
check("the Python session is detected", detect_language(LEETCODE_PY) == "python")

print("\n[3b] filenames are decisive")
for title, expect in [
    ("main.cpp - Visual Studio Code", "cpp"),
    ("brain.py - AURA", "python"),
    ("QuestsView.tsx - AURA", "typescript"),
    ("Main.java - IntelliJ", "java"),
    ("lib.rs - cargo", "rust"),
]:
    check(f"{title.split(' -')[0]} → {expect}",
          detect_language({"app": "editor", "title": title, "visible_text": ""}) == expect)

print("\n[3c] no guess when it isn't clear")
check("plain prose → None",
      detect_language({"app": "Chrome", "title": "news",
                       "visible_text": "the weather today is nice and clear"}) is None)
check("empty → None", detect_language({"app": "", "title": "", "visible_text": ""}) is None)
check("label of None is blank", detect_label({"app": "", "title": ""}) == "")

print("\n[3d] the error classifier is finally told the language")
# error_intelligence.classify() has had a `language` parameter since it was
# built; nothing ever passed one. The bridge now supplies it from the screen.
from core import v3_bridge  # noqa: E402
from core.brain import update_context  # noqa: E402

check("bridge has a screen-language lookup", hasattr(v3_bridge, "_screen_language"))
update_context(LEETCODE_CPP)
check("it reads the current screen", v3_bridge._screen_language() == "cpp")
update_context(LEETCODE_PY)
check("...and follows a language switch", v3_bridge._screen_language() == "python")
update_context({"app": "", "title": "", "visible_text": ""})
check("None when unknown", v3_bridge._screen_language() is None)

print("\n[3e] a C++ error is classified as C++, not Python")
from modules.error_intelligence import get_engine  # noqa: E402

r = get_engine().process("error: expected ';' before '}' token", language="cpp", record=False)
check("C++ error matched", r.classification.matched)
check("...as a C-family language",
      (r.classification.language or "").lower() in {"c", "cpp", "c++"})

print("\n" + "=" * 44)
print(f"{passed} passed, {failed} failed")
print("=" * 44)
sys.exit(1 if failed else 0)
