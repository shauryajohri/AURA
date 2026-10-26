import re
import random
from dataclasses import dataclass
from typing import List
import datetime

try:
    from core.personality_state import get_tone_modifiers
except:
    def get_tone_modifiers():
        return {'tones': [], 'energy_level': 5}

@dataclass
class SpeechChunk:
    text: str
    tone: str = "normal"
    pause_before: float = 0.0
    pause_after: float = 0.12
    speed_factor: float = 1.0


_CONTRACTIONS = {
    r"\bI will\b":      "I'll",
    r"\bI am\b":        "I'm",
    r"\bI have\b":      "I've",
    r"\bI would\b":     "I'd",
    r"\byou are\b":     "you're",
    r"\byou will\b":    "you'll",
    r"\bdo not\b":      "don't",
    r"\bdoes not\b":    "doesn't",
    r"\bdid not\b":     "didn't",
    r"\bcannot\b":      "can't",
    r"\bwill not\b":    "won't",
    r"\bwould not\b":   "wouldn't",
    r"\bshould not\b":  "shouldn't",
    r"\bcould not\b":   "couldn't",
    r"\bthey are\b":    "they're",
    r"\bwe are\b":      "we're",
    r"\bit is\b":       "it's",
    r"\bthat is\b":     "that's",
    r"\bhere is\b":     "here's",
    r"\bthere is\b":    "there's",
    r"\blet us\b":      "let's",
}

_FORMAL_TO_CASUAL = {
    r"\bI will open\b":             "Opening",
    r"\bI am going to\b":           "I'll",
    r"\bPlease note that\b":        "",
    r"\bIt should be noted that\b": "",
    r"\bIn order to\b":             "To",
    r"\bDue to the fact that\b":    "Because",
    r"\bAt this point in time\b":   "Right now",
    r"\bAs per your request\b":     "",
    r"\bCertainly[,!]?\b":          "Sure",
    r"\bAbsolutely[,!]?\b":         "Yep",
    r"\bOf course[,!]?\b":          "Sure",
    r"\bI apologize\b":             "Sorry",
    r"\bI understand\b":            "Got it",
}

_THINKING_FILLERS = ["Alright,", "Okay,", "So,", "Right,", "Got it —"]


def text_to_spoken(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", "", text)   # strip code blocks entirely
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*",     r"\1", text)
    text = re.sub(r"`(.+?)`",       r"\1", text)
    text = re.sub(r"#+\s+",         "",    text)
    for pattern, replacement in _CONTRACTIONS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    for pattern, replacement in _FORMAL_TO_CASUAL.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = re.sub(r"  +", " ", text).strip()
    return text


# Every chunk is its own TTS request, and the voice plans its intonation one
# request at a time. Chunks used to break at every comma, dash, "and" and
# "but" (and at word 16, mid-phrase), so each fragment was read as a complete
# flat statement with a gap after it — that was most of what made AURA sound
# robotic. Now a chunk is a whole sentence, or two short ones together, and a
# sentence is only broken (at a comma) when it's long enough that the first
# word would otherwise wait too long.
_SENTENCE = re.compile(r"(?<=[.!?…])\s+")
_CLAUSE   = re.compile(r"(?<=[,;:])\s+")
_MAX_WORDS = 28   # past this the first word waits too long on the network
_MIN_WORDS = 4    # shorter than this rides along with its neighbour

_SENTENCE_PAUSE = 0.08
_CLAUSE_PAUSE   = 0.02   # a long sentence broken at a comma: keep it flowing


def _split_long(sentence: str) -> List[tuple]:
    if len(sentence.split()) <= _MAX_WORDS:
        return [(sentence, _SENTENCE_PAUSE)]
    parts, buf = [], ""
    for clause in _CLAUSE.split(sentence):
        joined = f"{buf} {clause}".strip()
        if buf and len(joined.split()) > _MAX_WORDS:
            parts.append((buf, _CLAUSE_PAUSE))
            buf = clause
        else:
            buf = joined
    if buf:
        parts.append((buf, _SENTENCE_PAUSE))
    return parts


def _split_into_chunks(text: str) -> List[tuple]:
    pieces = []
    for sentence in _SENTENCE.split(text):
        if sentence.strip():
            pieces.extend(_split_long(sentence.strip()))

    merged = []
    for piece, pause in pieces:
        if merged:
            prev, _ = merged[-1]
            short = min(len(prev.split()), len(piece.split())) < _MIN_WORDS
            if short and len(f"{prev} {piece}".split()) <= _MAX_WORDS:
                merged[-1] = (f"{prev} {piece}", pause)
                continue
        merged.append((piece, pause))
    return merged


_TONE_RULES = [
    (r"\b(hmm+|let me|one sec|checking|hold on)\b",        "thinking"),
    (r"[😏😄😊🙂]|\bdon't get distracted\b|\bjust sayin\b", "tease"),
    (r"\b(warning|careful|important|critical|error)\b",     "serious"),
    (r"\b(great|perfect|awesome|nice|well done)\b",         "warm"),
    (r"[!]{2,}|\b(now|immediately|urgent|quick)\b",         "urgent"),
    (r"[?]\s*$",                                            "questioning"),
    (r"\.\.\.+$",                                           "uncertain"),
    (r"\b(negative|bad|wrong|failed|fail)\b.*[?]",          "frustrated"),
]


def _classify_tone(text: str) -> str:
    lower = text.lower()
    for pattern, tone in _TONE_RULES:
        if re.search(pattern, lower):
            return tone

    modifiers = get_tone_modifiers()

    if modifiers.get('energy_level', 5) < 3:
        return "tired"
    if modifiers.get('frustration', 0) > 7:
        return "sympathetic"

    return "normal"


_TONE_TIMING = {
    "thinking":      {"speed": 0.87, "extra_pause": 0.05, "before": 0.04},
    "tease":         {"speed": 0.95, "extra_pause": 0.03, "before": 0.0},
    "serious":       {"speed": 0.91, "extra_pause": 0.04, "before": 0.03},
    "warm":          {"speed": 1.03, "extra_pause": 0.0,  "before": 0.0},
    "urgent":        {"speed": 1.10, "extra_pause": 0.0,  "before": 0.0},
    "questioning":   {"speed": 0.98, "extra_pause": 0.06, "before": 0.0},
    "uncertain":     {"speed": 0.90, "extra_pause": 0.08, "before": 0.02},
    "frustrated":    {"speed": 0.88, "extra_pause": 0.04, "before": 0.03},
    "tired":         {"speed": 0.80, "extra_pause": 0.10, "before": 0.05},
    "sympathetic":   {"speed": 0.92, "extra_pause": 0.05, "before": 0.02},
    "normal":        {"speed": 1.00, "extra_pause": 0.0,  "before": 0.0},
}


def _jitter(base: float) -> float:
    return max(0.0, base + random.uniform(-0.01, 0.01))


def plan(llm_response: str, mode: str = "CHAT") -> List[SpeechChunk]:
    """
    mode: CHAT | EXPLAIN | COMMAND | CODE | LONG
    Imported from response_mode.py — controls speed + pause scaling.
    """
    from modules.response_mode import MODE_BEHAVIOR

    if not llm_response or not llm_response.strip():
        return []

    behavior = MODE_BEHAVIOR.get(mode, MODE_BEHAVIOR["CHAT"])
    speed_factor = behavior["speed_factor"]
    pause_scale  = behavior["pause_scale"]

    spoken = text_to_spoken(llm_response.strip())
    raw    = _split_into_chunks(spoken)
    chunks = []

    for i, (chunk_text, base_pause) in enumerate(raw):
        tone   = _classify_tone(chunk_text)
        timing = _TONE_TIMING[tone]

        chunks.append(SpeechChunk(
            text         = chunk_text,
            tone         = tone,
            pause_before = (timing["before"] if i > 0 else 0.0) * pause_scale,
            pause_after  = _jitter((base_pause + timing["extra_pause"]) * pause_scale),
            speed_factor = timing["speed"] * speed_factor,
        ))

    # filler only for EXPLAIN mode — said as part of the first sentence, not
    # as a one-word clip of its own
    if mode == "EXPLAIN" and len(chunks) >= 3 and random.random() < 0.20:
        chunks[0].text = f"{random.choice(_THINKING_FILLERS)} {chunks[0].text}"

    return chunks


def debug(llm_response: str, mode: str = "CHAT") -> str:
    chunks = plan(llm_response, mode)
    lines  = [f"\n── Speech Plan [{mode}] ({len(chunks)} chunks) ──────────────"]
    for i, c in enumerate(chunks):
        lines.append(
            f"  {i+1}. [{c.tone:8s}] ⏸{c.pause_before:.2f}s "
            f"| '{c.text[:55]}' | ⏸{c.pause_after:.2f}s  x{c.speed_factor:.2f}"
        )
    lines.append("─" * 44)
    return "\n".join(lines)