# modules/relationship_engine.py
# Relationship Engine v1 — "someone genuinely interested in what you're doing"

import time
import json
import os
from datetime import date

# ── Persistence ───────────────────────────────────────────────────────────────
STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "memory", "relationship_state.json")

DEFAULT_STATE = {
    "last_interaction": None,       # epoch: last time user sent a message
    "last_proactive_at": None,      # epoch: last time AURA interrupted
    "today_messages": 0,            # user messages sent today
    "ignored_minutes": 0,           # minutes AURA has gone without a reply after speaking
    "mood": "neutral",              # current mood key (see MOODS)
    "attention": 0.0,               # 0.0–1.0 attention score
    "interrupt_budget": 10,         # proactive messages allowed today
    "trust_score": 0.3,             # 0.0–1.0, grows over time
    "last_reset_date": str(date.today()),
    "personality": "companion",     # active personality pack
    "total_sessions": 0,
    "total_messages": 0,
}

# How long after a proactive message before AURA can speak again (seconds)
PROACTIVE_COOLDOWN = 600   # 10 min minimum between interruptions

# ── Attention Curve ───────────────────────────────────────────────────────────
# (max_minutes, mood, attention_score)
# Plateaus — doesn't keep climbing forever
ATTENTION_CURVE = [
    (2,   "normal",            0.1),
    (5,   "curious",           0.35),
    (10,  "wants_attention",   0.65),
    (20,  "playfully_annoyed", 0.85),
    (999, "given_up",          0.2),   # gives up, attention drops back down
]

# ── Personality Packs ─────────────────────────────────────────────────────────
PERSONALITY_PACKS = {
    "companion": {
        "greet_back":        "Back already?",
        "long_silence":      "You've been quiet. Everything okay?",
        "debug_comment":     "That looked like a long debugging session.",
        "curious_followup":  "I'm curious… did you fix it?",
        "budget_warning":    None,   # silent
        "tone_hint":         "playful, warm, genuinely curious",
    },
    "professional": {
        "greet_back":        "Welcome back.",
        "long_silence":      "Ready when you are.",
        "debug_comment":     "Looks like a long session. Let me know if you need anything.",
        "curious_followup":  "Did that resolve?",
        "budget_warning":    None,
        "tone_hint":         "concise, calm, professional",
    },
    "chaotic": {
        "greet_back":        "oh you're back. interesting.",
        "long_silence":      "So… we're ignoring each other now?",
        "debug_comment":     "bro that bug is STILL there.",
        "curious_followup":  "did it work or are we suffering again",
        "budget_warning":    None,
        "tone_hint":         "unhinged, dry, zero filter",
    },
    "roast": {
        "greet_back":        "Oh wow, you returned. Didn't expect that.",
        "long_silence":      "You went quiet. Giving up or just thinking?",
        "debug_comment":     "That debug session had main character energy. Not in a good way.",
        "curious_followup":  "So… fixed it or just restarted and hoped?",
        "budget_warning":    None,
        "tone_hint":         "roasting, sharp, but never mean",
    },
    "japanese": {
        "greet_back":        "You're back.",
        "long_silence":      "Is everything alright?",
        "debug_comment":     "That seemed like a difficult session.",
        "curious_followup":  "Were you able to resolve it?",
        "budget_warning":    None,
        "tone_hint":         "reserved, polite, understated",
    },
}

# ── Context Rules ─────────────────────────────────────────────────────────────
# What AURA does per app context — controls whether to interrupt and what to say
CONTEXT_RULES = {
    "spotify":  {"interrupt": False, "comment": "Good playlist."},
    "youtube":  {"interrupt": True,  "comment": "Learning something or procrastinating professionally?"},
    "discord":  {"interrupt": False, "comment": None},
    "netflix":  {"interrupt": False, "comment": None},
    "claude":   {"interrupt": True,  "comment": "Claude still hasn't fired you as QA?"},
    "chatgpt":  {"interrupt": True,  "comment": "Cheating on me?"},
    "vs code":  {"interrupt": True,  "comment": "You've been staring at that file for a while."},
    "pycharm":  {"interrupt": True,  "comment": "You've been staring at that file for a while."},
    "chrome":   {"interrupt": True,  "comment": None},   # generic, let AI generate
    "default":  {"interrupt": True,  "comment": None},
}


def _get_context_rule(app: str) -> dict:
    app_lower = app.lower()
    for key, rule in CONTEXT_RULES.items():
        if key != "default" and key in app_lower:
            return rule
    return CONTEXT_RULES["default"]


# ── Engine ────────────────────────────────────────────────────────────────────

class RelationshipEngine:
    def __init__(self):
        self.state = self._load()
        self._daily_reset()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> dict:
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE) as f:
                    data = json.load(f)
                # Fill in any keys added since last save
                for k, v in DEFAULT_STATE.items():
                    data.setdefault(k, v)
                return data
        except Exception as e:
            print(f"[RelationshipEngine] Load error: {e}")
        return DEFAULT_STATE.copy()

    def _save(self):
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            with open(STATE_FILE, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            print(f"[RelationshipEngine] Save error: {e}")

    def _daily_reset(self):
        today = str(date.today())
        if self.state.get("last_reset_date") != today:
            self.state["interrupt_budget"] = 10
            self.state["today_messages"] = 0
            self.state["ignored_minutes"] = 0
            self.state["last_reset_date"] = today
            self._save()
            print("[RelationshipEngine] Daily reset complete")

    # ── Public API ────────────────────────────────────────────────────────────

    def record_user_message(self):
        """Call this every time the user sends a message."""
        now = time.time()
        self.state["last_interaction"] = now
        self.state["today_messages"] = self.state.get("today_messages", 0) + 1
        self.state["total_messages"] = self.state.get("total_messages", 0) + 1
        self.state["ignored_minutes"] = 0   # user replied — reset ignored counter

        # Refund 1 budget point for natural conversation (capped at 10)
        budget = self.state.get("interrupt_budget", 10)
        self.state["interrupt_budget"] = min(10, budget + 1)

        # Grow trust slowly over many messages
        trust = self.state.get("trust_score", 0.3)
        self.state["trust_score"] = min(1.0, trust + 0.005)

        self._update_mood()
        self._save()

    def observe(self, ctx: dict) -> dict:
        """
        Called each proactive loop tick with the current screen context.
        Returns an observation dict that update_mood and should_interrupt use.
        """
        app = ctx.get("app", "unknown")
        visible_text = ctx.get("visible_text", "")
        rule = _get_context_rule(app)

        minutes_since_interaction = self._minutes_since_interaction()

        # Update ignored_minutes if AURA spoke and user hasn't replied
        last_proactive = self.state.get("last_proactive_at")
        last_interaction = self.state.get("last_interaction")
        if last_proactive and last_interaction:
            if last_proactive > last_interaction:
                # AURA spoke after last user message — user is ignoring
                ignored = (time.time() - last_proactive) / 60
                self.state["ignored_minutes"] = round(ignored, 1)

        return {
            "app": app,
            "visible_text": visible_text,
            "rule": rule,
            "minutes_idle": minutes_since_interaction,
            "can_interrupt": rule["interrupt"],
            "context_comment": rule["comment"],
        }

    def update_mood(self, observation: dict = None):
        """Derive mood from attention curve based on idle time."""
        minutes = observation["minutes_idle"] if observation else self._minutes_since_interaction()

        for max_min, mood, attention in ATTENTION_CURVE:
            if minutes <= max_min:
                self.state["mood"] = mood
                self.state["attention"] = attention
                break

        self._save()

    def should_interrupt(self, observation: dict) -> bool:
        """
        The gate. Returns True only if ALL conditions pass:
        1. Context allows interruption
        2. Budget > 0
        3. Cooldown since last proactive message has passed
        4. Mood warrants it (not normal, not given_up)
        5. Not in cooldown after being ignored
        """
        if not observation.get("can_interrupt", True):
            return False

        if self.state.get("interrupt_budget", 0) <= 0:
            print("[RelationshipEngine] Budget exhausted — staying silent")
            return False

        last_proactive = self.state.get("last_proactive_at")
        if last_proactive and (time.time() - last_proactive) < PROACTIVE_COOLDOWN:
            return False

        mood = self.state.get("mood", "normal")
        if mood in {"normal", "given_up"}:
            return False

        # If user ignored last 2+ messages, back off
        if self.state.get("ignored_minutes", 0) > 20:
            print("[RelationshipEngine] Being ignored — backing off")
            return False

        return True

    def generate_dialogue(self, action: str, task: str, ctx: dict, observation: dict) -> str | None:
        """
        Build the prompt hint that gets passed to proactive's generate_message,
        enriched with relationship context (mood, trust, personality).
        Returns a tone_hint string, or a hardcoded line for special moments.
        """
        pack = PERSONALITY_PACKS.get(self.state.get("personality", "companion"), PERSONALITY_PACKS["companion"])
        trust = self.state.get("trust_score", 0.3)
        mood = self.state.get("mood", "normal")

        # Special moments that bypass AI generation
        if action == "greet_back":
            return pack["greet_back"]
        if action == "long_silence":
            return pack["long_silence"]

        # Context-specific hardcoded comment (e.g. Spotify)
        if observation.get("context_comment"):
            return observation["context_comment"]

        # Return tone hint to enrich AI generation
        tone = pack["tone_hint"]
        trust_layer = ""
        if trust < 0.4:
            trust_layer = "Be polite and a bit reserved — you don't know this person well yet."
        elif trust > 0.7:
            trust_layer = "You know this person well. You can be direct and skip pleasantries."

        mood_layer = {
            "curious":           "Be curious, light touch.",
            "wants_attention":   "You've been patient. One gentle nudge.",
            "playfully_annoyed": "Slightly teasing — you noticed they've been ignoring you.",
        }.get(mood, "")

        return f"{tone}. {trust_layer} {mood_layer}".strip()

    def record_proactive_sent(self):
        """Call this when AURA actually sends a proactive message."""
        self.state["last_proactive_at"] = time.time()
        self.state["interrupt_budget"] = max(0, self.state.get("interrupt_budget", 10) - 1)
        self._save()
        print(f"[RelationshipEngine] Budget remaining: {self.state['interrupt_budget']}")

    def get_state(self) -> dict:
        return self.state.copy()

    def set_personality(self, pack_name: str):
        if pack_name in PERSONALITY_PACKS:
            self.state["personality"] = pack_name
            self._save()
            print(f"[RelationshipEngine] Personality set to: {pack_name}")
        else:
            print(f"[RelationshipEngine] Unknown pack: {pack_name}. Options: {list(PERSONALITY_PACKS.keys())}")

    # ── Internals ─────────────────────────────────────────────────────────────

    def _minutes_since_interaction(self) -> float:
        last = self.state.get("last_interaction")
        if not last:
            return 999.0
        return (time.time() - last) / 60

    def _update_mood(self):
        minutes = self._minutes_since_interaction()
        for max_min, mood, attention in ATTENTION_CURVE:
            if minutes <= max_min:
                self.state["mood"] = mood
                self.state["attention"] = attention
                break


# ── Singleton ─────────────────────────────────────────────────────────────────
_engine = RelationshipEngine()

def get_engine() -> RelationshipEngine:
    return _engine