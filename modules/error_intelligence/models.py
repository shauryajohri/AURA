# modules/error_intelligence/models.py
"""
Shared data model for the Error Intelligence Engine (AURA V3).

Kept dependency-free on purpose: every other module in this package imports
from here, so this file must never import from its siblings (avoids circular
imports) and must not touch the filesystem, network, or the LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Level(IntEnum):
    """How much this error 'deserves'. Higher = more serious.

    Ordering matters — the engine uses `level >= Level.CONCEPTUAL` to decide
    when Donna stops joking, so keep these in ascending severity.
    """
    SILLY = 1        # 😂 missing ; ) }, typos, forgot import
    MEDIUM = 2       # 🙂 type mismatch, wrong args, simple null
    CONCEPTUAL = 3   # 🧠 deadlock, race, infinite recursion, bad architecture
    DANGEROUS = 4    # 🔥 rm -rf, git reset --hard, data-loss operations


class Category(IntEnum):
    """The 6 buckets shown in the Problems UI. Independent of Level:
    a RUNTIME error can be MEDIUM or CONCEPTUAL depending on the case."""
    SYNTAX = 1    # 😂
    TYPING = 2    # 🙂
    LOGIC = 3     # 🤔
    CONCEPT = 4   # 🧠
    RUNTIME = 5   # ⚠
    CRITICAL = 6  # 🔥


LEVEL_EMOJI = {
    Level.SILLY: "😂",
    Level.MEDIUM: "🙂",
    Level.CONCEPTUAL: "🧠",
    Level.DANGEROUS: "🔥",
}

CATEGORY_EMOJI = {
    Category.SYNTAX: "😂",
    Category.TYPING: "🙂",
    Category.LOGIC: "🤔",
    Category.CONCEPT: "🧠",
    Category.RUNTIME: "⚠",
    Category.CRITICAL: "🔥",
}

CATEGORY_LABEL = {
    Category.SYNTAX: "Syntax",
    Category.TYPING: "Typing",
    Category.LOGIC: "Logic",
    Category.CONCEPT: "Concept",
    Category.RUNTIME: "Runtime",
    Category.CRITICAL: "Critical",
}


@dataclass(frozen=True)
class KBEntry:
    """One row in the Error Knowledge Base.

    `pattern` is a compiled-at-load regex (kept as a raw string here; the KB
    compiles it once). `reply_pool` holds the escalation-agnostic *base* lines
    for this error — the reply layer adds relationship escalation on top.
    """
    id: str                       # stable slug, also the mistake-tracker key
    label: str                    # human name: "Missing semicolon"
    languages: tuple[str, ...]    # ("c", "cpp") — "*" means language-agnostic
    pattern: str                  # regex tested against the raw error text
    category: Category
    level: Level
    confidence: float             # 0.0–1.0 how sure the KB is for this pattern
    reply_pool: tuple[str, ...] = field(default_factory=tuple)
    explanation: str = ""         # one-line "what this actually means"


@dataclass
class Classification:
    """Result of running the classifier over a raw error string."""
    matched: bool
    raw: str
    entry_id: str | None = None
    label: str | None = None
    language: str | None = None
    category: Category | None = None
    level: Level | None = None
    confidence: float = 0.0
    explanation: str = ""

    @property
    def emoji(self) -> str:
        if self.level is None:
            return "❔"
        return LEVEL_EMOJI.get(self.level, "❔")

    @property
    def needs_llm(self) -> bool:
        """Unmatched errors fall through to the LLM. The whole point of the
        KB is to answer instantly/free for the common cases and only pay for
        Claude/Groq on the genuinely novel ones."""
        return not self.matched


@dataclass
class EngineResponse:
    """What the engine hands back to the caller (brain / proactive loop)."""
    classification: Classification
    spoken_text: str              # the line Donna actually says
    repeat_count: int = 0         # times this error id happened *today*
    total_count: int = 0          # all-time count for this error id
    needs_llm: bool = False       # caller should ask the LLM to elaborate
    serious: bool = False         # True for CONCEPTUAL/DANGEROUS — no jokes
