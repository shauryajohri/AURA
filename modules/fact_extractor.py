"""AURA fact extraction — turn passing remarks into durable memory.

The visible failure on 2026-07-07 was AURA being *told* "its name was AURA"
and, a turn later, asking "can you remind me what it was?". The conversation
window alone can't fix that: once the line scrolls out, it's gone. Durable
facts are the fix — small, stable statements the user makes about themselves
or their work, saved once and injected into every future prompt.

Two capture paths, both best-effort and both writing to store.user_facts:

  * capture_heuristic(text) — instant, deterministic regex over the user's
    message. Cheap enough to run on every turn. Catches the obvious "my name
    is X", "the project is called X", "I'm learning X" statements — only
    when they're plain statements, never inside a question, a hypothetical,
    a quote, a joke or a line of code.

  * capture_with_llm_async(...) — a throttled background pass that asks the
    light model to pull durable facts from the recent conversation. Runs in a
    daemon thread so it never adds latency to the reply, and only every few
    turns so it barely touches the rate limit.
"""

import re
import threading
import time

from memory import store

# ── Is this a plain statement by the user? ───────────────────────────────────
# The patterns only mean something in a plain first-person statement. The
# same words inside a question ("can you call me later?"), a hypothetical
# ("what if I'm learning rust"), a quote or reported speech ("my friend said
# 'my name is Bond'"), sarcasm ("oh sure, call me Einstein") or a pasted line
# of code say nothing true about the user, so those are dropped before any
# pattern runs. A negated clause ("my name is not important", "I'm not a
# doctor") is a rejection, never a fact.
_CODE_RE = re.compile(r"`|[{}]|\w\(|=|(?:^|\s)#\s|\b(?:def|class)\s+\w+\s*[(:]", re.M)
_HYPOTHETICAL_RE = re.compile(
    r"\b(?:if|imagine|imagining|suppose|supposing|pretend|pretending|hypothetically|"
    r"assume|assuming|let'?s say|in theory|unless|whether|wish)\b", re.I)
_QUOTED_RE = re.compile(
    r"[\"\u201c\u201d\u00ab\u00bb]|(?:^|[\s(\[:])'(?=\w)"
    r"|(?<!\bi )\b(?:said|says|saying|say|told|tells|asked|wrote|writes|quote|quoting|according to)\b",
    re.I)
_SARCASM_RE = re.compile(
    r"\b(?:oh sure|yeah right|yeah sure|sure sure|as if|jk|j/k|just kidding|kidding|"
    r"lol|lmao|rofl|haha\w*|hehe\w*)\b|(?:^|\s)/s\b|[\U0001F644\U0001F60F\U0001F602\U0001F923]",
    re.I)
_QUESTION_RE = re.compile(
    r"(?:what|whats|who|whose|whom|where|when|why|how|which|can|could|would|will|"
    r"should|shall|may|might|must|do|does|did|is|are|am|was|were|have|has|had)\b", re.I)
_NEGATION_RE = re.compile(
    r"\b(?:not|no|never|nobody|nothing|none|neither|nor|cannot|dont|doesnt|didnt|isnt|"
    r"arent|wasnt|werent|cant|wont|wouldnt|shouldnt|havent|hasnt|aint)\b|n't\b", re.I)
_LEAD_RE = re.compile(
    r"^(?:(?:hi|hey|hello|yo|ok|okay|so|well|also|and|oh|btw|by the way|actually|"
    r"anyway|fyi|um+|uh+|yeah|yes|yep|basically|honestly)\b[\s,]*)+", re.I)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_CLAUSE_SPLIT = re.compile(
    r"[,;:]|\s[-\u2013\u2014]+\s|\b(?:and|but|because|though|although|so|while|whereas)\b", re.I)


def _statements(text: str) -> list[tuple[str, bool]]:
    """(clause, alone) for each clause of `text` that reads as the user plainly
    stating something, leading filler ("hey", "btw") stripped. `alone` is True
    when the clause is its whole sentence."""
    text = (text or "").replace("\u2019", "'").replace("\u2018", "'")
    if not text.strip() or _CODE_RE.search(text):
        return []
    out = []
    for sentence in _SENTENCE_SPLIT.split(text.strip()):
        if (_HYPOTHETICAL_RE.search(sentence) or _QUOTED_RE.search(sentence)
                or _SARCASM_RE.search(sentence)):
            continue
        parts = [p for p in _CLAUSE_SPLIT.split(sentence) if p.strip()]
        if sentence.rstrip().endswith("?"):
            parts = parts[:-1]          # the clause the '?' closes is a question
        clauses = [c for c in (_LEAD_RE.sub("", p).strip(" .!") for p in parts) if c]
        for clause in clauses:
            if _NEGATION_RE.search(clause) or _QUESTION_RE.match(clause):
                continue
            out.append((clause, len(clauses) == 1))
    return out


def statement_clauses(text: str) -> list[str]:
    """The clauses of `text` a fact pattern may match at the start of. Shared
    with core/thinking.py's passive extractor so both apply the same gate."""
    return [c for c, _ in _statements(text)]


# ── Heuristic patterns ───────────────────────────────────────────────────────
# Each entry: (compiled regex, category, value check). The regex is matched at
# the start of a clause; group 1 is the captured value. Kept deliberately
# tight — a false "fact" is worse than a missed one because it gets injected
# into every prompt.
_STOP_VALUES = {
    "tired", "back", "here", "done", "good", "fine", "okay", "ok", "busy",
    "sorry", "sure", "ready", "trying", "working", "coding", "thinking",
    "not", "just", "still", "so", "also", "gonna", "going",
    "the", "a", "an", "my", "it", "this", "that", "for", "in", "right", "now",
    "today", "tomorrow", "tonight", "later", "worst", "honestly", "lol",
}

# Words that open a phrase but never a name: "call me later", "call me an
# idiot", "its name is unknown".
_NOT_NAMES = _STOP_VALUES | {
    "your", "his", "her", "our", "their", "its", "these", "those", "me", "you",
    "him", "them", "us", "i", "we", "he", "she", "they", "no", "never", "ever",
    "only", "already", "really", "very", "too", "maybe", "perhaps", "probably",
    "soon", "then", "yesterday", "again", "sometime", "anytime", "whenever",
    "when", "if", "once", "before", "after", "at", "on", "by", "from", "to",
    "with", "without", "about", "of", "as", "or", "and", "but", "out", "up",
    "over", "unknown", "important", "secret", "whatever", "something",
    "anything", "nothing", "everything", "someone", "anyone", "nobody",
    "crazy", "lazy", "old", "old-fashioned", "stupid", "dumb", "weird", "names",
    "please", "there", "what", "who", "why", "how", "where", "which", "is",
    "was", "be", "btw", "haha", "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday", "weekend",
}

# What "I'm building / working on X" has to mention to be a project rather
# than dinner, a sandwich or "the bug you mentioned".
_PROJECT_NOUNS = {
    "app", "application", "game", "bot", "chatbot", "website", "site", "engine",
    "tool", "library", "framework", "extension", "plugin", "api", "compiler",
    "interpreter", "startup", "project", "assistant", "platform", "cli",
    "script", "dashboard", "service", "server", "model", "os", "kernel",
    "emulator", "portfolio", "blog", "repo", "agent", "editor", "clone",
    "backend", "frontend", "database", "pipeline", "package", "sdk", "browser",
}

_PATTERNS = [
    # Project / thing names. "It" points outside the message, so these only
    # count when the naming is the whole sentence ("its name was AURA").
    (re.compile(r"it'?s?\s+name\s+(?:is|was)\s+([A-Za-z0-9_\- ]{2,40})", re.I), "project", "it"),
    (re.compile(r"(?:it'?s|its)\s+called\s+([A-Za-z0-9_\- ]{2,40})", re.I), "project", "it"),
    (re.compile(r"(?:the\s+|my\s+|our\s+)?project\s+(?:is\s+)?(?:called|named)\s+([A-Za-z0-9_\- ]{2,40})", re.I), "project", "name"),
    (re.compile(r"i(?:'?m|\s+am)\s+(?:working on|building|making)\s+(?:a\s+|an\s+|my\s+)?([A-Za-z0-9_\- ]{2,40})", re.I), "project", "thing"),
    (re.compile(r"my\s+project\s+is\s+(?:called\s+)?([A-Za-z0-9_\- ]{2,40})", re.I), "project", "thing"),
    # Identity. "Call me" is far more often "call me later / back / crazy",
    # so there the name must be written like one.
    (re.compile(r"my\s+name\s+is\s+([A-Za-z0-9_\- ]{2,30})", re.I), "identity", "name"),
    (re.compile(r"(?:(?:you\s+can|just|please|(?:my\s+)?friends|everyone|people)\s+)?calls?\s+me\s+([A-Za-z0-9_\- ]{2,30})", re.I), "identity", "Name"),
    (re.compile(r"i'?m\s+a\s+([A-Za-z ]{3,40}?\b(?:developer|engineer|student|dev|designer))", re.I), "identity", None),
    # Learning / goals
    (re.compile(r"i(?:'?m|\s+am)\s+(?:currently\s+)?(?:learning|studying)\s+([A-Za-z0-9_\-+ ]{2,40})", re.I), "learning", None),
    (re.compile(r"(?:i'?m\s+)?preparing\s+for\s+([A-Za-z0-9_\- ]{2,40})", re.I), "goal", None),
    # Preferences
    (re.compile(r"i\s+(?:prefer|like|want)\s+([A-Za-z0-9_\- ]{3,40}\b(?:replies|responses|answers))", re.I), "preference", None),
]


def _name_value(value: str, capital: bool = False) -> str:
    """The name `value` opens with (up to three name-like words), or ''."""
    words = []
    for w in value.split()[:3]:
        if (w.lower() in _NOT_NAMES or not w[0].isalpha()
                or (capital and not w[0].isupper())):
            break
        words.append(w)
    return " ".join(words)


def _thing_value(value: str) -> str:
    """`value` if it reads as a project: names something (a capitalised
    word) or says what kind of thing it is (app, game, bot...). Else ''."""
    for w in value.split():
        if w.lower() in _PROJECT_NOUNS or (w[0].isupper() and w.lower() not in _NOT_NAMES):
            return value
    return ""


def _clean_value(value: str) -> str:
    v = value.strip().strip(".,!?;:'\"").strip()
    # Drop trailing filler clauses ("AURA and it's a mess" → "AURA")
    v = re.split(r"\b(?:and|but|because|so|which|that|when)\b", v, maxsplit=1)[0].strip()
    return v


def _is_meaningful(value: str) -> bool:
    if not value or len(value) < 2:
        return False
    low = value.lower()
    if low in _STOP_VALUES:
        return False
    # Reject values that are only stopword-ish filler.
    words = [w for w in re.split(r"\s+", low) if w]
    return any(w not in _STOP_VALUES for w in words)


def _phrase_for(category: str, value: str) -> str:
    return {
        "project": f"their project is called {value}",
        "identity": f"they are {value}" if " " in value else f"their name is {value}",
        "learning": f"they are learning {value}",
        "goal": f"they are preparing for {value}",
        "preference": f"they prefer {value}",
    }.get(category, f"{category}: {value}")


def capture_heuristic(text: str) -> list[str]:
    """Extract and persist obvious durable facts from one user message.
    Returns the list of fact strings saved (for logging/tests)."""
    if not text:
        return []
    saved = []
    for clause, alone in _statements(text):
        for pattern, category, check in _PATTERNS:
            m = pattern.match(clause)
            if not m or (check == "it" and not alone):
                continue
            value = _clean_value(m.group(1))
            if check in ("it", "name", "Name"):
                value = _name_value(value, capital=check == "Name")
            elif check == "thing":
                value = _thing_value(value)
            if not _is_meaningful(value):
                continue
            fact = _phrase_for(category, value)
            if fact in saved:
                continue
            try:
                store.save_user_fact(fact, category)
                saved.append(fact)
            except Exception:
                pass
    if saved:
        print(f"[AURA Facts] captured: {saved}")
    return saved


# ── Throttled background LLM extraction ──────────────────────────────────────
_last_llm_run = 0.0
_turn_counter = 0
_LLM_EVERY_N_TURNS = 4
_LLM_MIN_INTERVAL_S = 90


def _llm_extract(recent_convo: str):
    try:
        from core.ai_router import call_groq_raw, GROQ_MODEL_LIGHT
    except Exception:
        return
    system = (
        "You extract durable facts about the user from a conversation — things "
        "worth remembering next week: their name, projects and project names, "
        "what they're learning, goals, strong preferences. Ignore momentary "
        "state (mood, what they're doing right now). Reply with 0-3 short facts, "
        "one per line, each phrased like 'their project is called X'. If nothing "
        "durable, reply with exactly NONE."
    )
    try:
        out = call_groq_raw(
            f"Conversation:\n{recent_convo}\n\nDurable facts:",
            system=system, max_tokens=120, temperature=0.2,
            model=GROQ_MODEL_LIGHT,
        )
    except Exception:
        return
    if not out or out.strip().upper().startswith("NONE"):
        return
    if out in ("RATE_LIMIT", "CONNECTION_ERROR"):
        return
    for line in out.splitlines():
        fact = line.strip().lstrip("-•* ").strip()
        if 4 <= len(fact) <= 120:
            try:
                store.save_user_fact(fact, "llm")
            except Exception:
                pass


def maybe_capture_with_llm():
    """Every few turns, kick a background thread that mines recent
    conversation for durable facts. Non-blocking and rate-limit friendly."""
    global _turn_counter, _last_llm_run
    _turn_counter += 1
    now = time.time()
    if _turn_counter % _LLM_EVERY_N_TURNS != 0:
        return
    if now - _last_llm_run < _LLM_MIN_INTERVAL_S:
        return
    _last_llm_run = now

    try:
        rows = store.get_recent_conversations(10)
    except Exception:
        return
    convo = "\n".join(
        f"{'User' if r == 'user' else 'AURA'}: {(m or '').strip()[:300]}"
        for r, m, _ in rows if (m or "").strip()
    )
    if not convo:
        return
    threading.Thread(target=_llm_extract, args=(convo,), daemon=True).start()


def capture(text: str):
    """Single entry point called on each real user message."""
    capture_heuristic(text)
    maybe_capture_with_llm()
