# core/thinking.py
import json
import datetime
from core.ai_router import call_claude
from memory import store

# ── Working Memory ─────────────────────────────────────────────────────────────

def load_working_memory() -> dict:
    try:
        result = store.get_working_memory()
        return result if result else _empty_memory()
    except:
        return _empty_memory()

def _empty_memory() -> dict:
    return {
        "current_focus": None,
        "user_mood": "neutral",
        "open_questions": [],
        "last_action": None,
        "confidence": 5,
        "topics_today": [],
        "updated_at": None
    }

def save_working_memory(mem: dict):
    mem["updated_at"] = datetime.datetime.now().isoformat()
    try:
        store.save_working_memory(json.dumps(mem))
    except:
        pass


# ── Complexity classifier ──────────────────────────────────────────────────────

SIMPLE_INTENTS = {"CASUAL", "COMMAND", "SAVE", "REMINDER"}
COMPLEX_INTENTS = {"CODING", "SEARCH", "RECALL"}

SIMPLE_PATTERNS = [
    "hey", "hi", "hello", "thanks", "ok", "okay", "yes", "no",
    "what time", "open ", "close ", "remind me", "add task"
]

def _needs_deep_thinking(query: str, intent: str) -> bool:
    """Decide if this query needs full reasoning or lightweight injection."""
    q = query.lower().strip()

    # always lightweight for simple patterns
    if any(q.startswith(p) for p in SIMPLE_PATTERNS):
        return False

    # intent-based
    if intent in SIMPLE_INTENTS:
        return False

    if intent in COMPLEX_INTENTS:
        return True

    # length heuristic — short = simple
    if len(q.split()) <= 4:
        return False

    # question words that imply reasoning needed
    reasoning_signals = ["how", "why", "explain", "help me", "what should", "design", "build", "fix", "debug", "plan"]
    if any(s in q for s in reasoning_signals):
        return True

    return False


# ── Lightweight thinking ───────────────────────────────────────────────────────

def lightweight_think(query: str, intent: str, context: dict, memory: dict, history: list) -> str:
    """
    Fast path — just builds a rich context string to inject into the prompt.
    No extra LLM call. Sub-millisecond.
    """
    parts = []

    if memory.get("current_focus"):
        parts.append(f"User is currently focused on: {memory['current_focus']}.")

    if memory.get("user_mood") and memory["user_mood"] != "neutral":
        parts.append(f"User mood: {memory['user_mood']}.")

    if memory.get("open_questions"):
        q = memory["open_questions"][-1]
        parts.append(f"Unresolved from before: {q}.")

    if context.get("app") and context["app"] != "unknown":
        parts.append(f"Currently on: {context['app']}.")

    if history:
        last = history[-1]
        parts.append(f"Last exchange: {last['role']} said '{last['text'][:80]}'.")

    return " ".join(parts) if parts else ""


# ── Deep thinking ──────────────────────────────────────────────────────────────

DEEP_THINK_PROMPT = """
You are AURA's internal reasoning engine. Think silently before answering.

User said: "{query}"
Intent detected: {intent}
Current app: {app}
Recent history: {history}
Working memory: {memory}

Think through:
1. What does the user ACTUALLY need (not just what they said)?
2. What context from memory/screen is relevant?
3. Is there an open question from before that this connects to?
4. What's the ideal response strategy — direct answer, clarifying question, or action?
5. What tone fits right now?

Reply ONLY with a JSON object, no markdown, no explanation:
{{
  "real_need": "one sentence",
  "relevant_context": "one sentence or empty string",
  "strategy": "direct_answer | ask_clarify | take_action",
  "tone": "casual | focused | supportive | sharp",
  "updated_focus": "what user is working on",
  "updated_mood": "neutral | focused | frustrated | curious | tired",
  "open_question": "any unresolved thread to remember, or empty string"
}}
"""

def deep_think(query: str, intent: str, context: dict, memory: dict, history: list) -> dict:
    """
    Full reasoning pass — one extra LLM call, returns structured thought.
    Used for complex queries only.
    """
    history_text = " | ".join([
        f"{h['role']}: {h['text'][:60]}" for h in history[-4:]
    ]) if history else "none"

    prompt = DEEP_THINK_PROMPT.format(
        query=query,
        intent=intent,
        app=context.get("app", "unknown"),
        history=history_text,
        memory=json.dumps(memory)
    )

    try:
        raw = call_claude(prompt).strip()
        # strip markdown if model wraps it
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"[AURA Thinking] Deep think parse error: {e}")
        return {}


# ── Main entry point ───────────────────────────────────────────────────────────

def think(query: str, intent: str, context: dict, history: list) -> str:
    """
    Called before every LLM response.
    Returns a context string to prepend to the prompt.
    Also updates working memory silently.
    """
    memory = load_working_memory()

    if _needs_deep_thinking(query, intent):
        print("[AURA] Deep thinking...")
        thought = deep_think(query, intent, context, memory, history)

        # update working memory from thought
        if thought:
            if thought.get("updated_focus"):
                memory["current_focus"] = thought["updated_focus"]
            if thought.get("updated_mood"):
                memory["user_mood"] = thought["updated_mood"]
            if thought.get("open_question"):
                oq = thought["open_question"]
                if oq and oq not in memory["open_questions"]:
                    memory["open_questions"].append(oq)
                    memory["open_questions"] = memory["open_questions"][-3:]  # keep last 3
            if thought.get("updated_focus") and thought["updated_focus"] not in memory["topics_today"]:
                memory["topics_today"].append(thought["updated_focus"])
                memory["topics_today"] = memory["topics_today"][-10:]

            save_working_memory(memory)

            # build context string from deep thought
            parts = []
            if thought.get("real_need"):
                parts.append(f"What user actually needs: {thought['real_need']}.")
            if thought.get("relevant_context"):
                parts.append(thought["relevant_context"])
            if thought.get("tone"):
                parts.append(f"Tone: {thought['tone']}.")
            return " ".join(parts)

    else:
        print("[AURA] Lightweight thinking...")
        ctx_string = lightweight_think(query, intent, context, memory, history)

        # lightweight memory update
        if context.get("app") and context["app"] != "unknown":
            memory["current_focus"] = context["app"]
        memory["last_action"] = f"responded to: {query[:60]}"
        save_working_memory(memory)

        return ctx_string


# ── Post-think (called after response is sent) ─────────────────────────────────

def post_think(query: str, response: str, intent: str):
    """
    Silently update memory after responding.
    No LLM call — pure logic.
    """
    memory = load_working_memory()

    # mood inference from query
    frustration_words = ["still", "again", "why", "not working", "broken", "ugh", "wtf"]
    tired_words = ["tired", "exhausted", "done for today", "later"]
    curious_words = ["what if", "how about", "can we", "idea"]

    q = query.lower()
    if any(w in q for w in frustration_words):
        memory["user_mood"] = "frustrated"
    elif any(w in q for w in tired_words):
        memory["user_mood"] = "tired"
    elif any(w in q for w in curious_words):
        memory["user_mood"] = "curious"
    elif intent == "CODING":
        memory["user_mood"] = "focused"
    else:
        memory["user_mood"] = "neutral"

    memory["last_action"] = response[:80]
    save_working_memory(memory)