"""
core/guard/commands.py
----------------------
The owner's spoken/typed permissions for other people:

    "aura, you can help him"            → guest pass (30 min default)
    "let her use you for an hour"       → guest pass, 60 min
    "he's with me, help him out"        → guest pass
    "stop helping him" / "revoke guest" → passes revoked

Only ever parsed for a message that already passed as the OWNER — a guest
saying "you can help me" is just a sentence.
"""

from __future__ import annotations

import re

DEFAULT_MINUTES = 30
MAX_MINUTES = 12 * 60

_PERSON = (r"(?:him|her|them|my\s+(?:friend|brother|sister|mom|mum|dad|cousin|colleague"
           r"|roommate|buddy|girlfriend|boyfriend|wife|husband)|this\s+(?:guy|person|girl|kid))")
# A bare name ("you can help Rahul") — but "help me", "help fix this" and
# "help with the code" are ordinary requests, so the word can't be a pronoun /
# filler and must END the clause (or lead into "out", "for an hour", …).
_NAME = (r"(?!(?:me|us|myself|ourselves|you|yourself|it|this|that|these|those|with|out"
         r"|so|now|here|there|again|everyone|anyone|people)\b)[a-z]{2,15}"
         r"(?=\s*(?:$|[.,!?]|(?:out|for|with|too|now|please|today)\b))")
_WHO = rf"(?:{_PERSON}|{_NAME})"

_GRANT = re.compile(
    r"(?ix)\b(?:"
    rf"you\s+can\s+(?:help|talk\s+to)\s+{_WHO}"
    rf"|(?:please\s+)?help\s+{_WHO}\s+out"
    rf"|let\s+{_WHO}\s+(?:use|talk\s+to)\s+you"
    rf"|give\s+{_WHO}\s+access"
    rf"|(?:he|she|they)(?:'s|\s+is|'re|\s+are)\s+with\s+me"
    r"|(?:allow|enable)\s+guest(?:\s+(?:mode|access))?"
    r"|guest\s+(?:mode|access)\s+on"
    r")"
)

_REVOKE = re.compile(
    r"(?ix)\b(?:"
    rf"(?:stop|don'?t|do\s+not)\s+(?:help|helping|talk(?:ing)?\s+to|answer(?:ing)?)\s+{_PERSON}"
    rf"|(?:don'?t|do\s+not)\s+let\s+{_PERSON}\s+(?:use|talk\s+to)\s+you"
    r"|revoke\s+(?:guest|(?:his|her|their)\s+access|access)"
    r"|(?:disable|end|remove)\s+guest(?:\s+(?:mode|access|pass))?"
    r"|guest\s+(?:mode|access)\s+off"
    r"|only\s+(?:talk\s+to|answer|help)\s+me"
    r")"
)

# "nobody can use you", "don't help anyone" — "you can help" would also match
# grant on some phrasings, so negations are checked first.
_NEGATED_GRANT = re.compile(r"(?i)\b(?:don'?t|do\s+not|never|stop)\b[^.?!]{0,20}\b(?:help|let|give|talk)")

_DURATION = re.compile(
    r"(?ix)\bfor\s+(?:(an?|one|half\s+an?|\d{1,3}(?:\.\d)?)\s*"
    r"(hours?|hrs?|h|minutes?|mins?|m)\b|the\s+(day|rest\s+of\s+the\s+day|evening))"
)

_WORDS = {"a": 1, "an": 1, "one": 1}


def parse_minutes(text: str) -> int:
    m = _DURATION.search(text or "")
    if not m:
        return DEFAULT_MINUTES
    if m.group(3):  # "for the day" and friends
        return MAX_MINUTES
    qty, unit = m.group(1).lower(), m.group(2).lower()
    if qty.startswith("half"):
        n = 0.5
    else:
        n = _WORDS.get(qty) or float(qty)
    minutes = n * 60 if unit.startswith("h") else n
    return int(max(1, min(MAX_MINUTES, round(minutes))))


def parse(text: str) -> dict | None:
    """{"action": "grant", "minutes": n} | {"action": "revoke"} | None."""
    t = (text or "").strip()
    if not t or len(t) > 240:  # a command is a sentence, not an essay
        return None
    if _REVOKE.search(t):
        return {"action": "revoke"}
    if _GRANT.search(t) and not _NEGATED_GRANT.search(t):
        return {"action": "grant", "minutes": parse_minutes(t)}
    return None
