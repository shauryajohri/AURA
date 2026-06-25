"""
AURA Prompt Engine — Quick Test (no UI, no LLM call)
Run: python test_engine.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from core.prompt_engine import PromptEngine


def run_test(user_input: str):
    print("\n" + "═" * 60)
    print(f"INPUT: {user_input!r}")
    print("═" * 60)

    engine = PromptEngine()
    result = engine.process(user_input)
    s = result.summary_dict()

    print(f"\nGoal:              {s['goal']}")
    print(f"Domain:            {s['domain']}  (confidence: {result.intent.domain_confidence})")
    print(f"Project:           {s['project'] or '(none detected)'}")
    print(f"Complexity:        {s['complexity']} → {s['complexity_label']}")
    print(f"Model:             {s['model']}")
    print(f"Est. Cost:         {s['estimated_cost']}")
    print(f"\nSteps:")
    for step in s['steps']:
        icon = "✓" if step['done'] else "□"
        print(f"  {icon} {step['index']}. {step['title']}")
    print(f"\nFiles Affected:    {', '.join(s['files_affected']) or '(none)'}")

    print("\n--- COMPILED PROMPT ---")
    print(result.prompt)
    print("\n--- SYSTEM PROMPT ---")
    print(result.system_prompt)


if __name__ == "__main__":
    run_test("Improve my proactive system")
    run_test("Fix the memory bug in brain.py")
    run_test("Explain how the session memory module works")
    run_test("Add cooldown logic to proactive.py")
