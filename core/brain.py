import time
from core.personality import (
    INTENT_PROMPT, VERIFY_PROMPT, ANTICIPATE_PROMPT,
    SHOULD_RESPOND_PROMPT, OUTPUT_GUARD_PROMPT
)
from core.ai_router import call_claude, route
from memory import store
from modules.csv_handler import check_csv
from modules.command_handler import handle_command
from modules.screen_reader import get_screen_context
from modules.speech_planner import plan, debug as plan_debug
import modules.voice_output as tts

DEBUG_SPEECH = True

_last_context = {
    "app": "unknown",
    "visible_text": "",
    "clipboard": ""
}

_history = []


# ── Context ───────────────────────────────────────────────────────────────────
def guard_output(response: str) -> str:
    # strip surrounding quotes immediately
    response = response.strip().strip('"').strip("'").strip()
    

def update_context(ctx: dict):
    global _last_context
    _last_context = ctx


def get_context() -> dict:
    return _last_context


# ── Speech ────────────────────────────────────────────────────────────────────

def speak_response(text: str, mode: str = "CHAT"):
    from modules.response_mode import (
        classify_mode, get_code_reply, get_long_reply
    )

    # code mode — never read code
    if mode == "CODE":
        reply = get_code_reply()
        chunks = plan(reply, mode="COMMAND")
        if DEBUG_SPEECH:
            print(plan_debug(reply, "COMMAND"))
        tts.speak_chunks(chunks)
        return

    # long mode — offer summary
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



# ── Output guard ──────────────────────────────────────────────────────────────

def guard_output(response: str) -> str:
    """
    Filter LLM output before it reaches voice.
    Kills markdown, long responses, meta text leakage.
    Fast rule-based check first, LLM cleanup only if needed.
    """
    # rule-based fast checks
    red_flags = [
        "User asks:",
        "Screen content:",
        "Current app:",
        "AURA:",
        "```",
        "**",
        "##",
        "Certainly!",
        "Of course!",
        "Great question!",
        "As an AI",
    ]

    needs_fix = any(flag in response for flag in red_flags)

    # also fix if too long (over 3 sentences)
    sentences = [s.strip() for s in response.split('.') if s.strip()]
    if len(sentences) > 3:
        needs_fix = True

    if not needs_fix:
        return response

    # LLM cleanup — only when actually needed
    print("[AURA] Output guard triggered — cleaning response")
    prompt = OUTPUT_GUARD_PROMPT.format(response=response)
    result = call_claude(prompt).strip()

    if result.startswith("OK:"):
        return result.replace("OK:", "").strip()
    elif result.startswith("FIX:"):
        return result.replace("FIX:", "").strip()

    # fallback — truncate to first 2 sentences
    return ". ".join(sentences[:2]) + "."


# ── Intent ────────────────────────────────────────────────────────────────────

def classify_intent(query: str) -> str:
    prompt = INTENT_PROMPT.format(
        query=query,
        app=_last_context["app"],
        screen=_last_context["visible_text"][:300]
    )
    intent = call_claude(prompt).strip().upper()
    valid = ["CASUAL", "CODING", "SAVE", "REMINDER", "SEARCH", "COMMAND", "RECALL"]
    return intent if intent in valid else "CASUAL"


# ── Context builder ───────────────────────────────────────────────────────────

def build_context_prompt(query: str) -> str:
    history_text = ""
    if _history:
        last = _history[-3:]
        history_text = "\n".join([f"{h['role']}: {h['text']}" for h in last])

    return f"""
Recent conversation:
{history_text}

User asks: {query}

Rules: Max 2 sentences. No quotes. Talk like a friend. Never mention apps or screen content.
"""
# ── Anticipate ────────────────────────────────────────────────────────────────

def anticipate(answer: str) -> str | None:
    prompt = ANTICIPATE_PROMPT.format(
        answer=answer,
        app=_last_context["app"]
    )
    result = call_claude(prompt).strip()
    return None if (result == "NONE" or not result) else result


# ── Main pipeline ─────────────────────────────────────────────────────────────

def process(query: str) -> str:
    print(f"\n[AURA] Processing: '{query}'")

    # ── TIER 1: instant — no AI needed ───────────────────────────────────────

    # CSV fast path
    csv_response = check_csv(query)
    if csv_response:
        print("[AURA] CSV match")
        store.save_conversation("user", query)
        store.save_conversation("aura", csv_response)
        speak_response(csv_response)
        return csv_response

    # command handler
    cmd_response = handle_command(query)
    if cmd_response:
        print("[AURA] Command handled")
        store.save_conversation("user", query)
        store.save_conversation("aura", cmd_response)
        speak_response(cmd_response)
        return cmd_response

    # forex quick price
    if any(p in query.lower() for p in ["eurusd", "gbpusd", "usdjpy", "eur/usd", "gbp/usd", "gold"]):
        from modules.forex_report import get_quick_price
        result = get_quick_price(query.lower())
        store.save_conversation("user", query)
        store.save_conversation("aura", result)
        speak_response(result)
        return result

    # ── TIER 2: intent routing ────────────────────────────────────────────────

    intent = classify_intent(query)
    print(f"[AURA] Intent: {intent}")

    # recall — search memory, no LLM needed
    if intent == "RECALL":
        from modules.knowledge import recall
        query_words = query.lower().replace("what did i save about", "").strip()
        result = recall(query_words)
        store.save_conversation("user", query)
        store.save_conversation("aura", result)
        speak_response(result)
        return result

    # ── TIER 3: LLM ──────────────────────────────────────────────────────────

    full_prompt = build_context_prompt(query)
    print("[AURA] Routing to AI...")
    answer = route(intent, full_prompt)

    # connection errors
    if answer.startswith("ERROR") or answer == "CONNECTION_ERROR":
        err = "I'm having trouble connecting right now."
        speak_response(err)
        return err

    if answer == "RATE_LIMIT":
        msg = "Hit my rate limit — give me a moment."
        speak_response(msg)
        return msg

    # ── output guard ──────────────────────────────────────────────────────────
    final_answer = guard_output(answer)
    from modules.response_mode import classify_mode
    mode = classify_mode(final_answer, intent)
    print(f"[AURA] Mode: {mode}")

    # speak with mode
    speak_response(final_answer, mode)
    return final_answer

    # ── anticipate ────────────────────────────────────────────────────────────
    follow_up = anticipate(final_answer)
    if follow_up:
        final_answer += f" Also — {follow_up}"

    # ── memory ────────────────────────────────────────────────────────────────
    _history.append({"role": "user", "text": query})
    _history.append({"role": "aura", "text": final_answer})
    store.save_conversation("user", query)
    store.save_conversation("aura", final_answer)

    # ── speak ─────────────────────────────────────────────────────────────────
    speak_response(final_answer)
    return final_answer


# ── Should respond filter ─────────────────────────────────────────────────────

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