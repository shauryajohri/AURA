import threading

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot

from ui.orb import OrbWidget
from ui.main_window import MainWindow
from ui.execution_plan_panel import ExecutionPlanPanel
from core.prompt_engine import PromptEngine


# ── Phrases that should NEVER trigger the planner ────────────────────────────
CASUAL_BYPASS = {
    "hi", "hey", "hoi", "hello", "yo", "sup", "what's up", "wassup",
    "hola", "howdy", "good morning", "good evening", "good night",
    "thanks", "thank you", "ok", "okay", "cool", "nice", "great",
    "bye", "goodbye", "see you", "cya", "later", "lol", "haha",
    "sure", "yep", "nope", "nah", "hmm", "hm", "ugh", "wow",
}

# Phrases that look like tasks but are actually observations — bypass planner
OBSERVATION_PREFIXES = (
    "look at", "check out", "see ", "show me", "open ", "what is ",
    "what's ", "who is ", "who's ", "tell me about", "explain ",
)

PLANNER_PREFIXES = (
    "aura plan ",
    "aura make a plan",
    "aura create a plan",
    "aura prompt ",
)

CODING_APPROVAL_WORDS = {
    "code", "coding", "function", "class", "method", "script", "api",
    "bug", "fix", "implement", "refactor", "backend", "frontend",
    "python", "javascript", "typescript", "html", "css", "file",
    "brain.py", "main.py", "proactive.py", "command_handler.py",
}

CHANGE_APPROVAL_WORDS = {
    "change", "modify", "edit", "update", "delete", "remove", "write",
    "create", "build", "add", "generate", "optimize", "migrate",
    "restructure", "rewrite", "patch", "fix", "debug", "repair",
}


def _is_casual(text: str) -> bool:
    """Return True if the message needs no planning step."""
    t = text.strip().lower().rstrip("!.,?")

    # Exact match in bypass set
    if t in CASUAL_BYPASS:
        return True

    # Observation phrases ("look at vs code", "check out this error")
    # These should observe first and ask before switching into coding/planning.
    if any(t.startswith(p) for p in OBSERVATION_PREFIXES):
        return True

    return not _requires_approval(text)


def _requires_approval(text: str) -> bool:
    """Only coding/change tasks or explicit planning commands need approval."""
    t = text.strip().lower().rstrip("!.,?")

    if any(t.startswith(prefix) for prefix in PLANNER_PREFIXES):
        return True

    if any(t.startswith(p) for p in OBSERVATION_PREFIXES):
        return False

    words = set(
        t.replace("/", " ")
        .replace("\\", " ")
        .replace(",", " ")
        .replace("?", " ")
        .replace("!", " ")
        .split()
    )
    has_coding_signal = any(
        w in words or (w.endswith(".py") and w in t)
        for w in CODING_APPROVAL_WORDS
    )
    has_change_signal = any(w in words for w in CHANGE_APPROVAL_WORDS)
    return has_coding_signal and has_change_signal


class AuraAppController(QObject):
    responseChunk   = Signal(str)
    codeBlock       = Signal(str, str)
    taskFailed      = Signal(str)
    taskFinished    = Signal()
    planReady       = Signal(dict)
    presenceChanged = Signal(str)   # 'working' | 'idle' | 'afk'

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        self._busy = False
        self._pending_engine_result = None
        self._pending_response = []

        self.orb = OrbWidget()
        self.main_window = MainWindow(self.orb)

        self.prompt_engine = PromptEngine()

        self.plan_panel = ExecutionPlanPanel(self.main_window)
        self.plan_panel.approved.connect(self._on_plan_approved)
        self.plan_panel.edited.connect(self._on_plan_edited)
        self.plan_panel.rejected.connect(self._on_plan_rejected)

        if hasattr(self.main_window, "set_plan_panel"):
            self.main_window.set_plan_panel(self.plan_panel)

        self.orb.requestRestore.connect(self.show_main_window)
        self.orb.requestQuickPanel.connect(self._on_orb_single_click)
        self.orb.requestQuit.connect(self.app.quit)
        self.orb.requestUnlock.connect(self._on_unlock_requested)

        self.main_window.sendMessage.connect(self._on_user_message)
        self.responseChunk.connect(self._append_response_chunk)
        self.codeBlock.connect(self.main_window.append_code)
        self.taskFailed.connect(self._show_task_error)
        self.taskFinished.connect(self._on_task_finished)
        self.planReady.connect(self._show_plan_panel)
        self.presenceChanged.connect(self._on_presence_changed)

        self.show_main_window()
        self.float_orb()
        self._keep_orb_visible_timer = QTimer(self)
        self._keep_orb_visible_timer.timeout.connect(self.ensure_orb_visible)
        self._keep_orb_visible_timer.start(1000)

    # ── Mode switching ───────────────────────────────────────────────────
    def float_orb(self):
        self.orb.setParent(None)
        self.orb.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        screen_geo = self.app.primaryScreen().availableGeometry()
        self.orb.move(
            screen_geo.right() - self.orb.width() - 40,
            screen_geo.bottom() - self.orb.height() - 60,
        )
        self.orb.show()
        self.orb.raise_()
        self.orb.activateWindow()
        self.orb.update()

    def show_main_window(self):
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()
        self.ensure_orb_visible()

    def ensure_orb_visible(self):
        if self.orb.parent() is not None:
            self.orb.setParent(None)
            self.orb.setWindowFlags(
                Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            )
        if not self.orb.isVisible():
            self.float_orb()
        else:
            self.orb.raise_()
            self.orb.update()

    # ── Orb handlers ─────────────────────────────────────────────────────
    def _on_orb_single_click(self):
        if self.main_window.isVisible():
            self.main_window.hide()
            self.ensure_orb_visible()
        else:
            self.show_main_window()

    def _on_unlock_requested(self):
        try:
            from modules.proactive import clear_app_lock
            clear_app_lock()
            self.main_window.add_activity_note("Unlocked from focused app (via orb menu)")
        except Exception as e:
            print(f"[AURA UI] Unlock error: {e}")

    # ── Presence ─────────────────────────────────────────────────────────
    @Slot(str)
    def _on_presence_changed(self, state: str):
        self.main_window.set_presence(state)

    # ── Message routing ───────────────────────────────────────────────────
    def _on_user_message(self, text: str):
        # Plan waiting → only accept approve/cancel
        if self._busy and self._pending_engine_result is not None:
            lowered = text.strip().lower()
            if lowered in {"approve", "approved", "yes", "y", "run it", "do it", "continue"}:
                self._on_plan_approved({})
            elif lowered in {"cancel", "reject", "stop", "no", "n"}:
                self._on_plan_rejected()
            else:
                self.main_window.append_message(
                    "Plan is ready — type approve to run it, or cancel to drop it.", "AURA"
                )
            return

        if self._busy:
            self.main_window.append_message("Still working on the last one.", "AURA")
            return

        self._busy = True
        self._pending_response = []
        self.orb.set_state(OrbWidget.STATE_THINKING)

        if not _requires_approval(text):
            # Normal chat/observation/questions are direct. Approval is only
            # for coding changes or explicit "aura plan ..." requests.
            self.main_window.set_status_text("thinking")
            threading.Thread(
                target=self._process_direct, args=(text,), daemon=True
            ).start()
        else:
            # Real task → prompt engine → approval panel
            self.main_window.set_status_text("planning")
            threading.Thread(
                target=self._run_prompt_engine, args=(text,), daemon=True
            ).start()

    # ── Direct LLM (no planning) ──────────────────────────────────────────
    def _process_direct(self, text: str):
        try:
            from core.brain import process_streaming
            process_streaming(
                text,
                on_chunk=lambda c: self.responseChunk.emit(c),
                on_code=lambda l, c: self.codeBlock.emit(l, c),
            )
        except Exception as e:
            self.taskFailed.emit(str(e))
        finally:
            self.taskFinished.emit()

    # ── Prompt engine pipeline ────────────────────────────────────────────
    def _run_prompt_engine(self, text: str):
        try:
            result = self.prompt_engine.process(text)
            self._pending_engine_result = result
            self.planReady.emit(result.summary_dict())
        except Exception as e:
            self._busy = False
            self.taskFailed.emit(f"Prompt engine error: {e}")

    @Slot(dict)
    def _show_plan_panel(self, summary: dict):
        try:
            self.show_main_window()
            self.orb.set_state(OrbWidget.STATE_IDLE)
            self.main_window.set_status_text("awaiting approval")
            self.plan_panel.show_plan(summary)
            self.main_window.add_activity_note("Execution plan ready — approve or cancel")
        except Exception as e:
            self._busy = False
            self._pending_engine_result = None
            self._show_task_error(f"Plan panel error: {e}")

    @Slot(dict)
    def _on_plan_approved(self, summary: dict):
        if self._pending_engine_result is None:
            self._busy = False
            return
        self.orb.set_state(OrbWidget.STATE_THINKING)
        self.main_window.set_status_text("thinking")
        self._pending_response = []
        model_id, system_prompt, user_prompt = \
            self.prompt_engine.approve_and_execute(self._pending_engine_result)
        threading.Thread(
            target=self._process_approved_plan,
            args=(model_id, system_prompt, user_prompt),
            daemon=True,
        ).start()

    def _process_approved_plan(self, model_id: str, system_prompt: str, user_prompt: str):
        try:
            from core.brain import process_streaming
            process_streaming(
                user_prompt,
                on_chunk=lambda c: self.responseChunk.emit(c),
                on_code=lambda l, c: self.codeBlock.emit(l, c),
                system_prompt=system_prompt,
            )
        except Exception as e:
            self.taskFailed.emit(str(e))
        finally:
            self._pending_engine_result = None
            self.taskFinished.emit()

    @Slot(dict)
    def _on_plan_edited(self, updated_summary: dict):
        if self._pending_engine_result is None:
            self._busy = False
            return
        if "goal" in updated_summary:
            self._pending_engine_result.plan.goal = updated_summary["goal"]
        self.plan_panel.show_plan(self._pending_engine_result.summary_dict())

    @Slot()
    def _on_plan_rejected(self):
        self._pending_engine_result = None
        self._busy = False
        self.orb.set_state(OrbWidget.STATE_IDLE)
        self.main_window.set_status_text("idle")
        self.main_window.append_message("Cancelled. What would you like to do?", "AURA")

    # ── Response handlers ─────────────────────────────────────────────────
    @Slot(str)
    def _append_response_chunk(self, chunk: str):
        self._pending_response.append(chunk)

    @Slot(str)
    def _show_task_error(self, error: str):
        self._busy = False
        self.main_window.append_message(f"Error: {error}", "AURA")
        self.orb.set_state(OrbWidget.STATE_IDLE)
        self.main_window.set_status_text("idle")

    @Slot()
    def _on_task_finished(self):
        final = "".join(self._pending_response).strip()
        if final:
            self.main_window.append_message(final, "AURA")
        self._pending_response = []
        self._busy = False
        self.orb.set_state(OrbWidget.STATE_IDLE)
        self.main_window.set_status_text("idle")

    # ── External hooks ────────────────────────────────────────────────────
    def on_listening_start(self):
        self.orb.set_state(OrbWidget.STATE_LISTENING)
        self.main_window.set_voice_status("Listening...")
        self.main_window.set_status_text("listening")

    def on_thinking_start(self):
        self.orb.set_state(OrbWidget.STATE_THINKING)
        self.main_window.set_status_text("thinking")

    def on_speaking_start(self):
        self.orb.set_state(OrbWidget.STATE_SPEAKING)
        self.main_window.set_status_text("speaking")

    def on_idle(self):
        self.orb.set_state(OrbWidget.STATE_IDLE)
        self.main_window.set_voice_status("Listening for you")
        self.main_window.set_status_text("idle")
