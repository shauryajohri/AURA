import threading

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot

from ui.orb import OrbWidget
from ui.aura_window import AuraWindow
from ui.execution_plan_panel import ExecutionPlanPanel
from core.prompt_engine import PromptEngine


# V2.1: all message routing (casual bypass, observation prefixes, planner
# prefixes, coding permission gate, slash-command sessions) lives in
# core/conversation_director.py now. The controller just dispatches on the
# Directive it returns.
from core.conversation_director import ConversationDirector


class AuraAppController(QObject):
    responseChunk   = Signal(str)
    codeBlock       = Signal(str, str)
    taskFailed      = Signal(str)
    taskFinished    = Signal()
    planReady       = Signal(dict)
    presenceChanged = Signal(str)   # 'working' | 'idle' | 'afk'
    voiceHeard      = Signal(str)   # STT result (mic thread → Qt thread)
    wakeDetected    = Signal()      # wake word heard (wake thread → Qt thread)
    ttsStateChanged = Signal(bool)  # True = speaking started, False = finished
    modelChanged    = Signal(str)   # model id actually being used for this call

    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        self._busy = False
        self._pending_engine_result = None
        self._pending_response = []

        self.orb = OrbWidget()
        self.main_window = AuraWindow()

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
        self.main_window.micToggled.connect(self._on_mic_toggled)
        try:
            self.main_window.center.natureSelected.connect(self._on_nature_selected)
        except Exception:
            pass
        self.voiceHeard.connect(self._on_voice_heard)
        self.wakeDetected.connect(self._on_wake_detected)
        self.ttsStateChanged.connect(self._on_tts_state)
        self.modelChanged.connect(self._on_model_changed)
        self.responseChunk.connect(self._append_response_chunk)
        self.codeBlock.connect(self.main_window.append_code)
        self.taskFailed.connect(self._show_task_error)
        self.taskFinished.connect(self._on_task_finished)
        self.planReady.connect(self._show_plan_panel)
        self.presenceChanged.connect(self._on_presence_changed)

        # Voice pipeline state
        self._mic_stop_event = None
        self._tts_speaking = False
        self.speak_replies = True   # TTS chat responses out loud
        self._suppress_tts_once = False   # don't read out built prompts etc.

        # Conversation Director — owns modes, slash commands, and routing
        self.director = ConversationDirector(
            on_mode_changed=self._on_director_mode
        )
        if hasattr(self.main_window, "set_mode"):
            self.main_window.set_mode(self.director.mode)

        self.show_main_window()
        self.float_orb()
        self._keep_orb_visible_timer = QTimer(self)
        self._keep_orb_visible_timer.timeout.connect(self.ensure_orb_visible)
        self._keep_orb_visible_timer.start(1000)

        self._start_wake_word_thread()

        # Seed the Model chip with the default model before any call runs.
        try:
            from core.ai_router import GROQ_MODEL
            self.modelChanged.emit(GROQ_MODEL)
        except Exception:
            pass

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

    # ── Voice input (mic button → STT → brain) ──────────────────────────
    @Slot(bool)
    def _on_mic_toggled(self, on: bool):
        if on:
            try:
                from modules.voice_input import listen_continuous, mic_available
                if not mic_available():
                    self.main_window.add_activity_note("No microphone available")
                    self.main_window.set_voice_status("Mic unavailable")
                    return
                _, self._mic_stop_event = listen_continuous(
                    lambda text: self.voiceHeard.emit(text)
                )
                self.on_listening_start()
                self.main_window.add_activity_note("Mic on — listening")
            except Exception as e:
                self.main_window.add_activity_note(f"Mic error: {e}")
        else:
            if self._mic_stop_event is not None:
                self._mic_stop_event.set()
                self._mic_stop_event = None
            self.on_idle()
            self.main_window.add_activity_note("Mic off")

    @Slot(str)
    def _on_voice_heard(self, text: str):
        """STT result — route it exactly like a typed message."""
        if self._tts_speaking:
            return  # don't let AURA hear itself talk
        self.main_window.append_message(text, "You")
        self._on_user_message(text)

    # ── Wake word ("Jarvis") ─────────────────────────────────────────────
    def _start_wake_word_thread(self):
        threading.Thread(target=self._wake_loop, daemon=True).start()

    def _wake_loop(self):
        import time as _time
        try:
            from modules.wake_word import wait_for_wake_word
        except Exception as e:
            print(f"[AURA] Wake word disabled: {e}")
            return
        while True:
            # Don't fight the STT loop for the audio device.
            if self.main_window.is_mic_on():
                _time.sleep(1.0)
                continue
            result = wait_for_wake_word(
                stop_check=self.main_window.is_mic_on
            )
            if result is True:
                self.wakeDetected.emit()
                _time.sleep(1.0)
            elif result is False:
                print("[AURA] Wake word unavailable — thread stopped")
                return
            # result is None → mic turned on mid-wait; loop re-checks

    @Slot()
    def _on_wake_detected(self):
        self.main_window.add_activity_note("Wake word heard")
        if not self.main_window.is_mic_on():
            # Reuse the mic-button path so UI state stays in sync.
            self.main_window._toggle_mic()

    # ── Voice output (speak replies) ─────────────────────────────────────
    def _speak_reply(self, text: str):
        try:
            self.ttsStateChanged.emit(True)
            from modules.speech_planner import plan
            from modules.voice_output import speak_chunks
            speak_chunks(plan(text, "CHAT"))
        except Exception as e:
            print(f"[AURA TTS] {e}")
        finally:
            self.ttsStateChanged.emit(False)

    # ── Model display ─────────────────────────────────────────────────────
    _MODEL_LABELS = {
        "poolside/laguna-m.1:free":                "Laguna M.1",
        "nvidia/nemotron-3-super-120b-a12b:free":  "Nemotron 3 Super",
        "google/gemma-4-31b-it:free":              "Gemma 4 31B",
        "llama-3.3-70b-versatile":                 "Llama 3.3 70B",
        "llama-3.1-8b-instant":                    "Llama 3.1 8B",
    }

    @Slot(str)
    def _on_model_changed(self, model_id: str):
        label = self._MODEL_LABELS.get(model_id, model_id)
        if hasattr(self.main_window, "set_model_text"):
            self.main_window.set_model_text(label)
        # Center panel's "Model Routing:" bar reads from the StateBus
        # (was stuck on its mock default "GPT-4o").
        if hasattr(self.main_window, "bus"):
            self.main_window.bus.set_active_model(label)

    @Slot(bool)
    def _on_tts_state(self, speaking: bool):
        self._tts_speaking = speaking
        if speaking:
            self.on_speaking_start()
        elif self.main_window.is_mic_on():
            self.on_listening_start()
        else:
            self.on_idle()

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

        # ── Conversation Director decides who owns this message ──────────
        directive = self.director.handle(text)

        if directive.kind == "reply":
            # Instant local answer (mode acks, options menu, /help) — no LLM.
            self.main_window.append_message(directive.text, "AURA")
            return

        self._busy = True
        self._pending_response = []
        self.orb.set_state(OrbWidget.STATE_THINKING)

        if directive.kind == "plan":
            # Explicit plan request → prompt engine → approval panel
            self.main_window.set_status_text("planning")
            threading.Thread(
                target=self._run_prompt_engine, args=(directive.text,), daemon=True
            ).start()
        elif directive.kind == "generate":
            # Menu choice "Generate code" — choice IS approval, no panel
            self.main_window.set_status_text("planning")
            threading.Thread(
                target=self._run_generate, args=(directive.text,), daemon=True
            ).start()
        elif directive.kind == "execute_prompt":
            # Run the /prompt-built spec as a coding task — the full spec
            # travels with the request, no conversation-history fishing.
            self.main_window.set_status_text("thinking")
            threading.Thread(
                target=self._execute_built_prompt, args=(directive.text,),
                daemon=True,
            ).start()
        elif directive.kind == "llm_once":
            # One clean call (e.g. /prompt_end builds the final prompt)
            self.main_window.set_status_text("thinking")
            self._suppress_tts_once = True   # never read a built prompt aloud
            threading.Thread(
                target=self._process_llm_once,
                args=(directive.system, directive.user),
                daemon=True,
            ).start()
        else:
            # "chat" — normal streaming conversation
            self.main_window.set_status_text("thinking")
            threading.Thread(
                target=self._process_direct,
                args=(directive.text, directive.intent or None),
                daemon=True,
            ).start()

    @Slot(str)
    def _on_nature_selected(self, key: str):
        try:
            from core.nature import NATURES
            label = NATURES.get(key, {}).get("label", key)
        except Exception:
            label = key
        self.main_window.add_activity_note(
            f"Nature: {label}" + ("" if key == "auto" else " (locked)"))

    # ── Director hooks ────────────────────────────────────────────────────
    def _on_director_mode(self, mode: str):
        if hasattr(self.main_window, "set_mode"):
            self.main_window.set_mode(mode)
        self.main_window.add_activity_note(f"Mode: {mode}")

    def _process_llm_once(self, system: str, user: str):
        try:
            from core.ai_router import call_groq_raw
            result = call_groq_raw(user, system)
            if result == "RATE_LIMIT":
                result = "Hit my rate limit — give me a moment, then /prompt_end again."
            elif result == "CONNECTION_ERROR":
                result = "Connection trouble — your buffer is intact, /prompt_end to retry."
            else:
                self.director.note_prompt_result(result)
                result = ("Here's your optimized prompt:\n\n" + result +
                          "\n\n— What next?\n"
                          "2 / code → generate the code from this prompt\n"
                          "1 / explain → walk through what it asks for\n"
                          "/prompt save · /prompt export")
            self.responseChunk.emit(result)
        except Exception as e:
            self.taskFailed.emit(str(e))
        finally:
            self.taskFinished.emit()

    # ── Direct LLM (no planning) ──────────────────────────────────────────
    def _process_direct(self, text: str, intent_hint: str = None):
        try:
            from core.ai_router import GROQ_MODEL, resolve_model
            from core.brain import process_streaming
            # Show the model that will actually handle this (honors locks);
            # falls back to the Groq default if every candidate is locked.
            self.modelChanged.emit(resolve_model(intent_hint or "CASUAL") or GROQ_MODEL)
            process_streaming(
                text,
                on_chunk=lambda c: self.responseChunk.emit(c),
                on_code=lambda l, c: self.codeBlock.emit(l, c),
                intent_hint=intent_hint,
            )
        except Exception as e:
            self.taskFailed.emit(str(e))
        finally:
            self.taskFinished.emit()

    # ── Conversation context for short/contextless requests ──────────────
    # Lines that must never be fed back as "context": compiled plan
    # templates, and the tell-tale junk from failed runs (feeding those
    # back in made the model echo garbage — seen live on 2026-07-06).
    _CTX_JUNK = (
        "Execution Plan:",
        "no specific code or implementation details",
        "hypothetical coding task",
        "I couldn't find",
        "Try saying the full app name",
        "Run this program to test the functions",
    )

    @classmethod
    def _is_template_blob(cls, text: str) -> bool:
        return text.startswith("Task:") or any(j in text for j in cls._CTX_JUNK)

    @classmethod
    def _recent_context(cls, max_entries: int = 4) -> str:
        """Last few exchanges, so 'code' after a linked-list discussion
        means 'code THAT', not a context-free 'Task: Code'.

        brain._history is in-memory and EMPTY right after a restart — in
        that case fall back to the persisted conversation in the store
        (the same one the startup greeting reads)."""
        lines = []
        try:
            from core.brain import _history
            for h in _history[-max_entries:]:
                role = "User" if h.get("role") == "user" else "Assistant"
                text = (h.get("text") or "").strip()
                if text and not cls._is_template_blob(text):
                    lines.append(f"{role}: {text[:400]}")
        except Exception:
            pass

        if len(lines) < 2:   # fresh session → use persisted history
            try:
                from memory.store import get_recent_conversations
                lines = []
                for role, message, _ts in get_recent_conversations(8):
                    text = (message or "").strip()
                    if not text or cls._is_template_blob(text):
                        continue
                    label = "User" if role == "user" else "Assistant"
                    lines.append(f"{label}: {text[:400]}")
                lines = lines[-max_entries:]
            except Exception:
                pass

        return "\n".join(lines)

    @classmethod
    def _with_context(cls, user_prompt: str, original_request: str) -> str:
        if len(original_request.split()) <= 7:
            ctx = cls._recent_context()
            if ctx:
                return (user_prompt +
                        "\n\nConversation context — the task refers to this discussion:\n"
                        + ctx)
        return user_prompt

    _EXEC_PROMPT_SYSTEM = (
        "You are an expert software engineer. The user gives you a complete "
        "specification prompt. Execute it exactly: produce the full working "
        "code it asks for in ONE fenced code block, preceded by a one-line "
        "summary. Implement every requirement in the specification. "
        "Do not truncate the code."
    )

    def _execute_built_prompt(self, built: str):
        """Execute the /prompt-built specification as a coding task."""
        try:
            from core.brain import process_streaming
            process_streaming(
                built,
                on_chunk=lambda c: self.responseChunk.emit(c),
                on_code=lambda l, c: self.codeBlock.emit(l, c),
                system_prompt=self._EXEC_PROMPT_SYSTEM,
                intent_hint="CODING",
            )
        except Exception as e:
            self.taskFailed.emit(str(e))
        finally:
            self.taskFinished.emit()

    def _run_generate(self, text: str):
        """Menu-approved generation: compile the plan, execute immediately."""
        try:
            # A bare "code"/"do it" with no recoverable context would compile
            # into an empty "Task: Code" → the model writes placeholder junk.
            # Better to ask than to guess.
            if len(text.split()) <= 3 and not self._recent_context():
                self.responseChunk.emit(
                    "Generate code for what exactly? I don't have recent "
                    "conversation to go on — give me one line describing the task."
                )
                self.taskFinished.emit()
                return
            result = self.prompt_engine.process(text)
            model_id, system_prompt, user_prompt = \
                self.prompt_engine.approve_and_execute(result)
            user_prompt = self._with_context(user_prompt, text)
            self._process_approved_plan(model_id, system_prompt,
                                        user_prompt, "CODING")
        except Exception as e:
            self.taskFailed.emit(f"Generate error: {e}")

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
        try:
            domain = self._pending_engine_result.plan.domain
        except Exception:
            domain = None
        intent_hint = "CODING" if domain == "CODING" else None
        try:
            goal = self._pending_engine_result.plan.goal or ""
        except Exception:
            goal = ""
        model_id, system_prompt, user_prompt = \
            self.prompt_engine.approve_and_execute(self._pending_engine_result)
        user_prompt = self._with_context(user_prompt, goal)
        threading.Thread(
            target=self._process_approved_plan,
            args=(model_id, system_prompt, user_prompt, intent_hint),
            daemon=True,
        ).start()

    def _process_approved_plan(self, model_id: str, system_prompt: str,
                               user_prompt: str, intent_hint: str = None):
        try:
            from core.brain import process_streaming
            self.modelChanged.emit(model_id)
            process_streaming(
                user_prompt,
                on_chunk=lambda c: self.responseChunk.emit(c),
                on_code=lambda l, c: self.codeBlock.emit(l, c),
                system_prompt=system_prompt,
                model=model_id,          # the plan panel's model choice is real
                intent_hint=intent_hint, # CODING plans stay CODING (full code output)
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
            if self.speak_replies and not self._suppress_tts_once:
                threading.Thread(
                    target=self._speak_reply, args=(final,), daemon=True
                ).start()
        self._suppress_tts_once = False
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
