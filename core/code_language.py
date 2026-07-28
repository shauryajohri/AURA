# core/code_language.py
"""
Which language is he actually writing in?

AURA had no idea. On a LeetCode page she answered a "write this" request in
Python, and he had to follow up with "in c++" to get the version he wanted.
The answer was on screen the whole time — LeetCode puts the language in a
selector right above the editor, and the code itself is unmistakable.

Three sources, strongest first:

  1. filename / window title   "main.cpp - Visual Studio Code"   → decisive
  2. an explicit selector      "C++", "Python3", "Java" chips     → strong
  3. syntax markers            #include, std::, def, fn, func     → good

Everything is scored rather than short-circuited, because a browser tab can
show several at once (a Python solution in the editor, a C++ answer in the
comments) and the strongest evidence should win rather than the first seen.

Used by two callers that both already needed it:
  • the CODING path in brain.py — so "write this" answers in the right language
  • error_intelligence.classify(raw, language=…) — its language parameter has
    existed since it was built and was never once supplied
"""

from __future__ import annotations

import re

# Canonical id → (display name, file extensions)
LANGUAGES: dict[str, dict] = {
    "cpp":        {"label": "C++",        "ext": (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".h++")},
    "c":          {"label": "C",          "ext": (".c", ".h")},
    "python":     {"label": "Python",     "ext": (".py", ".pyi", ".ipynb")},
    "java":       {"label": "Java",       "ext": (".java",)},
    "javascript": {"label": "JavaScript", "ext": (".js", ".jsx", ".mjs", ".cjs")},
    "typescript": {"label": "TypeScript", "ext": (".ts", ".tsx")},
    "csharp":     {"label": "C#",         "ext": (".cs",)},
    "go":         {"label": "Go",         "ext": (".go",)},
    "rust":       {"label": "Rust",       "ext": (".rs",)},
    "ruby":       {"label": "Ruby",       "ext": (".rb",)},
    "kotlin":     {"label": "Kotlin",     "ext": (".kt", ".kts")},
    "swift":      {"label": "Swift",      "ext": (".swift",)},
    "php":        {"label": "PHP",        "ext": (".php",)},
    "sql":        {"label": "SQL",        "ext": (".sql",)},
}

# How an editor or judge labels the language in its own UI. Matched on word
# boundaries against the window title and visible text.
_SELECTOR_PATTERNS: dict[str, tuple[str, ...]] = {
    "cpp":        (r"c\+\+\s*(?:1[47]|20|23)?", r"\bcpp\b", r"\bg\+\+\b", r"\bclang\+\+\b"),
    "c":          (r"\bc\s*(?:99|11|17)\b", r"\bgcc\b"),
    "python":     (r"\bpython\s*3?\b", r"\bpy3\b", r"\bcpython\b", r"\bpypy3?\b"),
    "java":       (r"\bjava\b(?!script)",),
    "javascript": (r"\bjavascript\b", r"\bnode\.?js\b", r"\bjs\b"),
    "typescript": (r"\btypescript\b", r"\bts\b"),
    "csharp":     (r"\bc#\b", r"\bcsharp\b", r"\bdotnet\b"),
    "go":         (r"\bgolang\b", r"\bgo\b"),
    "rust":       (r"\brust\b", r"\bcargo\b"),
    "ruby":       (r"\bruby\b",),
    "kotlin":     (r"\bkotlin\b",),
    "swift":      (r"\bswift\b",),
    "php":        (r"\bphp\b",),
    "sql":        (r"\b(?:mysql|postgres|sqlite|t-sql|pl/sql)\b",),
}

# Syntax that only really appears in one language. Weighted: the first entry
# in each tuple is the strongest tell.
_SYNTAX: dict[str, tuple[tuple[str, int], ...]] = {
    "cpp": (
        ("#include <", 5), ("std::", 5), ("using namespace std", 5),
        ("vector<", 4), ("cout <<", 4), ("cin >>", 4), ("nullptr", 3),
        ("->second", 3), ("->first", 3), ("unordered_map", 4),
        ("template<", 3), ("public:", 3), ("int main(", 2),
    ),
    "c": (
        ("#include <stdio.h>", 5), ("printf(", 3), ("malloc(", 3),
        ("scanf(", 3), ("struct ", 1),
    ),
    "python": (
        ("def ", 4), ("elif ", 5), ("self.", 4), ("__init__", 5),
        ("print(", 2), ("import ", 2), ("from ", 1), ("None", 3),
        ("True", 2), ("False", 2), ("range(", 3), ("len(", 2),
        (":\n    ", 2), ("lambda ", 3),
    ),
    "java": (
        ("public class ", 5), ("System.out.print", 5), ("public static void main", 5),
        ("ArrayList<", 4), ("String[] args", 5), ("private final", 3),
    ),
    "javascript": (
        ("console.log(", 4), ("=>", 2), ("const ", 2), ("let ", 2),
        ("function ", 2), ("require(", 3), ("document.", 3), ("null", 1),
    ),
    "typescript": (
        (": string", 4), (": number", 4), ("interface ", 4), ("<T>", 3),
        ("as const", 3), ("export default", 2), ("useState<", 4),
    ),
    "csharp": (("Console.WriteLine", 5), ("namespace ", 3), ("public void ", 2)),
    "go": (("func main()", 5), ("package main", 5), (":=", 4), ("fmt.Print", 5)),
    "rust": (("fn main()", 5), ("let mut ", 5), ("println!", 5), ("impl ", 3), ("&str", 4)),
    "ruby": (("puts ", 4), ("end\n", 2), ("def ", 1), ("attr_accessor", 5)),
    "kotlin": (("fun main(", 5), ("val ", 3), ("println(", 2)),
    "swift": (("func ", 2), ("var ", 1), ("let ", 1), ("print(", 1), ("guard ", 4)),
    "php": (("<?php", 5), ("echo ", 3), ("$this->", 4)),
    "sql": (("SELECT ", 4), ("FROM ", 3), ("WHERE ", 3), ("JOIN ", 3), ("GROUP BY", 4)),
}

_EXT_RE = re.compile(r"[\w\-/\\.]+\.([A-Za-z0-9+#]{1,6})\b")


def _from_filename(text: str) -> dict[str, int]:
    """Strongest signal — an actual filename on screen or in the title bar."""
    scores: dict[str, int] = {}
    for m in _EXT_RE.finditer(text):
        ext = "." + m.group(1).lower()
        for lang, meta in LANGUAGES.items():
            if ext in meta["ext"]:
                scores[lang] = scores.get(lang, 0) + 10
    return scores


def _from_selector(text: str) -> dict[str, int]:
    scores: dict[str, int] = {}
    low = text.lower()
    for lang, pats in _SELECTOR_PATTERNS.items():
        for p in pats:
            if re.search(p, low):
                # Two-letter selectors ("ts", "js", "go") are noisy in prose,
                # so they're worth less than a spelled-out name.
                scores[lang] = scores.get(lang, 0) + (3 if len(p) < 8 else 6)
                break
    return scores


def _from_syntax(text: str) -> dict[str, int]:
    scores: dict[str, int] = {}
    for lang, markers in _SYNTAX.items():
        for marker, weight in markers:
            if marker in text:
                scores[lang] = scores.get(lang, 0) + weight
    return scores


def detect_language(ctx: dict | None = None, text: str = "") -> str | None:
    """Best guess at the language on screen, or None when it isn't clear.

    Returning None matters: a wrong guess is worse than no guess, because the
    caller will confidently answer in the wrong language.
    """
    blob = text or ""
    if ctx:
        blob = " ".join(str(ctx.get(k) or "") for k in
                        ("app", "title", "window_title", "visible_text")) + " " + blob
    blob = blob[:8000]
    if not blob.strip():
        return None

    scores: dict[str, int] = {}
    for source in (_from_filename(blob), _from_selector(blob), _from_syntax(blob)):
        for lang, s in source.items():
            scores[lang] = scores.get(lang, 0) + s
    if not scores:
        return None

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best, best_score = ranked[0]
    if best_score < 4:
        return None                     # too weak to act on
    # A near-tie means the screen genuinely shows two languages; say nothing
    # rather than pick wrong.
    if len(ranked) > 1 and ranked[1][1] >= best_score:
        return None
    return best


def language_label(lang: str | None) -> str:
    if not lang:
        return ""
    return LANGUAGES.get(lang, {}).get("label", lang)


def detect_label(ctx: dict | None = None, text: str = "") -> str:
    """Display name ('C++'), or '' when undetermined."""
    return language_label(detect_language(ctx, text))
