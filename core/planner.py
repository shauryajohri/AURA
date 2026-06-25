"""
AURA Prompt Engine — Step 3: Planner
Generates a structured, step-by-step execution plan based on intent + context.
"""

from dataclasses import dataclass, field
from typing import Optional

from core.intent_analyzer import IntentResult
from core.context_builder import ContextResult


@dataclass
class ExecutionStep:
    index: int
    title: str
    description: str
    done: bool = False


@dataclass
class ExecutionPlan:
    goal: str
    domain: str
    project: Optional[str]
    steps: list[ExecutionStep]
    files_affected: list[str]
    complexity: int
    complexity_label: str  # Low / Medium / High
    recommended_model: str
    estimated_cost: str
    approved: bool = False


# ---------------------------------------------------------------------------
# Step templates per domain
# ---------------------------------------------------------------------------

STEP_TEMPLATES = {
    "CODING": [
        ("Analyze", "Read and understand the current implementation"),
        ("Identify Issues", "Pinpoint exactly what needs to change and why"),
        ("Design", "Draft the improved logic or architecture"),
        ("Implement", "Write the updated code, touching only relevant sections"),
        ("Test", "Verify the change works and doesn't break existing behaviour"),
    ],
    "RESEARCH": [
        ("Define Scope", "Clarify what exactly needs to be researched"),
        ("Gather Sources", "Identify relevant, credible sources"),
        ("Synthesize", "Extract key insights and reconcile conflicting info"),
        ("Summarize", "Present findings in a clear, structured format"),
    ],
    "WRITING": [
        ("Outline", "Create a structure for the piece"),
        ("Draft", "Write the first full version"),
        ("Refine", "Edit for clarity, tone, and conciseness"),
        ("Finalize", "Polish and format the final output"),
    ],
    "SYSTEM": [
        ("Diagnose", "Identify the current system state and the target state"),
        ("Plan Changes", "Determine the exact commands or config changes needed"),
        ("Execute", "Apply the changes carefully"),
        ("Verify", "Confirm the system behaves as expected"),
    ],
    "PLANNING": [
        ("Understand Goals", "Clarify what success looks like"),
        ("Break Down", "Decompose the goal into concrete tasks"),
        ("Sequence", "Order tasks by dependency and priority"),
        ("Document", "Produce a clear, shareable plan"),
    ],
    "GENERAL": [
        ("Understand", "Clarify the request fully"),
        ("Plan", "Outline the approach"),
        ("Execute", "Carry out the work"),
        ("Review", "Check the result against the original goal"),
    ],
}

MODEL_ROUTING = [
    (30,  "qwen3-coder",  "Near-zero",  "$0.00–$0.01"),
    (70,  "minimax",      "Low",         "$0.01–$0.03"),
    (85,  "claude",       "Low–Medium",  "$0.03–$0.06"),
    (101, "claude",       "Medium",      "$0.05–$0.10"),
]

COMPLEXITY_LABELS = {
    (0, 30):  "Low",
    (30, 70): "Medium",
    (70, 101): "High",
}


def _complexity_label(score: int) -> str:
    for (lo, hi), label in COMPLEXITY_LABELS.items():
        if lo <= score < hi:
            return label
    return "High"


def _route_model(complexity: int) -> tuple[str, str, str]:
    for threshold, model, cost_label, cost_range in MODEL_ROUTING:
        if complexity < threshold:
            return model, cost_label, cost_range
    return "claude", "Medium", "$0.05–$0.10"


def create_plan(intent: IntentResult, context: ContextResult) -> ExecutionPlan:
    """Produce a full execution plan from analyzed intent and runtime context."""
    domain = intent.intent
    templates = STEP_TEMPLATES.get(domain, STEP_TEMPLATES["GENERAL"])

    # Build steps
    steps = [
        ExecutionStep(index=i + 1, title=title, description=desc)
        for i, (title, desc) in enumerate(templates)
    ]

    # Files affected
    files = context.recent_files or []

    # Model routing
    model, cost_label, cost_range = _route_model(intent.complexity)

    return ExecutionPlan(
        goal=intent.goal,
        domain=domain,
        project=intent.project or context.project,
        steps=steps,
        files_affected=files,
        complexity=intent.complexity,
        complexity_label=_complexity_label(intent.complexity),
        recommended_model=model,
        estimated_cost=cost_range,
    )
