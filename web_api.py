"""
AURA on the web: the public, sandboxed face of AURA.

Why this exists
---------------
`server.py` is AURA's private bridge. Its routes read and write Shaurya's own
SQLite memory, run shell commands and touch the filesystem with no auth
(QA_REPORT.md, C1). None of that may ever face the internet.

This module is the public surface. It runs the same conversation pipeline the
desktop app runs, minus everything personal:

  ConversationDirector   one per visitor: slash commands, sticky workspace
                         modes, natural mode cues, vague-ask clarifiers
  intent classifier      INTENT_PROMPT on the light model + core.intent_rules
  natures                core.nature overlays, appended last like the app
  routing                core.model_router chain with sentinel fallback
  streaming              core.ai_router.call_groq_streaming + the reasoning
                         stream sanitizer
  persona layer          core.response_composer
  voice                  edge-tts with AURA's voice and tone settings

It never imports server.py, core.brain or memory.store: no personal memory, no
relationship state, no tools, screen, files, git or shell.

Budget
------
  * 50 model messages per visitor, counted per session AND per IP over a
    rolling 24h, so a new tab does not buy a new 50 (QA_REPORT.md, M13)
  * sessions are issued by the server; a chat without one is refused
  * per-IP rate limit, a global daily ceiling, capped input
  * instant replies (mode switches, /help, clarifiers) cost nothing

Surfaces (all under /web/api)
-----------------------------
  GET|POST /session   handshake: budget, natures, modes, model roster
  POST     /chat      SSE: state, route, fallback, model, chunk, done | error
  POST     /mode      switch workspace mode (free)
  POST     /reset     new conversation (the budget is not restored)
  POST     /tts       one reply in AURA's voice, audio/mpeg

Run it standalone for anything public:

    python web_api.py        # http://127.0.0.1:8770, serves website/ at /

Env
---
  AURA_WEB_MSG_LIMIT    model messages per visitor          (default 50)
  AURA_WEB_IP_DAILY     model messages per IP, rolling 24h  (default = limit)
  AURA_WEB_IP_PER_MIN   requests per IP per minute          (default 20)
  AURA_WEB_DAILY_CAP    model messages across all visitors  (default 3000)
  AURA_WEB_TTS_DAILY    voice clips per IP, rolling 24h     (default 200)
  AURA_WEB_TTL_MIN      idle session lifetime in minutes    (default 240)
  AURA_WEB_ORIGINS      allowed CORS origins, comma list    (standalone only)
  AURA_WEB_TRUST_PROXY  "1" reads the client IP from X-Forwarded-For
  AURA_WEB_VOICE        edge-tts voice id                   (default Ava)
  AURA_WEB_HOST / AURA_WEB_PORT   standalone bind      (127.0.0.1 / 8770)
  AURA_WEB_SITE         "0" to not serve the static site
  AURA_WEB_SITE_DIR     static site folder                  (default website/)
"""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import os
import re
import secrets
import sys
import threading
import time
from collections import OrderedDict, deque
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Body, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

router = APIRouter(prefix="/web/api", tags=["web"])

HERE = Path(__file__).resolve().parent
SITE_DIR = Path(os.getenv("AURA_WEB_SITE_DIR") or HERE / "website")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Budget knobs
# ---------------------------------------------------------------------------
MSG_LIMIT = _env_int("AURA_WEB_MSG_LIMIT", 50)
IP_DAILY = _env_int("AURA_WEB_IP_DAILY", MSG_LIMIT)
IP_PER_MIN = _env_int("AURA_WEB_IP_PER_MIN", 20)
DAILY_CAP = _env_int("AURA_WEB_DAILY_CAP", 3000)
TTS_DAILY = _env_int("AURA_WEB_TTS_DAILY", 200)
SESSION_TTL = _env_int("AURA_WEB_TTL_MIN", 240) * 60
TRUST_PROXY = os.getenv("AURA_WEB_TRUST_PROXY", "") == "1"
# en-US-AvaNeural, not the desktop's AvaMultilingualNeural. Run through speech
# recognition, the multilingual model garbled her own name ("Hi, I'm Aura" came
# back as "Imambara", "AURA runs on" as "horror runs on") while the
# English-only Ava said "hi I am aura" cleanly. Same Ava, one language.
VOICE = os.getenv("AURA_WEB_VOICE", "en-US-AvaNeural")

DAY = 86400
MAX_SESSIONS = 2000
MAX_TURNS = 12            # transcript window handed to the model
MAX_INPUT_CHARS = 1200
MAX_TTS_CHARS = 600
SENTINELS = ("RATE_LIMIT", "CONNECTION_ERROR")

# Same set core.brain passes as longform to the composer: whole answers, no trim.
LONGFORM_INTENTS = {"RESEARCH", "DISCUSSION", "PLAN", "EXPLAIN"}
# The classifier can name these, but they need the personal store or the OS.
DESKTOP_ONLY_INTENTS = {"SAVE", "REMINDER", "COMMAND", "RECALL"}
WORKSPACE_MODES = ("CODE", "RESEARCH", "DISCUSSION", "PLAN")
MODE_KEY = {"NORMAL": "chat", "PROMPT": "chat", "CODE": "code", "RESEARCH": "research",
            "DISCUSSION": "discussion", "PLAN": "plan"}

PROMPT_DESKTOP_ONLY = ("Prompt Maker lives in the desktop app. Here, just tell me "
                       "what you want and I'll write it.")
MSG_RATE_LIMIT = "My free model tier is catching its breath. Give it twenty seconds."
MSG_UNREACHABLE = ("Can't reach my brain right now. The code is on GitHub if you "
                   "want to run me yourself.")


# ---------------------------------------------------------------------------
# Sessions and budget (RAM only, deliberately not persisted)
# ---------------------------------------------------------------------------
class WebSession:
    __slots__ = ("id", "seen", "turns", "used", "nature", "director", "lock")

    def __init__(self, sid: str) -> None:
        self.id = sid
        self.seen = time.time()
        self.turns: list[tuple[str, str]] = []   # (role, text)
        self.used = 0
        self.nature = "auto"
        self.director = _new_director()
        self.lock = threading.Lock()             # director state: one decision at a time


def _new_director():
    from core.conversation_director import ConversationDirector
    return ConversationDirector()


_SESSIONS: dict[str, WebSession] = {}
_LOCK = threading.Lock()
_IP_MSGS: dict[str, deque[float]] = {}   # model messages, rolling 24h
_IP_HITS: dict[str, deque[float]] = {}   # any request, rolling minute
_IP_TTS: dict[str, deque[float]] = {}    # voice clips, rolling 24h
_GLOBAL = {"day": 0, "n": 0}


def _trim(dq: deque[float], window: float, now: float) -> int:
    while dq and now - dq[0] > window:
        dq.popleft()
    return len(dq)


def _client_ip(request: Request) -> str:
    if TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "?") or "?"


def _rate_limit(ip: str) -> None:
    now = time.time()
    with _LOCK:
        hits = _IP_HITS.setdefault(ip, deque())
        if _trim(hits, 60, now) >= IP_PER_MIN:
            raise HTTPException(429, "Too many requests. Give it a minute.")
        hits.append(now)
        if len(_IP_HITS) > 5000:
            for k in [k for k, v in _IP_HITS.items() if not v][:2500]:
                _IP_HITS.pop(k, None)


def _ip_used(ip: str) -> int:
    dq = _IP_MSGS.get(ip)
    return _trim(dq, DAY, time.time()) if dq else 0


def _remaining(s: WebSession, ip: str) -> int:
    return max(0, min(MSG_LIMIT - s.used, IP_DAILY - _ip_used(ip)))


def _reset_in(ip: str) -> int:
    """Seconds until this IP gets a message back (0 when it has budget)."""
    dq = _IP_MSGS.get(ip)
    if dq and _ip_used(ip) >= IP_DAILY:
        return max(0, int(DAY - (time.time() - dq[0])))
    return 0


def _public(s: WebSession, ip: str) -> dict[str, Any]:
    return {
        "session": s.id,
        "used": s.used,
        "remaining": _remaining(s, ip),
        "limit": MSG_LIMIT,
        "reset_in": _reset_in(ip),
        "mode": MODE_KEY.get(s.director.mode, "chat"),
        "nature": s.nature,
    }


def _sweep() -> None:
    now = time.time()
    for k in [k for k, s in _SESSIONS.items() if now - s.seen > SESSION_TTL]:
        _SESSIONS.pop(k, None)
    if len(_SESSIONS) > MAX_SESSIONS:
        for s in sorted(_SESSIONS.values(), key=lambda s: s.seen)[: len(_SESSIONS) - MAX_SESSIONS]:
            _SESSIONS.pop(s.id, None)


def _get_session(token: str | None) -> WebSession | None:
    with _LOCK:
        _sweep()
        s = _SESSIONS.get(token or "")
        if s:
            s.seen = time.time()
        return s


def _new_session() -> WebSession:
    s = WebSession(secrets.token_urlsafe(18))
    with _LOCK:
        _sweep()
        _SESSIONS[s.id] = s
    return s


def _require_session(token: str | None) -> WebSession:
    s = _get_session(token)
    if s is None:
        raise HTTPException(401, "session expired")
    return s


def _charge(s: WebSession, ip: str) -> str | None:
    """Take one message from the visitor's budget up front. None = allowed."""
    now = time.time()
    with _LOCK:
        if _remaining(s, ip) <= 0:
            return "limit"
        day = int(now // DAY)
        if _GLOBAL["day"] != day:
            _GLOBAL.update(day=day, n=0)
        if _GLOBAL["n"] >= DAILY_CAP:
            return "busy"
        _GLOBAL["n"] += 1
        s.used += 1
        _IP_MSGS.setdefault(ip, deque()).append(now)
    return None


def _refund(s: WebSession, ip: str) -> None:
    """A turn that produced nothing is not charged."""
    with _LOCK:
        s.used = max(0, s.used - 1)
        dq = _IP_MSGS.get(ip)
        if dq:
            dq.pop()
        _GLOBAL["n"] = max(0, _GLOBAL["n"] - 1)


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------
_WEB_RULES = """

YOU ARE RUNNING AS THE PUBLIC WEB DEMO OF AURA.
- The person typing is a visitor trying you on your project website, often a
  recruiter or an engineer. They are not Shaurya.
- Here you have NO screen, NO files, NO terminal, NO saved memory, NO
  reminders and NO internet access. If they ask for any of that, or for live
  information like weather, news or prices, say plainly that you cannot reach
  it from here, then help with what you can.
- You remember only this browser conversation.
- Never claim to have done something you cannot do here.
- Only state facts about AURA, this site or Shaurya that appear in the fact
  sheet below. If something is not there, say you do not know and point to the
  code. Never make up features, bugs, jobs, schools, teams, clients or results.
- When they ask about you, this site or Shaurya, include at least one concrete
  detail from the fact sheet instead of a bare one-line answer.
- Be the same AURA: sharp, dry, warm, useful. Do not sell. No marketing voice."""

# Kept apart from the rules: the leak gate treats a reply that recites the
# RULES as deliberation, but repeating these facts is a legitimate answer.
# Before this sheet existed the demo invented a "version-control sync layer",
# a "race condition" as its hardest bug, "npm start" as the setup, and models
# that pick "the best-matching response". Everything here is checked against
# the repo; the roster line is filled from core.model_router at startup.
_WEB_FACTS = """
FACT SHEET (true; the only facts to use about AURA, this site and Shaurya):
- AURA is Shaurya's open source (MIT) desktop AI companion. He built it
  himself, starting in 2026, as his main project and a tool he uses every day.
  Code: https://github.com/shauryajohri/AURA
- Stack: Python, FastAPI and SQLite on the backend; React 18, TypeScript,
  Vite, Electron and Three.js for the face; Groq and OpenRouter serve the
  models; edge-tts is the voice.
- Every message: a small model classifies the intent and a rule layer checks
  it; context is gathered; the message goes to a chain of free models for that
  job; a persona layer and a reasoning-leak guard clean the reply.
- Routing: each job has its own chain, tried one model at a time, in order. If
  a model is rate limited, errors, or leaks its reasoning, the next model in
  the chain answers. GPT-OSS 120B and 20B on Groq are the safety net at the end
  of every chain. Models never run in parallel and never vote on an answer.
{roster}
- Memory, on the desktop: SQLite holds conversations, durable facts about the
  user, notes, session recaps, tasks and quests. Recent turns come from that
  store, and a project memory block (what they are working on, how far along,
  the last event) rides along with every message.
- Desktop only: voice with a wake word, reading the screen when asked, quests
  checked against a screenshot, proactive nudges that mostly stay quiet, and
  AURA Domain: a development OS where talking about a project becomes features,
  tasks and decisions in a knowledge graph, with a code editor, terminal, git,
  and a code review permission ladder (read only, sandbox, merge review, write,
  push) that never escalates itself.
- Real engineering calls: (1) Groq retired two models in August 2026 and
  replies failed mid-conversation, so every intent got a fallback chain.
  (2) Reasoning models leaked their thinking into replies; it took five fixes in
  five days, and the fix that held is layered: a provider flag, a stream filter
  that cuts to where the real answer starts, and a final gate. (3) Rooms move a
  conversation only when the new room clearly wins, because a wrong move loses
  the thread.
- Running AURA locally: git clone the repo, pip install -r requirements.txt,
  then cd frontend and npm install, put GROQ_API_KEY (OPENROUTER_API_KEY is
  optional) in a .env file at the repo root, then double-click AURA.bat on
  Windows, or run python server.py and, in frontend, npm run dev. Needs
  Python 3.10+ and Node 18+.
- This website: a short scroll intro, then a live console with five natures
  (auto, chill, focus, savage, professional) and modes (chat, code, research,
  discussion, plan), a panel showing what happened on each message, a tour in
  which you fly around the page explaining each part, and the code on GitHub.
  The demo runs the real pipeline without personal memory, and she speaks her
  replies and the tour aloud here too. Each visitor gets 50 messages per 24
  hours. Nothing typed here is kept after the tab closes.
- What AURA can do in this demo: chat, write and explain code, research and
  plan from what she already knows, switch natures and modes, and speak her
  replies. What she cannot do here: see the visitor's screen, open files, run
  commands, set reminders, remember anything past this tab, or look things up
  online. Screen reading, memory, reminders and Domain are desktop features.
  Asked what she can do, she names only what works here and says the rest is
  on the desktop.
- About Shaurya: he designed and built everything above. If asked why someone
  should hire him, answer from this work only.
"""


def _job_chains() -> dict[str, list[str]]:
    """The live roster by job, as the page and the fact sheet show it."""
    from core import model_router
    groq = [name for name, _ in getattr(model_router, "GROQ_FALLBACKS", [])]
    jobs = getattr(model_router, "JOB_CHAINS", None) or {}
    out: dict[str, list[str]] = {}
    for job, label in (("Coding", "Code"), ("Research", "Research and plans"), ("Chat", "Chat")):
        models = [m for m in jobs.get(job, []) if m not in groq]
        if models:
            out[label] = models
    if groq:
        out["Safety net"] = groq
    return out


@functools.lru_cache(maxsize=1)
def _facts() -> str:
    roster = "\n".join(f"  {job}: {', '.join(models)}." for job, models in _job_chains().items())
    return _WEB_FACTS.replace("{roster}", "- Current models by job:\n" + roster if roster else "")


def _session_facts(s: "WebSession | None", ip: str) -> str:
    """What the model cannot know on its own: this visitor's budget and settings."""
    if s is None:
        return ""
    return (f"\nTHIS VISITOR RIGHT NOW: {_remaining(s, ip)} of {MSG_LIMIT} demo messages "
            f"left, this one already counted. Mode: {MODE_KEY.get(s.director.mode, 'chat')}. "
            f"Nature: {s.nature}.")
# core.brain.build_context_prompt adds this rule to the user turn. Here it rides
# in the system prompt instead: a reasoning model recited the user-turn version
# back as its answer ("If code would genuinely help, ask first...").
_NO_CODE_RULE = (
    "\n- Do NOT write code or code blocks unless the visitor explicitly asked "
    "for code. If code would genuinely help, offer it in one line first."
)


# Questions about AURA herself are small talk with a fact sheet behind them, but
# the classifier often calls "who built you?" SEARCH: the slow research chain,
# and SEARCH in the trace a recruiter reads. Only a SEARCH verdict is moved.
_SELF_QUESTION = re.compile(
    r"(?i)\bwho\s+(?:built|made|created|designed|coded|wrote|develops|developed)\s+(?:you|aura)\b"
    r"|\b(?:who|what)\s+are\s+you\b|\babout\s+yourself\b|\bintroduce\s+yourself\b"
    r"|\bwhat\s+(?:can|do)\s+you\s+do\W*$|\bhow\s+do\s+you\s+work\W*$"
    r"|^\W*(?:who|what)\s+is\s+(?:aura|shaurya)\W*$"
)


def _classify(text: str) -> tuple[str, str]:
    """(routing intent, what the classifier itself said)."""
    from core.ai_router import call_classifier
    from core.intent_rules import VALID_INTENTS, correct_intent
    from core.personality import INTENT_PROMPT

    if re.search(r"https?://", text):
        return "SEARCH", "SEARCH"
    raw = call_classifier(INTENT_PROMPT.format(query=text, app="AURA web demo", screen=""))
    said = re.sub(r"[^A-Z]", "", raw or "")
    intent = said if said in VALID_INTENTS else "CASUAL"
    intent = correct_intent(text, intent)
    if intent == "SEARCH" and _SELF_QUESTION.search(text):
        intent = "CASUAL"
    if intent in DESKTOP_ONLY_INTENTS:
        intent = "CASUAL"
    return intent, (said if said in VALID_INTENTS else "CASUAL")


def _build_system(intent: str, query: str, nature: str,
                  s: "WebSession | None" = None, ip: str = "") -> str:
    from core.identity import identity_context
    from core.nature import NATURES
    from core.personality import DONNA_SYSTEM_PROMPT, INTENT_PERSONALITY_ADJUSTMENTS

    # Nature overlay goes LAST, exactly like ai_router.route_streaming, so a
    # manual lock overrides every tone rule above it.
    return (DONNA_SYSTEM_PROMPT + INTENT_PERSONALITY_ADJUSTMENTS.get(intent, "")
            + identity_context(query) + _WEB_RULES + _facts() + _session_facts(s, ip)
            + ("" if intent == "CODING" else _NO_CODE_RULE)
            + NATURES[nature]["overlay"])


def _build_prompt(s: WebSession, body: str) -> str:
    lines = [f"{'User' if role == 'user' else 'AURA'}: {text}"
             for role, text in s.turns[-MAX_TURNS:]]
    if not lines:
        return body
    return "CONVERSATION SO FAR:\n" + "\n".join(lines) + f"\n\nUser: {body}"


# ---------------------------------------------------------------------------
# The leak gate
# ---------------------------------------------------------------------------
# core.ai_router.sanitize_text strips the deliberation it can name, but the
# free reasoning models on OpenRouter keep finding new ways to recite their
# instructions ("As AURA in professional nature...", "Not given. So we must be
# chill."). A visitor reading that monologue is the one failure this page
# cannot afford, so their replies are held back until the opening reads like
# an answer, and a reply that recites its rules is re-routed down the chain.
GATE_CHARS = 280

_HEAD_TELLS = re.compile(
    r"(?i)(?:\bnature\b(?!\s+of\b)|\bsentence [12]\b|\buser'?s? activity\b|\bno meta\b|"
    r"\bsystem prompt\b|\bnot given\b|^\W*as aura\b|"
    r"\bwe (?:must|need to|should|cannot|can'?t|have to)\b|"
    r"\b(?:the|my|these) instructions?\b|\bpersona\b|\bno (?:emoji|fluff|hype)\b|"
    r"\bdirect answer\b|"
    # the prompt's own scaffolding read back: the transcript it was handed
    # ("Conversation so far: 1. User: ...") or the fact sheet's headers
    r"\bconversation so far\b|^\W*(?:\d+[.)]\s*)?(?:user|aura)\s*:|"
    r"\bfact sheet\b|\bthis visitor right now\b)"
)
_WORD = re.compile(r"[a-z0-9']+")


def _ngrams(text: str, n: int = 5) -> set[tuple[str, ...]]:
    words = _WORD.findall(text.lower())
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


@functools.lru_cache(maxsize=64)
def _rule_ngrams(intent: str, nature: str) -> frozenset:
    """Every five-word run of the instructions a reply must never recite."""
    from core.identity import IDENTITY_CORE
    from core.nature import NATURES
    from core.personality import DONNA_SYSTEM_PROMPT, INTENT_PERSONALITY_ADJUSTMENTS
    rules = (DONNA_SYSTEM_PROMPT.replace(IDENTITY_CORE, "")
             + INTENT_PERSONALITY_ADJUSTMENTS.get(intent, "")
             + _WEB_RULES + _NO_CODE_RULE + NATURES.get(nature, NATURES["auto"])["overlay"])
    return frozenset(_ngrams(rules))


def _looks_leaked(text: str, intent: str, nature: str, partial: bool = False) -> bool:
    from core.ai_router import _is_meta_sentence, _is_strong_meta, _split_sentences

    sentences = [x for x in _split_sentences(_FENCE.sub(" ", text)) if re.search(r"[A-Za-z]", x)]
    if partial and sentences and not re.search(r"[.!?\n]\s*$", sentences[-1]):
        sentences = sentences[:-1]              # the sentence still being written
    rules = _rule_ngrams(intent, nature)
    # Reports, plans and explanations legitimately say "the user signs in" and
    # "we should", which the chat-lane markers read as deliberation. For them
    # only a recited rule or an opening tell counts.
    longform = intent in LONGFORM_INTENTS
    for i, sentence in enumerate(sentences):
        if rules & _ngrams(sentence) or (not longform and _is_strong_meta(sentence)):
            return True
        if i < 3 and (_HEAD_TELLS.search(sentence) or (not longform and _is_meta_sentence(sentence))):
            return True
    return False


def _too_thin(text: str) -> bool:
    """A reply that stopped before it said anything, like the bare "The" a
    reasoning model handed back after a minute of thinking."""
    if "```" in text:
        return False
    words = re.findall(r"[A-Za-z0-9']+", text)
    return len(words) < 3 and not re.search(r"[.!?]\s*$", text.strip())


# How long a model gets to prove itself before its chain moves on: its first
# token, then (for a held OpenRouter reply) enough text to clear the gate. One
# test question sat through 180 seconds of two reasoning models thinking.
FIRST_TOKEN_DEADLINE = 30.0
FIRST_TEXT_DEADLINE = 25.0

# A model that keeps leaking, stalling or cutting out goes to the back of its
# chain for a while, so the next visitor is not kept waiting behind it.
STRIKE_WINDOW = 600
_STRIKES: dict[str, deque[float]] = {}


def _strike(model_id: str) -> None:
    with _LOCK:
        _STRIKES.setdefault(model_id, deque(maxlen=8)).append(time.time())


def _demote_struck(chain: list[tuple[str, str]]) -> list[tuple[str, str]]:
    now = time.time()
    with _LOCK:
        struck = {mid for mid, dq in _STRIKES.items()
                  if sum(1 for t in dq if now - t < STRIKE_WINDOW) >= 2}
    return [c for c in chain if c[1] not in struck] + [c for c in chain if c[1] in struck]


# ---------------------------------------------------------------------------
# Speech
# ---------------------------------------------------------------------------
# Names spelled for the ear. Order matters: GPT-OSS before the bare digits rule.
_SAY = (
    (re.compile(r"\bGPT-OSS\b", re.I), "G P T O S S"),
    (re.compile(r"\bGroq\b"), "Grok"),
    (re.compile(r"\bOpenRouter\b"), "Open Router"),
    (re.compile(r"\bFastAPI\b"), "Fast A P I"),
    (re.compile(r"\bSQLite\b"), "S Q Lite"),
    (re.compile(r"\bedge-tts\b", re.I), "edge T T S"),
    (re.compile(r"\bAURA\b"), "Aura"),
    (re.compile(r"\b(\d+)B\b"), r"\1 B"),
    (re.compile(r"\be\.g\.", re.I), "for example"),
    (re.compile(r"\bi\.e\.", re.I), "that is"),
)
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def _speakable(text: str, max_sentences: int = 3, max_chars: int = MAX_TTS_CHARS) -> str:
    """A reply as AURA should say it out loud, not as it reads on screen.

    Code, links, markdown, emoji and slash commands go. Sentences are cut only
    on real boundaries: the desktop cleaner split on every full stop, so "3.5"
    and "web_api.py" broke mid-word. A few names are spelled for the ear.
    """
    t = re.sub(r"```[\s\S]*?(?:```|$)", " ", text)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"https?://\S+", "", t)
    t = _EMOJI.sub("", t)
    t = re.sub(r"\([^()]*?/\w[^()]*\)", "", t)                          # "(/code_end to exit)"
    t = re.sub(r"(?<![\w/.])/([a-z]\w*)", lambda m: m.group(1).replace("_", " "), t)
    t = re.sub(r"(?m)^\s*(?:#{1,6}\s+|[-*•]\s+|\d+[.)]\s+)", "", t)     # headings and list markers
    t = re.sub(r"\*\*|__|~~|[*#>|]", "", t)
    t = re.sub(r"(?<=\w)_(?=\w)", " ", t)
    t = re.sub(r"\s*[—–·]\s*", ", ", t).replace("→", " to ")
    for pattern, spoken in _SAY:
        t = pattern.sub(spoken, t)
    t = re.sub(r"(?<=[.!?:;,])[ \t]*\n\s*", " ", t)                     # a line that already ends a thought
    t = re.sub(r"\s*\n\s*", ". ", t)                                     # a heading or list item on its own line
    t = re.sub(r"\s+", " ", t).strip(" ,")
    kept: list[str] = []
    total = 0
    for sentence in _SENTENCE_END.split(t):
        if kept and (len(kept) >= max_sentences or total + len(sentence) > max_chars):
            break
        kept.append(sentence)
        total += len(sentence) + 1
    return " ".join(kept)[:max_chars].strip()


# ---------------------------------------------------------------------------
# Generation: the model chain, run on a worker thread
# ---------------------------------------------------------------------------
def _generate(chain: list[tuple[str, str]], prompt: str, system: str, intent: str,
              put: Callable[[tuple[str, Any]], None]) -> None:
    """Try a model chain in order, like ai_router.route_streaming, reporting
    every fallback so the page can show it."""
    from core import ai_router

    last = "CONNECTION_ERROR"
    try:
        for name, mid in chain:
            gen = ai_router.call_groq_streaming(prompt, system, intent=intent, model=mid)
            try:
                first = next(gen)
            except StopIteration:
                put(("fallback", {"model": name, "reason": "empty reply"}))
                continue
            if first in SENTINELS:
                last = first
                put(("fallback", {"model": name, "reason": "rate limited"
                                  if first == "RATE_LIMIT" else "unavailable"}))
                continue
            put(("model", {"name": name, "id": mid, "provider": ai_router._provider_for(mid)}))

            def combined(first_chunk: str = first, rest=gen):
                yield first_chunk
                yield from rest

            for chunk in ai_router._sanitize_reasoning_stream(combined()):
                if chunk not in SENTINELS:      # mid-stream sentinels are status, not text
                    put(("chunk", chunk))
            return
        put(("exhausted", last))
    except Exception as e:  # noqa: BLE001
        print(f"[AURA web] generation failed: {type(e).__name__}: {e}")
        put(("exhausted", "CONNECTION_ERROR"))
    finally:
        put(("eof", None))


_FENCE = re.compile(r"(```[\s\S]*?```)")
_LOST = "Lost my train of thought there — say that again?"


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _finalize(raw: str, intent: str, query: str, model_name: str) -> dict[str, Any]:
    """Raw model text → what AURA actually says, plus what the guard did."""
    from core.ai_router import extract_code_block, sanitize_text
    from core.response_composer import _CAPS, PersonaLayer, _score, compose

    if intent == "CODING":
        if "```" not in raw:
            chat, lang, code = extract_code_block(raw)
            if code:
                raw = f"{chat}\n\n```{lang}\n{code}\n```".strip()
        # Scrub the prose around the code, never the code itself. The coding
        # style's "Here's the ...:" trim is skipped on purpose: it empties short
        # intros into the fallback line (QA_REPORT.md, H1).
        notes: list[str] = []
        out: list[str] = []
        for part in _FENCE.split(raw):
            if part.startswith("```"):
                out.append(part.strip())
            elif part.strip():
                cleaned, n = PersonaLayer.scrub(part)
                notes += n
                if cleaned:
                    out.append(cleaned)
        text = "\n\n".join(out) or raw
        quality, confidence, _ = _score(raw, text, notes)
        return {"text": text, "style": "coding", "cap": None, "notes": _dedupe(notes),
                "quality": quality, "confidence": confidence}

    longform = intent in LONGFORM_INTENTS
    if longform:
        # A report or plan keeps its structure: only a leading preamble is
        # peeled, the rest ships verbatim. sanitize_text rejoins what it keeps
        # without the line breaks ("...the weekend.Architecture / Approach:") and
        # deletes ordinary sentences like "the user signs in"; the opening of a
        # long reply was already checked by the leak gate.
        from core.ai_router import _peel_head
        deleaked = _peel_head(raw, final=True)[0].strip()
        leak_note = "reasoning preamble removed"
    else:
        deleaked = sanitize_text(raw, query=query)
        leak_note = "reasoning leak repaired"
    if not deleaked:
        return {"text": _LOST, "style": "casual", "cap": None,
                "notes": ["whole reply was reasoning, discarded"],
                "quality": 0.0, "confidence": 35}
    notes = [leak_note] if deleaked != raw.strip() else []
    # No query for the persona layer: its canned identity answers are written for
    # the desktop ("watch your screen when you ask", "remember facts about you"),
    # and a visitor here would take them as true of this tab. The model answers
    # from the fact sheet, which knows what the demo can and cannot do.
    c = compose(deleaked, intent, "", model_name, longform=longform)
    cap = None if longform else (4 if c.style == "casual" and intent == "PERSONAL"
                                 else _CAPS.get(c.style))
    # The models text like a friend and sometimes open in lowercase ("can't see
    # your screen from here."), which on this page reads as a cut-off reply.
    text = c.text[:1].upper() + c.text[1:] if c.text[:1].islower() else c.text
    return {"text": text, "style": c.style, "cap": cap, "notes": _dedupe(notes + c.notes),
            "quality": c.quality, "confidence": c.confidence}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def _stream(gen, s: WebSession) -> StreamingResponse:
    return StreamingResponse(gen, media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "X-Aura-Session": s.id,
    })


@router.api_route("/session", methods=["GET", "POST"])
async def web_session(request: Request,
                      x_aura_session: str | None = Header(default=None)) -> dict[str, Any]:
    ip = _client_ip(request)
    _rate_limit(ip)
    s = _get_session(x_aura_session) or _new_session()

    from core import ai_router, model_router
    from core.conversation_director import WORKSPACE
    from core.nature import NATURES
    return {
        **_public(s, ip),
        "natures": [{"key": k, "label": v["label"], "icon": v["icon"],
                     "overlay": v["overlay"].strip()} for k, v in NATURES.items()],
        "modes": [{"key": "chat", "intent": None, "blurb": ""}] + [
            {"key": k, "intent": v["intent"], "blurb": v["blurb"]} for k, v in WORKSPACE.items()],
        "models": [{"name": n, "id": m, "provider": ai_router._provider_for(m)}
                   for n, m in model_router.MODELS.items()],
        "routes": dict(model_router.INTENT_PRIMARY),
        "chains": _job_chains(),
        "voice": VOICE,
    }


@router.post("/mode")
async def web_mode(request: Request, payload: dict = Body(...),
                   x_aura_session: str | None = Header(default=None)) -> dict[str, Any]:
    ip = _client_ip(request)
    _rate_limit(ip)
    s = _require_session(x_aura_session)
    from core.conversation_director import WORKSPACE

    want = str(payload.get("mode") or "chat").lower()
    if want != "chat" and want not in WORKSPACE:
        raise HTTPException(400, "unknown mode")
    with s.lock:
        current = MODE_KEY.get(s.director.mode, "chat")
        text = ""
        if want != current:
            command = f"/{current}_end" if want == "chat" else f"/{want}"
            text = s.director.handle(command).text
    return {"text": text, **_public(s, ip)}


@router.post("/reset")
async def web_reset(request: Request,
                    x_aura_session: str | None = Header(default=None)) -> dict[str, Any]:
    ip = _client_ip(request)
    _rate_limit(ip)
    s = _require_session(x_aura_session)
    with s.lock:
        s.turns.clear()
        s.director = _new_director()
    return _public(s, ip)                  # the message budget is NOT restored


@router.post("/chat")
async def web_chat(request: Request, payload: dict = Body(...),
                   x_aura_session: str | None = Header(default=None)):
    ip = _client_ip(request)
    _rate_limit(ip)
    s = _require_session(x_aura_session)

    text = str(payload.get("text") or "").strip()[:MAX_INPUT_CHARS]
    if not text:
        raise HTTPException(400, "empty message")

    from core.conversation_director import Directive
    from core.nature import NATURES
    nature = str(payload.get("nature") or s.nature)
    s.nature = nature if nature in NATURES else "auto"
    t0 = time.perf_counter()

    # 1. The Director decides first, exactly as on the desktop.
    with s.lock:
        if text.lower().startswith("/prompt"):
            directive = Directive("reply", PROMPT_DESKTOP_ONLY)
        else:
            directive = s.director.handle(text)
        in_mode = s.director.mode in WORKSPACE_MODES
    mode = MODE_KEY.get(s.director.mode, "chat")

    if directive.kind in ("reply", "llm_once"):
        reply = directive.text if directive.kind == "reply" else PROMPT_DESKTOP_ONLY

        async def instant():
            yield _sse("route", {"lane": "reply", "mode": mode, "nature": s.nature})
            yield _sse("done", {
                "text": reply, "lane": "reply", "intent": None, "source": "director",
                "model": None, "fallbacks": [], "style": None, "cap": None,
                "notes": ["answered locally, no model call"], "counted": False,
                "ms": int((time.perf_counter() - t0) * 1000), **_public(s, ip),
            })
        return _stream(instant(), s)

    if directive.kind in ("generate", "plan", "execute_prompt"):
        body, pinned, source = directive.text or text, "CODING", "code request"
    else:
        body, pinned = directive.text or text, directive.intent or ""
        source = "workspace mode" if in_mode else ("director rule" if pinned else "classifier")

    blocked = _charge(s, ip)
    if blocked == "limit":
        return JSONResponse({"detail": "demo limit reached", "code": "limit",
                             **_public(s, ip)}, status_code=429)
    if blocked == "busy":
        return JSONResponse({"detail": "The demo hit today's ceiling. Try again tomorrow.",
                             "code": "busy", **_public(s, ip)}, status_code=503)

    loop = asyncio.get_running_loop()

    async def run_chain(chain, prompt: str, system: str, intent: str, acc: dict[str, Any]):
        """Stream one pass down `chain` into `acc`. An OpenRouter reply is held
        back until its opening reads like an answer; if it does not, the pass
        stops with acc["leaked"] set and the caller re-routes."""
        q: asyncio.Queue = asyncio.Queue()

        def put(item: tuple[str, Any]) -> None:
            try:
                loop.call_soon_threadsafe(q.put_nowait, item)
            except RuntimeError:        # loop closed: the visitor left
                pass

        threading.Thread(target=_generate, args=(chain, prompt, system, intent, put),
                         daemon=True).start()
        held: list[str] = []
        gated = False
        # until something reaches the visitor, each model is on the clock
        deadline: float | None = time.perf_counter() + FIRST_TOKEN_DEADLINE
        while True:
            if deadline is None:
                kind, data = await q.get()
            else:
                try:
                    kind, data = await asyncio.wait_for(
                        q.get(), timeout=max(0.05, deadline - time.perf_counter()))
                except asyncio.TimeoutError:
                    acc["leaked"] = acc["slow"] = True   # its thread winds down alone
                    return
            if kind == "eof":
                if held:
                    head = "".join(held)
                    if _looks_leaked(head, intent, s.nature):
                        acc["leaked"] = True
                        return
                    acc["parts"].append(head)
                    yield _sse("state", {"state": "speaking"})
                    yield _sse("chunk", {"text": head})
                return
            if kind == "fallback":
                acc["fallbacks"].append(data)
                acc["attempt"] += 1
                deadline = time.perf_counter() + FIRST_TOKEN_DEADLINE
                yield _sse("fallback", data)
            elif kind == "model":
                acc["model"] = data
                gated = data["provider"] == "openrouter"
                deadline = time.perf_counter() + FIRST_TEXT_DEADLINE if gated else None
                yield _sse("model", data)
                if not gated:
                    yield _sse("state", {"state": "speaking"})
            elif kind == "chunk":
                if not gated:
                    deadline = None
                    acc["parts"].append(data)
                    yield _sse("chunk", {"text": data})
                    continue
                held.append(data)
                head = "".join(held)
                if len(head) < GATE_CHARS and "```" not in head:
                    continue
                if _looks_leaked(head, intent, s.nature, partial=True):
                    acc["leaked"] = True    # abandon the stream; its thread winds down alone
                    return
                gated, held, deadline = False, [], None
                acc["parts"].append(head)
                yield _sse("state", {"state": "speaking"})
                yield _sse("chunk", {"text": head})
            elif kind == "exhausted":
                acc["failed"] = data

    async def finish(acc: dict[str, Any], intent: str):
        raw = "".join(acc["parts"]).strip()
        if not raw:
            return None
        return await asyncio.to_thread(_finalize, raw, intent, text,
                                       acc["model"]["name"] if acc["model"] else "")

    async def events():
        yield _sse("state", {"state": "thinking"})
        if pinned:
            intent, said = pinned, pinned
        else:
            intent, said = await asyncio.to_thread(_classify, text)

        from core import model_router
        chain = _demote_struck(model_router.candidates_for(intent))
        yield _sse("route", {
            "lane": "chat", "intent": intent, "classifier": said, "source": source,
            "mode": mode, "nature": s.nature, "candidates": [n for n, _ in chain],
        })

        system = _build_system(intent, text, s.nature, s, ip)
        prompt = _build_prompt(s, body)
        acc: dict[str, Any] = {"parts": [], "fallbacks": [], "model": None,
                               "failed": "", "leaked": False, "slow": False, "attempt": 0}
        start, final = 0, None
        while start < len(chain):
            acc.update(parts=[], model=None, failed="", leaked=False, slow=False, attempt=0)
            async for frame in run_chain(chain[start:], prompt, system, intent, acc):
                yield frame
            model = acc["model"]
            final = None if acc["leaked"] else await finish(acc, intent)
            tried = chain[min(start + acc["attempt"], len(chain) - 1)]
            next_at = start + acc["attempt"] + 1

            # A reply that recited its instructions, spent itself thinking out
            # loud, stopped after a word, or took too long to say anything goes
            # to the next model in the chain while one is left. A long report
            # already passed the opening check; regenerating a minute of output
            # over a late marker costs the visitor more than it saves.
            thin = bool(final and _too_thin(final["text"]))
            suspect = acc["leaked"] or thin or bool(
                final and model and model["provider"] == "openrouter"
                and (final["text"] == _LOST or (intent not in LONGFORM_INTENTS
                                                and _looks_leaked(final["text"], intent, s.nature))))
            if suspect and (acc["leaked"] or thin or model):
                _strike(tried[1])
            if thin and next_at >= len(chain):
                final = None                  # a bare "The" is not an answer; say so honestly
            if not suspect or next_at >= len(chain):
                break
            reason = ("took too long" if acc["slow"] else
                      "stopped mid-sentence" if thin else "tripped the leak guard")
            trip = {"model": tried[0], "reason": reason}
            acc["fallbacks"].append(trip)
            yield _sse("fallback", trip)
            yield _sse("reset", {"reason": trip["reason"]})
            yield _sse("state", {"state": "thinking"})
            start, final = next_at, None

        if not final:
            _refund(s, ip)
            yield _sse("error", {
                "message": MSG_RATE_LIMIT if acc["failed"] == "RATE_LIMIT" else MSG_UNREACHABLE,
                "code": acc["failed"] or "empty", "fallbacks": acc["fallbacks"], **_public(s, ip),
            })
            return

        s.turns.append(("user", text))
        s.turns.append(("aura", final["text"][:1500]))
        del s.turns[:-MAX_TURNS * 2]

        yield _sse("done", {
            **final, "lane": "chat", "intent": intent, "classifier": said,
            "source": source, "model": acc["model"], "fallbacks": acc["fallbacks"],
            "counted": True, "ms": int((time.perf_counter() - t0) * 1000), **_public(s, ip),
        })

    return _stream(events(), s)


_TTS_CACHE: OrderedDict[str, bytes] = OrderedDict()


@router.post("/tts")
async def web_tts(request: Request, payload: dict = Body(...),
                  x_aura_session: str | None = Header(default=None)) -> Response:
    ip = _client_ip(request)
    _rate_limit(ip)
    _require_session(x_aura_session)

    # Written for the ear (see _speakable), with the desktop voice's tone table
    # picking rate and pitch from the mood of the line.
    from modules.voice_output import TONE_SETTINGS, detect_tone
    text = _speakable(str(payload.get("text") or "")[:4000])
    if not text.strip(" ."):
        raise HTTPException(400, "nothing to say")
    tone = detect_tone(text)
    key = hashlib.sha1(f"{VOICE}|{tone}|{text}".encode()).hexdigest()

    audio = _TTS_CACHE.get(key)
    if audio is None:
        now = time.time()
        with _LOCK:
            clips = _IP_TTS.setdefault(ip, deque())
            if _trim(clips, DAY, now) >= TTS_DAILY:
                raise HTTPException(429, "voice limit reached")
            clips.append(now)
        try:
            import edge_tts
            tune = TONE_SETTINGS.get(tone, TONE_SETTINGS["normal"])
            speech = edge_tts.Communicate(text, voice=VOICE, rate=tune["rate"], pitch=tune["pitch"])
            buf = bytearray()
            async for chunk in speech.stream():
                if chunk.get("type") == "audio":
                    buf += chunk["data"]
            audio = bytes(buf)
        except Exception as e:  # noqa: BLE001
            print(f"[AURA web] tts failed: {type(e).__name__}: {e}")
            audio = b""
        if not audio:
            raise HTTPException(502, "voice unavailable")
        _TTS_CACHE[key] = audio
        while len(_TTS_CACHE) > 200:
            _TTS_CACHE.popitem(last=False)
    else:
        _TTS_CACHE.move_to_end(key)

    return Response(content=audio, media_type="audio/mpeg",
                    headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------------
# Static site + standalone app
# ---------------------------------------------------------------------------
def mount_site(app) -> bool:
    """Mount the public site at "/". Call AFTER every API router."""
    if os.getenv("AURA_WEB_SITE", "1") != "1":
        return False
    if not (SITE_DIR / "index.html").is_file():
        print(f"[AURA web] site directory missing: {SITE_DIR}")
        return False
    from fastapi.staticfiles import StaticFiles

    class FreshStaticFiles(StaticFiles):
        """Every file is revalidated against its ETag (usually a cheap 304).
        With no Cache-Control at all, browsers cached site.js, the styles and
        the voice clips heuristically and kept playing an old build for a
        while after every update."""

        async def get_response(self, path: str, scope):
            response = await super().get_response(path, scope)
            response.headers["Cache-Control"] = "no-cache"
            return response

    app.mount("/", FreshStaticFiles(directory=str(SITE_DIR), html=True), name="aura-site")
    print(f"[AURA web] site mounted at / from {SITE_DIR}")
    return True


def create_app():
    """The public demo on its own: this router, the site, nothing else."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="AURA web demo", docs_url=None, redoc_url=None, openapi_url=None)
    port = os.getenv("AURA_WEB_PORT", "8770")
    origins = [o.strip() for o in os.getenv(
        "AURA_WEB_ORIGINS", f"http://127.0.0.1:{port},http://localhost:{port}").split(",")
        if o.strip()]
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Aura-Session"], expose_headers=["X-Aura-Session"],
    )
    app.include_router(router)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "sessions": len(_SESSIONS)}

    mount_site(app)
    return app


if __name__ == "__main__":
    # The composer prints box-drawing debug lines; a redirected Windows
    # console would otherwise raise on them.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    import uvicorn
    uvicorn.run(create_app(), host=os.getenv("AURA_WEB_HOST", "127.0.0.1"),
                port=int(os.getenv("AURA_WEB_PORT", "8770")))
