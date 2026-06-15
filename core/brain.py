import datetime
import re
import time
from core.ai_router import call_claude, route, route_streaming
from core.thinking import think
from memory import store
from modules.csv_handler import check_csv
from modules.command_handler import handle_command
from modules.speech_planner import plan, debug as plan_debug
import modules.voice_output as tts
from core.personality import (INTENT_PROMPT, VERIFY_PROMPT, ANTICIPATE_PROMPT, SHOULD_RESPOND_PROMPT, OUTPUT_GUARD_PROMPT)

DEBUG_SPEECH = True

_last_context = {
    "app": "unknown",
    "visible_text": "",
    "clipboard": ""
}
_history = []

def update_context(ctx: dict):
    global _last_context
    _last_context = ctx

def get_context() -> dict:
    return _last_context

def speak_response(text: str, mode: str = "CHAT"):
    from modules.response_mode import classify_mode, get_code_reply, get_long_reply
    if mode == "CODE":
        reply = get_code_reply()
        chunks = plan(reply, mode="COMMAND")
        if DEBUG_SPEECH:
            print(plan_debug(reply, "COMMAND"))
        tts.speak_chunks(chunks)
        return
    if mode == "LONG":
        reply = get_long_reply(text)
        chunks = plan(reply, mode="CHAT")
        if DEBUG_SPEECH:
            print(plan_debug(reply, "CHAT"))
        tts.speak_chunks(chunks)
        return
    chunks = plan(text, mode)
    if DEBUG_SPEECH:
        print(plan_debug(text, mode))
    tts.speak_chunks(chunks)

def guard_output(response: str) -> str:
    response = response.strip().strip('"').strip("'").strip()
    # Additional pattern catches for stubborn leftovers
    if any(x in response for x in ["User is", "User asks", "AURA:", "Current app"]):
        print("[AURA] guard_output: stripping leaked context")
        response = re.sub(r"(User is .+?[,\.])", "", response, flags=re.IGNORECASE)
        response = re.sub(r"(User asks .+?[,\.])", "", response, flags=re.IGNORECASE)
        response = re.sub(r"(Current app .+?[,\.])", "", response, flags=re.IGNORECASE)
        response = re.sub(r"(AURA:?\s*)", "", response, flags=re.IGNORECASE)
    sentences = [s.strip() for s in response.split('.') if s.strip()]
    if len(sentences) > 2:
        response = ". ".join(sentences[:2]) + "."
    return response

def classify_intent(query: str) -> str:
    prompt = INTENT_PROMPT.format(
        query=query,
        app=_last_context["app"],
        screen=_last_context["visible_text"][:300]
    )
    intent = call_claude(prompt).strip().upper()
    valid = ["CASUAL", "CODING", "SAVE", "REMINDER", "SEARCH", "COMMAND", "RECALL"]
    return intent if intent in valid else "CASUAL"

def build_context_prompt(query: str, intent: str, thought_context: str) -> str:
    history_text = ""
    if _history:
        last = _history[-3:]
        history_text = "\n".join([f"{h['role']}: {h['text']}" for h in last])

    thought_section = f"\nContext: {thought_context}" if thought_context else ""

    return f"""Recent conversation:
{history_text}
{thought_section}

{query}"""

def anticipate(answer: str) -> str | None:
    prompt = ANTICIPATE_PROMPT.format(
        answer=answer,
        app=_last_context["app"]
    )
    result = call_claude(prompt).strip()
    return None if (result == "NONE" or not result) else result

def process(query: str) -> str:
    print(f"\n[AURA] Processing: '{query}'")
    query_lower = query.lower()

    if any(w in query_lower for w in ["add task", "new task", "i need to", "todo", "add a task", "remind me to"]):
        from modules.tasks import handle_add_task
        result = handle_add_task(query)
        store.save_conversation("user", query)
        store.save_conversation("aura", result)
        speak_response(result, "COMMAND")
        return result

    if any(w in query_lower for w in ["done with", "completed", "finished", "mark done"]):
        from modules.tasks import handle_complete_task
        result = handle_complete_task(query)
        store.save_conversation("user", query)
        store.save_conversation("aura", result)
        speak_response(result, "COMMAND")
        return result

    if any(w in query_lower for w in ["remove task", "delete task", "cancel task"]):
        from modules.tasks import handle_remove_task
        result = handle_remove_task(query)
        store.save_conversation("user", query)
        store.save_conversation("aura", result)
        speak_response(result, "COMMAND")
        return result

    # TIER 1 — instant, no AI
    csv_response = check_csv(query)
    if csv_response:
        print("[AURA] CSV match")
        store.save_conversation("user", query)
        store.save_conversation("aura", csv_response)
        return csv_response

    cmd_response = handle_command(query)
    if cmd_response:
        print("[AURA] Command handled")
        store.save_conversation("user", query)
        store.save_conversation("aura", cmd_response)
        return cmd_response

    if any(p in query.lower() for p in ["eurusd", "gbpusd", "usdjpy", "eur/usd", "gbp/usd", "gold"]):
        from modules.forex_report import get_quick_price
        result = get_quick_price(query.lower())
        store.save_conversation("user", query)
        store.save_conversation("aura", result)
        return result

    # TIER 2 — intent routing
    intent = classify_intent(query)
    print(f"[AURA] Intent: {intent}")

    if intent == "RECALL":
        from modules.knowledge import recall
        query_words = query.lower().replace("what did i save about", "").strip()
        result = recall(query_words)
        store.save_conversation("user", query)
        store.save_conversation("aura", result)
        return result

    if intent == "SAVE":
        from modules.knowledge import save_from_clipboard
        result = save_from_clipboard()
        store.save_conversation("user", query)
        store.save_conversation("aura", result)
        return result

    # TIER 3 — LLM
    full_prompt = build_context_prompt(query, intent, thought_context)
    print("[AURA] Routing to AI...")
    answer = route(intent, full_prompt)

    if answer.startswith("ERROR") or answer == "CONNECTION_ERROR":
        return "Connection trouble — one sec."

    if answer == "RATE_LIMIT":
        return "Hit my rate limit — give me a moment."

    final_answer = guard_output(answer)
    post_think(query, final_answer, intent)

    # Classify mode (still needed for UI to know how to speak, maybe pass back via tuple? We'll keep simple)
    # Not speaking here, so mode classification not needed inside process for speech.
    # We can simply return the text; UI can speak in CHAT mode always, or we can return mode too.
    # For simplicity, we'll return just the text, UI speaks as CHAT.
    # Anticipate follow‑up
    follow_up = anticipate(final_answer)
    if follow_up:
        final_answer += f" Also — {follow_up}"

    # Save to memory
    _history.append({"role": "user", "text": query})
    _history.append({"role": "aura", "text": final_answer})
    store.save_conversation("user", query)
    store.save_conversation("aura", final_answer)
    return final_answer


def process_streaming(query: str, on_chunk=None) -> str:
    print(f"\n[AURA] Streaming: '{query}'")
    query_lower = query.lower()

    if any(w in query_lower for w in ["add task", "new task", "i need to", "todo", "add a task", "remind me to"]):
        from modules.tasks import handle_add_task
        result = handle_add_task(query)
        store.save_conversation("user", query)
        store.save_conversation("aura", result)
        if on_chunk:
            on_chunk(result)
        return result

    if any(w in query_lower for w in ["done with", "completed", "finished", "mark done"]):
        from modules.tasks import handle_complete_task
        result = handle_complete_task(query)
        store.save_conversation("user", query)
        store.save_conversation("aura", result)
        if on_chunk:
            on_chunk(result)
        return result

    if any(w in query_lower for w in ["remove task", "delete task", "cancel task"]):
        from modules.tasks import handle_remove_task
        result = handle_remove_task(query)
        store.save_conversation("user", query)
        store.save_conversation("aura", result)
        if on_chunk:
            on_chunk(result)
        return result

    instant_response = check_csv(query) or handle_command(query)
    if instant_response:
        store.save_conversation("user", query)
        store.save_conversation("aura", instant_response)
        if on_chunk:
            on_chunk(instant_response)
        return instant_response

    if any(p in query_lower for p in ["eurusd", "gbpusd", "usdjpy", "eur/usd", "gbp/usd", "gold"]):
        from modules.forex_report import get_quick_price
        result = get_quick_price(query_lower)
        store.save_conversation("user", query)
        store.save_conversation("aura", result)
        if on_chunk:
            on_chunk(result)
        return result

    intent = classify_intent(query)
    # thinking layer
    from core.thinking import think, post_think
    thought_context = think(query, intent, _last_context, _history)

    full_prompt = build_context_prompt(query, intent, thought_context)

    if intent in {"RECALL", "SAVE"}:
        result = process(query)
        if on_chunk:
            on_chunk(result)
        return result

    from core.thinking import think, post_think
    thought_context = think(query, intent, _last_context, _history)
    full_prompt = build_context_prompt(query, intent, thought_context)
    chunks = []
    for chunk in route_streaming(intent, full_prompt):
        chunks.append(chunk)
        if on_chunk and chunk not in {"CONNECTION_ERROR", "RATE_LIMIT"}:
            on_chunk(chunk)

    answer = "".join(chunks).strip()
    if answer.startswith("ERROR") or answer == "CONNECTION_ERROR":
        return "Connection trouble — one sec."
    if answer == "RATE_LIMIT":
        return "Hit my rate limit — give me a moment."

    final_answer = guard_output(answer)
    post_think(query, final_answer, intent)
    post_think(query, final_answer, intent)
    _history.append({"role": "user", "text": query})
    _history.append({"role": "aura", "text": final_answer})
    store.save_conversation("user", query)
    store.save_conversation("aura", final_answer)
    return final_answer


def should_respond(text: str) -> bool:
    if check_csv(text):
        return True
    if handle_command(text):
        return True
    prompt = SHOULD_RESPOND_PROMPT.format(text=text)
    try:
        import ollama
        response = ollama.chat(
            model="phi3",
            messages=[{"role": "user", "content": prompt}]
        )
        return "YES" in response['message']['content'].strip().upper()
    except:
        return True

def start_proactive(speak_fn=None, on_suggestion_fn=None):
    """Start the Donna-style proactive loop."""
    if speak_fn is None:
        def speak_fn(text):
            speak_response(text, mode="CHAT")
    try:
        import modules.proactive as proactive
        proactive.start_proactive_loop(
            speak_fn=speak_fn,
            on_suggestion_fn=on_suggestion_fn
        )
        print("[AURA] Proactive module started (Donna is watching)")
    except Exception as e:
        print(f"[AURA] Proactive start error: {e}")
        
#use groq for chats