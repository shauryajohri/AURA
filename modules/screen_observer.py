import re


ERROR_PATTERNS = [
    r"\btraceback\b",
    r"\bexception\b",
    r"\berror\b",
    r"\bfailed\b",
    r"\bfailure\b",
    r"\bdenied\b",
    r"\bnot found\b",
    r"\bmodule not found\b",
    r"\bsyntaxerror\b",
    r"\btypeerror\b",
    r"\bnameerror\b",
    r"\battributeerror\b",
    r"\bimporterror\b",
    r"\bvalueerror\b",
    r"\bpermission denied\b",
    r"\bconnection trouble\b",
    r"\brate_limit\b",
]


def summarize_visible_issue(context: dict) -> str | None:
    """Return a short observation if the visible screen text looks problematic."""
    text = (context or {}).get("visible_text", "")
    if not text:
        return None

    compact = " ".join(text.split())
    lower = compact.lower()
    if not any(re.search(pattern, lower) for pattern in ERROR_PATTERNS):
        return None

    sentences = re.split(r"(?<=[.!?])\s+|\s{2,}", compact)
    useful = [
        s.strip()
        for s in sentences
        if any(re.search(pattern, s.lower()) for pattern in ERROR_PATTERNS)
    ]
    snippet = useful[0] if useful else compact
    snippet = snippet[:220].strip()
    return f"I can see something that looks like an error: {snippet}"


def build_observation_reply(window_title: str, action: str, context: dict) -> str:
    issue = summarize_visible_issue(context)
    if issue:
        return (
            f"Looking at {window_title} now. {issue}. "
            "Do you want me to suggest what to change?"
        )

    if action and action != "observe":
        return (
            f"Looking at {window_title} now to {action}. "
            "I don't see an obvious terminal error yet; do you want me to keep watching?"
        )

    return (
        f"Looking at {window_title} now. "
        "I don't see an obvious terminal error yet; do you want me to keep watching?"
    )
