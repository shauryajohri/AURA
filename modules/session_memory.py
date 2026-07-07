# modules/session_memory.py
from memory import store
from core.ai_router import call_groq_raw

def build_session_summary(history: list, last_app: str) -> dict:
    """One human-style narrative sentence about the session — a friend's
    diary note, not a report. Greeting AND conversational recall read it."""
    if not history:
        return {"app": last_app, "summary": "nothing much", "topics": []}

    convo = "\n".join([f"{h['role']}: {h['text'][:300]}" for h in history[-10:]])

    prompt = f"""Conversation between a user and AURA this session:
{convo}

Write ONE natural sentence describing what happened — what they worked on,
how it went, and their mood if evident. Phrase it so it completes
"last time you were ..." (start with a verb-ing phrase, e.g.
"debugging the voice pipeline and mostly winning").
IMPORTANT: if a project, tool, or file is named (e.g. "AURA", "main.py"),
use that exact name — do NOT paraphrase it into a generic description.
Never say "The user". Reply with ONLY that sentence."""

    from core.ai_router import GROQ_MODEL_LIGHT
    summary = call_groq_raw(
        prompt,
        system="You write one warm, specific sentence. Nothing else.",
        max_tokens=60, temperature=0.5, model=GROQ_MODEL_LIGHT,
    ).strip()
    if summary in ("RATE_LIMIT", "CONNECTION_ERROR") or not summary:
        summary = "up to something, but it's hazy now"

    # extract topics
    topics = []
    keywords = ["metaverse", "unity", "python", "react", "bug", "project", "design",
                "database", "api", "forex", "task", "study", "code", "aura"]
    for word in keywords:
        if word in convo.lower():
            topics.append(word)

    return {
        "app": last_app,
        "summary": summary,
        "topics": topics[:5]
    }

def save_on_exit(history: list, last_app: str):
    """Call this when AURA is closing"""
    snapshot = build_session_summary(history, last_app)
    store.save_session_snapshot(
        app=snapshot["app"],
        summary=snapshot["summary"],
        topics=snapshot["topics"]
    )
    # Persist durable facts from this session so the NEXT launch greets with
    # specifics (e.g. "AURA") instead of a vague paraphrase. Heuristic-only —
    # no network needed at shutdown.
    try:
        from modules.fact_extractor import capture_heuristic
        for h in history:
            if h.get("role") == "user":
                capture_heuristic(h.get("text", ""))
    except Exception:
        pass

def get_greeting_with_memory() -> str | None:
    """On startup, return a Donna-style recall of last session"""
    last = store.get_last_session()
    if not last:
        return None
    # NOTE: previously this wiped the entire session_snapshots table on every
    # startup, which destroyed the memory feature after a single launch. We now
    # read only — snapshots persist and are pruned by save/rotation elsewhere.
    # parse how long ago
    import datetime
    try:
        then = datetime.datetime.fromisoformat(last["created_at"])
        diff = datetime.datetime.now() - then
        hours = int(diff.total_seconds() // 3600)
        if hours < 1:
            time_str = "earlier"
        elif hours < 24:
            time_str = f"{hours}h ago"
        else:
            days = diff.days
            time_str = f"{days} day{'s' if days > 1 else ''} ago"
    except:
        time_str = "last time"

    summary = (last["summary"] or "").strip()
    # older snapshots start with "The user was ..." — make it read naturally
    low = summary.lower()
    for prefix in ("the user was ", "the user is ", "user was ", "you were "):
        if low.startswith(prefix):
            summary = summary[len(prefix):]
            break
    if summary:
        summary = summary[0].lower() + summary[1:]
    return f"last time ({time_str}) you were {summary} — picking up where you left off?"