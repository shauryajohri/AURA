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
check("whole SEARCH leak is discarded", sanitize_text(LEAK_SEARCH, query=Q_JP) == "")
check("discarded even without the query", sanitize_text(LEAK_SEARCH) == "")

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
