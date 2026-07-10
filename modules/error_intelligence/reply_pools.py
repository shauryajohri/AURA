# modules/error_intelligence/reply_pools.py
"""
Reply selection + relationship escalation.

The KB gives each error a base pool of one-liners. This layer decides which
line Donna actually says, factoring in:

  1. Level — SILLY errors get jokes; CONCEPTUAL/DANGEROUS drop the jokes and
     get serious, supportive lines straight from the KB pool.
  2. Repeat count *today* — the running gag. The 1st missing semicolon is a
     light jab; the 20th is "I'm keeping one in my pocket for you." This is the
     relationship integration from the V3 doc.
  3. Personality — a light tone tweak so 'roast'/'chaotic' packs read
     different from 'professional', without needing separate pools per pack.

Escalation lines are phrased around the error's label noun (e.g. "semicolon",
"parenthesis") so the running gag works for *any* silly error, not just
semicolons.
"""

from __future__ import annotations

import random

from .models import KBEntry, Level

# Repeat-count → escalation tier. Tiers are (min_count_inclusive, tier_name).
# Checked high→low; the first whose threshold is met wins.
_TIERS = [
    (20, "legendary"),
    (10, "exasperated"),
    (5, "personal"),
    (3, "again"),
    (1, "first"),
]


def _tier_for(count_today: int) -> str:
    for threshold, name in _TIERS:
        if count_today >= threshold:
            return name
    return "first"


def _noun(entry: KBEntry) -> str:
    """A short noun for the running gag, derived from the label.
    'Missing semicolon' -> 'semicolon', 'Missing parenthesis' -> 'parenthesis'."""
    label = entry.label.lower()
    for prefix in ("missing ", "likely ", "unexpected "):
        if label.startswith(prefix):
            return label[len(prefix):]
    return label


# Escalation overlays for SILLY repeats. {noun} is filled per-error.
_ESCALATION = {
    "again": [
        "Again? That's twice now with the {noun}.",
        "The {noun} is back. We keep meeting like this.",
    ],
    "personal": [
        "Okay, I'm starting to think you and the {noun} have personal issues.",
        "Five {noun} errors. At this point it's not an accident, it's a relationship.",
    ],
    "exasperated": [
        "We're in double digits on the {noun} now. I'm not mad, I'm just... documenting it.",
        "Ten of these. The {noun} has become a recurring character in your day.",
    ],
    "legendary": [
        "Twenty. I'm just going to keep a {noun} in my pocket for you at this point.",
        "This is a record. The {noun} deserves its own commit history.",
    ],
}

# Small tone suffixes per personality pack (matches relationship_engine packs).
_TONE_SUFFIX = {
    "roast": "",            # base lines are already sharp enough
    "chaotic": "",
    "professional": None,   # professional pack → strip jokes, see below
    "companion": "",
    "japanese": None,
}

# For packs that shouldn't joke, a calm neutral line per level.
_NEUTRAL = {
    Level.SILLY: "Small syntax fix — {label}. Quick one.",
    Level.MEDIUM: "{label}. Want me to explain why?",
}


def select_reply(
    entry: KBEntry,
    count_today: int,
    personality: str = "companion",
    rng: random.Random | None = None,
) -> str:
    """Pick the line Donna says for a matched, tracked error.

    `count_today` should already include the current occurrence (so the first
    time it's 1). `rng` is injectable for deterministic tests.
    """
    r = rng or random

    serious = entry.level >= Level.CONCEPTUAL

    # Serious errors: no escalation, no jokes — draw a supportive line straight
    # from the KB pool regardless of personality.
    if serious:
        pool = entry.reply_pool or (
            f"{entry.label}. This one's worth slowing down for — want to work through it?",
        )
        return r.choice(list(pool))

    # Non-serious. Professional/japanese packs stay calm rather than joking.
    if _TONE_SUFFIX.get(personality) is None:
        template = _NEUTRAL.get(entry.level, "{label}.")
        return template.format(label=entry.label, noun=_noun(entry))

    tier = _tier_for(count_today)

    # First occurrence (or MEDIUM level, which doesn't have a running gag):
    # use the base pool.
    if tier == "first" or entry.level != Level.SILLY:
        pool = entry.reply_pool or (f"{entry.label}.",)
        return r.choice(list(pool))

    # Repeat SILLY error → escalation overlay.
    overlays = _ESCALATION.get(tier)
    if not overlays:
        pool = entry.reply_pool or (f"{entry.label}.",)
        return r.choice(list(pool))
    return r.choice(overlays).format(noun=_noun(entry))


def victory_line(entry_label: str | None = None, personality: str = "companion") -> str:
    """Said when an error clears after being present — the 'I bullied the bug
    into leaving' beat from the doc."""
    lines = [
        "See? I bullied the bug into leaving.",
        "Build's green. That's what I like to see.",
        "Fixed. The endangered parenthesis has been returned to the wild.",
        "Clean now. We make a decent team.",
    ]
    return random.choice(lines)
