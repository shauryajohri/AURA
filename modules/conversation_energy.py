# modules/conversation_energy.py
# Conversation Energy — the "is this a good moment?" meter.
#
# Instead of the Attention Engine asking only "has it been N minutes?", it asks
# "does this feel like a good moment to reconnect?". That judgement is driven by
# a single 0–100 energy value:
#
#   • User chats frequently        → energy stays high (AURA stays quiet)
#   • Long silence                 → energy slowly drops
#   • Meaningful interaction        → energy instantly refills
#   • Background/study request     → no penalty (caller just doesn't decay it)
#   • User says "busy"             → meter frozen (no decay, no reconnect)
#   • Meeting detected             → meter frozen completely
#
# A "good moment" to reconnect is when energy has drained below a threshold AND
# the meter isn't frozen. High energy means the conversation is alive and AURA
# should stay out of the way.

import time
import threading

# ── Tunables ──────────────────────────────────────────────────────────────────
FULL_ENERGY          = 100.0
START_ENERGY         = 100.0   # energy at launch (fresh, engaged)
RECONNECT_THRESHOLD  = 45.0    # at/below this AND unfrozen → good moment to reconnect
DECAY_PER_MINUTE     = 18.0    # energy lost per minute of pure silence
MEANINGFUL_REFILL    = 100.0   # a real reply refills to full
MINOR_REFILL         = 25.0    # a small/background signal tops up a little

# Text the user can say to freeze / thaw the meter explicitly.
BUSY_PHRASES   = ("busy", "brb", "one sec", "hold on", "in a meeting",
                  "on a call", "give me a minute", "not now", "later")
FREE_PHRASES   = ("i'm back", "im back", "back now", "free now", "okay done",
                  "ok done", "done now", "what's up", "whats up")


class ConversationEnergy:
    def __init__(self):
        self._energy          = START_ENERGY
        self._last_update     = time.time()
        self._last_interaction = time.time()
        self._frozen          = False
        self._freeze_reason   = None
        self._lock            = threading.Lock()

    # ── Internal decay (call while holding the lock) ──────────────────────────
    def _decay_locked(self):
        now = time.time()
        if self._frozen:
            # Frozen meters don't decay — time simply doesn't count against you.
            self._last_update = now
            return
        elapsed_min = (now - self._last_update) / 60.0
        if elapsed_min > 0:
            self._energy = max(0.0, self._energy - elapsed_min * DECAY_PER_MINUTE)
            self._last_update = now

    # ── Public API ────────────────────────────────────────────────────────────
    def record_interaction(self, meaningful: bool = True):
        """User did something with AURA. Refills the meter. A meaningful
        exchange refills to full; a minor/background signal tops up a little."""
        with self._lock:
            self._decay_locked()
            if meaningful:
                self._energy = MEANINGFUL_REFILL
            else:
                self._energy = min(FULL_ENERGY, self._energy + MINOR_REFILL)
            self._last_interaction = time.time()
            # A genuine interaction clears a "busy" freeze — they're back.
            if self._freeze_reason == "busy":
                self._frozen = False
                self._freeze_reason = None
            self._last_update = time.time()

    def note_user_text(self, text: str):
        """Inspect a user message for explicit busy/free signals and freeze or
        thaw accordingly. Always counts as an interaction refill too."""
        low = (text or "").lower().strip()
        if any(p in low for p in FREE_PHRASES):
            self.unfreeze()
        elif any(p in low for p in BUSY_PHRASES):
            self.freeze("busy")

    def freeze(self, reason: str = "busy"):
        with self._lock:
            self._decay_locked()
            self._frozen = True
            self._freeze_reason = reason

    def unfreeze(self):
        with self._lock:
            self._frozen = False
            self._freeze_reason = None
            self._last_update = time.time()

    def set_environment_freeze(self, meeting: bool):
        """Called by the attention loop with detected environment state.
        A meeting freezes the meter; leaving a meeting thaws an env-freeze
        (but never overrides an explicit 'busy' the user asked for)."""
        with self._lock:
            if meeting:
                self._decay_locked()
                self._frozen = True
                self._freeze_reason = "meeting"
            elif self._freeze_reason == "meeting":
                self._frozen = False
                self._freeze_reason = None
                self._last_update = time.time()

    def level(self) -> float:
        with self._lock:
            self._decay_locked()
            return round(self._energy, 1)

    def is_frozen(self) -> bool:
        with self._lock:
            return self._frozen

    def freeze_reason(self):
        with self._lock:
            return self._freeze_reason

    def is_good_moment(self) -> bool:
        """True when it feels like a good moment to reconnect: the meter has
        drained below the reconnect threshold and isn't frozen."""
        with self._lock:
            self._decay_locked()
            if self._frozen:
                return False
            return self._energy <= RECONNECT_THRESHOLD

    def status(self) -> dict:
        with self._lock:
            self._decay_locked()
            return {
                "energy": round(self._energy, 1),
                "frozen": self._frozen,
                "freeze_reason": self._freeze_reason,
                "good_moment": (not self._frozen) and self._energy <= RECONNECT_THRESHOLD,
                "seconds_since_interaction": round(time.time() - self._last_interaction, 1),
            }


# ── Singleton ─────────────────────────────────────────────────────────────────
_energy = ConversationEnergy()

def get_energy() -> ConversationEnergy:
    return _energy
