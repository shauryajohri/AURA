# modules/decision_engine.py
"""
Confidence scoring for voice targets before AURA acts on them.

The problem this fixes: "aura look at X" used to lock onto whatever
string X was, no matter how nonsensical, with zero verification. This
module checks whether X actually resolves to something real (an open
window, or at least a known app name) before AURA commits to it, and
flags low-confidence targets so the caller can ask for clarification
instead of silently locking onto garbage.

Confidence isn't a static lookup table — it's driven by your actual
open windows via screen_reader.find_window(), so it stays accurate as
whatever you have running changes, instead of going stale like a
hardcoded app list would.
"""

CONFIDENCE_THRESHOLD = 70  # below this, caller should ask for clarification

# Confidence levels by how we resolved the target
CONFIDENCE_OPEN_WINDOW   = 95  # a currently open window title actually matches
CONFIDENCE_KNOWN_ALIAS   = 60  # we recognize the name, but no open window matches right now
CONFIDENCE_UNKNOWN       = 15  # no match anywhere


def evaluate_target(target_phrase: str) -> dict:
    """
    Score how confident we are that `target_phrase` refers to something
    real and actionable.

    Returns:
        {
            "target": str,            # the original phrase, lowercased/stripped
            "resolved_app": str|None, # the actual window title, if one was found open
            "type": str,              # "open_window" | "known_alias" | "unknown"
            "confidence": int,        # 0-100
            "requires_clarification": bool,
        }
    """
    phrase = (target_phrase or "").lower().strip()

    if not phrase:
        return _result(phrase, None, "unknown", 0)

    # 1. Is something matching this actually open right now?
    # This is the strongest signal — we're not guessing, we found it.
    try:
        from modules.screen_reader import find_window
        window = find_window(phrase)
        if window is not None:
            return _result(phrase, window.title, "open_window", CONFIDENCE_OPEN_WINDOW)
    except Exception as e:
        print(f"[AURA Decision] find_window check failed: {e}")

    # 2. Do we at least recognize the name as a known app, even if it's
    # not open right now? (e.g. user said "spotify" but hasn't opened it yet)
    try:
        from modules.proactive import APP_ALIASES
        if phrase in APP_ALIASES or phrase in APP_ALIASES.values():
            return _result(phrase, None, "known_alias", CONFIDENCE_KNOWN_ALIAS)
    except Exception as e:
        print(f"[AURA Decision] alias check failed: {e}")

    # 3. No idea what this is.
    return _result(phrase, None, "unknown", CONFIDENCE_UNKNOWN)


def _result(phrase: str, resolved_app: str | None, target_type: str, confidence: int) -> dict:
    return {
        "target": phrase,
        "resolved_app": resolved_app,
        "type": target_type,
        "confidence": confidence,
        "requires_clarification": confidence < CONFIDENCE_THRESHOLD,
    }


def clarification_message(decision: dict) -> str:
    """A short spoken line asking the user to clarify an unclear target."""
    target = decision.get("target", "that")
    return (
        f"I don't have anything open that looks like \"{target}\" — "
        f"is that an app I should know, or do you want me to just watch "
        f"whatever's active right now?"
    )