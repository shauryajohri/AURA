"""
core/voice_gate.py
------------------
Priority-based arbiter so multiple background loops (proactive,
attention_engine, curiosity_engine, error_detector, etc.) never both
decide to speak at once. Replaces the old "first one to grab a
20-second timestamp wins" gate with an actual priority system.

Default priorities (higher wins):
    100  code_error      (error_detector / proactive error flips)
     20  attention        (attention_engine stages/comebacks)
     15  curiosity        (curiosity_engine)
     10  observation      (proactive interaction/stuck/locked lines)

How it works:
    Each caller, instead of speaking immediately, calls
    request_to_speak(source, priority, message). This doesn't speak —
    it registers a bid. A short collection window (COLLECT_WINDOW
    seconds) is opened on the FIRST bid; any other bids that land
    inside that same window compete for the slot. When the window
    closes, the highest-priority bid wins and its message is returned
    to whichever thread asked to retrieve it. Losing callers get None
    back and should not speak.

    Because the existing loops are not designed to "wait and see if
    they won," this is implemented as a short blocking call: the
    calling thread sleeps out the remainder of the collection window
    and then finds out if it won. This is fine here — these are
    already background daemon threads on multi-second cadences, so a
    sub-second wait costs nothing.

Also enforces a MIN_GAP_SECONDS global cooldown after ANY winning
speech, same as the old gate, so winners can't fire back-to-back.
"""

import time
import threading

_lock = threading.Lock()
_last_spoken_time = 0.0
MIN_GAP_SECONDS = 20  # minimum gap after any winning speech

COLLECT_WINDOW = 0.35  # seconds — how long bids are collected before judging

PRIORITY = {
    "code_error":  100,
    "attention":    20,
    "curiosity":    15,
    "observation":  10,
}

# Active bidding round state
_round_open = False
_round_deadline = 0.0
_round_bids = []   # list of dicts: {source, priority, message, time}
_round_id = 0
_round_results = {}  # round_id -> winning bid dict (judged once, read by all bidders)


def _default_priority(source: str) -> int:
    return PRIORITY.get(source, 0)


def can_speak() -> bool:
    """Global cooldown check — kept for any caller that just wants the
    simple gap check without going through the bidding round."""
    with _lock:
        return (time.time() - _last_spoken_time) >= MIN_GAP_SECONDS


def mark_spoken():
    global _last_spoken_time
    with _lock:
        _last_spoken_time = time.time()


def seconds_since_last_spoken() -> float:
    with _lock:
        return time.time() - _last_spoken_time


def request_to_speak(source: str, message: str, priority: int = None) -> bool:
    """
    Call this instead of speaking directly. Blocks for up to
    COLLECT_WINDOW seconds to let other near-simultaneous requests in,
    then returns True only if this call's bid won the round AND the
    global cooldown has elapsed. Callers should speak immediately if
    (and only if) this returns True.

    source:   short string key, e.g. "attention", "observation",
              "code_error", "curiosity" — used for default priority
              if `priority` isn't given explicitly.
    message:  the text this caller wants to say (used only for
              logging/debugging here — caller still owns actually
              speaking it).
    priority: optional explicit override of the default priority.
    """
    global _round_open, _round_deadline, _round_bids, _round_id

    if not can_speak():
        return False

    bid_priority = priority if priority is not None else _default_priority(source)

    with _lock:
        now = time.time()
        if not _round_open:
            _round_open = True
            _round_deadline = now + COLLECT_WINDOW
            _round_bids = []
            _round_id += 1
        my_round_id = _round_id
        my_bid = {
            "source": source,
            "priority": bid_priority,
            "message": message,
            "time": now,
        }
        _round_bids.append(my_bid)
        wait_time = max(0.0, _round_deadline - now)

    if wait_time > 0:
        time.sleep(wait_time)

    with _lock:
        # The round is judged exactly ONCE — by whichever bidder wakes
        # first — and the winning bid is cached so every other bidder in
        # the same round sees the same verdict (fixes the race where a
        # losing thread cleared the bids and the real winner found an
        # empty round and stayed silent).
        winner = _round_results.get(my_round_id)
        if winner is None:
            if my_round_id != _round_id or not _round_bids:
                return False
            winner = max(_round_bids, key=lambda b: (b["priority"], -b["time"]))
            _round_results[my_round_id] = winner
            _round_open = False
            _round_bids = []
            # Prune old verdicts so the cache can't grow unbounded.
            for rid in [r for r in _round_results if r < my_round_id - 10]:
                del _round_results[rid]

        won = winner is my_bid  # identity — no accidental ties on equal bids

        if won:
            _last_spoken_time = time.time()
            print(f"[VoiceGate] '{source}' won (priority {bid_priority}): {message[:60]}")
        return won


def get_priority(source: str) -> int:
    return _default_priority(source)