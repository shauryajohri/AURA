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
# The DISPLAY NAME is the shared key: it must match the cosmos planet names
# (ui/cosmos_panel.PLANETS) and the lock keys (core/model_lock), so a locked
# planet in the UI maps to a model the router will actually skip.
#
# Provider is inferred from the id: an OpenRouter id contains a "/",
# a Groq id does not.
# ---------------------------------------------------------------------------

# display name → model id
MODELS = {
    "Laguna M.1":       "poolside/laguna-m.1:free",
    "Nemotron 3 Super": "nvidia/nemotron-3-super-120b-a12b:free",
    "Gemma 4 31B":      "google/gemma-4-31b-it:free",
    "Llama 3.3 70B":    "llama-3.3-70b-versatile",   # Groq (fallback / heavy)
    "Llama 3.1 8B":     "llama-3.1-8b-instant",       # Groq (fast / light)
}
NAME_FOR_ID = {mid: name for name, mid in MODELS.items()}

# The two Groq models are the always-available fallback chain (fast + free),
# used when the primary OpenRouter pick is locked, rate-limited, or errors.
GROQ_FALLBACKS = [
    ("Llama 3.3 70B", MODELS["Llama 3.3 70B"]),
    ("Llama 3.1 8B",  MODELS["Llama 3.1 8B"]),
]

# intent → primary model (display name)
INTENT_PRIMARY = {
    "CODING":     "Laguna M.1",
    "RESEARCH":   "Nemotron 3 Super",
    "SEARCH":     "Nemotron 3 Super",
    "PLAN":       "Nemotron 3 Super",   # roadmaps need long-horizon reasoning
    "DISCUSSION": "Gemma 4 31B",        # opinionated brainstorming
    "CASUAL":     "Gemma 4 31B",
    "PERSONAL":   "Gemma 4 31B",
}


def name_for_id(model_id: str):
    return NAME_FOR_ID.get(model_id)


def groq_fallbacks() -> list:
    """[(name, id)] Groq chain — always the safety net."""
    return list(GROQ_FALLBACKS)


def candidates_for(intent: str) -> list:
    """Ordered [(name, id)] the router should try for this intent: the
    intent's primary model first, then the Groq fallback chain. De-duped by
    id. Lock filtering happens later in ai_router."""
    primary_name = INTENT_PRIMARY.get(intent, "Gemma 4 31B")
    chain = [(primary_name, MODELS[primary_name])] + GROQ_FALLBACKS
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
# ai_router, which now picks the OpenRouter or Groq endpoint by id and applies
# lock/fallback). Domain rules come FIRST so they take precedence over tiers.

ROUTING_TABLE = [
    # Research → Nemotron 3 Super (1M context, long-horizon reasoning)
    (101, "RESEARCH", MODELS["Nemotron 3 Super"], "Nemotron 3 Super",
     "Research needs broad knowledge and long-context reasoning",
     "OpenRouter free"),

    # Coding → Laguna M.1 (purpose-built coding agent)
    (101, "CODING", MODELS["Laguna M.1"], "Laguna M.1",
     "Purpose-built coding model with tool calling and long context",
     "OpenRouter free"),

    # Fast, cheap model for trivial tasks — stays on Groq's instant model
    (30, None, MODELS["Llama 3.1 8B"], "Llama 3.1 8B",
     "Simple task — the small instant model is faster",
     "Groq free"),

    # Everything else → Gemma 4 31B (general assistant)
    (101, None, MODELS["Gemma 4 31B"], "Gemma 4 31B",
     "Default general assistant for everyday chat",
     "OpenRouter free"),
]

DEFAULT_MODEL_ID = MODELS["Gemma 4 31B"]


def select_model(complexity: int, domain: str = "GENERAL") -> ModelSelection:
    """Return the best model for a given complexity + domain combination."""
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
        display_name="Llama 3.3 70B (Groq)",
        reason="Fallback for unmatched routing",
        estimated_cost="free tier",
    )
