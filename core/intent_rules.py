"""
core/intent_rules.py
--------------------
The deterministic safety net over the LLM intent classifier.

Lives on its own so everything that classifies a message (the desktop brain,
the public web demo) applies the same rules without importing the whole
brain, which drags in the personal memory store, the screen and the voice.
"""

# A CODING verdict is only trusted if the message actually asks for code to be
# produced/modified. "get me info for dna storage system" sounds technical, so
# the LLM classifier sometimes mislabels it CODING → wrong (Laguna coding)
# model. These cues gate that.
CODE_ACTION_CUES = (
    "write ", "code", "implement", "refactor", "rewrite", "debug", "fix ",
    "patch", "compile", "function", "class ", "def ", "script", "program",
    "snippet", "syntax", "```", "leetcode", "regex", "algorithm to",
    ".py", ".js", ".ts", ".cpp", ".java", ".cs", ".go", ".rs", ".html", ".css",
)
# Broad info cues — used ONLY to pick SEARCH vs CASUAL when downgrading a wrong
# CODING verdict. "what is/are" included; bare "what's" is left out because it
# overlaps greetings ("what's up").
INFO_CUES = (
    "info", "information", "tell me about", "what is", "what are", "who is",
    "how does", "how do", "how to", "explain", "overview", "details",
    "research", "find out", "look up", "learn about", "difference between",
    "meaning of", "summary of", "facts about", "get me info", "give me info",
)
# Narrow, unambiguous info cues — safe to UPGRADE a CASUAL verdict to SEARCH
# without stealing greetings/small-talk.
STRONG_INFO_CUES = (
    "info", "information", "tell me about", "get me info", "give me info",
    "explain", "research", "look up", "find out", "learn about",
    "details about", "overview of", "summary of", "facts about",
)

# What the classifier is allowed to answer; anything else reads as CASUAL.
VALID_INTENTS = ("CASUAL", "CODING", "SAVE", "REMINDER", "SEARCH", "COMMAND", "RECALL")


def correct_intent(query: str, intent: str) -> str:
    """Deterministic safety net over the LLM classifier. Stops technical-
    sounding INFORMATION requests from being routed to the coding model."""
    q = query.lower()
    has_code_cue = any(c in q for c in CODE_ACTION_CUES)
    if intent == "CODING" and not has_code_cue:
        # CODING with no "produce code" cue → it's really an info/general ask.
        return "SEARCH" if any(c in q for c in INFO_CUES) else "CASUAL"
    if intent == "CASUAL" and not has_code_cue and any(c in q for c in STRONG_INFO_CUES):
        # Route genuine info requests to the research model, not small-talk.
        return "SEARCH"
    return intent
