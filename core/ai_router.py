import os
import re
import requests
from dotenv import load_dotenv
from core.personality import DONNA_SYSTEM_PROMPT, INTENT_PERSONALITY_ADJUSTMENTS

load_dotenv()  # must be before os.getenv
GROQ_API_KEY = os.getenv("GROQ_API_KEY")  # get from console.groq.com
# Groq decommissioned llama-3.3-70b-versatile and llama-3.1-8b-instant on
# 2026-08-16 — every call started coming back 404 model_not_found. These are
# the replacements Groq documents for them.
GROQ_MODEL   = "openai/gpt-oss-120b"
# Background/meta calls (classifier, think, anticipate, nudges, summaries)
# run on the small model — Groq rate limits are PER MODEL, so this keeps
# the whole heavy-model quota for actual user-facing replies (429s were
# eating chat).
GROQ_MODEL_LIGHT = "openai/gpt-oss-20b"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"

# Explicit registry of Groq-hosted model ids. Provider USED to be inferred
# from the id shape ("contains a slash" => OpenRouter), but Groq's current
# ids ("openai/gpt-oss-120b", "qwen/qwen3.6-27b") contain slashes too, so
# that heuristic would silently send Groq traffic to OpenRouter with the
# wrong key. Anything not listed here is treated as OpenRouter.
GROQ_MODEL_IDS = {
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
}

# OpenRouter — OpenAI-compatible, so the same request/response shape works;
# only the endpoint + key differ. User-facing chat/coding/research routes go
# here (see model_router); background/meta calls stay on Groq. Add your key as
# OPENROUTER_API_KEY in .env.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")  # shared/default fallback
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Per-model OpenRouter keys — AURA uses a SEPARATE key for each model so work
# is spread across three independent free-tier quotas instead of exhausting
# one. Each falls back to the shared OPENROUTER_API_KEY if its own key is
# blank, so a single key still works too. Model ids mirror core/model_router.
_OPENROUTER_MODEL_KEYS = {
    "poolside/laguna-m.1:free":
        os.getenv("OPENROUTER_KEY_CODING") or OPENROUTER_API_KEY,
    "nvidia/nemotron-3-super-120b-a12b:free":
        os.getenv("OPENROUTER_KEY_RESEARCH") or OPENROUTER_API_KEY,
    "google/gemma-4-31b-it:free":
        os.getenv("OPENROUTER_KEY_CHAT") or OPENROUTER_API_KEY,
}

RATE_LIMIT_COOLDOWN_SECONDS = 20
# Per-PROVIDER cooldown: an OpenRouter 429 must not freeze Groq (and vice
# versa), otherwise the fallback would be pointless.
_provider_cooldown = {}   # provider name -> unix ts until which it's paused

# The model actually used for the last user-facing generation — the UI model
# chip reads this so it shows the real model, not a guess.
_last_model_used = GROQ_MODEL


def _provider_for(model_id: str) -> str:
    """Groq ids are the ones in GROQ_MODEL_IDS; everything else is an
    OpenRouter id. Do NOT go back to sniffing for a "/" — Groq ids have
    slashes now too."""
    if not model_id:
        return "groq"
    return "groq" if model_id in GROQ_MODEL_IDS else "openrouter"


def _endpoint_for(model_id: str):
    """Return (provider, url, api_key) for a model id. OpenRouter models use
    their own per-model key (see _OPENROUTER_MODEL_KEYS) so each draws from a
    separate free quota."""
    if _provider_for(model_id) == "openrouter":
        key = _OPENROUTER_MODEL_KEYS.get(model_id, OPENROUTER_API_KEY)
        return "openrouter", OPENROUTER_URL, key
    return "groq", GROQ_URL, GROQ_API_KEY


def _cooldown_key(provider: str, model_id: str) -> str:
    """Cooldown is tracked PER OpenRouter model (each has its own key/quota),
    but shared for Groq. So a 429 on one model's quota never pauses another."""
    return model_id if provider == "openrouter" else "groq"


def _headers(provider: str, api_key: str) -> dict:
    h = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if provider == "openrouter":
        # Optional but recommended by OpenRouter for attribution.
        h["HTTP-Referer"] = "https://aura.local"
        h["X-Title"] = "AURA"
    return h


def _apply_reasoning_policy(body: dict, provider: str) -> dict:
    """Keep private chain-of-thought out of `content`, mutating `body` in
    place and returning it.

    OpenRouter: ask the provider to drop reasoning server-side.
    Groq: the gpt-oss models are reasoning models, so without
    reasoning_format='hidden' their CoT can surface in the reply, and
    without a low reasoning_effort the thinking eats the max_tokens budget
    before the actual answer is emitted (short calls come back empty).
    """
    if provider == "openrouter":
        body["reasoning"] = {"exclude": True}
    else:
        body["reasoning_format"] = "hidden"
        body.setdefault("reasoning_effort", "low")
    return body


def _in_rate_limit_cooldown(provider: str = "groq") -> bool:
    import time as _time
    return _time.time() < _provider_cooldown.get(provider, 0.0)


def _start_rate_limit_cooldown(provider: str = "groq"):
    import time as _time
    _provider_cooldown[provider] = _time.time() + RATE_LIMIT_COOLDOWN_SECONDS
    print(f"[AURA] Rate limited — pausing {provider} calls for {RATE_LIMIT_COOLDOWN_SECONDS}s")


def _key_is_real(key) -> bool:
    """A usable key: present and not a leftover .env placeholder."""
    return bool(key) and "your-" not in key and "your_" not in key


def openrouter_status() -> str:
    """One-line summary of which OpenRouter model keys are configured, so it's
    obvious at startup that dropping a key in .env 'just works'. Any model
    without its own key still runs — it falls back to the shared key, then to
    Groq."""
    from core import model_router
    ready = [model_router.name_for_id(mid) or mid
             for mid, key in _OPENROUTER_MODEL_KEYS.items() if _key_is_real(key)]
    if not ready:
        return ("OpenRouter: no key detected — running on Groq for everything. "
                "Add OPENROUTER_KEY_CODING / _RESEARCH / _CHAT (or a single "
                "OPENROUTER_API_KEY) to .env to switch models on.")
    return "OpenRouter live for: " + ", ".join(ready) + " (others fall back to Groq)."


def last_model_used() -> str:
    return _last_model_used


# ── which model is actually doing this to us ────────────────────────────────
# Five separate leak fixes in five days, each for a different phrasing, and the
# 2026-07-31 one arrived from nvidia/nemotron-3-super-120b — a reasoning model
# that emits its deliberation as ordinary content, so OpenRouter's
# `reasoning: {exclude: True}` has nothing to strip. Counting them per model
# turns "AURA is being weird again" into "this specific endpoint is the
# problem", which is the difference between guessing and swapping the model.
_LEAKS: dict[str, dict[str, int]] = {}


def note_leak(where: str = "", repaired: bool = False) -> None:
    """Record that a response contained chain-of-thought. Never raises."""
    try:
        model = last_model_used() or "unknown"
        row = _LEAKS.setdefault(model, {"discarded": 0, "repaired": 0})
        row["repaired" if repaired else "discarded"] += 1
        total = row["discarded"] + row["repaired"]
        verb = "repaired" if repaired else "DISCARDED"
        print(f"[AURA] reasoning leak {verb} — {model} "
              f"(#{total} this run{', ' + where if where else ''})")
        if total in (3, 10) or (total > 10 and total % 25 == 0):
            print(f"[AURA] ⚠ {model} has leaked its thinking {total} times this "
                  "run. It writes deliberation as ordinary content, so no "
                  "server-side flag can suppress it — lock this model in the "
                  "Models panel if it keeps happening.")
    except Exception:  # noqa: BLE001 — telemetry must never break a reply
        pass


def leak_stats() -> dict[str, dict[str, int]]:
    """Per-model leak counts since the process started."""
    return {k: dict(v) for k, v in _LEAKS.items()}


def _set_last_model(model_id: str):
    global _last_model_used
    _last_model_used = model_id


def _announce_model(name: str, model_id: str, intent: str):
    """Loud, consistent terminal line so you can SEE which model actually
    produced each answer (and whether it was OpenRouter or a Groq fallback)."""
    print(f"[AURA] ✅ ANSWERED BY → {name}  ·  {model_id}  "
          f"·  {_provider_for(model_id).upper()}  (intent: {intent})")


def resolve_model(intent: str):
    """The model id AURA WOULD use for this intent right now, honoring locks.
    Used by the UI to show the model chip before a call runs. None if every
    candidate is locked."""
    cands = _resolve_candidates(intent, None)
    return cands[0][1] if cands else None


def _resolve_candidates(intent: str, explicit_model: str | None) -> list:
    """Ordered [(name, id)] to try, with LOCKED models removed entirely.
    A locked model is never used, no matter what. When an explicit model is
    given (from the plan engine), it leads, then the Groq fallback chain."""
    from core import model_router, model_lock
    if explicit_model:
        lead_name = model_router.name_for_id(explicit_model) or explicit_model
        base = [(lead_name, explicit_model)] + model_router.groq_fallbacks()
    else:
        base = model_router.candidates_for(intent)

    seen, out = set(), []
    for name, mid in base:
        if mid in seen:
            continue
        seen.add(mid)
        if model_lock.is_locked(name):
            continue   # locked → AURA may never use it
        out.append((name, mid))
    return out


_ALL_LOCKED_MSG = ("Every model I'd use for that is locked — unlock one in the "
                   "cosmos and I'll answer.")


_CODING_SYSTEM_ADDON = """
YOU ARE IN CODING MODE. THIS OVERRIDES EVERYTHING ELSE INCLUDING YOUR PERSONALITY RULES AND THE 2-SENTENCE LIMIT.

MANDATORY OUTPUT FORMAT — follow this EXACTLY, no exceptions:

Line 1: one short sentence intro (e.g. "Here's the C program:")
Then: a fenced code block using ``` followed by the language name, the FULL code, then ```
Then optionally: one short sentence after.

Example of CORRECT output for "print hello world in c":
Here's the C program:
```c
#include <stdio.h>

int main() {
    printf("Hello, World!\\n");
    return 0;
}
```
Compile with gcc.

RULES:
- The code block must contain the COMPLETE program: all includes, the main function, everything needed to compile and run. NEVER just a single line like printf(...) by itself.
- NEVER write code inline in a sentence (e.g. NEVER say 'just use cout: std::cout << "hi";'). Code ONLY goes inside the ``` block.
- NEVER tell the user to "stick it in main" or "add the rest yourself" — YOU write the full main function and structure.
- NEVER refuse, stall, or ask clarifying questions. Pick sensible defaults and write the full code immediately.
- Do not skip the ``` fences under any circumstance. This is the most important rule.
"""


_CODE_SIGNAL_PATTERNS = [
    r"\bint main\s*\(", r"\bdef \w+\s*\(", r"#include\s*<",
    r"\bpublic class\b", r"\bfunction\s+\w+\s*\(", r";\s*$",
    r"\bprintf\s*\(", r"\bcout\s*<<", r"\bSystem\.out\.print",
    r"\bconsole\.log\(",
]


def _looks_like_code(text: str) -> bool:
    hits = sum(1 for p in _CODE_SIGNAL_PATTERNS if re.search(p, text, re.MULTILINE))
    return hits >= 2


def extract_code_block(text: str) -> tuple[str, str, str]:
    """
    Returns (chat_part, language, code).
    chat_part = text outside the code block (short message)
    language  = detected language (e.g. 'cpp', 'python')
    code      = raw code inside the block
    Returns (text, '', '') if no code found at all.
    """
    match = re.search(r"```(\w*)\n?([\s\S]*?)```", text)
    if match:
        lang = match.group(1).strip() or "text"
        code = match.group(2).strip()
        chat_part = (text[:match.start()] + " " + text[match.end():]).strip()
        return chat_part, lang, code

    # Fallback: model wrote code without fences. Detect and salvage it.
    if _looks_like_code(text):
        return "Here's the code:", "text", text.strip()

    return text.strip(), "", ""


def clean_response(text: str) -> str:
    """Short-lane cleaner: strip leaks, THEN clamp to 2 sentences.

    The clamp is why the long lanes (personal/explain/longform) used to skip
    this entirely — and skipping it meant they got no leak filtering at all.
    The leak-stripping now lives in sanitize_text() so both halves are usable
    independently; this function is just "sanitize + clamp".
    """
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"\*\*.*?\*\*", "", text)
    leak_patterns = [
        r"^.*User is .*$", r"^.*User asks.*$", r"^.*AURA:.*$",
        r"^.*Certainly.*$", r"^.*Of course.*$", r"^.*As an AI.*$",
    ]
    for pattern in leak_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"^(User|Assistant|AURA|Bot)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = sanitize_text(text)
    text = text.strip().strip('"').strip("'").strip()
    text = re.sub(r"\s+", " ", text).strip()
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    result = ". ".join(sentences[:2])
    if result and not result.endswith(('.', '?', '!')):
        result += "."
    return result.strip()

# Workspace long-form modes (/research, /discussion, /plan) — full structured
# reports, so the usual 2-sentence clamp is replaced with this.
_LONGFORM_INTENTS = {"RESEARCH", "DISCUSSION", "PLAN"}

_LONGFORM_SYSTEM_ADDON = """

WORKSPACE MODE — this OVERRIDES your default brevity rules:
- IGNORE any 2-sentence / "keep it short" guidance. Be thorough.
- Produce a COMPLETE, well-structured answer with clear section headings
  exactly as the request specifies.
- Be specific and concrete: real steps, real examples, real trade-offs.
- No filler, no hype, no emoji. Objective and useful.
"""


_EXPLAIN_SYSTEM_ADDON = """

TEACHING MODE — this OVERRIDES your default brevity rules:
- IGNORE any 2-sentence / "keep it short" guidance.
- Give a clear, well-organized explanation of the TOPIC THE USER NAMED.
- Structure it like a good teacher: what it is, why it matters, the key
  pieces, a small concrete example, and where to go next.
- Do NOT write code unless explicitly asked.
- NEVER mention or describe the user's screen, apps, context, or anything
  you were given besides the topic itself. Answer the topic only.
- No filler, no hype, no emoji.
"""


_PERSONAL_SYSTEM_ADDON = """

PERSONAL MODE — you're a close friend right now, not a tool:
- Warm, real, present. Up to 4 short sentences.
- NO lists, NO code, NO advice-dumps unless they ask.
- Never demand code, never call their message "a mess" or "jumbled" —
  if it's unclear, respond like a person would ("wait, no to what?").
- No emoji unless they use them first. No therapy-speak.
- It's fine to reference what you know about them and your shared history."""


def call_groq_streaming(prompt: str, system: str = DONNA_SYSTEM_PROMPT, intent: str = "CASUAL", model: str = None):
    model_id = model or GROQ_MODEL
    provider, url, api_key = _endpoint_for(model_id)
    cd_key = _cooldown_key(provider, model_id)
    if _in_rate_limit_cooldown(cd_key):
        yield "RATE_LIMIT"
        return

    is_coding = (intent == "CODING")
    is_personal = (intent == "PERSONAL")
    is_explain = (intent == "EXPLAIN")
    is_longform = (intent in _LONGFORM_INTENTS)
    if is_coding:
        strict_system = system + _CODING_SYSTEM_ADDON
    elif is_explain:
        strict_system = system + _EXPLAIN_SYSTEM_ADDON
    elif is_longform:
        strict_system = system + _LONGFORM_SYSTEM_ADDON
    elif is_personal:
        strict_system = system + _PERSONAL_SYSTEM_ADDON
    else:
        strict_system = system + """

OVERRIDE ALL YOUR DEFAULT BEHAVIOR:
- MAX 2 sentences. Hard limit.
- NO emoji. Zero.
- NO "OMG", "Whoopsie", "Let's", "Together", "Great question", "Certainly"
- NO made-up context. Only refer to what's in the conversation.
- Talk like a sharp friend texting. Dry. Direct. No hype.
"""
    # Reasoning models (Nemotron etc.) love narrating their process — block it
    # at the source for EVERY lane, on top of the strict addons above.
    strict_system += _NO_THINK_ALOUD
    body = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": strict_system},
            {"role": "user",   "content": prompt}
        ],
        # 150 was the CASUAL budget, and it is why answers arrived chopped
        # mid-word ("…a dashboard-focused project, maybe a UI"). A reasoning
        # model spends part of that budget thinking out loud, so the sentence
        # it finally starts writing runs out of room. The filter then either
        # bins a truncated answer or hands over half of one.
        #
        # shaurya, 2026-07-31: "text can come in paragraph thats not the issue.
        # text are cutted without sending full meaning text." Longer is fine;
        # incomplete is not. Brevity is enforced by the prompt and the clamp,
        # which cut on SENTENCE boundaries — the token ceiling doesn't.
        "max_tokens": 2048 if (is_coding or is_longform) else (1024 if is_explain else (600 if is_personal else 400)),
        "temperature": 0.6 if is_longform else (0.5 if is_explain else (0.3 if is_coding else 0.7)),
        "stream": True
    }
    # Reasoning models (Nemotron, gpt-oss) return their private
    # chain-of-thought. We tell the provider to DROP it server-side so it
    # never arrives as content — the real root fix, not the regex band-aid
    # below.
    _apply_reasoning_policy(body, provider)
    try:
        response = requests.post(
            url,
            headers=_headers(provider, api_key),
            json=body,
            timeout=60 if (is_longform or is_explain) else 30,
            stream=True
        )
        if response.status_code == 429:
            _start_rate_limit_cooldown(cd_key)
            yield "RATE_LIMIT"
            return
        if response.status_code >= 400:
            print(f"[AURA] {provider} stream error {response.status_code}: {response.text[:200]}")
            yield "CONNECTION_ERROR"
            return
        _debug_buffer = []
        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: ") and line != "data: [DONE]":
                    import json
                    chunk = json.loads(line[6:])
                    delta = chunk["choices"][0]["delta"]
                    # Some reasoning models stream thinking in a separate
                    # `reasoning`/`reasoning_content` field — never yield it.
                    content = delta.get("content", "")
                    if content:
                        if is_coding:
                            _debug_buffer.append(content)
                        yield content
        if is_coding:
            print(f"[AURA CODE STREAM RAW]\n{''.join(_debug_buffer)}\n[END RAW]")
    except Exception as e:
        print(f"[AURA] Groq streaming error: {e}")
        yield "CONNECTION_ERROR"

_CLASSIFIER_SYSTEM = "You are a classifier. Output ONLY the requested single word. No personality, no extra text, no punctuation."


def call_claude(prompt: str, system: str = DONNA_SYSTEM_PROMPT) -> str:
    """Meta-call alias used by think/anticipate/knowledge/tasks/curiosity —
    routed to the LIGHT model so it never competes with chat for 70B quota."""
    return call_groq(prompt, system, intent="CASUAL", model=GROQ_MODEL_LIGHT)


def call_classifier(prompt: str) -> str:
    """Lightweight call for classification tasks (intent, anticipate, should_respond) — no personality prompt."""
    if _in_rate_limit_cooldown():
        return ""
    try:
        response = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json=_apply_reasoning_policy({
                "model": GROQ_MODEL_LIGHT,   # 1-word task — never burn heavy quota
                "messages": [
                    {"role": "system", "content": _CLASSIFIER_SYSTEM},
                    {"role": "user", "content": prompt}
                ],
                # gpt-oss is a reasoning model: its hidden thinking counts
                # against max_tokens, so the old ceiling of 20 truncated the
                # run before the one-word answer was ever emitted. Headroom
                # here costs nothing — the answer itself is still one word.
                "max_tokens": 512,
                "temperature": 0.1,
                "stream": False
            }, "groq"),
            timeout=15
        )
        if response.status_code == 429:
            _start_rate_limit_cooldown()
            return ""
        data = response.json()
        if "choices" not in data:
            print(f"[AURA] Groq classifier API error (status {response.status_code}): {data}")
            return "CONNECTION_ERROR"
        raw = data["choices"][0]["message"]["content"]
        return clean_response(raw)
    except Exception as e:
        print(f"[AURA] Groq classifier error: {e}")
        return "CONNECTION_ERROR"


def route(intent: str, prompt: str) -> str:
    extra = INTENT_PERSONALITY_ADJUSTMENTS.get(intent, "")
    system = DONNA_SYSTEM_PROMPT + extra
    candidates = _resolve_candidates(intent, None)
    if not candidates:
        return _ALL_LOCKED_MSG
    last = "CONNECTION_ERROR"
    for name, mid in candidates:
        try:
            from core import activity
            activity.emit(f"Routing to {name}…", "route")
        except Exception:  # noqa: BLE001
            pass
        result = call_groq(prompt, system, intent=intent, model=mid)
        if result in ("RATE_LIMIT", "CONNECTION_ERROR"):
            last = result
            print(f"[AURA] ⚠ {name} unavailable ({result}) — falling back")
            try:
                from core import activity
                activity.emit(f"{name} unavailable — falling back…", "route")
            except Exception:  # noqa: BLE001
                pass
            continue
        _set_last_model(mid)
        _announce_model(name, mid, intent)
        return result
    return last

# ── V2.2: life-memory injection (cached; refreshed every 5 min) ─────────────
_facts_cache = {"ts": 0.0, "text": ""}


def _user_facts_block() -> str:
    import time as _t
    if _t.time() - _facts_cache["ts"] > 300:
        try:
            from memory.store import get_user_facts
            facts = get_user_facts(10)
            _facts_cache["text"] = (
                "\n\nThings you know about the user (reference naturally, "
                "never recite as a list):\n- " + "\n- ".join(facts)
            ) if facts else ""
        except Exception:
            _facts_cache["text"] = ""
        _facts_cache["ts"] = _t.time()
    return _facts_cache["text"]


def _nature_overlay() -> str:
    """V2.3: user-selected nature lock (empty string on Auto)."""
    try:
        from core.nature import overlay
        return overlay()
    except Exception:
        return ""


# ── V2.2 item 5: relationship state shapes the voice (auto nature only) ─────
_rel_cache = {"ts": 0.0, "text": ""}


def _trust_tier_line(trust: float, mood: str) -> str:
    if trust < 0.3:
        return (f"You're still getting to know each other (trust {trust:.2f}). "
                "Friendly but a little reserved — earn the teasing rights first.")
    if trust < 0.55:
        return (f"You're familiar now (trust {trust:.2f}, mood: {mood}). "
                "Light teasing is fine, occasional callbacks to past chats.")
    if trust < 0.8:
        return (f"You're close friends (trust {trust:.2f}, mood: {mood}). "
                "Callbacks to shared history, inside references, real teasing, "
                "and taking initiative all feel natural.")
    return (f"You're best friends (trust {trust:.2f}, mood: {mood}). "
            "Full comfort: running jokes, blunt honesty, initiative, callbacks "
            "to everything you've been through together. You KNOW this person.")


def _relationship_block() -> str:
    import time as _t
    if _t.time() - _rel_cache["ts"] > 60:
        try:
            from core.nature import get_nature
            if get_nature() != "auto":
                _rel_cache["text"] = ""   # manual nature lock wins outright
            else:
                from modules.relationship_engine import get_engine
                state = get_engine().get_state()
                trust = float(state.get("trust", 0.3))
                mood = state.get("mood", "neutral")
                _rel_cache["text"] = "\n\nRELATIONSHIP:\n" + _trust_tier_line(trust, mood)
        except Exception:
            _rel_cache["text"] = ""
        _rel_cache["ts"] = _t.time()
    return _rel_cache["text"]


_NO_THINK_ALOUD = (
    "\n\nCRITICAL: Reply with ONLY the final message to the user, addressed to "
    "them directly. Do NOT think out loud, restate the rules, or narrate your "
    "process. Never write phrases like \"the user wants\", \"looking at the "
    "conversation history\", \"we need to\", or \"there's a typo\" — just answer."
    # These three showed up in real leaks AFTER the first two fixes: the model
    # had stopped naming rules and started narrating the handover instead
    # ("So answer: ...", "So we can say: ...", "That's one sentence?"). Naming
    # the exact phrases is what finally moved the behaviour, since a general
    # "don't think out loud" reads as satisfied once the rule-echoes are gone.
    "\nDo not announce your answer before giving it — never write \"So answer:\", "
    "\"Final answer:\", \"So we can say:\", or \"Provide concise answer:\". "
    "Write the answer itself as your first words."
    "\nDo not evaluate your own reply afterwards — no \"That's one sentence?\", "
    "no \"That's explicit\", no counting your sentences back to the user."
    "\nSpeak in second person to them (\"you're\"), never third person about "
    "them (\"they're\", \"user's activity\")."
)


# ── Reasoning-leak sanitizer ─────────────────────────────────────────────────
# Reasoning models (Nemotron, R1-style) sometimes emit their private thinking
# into the answer: "<think>...</think>" blocks, or plain meta-preamble like
# "We need to obey the rules: 1-2 sentences, no emoji...". None of that should
# ever reach the user. We buffer only the HEAD of the stream, peel the leak,
# then stream the real answer live.
# Two tiers, and the split matters.
#
# STRONG markers are things a reply addressed TO the user can essentially never
# contain — third-person talk about "the user", echoes of the system prompt's
# own mode names and rules, explicit self-instruction. These are stripped
# ANYWHERE in the response.
#
# WEAK markers ("we need to", "let me think") do show up in legitimate
# explanations and code discussion, so they only strip a LEADING preamble.
# Mixing the two is what let a full page of deliberation through: the leak
# opened with "The user says:" — which the old pattern didn't cover, because it
# listed `said`/`asks` but not `says` — so peeling stopped at sentence one and
# every later "We need to respond in 1-2 sentences" streamed out untouched.
_re_mod = __import__("re")

_META_STRONG_RE = _re_mod.compile(
    r"(?i)("
    # third-person narration about the person being spoken to
    r"\bthe user\b|"
    # "user's" without a "the" in front — "No mention of user's activity unless
    # they explicitly told" was a real leak that slipped past, because the noun
    # list only covered things a user SAYS, not things a user IS DOING.
    r"\buser'?s (?:message|question|query|request|input|typo|last|activity|"
    r"screen|context|intent|tone|state|situation|goal|mood|words?|wording|"
    r"task|project|problem|behaviou?r|session)\b|"
    r"\bthey (?:want|said|asked|mean|are asking|likely)\b|\blikely they\b|"
    r"\bunless they (?:explicitly|specifically|actually)\b|"
    # Narrating the person as a subject under observation. Deliberately narrow:
    # "they should be joined" (about threads) must stay legal, while
    # "they're on the Two Sum II problem" and "they should be thinking about"
    # — both real leaks from the proactive path — must not.
    r"\bthey(?:'re| are| were)\s+(?:on|in|at|viewing|watching|looking at|"
    r"working on|doing|using|tackling|trying|solving|reading|browsing|"
    r"currently|probably|likely|apparently)\b|"
    r"\bthey\s+(?:should be thinking|seem to be|seems to be|appear to be|"
    r"appears to be|have been working|has been working|are probably|"
    r"might be trying|may be trying)\b|"
    # echoing the system prompt back
    r"teaching mode|personal mode|workspace mode|coding mode|override all|"
    r"\brule \d+\b|according to (?:the )?rule|per the (?:rule|instruction)|"
    r"banned words?|obey the rules|follow the rules|\bthe rules?:|"
    r"max(?:imum)? \d+ sentence|\d+\s*-\s*\d+ sentences|two sentences|"
    # counting its own sentences in WORDS, not digits — "That's one sentence?"
    # is the model checking its work out loud, which the digit patterns missed.
    r"\b(?:that'?s|is that|thats|keep(?:ing)? it to|just|only)\s+"
    r"(?:one|two|three|a single)\s+sentences?\b|"
    # any sentence that talks about its own sentence budget is self-instruction
    r"(?:need|keep it to|limit|within|use|only)\s+\d+\s+sentences?\b|"
    r"\d+\s+sentences?\s+(?:max|only|or less|at most)\b|"
    r"no emoji|no (?:extra |added )?fluff|brevity rules?|"
    # STYLE-RULE ECHO (2026-07-31 leak). The model recited the persona rules
    # as bare imperatives — no "the user", no colon-seam, no digits, so every
    # existing pattern missed all four sentences:
    #   'No starting with "I" unless unavoidable. Avoid meta commentary.
    #    So we can't say "You are looking for..." We can just give answer.'
    r"meta[- ]?commentary|unless unavoidable|"
    # "No starting with "I"" / "Avoid opening with I". A quote or a bare "I"
    # is required after `with`, so an ordinary instruction like "don't start
    # with the whole array" stays legal.
    r"(?:no|avoid|never|don'?t|do not)\s+(?:start|begin|open)(?:ing)?\s+"
    r"(?:the |your |a |my )?(?:reply|response|answer|sentence|message)?\s*"
    r"with\s+[\"“'‘]|"
    r"(?:no|avoid|never|don'?t|do not)\s+(?:start|begin|open)(?:ing)?\s+"
    r"(?:the |your |a |my )?(?:reply|response|answer|sentence|message)?\s*"
    r"with\s+I\b|"
    r"\b(?:first|second|third)[- ]person\b|"
    # CONTEXT NARRATION (2026-07-31, nvidia/nemotron via OpenRouter). Now that
    # work_recall injects the project brain, the model reads it back out loud
    # before answering: "We have context: Wasabikiri_remake — last: Fix
    # dashboard layout overflow, 22h ago." The richer the context, the more
    # there is to narrate, so this grew with the feature.
    r"\bwe have (?:the |a |some )?(?:context|info|information|history|memory|details?)\b|"
    r"\b(?:given|from|based on) the (?:context|above)\b[^.!?]{0,40}\bwe\b|"
    r"\b(?:so |thus |then )?we (?:can|could|should|might|will) "
    # "note" is deliberately absent: "we should note that Python ints are
    # arbitrary precision" is a legitimate explanatory sentence, and these
    # markers delete the sentence wherever it sits.
    r"(?:suggest|recommend|mention|offer|propose|point out|tell them|ask them|"
    r"describe|summari[sz]e|infer)\b|"
    # Reasoning ABOUT the gaps in its own context — the 12:33 leak, where she
    # had no description of the project stored and thought out loud about it:
    # "likely a dashboard? Not given explicitly, but we can infer…"
    r"\bnot (?:given|stated|specified|mentioned|provided) (?:explicitly|directly|anywhere)\b|"
    r"\bisn'?t (?:given|stated|specified) (?:explicitly|directly)\b|"
    # "We know last activity: Fix dashboard layout overflow." — reading the
    # injected context aloud. The colon is required, so "we know the loop
    # terminates" stays legal.
    r"\bwe know\b[^.!?]{0,30}:|"
    # Quoted banned-phrase rules: 'No "I think".' / 'Avoid "Sure".' The quote
    # is required, so ordinary negation ("no, that won't work") is untouched.
    r"(?:^|[.!?])\s*(?:no|avoid|never|don'?t use|don'?t say|not)\s+"
    r"[\"“'][^\"”']{1,40}[\"”']|"
    # A subjectless imperative IS self-instruction — nobody says "Must start
    # directly." to another person. Anchored to the sentence start.
    r"(?:^|[.!?])\s*must\s+"
    r"(?:start|begin|open|be|use|keep|avoid|not|stay|end|answer|reply|respond)\b|"
    r"\bstart(?:ing)? directly\b|"
    # Contraction form of the planning markers. The spelled-out "we can not"
    # was covered; "we can't say" was not. Kept narrow — a QUOTE must follow,
    # because "we can't say for sure" is a legitimate thing to tell someone.
    r"we (?:can'?t|cannot|won'?t|shouldn'?t|mustn'?t|couldn'?t)\s+"
    r"(?:say|write|start|begin|open|use|mention|respond|reply|answer)\b"
    r"\s*[:,]?\s*[\"“'‘]|"
    # "We can just give answer." The provide-answer pattern below demands an
    # adjective ("concise answer"), so the filler form walked straight past.
    # Two shapes, both model-speak: with a hedge word, or with no article.
    r"\b(?:we|i)\s+(?:can|could|should|shall|will|'ll|must|might)?\s*"
    r"(?:just|simply|only)\s+(?:provide|give|write|produce|output|say)\s+"
    r"(?:a |an |the )?(?:concise |short |brief |clear |direct |final |good )?"
    r"(?:answer|response|reply)\b|"
    r"\b(?:we|i)\s+(?:can|could|should|will|'ll|must)\s+"
    r"(?:provide|give|write|produce|output)\s+"
    r"(?:concise |short |brief |direct |final )?(?:answer|response|reply)\b|"
    # explicit planning / self-instruction about the answer
    r"we (?:must|should|need to|can|have to|are) not\b|"
    r"we need to (?:respond|answer|produce|give|write|say|follow|avoid|infer)|"
    r"we (?:must|should) (?:not |avoid |produce |respond |answer |follow )|"
    r"thus we (?:need|must|should)|so we (?:need|must) to|"
    r"our (?:response|reply|answer) (?:should|must|needs)|"
    # deliberating about HOW to answer — "Should we ask clarifying?",
    # "We have enough info to give suggestions.", "Provide concise answer:"
    r"should we (?:ask|say|give|provide|mention|clarify|include|add|offer|answer)|"
    r"we have enough (?:info|context|information|detail)|"
    r"ask (?:a )?clarifying|clarifying question|"
    r"(?:provide|give|write|produce|output|keep|make) (?:a |the )?"
    r"(?:concise|short|brief|clear|direct|final|good) (?:answer|response|reply|version|explanation)|"
    # THE SEAM. A reasoning model that has finished thinking announces its
    # output before writing it — "So answer: …", "So we can say: …",
    # "Final answer: …". The sentence that follows is usually the real reply,
    # which is exactly why this used to survive: nothing in it names the user,
    # quotes a rule, or plans anything. It just narrates the handover.
    r"\b(?:so|thus|hence|therefore|ok(?:ay)?)[,:]?\s*(?:the\s+)?(?:final\s+)?"
    r"answer\s*[:\-]|"
    r"\b(?:final|short|concise|direct)\s+answer\s*[:\-]|"
    # "…\s+say" optionally followed by "something like" / "it like": gpt-oss
    # writes "We can say something like: "…"", which slipped straight through
    # because the old pattern demanded the colon immediately after "say".
    r"\b(?:so|thus|hence|therefore)?\s*(?:we|i)\s+(?:can|could|should|shall|"
    r"will|'ll|might)\s+say(?:\s+(?:something|sth|it|this|that))?"
    r"(?:\s+like)?\s*[:,]|"
    # gpt-oss's planning voice: it narrates the shape of the reply before
    # writing it — "We can respond with a brief comment", "No meta.",
    # "No question at end." None of these are ever the answer.
    r"we (?:can|could|should|will|'ll) (?:respond|reply|answer) with\b|"
    r"(?:^|[.!?]\s*)no meta\b|"
    r"(?:^|[.!?]\s*)no question at (?:the )?end\b|"
    # The hedged handover — "Probably: "Start by pulling the latest main…"".
    # Same seam, worn as a guess instead of a conclusion.
    r"(?:^|[.!?])\s*(?:probably|perhaps|maybe|likely|something like|"
    r"i'?d say|response|reply|output)\s*:|"
    r"as an ai|chain[- ]of[- ]thought"
    r")"
)

_META_WEAK_RE = _re_mod.compile(
    r"(?i)("
    r"we need to|we must|we should|answer the question|sentence [12]\b|"
    r"they(?:'ve| have| are|'re| were) (?:been )?(?:discussing|talking about|asking|working on|building|mentioned)|"
    r"looking at (?:the |our )?(?:conversation|chat|history|context|previous message|screen)|"
    r"(?:the |our )?conversation history|based on (?:the |our )?(?:context|conversation|history|chat|prior|previous|above|earlier)|"
    r"(?:starts?|starting) with a typo|^\W*with a typo\b|there'?s a typo in (?:the|their|your) (?:message|question|query|input|last|text)|"
    r"let me (?:think|see|check|refine|look|start)\b|the question is\b|to answer (?:this|the|their)|"
    r"i (?:need|should|must|'ll|will) (?:to )?(?:obey|answer|give|respond|follow|refine|provide|note that)|"
    r"let'?s (?:obey|answer|start)\b|first,? i (?:need|should|must)"
    r")"
)

# Kept for backwards compatibility — anything that used _META_RE gets both.
_META_RE = _re_mod.compile(
    "(?i)(" + _META_STRONG_RE.pattern[5:-1] + "|" + _META_WEAK_RE.pattern[5:-1] + ")"
)
_SENT_SPLIT = _re_mod.compile(r"([.!?\n]+)")

# The handover phrase a reasoning model writes between thinking and answering.
# Whatever follows the LAST one of these is the reply it settled on, so instead
# of discarding the sentence (and the answer inside it) we cut to the tail.
# Anchored on the colon/dash: "So answer:" is a seam, "so we can say that X"
# in the middle of an explanation is not.
_SEAM_RE = _re_mod.compile(
    r"(?i)(?:^|[.!?\n]\s*|\s)"
    r"(?:"
    r"(?:so|thus|hence|therefore|ok(?:ay)?)[,:]?\s*(?:the\s+)?(?:final\s+)?answer"
    r"|(?:final|short|concise|direct)\s+answer"
    r"|(?:so|thus|hence|therefore)[,:]?\s*(?:we|i)\s+"
    r"(?:can|could|should|shall|will|'ll|might)\s+say"
    r"(?:\s+(?:something|sth|it|this|that))?(?:\s+like)?"
    r"|(?:we|i)\s+(?:can|could|should|shall|will|'ll)\s+say"
    # "We can say SOMETHING LIKE: "…"" — gpt-oss's habitual handover. Without
    # the optional tail the seam missed and the whole deliberation shipped.
    r"(?:\s+(?:something|sth|it|this|that))?(?:\s+like)?"
    r")"
    r"\s*[:\-—]\s*"
)

# The HEDGED handover, kept separate because it needs a tighter anchor. A
# reasoning model that isn't certain still announces its reply before writing
# it — 'Probably: "Start by pulling the latest main branch…"' — and the text
# after the colon is the actual answer, so cutting to it recovers the turn.
# Must be at a sentence start: "the cause is probably: a race" would otherwise
# get truncated to "A race", and "probably" mid-sentence is ordinary English.
_HEDGE_SEAM_RE = _re_mod.compile(
    r"(?i)(?:^|[.!?\n]\s*)(?:"
    r"(?:probably|perhaps|maybe|likely|i'?d say|final response|response|reply|output)"
    r"\s*[:\-—]"
    # "So we can say it's a dashboard-focused project" — the same handover with
    # NO colon, which is how it slipped past the strong marker and _SEAM_RE
    # (both anchor on the punctuation). Safe only because it must open a
    # sentence: "from the invariant we can say the loop terminates" doesn't.
    r"|(?:so|thus|hence|therefore|ok(?:ay)?)[,]?\s*(?:we|i)\s+"
    r"(?:can|could|should|shall|will|'ll|might)\s+say\s*[:,]?"
    r")\s*"
)


def _is_meta_sentence(s: str) -> bool:
    """Leading-preamble test: strong OR weak markers both count here."""
    return bool(_META_STRONG_RE.search(s) or _META_WEAK_RE.search(s))


def _is_strong_meta(s: str) -> bool:
    """Anywhere-in-the-text test: only unambiguous leaks."""
    return bool(_META_STRONG_RE.search(s))


def _split_sentences(text: str) -> list[str]:
    parts = _SENT_SPLIT.split(text)
    out, cur = [], ""
    for p in parts:
        cur += p
        if _SENT_SPLIT.fullmatch(p):
            out.append(cur)
            cur = ""
    if cur.strip():
        out.append(cur)
    return out


def _echoes_query(sentence: str, query: str, min_run: int = 34) -> bool:
    """True if `sentence` contains a long verbatim run from the user's message.

    Restating the prompt back is a reliable tell of leaked thinking — the real
    leak opened with the tail of the user's own question plus a stray closing
    quote. The run has to be long (34+ chars) so that normally echoing a short
    phrase back ("your N3 target") is never mistaken for it.
    """
    if not query or len(query) < min_run:
        return False
    import re
    norm = lambda s: re.sub(r"\s+", " ", s.lower()).strip()
    s, q = norm(sentence), norm(query)
    if len(s) < min_run:
        return False
    # Slide a window of min_run chars from the query across the sentence.
    for i in range(0, len(q) - min_run + 1):
        if q[i:i + min_run] in s:
            return True
    return False


def sanitize_text(text: str, query: str = "") -> str:
    """Full-response reasoning-leak filter.

    Unlike _peel_head (which only trims a preamble so streaming can start),
    this walks the WHOLE response: it drops a leading run of any meta
    sentences, then continues removing strongly-meta sentences wherever they
    appear. That second half is the part that was missing — a leak whose first
    sentence looked innocent used to pass through entirely.

    Pass `query` (the user's own message) when you have it — sentences that
    quote it back verbatim are deliberation, not answer.

    Returns "" when everything was deliberation, which is a real case: when the
    model spends its whole token budget thinking, there is no answer to show
    and the caller should fall back rather than print the monologue.
    """
    if not text:
        return ""
    import re

    # Fenced code is lifted out BEFORE any filtering and put back untouched.
    # This function whitespace-normalises prose, which flattened a C++ answer
    # into "```cpp class Solution { public: vector<int> twoSum(..." — one long
    # line in the chat bubble. Code must survive byte-for-byte; only the prose
    # around it is ever rewritten.
    blocks: list[str] = []

    def _stash(m: "re.Match[str]") -> str:
        blocks.append(m.group(0))
        return f"\x00CODE{len(blocks) - 1}\x00"

    text = re.sub(r"```[\s\S]*?```", _stash, text)
    # An unterminated fence — a stream cut off mid-block — counts as code too.
    if "```" in text:
        idx = text.index("```")
        blocks.append(text[idx:])
        text = text[:idx] + f"\x00CODE{len(blocks) - 1}\x00"

    def _restore(s: str) -> str:
        for i, b in enumerate(blocks):
            s = s.replace(f"\x00CODE{i}\x00", b)
        return s

    text = re.sub(r"(?is)<think>.*?</think>", "", text)
    text = re.sub(r"(?is)<(thinking|reasoning|scratchpad)>.*?</\1>", "", text)
    # An unterminated opener means the model was cut off mid-thought.
    ti = text.lower().find("<think>")
    if ti != -1:
        text = text[:ti]

    # Code alone is a complete answer. If the prose is empty (or turns out to
    # be pure deliberation below), the code block must still be returned —
    # dropping it would throw away the thing actually being asked for.
    def _code_only() -> str:
        return "\n\n".join(blocks).strip()

    # Cut to the answer the model settled on. A leak like
    #   "Looking at X now. So answer: You're on X. No mention of user's
    #    activity unless they explicitly told. So we can say: You're viewing X."
    # is deliberation wrapped around the real reply, and the reply sits after
    # the LAST handover phrase. Taking that tail keeps the answer instead of
    # binning the whole turn — the sentence filters below still clean the tail.
    # Only trusted when something substantial follows, so a response that merely
    # ends with "final answer:" (cut off mid-stream) falls through untouched.
    seams = list(_SEAM_RE.finditer(text)) + list(_HEDGE_SEAM_RE.finditer(text))
    if seams:
        seams.sort(key=lambda m: m.end())
        tail = text[seams[-1].end():].strip()
        if len(tail) >= 12:
            # The handover often carries filler into the answer — 'maybe "Start
            # with Genki I…' — including a quote it never closes. Drop that.
            tail = re.sub(
                r'^(?:maybe|perhaps|something like|roughly|i\.e\.|e\.g\.)[,:]?\s*',
                "", tail, flags=re.I)
            tail = tail.lstrip('"“\'` ').strip()
            if tail and tail[0].islower():
                tail = tail[0].upper() + tail[1:]
            text = tail

    # Stray punctuation fragments are dropped before anything is counted.
    # Splitting on [.!?] turns 'we can't say "You are looking for..."' into a
    # meta sentence PLUS a lone '"', and that orphan quote is what saved the
    # 2026-07-31 leak: it matches no marker, so the peel stopped on it and the
    # density check counted it as content. Fragments only survive if they carry
    # a letter or digit, or are long enough to be deliberate (a --- rule).
    sentences = [
        s for s in _split_sentences(text)
        if s.strip() and (re.search(r"[A-Za-z0-9]", s) or len(s.strip()) > 2)
    ]
    if not sentences:
        return _code_only()

    # A sentence that quotes the user's message back counts as strongly meta
    # for the rest of this pass.
    def _strong(s: str) -> bool:
        return _is_strong_meta(s) or _echoes_query(s, query)

    # 1. Peel the leading run of deliberation.
    idx = 0
    while idx < len(sentences) and (_is_meta_sentence(sentences[idx]) or _strong(sentences[idx])):
        idx += 1
    rest = sentences[idx:]
    if not rest:
        return _code_only()

    # 2. Density check on WHAT'S LEFT — deliberately after the peel, not
    #    before it. Keyword matching alone can't win this: a monologue also
    #    contains ordinary-looking sentences ("That's a statement about what
    #    they're doing") that match nothing, and chasing each new phrasing is a
    #    losing game. But a real reply is never MOSTLY meta. Running this on
    #    the raw text would punish the common good case — a short preamble
    #    followed by a genuine answer — so it only judges the remainder.
    strong = sum(1 for s in rest if _strong(s))
    # Three or more sentences: half being meta means the whole thing is a
    # monologue. Two sentences: half is ONE sentence, and "<real answer>. That's
    # one sentence?" is exactly that shape — an answer with the model's own
    # sanity-check stuck to the end. Binning it would throw away the reply, so a
    # short remainder must be entirely meta before it's discarded.
    if len(rest) >= 3 and strong / len(rest) >= 0.5:
        return _code_only()
    if len(rest) <= 2 and strong == len(rest):
        return _code_only()

    # 3. Drop any remaining strongly-meta sentences wherever they sit.
    kept = [s for s in rest if not _strong(s)]
    # Whitespace-normalise the PROSE only, then put the code back verbatim.
    prose = re.sub(r"[ \t]*\n[ \t]*", "\n", "".join(kept))
    prose = re.sub(r"[ \t]{2,}", " ", prose).strip()
    # Whatever survived has to actually say something. If the filters ate every
    # word and left punctuation behind, that's the same case as an all-reasoning
    # response — the caller must fall back, not print an orphan quote mark.
    if not re.search(r"[A-Za-z0-9]", prose):
        return _code_only()
    return _restore(prose).strip()


def _peel_head(head: str, final: bool = False):
    """Return (emit_text, new_head, start_streaming). Strips <think> blocks and
    leading meta-reasoning sentences until real content begins."""
    import re
    head = re.sub(r"(?is)<think>.*?</think>", "", head)
    ti = head.lower().find("<think>")
    if ti != -1:
        if final:
            head = head[:ti]
        else:
            return "", head, False  # wait for the closing tag

    parts = _SENT_SPLIT.split(head)
    sentences, cur = [], ""
    for p in parts:
        cur += p
        if _SENT_SPLIT.fullmatch(p):
            sentences.append(cur)
            cur = ""
    tail = cur  # incomplete trailing sentence

    idx = 0
    while idx < len(sentences) and _is_meta_sentence(sentences[idx]):
        idx += 1
    if idx < len(sentences):
        return ("".join(sentences[idx:]) + tail).lstrip(), "", True
    if final:
        return tail.strip(), "", True
    return "", tail, False


def _sanitize_reasoning_stream(chunks):
    head, streaming = "", False
    for ch in chunks:
        if ch in ("RATE_LIMIT", "CONNECTION_ERROR"):
            yield ch
            continue
        if streaming:
            yield ch
            continue
        head += ch
        emit, head, streaming = _peel_head(head)
        if streaming:
            if emit:
                yield emit
        elif len(head) > 1200:  # safety: never buffer forever
            emit, head, streaming = _peel_head(head, final=True)
            if emit:
                yield emit
            streaming = True
    if head and not streaming:
        emit, _, _ = _peel_head(head, final=True)
        if emit:
            yield emit


# ── Second-person enforcement (proactive / attention / curiosity) ───────────
# These lines are ALWAYS spoken directly to shaurya, so any third-person
# reference to him is a leak by definition — the model slipped from "talking
# to him" into "reporting about him". Chat can't use a rule this blunt (a
# reply may legitimately discuss other people), which is why it lives here and
# not in sanitize_text.
# Phrases that are ALWAYS a leak, whatever else the line says.
_THIRD_PERSON_RE = _re_mod.compile(
    r"(?i)(\bthe user\b|\bthe person\b|\bthis user\b|"
    r"\b(?:his|her|their)\s+screen\b|\bthe human\b)"
)

# Third-person pronouns referring to a person.
_PERSON_PRONOUN_RE = _re_mod.compile(r"(?i)\b(they|them|their|theirs)\b|\bthey['’]")

# Words ending in -s that are verbs or mass nouns, not plural antecedents.
_NOT_PLURAL = {
    "is", "was", "has", "does", "goes", "says", "looks", "seems", "gets",
    "needs", "keeps", "runs", "works", "means", "makes", "takes", "gives",
    "this", "its", "less", "mess", "class", "pass", "across", "unless",
    "plus", "guess", "yes", "us", "as", "his", "hers", "always", "perhaps",
    "status", "focus", "progress", "process", "success", "business",
}
_PLURAL_RE = _re_mod.compile(r"\b([a-z]{3,}s)\b", _re_mod.IGNORECASE)


def _has_antecedent(text: str) -> bool:
    """Is there a plural noun BEFORE the first 'they' for it to refer to?

    This is what separates "Those imports? They're unused." (fine — "they" is
    the imports) from "…looks like they've got a mix of notes scattered
    around" (a leak — the only nouns are singular, so "they" is shaurya).
    """
    m = _PERSON_PRONOUN_RE.search(text)
    if not m:
        return True
    before = text[:m.start()]
    return any(w.lower() not in _NOT_PLURAL for w in _PLURAL_RE.findall(before))

# Direct address. If the line talks to him, a "they" in it is about something
# else ("your tests — they've been red a while") and is perfectly fine.
_SECOND_PERSON_RE = _re_mod.compile(r"(?i)\b(you|your|yours|you['’](?:re|ve|ll|d))\b")

# "I notice you're…" / "I can see that…" — narrating the act of observing
# instead of just saying the thing.
_OBSERVER_RE = _re_mod.compile(
    r"(?i)^(i (?:notice|see|can see|observe|noticed)\b|it (?:seems|appears|looks like) "
    r"(?:that )?the\b|looks like the user\b)"
)


def is_addressed_to_user(line: str) -> bool:
    """True if this line talks TO shaurya rather than ABOUT him.

    Two rules, because listing pronoun spellings kept losing. An earlier
    version enumerated "they're / they are / they've"… and the alternation had
    leading spaces on some branches, so `they've` sailed through and produced
    "looks like they've got a mix of notes scattered around" live.

    Rule 1: a few phrases are always a leak ("the user", "their screen").
    Rule 2: a third-person pronoun is a leak UNLESS the line either addresses
            him directly ("your tests — they've been red a while") or gives
            the pronoun a plural antecedent ("those imports? they're unused").
            With neither, "they" can only be him.
    """
    if not line or not line.strip():
        return False
    text = line.strip()
    if _THIRD_PERSON_RE.search(text):
        return False
    if _OBSERVER_RE.search(text):
        return False
    if _PERSON_PRONOUN_RE.search(text):
        if not _SECOND_PERSON_RE.search(text) and not _has_antecedent(text):
            return False
    return True


def clean_proactive_line(line: str) -> str | None:
    """Final gate for every unprompted line AURA says.

    Returns None when the line should be thrown away — the caller then falls
    back to a canned line, which is always better than narrating the user to
    himself in the third person.
    """
    if not line:
        return None
    text = sanitize_text(line)
    if not text:
        return None
    text = text.strip().strip('"').strip("'").strip()
    if not is_addressed_to_user(text):
        print(f"[AURA] discarded third-person proactive line: {text[:70]}")
        return None
    return text


# ── Vision ──────────────────────────────────────────────────────────────────
# Gemma 4 31B is already in the roster (it answers CASUAL/PERSONAL) and it is
# multimodal — text AND image in, on the free tier. So screenshot verification
# needs no new key and no new quota: it reuses OPENROUTER_KEY_CHAT.
# Overridable in .env for when a better free vision model shows up.
VISION_MODEL = os.getenv("AURA_VISION_MODEL", "google/gemma-4-31b-it:free")
# Second free multimodal model on OpenRouter. Gemma's free tier gets rate-
# limited fast (shared quota across everyone on the no-cost tier, not just
# AURA's usage) — when that happens verification shouldn't just fail, it
# should quietly try a different model before telling shaurya it couldn't
# look. Same OPENROUTER_KEY_CHAT key covers this one too; no new key needed.
VISION_FALLBACK_MODEL = os.getenv(
    "AURA_VISION_FALLBACK_MODEL", "nvidia/nemotron-3-nano-omni-30b:free"
)


def vision_available() -> bool:
    """False when there's no key for EITHER vision model — callers fall back
    rather than erroring."""
    _, _, key = _endpoint_for(VISION_MODEL)
    if key:
        return True
    _, _, key2 = _endpoint_for(VISION_FALLBACK_MODEL)
    return bool(key2)


def _call_vision_one(model_id: str, prompt: str, image_b64: str, system: str,
                      max_tokens: int, timeout: int) -> str:
    """One attempt against a single vision model. Same sentinel contract as
    call_vision (RATE_LIMIT / CONNECTION_ERROR / NO_VISION_KEY / text)."""
    provider, url, api_key = _endpoint_for(model_id)
    if not api_key:
        return "NO_VISION_KEY"
    cd_key = _cooldown_key(provider, model_id)
    if _in_rate_limit_cooldown(cd_key):
        return "RATE_LIMIT"

    content: list[dict] = [{"type": "text", "text": prompt}]
    content.append({
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
    })
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": content})

    try:
        response = requests.post(
            url,
            headers=_headers(provider, api_key),
            json={"model": model_id, "messages": messages,
                  "max_tokens": max_tokens, "temperature": 0.1},
            timeout=timeout,
        )
        if response.status_code == 429:
            _start_rate_limit_cooldown(cd_key)
            return "RATE_LIMIT"
        data = response.json()
        if "choices" not in data:
            print(f"[AURA vision] {provider} error {response.status_code}: "
                  f"{str(data)[:200]}")
            return "CONNECTION_ERROR"
        return (data["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:  # noqa: BLE001
        print(f"[AURA vision] {e}")
        return "CONNECTION_ERROR"


def call_vision(prompt: str, image_b64: str, system: str = "",
                max_tokens: int = 400, timeout: int = 60) -> str:
    """Ask a vision model about one image.

    Tries VISION_MODEL first, and if that comes back rate-limited (or has no
    key) falls through to VISION_FALLBACK_MODEL before giving up — the two
    free-tier quotas are independent, so a Gemma 429 doesn't have to mean
    "can't verify right now" if Nemotron's omni model is free.

    `image_b64` is raw base64 (no data: prefix). Returns the model's text, or
    one of the usual sentinels — RATE_LIMIT / CONNECTION_ERROR / NO_VISION_KEY
    — so the caller can tell "it said no" apart from "it never ran", which for
    a verification feature is the difference between rejecting your work and
    admitting AURA couldn't look. The sentinel returned is only ever RATE_LIMIT
    or NO_VISION_KEY if BOTH models failed that way.
    """
    tried = []
    last = "NO_VISION_KEY"
    for model_id in (VISION_MODEL, VISION_FALLBACK_MODEL):
        if model_id in tried:
            continue
        tried.append(model_id)
        result = _call_vision_one(model_id, prompt, image_b64, system,
                                   max_tokens, timeout)
        if result in ("RATE_LIMIT", "CONNECTION_ERROR", "NO_VISION_KEY"):
            if result != "NO_VISION_KEY":
                last = result
            elif last == "NO_VISION_KEY":
                last = result
            print(f"[AURA vision] {model_id} unavailable ({result}) — "
                  f"trying next model" if model_id == VISION_MODEL else
                  f"[AURA vision] {model_id} also unavailable ({result})")
            continue
        if model_id != VISION_MODEL:
            print(f"[AURA vision] answered by fallback model {model_id}")
        return result
    return last


def route_streaming(intent: str, prompt: str, system_prompt: str | None = None, model: str | None = None):
    extra = INTENT_PERSONALITY_ADJUSTMENTS.get(intent, "")
    if system_prompt is not None:
        system = system_prompt   # compiled plans stay untouched
    else:
        # relationship shapes the voice on Auto; nature overlay goes LAST so
        # a manual lock overrides everything (including relationship tone)
        system = (DONNA_SYSTEM_PROMPT + extra + _user_facts_block()
                  + _relationship_block() + _nature_overlay())

    # Resolve the model chain for this intent (or the explicit plan model),
    # with LOCKED models removed. Try each in order; if one is rate-limited or
    # errors before any content, fall through to the next (Groq is the safety
    # net). Only the very first sentinel-free stream is shown to the user.
    candidates = _resolve_candidates(intent, model)
    if not candidates:
        yield _ALL_LOCKED_MSG
        return

    last_sentinel = "CONNECTION_ERROR"
    for name, mid in candidates:
        try:
            from core import activity
            activity.emit(f"Routing to {name}…", "route")
        except Exception:  # noqa: BLE001
            pass
        gen = call_groq_streaming(prompt, system, intent=intent, model=mid)
        try:
            first = next(gen)
        except StopIteration:
            continue
        if first in ("RATE_LIMIT", "CONNECTION_ERROR"):
            last_sentinel = first
            print(f"[AURA] ⚠ {name} unavailable ({first}) — falling back")
            try:
                from core import activity
                activity.emit(f"{name} unavailable — falling back…", "route")
            except Exception:  # noqa: BLE001
                pass
            continue
        _set_last_model(mid)
        _announce_model(name, mid, intent)

        def _combined(first_chunk=first, rest=gen):
            yield first_chunk
            yield from rest

        yield from _sanitize_reasoning_stream(_combined())
        return
    yield last_sentinel
def call_groq_raw(prompt: str, system: str, max_tokens: int = 1024,
                  temperature: float = 0.4, model: str = None) -> str:
    """Clean single call — NO personality addon, NO 2-sentence limit,
    NO response cleaning. Used by the Prompt Maker (/prompt_end) and any
    future session mode that needs full-length structured output."""
    model_id = model or GROQ_MODEL
    provider, url, api_key = _endpoint_for(model_id)
    cd_key = _cooldown_key(provider, model_id)
    if _in_rate_limit_cooldown(cd_key):
        return "RATE_LIMIT"
    try:
        response = requests.post(
            url,
            headers=_headers(provider, api_key),
            json=_apply_reasoning_policy({
                "model": model_id,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False
            }, provider),
            timeout=45
        )
        if response.status_code == 429:
            _start_rate_limit_cooldown(cd_key)
            return "RATE_LIMIT"
        data = response.json()
        if "choices" not in data:
            print(f"[AURA] {provider} raw API error (status {response.status_code}): {data}")
            return "CONNECTION_ERROR"
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[AURA] {provider} raw error: {e}")
        return "CONNECTION_ERROR"


def call_groq(prompt: str, system: str = DONNA_SYSTEM_PROMPT, intent: str = "CASUAL", model: str = None) -> str:
    model_id = model or GROQ_MODEL
    provider, url, api_key = _endpoint_for(model_id)
    cd_key = _cooldown_key(provider, model_id)
    if _in_rate_limit_cooldown(cd_key):
        return "RATE_LIMIT"

    is_coding = (intent == "CODING")
    is_personal = (intent == "PERSONAL")
    is_explain = (intent == "EXPLAIN")
    is_longform = (intent in _LONGFORM_INTENTS)
    if is_coding:
        strict_system = system + _CODING_SYSTEM_ADDON
    elif is_explain:
        strict_system = system + _EXPLAIN_SYSTEM_ADDON
    elif is_longform:
        strict_system = system + _LONGFORM_SYSTEM_ADDON
    elif is_personal:
        strict_system = system + _PERSONAL_SYSTEM_ADDON
    else:
        strict_system = system + """

OVERRIDE ALL YOUR DEFAULT BEHAVIOR:
- MAX 2 sentences. Hard limit. Count them.
- NO emoji. Zero.
- NO "OMG", "Whoopsie", "Let's", "Together", "Great question", "Certainly"
- NO made-up context. Only refer to what's in the conversation.
- NEVER guess or make up content about videos, URLs, or links you cannot access.
- If asked about a URL say: "can't open that directly — paste the key points and I'll work with it."
- Talk like a sharp friend texting. Dry. Direct. No hype.
- NEVER end with a question unless you have zero info to work with.
"""
    try:
        response = requests.post(
            url,
            headers=_headers(provider, api_key),
            json=_apply_reasoning_policy({
                "model": model_id,
                "messages": [
                    {"role": "system", "content": strict_system},
                    {"role": "user",   "content": prompt}
                ],
                # Same ceiling as the streaming path — see the note there.
                "max_tokens": 2048 if (is_coding or is_longform) else (1024 if is_explain else (600 if is_personal else 400)),
                "temperature": 0.6 if is_longform else (0.5 if is_explain else (0.3 if is_coding else 0.7)),
                "stream": False
            }, provider),
            timeout=60 if (is_longform or is_explain) else 30
        )
        print(f"[AURA {provider} Debug] Status: {response.status_code} | Intent: {intent} | Model: {model_id}")

        if response.status_code == 429:
            _start_rate_limit_cooldown(cd_key)
            return "RATE_LIMIT"

        data = response.json()
        if "choices" not in data:
            print(f"[AURA] {provider} API error (status {response.status_code}): {data}")
            return "CONNECTION_ERROR"

        raw = data["choices"][0]["message"]["content"]
        if is_coding:
            print(f"[AURA CODE RAW]\n{raw}\n[END RAW]")
            return raw           # code is returned verbatim — never filtered
        # Every non-code lane gets the reasoning filter. These three used to
        # return raw.strip() because clean_response fused leak-stripping with
        # the 2-sentence clamp, so keeping the filter meant losing the length.
        # sanitize_text separates those concerns, so the long lanes can be
        # filtered without being truncated.
        if is_personal or is_explain or is_longform:
            # NOT query=prompt: `prompt` here is the whole built context, which
            # now carries the project block. A legitimate answer quoting a task
            # title back would trip _echoes_query and get deleted as a leak.
            cleaned = sanitize_text(raw)
            if not cleaned:
                note_leak("non-streaming lane")
                return "THINKING_LEAK"
            if cleaned != raw.strip():
                note_leak("non-streaming lane", repaired=True)
            return cleaned
        return clean_response(raw)
    except Exception as e:
        print(f"[AURA] {provider} error: {e}")
        return "CONNECTION_ERROR"
