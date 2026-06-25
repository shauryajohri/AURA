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

ROUTING_TABLE = [
    # Fast, cheap model for trivial tasks
    (30, None, "qwen3-coder", "Qwen3-Coder",
     "Simple task — lightweight coder model is fast and cheap",
     "~$0.00"),

    # Mid-tier for moderate complexity
    (70, None, "minimax", "MiniMax",
     "Moderate task — balanced performance and cost",
     "~$0.01–$0.03"),

    # Research tasks always go to Claude regardless of complexity
    (101, "RESEARCH", "claude-sonnet-4-6", "Claude",
     "Research tasks need broad knowledge and nuanced reasoning",
     "~$0.03–$0.08"),

    # High-complexity coding
    (101, "CODING", "claude-sonnet-4-6", "Claude",
     "Complex code changes need strong reasoning and context retention",
     "~$0.04–$0.10"),

    # Everything else at high complexity
    (101, None, "claude-sonnet-4-6", "Claude",
     "High complexity — Claude handles the full context well",
     "~$0.05–$0.12"),
]


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
        model_id="claude-sonnet-4-6",
        display_name="Claude",
        reason="Fallback for unmatched routing",
        estimated_cost="~$0.05",
    )
