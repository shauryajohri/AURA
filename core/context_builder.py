"""
AURA Prompt Engine — Step 2: Context Builder
Gathers runtime context: focused app, active project, relevant files,
and any existing session goal from AURA's memory module.
"""

import os
import subprocess
from dataclasses import dataclass, field
from typing import Optional

# Optional AURA memory import — gracefully degrades if not available
try:
    from modules.session_memory import get_session_goal  # type: ignore
except ImportError:
    def get_session_goal() -> Optional[str]:
        return None

def get_context() -> dict:
    try:
        from core.brain import get_context as brain_get_context  # type: ignore
        return brain_get_context()
    except Exception:
        return {}


@dataclass
class ContextResult:
    focused_app: str
    project: Optional[str]
    active_file: Optional[str]
    session_goal: Optional[str]
    recent_files: list[str] = field(default_factory=list)
    raw_context: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# File relevance mapping
# ---------------------------------------------------------------------------

FILE_DOMAIN_MAP = {
    "proactive": "proactive.py",
    "memory": "memory.py",
    "brain": "brain.py",
    "session": "session_memory.py",
    "voice": "voice_output.py",
    "ui": "app.py",
    "config": "config.yaml",
    "main": "main.py",
    "intent": "intent_analyzer.py",
    "context": "context_builder.py",
    "planner": "planner.py",
    "router": "model_router.py",
    "compiler": "prompt_compiler.py",
}


def get_focused_app() -> str:
    """Best-effort detection of the currently focused application."""
    # Works on macOS
    try:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get name of first process '
             'whose frontmost is true'],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    # Works on Linux with xdotool
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    return "Unknown"


def infer_relevant_files(goal: str, project: Optional[str]) -> list[str]:
    """Return file names most likely affected by the goal."""
    goal_lower = goal.lower()
    relevant = []
    for keyword, filename in FILE_DOMAIN_MAP.items():
        if keyword in goal_lower:
            relevant.append(filename)
    # Always include main entry point for AURA project tasks
    if project == "AURA" and "main.py" not in relevant:
        relevant.append("main.py")
    return relevant[:5]  # cap at 5


def build_context(goal: str, project: Optional[str] = None) -> ContextResult:
    """Assemble full runtime context for the Planner."""
    focused_app = get_focused_app()

    # Pull from AURA brain if available
    brain_ctx = get_context()
    active_file = brain_ctx.get("file") or brain_ctx.get("active_file")
    session_goal = get_session_goal() or brain_ctx.get("session_goal")

    # Infer which project files are relevant
    recent_files = infer_relevant_files(goal, project)

    return ContextResult(
        focused_app=focused_app,
        project=project or brain_ctx.get("project"),
        active_file=active_file,
        session_goal=session_goal,
        recent_files=recent_files,
        raw_context=brain_ctx,
    )
