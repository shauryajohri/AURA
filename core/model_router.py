"""
AURA Prompt Engine — Step 4: Model Router
Selects the appropriate model based on task complexity and domain.
Can be extended with per-domain overrides and user preferences.
"""

from dataclasses import dataclass


@dataclass
class ModelSelection:
    model_id: str
    display_name: str
    reason: str
    estimated_cost: str


# ---------------------------------------------------------------------------
# Model roster — the single source of truth for the real models AURA can use.
# The DISPLAY NAME is the shared key: it must match the planet names
# (frontend/src/data/models.ts, server._MODELS) and the lock keys
# (core/model_lock), so a locked planet in the UI maps to a model the router
# will actually skip.
#
# EVERY model here is free — an OpenRouter ":free" endpoint or Groq's free
# tier — and each was live-tested with AURA's own request shape on 2026-09-14.
#
# Laguna M.1 (poolside/laguna-m.1:free) used to be the coding model. It left
# OpenRouter's free tier: every CODING turn 404'd ("No endpoints found") and
# fell through to GPT-OSS. North Mini Code and Laguna XS 2.1 replace it.
# Nemotron 3.5 Lightning was tried as the research backup and dropped: it
# spends its budget thinking — 35s to the first token, 122s for one answer.
#
# Provider comes from ai_router.GROQ_MODEL_IDS — an explicit allow-list.
# It is NOT inferred from the id shape any more: Groq's current ids
# ("openai/gpt-oss-120b") contain a "/" just like OpenRouter's do.
# ---------------------------------------------------------------------------

# display name → model id
MODELS = {
    # OpenRouter, free tier
    "North Mini Code":    "cohere/north-mini-code:free",
    "Laguna XS 2.1":      "poolside/laguna-xs-2.1:free",
    "Nemotron 3 Super":   "nvidia/nemotron-3-super-120b-a12b:free",
    "Dots 3 Note":        "dots-studio/dots-3-note-preview:free",   # preview release
    "Gemma 4 31B":        "google/gemma-4-31b-it:free",     # sees images too
    "Nex N2.5 Pro":       "nex-agi/nex-n2.5-pro:free",
    "Nemotron Nano Omni": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "Ling 3.0 Flash VL":  "inclusionai/ling-3.0-flash-vl:free",
    # Groq, free tier
    "Qwen3.8 27B":        "qwen/qwen3.8-27b",
    "GPT-OSS 120B":       "openai/gpt-oss-120b",        # fallback / heavy
    "GPT-OSS 20B":        "openai/gpt-oss-20b",         # fast / light
}
NAME_FOR_ID = {mid: name for name, mid in MODELS.items()}

# Which OPENROUTER_KEY_<SLOT> each OpenRouter model draws from; ai_router uses
# the shared OPENROUTER_API_KEY when that slot is blank. Vision rides on the
# CHAT key, as it always has.
OPENROUTER_KEY_SLOT = {
    MODELS["North Mini Code"]:    "CODING",
    MODELS["Laguna XS 2.1"]:      "CODING",
    MODELS["Nemotron 3 Super"]:   "RESEARCH",
    MODELS["Dots 3 Note"]:        "RESEARCH",
    MODELS["Gemma 4 31B"]:        "CHAT",
    MODELS["Nex N2.5 Pro"]:       "CHAT",
    MODELS["Nemotron Nano Omni"]: "CHAT",
    MODELS["Ling 3.0 Flash VL"]:  "CHAT",
}

# The two GPT-OSS models are the always-available fallback chain (fast + free),
# used when every model in an intent's chain is locked, rate-limited, or errors.
# These replaced llama-3.3-70b-versatile / llama-3.1-8b-instant, which Groq
# decommissioned on 2026-08-16 (they started 404-ing mid-conversation and
# took the whole fallback chain down with them).
GROQ_FALLBACKS = [
    ("GPT-OSS 120B", MODELS["GPT-OSS 120B"]),
    ("GPT-OSS 20B",  MODELS["GPT-OSS 20B"]),
]

# Groq rate limits are PER MODEL, so each GPT-OSS model gets a Groq backup with
# its own quota. Used by the direct Groq calls (classifier, memory, nudges,
# planning) that don't run through an intent chain.
GROQ_BACKUPS = {
    MODELS["GPT-OSS 120B"]: [MODELS["Qwen3.8 27B"], MODELS["GPT-OSS 20B"]],
    MODELS["GPT-OSS 20B"]:  [MODELS["Qwen3.8 27B"]],
}

# intent → models to try in order (display names). Every chain has at least
# two free models ahead of the Groq safety net, so one rate-limited model
# never decides whether AURA can answer. Dots 3 Note backs up research only:
# in the 400-token chat lane its hidden thinking uses the whole budget and it
# streams no reply (checked 2026-09-14), so chat falls to Nex instead.
_CODING   = ["North Mini Code", "Laguna XS 2.1", "Qwen3.8 27B"]
_THINKING = ["Nemotron 3 Super", "Dots 3 Note"]
_CHAT     = ["Gemma 4 31B", "Nex N2.5 Pro"]

INTENT_CHAIN = {
    "CODING":     _CODING,
    "RESEARCH":   _THINKING,
    "SEARCH":     _THINKING,
    "PLAN":       _THINKING,   # roadmaps need long-horizon reasoning
    "EXPLAIN":    _THINKING,   # teaching needs depth, not chat vibes
    "DISCUSSION": _CHAT,       # opinionated brainstorming
    "CASUAL":     _CHAT,
    "PERSONAL":   _CHAT,
}
# intent → lead model, for callers that only show the first pick (web demo).
INTENT_PRIMARY = {intent: chain[0] for intent, chain in INTENT_CHAIN.items()}

# Image questions (quest verification). ai_router uses these as defaults;
# AURA_VISION_MODEL / _FALLBACK_MODEL / _THIRD_MODEL in .env override them.
VISION_CHAIN = ["Gemma 4 31B", "Nemotron Nano Omni", "Ling 3.0 Flash VL"]

# Background calls — classifier, memory, curiosity and attention nudges.
BACKGROUND_CHAIN = ["GPT-OSS 20B", "Qwen3.8 27B"]

# job → chain, as the Models page shows it. Speech isn't here: listening runs
# on Groq Whisper (ai_router.WHISPER_MODELS) and speaking on edge-tts with the
# offline Windows voice behind it (modules/voice_output).
_GROQ_NAMES = [name for name, _ in GROQ_FALLBACKS]
JOB_CHAINS = {
    "Coding":     _CODING + _GROQ_NAMES,
    "Research":   _THINKING + _GROQ_NAMES,
    "Chat":       _CHAT + _GROQ_NAMES,
    "Vision":     VISION_CHAIN,
    "Background": BACKGROUND_CHAIN,
}


def name_for_id(model_id: str):
    name = NAME_FOR_ID.get(model_id)
    if name is None and model_id and model_id.startswith("ext:"):
        name = _integrations().name_for(model_id)
    return name


def groq_fallbacks() -> list:
    """[(name, id)] Groq chain — always the safety net."""
    return list(GROQ_FALLBACKS)


# ---------------------------------------------------------------------------
# Installed planets (core/integrations): models the user added by pasting a
# key or a link. Each is ticked for some jobs and sits either in FRONT of that
# job's built-in chain ("first") or behind it ("backup"), always ahead of the
# Groq safety net. Their ids are "ext:<n>"; ai_router resolves the endpoint.
# ---------------------------------------------------------------------------
_INTENT_JOB = {
    "CODING": "Coding",
    "RESEARCH": "Research", "SEARCH": "Research", "PLAN": "Research", "EXPLAIN": "Research",
    "DISCUSSION": "Chat", "CASUAL": "Chat", "PERSONAL": "Chat",
}


def _integrations():
    from core import integrations
    return integrations


def installed_for(job: str) -> tuple[list, list]:
    """([(name, id)] to try first, [(name, id)] backups) for one job."""
    try:
        rows = _integrations().routed(job)
    except Exception as e:  # noqa: BLE001 — a broken table must not stop routing
        print(f"[AURA] installed planets skipped: {e}")
        return [], []
    first = [(n, i) for n, i, pos in rows if pos == "first"]
    backup = [(n, i) for n, i, pos in rows if pos != "first"]
    return first, backup


def job_chains() -> dict:
    """JOB_CHAINS with installed planets slotted in, as the Models page shows."""
    out = {}
    for job, chain in JOB_CHAINS.items():
        first, backup = installed_for(job)
        names = [n for n, _ in first] + list(chain)
        if job in ("Coding", "Research", "Chat"):
            # built-in chains end in the Groq safety net; backups go before it
            tail = [n for n in names if n in _GROQ_NAMES]
            names = [n for n in names if n not in _GROQ_NAMES] + [n for n, _ in backup] + tail
        else:
            names += [n for n, _ in backup]
        out[job] = names
    return out


def jobs_for(name: str) -> list:
    """[{"job", "rank"}] for every job whose chain includes `name`; rank 1 is
    the model tried first."""
    return [{"job": job, "rank": chain.index(name) + 1}
            for job, chain in job_chains().items() if name in chain]


def candidates_for(intent: str) -> list:
    """Ordered [(name, id)] the router should try for this intent: installed
    "first" planets, the intent's chain, installed backups, then the Groq
    fallback chain. De-duped by id. Lock filtering happens later in ai_router."""
    names = INTENT_CHAIN.get(intent, _CHAT)
    first, backup = installed_for(_INTENT_JOB.get(intent, "Chat"))
    chain = first + [(name, MODELS[name]) for name in names] + backup + GROQ_FALLBACKS
    seen, out = set(), []
    for name, mid in chain:
        if mid in seen:
            continue
        seen.add(mid)
        out.append((name, mid))
    return out


# ---------------------------------------------------------------------------
# Routing table
# Entries are checked in order; first match wins.
# Each entry: (max_complexity, domain_filter, model_id, display_name, reason, cost)
# domain_filter=None means "any domain"
# ---------------------------------------------------------------------------

# The selection is actually dispatched (ui/app.py passes model_id through to
# ai_router, which leads with it, then walks that intent's normal chain with
# locks applied). Domain rules come FIRST so they take precedence over tiers.

ROUTING_TABLE = [
    # Research → Nemotron 3 Super (262K context, long-horizon reasoning)
    (101, "RESEARCH", MODELS["Nemotron 3 Super"], "Nemotron 3 Super",
     "Research needs broad knowledge and long-context reasoning",
     "OpenRouter free"),

    # Coding → North Mini Code (purpose-built code model)
    (101, "CODING", MODELS["North Mini Code"], "North Mini Code",
     "Purpose-built coding model with tool calling and long context",
     "OpenRouter free"),

    # Fast, cheap model for trivial tasks — stays on Groq's instant model
    (30, None, MODELS["GPT-OSS 20B"], "GPT-OSS 20B",
     "Simple task — the small instant model is faster",
     "Groq free"),

    # Everything else → Gemma 4 31B (general assistant)
    (101, None, MODELS["Gemma 4 31B"], "Gemma 4 31B",
     "Default general assistant for everyday chat",
     "OpenRouter free"),
]

DEFAULT_MODEL_ID = MODELS["Gemma 4 31B"]


_DOMAIN_JOB = {"CODING": "Coding", "RESEARCH": "Research", "PLANNING": "Research"}


def select_model(complexity: int, domain: str = "GENERAL") -> ModelSelection:
    """Return the best model for a given complexity + domain combination."""
    # A planet the user installed as "first pick" for this job wins — the plan
    # engine passes its choice as an explicit lead model, which would
    # otherwise jump ahead of it. Trivial general tasks keep the fast model.
    job = _DOMAIN_JOB.get(domain, "Chat")
    if job != "Chat" or complexity >= 30:
        first, _ = installed_for(job)
        if first:
            name, mid = first[0]
            return ModelSelection(model_id=mid, display_name=name,
                                  reason=f"You installed it as first pick for {job}",
                                  estimated_cost="installed planet")
    for max_c, domain_filter, model_id, display_name, reason, cost in ROUTING_TABLE:
        if complexity < max_c:
            if domain_filter is None or domain_filter == domain:
                return ModelSelection(
                    model_id=model_id,
                    display_name=display_name,
                    reason=reason,
                    estimated_cost=cost,
                )
    # Fallback
    return ModelSelection(
        model_id=DEFAULT_MODEL_ID,
        # Must describe DEFAULT_MODEL_ID — it used to say "Llama 3.3 70B
        # (Groq)" while actually dispatching Gemma, so the UI chip lied.
        display_name=NAME_FOR_ID.get(DEFAULT_MODEL_ID, "Gemma 4 31B"),
        reason="Fallback for unmatched routing",
        estimated_cost="free tier",
    )
