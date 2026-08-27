"""Which room does this message belong in?

Chats already give the conversation boundaries. A room says what a boundary is
ABOUT, and that is what can be inferred: score the message against every room's
keywords, name and topic, and if one clearly wins, move there.

Deliberately generic — nothing here knows about "coding" or "Japanese". Those
are rows in chat_rooms, so a room invented tomorrow is routed the same way.

A wrong switch costs far more than a missed one: it tears the conversation
away from the history it needed. So a challenger has to clear an absolute
floor AND beat the room you are already in by a margin.
"""

from __future__ import annotations

import re

MIN_SCORE = 1.8          # two real signals, or one distinctive one
SWITCH_MARGIN = 0.7
STICKINESS = 0.8         # weight of simply already being here
SUBSTRING_MIN_LEN = 5    # "KeyError" counts as "error"; "api" must not match "rapid"
DISTINCTIVE_BONUS = 0.8

_STOP = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be", "to",
    "of", "in", "on", "at", "for", "with", "it", "its", "this", "that", "you",
    "your", "my", "me", "i", "we", "us", "they", "them", "do", "does", "did",
    "so", "if", "as", "by", "from", "up", "out", "not", "no", "yes", "own",
    "room", "just", "some", "any", "what", "when", "how", "why", "who", "can",
    "will", "off", "clock", "else",
}

# Good topic markers that also appear in ordinary sentences. A hit still counts,
# it just is not decisive on its own — "I'm reading the docs" must not land in
# Japanese Study because "reading" is on its list.
_AMBIGUOUS = {
    "reading", "phrase", "class", "function", "test", "build", "note", "order",
    "particle", "radical", "translate", "happy", "food", "music", "movie",
    "friend", "family", "weekend", "sleep", "mood", "feeling", "query",
    "branch", "merge", "commit", "grammar", "vocab", "verb",
}

_WORD_RE = re.compile(r"[a-z0-9+#]+")


def _words(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower())
            if w not in _STOP and len(w) > 1}


def score_room(text: str, room: dict) -> float:
    """How strongly this message belongs in this room. 0 = no signal."""
    lowered = (text or "").lower()
    if not lowered.strip():
        return 0.0
    words = _words(lowered)
    score, hits = 0.0, 0

    for kw in room.get("keywords") or []:
        kw = kw.strip().lower()
        if not kw:
            continue
        if " " in kw:
            if kw in lowered:
                score += 2.0
                hits += 1
        elif kw in words:
            score += 1.0 + (0.0 if kw in _AMBIGUOUS else DISTINCTIVE_BONUS)
            hits += 1
        elif len(kw) >= SUBSTRING_MIN_LEN and any(kw in w for w in words):
            score += 0.8 + (0.0 if kw in _AMBIGUOUS else 0.4)
            hits += 1

    for term in _words(room.get("name", "")):
        if len(term) > 2 and term in words:
            score += 1.5
            hits += 1

    topic_terms = _words(room.get("topic", ""))
    if topic_terms:
        score += 0.35 * len(topic_terms & words)

    # One word can be a passing mention; two is what the message is about.
    if hits >= 2:
        score += 0.5
    return score


def switch_note(room: dict) -> str:
    """What AURA says when she moves you. A context change you cannot see is
    indistinguishable from her losing the thread, so she always says it."""
    return f"Switching us to {(room or {}).get('name') or 'another room'} — I'll keep this thread there."


def route(text: str) -> dict:
    """Decide, don't act. Returns {switch, room, room_id, from_room_id, note}."""
    from memory import store

    rooms = store.list_rooms()
    current = store.active_room()
    current_id = current["id"] if current else None
    current_score = score_room(text, current) if current else 0.0

    best, best_score = None, 0.0
    for r in rooms:
        if not r.get("auto_switch") or r["id"] == current_id:
            continue
        sc = score_room(text, r)
        if sc > best_score:
            best, best_score = r, sc

    switch = bool(best and best_score >= MIN_SCORE
                  and best_score >= current_score + STICKINESS + SWITCH_MARGIN)

    return {
        "switch": switch,
        "room": best if switch else current,
        "room_id": best["id"] if switch else current_id,
        "from_room_id": current_id,
        "note": switch_note(best) if switch else "",
        "score": best_score if switch else current_score,
    }
