# core/engagement.py
"""
Engagement — is shaurya actually WORKING right now, or just around?

This exists because AURA kept saying "you've been quiet, what's going on over
there?" while he was thirty minutes deep in code. The AttentionEngine measures
silence toward AURA and treats it as absence, so a focused work session and
ignoring her look identical to it. They are not remotely the same thing, and
interrupting the first one is the worst thing a companion can do.

So: one place that answers "are they working", consulted by every module that
wants to interrupt.

The verdict combines signals AURA already collects, strongest first:

    quest match     the screen matches a quest they committed to  → working
    developer state V3 says flow / debugging / momentum           → working
    code editor     a real IDE is in front                        → working
    leisure         YouTube, Netflix, Spotify, social             → NOT working
    productive app  docs, design, terminal, notes                 → working
    otherwise                                                     → idle

Leisure is checked BEFORE the generic app list on purpose: proactive's
WORK_APPS contains "chrome", so a browser playing anime counted as work.

It also tracks the SHAPE of a session — when a work stretch starts, how long
it runs, and when it ends — so AURA can say "you were in the quest tracker for
40 minutes, did you get it sorted?" instead of pretending she saw nothing.
"""

from __future__ import annotations

import threading
import time
from typing import Any

# How long a non-work sample streak before we call the work stretch over.
# One glance at a browser tab shouldn't end a coding session.
STRETCH_BREAK_SECONDS = 5 * 60

# Stretches shorter than this aren't worth mentioning afterwards.
MIN_DEBRIEF_SECONDS = 8 * 60

# A debrief goes stale — nobody wants to be asked about this morning at 9pm.
DEBRIEF_TTL = 45 * 60

# Screens that are definitively NOT work, whatever app is hosting them.
LEISURE_MARKERS = (
    "youtube", "netflix", "prime video", "hotstar", "disney+", "crunchyroll",
    "spotify", "soundcloud", "twitch", "instagram", "facebook", "reddit",
    "tiktok", "snapchat", "whatsapp", "telegram", "discord", "pinterest",
    "9gag", "imgur", "steam", "epic games", "valorant", "minecraft",
    "episode", "season ", "official trailer", "music video", "full movie",
    "highlights", "funny", "meme",
)

# Apps that mean real work even without a quest match.
PRODUCTIVE_APPS = (
    "visual studio code", "vs code", "vscode", "cursor", "windsurf", "zed",
    "pycharm", "intellij", "webstorm", "clion", "android studio", "xcode",
    "sublime", "neovim", "vim", "emacs", "terminal", "powershell", "cmd",
    "wsl", "iterm", "warp", "docker", "postman", "insomnia",
    "figma", "blender", "photoshop", "illustrator",
    "word", "excel", "powerpoint", "notion", "obsidian", "logseq",
    "anki", "wanikani",
)

CODE_EDITORS = (
    "visual studio code", "vs code", "vscode", "cursor", "windsurf", "zed",
    "pycharm", "intellij", "webstorm", "clion", "sublime", "neovim", "vim",
)

# Work that lives in a browser tab. Checked only after LEISURE_MARKERS.
WORK_SITES = (
    "github", "gitlab", "stack overflow", "stackoverflow", "leetcode",
    "localhost", "127.0.0.1", "docs.", "documentation", "developer.",
    "claude.ai", "chatgpt", "chat.openai", "gemini.google", "perplexity",
    "jira", "linear.app", "notion.so", "figma.com", "colab", "kaggle",
    "npmjs", "pypi", "readthedocs", "mdn", "w3schools", "geeksforgeeks",
)


def _text_of(ctx: dict[str, Any]) -> str:
    return " ".join(str(ctx.get(k) or "") for k in
                    ("app", "title", "window_title", "visible_text"))[:4000].lower()


def _app_of(ctx: dict[str, Any]) -> str:
    return str(ctx.get("app") or "").lower()


def classify(ctx: dict[str, Any]) -> dict[str, Any]:
    """One screen sample → {working, kind, reason, quest_id, quest_title}.

    `kind` is the useful detail: 'quest' / 'coding' / 'productive' /
    'leisure' / 'unknown'. Callers that just want a yes/no read `working`.
    """
    app = _app_of(ctx)
    blob = _text_of(ctx)
    out: dict[str, Any] = {
        "working": False, "kind": "unknown", "reason": "",
        "quest_id": None, "quest_title": "",
    }
    if not blob.strip():
        return out

    # 1. A quest match is the strongest possible signal — they told us this
    #    is what they'd be doing today, and it's on screen.
    try:
        from core import quests
        # Every kind counts here: working toward a screenshot-verified or
        # manual quest is still working, even though no clock is running.
        qid, _score = quests.match(ctx, time_only=False)
        if qid is not None:
            board = quests.store.get_quest_board()["quests"]
            q = next((x for x in board if x["id"] == qid), None)
            out.update(working=True, kind="quest", quest_id=qid,
                       quest_title=(q or {}).get("title", ""),
                       reason=f"working on quest: {(q or {}).get('title', '')}")
            return out
    except Exception:  # noqa: BLE001
        pass

    # 2. Leisure BEFORE the generic app list. proactive.WORK_APPS contains
    #    "chrome", so without this a browser playing an episode read as work.
    if any(m in blob for m in LEISURE_MARKERS):
        out.update(working=False, kind="leisure", reason="leisure content on screen")
        return out

    # 3. A real editor in front.
    if any(e in app for e in CODE_EDITORS):
        out.update(working=True, kind="coding", reason="code editor in focus")
        return out

    # 4. What the developer-state engine thinks of the session so far.
    try:
        from core import v3_bridge
        state = (v3_bridge.session() or {}).get("state", "")
        if state in {"flow", "long_flow", "debugging", "momentum"}:
            out.update(working=True, kind="coding", reason=f"developer state: {state}")
            return out
    except Exception:  # noqa: BLE001
        pass

    # 5. Productive desktop apps, and work that lives in a browser tab.
    if any(a in app for a in PRODUCTIVE_APPS):
        out.update(working=True, kind="productive", reason=f"{app} in focus")
        return out
    if any(s in blob for s in WORK_SITES):
        out.update(working=True, kind="productive", reason="work site on screen")
        return out

    return out


class EngagementTracker:
    """Remembers the shape of the current and previous work stretch."""

    def __init__(self):
        self._lock = threading.Lock()
        self._working = False
        self._kind = "unknown"
        self._reason = ""
        self._quest_title = ""
        self._started: float = 0.0
        self._last_work_seen: float = 0.0
        self._last_sample: float = 0.0
        # The most recently FINISHED stretch, waiting to be mentioned.
        self._debrief: dict[str, Any] | None = None

    # -- fed by the watch loop ---------------------------------------------
    def observe(self, ctx: dict[str, Any], afk: bool = False,
                now: float | None = None) -> dict[str, Any]:
        now = now if now is not None else time.time()
        verdict = {"working": False, "kind": "afk", "reason": "away",
                   "quest_id": None, "quest_title": ""} if afk else classify(ctx)

        with self._lock:
            self._last_sample = now
            if verdict["working"]:
                if not self._working:
                    self._working = True
                    self._started = now
                self._kind = verdict["kind"]
                self._reason = verdict["reason"]
                if verdict.get("quest_title"):
                    self._quest_title = verdict["quest_title"]
                self._last_work_seen = now
            elif self._working and (now - self._last_work_seen) >= STRETCH_BREAK_SECONDS:
                # Long enough away from work to call the stretch finished.
                self._close_stretch(now)
        return verdict

    def _close_stretch(self, now: float) -> None:
        duration = max(0.0, self._last_work_seen - self._started)
        if duration >= MIN_DEBRIEF_SECONDS:
            self._debrief = {
                "seconds": duration,
                "kind": self._kind,
                "quest_title": self._quest_title,
                "ended_at": self._last_work_seen,
            }
        self._working = False
        self._kind = "unknown"
        self._reason = ""
        self._quest_title = ""
        self._started = 0.0

    # -- read by everything that wants to interrupt ------------------------
    def is_working(self, now: float | None = None) -> bool:
        """True while a work stretch is open.

        Grace period included: momentarily alt-tabbing to a browser does not
        instantly make it "safe" to interrupt, or AURA would jump in during
        every glance away.
        """
        now = now if now is not None else time.time()
        with self._lock:
            if not self._working:
                return False
            return (now - self._last_work_seen) < STRETCH_BREAK_SECONDS

    def state(self, now: float | None = None) -> dict[str, Any]:
        now = now if now is not None else time.time()
        with self._lock:
            return {
                "working": self._working,
                "kind": self._kind,
                "reason": self._reason,
                "quest_title": self._quest_title,
                "minutes": round((now - self._started) / 60.0, 1) if self._working else 0.0,
            }

    # -- the debrief -------------------------------------------------------
    def take_debrief(self, now: float | None = None) -> dict[str, Any] | None:
        """Pop the last finished work stretch, if it's still worth mentioning.

        Called when the user speaks to AURA. Consuming it here is deliberate:
        the session gets commented on ONCE, not every message afterwards.
        """
        now = now if now is not None else time.time()
        with self._lock:
            # Speaking to AURA while still "working" also ends the stretch —
            # turning to her IS the end of the session.
            if self._working:
                self._last_work_seen = min(self._last_work_seen, now)
                self._close_stretch(now)
            d = self._debrief
            if not d:
                return None
            if (now - d["ended_at"]) > DEBRIEF_TTL:
                self._debrief = None
                return None
            self._debrief = None
            return d


_TRACKER: EngagementTracker | None = None


def get_tracker() -> EngagementTracker:
    global _TRACKER
    if _TRACKER is None:
        _TRACKER = EngagementTracker()
    return _TRACKER


# ── Convenience ─────────────────────────────────────────────────────────────
def is_working(now: float | None = None) -> bool:
    """The one-line gate every interrupting module should call."""
    try:
        return get_tracker().is_working(now)
    except Exception:  # noqa: BLE001
        return False    # never let a bug here cause SILENCE forever


def describe_minutes(seconds: float) -> str:
    m = int(seconds // 60)
    if m < 60:
        return f"{m} minutes"
    h, mm = divmod(m, 60)
    if mm == 0:
        return f"{h} hour" if h == 1 else f"{h} hours"
    return f"{h}h{mm:02d}"


def debrief_hint(now: float | None = None) -> str | None:
    """A prompt fragment describing the work stretch that just ended.

    Returned as CONTEXT for the model rather than a canned line, so the
    question AURA asks fits the conversation instead of sounding like a form.
    """
    d = get_tracker().take_debrief(now)
    if not d:
        return None
    span = describe_minutes(d["seconds"])
    what = d.get("quest_title") or {
        "coding": "code", "productive": "focused work", "quest": "their quest",
    }.get(d.get("kind", ""), "something")
    return (
        f"(They just finished a stretch of work — about {span} on {what} — and "
        "have now come back to you. Acknowledge it naturally in ONE sentence: "
        "say what you saw and how long, then ask a single specific question "
        "about how it went. Don't list, don't congratulate excessively.)"
    )
