"""
Regression tests for the chain-of-thought leak (2026-07-27).

Symptom: AURA printed her own deliberation instead of her reply —
"The user says: '...'. Likely they are continuing about their Aura project.
We need to respond in 1-2 sentences, no fluff..."

Two root causes, both covered below:

  1. _META_RE listed `said`/`asks` but not `says`, so the opening sentence of
     the leak wasn't recognised as meta.
  2. _peel_head stops filtering at the FIRST non-meta sentence, so once (1)
     let sentence one through, every later "We need to respond in 1-2
     sentences" streamed out untouched.

The fix splits leak-stripping (sanitize_text) from the 2-sentence clamp
(clean_response) so the personal/explain/longform lanes — which returned raw
text precisely to avoid the clamp — can be filtered without being truncated.

Run:  python test_reasoning_leak.py
"""

from core.ai_router import (
    _is_meta_sentence,
    _is_strong_meta,
    clean_response,
    sanitize_text,
)

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {label}")
    else:
        failed += 1
        print(f"  ✗ {label}")


# The two replies from the real transcript.
LEAK_CASUAL = (
    'The user says: "trying to add more smartness". Likely they are continuing '
    "about their Aura project. We need to respond in 1-2 sentences, no fluff, "
    'no "I" unless unavoidable, no mention of their activity unless they '
    "explicitly told us what they're doing. They said \"trying to add more "
    'smartness". That\'s a statement about what they\'re doing. According to '
    "rule 2: NEVER mention the user's activity unless they explicitly told you "
    "what they're doing."
)

LEAK_EXPLAIN = (
    'The user says: "Explain this clearly and conversationally. Do NOT write '
    'code unless explicitly asked: so there is an update that i am working '
    'with which is for aura domain like spcially built for coding" They want an '
    "explanation of something. So we need to give a clear, well-organized "
    "explanation of the topic they named. Also we need to follow the AURA "
    "style. TEACHING MODE — this OVERRIDES your default brevity rules. "
    "Thus we need to produce a teaching-mode explanation. We must not mention "
    "the user's screen. We must not use banned words: Certainly, Of course."
)

print("\n[the sentence that started it]")
check("'The user says:' is now meta", _is_meta_sentence('The user says: "hi".'))
check("'The user said' still meta", _is_meta_sentence("The user said hello."))
check("'The user asks' still meta", _is_meta_sentence("The user asks about X."))
check("'Likely they are' is meta", _is_meta_sentence("Likely they are continuing."))
check("'According to rule 2' is meta", _is_meta_sentence("According to rule 2: never."))

print("\n[strong vs weak separation]")
check("'the user' is STRONG", _is_strong_meta("The user says: hi."))
check("'TEACHING MODE' is STRONG", _is_strong_meta("TEACHING MODE overrides brevity."))
check("'banned words' is STRONG", _is_strong_meta("We must not use banned words."))
check(
    "'we need to' alone is only WEAK",
    _is_meta_sentence("we need to add an index") and not _is_strong_meta("we need to add an index"),
)

print("\n[the real leaks are fully removed]")
out_casual = sanitize_text(LEAK_CASUAL)
check("casual leak leaves nothing", out_casual == "")
check("no 'The user says' survives", "the user says" not in out_casual.lower())

out_explain = sanitize_text(LEAK_EXPLAIN)
check("explain leak leaves nothing", out_explain == "")
check("no 'TEACHING MODE' survives", "teaching mode" not in out_explain.lower())

print("\n[leak followed by a real answer keeps the answer]")
mixed = (
    "The user says they want help with sorting. We need to respond in 1-2 "
    "sentences. Quicksort averages O(n log n) but degrades to O(n^2) on "
    "already-sorted input. Use introsort if that worries you."
)
out = sanitize_text(mixed)
check("real answer survives", "Quicksort averages" in out)
check("introsort line survives", "introsort" in out)
check("deliberation is gone", "we need to respond" not in out.lower())
check("third-person narration gone", "the user says" not in out.lower())

print("\n[density rule: a mostly-meta response is discarded wholesale]")
# "That's a statement about what they're doing" matches no keyword, but a real
# reply is never mostly deliberation — so the whole monologue goes.
check("stray non-keyword meta sentence doesn't survive", sanitize_text(LEAK_CASUAL) == "")
check(
    "one flagged sentence does NOT nuke a real answer",
    "Postgres uses MVCC" in sanitize_text(
        "Postgres uses MVCC for isolation. The user asked about locking. "
        "Readers never block writers. That's the whole trick. It costs vacuum."
    ),
)

print("\n[meta AFTER real content is still removed — the old blind spot]")
trailing = (
    "Redis keeps everything in memory, which is why it's fast. "
    "We must not mention the user's screen. "
    "It persists to disk with snapshots."
)
out = sanitize_text(trailing)
check("first real sentence kept", "Redis keeps everything" in out)
check("last real sentence kept", "persists to disk" in out)
check("mid-text meta removed", "must not mention" not in out.lower())

print("\n[<think> blocks]")
check("closed think block stripped",
      sanitize_text("<think>plotting</think>Here's the answer.") == "Here's the answer.")
check("unterminated think block truncates",
      sanitize_text("Real answer here. <think>cut off mid-thou") == "Real answer here.")
check("uppercase THINK handled",
      "plotting" not in sanitize_text("<THINK>plotting</THINK>Answer."))

print("\n[legitimate answers are NOT damaged]")
legit = [
    "Quicksort averages O(n log n). Worst case is O(n^2).",
    "You'll want an index on that column, otherwise the scan is linear.",
    "Yeah, that's the tricky part about async generators.",
    "Redis is in-memory, Postgres is on disk. Different jobs.",
    "afternoon to you too, what's new with the Aura project?",
]
for text in legit:
    check(f"unchanged: {text[:38]}...", sanitize_text(text) == text)

print("\n[long lanes keep their length — the reason they skipped filtering]")
long_answer = (
    "A vector index maps embeddings to nearest neighbours. "
    "It matters because brute-force search is linear in corpus size. "
    "The key pieces are the embedding model, the distance metric, and the "
    "index structure. HNSW is the usual default. "
    "Start with the metric your embedding model was trained against."
)
out = sanitize_text(long_answer)
check("5 sentences survive sanitize_text", out.count(".") >= 5)
check("clean_response still clamps to 2", clean_response(long_answer).count(".") <= 2)

print("\n[clean_response now strips leaks too]")
out = clean_response(LEAK_CASUAL)
check("short lane drops the leak", "the user says" not in out.lower())

print("\n[self-referential sentence budgets are meta]")
check("'We need 2 sentences' is strong", _is_strong_meta("We need 2 sentences."))
check("'keep it to 2 sentences' is strong", _is_strong_meta("Keep it to 2 sentences."))
check("'3 sentences max' is strong", _is_strong_meta("3 sentences max."))
check(
    "a real sentence about counting isn't flagged",
    not _is_strong_meta("The parser splits it into sentences."),
)

print("\n[second live leak — SEARCH lane, 2026-07-27]")
# This one survived the first fix: none of its four sentences matched, and
# "no extra fluff" slipped past the `no fluff` pattern because of the inserted
# word. It also opened by quoting the user's own question back.
Q_JP = (
    "i need info i am newbie with japanese i need info abt this like from "
    "where i can learn and how can i learn. my target is to clear n3 in next "
    "6 months"
)
LEAK_SEARCH = (
    'my target is to clear n3 in next 6 months" No extra fluff. '
    "Should we ask clarifying? We have enough info to give suggestions. "
    'Provide concise answer: maybe "Start with Genki I & II plus Wanikani '
    "for kanji, and practice daily with Bunpro grammar; aim for 2 hours a day."
)
check("'no extra fluff' now matches", _is_strong_meta("No extra fluff."))
check("'Should we ask clarifying?' matches", _is_strong_meta("Should we ask clarifying?"))
check("'We have enough info' matches", _is_strong_meta("We have enough info to give suggestions."))
check("'Provide concise answer' matches", _is_strong_meta("Provide concise answer: maybe this."))
# Behaviour CHANGED 2026-07-30 and deliberately so: this leak ends with
# "Provide concise answer: maybe "Start with Genki I…" — the real reply is
# sitting right there after the handover phrase. It used to be discarded
# wholesale (fallback line shown); now the tail is recovered, de-quoted and
# capitalised. The deliberation must still be gone either way.
for _q in (Q_JP, ""):
    _out = sanitize_text(LEAK_SEARCH, query=_q)
    _label = "with query" if _q else "without query"
    check(f"SEARCH leak: deliberation gone ({_label})",
          "should we ask" not in _out.lower() and "enough info" not in _out.lower())
    check(f"SEARCH leak: prompt echo gone ({_label})", "clear n3 in next" not in _out.lower())
    check(f"SEARCH leak: the settled answer is recovered ({_label})", "Genki I" in _out)
    check(f"SEARCH leak: filler quote stripped ({_label})", not _out.startswith('maybe'))

print("\n[query-echo detection]")
check(
    "verbatim restatement of the prompt is stripped",
    sanitize_text("my target is to clear n3 in next 6 months. Genki I is the standard start.",
                  query=Q_JP).startswith("Genki"),
)
check(
    "a real answer to that same query is untouched",
    sanitize_text(
        "Start with Genki I for grammar and WaniKani for kanji. "
        "Two hours a day gets you to N3 in six months.",
        query=Q_JP,
    ).startswith("Start with Genki"),
)
check(
    "short overlaps are not treated as echoes",
    sanitize_text("Your N3 target is realistic.", query=Q_JP) == "Your N3 target is realistic.",
)

print("\n[code blocks survive the filter byte-for-byte]")
# Regression: the filter whitespace-normalised everything, which flattened a
# C++ answer into "```cpp class Solution { public: vector<int> twoSum(..." —
# one unreadable line in the chat bubble.
CPP_ANSWER = """Here's a clean C++ solution using two pointers.

```cpp
class Solution {
public:
    vector<int> twoSum(vector<int>& numbers, int target) {
        int left = 0, right = numbers.size() - 1;
        while (left < right) {
            int sum = numbers[left] + numbers[right];
            if (sum == target) return {left + 1, right + 1};
            if (sum < target) ++left; else --right;
        }
        return {};
    }
};
```

That's O(n) time and O(1) space."""

out = sanitize_text(CPP_ANSWER)
check("line breaks preserved", out.count("\n") == CPP_ANSWER.count("\n"))
check("indentation preserved", "        int left = 0" in out)
check("both fences intact", out.count("```") == 2)
check("language tag intact", "```cpp" in out)
check("prose before the block kept", out.startswith("Here's a clean C++"))
check("prose after the block kept", out.rstrip().endswith("O(1) space."))

print("\n[code survives even when the prose around it is a leak]")
out = sanitize_text("The user wants C++. We need to respond concisely.\n\n"
                    "```cpp\nint x = 1;\n```")
check("deliberation removed", "the user wants" not in out.lower())
check("code still returned", "int x = 1;" in out)
check("fences still intact", out.count("```") == 2)

print("\n[an unterminated block — a cut-off stream — is still code]")
out = sanitize_text("Here you go.\n\n```python\ndef f():\n    return 1")
check("partial block keeps its newlines", "\n    return 1" in out)

print("\n[prose-only answers are still normalised]")
check("runs of spaces collapse",
      sanitize_text("Two   pointers    work here.") == "Two pointers work here.")

print("\n[third live leak — screen-reading lane, 2026-07-30]")
# Nothing in this one named a rule or planned an answer: it narrated the
# handover from thinking to replying ("So answer:", "So we can say:") and
# checked its own work ("That's one sentence?"). Every sentence looked
# innocent to the old patterns, so the whole monologue printed.
LEAK_SEAM = (
    "Looking at Merge Sorted Array - LeetCode - Comet now. "
    "So answer: You're looking at the Comet project (Merge Sorted Array on "
    "LeetCode). No mention of user's activity unless they explicitly told. "
    "That's explicit. So we can say: You're currently viewing the Comet "
    "project — the Merge Sorted Array LeetCode problem. That's one sentence?"
)
check("'So answer:' is strong", _is_strong_meta("So answer: you're on LeetCode."))
check("'Final answer:' is strong", _is_strong_meta("Final answer: 42."))
check("'So we can say:' is strong", _is_strong_meta("So we can say: it's fine."))
check("\"user's activity\" is strong", _is_strong_meta("No mention of user's activity."))
check("'unless they explicitly' is strong", _is_strong_meta("Unless they explicitly told."))
check("'That's one sentence?' is strong", _is_strong_meta("That's one sentence?"))

out = sanitize_text(LEAK_SEAM)
check("deliberation is gone", "so answer" not in out.lower())
check("self-check is gone", "one sentence" not in out.lower())
check("third-person narration gone", "user's activity" not in out.lower())
# The reply it settled on sits after the LAST handover phrase — keep it rather
# than binning the turn.
check("the settled answer is recovered", "currently viewing the Comet" in out)
check("only the answer remains", out.count(".") <= 2)

print("\n[the seam cut doesn't eat legitimate prose]")
check(
    "'we can say' mid-explanation without a colon is left alone",
    sanitize_text("From the invariant we can say the loop terminates.")
    == "From the invariant we can say the loop terminates.",
)
check(
    "a trailing 'final answer:' with nothing after it isn't trusted",
    "Two pointers" in sanitize_text("Two pointers work here. Final answer:"),
)
check(
    "an answer that merely mentions sentences is untouched",
    sanitize_text("Split the paragraph into sentences first.")
    == "Split the paragraph into sentences first.",
)
check(
    "one trailing meta sentence doesn't nuke a two-sentence answer",
    "Redis is in-memory" in sanitize_text("Redis is in-memory. That's one sentence?"),
)

print("\n[guard_output refuses to print a monologue]")
from core.brain import guard_output  # noqa: E402

out = guard_output("The user asks X. We must not answer. According to rule 2, no.")
check("all-meta gets the fallback line", "train of thought" in out.lower())
check("no leak text in the fallback", "the user asks" not in out.lower())
check("normal reply passes through", guard_output("Yeah that works. Ship it.") == "Yeah that works. Ship it.")

print("\n" + "=" * 40)
print(f"{passed} passed, {failed} failed")
print("=" * 40)
raise SystemExit(1 if failed else 0)
