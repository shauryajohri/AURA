import datetime
import re
import time
from modules.proactive import set_app_lock, clear_app_lock, get_app_lock
from core.ai_router import call_claude, route, route_streaming, extract_code_block, call_classifier
from core.thinking import think, post_think
from memory import store
from modules.csv_handler import check_csv
from modules.command_handler import handle_command
from modules.speech_planner import plan, debug as plan_debug
import modules.voice_output as tts
from core.personality import (INTENT_PROMPT, ANTICIPATE_PROMPT, SHOULD_RESPOND_PROMPT)

DEBUG_SPEECH = True

_last_context = {
    "app": "unknown",
    "visible_text": "",
    "clipboard": ""
}
_history = []
_last_user_message_time = 0
_pending_observation = None


def get_last_user_message_time() -> float:
    return _last_user_message_time


def mark_user_active(text: str = ""):
    global _last_user_message_time
    _last_user_message_time = time.time()
    try:
        from modules.relationship_engine import get_engine
        get_engine().record_user_message()
    except Exception:
        pass
    try:
        from modules.proactive import record_user_activity
        record_user_activity()
    except Exception:
        pass
    try:
        from modules.attention_engine import get_engine as get_ae
        get_ae().record_user_message()
    except Exception:
        pass
    try:
        # Refill conversation energy on every real message, and honour explicit
        # "busy" / "I'm back" phrases by freezing/thawing the meter.
        from modules.conversation_energy import get_energy
        energy = get_energy()
        energy.record_interaction(meaningful=True)
        if text:
            energy.note_user_text(text)
    except Exception:
        pass
    # Durable-fact capture: turn stable statements ("its name is AURA",
    # "I'm learning DSA") into memory that survives past the chat window.
    try:
        if text:
            from modules.fact_extractor import capture as capture_facts
            capture_facts(text)
    except Exception:
        pass
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

def guard_output(response: str, max_sentences: int = 2) -> str:
    response = response.strip().strip('"').strip("'").strip()
    # Additional pattern catches for stubborn leftovers
    if any(x in response for x in ["User is", "User asks", "AURA:", "Current app"]):
        print("[AURA] guard_output: stripping leaked context")
        response = re.sub(r"(User is .+?[,\.])", "", response, flags=re.IGNORECASE)
        response = re.sub(r"(User asks .+?[,\.])", "", response, flags=re.IGNORECASE)
        response = re.sub(r"(Current app .+?[,\.])", "", response, flags=re.IGNORECASE)
        response = re.sub(r"(AURA:?\s*)", "", response, flags=re.IGNORECASE)
    sentences = [s.strip() for s in response.split('.') if s.strip()]
    if len(sentences) > max_sentences:
        response = ". ".join(sentences[:max_sentences]) + "."
    return response

def classify_intent(query: str) -> str:
    prompt = INTENT_PROMPT.format(
        query=query,
        app=_last_context["app"],
        screen=_last_context["visible_text"][:300]
    )
    intent = call_classifier(prompt)
    intent = re.sub(r"[^A-Z]", "", intent)  # strip punctuation, whitespace, etc.
    print(f"[AURA] Raw classifier output: '{intent}'")
    valid = ["CASUAL", "CODING", "SAVE", "REMINDER", "SEARCH", "COMMAND", "RECALL"]
    return intent if intent in valid else "CASUAL"

def conversational_recall(query: str) -> str:
    """Answer memory questions like a companion, not a filing cabinet.

    Old behavior: knowledge-table lookup with the whole sentence as key →
    'I couldn't find anything saved about <echo>'. Now: gather everything
    AURA actually knows (session snapshot, recent conversation, knowledge
    hits) and let the LLM answer naturally."""
    parts = []
    try:
        last = store.get_last_session()
        if last and last.get("summary"):
            parts.append(f"Last session: {last['summary']}")
    except Exception:
        pass
    try:
        convo = []
        for role, message, _ts in store.get_recent_conversations(12):
            text = (message or "").strip()
            if not text or "Execution Plan:" in text or text.startswith("Task:"):
                continue
            convo.append(f"{'User' if role == 'user' else 'AURA'}: {text[:300]}")
        if convo:
            parts.append("Recent conversation:\n" + "\n".join(convo[-10:]))
    except Exception:
        pass
    try:
        results = store.search_entries(query)
        if results:
            top = results[0]
            parts.append(f"Saved note '{top[0]}': {top[1] or top[4][:150]}")
    except Exception:
        pass
    try:
        facts = store.get_user_facts(limit=10)
        if facts:
            parts.append("Durable facts about them:\n" + "\n".join(f"- {f}" for f in facts))
    except Exception:
        pass

    if not parts:
        return "Honestly, that one's fuzzy — remind me what we were on?"

    from core.ai_router import call_groq_raw
    system = (
        "You are AURA, a sharp, warm AI companion. The user is asking what you "
        "remember. Answer naturally in 1-3 sentences, like a friend recalling "
        "it — specifics first. If what you know doesn't cover their question, "
        "say it's fuzzy and ask them to remind you. NEVER mention 'context', "
        "'database', 'saved entries', or that you were given information."
    )
    prompt = f'The user asks: "{query}"\n\nWhat you know:\n' + "\n\n".join(parts)
    result = call_groq_raw(prompt, system, max_tokens=200, temperature=0.6)
    if result in ("RATE_LIMIT", "CONNECTION_ERROR"):
        return "My memory's being slow — give me a second and ask again."
    return result


# Lines that must never be fed back as "context": compiled plan templates
# and the tell-tale junk from failed runs (feeding those back made the model
# echo garbage — seen live on 2026-07-06). Mirrors ui/app._CTX_JUNK.
_CTX_JUNK = (
    "Execution Plan:",
    "no specific code or implementation details",
    "hypothetical coding task",
    "I couldn't find",
    "Try saying the full app name",
    "Run this program to test the functions",
)


def _is_context_junk(text: str) -> bool:
    return text.startswith("Task:") or any(j in text for j in _CTX_JUNK)


def _recent_turns(max_turns: int = 8) -> str:
    """Recent conversation as labelled lines.

    Reads from the PERSISTED store, not the in-RAM `_history`. The store is
    the complete record — every branch (chat, RECALL, tasks, commands) calls
    `store.save_conversation`, and it survives restarts. This is what fixes
    the bug where AURA forgot things said one turn ago: `_history` was empty
    at launch and never recorded RECALL/command turns, so the model saw at
    most the last 3 chat lines. Junk template blobs are filtered out."""
    lines = []
    try:
        for role, message, _ts in store.get_recent_conversations(max_turns * 2):
            text = (message or "").strip()
            if not text or _is_context_junk(text):
                continue
            label = "User" if role == "user" else "AURA"
            lines.append(f"{label}: {text[:400]}")
    except Exception:
        # Fall back to in-RAM history if the store read fails.
        for h in _history[-max_turns:]:
            text = (h.get("text") or "").strip()
            if text and not _is_context_junk(text):
                label = "User" if h.get("role") == "user" else "AURA"
                lines.append(f"{label}: {text[:400]}")
    return "\n".join(lines[-max_turns:])


def _facts_block() -> str:
    """Compact 'what you know about the user' block from the durable
    user_facts store. Empty string when there's nothing yet."""
    try:
        facts = store.get_user_facts(limit=10)
    except Exception:
        facts = []
    if not facts:
        return ""
    bullets = "\n".join(f"- {f}" for f in facts)
    return f"What you know about them (use naturally, don't recite):\n{bullets}"


def build_context_prompt(query: str, intent: str, thought_context: str) -> str:
    history_text = _recent_turns(8)
    facts_text = _facts_block()

    # include screen context. For PERSONAL talk it's framed as a friend
    # hanging out — react to WHAT they're doing (F1 race, video, game,
    # code), never push work. For task intents it stays informational.
    screen_info = ""
    app = _last_context.get("app")
    visible = _last_context.get("visible_text") or ""
    if intent == "PERSONAL":
        if app and app != "unknown":
            screen_info = (
                f"\n(You can see their screen: {app}"
                + (f" — \"{visible[:200]}\"" if visible else "")
                + ". You're hanging out with them. If it fits the conversation, "
                "react to the CONTENT like a friend on the couch — the race, "
                "the video, the game, whatever it is. Never use their screen "
                "as a reason to push work or ask for code.)"
            )
    else:
        if app and app != "unknown":
            screen_info = f"\nCurrently on: {app}"
        if visible:
            screen_info += f"\nVisible content: {visible[:300]}"

    thought_section = f"\nContext: {thought_context}" if thought_context else ""
    facts_section = f"\n{facts_text}" if facts_text else ""

    return f"""Recent conversation:
{history_text}
{facts_section}
{screen_info}
{thought_section}

{query}"""

def anticipate(answer: str) -> str | None:
    prompt = ANTICIPATE_PROMPT.format(
        answer=answer,
        app=_last_context["app"]
    )
    result = call_claude(prompt).strip()
    return None if (result == "NONE" or not result) else result

LOCK_TRIGGERS = ["aura see", "aura watch", "aura focus on", "aura lock to", "aura look at"]
UNLOCK_PHRASES = [
    "aura see everything", "aura unlock", "aura stop watching",
    "aura unfocus", "aura stop focusing", "aura watch everything"
]

def handle_focus_command(query: str) -> str | None:
    global _pending_observation
    q = query.lower().strip()

    if any(p in q for p in UNLOCK_PHRASES):
        if get_app_lock():
            clear_app_lock()
            return "Back to watching everything."
        return None

    for trig in LOCK_TRIGGERS:
        if trig in q:
            app_phrase = q.split(trig, 1)[1].strip(" .?!")
            if app_phrase:
                from modules.decision_engine import evaluate_target, clarification_message
                decision = evaluate_target(app_phrase)
                print(f"[AURA] Target decision: {decision}")

                if decision["requires_clarification"]:
                    return clarification_message(decision)

                # Lock onto the short phrase the user said — this stays
                # robust against title changes (tab switches, etc).
                # resolved_app is only used for the spoken confirmation,
                # never as the actual stored lock value.
                set_app_lock(app_phrase)
                confirm_name = decision["resolved_app"] or app_phrase
                try:
                    from modules.screen_reader import get_screen_context
                    from modules.screen_observer import build_observation_reply, summarize_visible_issue
                    context = get_screen_context(app_phrase)
                    update_context(context)
                    issue = summarize_visible_issue(context)
                    _pending_observation = {
                        "app": confirm_name,
                        "context": context,
                        "issue": issue,
                    } if issue else None
                    return build_observation_reply(confirm_name, "observe", context)
                except Exception as e:
                    print(f"[AURA] Focus observation error: {e}")
                    return (
                        f"Looking at {confirm_name} now. "
                        "Do you want me to watch it for errors?"
                    )

    return None


def handle_observation_followup(query: str) -> str | None:
    global _pending_observation
    if not _pending_observation:
        return None

    q = query.lower().strip(" .?!")
    if q in {"no", "nope", "nah", "not now", "cancel", "stop"}:
        _pending_observation = None
        return "Okay, I’ll just keep watching."

    if q not in {"yes", "yeah", "yep", "sure", "ok", "okay", "please do"}:
        return None

    observation = _pending_observation
    _pending_observation = None
    visible_text = observation.get("context", {}).get("visible_text", "")
    app = observation.get("app", "that window")
    prompt = (
        f"The user asked me to look at {app}. I saw this screen/terminal text:\n"
        f"{visible_text}\n\n"
        "Briefly explain the likely problem and suggest what could be changed. "
        "Do not write a full code file. Ask before making changes."
    )
    answer = route("CASUAL", prompt)
    if answer in {"CONNECTION_ERROR", "RATE_LIMIT"} or answer.startswith("ERROR"):
        return "I saw the error, but the model connection stumbled. Paste the terminal text and I’ll reason from it."
    return guard_output(answer)


def process(query: str) -> str:
    print(f"\n[AURA] Processing: '{query}'")
    query_lower = query.lower()
    focus_response = handle_focus_command(query)
    if focus_response:
        store.save_conversation("user", query)
        store.save_conversation("aura", focus_response)
        return focus_response

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
    if any(w in query_lower for w in ["check for error", "any error", "is there an error", "errors?", "any errors"]):
        from modules.error_detector import handle_error_check
        result = handle_error_check(query)
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
    try:
        from modules.screen_reader import get_screen_context
        update_context(get_screen_context())
    except Exception as e:
        print(f"[AURA] Screen context refresh error: {e}")
    intent = classify_intent(query)
    print(f"[AURA] Intent: {intent}")

    if intent == "RECALL":
        result = conversational_recall(query)
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
    thought_context = think(query, intent, _last_context, _history)
    full_prompt = build_context_prompt(query, intent, thought_context)
    print("[AURA] Routing to AI...")
    answer = route(intent, full_prompt)

    if answer.startswith("ERROR") or answer == "CONNECTION_ERROR":
        return "Connection trouble — one sec."

    if answer == "RATE_LIMIT":
        return "Hit my rate limit — give me a moment."

    final_answer = guard_output(answer, 4 if intent == "PERSONAL" else 2)
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


def process_streaming(query: str, on_chunk=None, on_code=None, system_prompt: str | None = None, model: str | None = None, intent_hint: str | None = None) -> str:
    mark_user_active(query)
    print(f"\n[AURA] Streaming: '{query}'")
    query_lower = query.lower()
    focus_response = handle_focus_command(query)
    if focus_response:
        store.save_conversation("user", query)
        store.save_conversation("aura", focus_response)
        if on_chunk:
            on_chunk(focus_response)
        return focus_response

    observation_followup = handle_observation_followup(query)
    if observation_followup:
        store.save_conversation("user", query)
        store.save_conversation("aura", observation_followup)
        if on_chunk:
            on_chunk(observation_followup)
        return observation_followup
    if "afk" in query_lower:
          from modules.command_handler import describe_afk_status
          result = describe_afk_status()
          store.save_conversation("user", query)
          store.save_conversation("aura", result)
          if on_chunk:
              on_chunk(result)
          return result
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
    if any(w in query_lower for w in ["check for error", "any error", "is there an error", "errors?", "any errors"]):
        from modules.error_detector import handle_error_check
        result = handle_error_check(query)
        store.save_conversation("user", query)
        store.save_conversation("aura", result)
        if on_chunk:
            on_chunk(result)
        return result

    # Canned/command handlers fire ONLY when the Director hasn't already
    # ruled this a conversation. Without this, "i will ... start with work"
    # (a PERSONAL statement) hit the app launcher, which tried to open an
    # app literally called "with work".
    instant_response = None
    if intent_hint is None:
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
    try:
        from modules.screen_reader import get_screen_context
        update_context(get_screen_context())
    except Exception as e:
        print(f"[AURA] Screen context refresh error: {e}")
    import re as _re

    # If a system_prompt was passed, this is a compiled prompt from the engine.
    # Use the system_prompt to determine intent properly, and use the query
    # (which IS the compiled user prompt) as-is - don't wrap it in context.
    if system_prompt is not None:
        sp_lower = system_prompt.lower()
        if intent_hint:
            # The plan engine knows its domain — trust it over keyword
            # guessing (a miss dropped coding plans into CASUAL mode:
            # 150 tokens, 2-sentence limit, no code extraction).
            intent = intent_hint
        elif any(w in sp_lower for w in ["software engineer", "code", "coding", "implement"]):
            intent = "CODING"
        elif "research" in sp_lower:
            intent = "SEARCH"
        elif "writer" in sp_lower or "writing" in sp_lower:
            intent = "CASUAL"
        else:
            intent = "CASUAL"
        full_prompt = query
    elif _re.search(r'https?://', query):
        intent = "SEARCH"
        full_prompt = build_context_prompt(query, intent, "")
    else:
        # An explicit hint from the Conversation Director pins the intent —
        # the classifier alone could decide CODING for a mere statement of
        # intent and generate unsolicited code past the permission gate.
        intent = intent_hint or classify_intent(query)
        full_prompt = build_context_prompt(query, intent, "")
    if intent in {"RECALL", "SAVE"}:
        result = process(query)
        if on_chunk:
            on_chunk(result)
        return result

    if intent == "CODING":
        # Only inject AURA's own source when the request is actually about
        # THIS project. Generic coding questions ("linked list in python")
        # were getting AURA code chunks stuffed in, and the model wrote
        # about those instead of the user's task.
        q_low_ctx = query.lower()
        wants_project = (".py" in q_low_ctx or "aura" in q_low_ctx
                         or "this project" in q_low_ctx
                         or "the project" in q_low_ctx)
        project_ctx = ""
        if wants_project:
            from modules.project_context import get_relevant_context
            project_ctx = get_relevant_context(query)
        if project_ctx:
            full_prompt = f"Relevant code from the AURA project:\n{project_ctx}\n\n{full_prompt}"
            print(f"[AURA] Injected project context ({len(project_ctx)} chars)")

        raw_chunks = []
        for chunk in route_streaming(intent, full_prompt, system_prompt=system_prompt, model=model):
            raw_chunks.append(chunk)
        raw = "".join(raw_chunks).strip()

        if raw in {"CONNECTION_ERROR", "RATE_LIMIT"}:
            msg = "Connection trouble — one sec." if raw == "CONNECTION_ERROR" \
                  else "Hit my rate limit — give me a moment."
            if on_chunk:
                on_chunk(msg)
            return msg

        chat_part, lang, code = extract_code_block(raw)
        chat_msg = chat_part if chat_part else "Here's the code:"

        if on_chunk:
            on_chunk(chat_msg)
        if code and on_code:
            on_code(lang, code)

        store.save_conversation("user", query)
        store.save_conversation("aura", chat_msg)
        _history.append({"role": "user", "text": query})
        _history.append({"role": "aura", "text": chat_msg})
        post_think(query, chat_msg, intent)
        return chat_msg

    chunks = []
    for chunk in route_streaming(intent, full_prompt, system_prompt=system_prompt, model=model):
        chunks.append(chunk)
        if on_chunk and chunk not in {"CONNECTION_ERROR", "RATE_LIMIT"}:
            on_chunk(chunk)

    answer = "".join(chunks).strip()
    if answer.startswith("ERROR") or answer == "CONNECTION_ERROR":
        return "Connection trouble — one sec."
    if answer == "RATE_LIMIT":
        return "Hit my rate limit — give me a moment."

    final_answer = guard_output(answer, 4 if intent == "PERSONAL" else 2)
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

def start_proactive(speak_fn=None, on_suggestion_fn=None, on_presence_fn=None):
    """Start the Donna-style proactive loop."""
    if speak_fn is None:
        def speak_fn(text):
            speak_response(text, mode="CHAT")
    try:
        import modules.proactive as proactive
        proactive.start_proactive_loop(
            speak_fn=speak_fn,
            on_suggestion_fn=on_suggestion_fn,
            on_presence_fn=on_presence_fn,
        )
        print("[AURA] Proactive module started (Donna is watching)")
    except Exception as e:
        print(f"[AURA] Proactive start error: {e}")
        
    try:
        from modules.attention_engine import get_engine as get_ae
        import modules.voice_output as tts
        from modules.speech_planner import plan
        def _speak(text):
            tts.speak_chunks(plan(text, "CHAT"))
        get_ae().start(_speak, on_suggestion_fn)
    except Exception as e:
        print(f"[AURA] Attention engine start error: {e}")
        
