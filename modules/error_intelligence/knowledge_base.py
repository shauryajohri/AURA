# modules/error_intelligence/knowledge_base.py
"""
The Error Knowledge Base — the heart of V3's "don't use an LLM first" idea.

Each entry is a regex tested against raw compiler/runtime error text. The
FIRST entry (in list order) whose pattern matches wins, so entries are ordered
most-specific → most-generic within each language, and dangerous/critical
shell operations sit at the very top (we never want a `rm -rf` misread as a
mild syntax thing).

Adding a new error type = append one KBEntry. No engine changes needed.
"""

from __future__ import annotations

import re
from functools import lru_cache

from .models import Category, KBEntry, Level

# ---------------------------------------------------------------------------
# Reply pools live inline with each entry so the "funny reply pool" for a given
# error is right next to its pattern. The reply layer (reply_pools.py) handles
# relationship *escalation*; these are the base one-liners it draws from.
# ---------------------------------------------------------------------------

_ENTRIES: list[KBEntry] = [
    # ===================================================================
    # LEVEL 4 — DANGEROUS  🔥  (checked first, order is safety-critical)
    # ===================================================================
    KBEntry(
        id="rm_rf",
        label="Recursive force delete",
        languages=("*",),
        pattern=r"\brm\s+-[a-z]*r[a-z]*f|\brm\s+-[a-z]*f[a-z]*r",
        category=Category.CRITICAL,
        level=Level.DANGEROUS,
        confidence=0.99,
        explanation="rm -rf permanently deletes a directory tree with no undo.",
        reply_pool=(
            "Hold on. Before we do that — are you absolutely sure? rm -rf doesn't ask twice.",
            "Wait. That's a recursive force delete. There's no undo button after this one.",
        ),
    ),
    KBEntry(
        id="git_reset_hard",
        label="git reset --hard",
        languages=("*",),
        pattern=r"git\s+reset\s+--hard|git\s+clean\s+-[a-z]*f",
        category=Category.CRITICAL,
        level=Level.DANGEROUS,
        confidence=0.97,
        explanation="git reset --hard / git clean -f discards uncommitted work permanently.",
        reply_pool=(
            "Hold on — reset --hard throws away everything uncommitted. Sure you don't want a stash first?",
            "That wipes your working changes for good. Want me to stash them before you pull the trigger?",
        ),
    ),
    KBEntry(
        id="drop_database",
        label="Destructive SQL",
        languages=("*", "sql"),
        pattern=r"\b(DROP\s+(TABLE|DATABASE)|TRUNCATE\s+TABLE|DELETE\s+FROM\s+\w+\s*;)",
        category=Category.CRITICAL,
        level=Level.DANGEROUS,
        confidence=0.9,
        explanation="Dropping/truncating a table or an unfiltered DELETE removes data irreversibly.",
        reply_pool=(
            "That's a destructive query. Are you absolutely sure? There's no ctrl-Z on a dropped table.",
        ),
    ),

    # ===================================================================
    # LEVEL 3 — CONCEPTUAL  🧠  (Donna stops joking)
    # ===================================================================
    KBEntry(
        id="segfault",
        label="Segmentation fault",
        languages=("c", "cpp"),
        pattern=r"segmentation fault|SIGSEGV|core dumped|access violation",
        category=Category.RUNTIME,
        level=Level.CONCEPTUAL,
        confidence=0.95,
        explanation="Your program touched memory it doesn't own — usually a bad pointer or overrun.",
        reply_pool=(
            "Okay. This one's actually interesting. A segfault means we touched memory we don't own. Let's figure it out together.",
            "Segfault. That's not a typo problem — it's a pointer or a buffer going somewhere it shouldn't. Want to walk through it?",
        ),
    ),
    KBEntry(
        id="infinite_recursion",
        label="Infinite recursion",
        languages=("*",),
        pattern=r"maximum recursion depth exceeded|RecursionError|stack overflow|StackOverflowError",
        category=Category.CONCEPT,
        level=Level.CONCEPTUAL,
        confidence=0.93,
        explanation="A function keeps calling itself without ever hitting a base case.",
        reply_pool=(
            "I don't think this is just a syntax issue — the recursion never hits a base case. Want me to walk through it?",
            "The algorithm itself is looping forever. There's no exit condition being reached. Let's trace it.",
        ),
    ),
    KBEntry(
        id="deadlock",
        label="Deadlock / lock contention",
        languages=("*",),
        pattern=r"\bdeadlock\b|resource deadlock avoided|lock order|would deadlock",
        category=Category.CONCEPT,
        level=Level.CONCEPTUAL,
        confidence=0.9,
        explanation="Two threads are each waiting on a lock the other holds — nobody proceeds.",
        reply_pool=(
            "This is a deadlock — two threads each holding what the other needs. This is a design thing, not a quick fix. Let's map the lock order.",
        ),
    ),
    KBEntry(
        id="race_condition",
        label="Data race",
        languages=("*",),
        pattern=r"data race|race condition|ThreadSanitizer|concurrent modification",
        category=Category.CONCEPT,
        level=Level.CONCEPTUAL,
        confidence=0.85,
        explanation="Two threads touch shared state without synchronisation; the result is timing-dependent.",
        reply_pool=(
            "That looks like a race condition — the bug depends on timing, so it won't reproduce reliably. Let's find the shared state.",
        ),
    ),
    KBEntry(
        id="cpp_template_error",
        label="C++ template error",
        languages=("cpp",),
        pattern=r"no matching function for call|template argument deduction|no type named|substitution failure|required from here",
        category=Category.CONCEPT,
        level=Level.CONCEPTUAL,
        confidence=0.8,
        explanation="A template couldn't be instantiated for the types you gave it.",
        reply_pool=(
            "Template errors are a wall of text on purpose. The real issue is a type that doesn't satisfy what the template expects. Want me to find the actual line?",
        ),
    ),
    KBEntry(
        id="memory_leak",
        label="Memory leak",
        languages=("c", "cpp"),
        pattern=r"definitely lost|LeakSanitizer|memory leak|AddressSanitizer.*leak",
        category=Category.CONCEPT,
        level=Level.CONCEPTUAL,
        confidence=0.85,
        explanation="Allocated memory was never freed — it accumulates over the program's life.",
        reply_pool=(
            "There's a leak — memory that's allocated and never freed. Let's find the allocation that has no matching free.",
        ),
    ),

    # ===================================================================
    # LEVEL 2 — MEDIUM  🙂  (helpful, not roasting)
    # ===================================================================
    KBEntry(
        id="py_type_error",
        label="Type mismatch",
        languages=("python",),
        pattern=r"TypeError:.*(argument|not callable|unsupported operand|takes \d+ positional)",
        category=Category.TYPING,
        level=Level.MEDIUM,
        confidence=0.85,
        explanation="A value's type doesn't fit what the operation or function expected.",
        reply_pool=(
            "Type mismatch — the function got a type it wasn't expecting. Want me to explain why?",
            "Looks like the arguments don't line up with what the function wants. Want the details?",
        ),
    ),
    KBEntry(
        id="py_key_index_error",
        label="Missing key / index out of range",
        languages=("python",),
        pattern=r"(KeyError|IndexError):",
        category=Category.RUNTIME,
        level=Level.MEDIUM,
        confidence=0.8,
        explanation="You asked for a key or index that isn't there.",
        reply_pool=(
            "You reached for a key/index that doesn't exist. Off-by-one, or the data just isn't shaped how you thought?",
        ),
    ),
    KBEntry(
        id="py_attribute_error",
        label="Attribute error",
        languages=("python",),
        pattern=r"AttributeError:.*has no attribute",
        category=Category.TYPING,
        level=Level.MEDIUM,
        confidence=0.8,
        explanation="You called something on an object that doesn't have it — often a None or wrong type.",
        reply_pool=(
            "That object doesn't have the attribute you asked for. Is it None, or the wrong type entirely?",
        ),
    ),
    KBEntry(
        id="null_pointer",
        label="Null / None dereference",
        languages=("*",),
        pattern=r"NullPointerException|dereferenc\w* null|null pointer|Cannot read propert(y|ies) of (null|undefined)|nil pointer dereference",
        category=Category.RUNTIME,
        level=Level.MEDIUM,
        confidence=0.82,
        explanation="You used something that turned out to be null/None/undefined.",
        reply_pool=(
            "Something you expected to have a value is null. Want me to trace where it should've been set?",
        ),
    ),
    KBEntry(
        id="cpp_linker_error",
        label="Linker / undefined reference",
        languages=("c", "cpp"),
        pattern=r"undefined reference to|unresolved external symbol|ld returned|collect2: error",
        category=Category.TYPING,
        level=Level.MEDIUM,
        confidence=0.8,
        explanation="The code compiled but a symbol has no definition to link against.",
        reply_pool=(
            "It compiled but won't link — a symbol was declared but never defined, or you forgot to link a library.",
        ),
    ),
    KBEntry(
        id="js_type_error",
        label="JS type error",
        languages=("javascript", "typescript"),
        pattern=r"TypeError:.*(is not a function|is not iterable|Assignment to constant)",
        category=Category.TYPING,
        level=Level.MEDIUM,
        confidence=0.8,
        explanation="A value isn't the type the operation needs (e.g. calling a non-function).",
        reply_pool=(
            "You're using a value as something it isn't — like calling something that's not a function. Want me to check the type?",
        ),
    ),
    KBEntry(
        id="ts_type_mismatch",
        label="TS type not assignable",
        languages=("typescript",),
        pattern=r"is not assignable to type|Type '.*' is not assignable|Property '.*' does not exist on type",
        category=Category.TYPING,
        level=Level.MEDIUM,
        confidence=0.8,
        explanation="TypeScript's checker found a type that doesn't fit where you put it.",
        reply_pool=(
            "TypeScript's blocking this — the type you gave doesn't match what's declared. Want me to reconcile them?",
        ),
    ),

    # ===================================================================
    # LEVEL 1 — SILLY  😂  (Donna, not Claude)
    # ===================================================================
    KBEntry(
        id="missing_semicolon",
        label="Missing semicolon",
        languages=("c", "cpp", "java", "javascript", "typescript"),
        pattern=r"expected ['\"`]?;|missing ['\"`]?;|expected ';' before",
        category=Category.SYNTAX,
        level=Level.SILLY,
        confidence=0.99,
        explanation="A statement is missing its terminating semicolon.",
        reply_pool=(
            "Seriously? One semicolon. That's all that's stopping this masterpiece.",
            "A semicolon. The whole build, held hostage by one semicolon.",
        ),
    ),
    KBEntry(
        id="missing_paren",
        label="Missing parenthesis",
        languages=("*",),
        pattern=r"expected ['\"`]?\)|missing ['\"`]?\)|unbalanced paren|expected '\)'|was never closed",
        category=Category.SYNTAX,
        level=Level.SILLY,
        confidence=0.97,
        explanation="An opening parenthesis has no matching close.",
        reply_pool=(
            "You lost a parenthesis again. They're becoming an endangered species.",
            "Missing a closing paren. It opened, it never closed, the compiler noticed.",
        ),
    ),
    KBEntry(
        id="missing_brace",
        label="Missing brace",
        languages=("*",),
        pattern=r"expected ['\"`]?\}|missing ['\"`]?\}|expected '\}'|unexpected end of (input|file)",
        category=Category.SYNTAX,
        level=Level.SILLY,
        confidence=0.95,
        explanation="A block was opened with { and never closed.",
        reply_pool=(
            "A brace ran off without closing. Classic.",
            "You opened a block and never closed it. The compiler waited. It's still waiting.",
        ),
    ),
    KBEntry(
        id="py_indentation",
        label="Indentation error",
        languages=("python",),
        pattern=r"(IndentationError|TabError):|unexpected indent|expected an indented block",
        category=Category.SYNTAX,
        level=Level.SILLY,
        confidence=0.97,
        explanation="Python's block structure is whitespace — the indentation doesn't line up.",
        reply_pool=(
            "Indentation. Python cares about whitespace more than most people care about anything.",
            "The indentation is off. Tabs and spaces had a fight and the parser lost.",
        ),
    ),
    KBEntry(
        id="py_syntax_error",
        label="Python syntax error",
        languages=("python",),
        pattern=r"SyntaxError:|invalid syntax|EOL while scanning|unexpected EOF",
        category=Category.SYNTAX,
        level=Level.SILLY,
        confidence=0.9,
        explanation="The parser hit something it can't read — often a stray character or missing colon.",
        reply_pool=(
            "Syntax error. Something small is in the wrong place. Missing colon, maybe?",
            "The parser choked. Usually it's a colon, a quote, or a bracket that wandered off.",
        ),
    ),
    KBEntry(
        id="py_name_error",
        label="Name not defined",
        languages=("python",),
        pattern=r"NameError:.*is not defined",
        category=Category.SYNTAX,
        level=Level.SILLY,
        confidence=0.92,
        explanation="You referenced a variable or name that was never defined in scope.",
        reply_pool=(
            "You referenced a variable that doesn't exist. Did it disappear overnight?",
            "That name isn't defined. Typo, or did you forget to actually create it?",
        ),
    ),
    KBEntry(
        id="py_import_error",
        label="Import error",
        languages=("python",),
        pattern=r"(ModuleNotFoundError|ImportError):",
        category=Category.SYNTAX,
        level=Level.SILLY,
        confidence=0.9,
        explanation="An import failed — the module isn't installed or the name is wrong.",
        reply_pool=(
            "Forgot an import, or it's not installed. Either way, Python can't find it.",
            "That module isn't where Python's looking. pip install, or a typo in the name?",
        ),
    ),
    KBEntry(
        id="js_reference_error",
        label="Reference error",
        languages=("javascript", "typescript"),
        pattern=r"ReferenceError:.*is not defined",
        category=Category.SYNTAX,
        level=Level.SILLY,
        confidence=0.9,
        explanation="You used a name that doesn't exist in scope.",
        reply_pool=(
            "You referenced something that doesn't exist. Typo, or wrong scope?",
            "That name isn't defined. JavaScript looked, JavaScript shrugged.",
        ),
    ),
    KBEntry(
        id="js_unexpected_token",
        label="Unexpected token",
        languages=("javascript", "typescript"),
        pattern=r"SyntaxError:.*(Unexpected token|Unexpected end of input)",
        category=Category.SYNTAX,
        level=Level.SILLY,
        confidence=0.88,
        explanation="The parser hit a character it wasn't expecting — a stray comma, bracket, or quote.",
        reply_pool=(
            "Unexpected token. Something small snuck in where it shouldn't be.",
        ),
    ),
    KBEntry(
        id="c_implicit_decl",
        label="Implicit declaration",
        languages=("c",),
        pattern=r"implicit declaration of function|undeclared \(first use",
        category=Category.SYNTAX,
        level=Level.SILLY,
        confidence=0.85,
        explanation="You called a function C hasn't seen declared — usually a missing #include.",
        reply_pool=(
            "Called a function C's never heard of. Missing an #include, probably.",
        ),
    ),
    KBEntry(
        id="typo_common",
        label="Likely typo",
        languages=("*",),
        pattern=r"\b(pritn|prnit|retrun|fucntion|lenght|flase|treu|improt|defien)\b",
        category=Category.SYNTAX,
        level=Level.SILLY,
        confidence=0.85,
        explanation="A common keyword/identifier looks misspelled.",
        reply_pool=(
            "That's a typo. Your fingers got ahead of your brain again.",
            "Spelling. One transposed letter and the whole thing falls over.",
        ),
    ),
]


@lru_cache(maxsize=1)
def _compiled() -> tuple[tuple[KBEntry, "re.Pattern[str]"], ...]:
    """Compile every pattern once. Cached so repeated engine calls are cheap."""
    out = []
    for entry in _ENTRIES:
        out.append((entry, re.compile(entry.pattern, re.IGNORECASE | re.MULTILINE)))
    return tuple(out)


def all_entries() -> list[KBEntry]:
    """Every KB entry, in match-priority order (dangerous first)."""
    return list(_ENTRIES)


def entry_by_id(entry_id: str) -> KBEntry | None:
    for entry in _ENTRIES:
        if entry.id == entry_id:
            return entry
    return None


def _language_ok(entry: KBEntry, language: str | None) -> bool:
    """A language-agnostic entry ('*') always applies. Otherwise the caller's
    language must be in the entry's list. If the caller gives no language, we
    allow every entry (better to classify than to miss)."""
    if "*" in entry.languages:
        return True
    if language is None:
        return True
    return language.lower() in entry.languages


def match(raw_error: str, language: str | None = None) -> KBEntry | None:
    """Return the first KB entry whose pattern matches the raw error text and
    whose language constraint is satisfied. None means 'ask the LLM'."""
    if not raw_error:
        return None
    for entry, pattern in _compiled():
        if not _language_ok(entry, language):
            continue
        if pattern.search(raw_error):
            return entry
    return None
