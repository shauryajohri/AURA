"""
core/conversation_director.py
------------------------------
V2.1 — every user message passes through here FIRST. The Director owns:

  1. The current mode (NORMAL / PROMPT for now; STUDY, DEBUG, RESEARCH
     and MEMORY are V2.2 — the session pattern is already in place).
  2. Slash commands (/prompt, /prompt_end, /prompt save|export|clear, /help).
  3. The routing that used to be smeared across ui/app.py
     (CASUAL_BYPASS, OBSERVATION_PREFIXES, _requires_approval) and the
     coding permission gate: explicit requests run directly, ambiguous
     ones get a numbered options menu, and choices are remembered per
     topic for the session.

The Director never talks to the LLM or the UI itself. It returns a
Directive telling the controller (ui/app.py) what to do:

    kind="reply"     → show text as an AURA message instantly (no LLM)
    kind="chat"      → normal streaming chat (text may be augmented)
    kind="plan"      → prompt-engine → approval panel pipeline
    kind="generate"  → prompt-engine, but execute IMMEDIATELY (picking
                       "2. Generate code" from the menu already IS the
                       approval — no second panel)
    kind="llm_once"       → one clean LLM call (system+user), e.g. /prompt_end
    kind="execute_prompt" → run the /prompt-built prompt as a full coding
                            task (user picked "code"/"2" after the build)
"""

from dataclasses import dataclass


class Mode:
    NORMAL = "NORMAL"
    PROMPT = "PROMPT"
    # V2.2: STUDY, DEBUG, RESEARCH, MEMORY


@dataclass
class Directive:
    kind: str            # "reply" | "chat" | "plan" | "generate" | "llm_once" | "execute_prompt"
    text: str = ""       # reply text, or the (possibly augmented) chat/plan text
    system: str = ""     # llm_once only
    user: str = ""       # llm_once only
    intent: str = ""     # optional intent override for chat ("CASUAL" pins
                         # brain's classifier — it can otherwise decide
                         # CODING on its own and bypass the permission gate)


# ── Routing tables (moved here from ui/app.py) ───────────────────────────────

CASUAL_BYPASS = {
    "hi", "hey", "hoi", "hello", "yo", "sup", "what's up", "wassup",
    "hola", "howdy", "good morning", "good evening", "good night",
    "thanks", "thank you", "ok", "okay", "cool", "nice", "great",
    "bye", "goodbye", "see you", "cya", "later", "lol", "haha",
    "sure", "yep", "nope", "nah", "hmm", "hm", "ugh", "wow",
}

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

# ── Coding permission gate vocabulary ────────────────────────────────────────

CODING_TOPICS = {
    "dsa", "algorithm", "algorithms", "recursion", "leetcode", "array",
    "arrays", "linked list", "tree", "graph", "dp", "dynamic programming",
    "sorting", "python", "javascript", "typescript", "java", "c++", "sql",
    "code", "coding", "programming", "backend", "frontend", "api", "regex",
    "oop", "pointers", "stack", "queue", "hashmap", "binary search",
}

GENERATE_VERBS = {
    "write", "generate", "implement", "create", "build", "make me",
    "code me", "give me code", "refactor", "rewrite", "fix this code",
    "fix my code", "patch", "convert", "translate this code",
}

EXPLAIN_VERBS = {"explain", "what is", "what's", "how does", "how do", "why",
                 "teach", "walk me through", "help me understand"}
REVIEW_VERBS = {"review", "check my", "look at my", "audit", "critique",
                "is this correct", "find the bug", "debug my"}
PLAN_VERBS = {"plan", "roadmap", "schedule", "study plan", "curriculum"}
PRACTICE_VERBS = {"practice", "quiz", "questions", "exercises", "problems",
                  "test me", "drill"}

OPTIONS_MENU = (
    "How do you want me to help?\n"
    "1. Explain the topic\n"
    "2. Generate code\n"
    "3. Review your existing code\n"
    "4. Make a study plan\n"
    "5. Practice questions\n"
    "(reply with a number or word — I'll remember your choice for this topic)"
)

CHOICE_MAP = {
    "1": "EXPLAIN", "explain": "EXPLAIN", "explanation": "EXPLAIN",
    "2": "GENERATE", "generate": "GENERATE", "code": "GENERATE",
    "3": "REVIEW", "review": "REVIEW",
    "4": "PLAN", "plan": "PLAN", "study plan": "PLAN",
    "5": "PRACTICE", "practice": "PRACTICE", "questions": "PRACTICE",
}

INTENT_INSTRUCTIONS = {
    "EXPLAIN":  "Explain this clearly and conversationally. Do NOT write code unless explicitly asked: ",
    "REVIEW":   "Review this — point out issues and improvements. Do NOT rewrite or generate new code unless asked: ",
    "PLAN":     "Make a concise, practical plan for this. No code: ",
    "PRACTICE": "Give a few practice questions on this (no solutions unless asked): ",
}

# "I'm about to do X" — narration, not a request
STATEMENT_PREFIXES = ("i will ", "i'll ", "i am going to", "i'm going to",
                      "im going to", "let me ", "about to ", "gonna ")
# ...unless AURA is being asked to participate
ASK_MARKERS = ("you", "aura", "?", "please", "help")

_STOPWORDS = {"the", "a", "an", "on", "in", "at", "to", "for", "of", "and",
              "or", "is", "it", "my", "me", "i", "you", "with", "this",
              "that", "let's", "lets", "want", "need", "focus", "start"}


def _keywords(text: str) -> frozenset:
    words = text.lower().replace("/", " ").replace(",", " ").split()
    return frozenset(w.strip("!?.") for w in words
                     if w.strip("!?.") not in _STOPWORDS and len(w) > 1)


class ConversationDirector:
    def __init__(self, on_mode_changed=None):
        self.mode = Mode.NORMAL
        self._on_mode_changed = on_mode_changed
        self._pending_gate = None      # original ambiguous text awaiting a choice
        self._topic_choices = []       # [(frozenset keywords, choice)]
        self._pending_prompt_action = False   # menu offered on a built prompt

        from modules.prompt_maker import PromptSession
        self.prompt_session = PromptSession()

    # ── mode plumbing ─────────────────────────────────────────────────────
    def _set_mode(self, mode: str):
        if mode != self.mode:
            self.mode = mode
            if self._on_mode_changed:
                self._on_mode_changed(mode)

    # ── main entry ────────────────────────────────────────────────────────
    def handle(self, text: str) -> Directive:
        t = text.strip()
        if t.startswith("/"):
            return self._handle_command(t)

        if self.mode == Mode.PROMPT:
            n = self.prompt_session.add(t)
            return Directive("reply", f"[prompt] line {n} captured. /prompt_end to build, /prompt clear to restart.")

        return self._handle_normal(t)

    # ── slash commands (work in ANY mode) ────────────────────────────────
    def _handle_command(self, t: str) -> Directive:
        cmd = " ".join(t.lower().split())

        if cmd in ("/prompt", "/prompt start"):
            self._set_mode(Mode.PROMPT)
            self.prompt_session.clear()
            return Directive("reply",
                "Prompt Maker enabled. Everything you type is now buffered as "
                "prompt instructions — nothing is sent to the model. "
                "/prompt_end to build, /prompt clear to restart, /prompt save · /prompt export after building.")

        if cmd in ("/prompt_end", "/prompt end"):
            if self.mode != Mode.PROMPT or self.prompt_session.is_empty():
                self._set_mode(Mode.NORMAL)
                return Directive("reply", "Nothing buffered. /prompt to start a session first.")
            self._set_mode(Mode.NORMAL)
            system, user = self.prompt_session.finalize_payload()
            return Directive("llm_once", system=system, user=user)

        if cmd == "/prompt clear":
            self.prompt_session.clear()
            return Directive("reply", "[prompt] buffer cleared. Keep typing.")

        if cmd == "/prompt save":
            ok, msg = self.prompt_session.save()
            return Directive("reply", msg)

        if cmd == "/prompt export":
            ok, msg = self.prompt_session.export_clipboard()
            return Directive("reply", msg)

        if cmd == "/help":
            return Directive("reply",
                "Commands: /prompt (start session) · /prompt_end (build) · "
                "/prompt clear · /prompt save · /prompt export · /help\n"
                "Coming in V2.2: /study, /research, /memory, /debug.")

        return Directive("reply", f"Unknown command: {t.split()[0]}. Try /help.")

    # extra aliases that act on a freshly built prompt
    _PROMPT_ACTION_EXTRA = {"run": "GENERATE", "run it": "GENERATE",
                            "execute": "GENERATE", "go": "GENERATE",
                            "use it": "GENERATE", "do it": "GENERATE"}

    # ── normal-mode routing (absorbed from ui/app.py) ─────────────────────
    def _handle_normal(self, t: str) -> Directive:
        low = t.lower().rstrip("!.,?")

        # A prompt was just built (/prompt_end) and the menu was offered on
        # it — "2"/"code"/"run" executes THAT prompt directly. This is the
        # scalable path: the task spec travels with the request instead of
        # being fished out of conversation history.
        if self._pending_prompt_action and self.prompt_session.last_result:
            choice = self._resolve_choice(low) or self._PROMPT_ACTION_EXTRA.get(low)
            if choice:
                self._pending_prompt_action = False
                built = self.prompt_session.last_result
                if choice == "GENERATE":
                    return Directive("execute_prompt", built)
                return Directive("chat", INTENT_INSTRUCTIONS[choice] + "\n" + built)
            # anything else = user moved on; drop the offer
            self._pending_prompt_action = False

        # A pending permission menu? Try to resolve the choice.
        if self._pending_gate is not None:
            choice = self._resolve_choice(low)
            if choice:
                original = self._pending_gate
                self._pending_gate = None
                self._topic_choices.append((_keywords(original), choice))
                return self._route_choice(choice, original)
            # Not an answer — drop the menu and treat as a fresh message.
            self._pending_gate = None

        if low in CASUAL_BYPASS:
            return Directive("chat", t)

        if any(low.startswith(p) for p in PLANNER_PREFIXES):
            return Directive("plan", t)

        if any(low.startswith(p) for p in OBSERVATION_PREFIXES):
            return Directive("chat", t)

        # Statements of intent ("i will perform some test cases") are the
        # user narrating THEIR next step — not a request. Without this,
        # brain's own classifier marks them CODING and generates
        # unsolicited code, bypassing the permission gate entirely.
        if (any(low.startswith(p) for p in STATEMENT_PREFIXES)
                and not any(m in low for m in ASK_MARKERS)):
            return Directive("chat", t, intent="CASUAL")

        return self._coding_gate(t, low)

    @staticmethod
    def _resolve_choice(low: str) -> str | None:
        """Match menu answers loosely: '2', 'generate', '2 generate code',
        'explain please' — anything short that clearly names an option."""
        choice = CHOICE_MAP.get(low)
        if choice:
            return choice
        words = low.split()
        if not words or len(words) > 4:
            return None            # long messages are new requests, not answers
        first = CHOICE_MAP.get(words[0])
        if first:
            return first
        for key, val in CHOICE_MAP.items():
            if not key.isdigit() and key in low:
                return val
        return None

    # ── coding permission gate ────────────────────────────────────────────
    def _coding_gate(self, t: str, low: str) -> Directive:
        has_topic = any(topic in low for topic in CODING_TOPICS)
        if not has_topic:
            return Directive("chat", t)   # not code-adjacent → normal chat

        # Explicit action verb → route directly, no menu.
        if any(v in low for v in GENERATE_VERBS):
            return Directive("plan", t)   # code generation still goes through approval
        for verbs, intent in ((EXPLAIN_VERBS, "EXPLAIN"), (REVIEW_VERBS, "REVIEW"),
                              (PLAN_VERBS, "PLAN"), (PRACTICE_VERBS, "PRACTICE")):
            if any(v in low for v in verbs):
                return Directive("chat", INTENT_INSTRUCTIONS[intent] + t)

        # Ambiguous ("focus on DSA") — do we remember a choice for this topic?
        kw = _keywords(t)
        for stored_kw, choice in reversed(self._topic_choices):
            overlap = len(kw & stored_kw)
            if stored_kw and overlap / len(stored_kw) >= 0.5:
                return self._route_choice(choice, t)

        # Genuinely ambiguous → ask.
        self._pending_gate = t
        return Directive("reply", OPTIONS_MENU)

    def _route_choice(self, choice: str, original: str) -> Directive:
        if choice == "GENERATE":
            # The menu choice is the approval — skip the plan panel.
            return Directive("generate", original)
        return Directive("chat", INTENT_INSTRUCTIONS[choice] + original)

    # ── hooks for the controller ──────────────────────────────────────────
    def note_prompt_result(self, text: str):
        """Controller calls this with the finalized prompt so /prompt save
        and /prompt export operate on the built result — and so the next
        short answer ("2", "code", "run") executes it."""
        self.prompt_session.last_result = text
        self._pending_prompt_action = True
