"""
AURA Prompt Engine — Step 5: Prompt Compiler
Assembles the final, clean, structured prompt from plan + context.
This is what gets sent to the model — not the raw user input.
"""

from core.planner import ExecutionPlan
from core.context_builder import ContextResult


DOMAIN_REQUIREMENTS = {
    "CODING": [
        "Only modify sections directly relevant to the task.",
        "Explain your reasoning briefly before writing code.",
        "Preserve existing code style and patterns.",
        "Do not break any imports or interfaces that aren't being changed.",
    ],
    "RESEARCH": [
        "Cite sources where possible.",
        "Distinguish between established facts and your own synthesis.",
        "Keep the response structured with clear headings.",
    ],
    "WRITING": [
        "Match the requested tone and audience.",
        "Be concise — eliminate filler.",
        "Use active voice by default.",
    ],
    "SYSTEM": [
        "Provide exact commands — no placeholders.",
        "Warn about any potentially destructive steps.",
        "Include a verification step.",
    ],
    "PLANNING": [
        "Break down into concrete, actionable tasks.",
        "Identify dependencies between tasks.",
        "Flag risks or unknowns explicitly.",
    ],
    "GENERAL": [
        "Be specific and direct.",
        "Explain your reasoning.",
    ],
}


def compile_prompt(plan: ExecutionPlan, context: ContextResult) -> str:
    """Build the full structured prompt string to send to the LLM."""
    lines = []

    # --- Project header ---
    if plan.project:
        lines.append(f"Project: {plan.project}")
        lines.append("")

    # --- Active file ---
    if context.active_file:
        lines.append(f"Current File: {context.active_file}")
        lines.append("")

    # --- Files affected ---
    if plan.files_affected:
        lines.append("Files Involved:")
        for f in plan.files_affected:
            lines.append(f"  - {f}")
        lines.append("")

    # --- Session goal context ---
    if context.session_goal and context.session_goal.lower() != plan.goal.lower():
        lines.append(f"Session Context: {context.session_goal}")
        lines.append("")

    # --- Primary task ---
    lines.append(f"Task: {plan.goal}")
    lines.append("")

    # --- Execution steps ---
    lines.append("Execution Plan:")
    for step in plan.steps:
        status = "✓" if step.done else "□"
        lines.append(f"  {status} {step.index}. {step.title} — {step.description}")
    lines.append("")

    # --- Domain-specific requirements ---
    requirements = DOMAIN_REQUIREMENTS.get(plan.domain, DOMAIN_REQUIREMENTS["GENERAL"])
    lines.append("Requirements:")
    for req in requirements:
        lines.append(f"  - {req}")
    lines.append("")

    # --- Output instruction ---
    lines.append("Respond with your solution. Follow the execution plan steps in order.")

    return "\n".join(lines)


def compile_system_prompt(plan: ExecutionPlan) -> str:
    """Build a system prompt that primes the model for this task type."""
    domain_priming = {
        "CODING": (
            "You are an expert software engineer. You write clean, minimal, "
            "well-reasoned code. You explain your changes concisely and never "
            "modify code outside the scope of the task."
        ),
        "RESEARCH": (
            "You are a rigorous research assistant. You synthesize information "
            "accurately, cite your sources, and clearly distinguish facts from "
            "interpretation."
        ),
        "WRITING": (
            "You are a skilled writer. You produce clear, direct, purposeful prose "
            "matched to the requested tone and audience."
        ),
        "SYSTEM": (
            "You are a precise systems engineer. You provide exact, tested commands "
            "and always include verification steps."
        ),
        "PLANNING": (
            "You are a clear-headed technical planner. You break down goals into "
            "concrete tasks, identify dependencies, and flag risks."
        ),
        "GENERAL": (
            "You are a highly capable AI assistant. Be direct, specific, and helpful."
        ),
    }

    base = domain_priming.get(plan.domain, domain_priming["GENERAL"])

    if plan.project:
        base += f" You are working within the {plan.project} project."

    return base
