# modules/error_intelligence/classifier.py
"""
Classifier + severity resolution.

Takes raw compiler / terminal / traceback text and turns it into a
Classification. This layer is pure and side-effect-free: no tracking, no
persistence, no reply text. That keeps it trivially unit-testable and lets the
engine decide what to *do* with a classification separately from *what it is*.

Language can be passed explicitly (best) or inferred from the text/file
extension when the caller doesn't know it.
"""

from __future__ import annotations

import re

from . import knowledge_base as kb
from .models import Classification

# Cheap language inference from telltale tokens in the error text. Used only
# when the caller doesn't tell us the language. Ordered so more distinctive
# signals win.
_LANG_HINTS: list[tuple[str, "re.Pattern[str]"]] = [
    ("python", re.compile(r"Traceback \(most recent call last\)|\.py[\"']|File \".*\.py\"|SyntaxError:", re.IGNORECASE)),
    ("typescript", re.compile(r"\.tsx?[\"'):]|is not assignable to type|TS\d{3,}", re.IGNORECASE)),
    ("javascript", re.compile(r"\.jsx?[\"'):]|ReferenceError:|at Object\.<anonymous>|node:internal", re.IGNORECASE)),
    ("cpp", re.compile(r"\.cpp|\.hpp|template argument|std::|no matching function|::~?\w+\(", re.IGNORECASE)),
    ("c", re.compile(r"\.c[\":]|implicit declaration|gcc|undefined reference to `", re.IGNORECASE)),
    ("java", re.compile(r"\.java|Exception in thread \"main\"|at [\w.]+\([\w.]+\.java", re.IGNORECASE)),
]


def infer_language(raw_error: str) -> str | None:
    """Best-effort language guess from the error text. Returns None if nothing
    is distinctive enough — the KB then falls back to language-agnostic and
    '*' entries, which is the safe behaviour."""
    if not raw_error:
        return None
    for lang, pattern in _LANG_HINTS:
        if pattern.search(raw_error):
            return lang
    return None


def classify(raw_error: str, language: str | None = None) -> Classification:
    """Classify one error blob.

    `language`: pass the editor's known language when you have it (from the
    active file's extension, say). If omitted, we infer it. Inference only
    narrows which KB entries are eligible — a wrong guess degrades gracefully
    to the '*' entries rather than throwing.
    """
    raw = (raw_error or "").strip()
    if not raw:
        return Classification(matched=False, raw=raw, language=language)

    lang = language or infer_language(raw)

    entry = kb.match(raw, lang)
    if entry is None:
        # Nothing in the KB matched → the engine will route this to the LLM.
        return Classification(matched=False, raw=raw, language=lang)

    return Classification(
        matched=True,
        raw=raw,
        entry_id=entry.id,
        label=entry.label,
        language=lang,
        category=entry.category,
        level=entry.level,
        confidence=entry.confidence,
        explanation=entry.explanation,
    )
