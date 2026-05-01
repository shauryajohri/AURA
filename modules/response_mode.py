"""
AURA Response Mode Classifier
------------------------------
Classifies LLM response into a mode BEFORE it hits speech planner.

Modes:
  COMMAND  → short, confident, no fluff
  CODE     → don't read, just say "check screen"
  EXPLAIN  → slower, chunked, structured
  CHAT     → fast, casual, flowing
  LONG     → offer summary instead
"""

import re

# code indicators
_CODE_PATTERNS = [
    r"```",
    r"def ",
    r"class ",
    r"import ",
    r"for .+ in ",
    r"if __name__",
    r"return ",
    r"print\(",
    r"#.*\n",
    r"\{\s*\n",
]

# explain indicators
_EXPLAIN_PATTERNS = [
    r"\b(think of it|imagine|basically|essentially|works by|means that)\b",
    r"\b(first|second|third|step \d|finally)\b",
    r"\b(for example|for instance|such as|like when)\b",
]

# command indicators  
_COMMAND_PATTERNS = [
    r"^(opening|on it|done|got it|launched|closed|saved|noted)",
    r"^(here you go|checking|loading|fetching)",
]

# long response threshold
LONG_THRESHOLD = 120  # words


def classify_mode(response: str, intent: str = "CASUAL") -> str:
    """
    Returns: COMMAND | CODE | EXPLAIN | CHAT | LONG
    """
    text = response.strip()

    # intent-based overrides first
    if intent == "COMMAND":
        return "COMMAND"

    # code detection
    for pattern in _CODE_PATTERNS:
        if re.search(pattern, text):
            return "CODE"

    # command-style response
    lower = text.lower()
    for pattern in _COMMAND_PATTERNS:
        if re.search(pattern, lower):
            return "COMMAND"

    # long response
    word_count = len(text.split())
    if word_count > LONG_THRESHOLD:
        return "LONG"

    # explain detection
    for pattern in _EXPLAIN_PATTERNS:
        if re.search(pattern, lower, re.IGNORECASE):
            return "EXPLAIN"

    return "CHAT"


# mode → speech behavior
MODE_BEHAVIOR = {
    "CHAT": {
        "speed_factor":  1.10,   # faster
        "pause_scale":   0.6,    # shorter pauses
        "add_filler":    False,
    },
    "EXPLAIN": {
        "speed_factor":  0.90,   # slower, clearer
        "pause_scale":   1.4,    # longer pauses between chunks
        "add_filler":    True,
    },
    "COMMAND": {
        "speed_factor":  1.05,
        "pause_scale":   0.4,    # very short pauses
        "add_filler":    False,
    },
    "CODE": {
        "speed_factor":  1.0,
        "pause_scale":   0.5,
        "add_filler":    False,
    },
    "LONG": {
        "speed_factor":  1.0,
        "pause_scale":   1.0,
        "add_filler":    False,
    },
}

# code mode responses — random pick
_CODE_REPLIES = [
    "done. check your screen.",
    "it's up on your screen — want me to walk through it?",
    "code's there. want an explanation?",
    "check it. want me to break it down?",
]

# long mode responses
_LONG_REPLIES = [
    "that's a lot — want the short version?",
    "got a full answer. want me to summarize?",
    "it's detailed. want just the key points?",
]

import random

def get_code_reply() -> str:
    return random.choice(_CODE_REPLIES)

def get_long_reply(full_response: str) -> str:
    return random.choice(_LONG_REPLIES)