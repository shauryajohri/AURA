"""
core/curiosity_engine.py
-------------------------
AURA's Curiosity Engine. Runs on its own daemon thread, separate from
modules.proactive's 30s reactive loop. Where proactive reacts to "what's
on screen right now" (errors, stuck, idle), curiosity thinks slower and
looks for patterns, gaps, and connections across time.

Design constraints (deliberate):
- Every external dependency (core.brain, core.thinking, modules.proactive,
  modules.project_context, memory.store extras) is imported lazily and
  wrapped in try/except. If a module doesn't exist yet, or its function
  signature differs from what's guessed here, that signal source is
  skipped — the engine degrades, it never crashes the thread.
- Shares core.voice_gate with modules.proactive so the two loops don't
  talk over each other.
- Fires rarely. This is the whole point — it should feel like an
  occasional sharp observation, not another notification stream.
"""

import time
import threading
import re
from dataclasses import dataclass, field
from typing import Optional, Callable

from core.voice_gate import can_speak, mark_spoken, seconds_since_last_spoken

# ── Timing ────────────────────────────────────────────────────────────────────
THINK_INTERVAL          = 300   # 5 minutes between thinking cycles
CURIOSITY_COOLDOWN      = 480   # 8 minutes minimum between actually speaking
USER_SILENCE_REQUIRED   = 120   # don't interrupt if user messaged in last 2 min
CONFIDENCE_THRESHOLD    = 0.6
RESTART_PATTERN_WINDOW  = 60    # minutes, for pattern curiosity

_last_curiosity_time = 0.0
_last_fired_signature = ""


@dataclass
class CuriosityCandidate:
    kind: str                # "pattern" | "gap" | "insight"
    confidence: float
    message: str
    signature: str = ""      # used to avoid repeating the same observation


# ── Defensive accessors — every one of these can fail safely ─────────────────

def _safe_get_recent_conversations(limit: int = 30) -> list:
    try:
        from memory import store
        return store.get_recent_conversations(limit)
    except Exception as e:
        print(f"[Curiosity] conversations unavailable: {e}")
        return []


def _safe_count_recent_restarts() -> int:
    try:
        from memory import store
        if hasattr(store, "count_recent_restarts"):
            return store.count_recent_restarts(RESTART_PATTERN_WINDOW)
    except Exception as e:
        print(f"[Curiosity] restart-count unavailable: {e}")
    return 0


def _safe_get_working_memory() -> Optional[dict]:
    try:
        from memory import store
        if hasattr(store, "get_working_memory"):
            return store.get_working_memory()
    except Exception as e:
        print(f"[Curiosity] working memory unavailable: {e}")
    return None


def _safe_get_last_session() -> Optional[dict]:
    try:
        from memory import store
        if hasattr(store, "get_last_session"):
            return store.get_last_session()
    except Exception as e:
        print(f"[Curiosity] last session unavailable: {e}")
    return None


def _safe_get_context() -> dict:
    try:
        from core.brain import get_context
        return get_context() or {}
    except Exception as e:
        print(f"[Curiosity] brain context unavailable: {e}")
        return {}


def _safe_get_last_user_message_time() -> float:
    try:
        from core.brain import get_last_user_message_time
        return get_last_user_message_time()
    except Exception:
        return 0.0


def _safe_is_afk() -> bool:
    try:
        from modules.proactive import _is_user_afk
        return _is_user_afk()
    except Exception:
        return False  # if we can't tell, assume present rather than going silent forever


def _safe_get_app_lock() -> Optional[str]:
    try:
        from modules.proactive import get_app_lock
        return get_app_lock()
    except Exception:
        return None


def _safe_get_project_context(query: str) -> str:
    try:
        from modules.project_context import get_relevant_context
        return get_relevant_context(query) or ""
    except Exception:
        return ""


def _safe_call_groq(prompt: str) -> Optional[str]:
    """Tries call_groq first (current router), falls back to call_claude
    (older alias seen in brain.py), gives up cleanly otherwise."""
    try:
        from core.ai_router import call_groq
        result = call_groq(prompt, intent="CASUAL").strip()
        if result and result.upper() not in {"CONNECTION_ERROR", "RATE_LIMIT", ""}:
            return result
    except Exception:
        pass
    try:
        from core.ai_router import call_claude
        result = call_claude(prompt).strip()
        if result and result.upper() not in {"CONNECTION_ERROR", "RATE_LIMIT", ""}:
            return result
    except Exception as e:
        print(f"[Curiosity] LLM call unavailable: {e}")
    return None


# ── Curiosity type 1: PATTERN ─────────────────────────────────────────────────
# "you've restarted brain.py 4 times in the last hour"

RESTART_KEYWORDS = ["restart", "rerun", "crash", "crashed", "won't start", "keeps failing"]


def _detect_pattern() -> Optional[CuriosityCandidate]:
    conversations = _safe_get_recent_conversations(40)
    if not conversations:
        return None

    user_msgs = [m for role, m, _ in conversations if role == "user"]
    if len(user_msgs) < 4:
        return None

    hits = 0
    for msg in user_msgs:
        lower = msg.lower()
        if any(kw in lower for kw in RESTART_KEYWORDS):
            hits += 1

    restart_count = _safe_count_recent_restarts() or hits

    if restart_count < 3:
        return None

    ctx = _safe_get_context()
    task_hint = ctx.get("app", "this") if ctx else "this"

    prompt = (
        f"AURA noticed the user has hit restart/crash-style language about "
        f"{restart_count} times recently while working in {task_hint}. "
        "Write ONE short, dry, Donna-style line (max 2 sentences, no quotes) "
        "pointing out the pattern and offering to look at the root cause "
        "instead of the symptom. Don't invent specifics you don't have."
    )
    msg = _safe_call_groq(prompt)
    if not msg:
        msg = f"That's the {restart_count}th restart-ish thing recently — want to chase the actual root cause instead?"

    return CuriosityCandidate(
        kind="pattern",
        confidence=min(0.9, 0.5 + restart_count * 0.1),
        message=msg,
        signature=f"pattern:{task_hint}:{restart_count}",
    )


# ── Curiosity type 2: GAP ─────────────────────────────────────────────────────
# "proactive.py has no unit tests — want me to write some?"
# Deliberately conservative: low confidence, only fires on a strong, simple signal
# (a specific file name mentioned often with no nearby "test" mention), since the
# real project_context.py internals aren't visible from here.

FILE_MENTION_RE = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*\.py)\b")


def _detect_gap() -> Optional[CuriosityCandidate]:
    conversations = _safe_get_recent_conversations(40)
    if not conversations:
        return None

    mentioned_files = {}
    test_mentioned = False
    for role, msg, _ in conversations:
        if role != "user":
            continue
        lower = msg.lower()
        if "test" in lower or "unit test" in lower:
            test_mentioned = True
        for fname in FILE_MENTION_RE.findall(msg):
            mentioned_files[fname] = mentioned_files.get(fname, 0) + 1

    if not mentioned_files or test_mentioned:
        # either nothing to go on, or the user is already thinking about tests
        return None

    top_file, count = max(mentioned_files.items(), key=lambda kv: kv[1])
    if count < 3:
        return None

    project_ctx = _safe_get_project_context(top_file)

    prompt = (
        f"AURA noticed the user has been working in {top_file} repeatedly "
        f"({count} mentions recently) without mentioning tests for it. "
        + (f"Here is some relevant code context:\n{project_ctx[:600]}\n" if project_ctx else "")
        + "Write ONE short, dry, Donna-style line (max 2 sentences, no quotes) "
        "offering to write tests for it while they work on something else. "
        "Don't claim certainty about what's inside the file beyond what's given."
    )
    msg = _safe_call_groq(prompt)
    if not msg:
        msg = f"You've been in {top_file} a lot lately — want me to draft some tests for it while you keep going?"

    return CuriosityCandidate(
        kind="gap",
        confidence=0.55 + min(0.2, count * 0.03),
        message=msg,
        signature=f"gap:{top_file}",
    )


# ── Curiosity type 3: INSIGHT ─────────────────────────────────────────────────
# "last week you were stuck on the same memory bug — want to look at what changed?"

def _detect_insight() -> Optional[CuriosityCandidate]:
    last_session = _safe_get_last_session()
    if not last_session:
        return None

    ctx = _safe_get_context()
    current_app = (ctx.get("app") or "").lower()
    last_app = (last_session.get("app") or "").lower()

    if not current_app or not last_app:
        return None

    # crude but safe: same app/window context as last session, and topics overlap
    if last_app not in current_app and current_app not in last_app:
        return None

    last_topics = [t.strip() for t in last_session.get("topics", []) if t.strip()]
    if not last_topics:
        return None

    prompt = (
        f"AURA remembers the user was previously working on: {', '.join(last_topics[:5])} "
        f"(in {last_session.get('app', 'an app')}), and they're back in a similar context now "
        f"({ctx.get('app', 'same app')}). "
        "Write ONE short, warm-but-dry, Donna-style line (max 2 sentences, no quotes) "
        "connecting this session to that one and offering to pick it back up. "
        "Don't invent details beyond the topic list given."
    )
    msg = _safe_call_groq(prompt)
    if not msg:
        topic = last_topics[0]
        msg = f"You were on {topic} last time too — picking that back up, or starting fresh?"

    return CuriosityCandidate(
        kind="insight",
        confidence=0.65,
        message=msg,
        signature=f"insight:{last_app}:{last_topics[0] if last_topics else ''}",
    )


_DETECTORS: list[Callable[[], Optional[CuriosityCandidate]]] = [
    _detect_pattern,
    _detect_gap,
    _detect_insight,
]


# ── Decision ──────────────────────────────────────────────────────────────────
def _safe_is_attention_active() -> bool:
    try:
        from modules.attention_engine import get_engine as get_ae
        return get_ae().is_attention_active()
    except Exception:
        return False


def _should_think() -> bool:
    now = time.time()

    if _safe_is_afk():
        return False

    last_msg_time = _safe_get_last_user_message_time()
    if last_msg_time and (now - last_msg_time) < USER_SILENCE_REQUIRED:
        return False

    if (now - _last_curiosity_time) < CURIOSITY_COOLDOWN:
        return False

    if not can_speak():
        return False

    # BUG 2 FIX — same yield point proactive.py uses. Attention owns the
    # conversation while it's mid-utterance; curiosity waits its turn.
    if _safe_is_attention_active():
        return False

    locked_app = _safe_get_app_lock()
    if locked_app:
        # Respect focus mode — curiosity stays quiet while the user has
        # explicitly locked AURA onto watching one thing via proactive's
        # observation flow. Don't compete with that UX.
        return False

    return True
def think_once() -> Optional[CuriosityCandidate]:
    """Runs all detectors, returns the highest-confidence candidate above
    threshold, or None. Exposed standalone so it can be unit tested or
    triggered manually without spinning up the thread."""
    global _last_fired_signature

    best: Optional[CuriosityCandidate] = None
    for detector in _DETECTORS:
        try:
            candidate = detector()
        except Exception as e:
            print(f"[Curiosity] detector error: {e}")
            continue
        if candidate is None:
            continue
        if candidate.signature and candidate.signature == _last_fired_signature:
            continue  # don't repeat the exact same observation back to back
        if best is None or candidate.confidence > best.confidence:
            best = candidate

    if best and best.confidence >= CONFIDENCE_THRESHOLD:
        return best
    return None


# ── Loop ──────────────────────────────────────────────────────────────────────

def _loop(speak_fn, on_curiosity_fn=None):
    global _last_curiosity_time, _last_fired_signature
    print("[Curiosity] Loop started")

    while True:
        try:
            time.sleep(THINK_INTERVAL)

            if not _should_think():
                continue

            candidate = think_once()
            if not candidate:
                continue

            mark_spoken()
            _last_curiosity_time = time.time()
            _last_fired_signature = candidate.signature

            print(f"[Curiosity] ({candidate.kind}, conf={candidate.confidence:.2f}) {candidate.message}")
            if on_curiosity_fn:
                on_curiosity_fn(candidate.message)
            speak_fn(candidate.message)
            try:
                from modules.attention_engine import register_speech as _ae_register_speech
                _ae_register_speech()
            except Exception:
                pass

        except Exception as e:
            print(f"[Curiosity Error] {e}")


def start_curiosity_loop(speak_fn, on_curiosity_fn=None):
    """Start the curiosity engine on its own daemon thread.

    speak_fn: same signature as proactive's — speak_fn(text: str)
    on_curiosity_fn: optional callback, e.g. to push the line into the UI
                     before/while it's spoken (mirrors proactive's on_suggestion_fn)
    """
    t = threading.Thread(target=_loop, args=(speak_fn, on_curiosity_fn), daemon=True)
    t.start()
    return t