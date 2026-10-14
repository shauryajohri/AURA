"""
core/guard/guest_lane.py
------------------------
How AURA talks to a guest the owner vouched for.

A guest gets real help — questions, explanations, code — but not the owner's
life. So this lane deliberately bypasses core.brain: no durable facts, no
past conversations, no screen reading, no project memory, no task/quest/app
commands, and nothing the guest says is written to the store (otherwise "my
name is Rahul" would become a fact about the owner).

History is a small in-RAM window, wiped when the guest pass ends.
"""

from __future__ import annotations

import re
import threading

_history: list[tuple[str, str]] = []
_lock = threading.Lock()
MAX_TURNS = 6

_CODE_HINT = re.compile(
    r"(?i)\b(code|function|bug|error|exception|compile|python|javascript|typescript|java|c\+\+|"
    r"rust|golang|sql|regex|algorithm|leetcode|class|api|stack trace|traceback)\b|```")
_EXPLAIN_HINT = re.compile(r"(?i)\b(explain|how (?:does|do|is|can)|what (?:is|are)|why (?:does|is|do)|teach me)\b")


def _system(owner: str) -> str:
    try:
        from core.personality import DONNA_SYSTEM_PROMPT as base
    except Exception:  # noqa: BLE001
        base = "You are AURA, a sharp, warm AI companion."
    return (
        base
        + f"\n\nRIGHT NOW YOU ARE TALKING TO A GUEST, NOT {owner.upper()}.\n"
        f"- {owner} (your owner and buddy) said it's okay to help this person.\n"
        f"- Be genuinely helpful and friendly, and you may say {owner} let you help them.\n"
        f"- NEVER share anything about {owner}: no memories, facts, projects, past "
        "conversations, schedule, files or screen. If asked, say that's "
        f"{owner}'s to share, not yours.\n"
        "- You can't open apps, run commands, or change anything on this laptop for a guest.\n"
        "- Don't call them by the owner's name. If they tell you their name, use it."
    )


_LOST = "Sorry — I lost my train of thought. Say that again?"


def reset() -> None:
    with _lock:
        _history.clear()


_FENCE = re.compile(r"```([\w+#.-]*)\n(.*?)```", re.S)


class _ProseOnly:
    """Pass streamed text through with fenced code held back. The blocks are
    re-emitted whole via on_code at the end, so showing them inline too would
    print every block twice."""

    def __init__(self, emit) -> None:
        self.emit = emit
        self.in_code = False
        self.tail = ""   # trailing backticks that might be half a fence

    def feed(self, chunk: str) -> None:
        s, out, i = self.tail + chunk, [], 0
        while (j := s.find("```", i)) != -1:
            if not self.in_code:
                out.append(s[i:j])
            self.in_code = not self.in_code
            i = j + 3
        rest = s[i:]
        hold = len(rest) - len(rest.rstrip("`"))
        self.tail = rest[len(rest) - hold:] if hold else ""
        if not self.in_code:
            out.append(rest[:len(rest) - hold] if hold else rest)
        if "".join(out):
            self.emit("".join(out))

    def flush(self) -> None:
        if self.tail and not self.in_code:
            self.emit(self.tail)
        self.tail = ""


def answer(text: str, owner: str, on_chunk=None, on_code=None) -> str:
    """Stream a guest reply. Returns the PROSE (what gets spoken); fenced code
    goes to on_code, the same split core.brain makes, so code is shown but
    never read aloud."""
    from core.ai_router import route_streaming, sanitize_text

    with _lock:
        past = list(_history[-MAX_TURNS:])
    convo = "\n".join(f"{'Guest' if r == 'user' else 'AURA'}: {t}" for r, t in past)
    prompt = (f"Earlier with this guest (background only):\n{convo}\n\n" if convo else "") + (
        f"THE GUEST'S MESSAGE TO ANSWER:\n{text}")
    intent = ("CODING" if _CODE_HINT.search(text)
              else "EXPLAIN" if _EXPLAIN_HINT.search(text) else "CASUAL")

    sink = None
    if on_chunk:
        sink = _ProseOnly(on_chunk) if on_code else None
    parts: list[str] = []
    for chunk in route_streaming(intent, prompt, system_prompt=_system(owner)):
        if chunk in ("RATE_LIMIT", "CONNECTION_ERROR"):
            chunk = "I can't reach my models right now — try again in a moment."
        parts.append(chunk)
        if sink:
            sink.feed(chunk)
        elif on_chunk:
            on_chunk(chunk)
    if sink:
        sink.flush()
    # Never fall back to the raw text: when the sanitiser strips everything,
    # what's left is the model thinking out loud — which can quote the
    # owner-protection instructions and the owner's name.
    reply = sanitize_text("".join(parts), query=text).strip() or _LOST

    with _lock:
        _history.extend([("user", text), ("aura", reply)])
        del _history[:-2 * MAX_TURNS]

    if on_code and _FENCE.search(reply):
        for lang, code in _FENCE.findall(reply):
            on_code(lang, code.rstrip("\n"))
        return _FENCE.sub("", reply).strip()
    return reply
