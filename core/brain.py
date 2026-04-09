import time
from core.personality import INTENT_PROMPT, VERIFY_PROMPT, ANTICIPATE_PROMPT
from core.ai_router import call_claude, route
from memory import store
from modules.csv_handler import check_csv
from modules.command_handler import handle_command
# stores last screen context
_last_context = {
    "app": "unknown",
    "visible_text": "",
    "clipboard": ""
}

# conversation history for memory within session
_history = []


def update_context(ctx: dict):
    global _last_context
    _last_context = ctx


def get_context() -> dict:
    return _last_context


def classify_intent(query: str) -> str:
    prompt = INTENT_PROMPT.format(
        query=query,
        app=_last_context["app"],
        screen=_last_context["visible_text"][:300]
    )
    intent = call_claude(prompt).strip().upper()

    # safety check — if Claude returns something unexpected
    valid = ["CASUAL", "CODING", "SAVE", "REMINDER", "SEARCH", "COMMAND", "RECALL"]
    if intent not in valid:
        intent = "CASUAL"

    return intent


def verify_answer(query: str, answer: str) -> str:
    prompt = VERIFY_PROMPT.format(query=query, answer=answer)
    result = call_claude(prompt).strip()

    if result.startswith("VERIFIED:"):
        return result.replace("VERIFIED:", "").strip()
    elif result.startswith("IMPROVED:"):
        return result.replace("IMPROVED:", "").strip()
    else:
        return answer  # fallback to original


def anticipate(answer: str) -> str | None:
    prompt = ANTICIPATE_PROMPT.format(
        answer=answer,
        app=_last_context["app"]
    )
    result = call_claude(prompt).strip()
    if result == "NONE" or not result:
        return None
    return result


def build_context_prompt(query: str) -> str:
    history_text = ""
    if _history:
        last = _history[-3:]  # last 3 exchanges only
        history_text = "\n".join([f"{h['role']}: {h['text']}" for h in last])

    return f"""
User's current app: {_last_context['app']}
Screen content: {_last_context['visible_text'][:400]}
Clipboard: {_last_context['clipboard'][:200]}

Recent conversation:
{history_text}

User asks: {query}
"""


def process(query: str) -> str:
    print(f"\n[AURA] Processing: '{query}'")

    # step 0 — check CSV first (instant, no AI needed)
    csv_response = check_csv(query)
    if csv_response:
        print(f"[AURA] CSV match found")
        store.save_conversation("user", query)
        store.save_conversation("aura", csv_response)
        return csv_response

    # step 0b — check commands
    cmd_response = handle_command(query)
    if cmd_response:
        print(f"[AURA] Command handled")
        store.save_conversation("user", query)
        store.save_conversation("aura", cmd_response)
        return cmd_response

    # step 1 — classify intent
    intent = classify_intent(query)
    # step 1 — classify intent
    intent = classify_intent(query)
    print(f"[AURA] Intent detected: {intent}")

    # step 2 — build full context prompt
    full_prompt = build_context_prompt(query)

    # step 3 — route to right AI
    print(f"[AURA] Routing to AI...")
    answer = route(intent, full_prompt)

    if answer.startswith("ERROR") or answer == "CONNECTION_ERROR":
        return "I'm having trouble connecting right now. Please check your API key."

    if answer == "RATE_LIMIT":
        return "I've hit my rate limit. Give me a moment."

    # step 4 — donna verify (disabled for speed)
    final_answer = answer

    # step 5 — anticipate follow-up
    follow_up = anticipate(final_answer)

    # step 6 — save to session history
    _history.append({"role": "user", "text": query})
    _history.append({"role": "aura", "text": final_answer})

    # step 7 — save to persistent memory
    store.save_conversation("user", query)
    store.save_conversation("aura", final_answer)

    # attach follow-up suggestion if exists
    if follow_up:
        final_answer += f"\n\n[You might also want to know: {follow_up}]"

    return final_answer