# core/screen_text.py
"""
Is this OCR output actually readable, or is it mush?

AURA reads the screen with OCR, and OCR of a busy browser window produces
things like:

    © choy | Undetectabie © & 3 taateodecom / Two Sum Int ray le Sorted M
    Gait Youtube BM Translate Anendx-Smart_ [The Best river © Problemtist

The old gate in proactive.py accepted that — it only checked for 6+ alphabetic
words and a ratio of very short tokens, and mush like this clears both. So the
garbage was handed to the model, which dutifully described it back:

    "The visible content is garbled: '© choy | Undetectabie...'"

Being confidently wrong about what's on screen is worse than saying nothing,
so this module is deliberately strict: when in doubt, call it unreadable.

The signals that actually separate mush from real text:
  • symbol density — OCR sprinkles ©, ¢, |, », ~ through everything
  • vowel-less tokens — "BM", "Gait", "hgf" — real words have vowels
  • orphan fragments — 1-2 character tokens between real words
  • casing chaos — "Anendx-Smart_", "Problemtist"

Code is checked separately, because source code legitimately breaks all the
prose rules (symbols everywhere, short identifiers) and must never be rejected
as mush.
"""

from __future__ import annotations

import re

# Enough text to judge at all.
MIN_CHARS = 25
MIN_WORDS = 6

# Above this share of junk signals, the text is treated as unreadable.
JUNK_THRESHOLD = 0.42

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")
_VOWEL_RE = re.compile(r"[aeiouAEIOU]")

# Characters that appear when OCR mangles UI chrome — icons, borders, badges.
# Ordinary prose punctuation (. , ' " ? ! : ; - ( )) is excluded, and code is
# short-circuited before this runs, so brackets here cost nothing real.
_NOISE_RE = re.compile(r"[©®¢£¥§¶†‡•·~^`|\\<>{}\[\]_@#*/+=]")

# Markers that mean "this is source code / a terminal", where the prose rules
# don't apply. Checked before anything else.
_CODE_MARKERS = (
    "def ", "class ", "import ", "from ", "return", "#include", "std::",
    "public ", "private ", "function ", "const ", "let ", "var ", "=>",
    "print(", "console.log", "printf", "cout", "vector<", "int main",
    "if (", "for (", "while (", "});", "();", "self.", "->", "::",
    "traceback", "error:", "warning:", "exception", "at line", "npm ",
    "$ ", "PS ", "~/", "sudo ", "git ",
)

# Common English words — a cheap way to ask "is this a real sentence?"
# without shipping a dictionary. Deliberately tiny and high-frequency.
_COMMON = {
    "the", "and", "for", "you", "your", "with", "from", "this", "that",
    "have", "has", "not", "are", "was", "were", "will", "can", "all",
    "but", "how", "what", "when", "where", "which", "who", "why", "into",
    "out", "get", "set", "new", "add", "run", "use", "one", "two", "see",
    "code", "file", "line", "error", "test", "data", "time", "make",
    "problem", "solution", "input", "output", "array", "sorted", "return",
    "given", "example", "description", "editorial", "submissions",
}


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"\s+", text.strip()) if t]


def looks_like_code(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in _CODE_MARKERS)


def readability(text: str) -> float:
    """0.0 (mush) → 1.0 (clean text). Code short-circuits to 1.0."""
    if not text or not text.strip():
        return 0.0
    if looks_like_code(text):
        return 1.0

    toks = _tokens(text)
    if len(toks) < 2:
        return 0.0

    # No length floor. An early version required 25 characters and 6 words,
    # which rejected "0 Problems" and "2 Errors, 1 Warning" — the VS Code
    # status bar, i.e. the single most important short string AURA reads.
    # The ratios below judge short text perfectly well on their own.
    junk = 0
    for t in toks:
        # Numbers are real content ("2 Errors", "line 42"), not noise.
        if t.strip(",.;:()[]").isdigit():
            continue
        stripped = _WORD_RE.sub("", t)
        letters = _WORD_RE.findall(t)
        # A token that is mostly punctuation/symbols.
        if len(stripped) > max(1, len(t) // 2):
            junk += 1
            continue
        if not letters:
            junk += 1
            continue
        w = letters[0]
        # Real words have vowels. "BM", "hgf", "Gt" do not.
        if len(w) >= 3 and not _VOWEL_RE.search(w):
            junk += 1
            continue
        # Orphan 1-2 char alphabetic fragments — classic OCR shrapnel.
        if len(t) <= 2 and w.lower() not in {"a", "i", "in", "is", "it", "to",
                                             "of", "or", "on", "at", "by", "if",
                                             "no", "so", "up", "we", "do", "my"}:
            junk += 1
            continue
        # Casing chaos inside a word: "Undetectabie" is fine, "aBcDe" is not.
        if len(w) > 3 and re.search(r"[a-z][A-Z]", w[1:]):
            junk += 1

    junk_ratio = junk / len(toks)

    # Symbol noise is the decisive signal, and the one the old gate missed.
    # OCR of a browser chrome sprays ©, ¢, |, », ~ through the text. Counting
    # per token rather than per character keeps it scale-free.
    #
    # A word-frequency bonus was tried here first and had to go: this exact
    # garbled sample is full of REAL page words — "Two Sum", "Sorted",
    # "Description", "Editorial", "Submissions" — so recognising vocabulary
    # actively rewarded the mush. The layout being shredded is the problem,
    # not the words, and symbol density is what measures that.
    weird = len(_NOISE_RE.findall(text))
    weird_ratio = weird / len(toks)

    return max(0.0, min(1.0, 1.0 - junk_ratio - weird_ratio * 2.0))


def is_readable(text: str) -> bool:
    """The gate: may this text be quoted, referenced, or reasoned about?"""
    return readability(text) >= (1.0 - JUNK_THRESHOLD)


def safe_excerpt(text: str, limit: int = 400) -> str | None:
    """Text fit to put in a prompt, or None if it shouldn't be shown at all."""
    if not is_readable(text):
        return None
    return text[:limit]
