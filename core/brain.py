import datetime
import re
import time
from modules.proactive import set_app_lock, clear_app_lock, get_app_lock
from core.ai_router import call_claude, route, route_streaming, extract_code_block, call_classifier, last_model_used
from core.response_composer import compose_text
from core.thinking import think, post_think
from memory import store
from modules.csv_handler import check_csv
from modules.command_handler import handle_command
from modules.speech_planner import plan, debug as plan_debug
import modules.voice_output as tts
from core.personality import (INTENT_PROMPT, ANTICIPATE_PROMPT, SHOULD_RESPOND_PROMPT)

DEBUG_SPEECH = True

# Intents whose answers are full-length (reports, explanations), not
# 2-sentence chat — the guard trim is skipped for these (see process_streaming).
LONGFORM_INTENTS = {"RESEARCH", "DISCUSSION", "PLAN", "EXPLAIN"}

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
    # V3 developer state: a message is a heartbeat. It keeps the session's
    # activity clock alive so the flow/idle detection reflects real presence
    # rather than only screen-watcher samples.
    try:
        from core import v3_bridge
        v3_bridge.note_activity()
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
    # Last line of defence before anything is shown or spoken: strip any
    # chain-of-thought that survived the router. If nothing survives, the whole
    # response was deliberation — say so plainly rather than falling back to
    # the raw text, which would print the exact monologue this guards against.
    try:
        from core.ai_router import sanitize_text
        _deleaked = sanitize_text(response)
        if not _deleaked:
            print("[AURA] guard_output: response was all reasoning — discarded")
            return "Lost my train of thought there — say that again?"
        response = _deleaked
    except Exception:
        pass
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

# A CODING verdict is only trusted if the message actually asks for code to be
# produced/modified. "get me info for dna storage system" sounds technical, so
# the LLM classifier sometimes mislabels it CODING → wrong (Laguna coding)
# model. These cues gate that.
_CODE_ACTION_CUES = (
    "write ", "code", "implement", "refactor", "rewrite", "debug", "fix ",
    "patch", "compile", "function", "class ", "def ", "script", "program",
    "snippet", "syntax", "```", "leetcode", "regex", "algorithm to",
    ".py", ".js", ".ts", ".cpp", ".java", ".cs", ".go", ".rs", ".html", ".css",
)
# Broad info cues — used ONLY to pick SEARCH vs CASUAL when downgrading a wrong
# CODING verdict. "what is/are" included; bare "what's" is left out because it
# overlaps greetings ("what's up").
_INFO_CUES = (
    "info", "information", "tell me about", "what is", "what are", "who is",
    "how does", "how do", "how to", "explain", "overview", "details",
    "research", "find out", "look up", "learn about", "difference between",
    "meaning of", "summary of", "facts about", "get me info", "give me info",
)
# Narrow, unambiguous info cues — safe to UPGRADE a CASUAL verdict to SEARCH
# without stealing greetings/small-talk.
_STRONG_INFO_CUES = (
    "info", "information", "tell me about", "get me info", "give me info",
    "explain", "research", "look up", "find out", "learn about",
    "details about", "overview of", "summary of", "facts about",
)


def _correct_intent(query: str, intent: str) -> str:
    """Deterministic safety net over the LLM classifier. Stops technical-
    sounding INFORMATION requests from being routed to the coding model."""
    q = query.lower()
    has_code_cue = any(c in q for c in _CODE_ACTION_CUES)
    if intent == "CODING" and not has_code_cue:
        # CODING with no "produce code" cue → it's really an info/general ask.
        return "SEARCH" if any(c in q for c in _INFO_CUES) else "CASUAL"
    if intent == "CASUAL" and not has_code_cue and any(c in q for c in _STRONG_INFO_CUES):
        # Route genuine info requests to the research model, not small-talk.
        return "SEARCH"
    return intent


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
    intent = intent if intent in valid else "CASUAL"
    corrected = _correct_intent(query, intent)
    if corrected != intent:
        print(f"[AURA] Intent corrected: {intent} → {corrected} (no matching cue)")
    return corrected

def conversational_recall(query: str) -> str:
    """Answer memory questions like a companion, not a filing cabinet.

    Old behavior: knowledge-table lookup with the whole sentence as key →
    'I couldn't find anything saved about <echo>'. Now: gather everything
    AURA actually knows (session snapshot, recent conversation, knowledge
    hits) and let the LLM answer naturally."""
    parts = []
    # The project graph first — when they ask "what were we doing", the answer
    # is almost always a project, not a chat line. This is the same block the
    # ordinary chat turn gets, expanded.
    try:
        from core import work_recall
        # If the question names a project she knows, lead with THAT project's
        # detail — "what did we decide on the portfolio?" should answer about
        # the portfolio, not about whatever was touched most recently.
        focused = work_recall.find_project(query)
        if focused:
            parts.append(work_recall.focus_block(focused, query))
        work = work_recall.answer_context(query)
        if work:
            parts.append(work)
    except Exception:
        pass
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
            if not text or _is_context_junk(text):
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

    from core.ai_router import call_groq_raw, sanitize_text
    system = (
        "You are AURA, a sharp, warm AI companion, answering a question about "
        "what you remember. Speak straight TO them in second person. Answer in "
        "1-3 sentences, specifics first — name the project, the file, the "
        "decision. If what you know doesn't cover it, say it's fuzzy and ask "
        "them to remind you. NEVER mention 'context', 'database', 'saved "
        "entries', or that you were given information. Do not restate or "
        "analyse the question, do not write \"you asked\" or \"So answer:\" — "
        "the first words out of you are the answer itself."
    )
    # The old framing here was 'The user asks: "<query>"', which is precisely
    # the third-person shape the leak filter has to strip back out. Ask the
    # question as a question and the model answers instead of narrating.
    prompt = f'THEIR QUESTION: {query}\n\nWHAT YOU KNOW:\n' + "\n\n".join(parts)
    result = call_groq_raw(prompt, system, max_tokens=200, temperature=0.6)
    if result in ("RATE_LIMIT", "CONNECTION_ERROR"):
        return "My memory's being slow — give me a second and ask again."
    # This path bypassed guard_output, so a leak here reached the screen raw.
    cleaned = sanitize_text(result, query=query)
    if not cleaned:
        return "That one's fuzzy — remind me what we were on?"
    return cleaned


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
    # Director-injected instruction wrappers — backend detail, never context.
    "You are in RESEARCH mode",
    "You are in DISCUSSION mode",
    "You are in PLANNING mode",
    "Explain this clearly and conversationally",
    "Review this — point out issues",
    "Make a concise, practical plan",
    "Give a few practice questions",
    "User request:",
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


# ── V3 error intelligence hand-off ─────────────────────────────────────────
# scan_user_text() runs at the top of a turn (it needs the raw query); the
# prompt is assembled later. This one-shot slot carries the classification
# between the two without threading a new argument through every call site.
_v3_hint: dict | None = None


def _set_v3_hint(hint: dict | None) -> None:
    global _v3_hint
    _v3_hint = hint


def _consume_v3_hint() -> dict | None:
    """Read and clear — a stale hint must never leak into the next turn."""
    global _v3_hint
    hint, _v3_hint = _v3_hint, None
    return hint


_QUEST_STATUS_CUES = (
    "quest", "quests", "my board", "daily board",
)
_QUEST_ADD_CUES = ("add quest", "new quest", "make a quest", "create quest",
                   "set a quest", "add a quest")


def handle_quest_command(query: str) -> str | None:
    """Plain-language quest control from chat.

    Two shapes, because these are the two things worth doing without opening
    the tab: "add quest japanese 2 hrs" and "how are my quests".
    Returns None when the message isn't about quests, so the normal LLM path
    continues untouched.
    """
    q = (query or "").strip()
    low = q.lower()
    if not any(cue in low for cue in _QUEST_STATUS_CUES):
        return None
    try:
        from core import quests
        # Creation: strip the command words, hand the rest to the parser.
        for cue in _QUEST_ADD_CUES:
            if cue in low:
                spec_text = q[low.index(cue) + len(cue):].strip(" :-–—")
                if not spec_text:
                    return "What's the quest, and how long? Something like \"japanese 2 hrs\"."
                created = quests.create_from_text(spec_text)
                mins = created["target_minutes"]
                if not mins:
                    return (f"{created['title']} added — no target, I'll just "
                            "track how long you spend on it.")
                pretty = f"{mins // 60}h" if mins % 60 == 0 else f"{mins}m"
                return (f"{created['title']} added — {pretty} a day. "
                        "I'll count it when I see you doing it.")
        # Otherwise it's a status question — but only if it's about THEIR
        # board. "what is a quest in gaming" mentions quests and is not a
        # status check; it should reach the model like any other question.
        owned = any(p in low for p in (
            "my quest", "my board", "daily board", "quest board",
            "quests today", "today's quests", "todays quests",
            "quests left", "quests done", "quests remaining",
            "on my quests", "quest progress", "quest status",
        ))
        if owned:
            return quests.summary_line()
    except Exception as e:  # noqa: BLE001
        print(f"[AURA] quest command failed: {e}")
    return None


def scan_for_errors(query: str) -> dict | None:
    """Run the user's message past the V3 knowledge base.

    Returns the classification (and arms the prompt hint) when it recognised
    an error, else None. Deliberately silent on failure: the intelligence
    layer must never be able to break the chat path.
    """
    try:
        from core import v3_bridge
        hint = v3_bridge.scan_user_text(query)
    except Exception as e:  # noqa: BLE001
        print(f"[AURA] V3 scan skipped: {e}")
        return None
    if hint:
        print(f"[AURA] V3 recognised: {hint.get('label')} ({hint.get('level')})")
        _set_v3_hint(hint)
    return hint


def build_context_prompt(query: str, intent: str, thought_context: str, comeback: str | None = None) -> str:
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
    elif intent in {"CODING", "SEARCH", "COMMAND", "SAVE"}:
        # Task intents: screen content is real working context.
        if app and app != "unknown":
            screen_info = f"\nCurrently on: {app}"
        if visible:
            screen_info += f"\nVisible content: {visible[:300]}"
    else:
        # CASUAL small-talk: never dump raw screen text — the model kept
        # narrating the user's own screen back at them ("looks like you're
        # browsing through some design updates..."). Ambient mention only.
        if app and app != "unknown":
            screen_info = (f"\n(Background: {app} is open. Do NOT comment on "
                           "their screen or apps unless they ask about it.)")

    thought_section = f"\nContext: {thought_context}" if thought_context else ""
    facts_section = f"\n{facts_text}" if facts_text else ""

    # The Project Brain, in the conversation. Without this the chat could see
    # eight lines of history and nothing else, so "what project were we on last
    # time?" was answered by guessing — while the whole project graph (features,
    # tasks, decisions, commits, progress) sat in the same SQLite file. Compact
    # on ordinary turns; expanded when they're actually asking about the work.
    work_memory_section = ""
    try:
        from core import work_recall
        if work_recall.is_work_question(query):
            try:
                from core import activity
                activity.emit("Searching memory…", "memory")
            except Exception:  # noqa: BLE001
                pass
        block = work_recall.prompt_section(query)
        if block:
            work_memory_section = f"\n{block}"
    except Exception as e:  # noqa: BLE001 — context is a bonus, never a blocker
        print(f"[AURA] work_recall skipped: {e}")

    # If the user is asking about AURA herself, surface her fuller self-knowledge
    # so "who are you / who made you / what can you do" answers as her, not as a
    # generic assistant or a third-party tool.
    identity_section = ""
    try:
        from core.identity import identity_context
        identity_section = identity_context(query)
    except Exception:
        pass

    # Which language is on screen. This was the "give me it in c++" problem:
    # AURA answered a LeetCode question in Python because nothing ever looked
    # at the language selector sitting right above the editor.
    language_rule = ""
    if intent == "CODING":
        try:
            from core.code_language import detect_label
            lang = detect_label(_last_context)
            if lang:
                language_rule = (
                    f"\n(They are working in {lang} — the screen shows it. "
                    f"Answer in {lang} unless they explicitly ask for another "
                    "language. Do not ask which language to use.)"
                )
        except Exception:
            pass

    # Chat is chat. Code only exists when the user explicitly asks for code —
    # a topic mention ("i'm stuck on the websocket part") gets talked through,
    # not answered with an unsolicited code dump. If code seems needed, offer.
    no_code_rule = ""
    if intent != "CODING":
        no_code_rule = (
            "\n(Rule: do NOT write code or code blocks unless the user "
            "explicitly asked for code. If code would genuinely help, ask "
            "first — one line, e.g. \"Want me to write that?\")"
        )

    # Work-session debrief: they just came back from a real stretch of work.
    # AURA watched it happen, so she should say what she saw rather than open
    # with "you've been quiet". One-shot — consumed when the stretch is taken.
    work_section = ""
    if intent in {"PERSONAL", "CASUAL", "RECALL"}:
        try:
            from core.engagement import debrief_hint
            hint = debrief_hint()
            if hint:
                work_section = f"\n{hint}"
        except Exception:
            pass

    # Relationship surfacing (V2.2 item 5): trust and mood have been tracked
    # since the beginning but only ever reached PROACTIVE messages, so normal
    # conversation sounded the same on day 1 and day 200. Personal/casual talk
    # is where the relationship should show; task intents stay task-shaped.
    relationship_section = ""
    if intent in {"PERSONAL", "CASUAL", "RECALL"}:
        try:
            from modules.relationship_engine import get_engine as _get_re
            layer = _get_re().conversation_layer()
            if layer:
                relationship_section = f"\n({layer})"
        except Exception:
            pass

    # V3 error intelligence: if the user pasted something the knowledge base
    # recognised, the classifier already knows what it is and how serious it
    # is. Hand that to the model as CONTEXT rather than as the answer — the
    # KB line is a fast local read, not a replacement for actually helping.
    v3_section = ""
    hint = _consume_v3_hint()
    if hint:
        seriousness = ("This is serious — explain it properly, no jokes."
                       if hint.get("serious")
                       else "This is a small one — keep it light and quick.")
        repeat = ""
        if hint.get("repeat_count", 0) > 1:
            repeat = (f" They've hit this same error {hint['repeat_count']} times "
                      "today; you may acknowledge the pattern once, briefly.")
        v3_section = (
            f"\n(Error recognised locally: {hint.get('label')} "
            f"[{hint.get('category')}/{hint.get('level')}]. "
            f"{hint.get('explanation')} {seriousness}{repeat})"
        )

    # Returning after AURA checked in on them → resume the thread in ONE reply,
    # never a separate quip. "Since you're back — here's what you wanted..."
    comeback_rule = ""
    if comeback:
        warmth = ("They'd been away a while" if comeback == "full"
                  else "You'd just nudged them")
        comeback_rule = (
            f"\n({warmth} and now they're back. Open by acknowledging they're "
            "back — warm, not passive-aggressive — and CONTINUE where you left "
            "off: if they'd asked for something, deliver it now (\"Since you're "
            "back — here's...\"). One natural message.)"
        )

    return f"""Recent conversation:
{history_text}
{facts_section}
{work_memory_section}
{identity_section}
{screen_info}
{thought_section}
{work_section}
{relationship_section}
{v3_section}
{language_rule}
{no_code_rule}
{comeback_rule}

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
    if answer in {"CONNECTION_ERROR", "RATE_LIMIT", "THINKING_LEAK"} or answer.startswith("ERROR"):
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

    # The model produced nothing but chain-of-thought (ai_router filtered it
    # all out). Better to ask again than to print the deliberation.
    if answer == "THINKING_LEAK":
        return "Lost my train of thought there — say that again?"

    final_answer = compose_text(answer, intent, query, last_model_used())
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
    # Did the user just return after a nudge / being away? If so, the reply
    # should resume the thread ("since you're back...") instead of a separate
    # comeback quip colliding with the answer. One-shot — consumed here.
    comeback_hint = None
    try:
        from modules.attention_engine import get_engine as _get_ae
        comeback_hint = _get_ae().consume_comeback_hint()
    except Exception:
        pass
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
    # Quests: status and creation, both in plain language. Placed above the
    # generic task handlers because "add quest japanese 2 hrs" contains "add",
    # which the task matcher would otherwise claim.
    quest_reply = handle_quest_command(query)
    if quest_reply:
        store.save_conversation("user", query)
        store.save_conversation("aura", quest_reply)
        if on_chunk:
            on_chunk(quest_reply)
        return quest_reply

    if any(w in query_lower for w in ["check for error", "any error", "is there an error", "errors?", "any errors"]):
        from modules.error_detector import handle_error_check
        result = handle_error_check(query)
        store.save_conversation("user", query)
        store.save_conversation("aura", result)
        if on_chunk:
            on_chunk(result)
        return result

    # If they pasted a traceback, log it and arm the prompt hint. This does
    # NOT short-circuit the turn — the model still writes the reply; it just
    # writes it knowing what the error is. Placed after the canned handlers
    # above so an explicit command still wins.
    scan_for_errors(query)

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
        # A compiled prompt is deliberately NOT wrapped in the usual context —
        # but "what were we working on" asked inside a workspace mode is still a
        # memory question, and answering it from nothing looked like amnesia.
        # Append the project block only for those, so ordinary compiled prompts
        # stay exactly as the engine built them.
        # Also for a question that names a project: "/code ... how do I upgrade
        # the portfolio?" is a question about a real codebase, and answering it
        # from nothing is the same amnesia in a different mode.
        try:
            from core import work_recall
            if work_recall.is_work_question(query) or work_recall.find_project(query):
                block = work_recall.prompt_section(query)
                if block:
                    full_prompt = f"{query}\n\nWHAT YOU KNOW ABOUT THE WORK:\n{block}"
        except Exception:
            pass
    elif _re.search(r'https?://', query):
        intent = "SEARCH"
        full_prompt = build_context_prompt(query, intent, "", comeback=comeback_hint)
    else:
        # An explicit hint from the Conversation Director pins the intent —
        # the classifier alone could decide CODING for a mere statement of
        # intent and generate unsolicited code past the permission gate.
        intent = intent_hint or classify_intent(query)
        full_prompt = build_context_prompt(query, intent, "", comeback=comeback_hint)
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
            if chunk in {"CONNECTION_ERROR", "RATE_LIMIT"} and raw_chunks:
                continue   # mid-stream sentinel — status, not text
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
        # Persona layer: even the coding chat line sounds like AURA.
        chat_msg = compose_text(chat_msg, "CODING", query, last_model_used())

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
    saw_sentinel = None
    for chunk in route_streaming(intent, full_prompt, system_prompt=system_prompt, model=model):
        # Sentinels can arrive mid-stream (provider died after content began).
        # They are status codes, not text — never show or store them.
        if chunk in {"CONNECTION_ERROR", "RATE_LIMIT"}:
            saw_sentinel = chunk
            continue
        chunks.append(chunk)
        if on_chunk:
            on_chunk(chunk)

    answer = "".join(chunks).strip()
    if not answer and saw_sentinel == "RATE_LIMIT":
        return "Hit my rate limit — give me a moment."
    if answer.startswith("ERROR") or not answer:
        return "Connection trouble — one sec."

    # Final reasoning-leak pass over the ASSEMBLED answer.
    #
    # The streaming sanitizer can only peel a preamble — once it sees one
    # innocent-looking sentence it has to start emitting, and anything the
    # model thinks out loud after that point is already gone down the wire.
    # This second pass catches those, and it's the version the UI actually
    # displays: the client replaces the streamed text with this final string
    # when the "done" frame arrives.
    if intent != "CODING":
        from core.ai_router import sanitize_text
        # Pass the query: sentences that quote it back verbatim are the model
        # restating the prompt to itself, not answering it.
        from core.ai_router import note_leak
        deleaked = sanitize_text(answer, query=query)
        if not deleaked:
            # The model spent its whole budget deliberating and never wrote an
            # answer. Showing the monologue is strictly worse than admitting it.
            note_leak("streamed")
            return "Lost my train of thought there — say that again?"
        if deleaked != answer:
            # Repaired, not lost: usually the seam cut recovering the reply the
            # model settled on. Still counted — five leaks in five days means
            # the model matters more than the phrasing.
            note_leak("streamed", repaired=True)
        answer = deleaked

    # Response Composer + Persona Layer: every model's raw answer becomes
    # AURA's answer here — disclaimers stripped, identity questions answered
    # by AURA herself, style-shaped per intent (see core/response_composer).
    # Long-form workspace modes pass through whole (scrub only, no trim).
    final_answer = compose_text(
        answer, intent, query, last_model_used(),
        longform=intent in LONGFORM_INTENTS,
    )
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
        
