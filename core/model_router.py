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
# Routing table
# Entries are checked in order; first match wins.
# Each entry: (max_complexity, domain_filter, model_id, display_name, reason, cost)
# domain_filter=None means "any domain"
# ---------------------------------------------------------------------------

# These are REAL Groq model ids — the selection is actually dispatched
# (ui/app.py passes model_id through to ai_router.call_groq). Domain rules
# come FIRST so they genuinely take precedence over the generic tiers.

ROUTING_TABLE = [
    # Research tasks always go to the big model regardless of complexity
    (101, "RESEARCH", "llama-3.3-70b-versatile", "Llama 3.3 70B (Groq)",
     "Research tasks need broad knowledge and nuanced reasoning",
     "free tier"),

    # Coding always goes to the big model
    (101, "CODING", "llama-3.3-70b-versatile", "Llama 3.3 70B (Groq)",
     "Code changes need strong reasoning and context retention",
     "free tier"),

    # Fast, cheap model for trivial tasks
    (30, None, "llama-3.1-8b-instant", "Llama 3.1 8B Instant (Groq)",
     "Simple task — the small instant model is faster",
     "free tier"),

    # Everything else
    (101, None, "llama-3.3-70b-versatile", "Llama 3.3 70B (Groq)",
     "Default — full-size model handles the whole context",
     "free tier"),
]

DEFAULT_MODEL_ID = "llama-3.3-70b-versatile"


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
