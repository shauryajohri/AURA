# modules/session_memory.py
from memory import store
from core.ai_router import call_claude

def build_session_summary(history: list, last_app: str) -> dict:
    """Use LLM to summarize what user was doing this session"""
    if not history:
        return {"app": last_app, "summary": "nothing much", "topics": []}

    convo = "\n".join([f"{h['role']}: {h['text']}" for h in history[-10:]])

    prompt = f"""This is a conversation between a user and AURA (AI assistant).
Summarize in ONE sentence what the user was working on or doing.
Be specific. No filler words.

Conversation:
{convo}

Reply with ONLY the one-sentence summary. Nothing else."""

    summary = call_claude(prompt).strip()

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

    summary = last["summary"]
    return f"last time ({time_str}) you were {summary} — picking up where you left off?"