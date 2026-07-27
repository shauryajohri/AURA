# core/quests.py
"""
Quest engine — daily commitments that AURA verifies instead of trusting.

A task is something you tick off. A quest is something you actually have to
DO, for a real amount of time, while AURA watches the screen to confirm it.
"2h Japanese" only fills up while Japanese is genuinely on screen; alt-tabbing
to YouTube stops the clock, and the quest completes itself when the time is met.

The four pieces:

    match()     screen context → which quest this is (or none)
    tick()      credit elapsed seconds, honestly
    pressure()  do the remaining quests still fit in the day?
    announce    speak only at moments that earned it

Design rules, same as core/v3_bridge:
  • Never raise into a caller — the watch loop must survive a bug in here.
  • Time is injected as `now` so the whole thing is testable without sleeping.
  • Announcements go through one injected sink; this module knows nothing
    about websockets.

Honesty rules, which are the actual point of the feature:
  • AFK time never counts. Neither does a screen that matches nothing.
  • A gap larger than MAX_CREDIT_GAP is discarded rather than credited — a
    closed laptop must not silently award an hour of "study".
  • Time that matched no quest is recorded as unallocated, not as failure.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Any, Callable

from core.quest_presets import (
    GENERIC_TERMS,
    STOPWORDS,
    guess_preset,
    is_container_app,
    is_identifying,
    is_specific,
    preset_keywords,
)
from memory import store

# ── Tuning ──────────────────────────────────────────────────────────────────
# The watch loop ticks every 30s; anything beyond this is treated as a gap
# (sleep, hibernate, AURA restarted) and thrown away rather than credited.
MAX_CREDIT_GAP = 120          # seconds
MIN_MATCH_SCORE = 4           # evidence needed to attribute time

# Evidence weights. Titles are near-definitive; body text is supporting, and
# needs repetition before it's trusted on its own.
W_ANCHOR_TITLE = 4            # a distinctive term in the app/window title
W_TERM_TITLE = 2              # an ordinary term in the title
W_ANCHOR_BODY_STRONG = 5      # distinctive term all over the screen — decisive
W_ANCHOR_BODY_SPECIFIC = 4    # a near-unique identifier, even once
W_ANCHOR_BODY_REPEATED = 3    # distinctive term appearing twice
W_ANCHOR_BODY = 2             # distinctive term appearing once — a mention
W_TERM_BODY = 1               # ordinary term somewhere in the page text
BODY_REPEAT_MIN = 2           # occurrences that make a body mention "about it"
BODY_STRONG_MIN = 3           # occurrences that make the screen ABOUT it
DAY_END_HOUR = 23             # when "the day" is assumed to end, for pressure

# Pressure bands: ratio of required time to time actually left.
RUSH_RATIO = 0.9
TIGHT_RATIO = 0.7

# Speak gates — a quest nag is worse than no quest at all.
COMPLETE_COOLDOWN = 0         # completions always speak (they're earned, once)
PRESSURE_COOLDOWN = 90 * 60   # at most once every 90 minutes
DRIFT_COOLDOWN = 45 * 60

# Minutes PAST a target at which AURA says something. Each fires once per
# quest per day, so a long session gets acknowledged a handful of times over
# hours rather than nagged at every tick.
OVERTIME_MARKS = (30, 60, 120, 180, 240)

# Hour marks for UNTIMED quests. No target to pass, so the milestone is simply
# how long you've been at it.
UNTIMED_MARKS = (60, 120, 180, 240, 300, 360)


# ── Announcement sink ───────────────────────────────────────────────────────
_sink: Callable[[dict], None] | None = None
_lock = threading.Lock()


def set_sink(fn: Callable[[dict], None] | None) -> None:
    global _sink
    _sink = fn


def _publish(payload: dict) -> None:
    payload.setdefault("ts", time.time())
    if _sink is not None:
        try:
            _sink(payload)
        except Exception:  # noqa: BLE001
            pass


# ── Natural-language quest creation ─────────────────────────────────────────
_DUR_RE = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>h(?:rs?|ours?)?|m(?:ins?|inutes?)?)\b",
    re.IGNORECASE,
)


def parse_quest(text: str) -> dict:
    """Turn "japanese 2 hrs" / "2h dsa" / "read 45 min" into a quest spec.

    shaurya's phrasing puts the duration on either side of the subject, so the
    duration is extracted wherever it sits and the remainder becomes the title.

    NO duration means an UNTIMED quest (target 0) rather than a made-up default:
    "just watch this and tell me how long I spent on it".
    """
    raw = (text or "").strip()
    minutes = 0
    for m in _DUR_RE.finditer(raw):
        val = float(m.group("num"))
        minutes += int(round(val * 60)) if m.group("unit").lower().startswith("h") else int(round(val))
    title = _DUR_RE.sub(" ", raw)
    title = re.sub(r"\b(for|of|a|an|the|every ?day|daily|quest)\b", " ", title, flags=re.IGNORECASE)
    title = re.sub(r"[^\w\s　-鿿]+", " ", title)
    title = re.sub(r"\s+", " ", title).strip().title()
    return {
        "title": title or "Quest",
        "target_minutes": minutes,      # 0 = untimed, monitored only
        "preset": guess_preset(raw),
    }


# ── Matching ────────────────────────────────────────────────────────────────
def quest_terms(quest: dict) -> tuple[list[str], set[str]]:
    """(all terms, anchor terms) for a quest, lowercased.

    Four sources: the preset pack, the user's own keywords, keywords harvested
    from a linked project folder, and the quest title itself — so "Thesis"
    matches thesis.docx with no configuration at all.

    ANCHORS are the distinctive subset. They're what makes content-only
    matching safe: a quest called "Aura Code Base" anchors on "aura", never on
    "code" or "base", so an unrelated Claude conversation can't accidentally
    satisfy it just by containing the word "code".
    """
    terms: list[str] = []
    anchors: set[str] = set()

    # Preset packs are curated and already distinctive — all anchors.
    for kw in preset_keywords(quest.get("preset", "custom")):
        terms.append(kw)
        anchors.add(kw)

    # The user's own keywords are an explicit statement of what matters.
    for kw in (quest.get("keywords") or "").split(","):
        kw = kw.strip().lower()
        if len(kw) >= 3:
            terms.append(kw)
            if kw not in GENERIC_TERMS:
                anchors.add(kw)

    # Harvested from a linked folder (cached; see project_terms).
    harvested = quest.get("project_terms")
    if harvested is None and quest.get("project_path"):
        harvested = project_terms(quest["project_path"])
    for kw in (harvested or []):
        kw = str(kw).strip().lower()
        if len(kw) >= 3:
            terms.append(kw)
            # "core", "api", "utils" are real folders but identify no project.
            if is_identifying(kw):
                anchors.add(kw)

    # The title, minus filler. This is where "aura" comes from.
    for word in re.split(r"\W+", (quest.get("title") or "").lower()):
        if len(word) >= 3 and word not in STOPWORDS:
            terms.append(word)
            if word not in GENERIC_TERMS:
                anchors.add(word)

    uniq = sorted({t for t in terms if len(t) >= 3}, key=len, reverse=True)
    return uniq, anchors


# ── Project folder → vocabulary ─────────────────────────────────────────────
_SKIP_DIRS = {
    "node_modules", ".git", "venv", ".venv", "dist", "build", "__pycache__",
    ".idea", ".vscode", "target", "vendor", ".next", "coverage", "env",
    ".ruff_cache", ".pytest_cache", "site-packages",
}
_CODE_EXT = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".rb", ".c",
    ".cpp", ".cs", ".swift", ".kt", ".vue", ".svelte", ".md",
}
_PROJECT_TERMS_MAX = 140
_project_cache: dict[str, tuple[float, list[str]]] = {}
_PROJECT_TTL = 600.0   # re-scan a folder at most every 10 minutes


def project_terms(path: str) -> list[str]:
    """Harvest a project's own vocabulary from its folder.

    This is what makes a codebase quest work everywhere without the user
    hand-writing keywords: the module and directory names of the AURA repo
    ("brain", "sanctuary", "proactive", "v3_bridge") are exactly the words
    that show up in a VS Code title bar, a GitHub tab, AND in a Claude
    conversation about the project. Harvest once, match anywhere.

    Cheap and shallow on purpose — two levels deep, names only, never file
    contents — and cached, because this runs from the watch loop.
    """
    import os
    path = (path or "").strip()
    if not path or not os.path.isdir(path):
        return []
    now = time.time()
    hit = _project_cache.get(path)
    if hit and (now - hit[0]) < _PROJECT_TTL:
        return hit[1]

    # (term -> rank). Lower rank = more identifying, and the cap is applied by
    # RANK, never alphabetically: sorting names then truncating quietly threw
    # away everything after "d", so a scan of this very repo kept "analyzer"
    # and dropped "proactive", "sanctuary" and "quests".
    ranked: dict[str, int] = {}

    def offer(term: str, rank: int):
        term = term.lower()
        if len(term) < 4 or term in GENERIC_TERMS or term in STOPWORDS or term.isdigit():
            return
        if term not in ranked or rank < ranked[term]:
            ranked[term] = rank

    try:
        base = os.path.basename(os.path.normpath(path)).lower()
        if len(base) >= 3 and base not in GENERIC_TERMS:
            ranked[base] = 0                       # the project's own name
        for root, dirs, files in os.walk(path):
            rel = os.path.relpath(root, path)
            depth = 0 if rel == "." else rel.count(os.sep) + 1
            if depth >= 2:
                dirs[:] = []                        # two levels is plenty
            dirs[:] = [d for d in dirs if d.lower() not in _SKIP_DIRS
                       and not d.startswith(".")]
            for d in dirs:
                offer(d, 1 + depth)                 # directory names identify best
            for f in files:
                stem, ext = os.path.splitext(f)
                if ext.lower() in _CODE_EXT:
                    offer(stem, 4 + depth)
    except Exception as e:  # noqa: BLE001
        print(f"[Quests] could not scan {path}: {e}")
        return []

    cleaned = [t for t, _ in sorted(ranked.items(), key=lambda kv: (kv[1], kv[0]))]
    cleaned = cleaned[:_PROJECT_TERMS_MAX]
    _project_cache[path] = (now, cleaned)
    return cleaned


def _haystack(ctx: dict[str, Any]) -> tuple[str, str]:
    """(title-ish text, body text), both lowercased.

    The app name joins the title text ONLY for non-container apps. "Anki" is
    real evidence of Japanese study; "Chrome" or "Claude" is evidence of
    nothing, so for those the name is dropped and the subject has to be proven
    by the window title or what's actually on screen.
    """
    app = str(ctx.get("app") or "")
    title = str(ctx.get("title") or ctx.get("window_title") or "")
    body = str(ctx.get("visible_text") or ctx.get("text") or "")[:6000]
    head = title if is_container_app(app) else f"{app} {title}"
    return head.lower(), body.lower()


def _hits(term: str, text: str) -> bool:
    if not text:
        return False
    # CJK has no word breaks, so those terms use a plain substring test.
    if re.search(r"[　-鿿]", term):
        return term in text
    # Boundaries are letters/digits ONLY — deliberately not \w, which counts
    # underscore and would stop "thesis" matching "thesis_draft_v4.docx".
    # Filenames and window titles are full of _ - . separators, and those are
    # word breaks to a human reading the title.
    return re.search(
        r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text
    ) is not None


def _count(term: str, text: str) -> int:
    if not text:
        return 0
    if re.search(r"[　-鿿]", term):
        return text.count(term)
    return len(re.findall(
        r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text
    ))


def score_quest(quest: dict, ctx: dict[str, Any]) -> tuple[int, bool]:
    """(score, saw_anchor) — how strongly this screen looks like this quest.

    Two numbers rather than one because they answer different questions.
    Score says "how much evidence"; saw_anchor says "was any of it actually
    specific to this quest". Both have to pass, which is what stops a generic
    word cloud from filling a quest.
    """
    head, body = _haystack(ctx)
    terms, anchors = quest_terms(quest)
    score, saw_anchor = 0, False

    for term in terms:
        is_anchor = term in anchors
        if _hits(term, head):
            score += W_ANCHOR_TITLE if is_anchor else W_TERM_TITLE
            saw_anchor = saw_anchor or is_anchor
            continue
        n = _count(term, body)
        if n:
            if is_anchor:
                # One passing mention is weak; a term threaded all through the
                # screen means the screen is genuinely ABOUT this. That
                # gradient is what lets a Claude conversation about AURA count
                # on content alone while one about pasta never does.
                if n >= BODY_STRONG_MIN:
                    score += W_ANCHOR_BODY_STRONG
                elif n >= BODY_REPEAT_MIN:
                    score += W_ANCHOR_BODY_REPEATED
                elif is_specific(term):
                    # A snake_case symbol or a long unique name. Nobody types
                    # "response_composer" by accident, so one mention is proof.
                    score += W_ANCHOR_BODY_SPECIFIC
                else:
                    score += W_ANCHOR_BODY
                saw_anchor = True
            else:
                score += W_TERM_BODY
        if score >= 12:
            break               # already certain; stop scanning
    return score, saw_anchor


def match(ctx: dict[str, Any], quests: list[dict] | None = None) -> tuple[int | None, int]:
    """Return (quest_id, score) for the best match, or (None, score).

    A quest is only credited when it clears MIN_MATCH_SCORE *and* something
    distinctive to it was on screen.
    """
    try:
        board = quests if quests is not None else store.get_quest_board()["quests"]
    except Exception:  # noqa: BLE001
        return None, 0
    best_id, best_score, top_seen = None, 0, 0
    for q in board:
        s, anchored = score_quest(q, ctx)
        top_seen = max(top_seen, s)
        # Only QUALIFYING quests compete for the win. Ranking on raw score
        # first would let a high-scoring but unanchored quest shadow a lower
        # one that genuinely matched.
        if s >= MIN_MATCH_SCORE and anchored and s > best_score:
            best_id, best_score = q["id"], s
    return best_id, best_score or top_seen


# ── Time pressure ───────────────────────────────────────────────────────────
def _minutes_left_in_day(now: float | None = None) -> int:
    import datetime
    dt = datetime.datetime.fromtimestamp(now) if now else datetime.datetime.now()
    end = dt.replace(hour=DAY_END_HOUR, minute=0, second=0, microsecond=0)
    if dt >= end:
        return 0
    return int((end - dt).total_seconds() // 60)


def pressure(board: dict | None = None, now: float | None = None) -> dict:
    """Does the remaining work still fit in the day?

    This is the "6 hours of quests and 4 hours left — rush up" calculation.
    """
    try:
        board = board or store.get_quest_board()
    except Exception:  # noqa: BLE001
        return {"status": "unknown", "required_minutes": 0, "available_minutes": 0}

    # Untimed quests are excluded on purpose: they have no target, so they
    # can't be "owed" and must never make the day look overcommitted.
    required = sum(
        q["remaining_seconds"] for q in board["quests"]
        if not q["completed"] and not q.get("untimed")
    ) // 60
    available = _minutes_left_in_day(now)

    if required == 0:
        status = "clear"
    elif available <= 0:
        status = "out_of_time"
    else:
        ratio = required / available
        if ratio > 1:
            status = "impossible"
        elif ratio >= RUSH_RATIO:
            status = "rush"
        elif ratio >= TIGHT_RATIO:
            status = "tight"
        else:
            status = "ok"

    return {
        "status": status,
        "required_minutes": required,
        "available_minutes": available,
        "deficit_minutes": max(0, required - available),
    }


_PRESSURE_LINES = {
    "impossible": "{req} of quests left and only {avail} in the day — something's got to give.",
    "rush": "{req} left across your quests, {avail} of day. Tight. Pick the important one.",
    "tight": "{req} of quests against {avail} — doable, but not if you drift.",
    "out_of_time": "Day's basically gone and {req} of quests are still open.",
}


def _fmt_minutes(m: int) -> str:
    if m < 60:
        return f"{m}m"
    h, mm = divmod(m, 60)
    return f"{h}h" if mm == 0 else f"{h}h{mm:02d}"


# ── The tracker ─────────────────────────────────────────────────────────────
class QuestTracker:
    """Accumulates verified time. One instance, driven by the watch loop."""

    def __init__(self):
        self._last_tick: float = 0.0
        self._last_quest: int | None = None
        self._spoken: dict[str, float] = {}
        self._completed_today: set[tuple[str, int]] = set()
        # (day, quest_id, mark) already acknowledged — keeps a long session
        # from re-announcing the same milestone every 30 seconds.
        self._marks_hit: set[tuple[str, int, int]] = set()

    # -- speak gate ---------------------------------------------------------
    def _may_speak(self, key: str, cooldown: int, now: float) -> bool:
        last = self._spoken.get(key, 0.0)
        if cooldown and (now - last) < cooldown:
            return False
        self._spoken[key] = now
        return True

    # -- main entry ---------------------------------------------------------
    def tick(self, ctx: dict[str, Any], afk: bool = False,
             now: float | None = None) -> str | None:
        """One sample from the watch loop. Returns a line worth saying, or None.

        Returning None is the normal case — this runs every 30 seconds all day.
        """
        now = now if now is not None else time.time()
        prev, self._last_tick = self._last_tick, now
        if not prev:
            return None                       # first sample: nothing to credit yet

        elapsed = now - prev
        if elapsed <= 0 or elapsed > MAX_CREDIT_GAP:
            # Machine slept, or AURA was restarted. Crediting this would be a
            # lie, and the whole feature rests on the numbers being true.
            self._last_quest = None
            return None
        if afk:
            self._last_quest = None
            return None

        try:
            board = store.get_quest_board()
        except Exception as e:  # noqa: BLE001
            print(f"[Quests] board unavailable: {e}")
            return None
        if not board["quests"]:
            return None

        quest_id, _score = match(ctx, board["quests"])
        secs = int(round(elapsed))

        if quest_id is None:
            self._last_quest = None
            try:
                store.add_unallocated_seconds(secs, day=board["day"])
            except Exception:  # noqa: BLE001
                pass
            return self._pressure_nudge(now)

        self._last_quest = quest_id
        quest = next((q for q in board["quests"] if q["id"] == quest_id), None)
        if quest is None:
            return None

        try:
            total = store.add_quest_seconds(quest_id, secs, day=board["day"])
        except Exception as e:  # noqa: BLE001
            print(f"[Quests] could not credit time: {e}")
            return None

        target_s = quest["target_seconds"]
        _publish({
            "kind": "progress", "quest_id": quest_id, "title": quest["title"],
            "seconds": total, "target_seconds": target_s,
            "untimed": bool(quest.get("untimed")),
            "percent": min(100, round(total / target_s * 100)) if target_s > 0 else 0,
            "overtime_seconds": max(0, total - target_s) if target_s > 0 else 0,
            "day": board["day"],
        })

        # Untimed quests never complete — they just accumulate, and AURA
        # acknowledges the hour marks so the effort is still noticed.
        if quest.get("untimed"):
            return self._milestone_line(quest, board, total, now) or self._pressure_nudge(now)

        # Auto-complete: the quest finishes itself, exactly as asked.
        key = (board["day"], quest_id)
        if total >= quest["target_seconds"] and not quest["completed"] and key not in self._completed_today:
            self._completed_today.add(key)
            try:
                store.complete_quest(quest_id, day=board["day"])
            except Exception:  # noqa: BLE001
                pass
            line = self._completion_line(quest, board)
            _publish({"kind": "complete", "quest_id": quest_id,
                      "title": quest["title"], "text": line, "day": board["day"]})
            if self._may_speak(f"complete:{quest_id}", COMPLETE_COOLDOWN, now):
                return line
            return None

        # Already done but still going — the clock keeps running and the extra
        # gets acknowledged. Doing 3h on a 2h quest should be seen, not ignored
        # because a box was already ticked.
        if total > quest["target_seconds"]:
            over = self._milestone_line(quest, board, total, now)
            if over:
                return over

        return self._pressure_nudge(now)

    # -- lines --------------------------------------------------------------
    def _completion_line(self, quest: dict, board: dict) -> str:
        """State what got done, how long it took, and what's left.

        Completing a target is the natural moment to stop, so it offers the
        break rather than immediately pointing at the next thing — the point
        of the board is to finish the day well, not to keep grinding.
        """
        # Untimed quests are excluded from "what's left" — they're never owed.
        remaining = [q for q in board["quests"]
                     if not q["completed"] and not q.get("untimed")
                     and q["id"] != quest["id"]]
        span = _fmt_minutes(quest["target_minutes"])
        if not remaining:
            return (f"{quest['title']} done — {span}, and that's the whole board "
                    "clear. Go take a break, you've earned it.")
        nxt = min(remaining, key=lambda q: q["remaining_seconds"])
        return (f"{quest['title']} done — {span} of it. "
                f"{len(remaining)} left, {nxt['title']} is the shortest at "
                f"{_fmt_minutes(nxt['remaining_seconds'] // 60)}. "
                "Take a break first if you want it.")

    def _milestone_line(self, quest: dict, board: dict, total: int,
                        now: float) -> str | None:
        """Acknowledge sustained time — overtime on a target, or hours on an
        untimed quest. Each mark fires once per quest per day."""
        untimed = bool(quest.get("untimed"))
        if untimed:
            minutes_in = total // 60
            marks = UNTIMED_MARKS
        else:
            minutes_in = max(0, (total - quest["target_seconds"]) // 60)
            marks = OVERTIME_MARKS

        hit = None
        for mark in marks:
            if minutes_in >= mark:
                hit = mark
        if hit is None:
            return None

        key = (board["day"], quest["id"], hit)
        if key in self._marks_hit:
            return None
        self._marks_hit.add(key)

        if untimed:
            line = (f"{quest['title']} — {_fmt_minutes(hit)} in today. "
                    "No target on it, just telling you where the time went. "
                    "Good point to stretch if you want one.")
        else:
            line = (f"That's {_fmt_minutes(total // 60)} on {quest['title']} — "
                    f"{_fmt_minutes(hit)} past the {_fmt_minutes(quest['target_minutes'])} "
                    "you set. Keep going if you're in it, but a break's fair here.")

        _publish({
            "kind": "milestone", "quest_id": quest["id"], "title": quest["title"],
            "text": line, "minutes": hit, "total_seconds": total,
            "untimed": untimed, "day": board["day"],
        })
        if self._may_speak(f"mark:{quest['id']}:{hit}", 0, now):
            return line
        return None

    def _pressure_nudge(self, now: float) -> str | None:
        p = pressure(now=now)
        if p["status"] not in _PRESSURE_LINES:
            return None
        if not self._may_speak(f"pressure:{p['status']}", PRESSURE_COOLDOWN, now):
            return None
        line = _PRESSURE_LINES[p["status"]].format(
            req=_fmt_minutes(p["required_minutes"]),
            avail=_fmt_minutes(p["available_minutes"]),
        )
        _publish({"kind": "pressure", "text": line, **p})
        return line

    # -- snapshot for the UI ------------------------------------------------
    def status(self) -> dict:
        try:
            board = store.get_quest_board()
        except Exception:  # noqa: BLE001
            return {"quests": [], "pressure": {"status": "unknown"}}
        return {
            **board,
            "pressure": pressure(board),
            "active_quest_id": self._last_quest,
        }


_TRACKER: QuestTracker | None = None


def get_tracker() -> QuestTracker:
    global _TRACKER
    if _TRACKER is None:
        _TRACKER = QuestTracker()
    return _TRACKER


# ── Convenience wrappers (REST + brain use these) ───────────────────────────
def board() -> dict:
    return get_tracker().status()


def create_from_text(text: str) -> dict:
    """'japanese 2 hrs' → a real quest row."""
    spec = parse_quest(text)
    from core.quest_presets import PRESETS
    color = PRESETS.get(spec["preset"], PRESETS["custom"])["color"]
    qid = store.add_quest(
        spec["title"], spec["target_minutes"], "", spec["preset"], color
    )
    return {"id": qid, **spec, "color": color}


def summary_line() -> str:
    """One sentence for chat: where the board stands right now."""
    try:
        b = store.get_quest_board()
    except Exception:  # noqa: BLE001
        return "Quest board isn't reachable right now."
    quests = b["quests"]
    if not quests:
        return "No quests set up yet."

    timed = [q for q in quests if not q.get("untimed")]
    untimed = [q for q in quests if q.get("untimed") and q["seconds"] > 0]

    # A board of nothing but untimed quests has no completion to report —
    # just where the time went.
    if not timed:
        if not untimed:
            return "Nothing tracked yet today."
        bits = [f"{q['title']} {_fmt_minutes(q['seconds'] // 60)}" for q in untimed]
        return "Tracked today: " + ", ".join(bits) + "."

    done = [q for q in timed if q["completed"]]
    parts = []
    if len(done) == len(timed):
        parts.append("Quest done today" if len(timed) == 1
                     else f"All {len(timed)} quests done today")
    else:
        parts.append(f"{len(done)}/{len(timed)} quests done")
        open_q = [q for q in timed if not q["completed"]]
        if open_q:
            nxt = min(open_q, key=lambda q: q["remaining_seconds"])
            parts.append(f"closest is {nxt['title']} with "
                         f"{_fmt_minutes(nxt['remaining_seconds'] // 60)} to go")
        p = pressure(b)
        if p["status"] in {"rush", "impossible", "out_of_time"}:
            parts.append(f"and only {_fmt_minutes(p['available_minutes'])} of day left")

    over = [q for q in timed if q.get("overtime_seconds", 0) >= 600]
    if over:
        q = max(over, key=lambda x: x["overtime_seconds"])
        parts.append(f"{_fmt_minutes(q['overtime_seconds'] // 60)} extra on {q['title']}")
    if untimed:
        bits = [f"{q['title']} {_fmt_minutes(q['seconds'] // 60)}" for q in untimed]
        parts.append("also tracked " + ", ".join(bits))
    return ", ".join(parts) + "."
