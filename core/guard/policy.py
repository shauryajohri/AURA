"""
core/guard/policy.py
--------------------
Buddy Lock's judgement: for each message, is the person talking to AURA her
buddy (the owner), a guest the owner vouched for, or nobody she should answer?

Evidence
--------
camera  The renderer sends a frame every few seconds while AURA is on screen
        (presence) and a fresh frame WITH every typed message (the check the
        owner asked for: "when typing, check the camera").
voice   A voice message carries the utterance audio. A confident speaker
        match is enough on its own; anything short or unsure falls back to
        the camera, exactly as if it had been typed.
PIN     Recovery when the camera can't help (no webcam, bad light). Opens a
        time-boxed owner session.

Rules for a message
-------------------
1. Voice matches the owner                          → owner
2. Fresh frame shows the owner                      → owner
     …but if the voice was confidently NOT the owner and someone else is in
     frame too, the speaker is that someone            → guest ("I'm there")
3. Fresh frame shows a face that is *probably* the owner (looking down at the
   keyboard drags the score) and the owner was clearly seen in the last
   LOCK_AFTER_S                                     → owner
4. Frame shows nobody, owner clearly seen within GRACE_S → owner
   (detection misses are common; a stranger in frame is never excused)
5. PIN session open                                 → owner
6. A guest pass covers the face in frame            → guest
7. Otherwise                                        → not answered

Walking away
------------
The UI and REST API stay unlocked for LOCK_AFTER_S after the owner was last
clearly seen — but if the camera shows someone else (and not the owner) for
STRANGER_TAKEOVER_FRAMES frames in a row, the owner counts as gone at once.

Guest passes
------------
Granted only by a message that already passed as the owner ("you can help
him"). If the guest is in frame at that moment the pass is bound to their
face; if not, it's *unclaimed* and binds to the first unfamiliar face that
shows up — so "help him" can't be picked up by a third person later. Passes
live in memory only: a restart ends them.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

from core.guard import commands
from core.guard.face import best_match, cosine

LOCK_AFTER_S = 90         # owner unseen this long → UI and API lock
GRACE_S = 20              # empty frame tolerated this long after a clear sighting
FRESH_S = 6               # a sighting this recent can stand in for a missing frame
PIN_SESSION_S = 10 * 60
# "Probably the owner": OpenCV's published SFace same-person threshold. Only
# honoured right after a clear (>= face_threshold) sighting — it's what lets
# the owner glance down at the keyboard without being locked out. Set from
# testing: a stranger scored 0.26 against a 3-sample enrollment, so 0.30 was
# too close for comfort.
CONTINUITY_THRESHOLD = 0.363
PIN_FREE_ATTEMPTS = 5
# Consecutive frames showing faces but not the owner (not even "probably")
# before the owner counts as gone. Without this, someone sitting down right
# after the owner left inherited the unlocked UI for the rest of LOCK_AFTER_S.
# Two, not one, so a single bad frame of the owner can't flash the lock.
STRANGER_TAKEOVER_FRAMES = 2


@dataclass
class Sighting:
    at: float
    faces: int
    owner: bool                       # a face cleared the owner threshold
    owner_score: float                # best score of any face in frame
    strangers: list = field(default_factory=list, repr=False)  # embeddings, largest first


@dataclass
class GuestPass:
    id: str
    granted_at: float
    expires_at: float
    faces: list = field(default_factory=list, repr=False)  # [] = unclaimed

    @property
    def claimed(self) -> bool:
        return bool(self.faces)


@dataclass
class Decision:
    allowed: bool
    role: str | None          # "owner" | "guest" | None
    reason: str               # machine-readable why
    message: str = ""         # deny text, or the reply to a guard command
    handled: bool = False     # True → a guard command consumed the message (no LLM)
    detail: dict = field(default_factory=dict)


class Guard:
    def __init__(self, vault, face_engine, voice_engine, clock=time.time) -> None:
        self.vault = vault
        self.face = face_engine
        self.voice = voice_engine
        self.clock = clock
        self._lock = threading.RLock()
        self._owner_seen_at = 0.0
        self._guest_seen_at = 0.0
        self._last: Sighting | None = None
        self._last_frame_at = 0.0
        self._camera_error = ""
        self._pin_until = 0.0
        self._pin_failures = 0
        self._pin_blocked_until = 0.0
        self._passes: list[GuestPass] = []
        self._stranger_streak = 0

    # ── basic state ────────────────────────────────────────────────────────
    @property
    def active(self) -> bool:
        """Is the lock actually enforcing? Off until an owner is enrolled."""
        v = self.vault
        return v.enabled and (bool(v.faces) or v.corrupt)

    def owner_name(self) -> str:
        if self.vault.owner_name and self.vault.owner_name != "my buddy":
            return self.vault.owner_name
        try:
            from core.identity import CREATOR
            return CREATOR
        except Exception:  # noqa: BLE001
            return "my buddy"

    def _passes_now(self, now: float) -> list[GuestPass]:
        self._passes = [p for p in self._passes if p.expires_at > now]
        return self._passes

    def owner_present(self, window: float = LOCK_AFTER_S) -> bool:
        """Owner clearly seen/heard recently (or a PIN session is open)."""
        now = self.clock()
        return (now - self._owner_seen_at) <= window or now < self._pin_until

    def role(self) -> str:
        """Who the UI and REST API are serving right now."""
        if not self.active:
            return "open"
        with self._lock:
            now = self.clock()
            if self.owner_present():
                return "owner"
            for p in self._passes_now(now):
                if not p.claimed or (now - self._guest_seen_at) <= LOCK_AFTER_S:
                    return "guest"
            return "locked"

    # ── camera ─────────────────────────────────────────────────────────────
    def observe(self, frame: bytes) -> Sighting:
        """Analyse one camera frame and update presence. Raises on an engine
        failure or an undecodable frame (callers decide what that means)."""
        try:
            faces = self.face.analyze(frame)
        except RuntimeError as e:
            self._camera_error = str(e)
            raise
        self._camera_error = ""
        enrolled = self.vault.faces
        thr = self.vault.tuning("face_threshold")
        now = self.clock()

        scores = [best_match(f.embedding, enrolled) for f in faces]
        owner_idx = max(range(len(faces)), key=lambda i: scores[i]) if faces else -1
        owner = owner_idx >= 0 and scores[owner_idx] >= thr
        strangers = [f.embedding for i, f in enumerate(faces)
                     if scores[i] < CONTINUITY_THRESHOLD]
        s = Sighting(at=now, faces=len(faces), owner=owner,
                     owner_score=scores[owner_idx] if faces else 0.0,
                     strangers=strangers)
        with self._lock:
            self._last = s
            self._last_frame_at = now
            if owner:
                self._owner_seen_at = now
                self._stranger_streak = 0
            elif faces and s.owner_score < CONTINUITY_THRESHOLD:
                self._stranger_streak += 1
                if self._stranger_streak >= STRANGER_TAKEOVER_FRAMES and self._owner_seen_at:
                    print("[Guard] someone else is at the camera — owner presence ended")
                    self._owner_seen_at = 0.0
            elif faces:
                self._stranger_streak = 0  # "probably the owner"
            # an empty frame says nothing about who's there: streak unchanged
            self._note_guests(s, now)
        return s

    def _note_guests(self, s: Sighting, now: float) -> None:
        """Bind unclaimed passes to the first unfamiliar face; refresh the
        'guest seen' clock when a bound guest is in frame."""
        if not s.strangers:
            return
        thr = self.vault.tuning("face_threshold")
        for p in self._passes_now(now):
            if not p.claimed:
                p.faces = [s.strangers[0]]
                print("[Guard] guest pass claimed by the face in frame")
            if any(best_match(e, p.faces) >= thr for e in s.strangers):
                self._guest_seen_at = now

    def _guest_pass_for(self, s: Sighting | None, now: float) -> GuestPass | None:
        thr = self.vault.tuning("face_threshold")
        for p in self._passes_now(now):
            if not p.claimed:
                # Owner said "help him" and nobody has claimed it yet. With a
                # camera frame it would have been bound in observe(); without
                # one (camera off) the owner's word is all there is.
                return p
            if s and any(best_match(e, p.faces) >= thr for e in s.strangers):
                return p
        return None

    # ── voice ──────────────────────────────────────────────────────────────
    def _voice_score(self, audio: bytes) -> tuple[float | None, float]:
        """(similarity to the owner's voice or None if not judgeable, voiced s)."""
        voices = self.vault.voices
        if not voices or not audio:
            return None, 0.0
        try:
            sample = self.voice.embed(audio)
        except Exception as e:  # noqa: BLE001 - voice is a fast path, not a gate
            print(f"[Guard] voice check skipped: {e}")
            return None, 0.0
        if sample.embedding is None:
            return None, sample.voiced_seconds
        import numpy as np
        centroid = np.mean(np.asarray(voices, dtype=np.float32), axis=0)
        return cosine(sample.embedding, centroid), sample.voiced_seconds

    # ── the decision ───────────────────────────────────────────────────────
    def authorize(self, text: str, via: str = "text", frame: bytes | None = None,
                  audio: bytes | None = None) -> Decision:
        if not self.active:
            return Decision(True, "owner", "guard_off")
        now = self.clock()
        detail: dict = {"via": via}

        # 1. voice
        vscore = None
        if via == "voice" and audio:
            vscore, voiced = self._voice_score(audio)
            detail.update(voice_score=None if vscore is None else round(vscore, 3),
                          voiced_s=round(voiced, 2))
            if vscore is not None and vscore >= self.vault.tuning("voice_threshold"):
                with self._lock:
                    self._owner_seen_at = now
                return self._owner(text, "voice", detail)

        # 2-4. camera
        s: Sighting | None = None
        if frame:
            try:
                s = self.observe(frame)
            except (RuntimeError, ValueError) as e:
                detail["camera_error"] = str(e)
        if s is None and self._last and now - self._last.at <= FRESH_S:
            s = self._last
        if s is not None:
            detail.update(faces=s.faces, face_score=round(s.owner_score, 3))
            if s.owner:
                voice_says_other = (vscore is not None
                                    and vscore < self.vault.tuning("voice_threshold"))
                if voice_says_other and s.faces >= 2:
                    return Decision(True, "guest", "owner_present", detail=detail)
                return self._owner(text, "face", detail)
            if (s.faces and s.owner_score >= CONTINUITY_THRESHOLD
                    and now - self._owner_seen_at <= LOCK_AFTER_S):
                return self._owner(text, "face_continuity", detail)
            if s.faces == 0 and now - self._owner_seen_at <= GRACE_S:
                return self._owner(text, "face_recent", detail)
        elif now - self._owner_seen_at <= GRACE_S:
            return self._owner(text, "face_recent", detail)

        # 5. PIN
        if now < self._pin_until:
            return self._owner(text, "pin", detail)

        # 6. guest pass
        with self._lock:
            p = self._guest_pass_for(s, now)
        if p:
            if p.claimed:
                self._guest_seen_at = now
            detail["guest_expires_in"] = int(p.expires_at - now)
            return Decision(True, "guest", "guest_pass", detail=detail)

        # 7. no
        if s is None:
            reason = "no_camera"
        elif s.faces == 0:
            reason = "nobody"
        else:
            reason = "stranger"
        return Decision(False, None, reason, self.deny_text(reason), detail=detail)

    def deny_text(self, reason: str) -> str:
        name = self.owner_name()
        return {
            "no_camera": (f"I can't see who's there — the camera isn't on, so I can't "
                          f"check it's {name}. Turn it on, or unlock with the PIN."),
            "nobody": f"I don't see anyone at the camera, so I'm keeping quiet.",
            "stranger": (f"I don't recognise you, and I only talk to {name}. "
                         f"If {name} tells me it's okay, I'll help."),
        }.get(reason, "I can't answer right now.")

    def _owner(self, text: str, reason: str, detail: dict) -> Decision:
        """Owner verified — but the message might be a guard command."""
        cmd = commands.parse(text)
        if not cmd:
            return Decision(True, "owner", reason, detail=detail)
        if cmd["action"] == "grant":
            msg = self.grant(cmd["minutes"])
        else:
            msg = self.revoke()
        return Decision(True, "owner", reason, msg, handled=True, detail=detail)

    # ── guest passes ───────────────────────────────────────────────────────
    def grant(self, minutes: int) -> str:
        now = self.clock()
        with self._lock:
            s = self._last if self._last and now - self._last.at <= FRESH_S else None
            faces = list(s.strangers) if s else []
            self._passes.append(GuestPass(id=uuid.uuid4().hex[:8], granted_at=now,
                                          expires_at=now + minutes * 60, faces=faces))
            if faces:
                self._guest_seen_at = now
        _reset_guest_chat()
        span = _span(minutes)
        if faces:
            who = "them" if len(faces) > 1 else "your friend"
            return f"Got it — I'll help {who} for the next {span}. Say \"stop helping him\" to end it."
        return (f"Okay — I'll help the next person who sits down for the next {span}, "
                f"and only them. Say \"stop helping him\" to end it.")

    def revoke(self) -> str:
        with self._lock:
            had = bool(self._passes_now(self.clock()))
            self._passes.clear()
            self._guest_seen_at = 0.0
        _reset_guest_chat()
        return "Done — it's just you and me again." if had else "There's no guest right now — it's just you."

    # ── PIN ────────────────────────────────────────────────────────────────
    def _check_pin(self, pin: str) -> tuple[bool, str]:
        """Verify the PIN with brute-force backoff. Opens nothing."""
        now = self.clock()
        if now < self._pin_blocked_until:
            return False, f"Too many wrong PINs — try again in {int(self._pin_blocked_until - now) + 1}s."
        if not self.vault.check_pin(pin):
            self._pin_failures += 1
            if self._pin_failures >= PIN_FREE_ATTEMPTS:
                wait = 30 * 2 ** (self._pin_failures - PIN_FREE_ATTEMPTS)
                self._pin_blocked_until = now + min(wait, 3600)
            return False, "That PIN isn't right."
        self._pin_failures = 0
        return True, ""

    def unlock_pin(self, pin: str) -> tuple[bool, str]:
        """The lock screen's PIN: a time-boxed owner session in which the
        camera isn't consulted (that's the point — it couldn't see you)."""
        ok, why = self._check_pin(pin)
        if ok:
            self._pin_until = self.clock() + PIN_SESSION_S
        return ok, why

    def unlock_voice(self, audio: bytes) -> tuple[bool, str]:
        """The lock screen's "use my voice": same timed session as the PIN.
        A plain presence bump wouldn't do — the reason to unlock by voice is
        usually that the camera can't recognise you, and it would re-lock two
        frames later. Returns (ok, "" | "short" | "mismatch")."""
        score, _ = self._voice_score(audio)
        if score is None:
            return False, "short"
        if score < self.vault.tuning("voice_threshold"):
            return False, "mismatch"
        now = self.clock()
        with self._lock:
            self._owner_seen_at = now
            self._pin_until = now + PIN_SESSION_S
        return True, ""

    def verify_owner_now(self, frame: bytes | None = None, pin: str | None = None) -> bool:
        """For sensitive actions (disable, reset, re-enroll): a fresh owner
        face in THIS frame, or the PIN. A stale sighting isn't enough."""
        # PIN as proof for ONE action — it must not also open a session, or
        # whoever sits down next inherits the owner for ten minutes.
        if pin and self._check_pin(pin)[0]:
            return True
        if frame:
            try:
                return self.observe(frame).owner
            except (RuntimeError, ValueError):
                return False
        return False

    def lock_now(self) -> None:
        with self._lock:
            self._owner_seen_at = 0.0
            self._pin_until = 0.0
            self._last = None
            self._stranger_streak = 0

    # ── reporting ──────────────────────────────────────────────────────────
    def status(self) -> dict:
        now = self.clock()
        with self._lock:
            passes = self._passes_now(now)
            last = self._last
            return {
                "active": self.active,
                "role": self.role(),
                "owner_name": self.owner_name(),
                "vault": self.vault.summary(),
                "pin_session": now < self._pin_until,
                "owner_seen_ago": (round(now - self._owner_seen_at, 1)
                                   if self._owner_seen_at else None),
                "faces_in_frame": last.faces if last else None,
                "frame_ago": round(now - self._last_frame_at, 1) if self._last_frame_at else None,
                "camera_error": self._camera_error,
                "guest": ({"claimed": passes[0].claimed,
                           "expires_in": int(max(p.expires_at for p in passes) - now)}
                          if passes else None),
                "lock_after_s": LOCK_AFTER_S,
            }


def _reset_guest_chat() -> None:
    """A new (or ended) guest starts from a blank page — never the last
    guest's conversation."""
    try:
        from core.guard import guest_lane
        guest_lane.reset()
    except Exception:  # noqa: BLE001
        pass


def _span(minutes: int) -> str:
    if minutes >= 60 and minutes % 60 == 0:
        h = minutes // 60
        return "hour" if h == 1 else f"{h} hours"
    if minutes > 60:
        return f"{minutes // 60}h {minutes % 60}m"
    return f"{minutes} minutes"
