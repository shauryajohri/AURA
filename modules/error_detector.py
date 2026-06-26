# modules/error_detector.py
"""
Detects whether the user's code currently has errors, combining two signals:

1. VS Code's own problem count — the status bar / Problems panel text
   (e.g. "0 Problems", "2 Errors, 1 Warning") that shows up in OCR'd /
   accessibility-read screen text. This is VS Code telling us directly,
   so it's the stronger signal when present.

2. Terminal output — tracebacks, "Error:", "Exception", non-zero exit
   language, vs. clean-completion markers. Useful when the Problems
   panel isn't visible or the user just ran something.

Two ways to use this module:

  - On-demand (chat command): handle_error_check(query) — same shape as
    modules/tasks.py's handlers, drop into core/brain.py's process() /
    process_streaming() routing next to the existing "add task" block.

  - Proactive (watch loop): ErrorStateTracker — call .check(...) every
    cycle from modules/proactive.py with the current screen context.
    It only returns a message when the state actually flips (clean ->
    error or error -> clean); otherwise returns None so the loop stays
    silent and doesn't repeat itself every cycle.
"""

import re
from dataclasses import dataclass
from enum import Enum


class ErrorState(Enum):
    CLEAN = "clean"
    HAS_ERRORS = "has_errors"
    UNKNOWN = "unknown"


@dataclass
class ErrorCheckResult:
    state: ErrorState
    reason: str            # short human-readable basis for the verdict
    error_count: int | None = None
    warning_count: int | None = None


# ── Signal 1: VS Code status bar / Problems panel ────────────────────────
# Matches things like:
#   "0 Problems"
#   "2 Errors, 1 Warning"
#   "No problems have been detected"
#   "1 Error  0 Warnings  0 Infos"
_PROBLEMS_COUNT_PATTERN = re.compile(
    r"(?P<errors>\d+)\s*Errors?\b.*?(?P<warnings>\d+)\s*Warnings?\b",
    re.IGNORECASE | re.DOTALL,
)
_ZERO_PROBLEMS_PATTERN = re.compile(
    r"\b(0\s*Problems|No problems have been detected|No errors? found)\b",
    re.IGNORECASE,
)
_NONZERO_SINGLE_PATTERN = re.compile(
    r"(?P<count>[1-9]\d*)\s*Errors?\b", re.IGNORECASE
)

# ── Signal 2: terminal output ──────────────────────────────────────────────
_TRACEBACK_MARKERS = (
    "traceback (most recent call last)",
    "exception in thread",
    "unhandled exception",
)
_ERROR_LINE_PATTERN = re.compile(
    r"^\s*(?:[\w.]*Error|[\w.]*Exception)\b.*:", re.MULTILINE
)
_CLEAN_RUN_MARKERS = (
    "process finished with exit code 0",
    "0 failed",
    "all tests passed",
    "build succeeded",
    "compiled successfully",
)
_NONZERO_EXIT_PATTERN = re.compile(
    r"\bexit code (?!0\b)\d+\b", re.IGNORECASE
)


def _check_vscode_signal(visible_text: str) -> ErrorCheckResult | None:
    """Looks for VS Code's own problem-count text. Returns None if no
    such signal is present in the given text at all (caller falls back
    to the terminal signal or UNKNOWN)."""
    if not visible_text:
        return None

    text = visible_text.strip()

    if _ZERO_PROBLEMS_PATTERN.search(text):
        return ErrorCheckResult(
            state=ErrorState.CLEAN,
            reason="VS Code reports 0 problems",
            error_count=0,
        )

    match = _PROBLEMS_COUNT_PATTERN.search(text)
    if match:
        errors = int(match.group("errors"))
        warnings = int(match.group("warnings"))
        if errors == 0:
            return ErrorCheckResult(
                state=ErrorState.CLEAN,
                reason=f"VS Code reports 0 errors ({warnings} warning(s))",
                error_count=0,
                warning_count=warnings,
            )
        return ErrorCheckResult(
            state=ErrorState.HAS_ERRORS,
            reason=f"VS Code reports {errors} error(s)",
            error_count=errors,
            warning_count=warnings,
        )

    single = _NONZERO_SINGLE_PATTERN.search(text)
    if single:
        count = int(single.group("count"))
        return ErrorCheckResult(
            state=ErrorState.HAS_ERRORS,
            reason=f"VS Code reports {count} error(s)",
            error_count=count,
        )

    return None


def _check_terminal_signal(terminal_text: str) -> ErrorCheckResult | None:
    """Looks for traceback/error language or clean-completion markers in
    terminal output. Returns None if the text doesn't clearly indicate
    either state."""
    if not terminal_text:
        return None

    text = terminal_text.strip()
    lower = text.lower()

    for marker in _TRACEBACK_MARKERS:
        if marker in lower:
            return ErrorCheckResult(
                state=ErrorState.HAS_ERRORS,
                reason="Traceback found in terminal output",
            )

    if _ERROR_LINE_PATTERN.search(text):
        return ErrorCheckResult(
            state=ErrorState.HAS_ERRORS,
            reason="Error/Exception line found in terminal output",
        )

    if _NONZERO_EXIT_PATTERN.search(lower):
        return ErrorCheckResult(
            state=ErrorState.HAS_ERRORS,
            reason="Non-zero exit code in terminal output",
        )

    for marker in _CLEAN_RUN_MARKERS:
        if marker in lower:
            return ErrorCheckResult(
                state=ErrorState.CLEAN,
                reason=f"Terminal shows clean run ('{marker}')",
            )

    return None


def detect_error_state(visible_text: str = "", terminal_text: str = "") -> ErrorCheckResult:
    """
    Combines both signals. VS Code's own problem count wins when present,
    since it's the more direct/authoritative signal (it's the editor
    telling us, not us inferring from raw text); terminal output is the
    fallback or corroborating signal.

    If neither signal is conclusive, returns UNKNOWN — callers should
    treat UNKNOWN as "don't claim anything either way" rather than
    defaulting to "no errors", since silently asserting a clean state
    AURA didn't actually verify is worse than saying nothing.
    """
    vscode_result = _check_vscode_signal(visible_text)
    terminal_result = _check_terminal_signal(terminal_text)

    if vscode_result is not None:
        return vscode_result
    if terminal_result is not None:
        return terminal_result

    return ErrorCheckResult(
        state=ErrorState.UNKNOWN,
        reason="No problem-count or terminal signal detected",
    )


# ── On-demand: chat command handler ──────────────────────────────────────
# Drop into core/brain.py's process()/process_streaming(), same pattern as
# the existing "add task" / "done with" blocks:
#
#   if any(w in query_lower for w in ["check for error", "any error",
#                                      "is there an error", "errors?"]):
#       from modules.error_detector import handle_error_check
#       result = handle_error_check(query)
#       ...

def handle_error_check(query: str) -> str:
    try:
        from modules.screen_reader import get_screen_context
        context = get_screen_context()
        visible_text = context.get("visible_text", "")
    except Exception:
        visible_text = ""

    terminal_text = ""
    try:
        from modules.screen_reader import get_terminal_output
        terminal_text = get_terminal_output()
    except Exception:
        # get_terminal_output may not exist yet — visible_text alone is
        # still enough to check the VS Code Problems/status bar signal.
        pass

    result = detect_error_state(visible_text, terminal_text)
    return _format_result(result)


def _format_result(result: ErrorCheckResult) -> str:
    if result.state == ErrorState.CLEAN:
        return "No errors in your code — looks clean."
    if result.state == ErrorState.HAS_ERRORS:
        if result.error_count:
            return f"There's {result.error_count} error(s) showing — want me to take a look?"
        return "There's an error showing — want me to take a look?"
    return "I can't tell from what's on screen right now — open the Problems panel or run it and I'll check again."


# ── Proactive: state-change-only tracker ─────────────────────────────────
# Drop into modules/proactive.py's watch loop, called once per cycle with
# whatever screen/terminal context that loop already has:
#
#   _error_tracker = ErrorStateTracker()
#   ...
#   message = _error_tracker.check(visible_text, terminal_text)
#   if message:
#       speak_fn(message)

class ErrorStateTracker:
    """
    Tracks error state across proactive cycles and only returns a message
    when the state actually flips, so the loop doesn't repeat itself.
    UNKNOWN never triggers a flip in either direction — it's treated as
    "no new information" rather than a state of its own, so a brief
    unreadable screen doesn't cause a false "errors fixed!" or false
    "error appeared!" the moment the signal becomes clear again.
    """

    def __init__(self):
        self._last_known_state: ErrorState | None = None

    def check(self, visible_text: str = "", terminal_text: str = "") -> str | None:
        result = detect_error_state(visible_text, terminal_text)

        if result.state == ErrorState.UNKNOWN:
            return None

        if self._last_known_state is None:
            # First real reading — record it, but don't announce on
            # startup; nothing has "changed" yet from AURA's perspective.
            self._last_known_state = result.state
            return None

        if result.state == self._last_known_state:
            return None

        previous_state = self._last_known_state
        self._last_known_state = result.state

        if previous_state == ErrorState.HAS_ERRORS and result.state == ErrorState.CLEAN:
            return "No errors in your code — looks clean now."
        if previous_state == ErrorState.CLEAN and result.state == ErrorState.HAS_ERRORS:
            if result.error_count:
                return f"Heads up — {result.error_count} error(s) just showed up."
            return "Heads up — an error just showed up."

        return None

    def reset(self):
        """Call this if the user switches files/projects, so an unrelated
        error/clean state from a different context doesn't get reported
        as a 'change' against the previous file's state."""
        self._last_known_state = None