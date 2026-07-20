"""
core/response_composer.py
-------------------------
The last mile between a raw model answer and AURA's voice.

Every model (Groq, OpenRouter, whatever comes later) flows through here, so
AURA is ONE consistent personality no matter which mind produced the words:

    LLM → ResponseComposer → PersonaLayer → User

What it does:
  1. PersonaLayer.scrub()  — strips AI disclaimers, corporate openers and
     leaked context from any model's output.
  2. Identity override     — "who are you?" / "what can you do?" / "what
     models?" get answered by AURA herself (product voice), never by the
     underlying model's generic self-description.
  3. Style shaping         — 5 styles (casual / explain / coding / search /
     creative), each with its own length + formatting discipline.
  4. Telemetry             — quality score, confidence %, and the reasons,
     printed as a debug box next to the reasoning box.

Pure rules, zero extra API calls: no added latency, no extra rate-limit
pressure. Deterministic, unit-testable.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

# ----------------------------------------------------------------------------
# Style registry — intent → one of the 5 response styles
# ----------------------------------------------------------------------------
# casual   : friendly, natural, short (group-chat energy)
# explain  : teacher mode — clear, roomy, examples welcome
# coding   : professional, technical, zero fluff
# search   : Perplexity energy — direct answer first, structured
# creative : longer, expressive (long-form workspace modes)
STYLE_FOR_INTENT = {
    "CASUAL": "casual",
    "PERSONAL": "casual",
    "COMMAND": "casual",
    "EXPLAIN": "explain",
    "CODING": "coding",
    "SEARCH": "search",
    "RESEARCH": "search",
    "DISCUSSION": "creative",
    "PLAN": "creative",
    "CREATIVE": "creative",
}

# sentence caps per style (None = no cap)
_CAPS = {"casual": 2, "explain": 8, "coding": None, "search": 6, "creative": None}

DEBUG_COMPOSER = True


@dataclass
class Composed:
    text: str
    style: str
    quality: float          # 0..10 — how clean the raw answer was
    confidence: int         # 0..100 — how sure the answer sounds
    notes: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------
# Persona layer — every model output is scrubbed here
# ----------------------------------------------------------------------------

# Whole sentences that must die wherever they appear.
_DISCLAIMER_SENTENCES = [
    r"as an ai(?: language model| assistant| model)?\b[^.!?\n]*[.!?]?",
    r"i(?:'m| am) (?:just )?(?:an?|your) (?:ai|artificial intelligence|large language model|language model|llm|virtual assistant|ai assistant|chatbot|computer program|digital assistant)\b[^.!?\n]*[.!?]?",
    r"i (?:was |am |'ve been )?(?:designed|created|programmed|trained|developed|built) (?:by|to)\b[^.!?\n]*(?:openai|meta|google|anthropic|nvidia|ai)[^.!?\n]*[.!?]?",
    r"i don'?t have (?:personal )?(?:feelings|emotions|a body|consciousness|personal experiences)\b[^.!?\n]*[.!?]?",
    r"my knowledge (?:cutoff|is limited to)\b[^.!?\n]*[.!?]?",
    r"i cannot (?:browse|access) the internet\b[^.!?\n]*[.!?]?",
]

# Corporate warm-up openers — deleted from the front of a reply.
_OPENERS = [
    r"certainly[,!.]?\s*",
    r"of course[,!.]?\s*",
    r"sure(?: thing)?[,!.]?\s*",
    r"absolutely[,!.]?\s*",
    r"great question[,!.]?\s*",
    r"good question[,!.]?\s*",
    r"i(?:'d| would) be happy to (?:help(?: you)?(?: with that)?|assist)[,!.]?\s*",
    r"let'?s tackle (?:this|that)[,!.]?\s*",
    r"thanks? for (?:asking|your question)[,!.]?\s*",
]

# Leaked prompt/context fragments (kept in sync with brain.guard_output).
_LEAKS = [
    r"User is .+?[,.]",
    r"User asks .+?[,.]",
    r"Current app .+?[,.]",
    r"\bAURA:\s*",
    r"Screen content:?[^.\n]*[.\n]",
]

_HEDGES = re.compile(
    r"\b(maybe|perhaps|possibly|i think|i believe|i guess|not (?:entirely )?sure|"
    r"it (?:seems|appears)|might be|could be|i'?m not certain)\b", re.I)


def _split_sentences(text: str) -> list[str]:
    """Split on sentence ends without shredding decimals, urls or code."""
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", text.strip())
    return [p.strip() for p in parts if p.strip()]


class PersonaLayer:
    """Keep AURA's tone. Remove AI disclaimers. Improve flow.
    Every single model goes through this — Claude, GPT, Gemini, Llama, all."""

    @staticmethod
    def scrub(raw: str) -> tuple[str, list[str]]:
        notes: list[str] = []
        text = raw.strip().strip('"').strip("'").strip()

        for pat in _LEAKS:
            new = re.sub(pat, "", text, flags=re.I)
            if new != text:
                notes.append("leaked context stripped")
                text = new

        for pat in _DISCLAIMER_SENTENCES:
            new = re.sub(pat, "", text, flags=re.I)
            if new != text:
                notes.append("AI disclaimer removed")
                text = new

        # openers only bite at the very start
        changed = True
        while changed:
            changed = False
            for pat in _OPENERS:
                new = re.sub(r"^\s*" + pat, "", text, flags=re.I)
                if new != text:
                    notes.append("corporate opener removed")
                    text = new
                    changed = True

        # collapse the scars: double spaces, orphaned punctuation, blank runs
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"^[,.;:!?\s]+", "", text)
        return text.strip(), notes


# ----------------------------------------------------------------------------
# Identity answers — AURA speaks for herself, no model gets to
# ----------------------------------------------------------------------------
_RE_WHO = re.compile(
    r"(?i)\b(who (?:are|r) (?:you|u)|what are you\b|what'?s your name|"
    r"introduce yourself|tell me about (?:yourself|you)\b|so (?:ur|you'?re) (?:the )?aura)")
_RE_CAN = re.compile(
    r"(?i)\b(what (?:all )?(?:tasks? )?(?:can|do) (?:you|u) (?:do|perform|handle)|"
    r"what (?:all )?tasks? (?:u|you) can|your (?:capabilities|abilities|features)|"
    r"what are you (?:capable|able))")
_RE_MODELS = re.compile(
    r"(?i)\b(what (?:all )?models?\b.{0,20}(?:use|run|have|support)|"
    r"which models?|what model are you|models? (?:u|you) can use)")

_WHO_ANSWERS = [
    "I'm AURA — your AI companion and workspace in one. I help you build software, "
    "research ideas, organize projects, and I remember what matters. The goal isn't "
    "just answering questions — it's helping you create.",
    "AURA. Not a chatbot — your companion and command center. I code with you, "
    "research for you, keep your projects and memories in one place, and occasionally "
    "judge your CSS.",
]
_CAN_ANSWERS = [
    "Plenty. I chat and keep you company, help you write and debug code, research topics, "
    "plan and manage projects, remember facts about you, watch your screen when you ask, "
    "handle your tasks, and talk back over voice. Ask for something and I'll route it to "
    "the right part of my brain.",
]


def _models_answer() -> str:
    """Built live from the roster so it never goes stale."""
    try:
        from core.model_router import MODELS as _RM  # display name → model id
        names = list(_RM.keys())
    except Exception:
        names = []
    roster = ", ".join(n for n in names[:6] if n) if names else \
        "several specialist models — coders, researchers, fast talkers"
    return (
        "I route your request to different minds depending on the job — for coding one "
        "model, research another, quick chat something faster. Right now my roster runs "
        f"{roster}, with automatic fallback when one is busy. You never have to pick — "
        "I choose, though you can lock or override any of them from the cosmos."
    )


def _identity_answer(query: str) -> str | None:
    if _RE_MODELS.search(query):
        return _models_answer()
    if _RE_CAN.search(query):
        return random.choice(_CAN_ANSWERS)
    if _RE_WHO.search(query):
        return random.choice(_WHO_ANSWERS)
    return None


# ----------------------------------------------------------------------------
# Style shaping
# ----------------------------------------------------------------------------
def _shape(text: str, style: str, intent: str) -> tuple[str, list[str]]:
    notes: list[str] = []
    cap = _CAPS.get(style)
    if style == "casual" and intent == "PERSONAL":
        cap = 4

    if cap and "```" not in text and "\n-" not in text and "\n*" not in text:
        sentences = _split_sentences(text)
        if len(sentences) > cap:
            text = " ".join(sentences[:cap])
            notes.append(f"trimmed {len(sentences)}→{cap} sentences")

    if style == "search":
        # answer-first discipline: if the model buried the answer under a
        # preamble like "There are several things to consider:", drop it.
        sentences = _split_sentences(text)
        if len(sentences) > 1 and re.match(
                r"(?i)^(there are (?:several|many|a few)|it depends|when it comes to|"
                r"that'?s an? (?:interesting|broad))", sentences[0]):
            text = " ".join(sentences[1:])
            notes.append("preamble dropped (answer first)")

    if style == "coding":
        text = re.sub(r"(?i)^(here(?:'s| is) (?:the|your|an?) [^.:\n]*[:.])\s*", "", text)

    return text.strip(), notes


# ----------------------------------------------------------------------------
# Telemetry — quality & confidence, for the debug box
# ----------------------------------------------------------------------------
def _score(raw: str, final: str, notes: list[str]) -> tuple[float, int, str]:
    quality = 10.0
    reasons = []
    disc = sum(1 for n in notes if "disclaimer" in n)
    opener = sum(1 for n in notes if "opener" in n)
    leak = sum(1 for n in notes if "leaked" in n)
    if disc:
        quality -= 1.5 * disc; reasons.append(f"{disc} disclaimer(s)")
    if opener:
        quality -= 0.5 * opener; reasons.append("corporate opener")
    if leak:
        quality -= 2.0 * leak; reasons.append("context leak")
    if not final:
        quality = 0.0; reasons.append("empty after scrub")
    if any("trimmed" in n for n in notes):
        quality -= 0.5; reasons.append("over-length")

    hedges = len(_HEDGES.findall(final))
    confidence = max(35, 96 - hedges * 12)
    if not reasons:
        reasons.append("clean pass")
    return max(0.0, round(quality, 1)), confidence, ", ".join(reasons)


# ----------------------------------------------------------------------------
# The composer
# ----------------------------------------------------------------------------
def compose(raw: str, intent: str, query: str = "", model_name: str = "",
            longform: bool = False) -> Composed:
    """Everything AURA says out loud comes through here."""
    style = "creative" if longform else STYLE_FOR_INTENT.get(intent, "casual")

    text, notes = PersonaLayer.scrub(raw)

    # Identity questions: AURA answers, not the model.
    identity = _identity_answer(query) if query else None
    if identity is not None:
        notes.append("identity answered by persona layer")
        text = identity
    elif not longform:
        text, shape_notes = _shape(text, style, intent)
        notes += shape_notes

    if not text:
        text = "Hmm — lost my train of thought. Say that again?"
        notes.append("fallback line used")

    quality, confidence, reason = _score(raw, text, notes)

    if DEBUG_COMPOSER:
        print("┌─ Composer ────────────────────────────────────")
        print(f"│  style : {style.upper():8s}  intent: {intent}"
              + (f"  ·  {model_name}" if model_name else ""))
        print(f"│  quality: {quality}/10   confidence: {confidence}%")
        print(f"│  reason : {reason}")
        if notes:
            print(f"│  actions: {', '.join(dict.fromkeys(notes))}")
        print("└───────────────────────────────────────────────")

    return Composed(text=text, style=style, quality=quality,
                    confidence=confidence, notes=notes)


def compose_text(raw: str, intent: str, query: str = "", model_name: str = "",
                 longform: bool = False) -> str:
    """Convenience: composed text only."""
    return compose(raw, intent, query, model_name, longform).text
