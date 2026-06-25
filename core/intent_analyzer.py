"""
AURA Prompt Engine — Step 1: Intent Analyzer
Detects the user's domain, goal, and complexity score from raw input.
"""

import re
from dataclasses import dataclass
from typing import Optional

DOMAIN_KEYWORDS = {
    "CODING": [
        "code", "function", "bug", "fix", "implement", "refactor", "class",
        "module", "script", "api", "async", "loop", "error", "import", "test",
        "proactive", "brain", "memory", "ui", "backend", "frontend", "python",
        "file", "variable", "method", "optimize", "improve", "add", "build",
    ],
    "RESEARCH": [
        "research", "explain", "how does", "what is", "summarize", "find",
        "look up", "article", "paper", "information", "learn", "understand",
    ],
    "WRITING": [
        "write", "draft", "email", "essay", "letter", "message", "blog",
        "summarize text", "rewrite", "edit",
    ],
    "SYSTEM": [
        "install", "configure", "setup", "terminal", "shell", "command",
        "process", "memory usage", "cpu", "performance", "run",
    ],
    "PLANNING": [
        "plan", "roadmap", "architecture", "design", "structure", "strategy",
        "feature", "milestone", "task", "todo",
    ],
}

COMPLEXITY_SIGNALS = {
    # Raises complexity
    "high": [
        "entire", "full", "all", "everything", "redesign", "overhaul",
        "multiple files", "architecture", "refactor", "system", "complex",
        "from scratch", "integrate", "pipeline",
    ],
    # Lowers complexity
    "low": [
        "small", "quick", "simple", "minor", "just", "only", "single",
        "one line", "tiny", "brief",
    ],
}

PROJECT_HINTS = {
    "AURA": ["aura", "proactive", "brain.py", "memory.py", "proactive.py",
             "brain", "suggestion", "session_memory", "voice_output"],
}


@dataclass
class IntentResult:
    intent: str          # CODING | RESEARCH | WRITING | SYSTEM | PLANNING | GENERAL
    goal: str            # Clean 1-sentence summary of what user wants
    complexity: int      # 0–100
    project: Optional[str]
    domain_confidence: float


def analyze_intent(user_input: str) -> IntentResult:
    text = user_input.lower()

    # --- Domain detection ---
    domain_scores: dict[str, int] = {d: 0 for d in DOMAIN_KEYWORDS}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                domain_scores[domain] += 1

    best_domain = max(domain_scores, key=lambda d: domain_scores[d])
    top_score = domain_scores[best_domain]
    total_hits = sum(domain_scores.values()) or 1
    confidence = round(top_score / total_hits, 2)

    if top_score == 0:
        best_domain = "GENERAL"
        confidence = 0.0

    # --- Project detection ---
    detected_project = None
    for project, hints in PROJECT_HINTS.items():
        if any(h in text for h in hints):
            detected_project = project
            break

    # --- Complexity score ---
    base = 40
    for word in COMPLEXITY_SIGNALS["high"]:
        if word in text:
            base += 10
    for word in COMPLEXITY_SIGNALS["low"]:
        if word in text:
            base -= 10
    # Longer inputs = more complex
    word_count = len(user_input.split())
    base += min(word_count // 5, 20)
    complexity = max(10, min(100, base))

    # --- Goal extraction (clean up the input) ---
    goal = _extract_goal(user_input)

    return IntentResult(
        intent=best_domain,
        goal=goal,
        complexity=complexity,
        project=detected_project,
        domain_confidence=confidence,
    )


def _extract_goal(text: str) -> str:
    """Strip filler phrases and return a clean goal sentence."""
    fillers = [
        r"^(can you|could you|please|hey|hi|aura)[,\s]+",
        r"^(i want to|i need to|i'd like to|help me to?)\s+",
        r"^(can you help me|help me)[,\s]+",
    ]
    result = text.strip()
    for pattern in fillers:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE).strip()
    # Capitalize first letter
    return result[0].upper() + result[1:] if result else text
