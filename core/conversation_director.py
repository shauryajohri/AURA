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

import re as _re
from dataclasses import dataclass


class Mode:
    NORMAL = "NORMAL"
    PROMPT = "PROMPT"
    # v2.1 workspace modes — each entered via /<name>, left via /<name>_end
    CODE = "CODE"
    RESEARCH = "RESEARCH"
    DISCUSSION = "DISCUSSION"
    PLAN = "PLAN"


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

# First-person NARRATION: the user describing what THEY are doing / just did,
# optionally after a filler ("yess", "ok", "lol"). This is the fix for the
# coding-menu misfire — "i am doing some vibe coding" name-drops a coding topic
# ("coding") but is a statement about the user, NOT a request for AURA to act,
# so it must get a warm reply, never the work menu. A real question or an
# AURA-directed ask ("...can you help?") still falls through to the gate.
_NARRATION_RE = _re.compile(
    r"^(?:yes+|yeah|yep|yup|nah|ok(?:ay)?|so|and|well|lol|haha|hmm|dude|bro|man|"
    r"just|currently|right now)?[\s,]*"
    r"i(?:'?m|'?ve| am| have| just| was| did| been| finished| already|'?ll be)\b"
    r".*\b(?:doing|do|working|work|coding|code|writing|wrote|building|built|"
    r"making|made|learning|studying|grinding|practicing|practising|messing|"
    r"hacking|debugging|playing|reading|watching|trying|busy|on)\b"
)
# If any of these appear, treat it as a real request and let the gate decide.
# NOTE: "aura" is intentionally NOT here — the project itself is named AURA, so
# "i'm working on aura" is narration, and a real command like "aura write X"
# won't match _NARRATION_RE anyway (it requires a first-person "i ..." start).
_NARRATION_ASK_GUARD = ("?", "you", "please", "can you", "could you",
                        "how do", "how to", "help me", "show me", "give me",
                        "teach", "walk me", "should i")


def _is_narration(low: str) -> bool:
    """True when the message is the user narrating their own activity rather
    than asking AURA for anything."""
    if any(m in low for m in _NARRATION_ASK_GUARD):
        return False
    return bool(_NARRATION_RE.search(low))

# Personal/emotional talk → PERSONAL lane (warm persona, no 2-sentence clamp,
# never snaps "send me something that makes sense" at an interjection)
PERSONAL_MARKERS = (
    "i feel", "i'm tired", "im tired", "i am tired", "stressed", "sad",
    "happy", "excited", "bored", "lonely", "annoyed", "frustrated",
    "my day", "my life", "how are you", "how r u", "how was your",
    "talk to me", "i'm done", "im done", "i give up", "proud of",
    "love", "hate", "miss you", "thank",
    "chill", "chilling", "relax", "vibing", "taking a break", "just watching",
)

# negation up to 2 words before a coding topic = declining, not requesting
_NEG_NEAR_TOPIC = _re.compile(
    r"\b(?:no|not|nah|nope|don'?t|dont|stop|quit|enough|zero|done with)\s+(?:\w+\s+){0,2}(?:"
    + "|".join(_re.escape(topic) for topic in sorted(CODING_TOPICS, key=len, reverse=True))
    + r")\b"
)

_STOPWORDS = {"the", "a", "an", "on", "in", "at", "to", "for", "of", "and",
              "or", "is", "it", "my", "me", "i", "you", "with", "this",
              "that", "let's", "lets", "want", "need", "focus", "start"}


def _keywords(text: str) -> frozenset:
    words = text.lower().replace("/", " ").replace(",", " ").split()
    return frozenset(w.strip("!?.") for w in words
                     if w.strip("!?.") not in _STOPWORDS and len(w) > 1)


# ── Workspace modes (v2.1) ───────────────────────────────────────────────────
# Each mode is entered with /<name>, stays active (so every following message
# is handled in that mode, like /prompt), and is left with /<name>_end. Adding
# a new mode later = one WORKSPACE entry + one instruction + one UI chip.

RESEARCH_INSTRUCTION = (
    "You are in RESEARCH mode. Do NOT answer off the cuff — deliver a "
    "structured, evidence-based research report on the user's goal. Use these "
    "sections as headings (skip any that genuinely don't apply):\n"
    "Objective\nCurrent Position\nRequired Skills / Knowledge\nGap Analysis\n"
    "Roadmap (phased)\nKey Companies / Players\nTimeline\n"
    "Salary / Market (if relevant)\nResources\nRecommendation\n"
    "Be objective and specific. End by offering to go deeper on any section."
)

DISCUSSION_INSTRUCTION = (
    "You are in DISCUSSION mode — a sharp brainstorming partner, NOT a yes-man. "
    "Do not simply agree; pressure-test the idea. Use these headings:\n"
    "Pros\nCons\nRisks\nAlternatives\nRecommendation\n"
    "Be opinionated and honest — if it's a weak idea, say so and explain why. "
    "End with one pointed question that pushes the thinking further."
)

PLAN_INSTRUCTION = (
    "You are in PLANNING mode. Turn the user's idea into an executable "
    "roadmap. Use these headings:\n"
    "Goal\nArchitecture / Approach\nDependencies\nSteps (ordered)\n"
    "Estimated Time\nRisks\nTesting\nCompletion Criteria\n"
    "Be concrete and realistic. No code — this is the plan, not the build."
)

# command name → behavior. instruction=None means the mode relies purely on its
# intent's own formatting (CODE uses the CODING pipeline / Laguna).
WORKSPACE = {
    "code": {
        "mode": Mode.CODE, "intent": "CODING", "instruction": None,
        "blurb": "💻 Code mode on — every message is a coding task, straight to "
                 "the code. What are we building? (/code_end to exit)",
    },
    "research": {
        "mode": Mode.RESEARCH, "intent": "RESEARCH", "instruction": RESEARCH_INSTRUCTION,
        "blurb": "🔍 Research mode on — I'll research and build a structured "
                 "report instead of answering off the cuff. What's the goal? "
                 "(/research_end to exit)",
    },
    "discussion": {
        "mode": Mode.DISCUSSION, "intent": "DISCUSSION", "instruction": DISCUSSION_INSTRUCTION,
        "blurb": "🧠 Discussion mode on — I'll challenge the idea, not just "
                 "agree. What's on your mind? (/discussion_end to exit)",
    },
    "plan": {
        "mode": Mode.PLAN, "intent": "PLAN", "instruction": PLAN_INSTRUCTION,
        "blurb": "📋 Planning mode on — give me an idea and I'll turn it into a "
                 "roadmap. (/plan_end to exit)",
    },
}
# active Mode → its spec, for routing in-mode messages
MODE_BY_STATE = {spec["mode"]: spec for spec in WORKSPACE.values()}


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

        # In a workspace mode (CODE/RESEARCH/DISCUSSION/PLAN) every message is
        # handled in-mode until the matching /<name>_end.
        if self.mode in MODE_BY_STATE:
            return self._mode_directive(MODE_BY_STATE[self.mode], t)

        return self._handle_normal(t)

    def _mode_directive(self, spec: dict, text: str) -> Directive:
        """Route one message through an active workspace mode: prepend the
        mode's structured instruction (if any) and pin its routing intent."""
        if spec["instruction"]:
            payload = spec["instruction"] + "\n\nUser request: " + text
        else:
            payload = text
        return Directive("chat", payload, intent=spec["intent"])

    # ── slash commands (work in ANY mode) ────────────────────────────────
    def _handle_command(self, t: str) -> Directive:
        cmd = " ".join(t.lower().split())

        # ── Workspace modes: /code /research /discussion /plan (+ *_end) ────
        parts = t.split(maxsplit=1)
        head = parts[0].lower()          # "/research"
        rest = parts[1].strip() if len(parts) > 1 else ""   # keep original case
        name = head[1:]                  # "research"
        if name in WORKSPACE:
            spec = WORKSPACE[name]
            self._set_mode(spec["mode"])
            # An inline goal runs immediately; bare "/research" just enters.
            if rest:
                return self._mode_directive(spec, rest)
            return Directive("reply", spec["blurb"])
        if name.endswith("_end") and name[:-4] in WORKSPACE:
            was = name[:-4]
            self._set_mode(Mode.NORMAL)
            return Directive("reply",
                f"{was.capitalize()} mode closed — back to normal chat.")

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
                "Workspace modes (type the command, work, then /<name>_end):\n"
                "💻 /code — coding partner (straight to code)\n"
                "🔍 /research — structured, evidence-based reports\n"
                "🧠 /discussion — brainstorming that challenges your idea\n"
                "📋 /plan — turn an idea into an executable roadmap\n"
                "✍️ /prompt — prompt engineering (buffers, /prompt_end to build)\n"
                "Tip: /research <goal> enters the mode AND runs it in one go.\n"
                "Prompt extras: /prompt clear · /prompt save · /prompt export")

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
            return Directive("chat", t, intent="PERSONAL")

        # "wassup, nothing just chilling" — casual opener, casual message,
        # even though the whole string isn't an exact bypass match.
        first_word = low.split()[0].strip(",.!?") if low.split() else ""
        if first_word in CASUAL_BYPASS:
            return Directive("chat", t, intent="PERSONAL")

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
            return Directive("chat", t, intent="PERSONAL")

        # First-person narration ("yess i am doing some vibe coding") — the
        # user is describing what THEY are up to, not asking for help. Route to
        # warm chat before the coding gate can pop the work menu on the topic
        # word. Real asks ("...can you help?") are excluded by the guard.
        if _is_narration(low):
            return Directive("chat", t, intent="PERSONAL")

        # Emotional / personal talk → warm lane
        if any(m in low for m in PERSONAL_MARKERS):
            return Directive("chat", t, intent="PERSONAL")

        # Tiny interjections ("nono", "ugh", "bruh") aren't tasks — respond
        # like a person, don't demand "something that makes sense".
        # (Coding-topic words like a bare "code" still go to the gate/menu.)
        if (len(low.split()) <= 2
                and not any(ch.isdigit() for ch in low)
                and not any(topic in low for topic in CODING_TOPICS)):
            return Directive("chat", t, intent="PERSONAL")

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

        # Negation NEAR the coding word: "no code for now", "not doing python
        # today", "done with dsa" — declining must not pop the options menu,
        # at ANY message length ("i mean no code for now so jusst chill").
        # Negation AFTER the topic ("why does my python code not work") is a
        # real request → still gates.
        if _NEG_NEAR_TOPIC.search(low):
            return Directive("chat", t, intent="PERSONAL")
        # Short declines without the topic adjacency ("nah not today man")
        if (len(low.split()) <= 6
                and _re.search(r"\b(no|not|nah|nope|don'?t|dont|stop|quit|enough|done|later)\b", low)):
            return Directive("chat", t, intent="PERSONAL")

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
