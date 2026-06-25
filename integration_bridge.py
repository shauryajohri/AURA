"""
AURA Prompt Engine — Integration Bridge
Shows how to replace the raw "User → LLM" flow in AuraAppController
with the new pipeline.

==========================================================================
BEFORE (current app.py or brain.py):

    def handle_user_message(self, text: str):
        response = call_llm(text)
        self.main_window.append_message(response, "AURA")

==========================================================================
AFTER (with Prompt Engine):

    def handle_user_message(self, text: str):
        engine_result = self.prompt_engine.process(text)
        summary = engine_result.summary_dict()

        # Show the approval panel — LLM is NOT called yet
        self.plan_panel.show_plan(summary)

        # Store result so we can use it after approval
        self._pending_engine_result = engine_result

    def _on_plan_approved(self, summary: dict):
        if self._pending_engine_result is None:
            return
        model_id, system_prompt, user_prompt = \\
            self.prompt_engine.approve_and_execute(self._pending_engine_result)

        # Now call the actual LLM with the compiled prompt
        response = call_llm(
            model=model_id,
            system=system_prompt,
            user=user_prompt,
        )
        self.main_window.append_message(response, "AURA")
        self._pending_engine_result = None

    def _on_plan_rejected(self):
        self._pending_engine_result = None
        self.main_window.append_message(
            "OK, cancelled. What would you like to do instead?", "AURA"
        )

==========================================================================

FULL INTEGRATION EXAMPLE — drop into your AuraAppController.__init__:
"""

from typing import Optional
from core.prompt_engine import PromptEngine, EngineResult


class PromptEngineBridge:
    """
    Mixin / helper you can compose into AuraAppController.
    Keeps the pending result and wires signals.
    """

    def __init__(self):
        self.prompt_engine = PromptEngine()
        self._pending_result: Optional[EngineResult] = None

    # ------------------------------------------------------------------
    # Call this instead of calling the LLM directly
    # ------------------------------------------------------------------

    def process_with_engine(self, user_input: str) -> dict:
        """
        Run the full pipeline and return a summary dict for the UI panel.
        Does NOT call the LLM.
        """
        result = self.prompt_engine.process(user_input)
        self._pending_result = result
        return result.summary_dict()

    # ------------------------------------------------------------------
    # Connect these to your panel signals
    # ------------------------------------------------------------------

    def on_plan_approved(self) -> tuple[str, str, str]:
        """
        Returns (model_id, system_prompt, user_prompt) ready for LLM call.
        Call your LLM with these three values.
        """
        if self._pending_result is None:
            raise RuntimeError("No pending engine result to approve.")
        model_id, system_prompt, user_prompt = \
            self.prompt_engine.approve_and_execute(self._pending_result)
        self._pending_result = None
        return model_id, system_prompt, user_prompt

    def on_plan_rejected(self) -> None:
        """Cancel the pending plan."""
        self._pending_result = None

    def on_plan_edited(self, updated_summary: dict) -> None:
        """
        Update the pending plan with user edits from the panel.
        Currently updates the goal; extend as needed.
        """
        if self._pending_result is None:
            return
        if "goal" in updated_summary:
            self._pending_result.plan.goal = updated_summary["goal"]
        if "steps" in updated_summary:
            for step_data in updated_summary["steps"]:
                for step in self._pending_result.plan.steps:
                    if step.index == step_data["index"]:
                        step.done = step_data.get("done", step.done)
