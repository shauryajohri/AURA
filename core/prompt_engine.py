"""
AURA Prompt Engine — Orchestrator
Ties together all 5 pipeline stages:
  1. Intent Analyzer
  2. Context Builder
  3. Planner
  4. Model Router
  5. Prompt Compiler

Usage:
    from core.prompt_engine import PromptEngine

    engine = PromptEngine()
    result = engine.process("Improve my proactive system")
    # result.plan  → ExecutionPlan (show to user for approval)
    # result.prompt → str (final prompt to send to LLM)
    # result.system_prompt → str (system prompt for LLM)
    # result.model_id → str (model to use)
"""

from dataclasses import dataclass

from core.intent_analyzer import analyze_intent, IntentResult
from core.context_builder import build_context, ContextResult
from core.planner import create_plan, ExecutionPlan
from core.model_router import select_model, ModelSelection
from core.prompt_compiler import compile_prompt, compile_system_prompt


@dataclass
class EngineResult:
    raw_input: str
    intent: IntentResult
    context: ContextResult
    plan: ExecutionPlan
    model: ModelSelection
    prompt: str
    system_prompt: str

    @property
    def model_id(self) -> str:
        return self.model.model_id

    def summary_dict(self) -> dict:
        """Flat dict suitable for logging or the approval panel."""
        return {
            "goal": self.plan.goal,
            "domain": self.plan.domain,
            "project": self.plan.project,
            "steps": [
                {"index": s.index, "title": s.title, "done": s.done}
                for s in self.plan.steps
            ],
            "files_affected": self.plan.files_affected,
            "complexity": self.plan.complexity,
            "complexity_label": self.plan.complexity_label,
            "model": self.model.display_name,
            "estimated_cost": self.plan.estimated_cost,
            "approved": self.plan.approved,
        }


class PromptEngine:
    """
    Main entry point for the AURA Prompt Engine pipeline.

    Call process() to run all stages and get a result ready for the
    approval panel. Call execute() after user approval to get the
    final prompt + model for the LLM call.
    """

    def process(self, user_input: str) -> EngineResult:
        """Run all pipeline stages. Returns plan for user approval."""
        # Stage 1: Intent
        intent = analyze_intent(user_input)

        # Stage 2: Context
        context = build_context(goal=intent.goal, project=intent.project)

        # Stage 3: Plan
        plan = create_plan(intent, context)

        # Stage 4: Model selection
        model = select_model(intent.complexity, intent.intent)
        # Sync model info back into the plan for display
        plan.recommended_model = model.display_name
        plan.estimated_cost = model.estimated_cost

        # Stage 5: Compile prompt
        prompt = compile_prompt(plan, context)
        system_prompt = compile_system_prompt(plan)

        return EngineResult(
            raw_input=user_input,
            intent=intent,
            context=context,
            plan=plan,
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
        )

    def approve_and_execute(self, result: EngineResult) -> tuple[str, str, str]:
        """
        Mark plan as approved and return (model_id, system_prompt, user_prompt).
        Pass these directly to your LLM API call.
        """
        result.plan.approved = True
        return result.model_id, result.system_prompt, result.prompt
