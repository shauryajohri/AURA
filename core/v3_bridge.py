# core/v3_bridge.py
"""
V3 Bridge — the single seam between the two standalone V3 engines and the
live app (brain.py, proactive.py, server.py, the React UI).

Both engines were built dependency-free and unit-tested in isolation:

    modules/error_intelligence  →  "what went wrong, and what do I say?"
    modules/developer_state     →  "how is this session going, and should I
                                    say anything at all?"

Neither of them knows about AURA's personality system, the websocket, or the
screen watcher. This module owns exactly that glue and nothing else, so the
engines stay testable and the app keeps one obvious place to look when the
integration misbehaves.

Design rules kept deliberately tight:

  • Never raise into a caller. Every public function is wrapped — a bug in
    the intelligence layer must not take down the chat loop or the watcher.
  • Never call the network. `explain_error` reports `needs_llm` and lets the
    caller (which owns the model router) do the LLM hop.
  • Announcements go out through one injected sink, so server.py decides how
    they reach the UI and this module stays importable without FastAPI.

Wiring map (who calls what):

    proactive._loop          → observe_screen(ctx), tick()
    brain.mark_user_active   → note_activity()
    brain.process_streaming  → scan_user_text(query)   [records + context hint]
    server REST /api/v3/*    → mistakes_today(), trends(), session()
    server REST /api/v3/build→ report_build(success)
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from modules.developer_state import get_state_engine
from modules.developer_state.models import Announcement
from modules.error_intelligence import get_engine as get_error_engine

# ---------------------------------------------------------------------------
# Personality mapping
# ---------------------------------------------------------------------------
# The V3 reply packs speak in four voices; AURA's user-facing "nature" picker
# has its own vocabulary. One table, one place to change it.
_NATURE_TO_PACK = {
    "auto": "companion",
    "chill": "companion",
    "focus": "engineer",
    "savage": "roast",
    "professional": "professional",
}


def _personality() -> str:
    try:
        from core.nature import get_nature
        return _NATURE_TO_PACK.get(get_nature(), "companion")
    except Exception:  # noqa: BLE001
        return "companion"


# ---------------------------------------------------------------------------
# Announcement sink (set by server.py at startup)
# ---------------------------------------------------------------------------
_sink: Callable[[dict], None] | None = None
_lock = threading.Lock()

# Last N things V3 said, so a UI that connects late still has something to show.
_recent: list[dict] = []
_RECENT_MAX = 30


def set_sink(fn: Callable[[dict], None] | None) -> None:
    """Register where announcements go (server.py hands us a broadcaster)."""
    global _sink
    _sink = fn


def _publish(payload: dict) -> None:
    payload.setdefault("ts", time.time())
    with _lock:
        _recent.append(payload)
        if len(_recent) > _RECENT_MAX:
            del _recent[: len(_recent) - _RECENT_MAX]
    if _sink is not None:
        try:
            _sink(payload)
        except Exception:  # noqa: BLE001
            pass


def recent_events(limit: int = 20) -> list[dict]:
    with _lock:
        return list(_recent[-limit:])


def _announce(ann: Announcement | None, kind: str) -> str | None:
    """Push a state-engine announcement to the UI and return its text."""
    if ann is None or not getattr(ann, "text", ""):
        return None
    _publish({
        "kind": kind,
        "signal": getattr(ann.signal, "value", str(ann.signal)),
        "text": ann.text,
        "state": getattr(ann.state, "value", str(ann.state)),
        "confidence": ann.confidence,
        "emoji": ann.emoji,
    })
    return ann.text


# ---------------------------------------------------------------------------
# Error intelligence
# ---------------------------------------------------------------------------
def explain_error(raw_text: str, language: str | None = None, record: bool = True) -> dict:
    """Classify one error blob.

    Returns a plain dict (JSON-safe, so REST can return it directly):
        {matched, needs_llm, text, level, category, label,
         repeat_count, total_count, serious}

    `needs_llm=True` means the knowledge base had no pattern for it and the
    caller should ask a model — this module never makes that call itself.
    """
    blank = {
        "matched": False, "needs_llm": True, "text": "",
        "id": "", "label": "", "level": "", "category": "", "emoji": "❔",
        "language": "", "explanation": "", "confidence": 0.0,
        "repeat_count": 0, "total_count": 0, "serious": False,
    }
    if not (raw_text or "").strip():
        return {**blank, "needs_llm": False}
    try:
        resp = get_error_engine().process(
            raw_text, language=language, personality=_personality(), record=record
        )
    except Exception as e:  # noqa: BLE001
        print(f"[V3] explain_error failed: {e}")
        return blank

    c = resp.classification
    # Level/Category are IntEnums — send the NAME, not the int, so the UI can
    # label rows without carrying a copy of the enum table.
    out = {
        "matched": bool(c.matched),
        "needs_llm": bool(resp.needs_llm),
        "text": resp.spoken_text,
        "id": c.entry_id or "",
        "label": c.label or "",
        "level": c.level.name if c.level is not None else "",
        "category": c.category.name if c.category is not None else "",
        "emoji": c.emoji,
        "language": c.language or "",
        "explanation": c.explanation or "",
        "confidence": round(float(c.confidence), 2),
        "repeat_count": resp.repeat_count,
        "total_count": resp.total_count,
        "serious": bool(resp.serious),
    }
    if out["matched"] and record:
        _publish({"kind": "error", **out})
    return out


def _screen_language() -> str | None:
    """The language currently on screen, for the classifier's `language` arg.

    The knowledge base has been language-aware since it was built, but nothing
    ever passed this — so a C++ error could be matched against a Python
    pattern. The screen knows; ask it.
    """
    try:
        from core.brain import get_context
        from core.code_language import detect_language
        return detect_language(get_context())
    except Exception:  # noqa: BLE001
        return None


def scan_user_text(text: str) -> dict | None:
    """Called from the chat path when the user pastes something.

    Only fires on text that actually looks like an error dump, so ordinary
    questions never touch the tracker. Returns the classification dict when it
    matched (so brain.py can fold a hint into the prompt), else None.
    """
    if not _looks_like_error(text):
        return None
    # Prefer the language visible in the paste itself; fall back to the screen.
    result = explain_error(text, language=_screen_language(), record=True)
    if not result.get("matched"):
        return None
    try:
        get_state_engine(_personality()).on_errors(1)
    except Exception:  # noqa: BLE001
        pass
    return result


_ERROR_MARKERS = (
    "traceback (most recent call last)",
    "syntaxerror", "typeerror", "valueerror", "nameerror", "keyerror",
    "attributeerror", "indexerror", "importerror", "modulenotfounderror",
    "indentationerror", "zerodivisionerror", "recursionerror",
    "referenceerror", "segmentation fault", "null pointer",
    "cannot read propert", "is not defined", "unhandled exception",
    "expected ';'", "undefined reference to", "error ts",
)


def _looks_like_error(text: str) -> bool:
    """Cheap pre-filter. The knowledge base does the real work; this only
    stops every chat message from being run through it."""
    if not text or len(text) < 8:
        return False
    low = text.lower()
    return any(m in low for m in _ERROR_MARKERS)


def mistakes_today() -> list[dict]:
    try:
        return get_error_engine().todays_mistakes()
    except Exception as e:  # noqa: BLE001
        print(f"[V3] mistakes_today failed: {e}")
        return []


def trends(window_days: int = 7) -> list[dict]:
    try:
        return get_error_engine().trends(window_days)
    except Exception as e:  # noqa: BLE001
        print(f"[V3] trends failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Developer state
# ---------------------------------------------------------------------------
_session_started = False


def start_session() -> None:
    """Mark the beginning of a coding session (called once at server boot).

    This matters more than it looks. SessionMetrics defaults `session_start`
    to 0.0, and the engine only auto-starts on an *event* — so a read-only
    call like session_summary() before any event measured the session from
    the Unix epoch and reported ~56 years of uptime. Starting explicitly at
    boot gives every read a sane baseline.
    """
    global _session_started
    try:
        get_state_engine(_personality()).start()
        _session_started = True
    except Exception as e:  # noqa: BLE001
        print(f"[V3] start_session failed: {e}")


def session() -> dict:
    try:
        if not _session_started:
            start_session()
        return get_state_engine(_personality()).session_summary()
    except Exception as e:  # noqa: BLE001
        print(f"[V3] session failed: {e}")
        return {}


def note_activity(lines_added: int = 0) -> str | None:
    try:
        eng = get_state_engine(_personality())
        return _announce(eng.on_activity(lines_added=lines_added), "activity")
    except Exception:  # noqa: BLE001
        return None


def report_build(success: bool) -> str | None:
    try:
        eng = get_state_engine(_personality())
        return _announce(eng.on_build(success=success), "build")
    except Exception:  # noqa: BLE001
        return None


def report_errors(count: int) -> str | None:
    try:
        eng = get_state_engine(_personality())
        return _announce(eng.on_errors(count=count), "errors")
    except Exception:  # noqa: BLE001
        return None


def tick() -> str | None:
    """Periodic heartbeat from the proactive loop — drives flow/fatigue."""
    try:
        eng = get_state_engine(_personality())
        return _announce(eng.tick(), "tick")
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Screen observation (called from the proactive watch loop)
# ---------------------------------------------------------------------------
_last_error_sig: str = ""


def observe_screen(ctx: dict[str, Any]) -> str | None:
    """Turn one screen-context snapshot into engine events.

    Uses the existing binary detector (modules/error_detector) as the gauge —
    it already knows how to read a VS Code problems bar and a terminal tail —
    and layers the V3 classifier on top of the raw text when it reports errors.

    Returns a line worth speaking, or None (the common, intended case).
    """
    global _last_error_sig
    try:
        from modules.error_detector import ErrorState, detect_error_state
    except Exception:  # noqa: BLE001
        return None

    try:
        visible = (ctx.get("text") or ctx.get("visible_text") or "")[:6000]
        terminal = (ctx.get("terminal") or ctx.get("terminal_text") or "")[:6000]
        if not visible and not terminal:
            return None

        result = detect_error_state(visible_text=visible, terminal_text=terminal)

        if result.state is ErrorState.CLEAN:
            _last_error_sig = ""
            # A clean board is what triggers bug-killer / celebration lines.
            return report_errors(0)

        if result.state is ErrorState.HAS_ERRORS:
            count = result.error_count if result.error_count is not None else 1
            spoken = report_errors(count)

            # Only classify a *new* error episode — re-reading the same red
            # squiggle every 30 seconds must not inflate the mistake stats.
            sig = f"{result.reason}|{count}"
            if sig != _last_error_sig:
                _last_error_sig = sig
                blob = terminal or visible
                lang = None
                try:
                    from core.code_language import detect_language
                    lang = detect_language(ctx)
                except Exception:  # noqa: BLE001
                    pass
                info = explain_error(blob, language=lang, record=True)
                if info.get("matched") and info.get("text"):
                    return info["text"]
            return spoken
    except Exception as e:  # noqa: BLE001
        print(f"[V3] observe_screen failed: {e}")
    return None


# ---------------------------------------------------------------------------
# One-shot snapshot for the UI
# ---------------------------------------------------------------------------
def snapshot() -> dict:
    return {
        "session": session(),
        "mistakes": mistakes_today(),
        "trends": trends(),
        "events": recent_events(),
        "personality": _personality(),
    }
