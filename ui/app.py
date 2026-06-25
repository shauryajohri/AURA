import threading

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot

from ui.orb import OrbWidget
from ui.main_window import MainWindow
from ui.execution_plan_panel import ExecutionPlanPanel
from core.prompt_engine import PromptEngine


class AuraAppController(QObject):
    responseChunk = Signal(str)
    codeBlock = Signal(str, str)
    taskFailed = Signal(str)
    taskFinished = Signal()

    # Emitted when engine finishes processing (before approval)
    planReady = Signal(dict)

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        self._busy = False
        self._pending_engine_result = None

        self.orb = OrbWidget()
        self.main_window = MainWindow(self.orb)

        # ── Prompt Engine ────────────────────────────────────────────────
        self.prompt_engine = PromptEngine()

        # ── Execution Plan Panel ─────────────────────────────────────────
        self.plan_panel = ExecutionPlanPanel(self.main_window)
        self.plan_panel.approved.connect(self._on_plan_approved)
        self.plan_panel.edited.connect(self._on_plan_edited)
        self.plan_panel.rejected.connect(self._on_plan_rejected)

        # Tell MainWindow to embed the panel (see note below)
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

    # ── Orb interaction handlers ─────────────────────────────────────────
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

    # ── Step 1: User sends message → run engine in background ────────────
    def _on_user_message(self, text: str):
        if self._busy:
            if self._pending_engine_result is not None:
                lowered = text.strip().lower()
                if lowered in {"approve", "approved", "yes", "y", "run it", "do it", "continue"}:
                    self._on_plan_approved({})
                    return
                if lowered in {"cancel", "reject", "stop", "no", "n"}:
                    self._on_plan_rejected()
                    return
                self.main_window.append_message(
                    "Execution plan is ready. Type approve to run it, or cancel to drop it.",
                    "AURA",
                )
            else:
                self.main_window.append_message("Still working on the last one.", "AURA")
            return

        self._busy = True
        self.orb.set_state(OrbWidget.STATE_THINKING)
        self.main_window.set_status_text("planning")

        # Run prompt engine in background thread (it may call get_context etc.)
        worker = threading.Thread(
            target=self._run_prompt_engine,
            args=(text,),
            daemon=True,
        )
        worker.start()

    def _run_prompt_engine(self, text: str):
        """Background: run the 5-stage pipeline, then signal the UI."""
        try:
            result = self.prompt_engine.process(text)
            self._pending_engine_result = result
            self.planReady.emit(result.summary_dict())
        except Exception as e:
            self.taskFailed.emit(f"Prompt engine error: {e}")

    # ── Step 2: Show the plan panel (main thread) ─────────────────────────
    @Slot(dict)
    def _show_plan_panel(self, summary: dict):
        try:
            self.show_main_window()
            self.orb.set_state(OrbWidget.STATE_IDLE)
            self.main_window.set_status_text("awaiting approval")
            self.plan_panel.show_plan(summary)
            self.main_window.add_activity_note("Execution plan ready for approval")
            self.main_window.append_message(
                "I made an execution plan. Type approve to run it, or cancel to drop it.",
                "AURA",
            )
        except Exception as e:
            self._busy = False
            self._pending_engine_result = None
            self._show_task_error(f"Plan panel error: {e}")

    # ── Step 3a: User approves → call LLM with compiled prompt ───────────
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

        worker = threading.Thread(
            target=self._process_approved_plan,
            args=(model_id, system_prompt, user_prompt),
            daemon=True,
        )
        worker.start()

    def _process_approved_plan(self, model_id: str, system_prompt: str, user_prompt: str):
        """Background: send compiled prompt to brain."""
        try:
            from core.brain import process_streaming

            def on_chunk(chunk: str):
                self.responseChunk.emit(chunk)

            def on_code(lang: str, code: str):
                self.codeBlock.emit(lang, code)

            # Pass the compiled prompt — clean, structured, no raw user vagueness
            process_streaming(
                user_prompt,
                on_chunk=on_chunk,
                on_code=on_code,
                system_prompt=system_prompt,
            )
        except Exception as e:
            self.taskFailed.emit(str(e))
        finally:
            self._pending_engine_result = None
            self.taskFinished.emit()

    # ── Step 3b: User edits plan ──────────────────────────────────────────
    @Slot(dict)
    def _on_plan_edited(self, updated_summary: dict):
        """User tweaked the plan — update and re-show."""
        if self._pending_engine_result is None:
            self._busy = False
            return
        # Apply edits back onto the plan
        if "goal" in updated_summary:
            self._pending_engine_result.plan.goal = updated_summary["goal"]
        # Re-show the updated panel
        self.plan_panel.show_plan(self._pending_engine_result.summary_dict())

    # ── Step 3c: User cancels ─────────────────────────────────────────────
    @Slot()
    def _on_plan_rejected(self):
        self._pending_engine_result = None
        self._busy = False
        self.orb.set_state(OrbWidget.STATE_IDLE)
        self.main_window.set_status_text("idle")
        self.main_window.append_message("Cancelled. What would you like to do?", "AURA")

    # ── Shared response handlers ──────────────────────────────────────────
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
