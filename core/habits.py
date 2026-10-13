"""
core/habits.py
--------------
What AURA learns about how you use your computer: which apps and tools, for
how long, and at what time of day — so she can help like someone who knows
your routine, without you having to explain it.

How it works:
  · A background thread reads the FOREGROUND app every SAMPLE_SECONDS. It reads
    the process name and window title only — no screenshots, no OCR — so it's
    cheap enough to run all day.
  · Time is credited per (day, hour, app) and flushed to memory/store.py about
    once a minute.
  · AFK time, sleep/suspend gaps and AURA's own window are never credited.

Privacy:
  · Only the app name is stored — or, for browsers, a WELL-KNOWN site name
    (YouTube, GitHub, Gmail…). Raw window titles never touch the disk, because
    they can carry email subjects, document names and chat previews.
  · Settings → Privacy: `habits.enabled` pauses everything, `habits.ignore`
    lists apps that are never tracked, and "forget" wipes the history.

The chat reads it through prompt_block(): one line on ordinary turns, the full
picture when they ask about their habits or time.
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
from collections import defaultdict
from typing import Any, Callable

SAMPLE_SECONDS = 5
FLUSH_SECONDS = 60
# A gap longer than this between samples means the machine slept or AURA was
# paused — crediting it would invent hours nobody spent.
MAX_GAP_SECONDS = SAMPLE_SECONDS * 4
AFK_SECONDS = 180
SETTINGS_TTL = 30.0
PROMPT_TTL = 120.0
SUMMARY_DAYS = 7
MIN_TOP_SECONDS = 10 * 60   # under 10 minutes a week isn't a habit
MAX_LABEL_CHARS = 40

# ── naming: process / title → a label worth remembering ─────────────────────
_FRIENDLY_EXE = {
    "code.exe": "VS Code", "cursor.exe": "Cursor", "pycharm64.exe": "PyCharm",
    "idea64.exe": "IntelliJ IDEA", "studio64.exe": "Android Studio",
    "devenv.exe": "Visual Studio", "sublime_text.exe": "Sublime Text",
    "windowsterminal.exe": "Terminal", "cmd.exe": "Command Prompt",
    "powershell.exe": "PowerShell", "pwsh.exe": "PowerShell",
    "excel.exe": "Excel", "winword.exe": "Word", "powerpnt.exe": "PowerPoint",
    "onenote.exe": "OneNote", "outlook.exe": "Outlook", "olk.exe": "Outlook",
    "acrobat.exe": "Acrobat", "acrord32.exe": "Acrobat",
    "explorer.exe": "File Explorer", "notepad.exe": "Notepad",
    "discord.exe": "Discord", "slack.exe": "Slack", "teams.exe": "Teams",
    "ms-teams.exe": "Teams", "zoom.exe": "Zoom", "whatsapp.exe": "WhatsApp",
    "telegram.exe": "Telegram", "spotify.exe": "Spotify", "vlc.exe": "VLC",
    "steam.exe": "Steam", "figma.exe": "Figma", "notion.exe": "Notion",
    "obsidian.exe": "Obsidian", "blender.exe": "Blender",
    "photoshop.exe": "Photoshop", "obs64.exe": "OBS",
}
_BROWSER_EXE = {
    "chrome.exe": "Chrome", "msedge.exe": "Edge", "firefox.exe": "Firefox",
    "brave.exe": "Brave", "opera.exe": "Opera", "arc.exe": "Arc",
}
# Title suffix → label, for when there's no process name (non-Windows, UWP).
_FRIENDLY_TITLE = {
    "visual studio code": "VS Code", "google chrome": "Chrome",
    "microsoft edge": "Edge", "microsoft​ edge": "Edge",
    "mozilla firefox": "Firefox", "brave": "Brave",
}
_BROWSER_TITLE = {"Chrome", "Edge", "Firefox", "Brave", "Opera", "Arc"}
# Never credited: AURA herself, the lock screen, shell overlays.
_IGNORE_EXE = {
    "lockapp.exe", "searchhost.exe", "searchapp.exe", "shellexperiencehost.exe",
    "startmenuexperiencehost.exe", "textinputhost.exe", "aura.exe",
}
# A browser tab only becomes a label when it's one of these — matched against
# a whole title segment, so an arbitrary page title is never stored.
_KNOWN_SITES = {
    "youtube": "YouTube", "github": "GitHub", "gmail": "Gmail",
    "chatgpt": "ChatGPT", "claude": "Claude", "leetcode": "LeetCode",
    "netflix": "Netflix", "prime video": "Prime Video", "instagram": "Instagram",
    "reddit": "Reddit", "twitter": "X", "linkedin": "LinkedIn",
    "stack overflow": "Stack Overflow", "google docs": "Google Docs",
    "google sheets": "Google Sheets", "google slides": "Google Slides",
    "google drive": "Google Drive", "google calendar": "Google Calendar",
    "notion": "Notion", "figma": "Figma", "whatsapp": "WhatsApp",
    "discord": "Discord", "spotify": "Spotify", "twitch": "Twitch",
    "coursera": "Coursera", "udemy": "Udemy", "codeforces": "Codeforces",
    "amazon": "Amazon", "outlook": "Outlook", "canva": "Canva",
}
_SEG_RE = re.compile(r"\s+[-–—|]\s+")
_COUNT_PREFIX_RE = re.compile(r"^\(\d+\+?\)\s*")


def _segments(title: str) -> list[str]:
    return [s.strip() for s in _SEG_RE.split(title or "") if s.strip()]


def _site(title: str) -> str | None:
    for seg in _segments(title):
        key = _COUNT_PREFIX_RE.sub("", seg).strip().lower()
        if key in _KNOWN_SITES:
            return _KNOWN_SITES[key]
    return None


def label_for(exe: str, title: str) -> str | None:
    """A short, privacy-safe name for what's in front, or None to skip it."""
    title = (title or "").strip()
    exe = (exe or "").strip().lower()
    if title.lower() == "aura":            # AURA's own window (frontend <title>)
        return None
    if exe in _IGNORE_EXE:
        return None
    if exe in _BROWSER_EXE:
        return _site(title) or _BROWSER_EXE[exe]
    if exe in _FRIENDLY_EXE:
        return _FRIENDLY_EXE[exe]
    if exe and exe != "applicationframehost.exe":
        stem = os.path.splitext(exe)[0]
        return stem[:1].upper() + stem[1:MAX_LABEL_CHARS] if stem else None
    # No usable process name: the app is usually the last title segment.
    segs = _segments(title)
    if not segs:
        return None
    app = segs[-1]
    app = _FRIENDLY_TITLE.get(app.lower(), app)
    if app in _BROWSER_TITLE:
        return _site(" - ".join(segs[:-1])) or app
    if len(segs) == 1 and len(app) > MAX_LABEL_CHARS:
        return None                        # a bare long title is content, not an app
    return app[:MAX_LABEL_CHARS]


# ── reading the foreground window ───────────────────────────────────────────
def _foreground_windows() -> tuple[str, str]:
    """(exe name, title) via Win32 — no extra dependencies."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "", ""
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    exe = ""
    handle = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
    if handle:
        try:
            size = wintypes.DWORD(1024)
            path = ctypes.create_unicode_buffer(1024)
            if kernel32.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                exe = os.path.basename(path.value)
        finally:
            kernel32.CloseHandle(handle)
    return exe, buf.value


def foreground() -> tuple[str, str]:
    """(exe, title) of the focused window; ("", "") when it can't be read."""
    try:
        if sys.platform == "win32":
            return _foreground_windows()
        from modules.screen_reader import get_active_window
        title = get_active_window()
        return "", ("" if title == "unknown" else title)
    except Exception:  # noqa: BLE001
        return "", ""


def _idle_seconds() -> float:
    try:
        from modules.proactive import _idle_seconds as idle
        return float(idle())
    except Exception:  # noqa: BLE001 — no idle signal means assume present
        return 0.0


def _settings() -> dict[str, Any]:
    try:
        from memory import store
        s = store.get_settings()
    except Exception:  # noqa: BLE001
        s = {}
    ignore = s.get("habits.ignore") or []
    return {
        "enabled": s.get("habits.enabled", True) is not False,
        "ignore": {str(a).strip().lower() for a in ignore if str(a).strip()}
        if isinstance(ignore, list) else set(),
    }


# ── the tracker ─────────────────────────────────────────────────────────────
class HabitTracker:
    """Samples the foreground app and credits the time between samples."""

    def __init__(
        self,
        read: Callable[[], tuple[str, str]] = foreground,
        idle: Callable[[], float] = _idle_seconds,
        settings: Callable[[], dict[str, Any]] = _settings,
        clock: Callable[[], float] = time.time,
    ):
        self._read, self._idle, self._settings_fn, self._clock = read, idle, settings, clock
        self._lock = threading.Lock()
        self._pending: dict[tuple[str, int, str], float] = defaultdict(float)
        self._last_ts = 0.0
        self._last_label: str | None = None
        self._stretch_label: str | None = None
        self._stretch_start = 0.0
        self._last_flush = 0.0
        self._settings_cache: tuple[float, dict[str, Any]] = (0.0, {})
        self._thread: threading.Thread | None = None

    def settings(self, now: float) -> dict[str, Any]:
        ts, value = self._settings_cache
        if not value or now - ts > SETTINGS_TTL:
            value = self._settings_fn()
            self._settings_cache = (now, value)
        return value

    def refresh_settings(self) -> None:
        self._settings_cache = (0.0, {})

    def _reset(self, now: float) -> None:
        self._last_label = None
        self._stretch_label = None
        self._last_ts = now

    def sample(self, now: float | None = None) -> str | None:
        """Take one sample; returns the label now in front (or None)."""
        now = self._clock() if now is None else now
        cfg = self.settings(now)
        with self._lock:
            if not cfg.get("enabled", True):
                self._pending.clear()   # paused means nothing is kept, not just not saved
                self._reset(now)
                return None
            prev_ts, prev_label = self._last_ts, self._last_label
            elapsed = now - prev_ts if prev_ts else 0.0

            if self._idle() >= AFK_SECONDS:
                self._reset(now)
                return None
            label = label_for(*self._read())
            if label and label.lower() in cfg.get("ignore", set()):
                label = None

            if prev_label and 0 < elapsed <= MAX_GAP_SECONDS:
                t = time.localtime(prev_ts)
                key = (time.strftime("%Y-%m-%d", t), t.tm_hour, prev_label)
                self._pending[key] += elapsed
            elif elapsed > MAX_GAP_SECONDS:
                self._stretch_label = None   # slept: the current stretch is over

            if label != self._stretch_label:
                self._stretch_label, self._stretch_start = label, now
            self._last_ts, self._last_label = now, label
            return label

    def current(self, now: float | None = None) -> dict[str, Any] | None:
        """What's in front right now and for how long, e.g. Excel for 40 min."""
        now = self._clock() if now is None else now
        with self._lock:
            if not self._stretch_label or not self._last_ts or now - self._last_ts > MAX_GAP_SECONDS:
                return None
            return {"app": self._stretch_label, "seconds": int(now - self._stretch_start)}

    def pending_rows(self) -> list[tuple[str, int, str, int]]:
        with self._lock:
            return [(d, h, a, int(s)) for (d, h, a), s in self._pending.items() if int(s) > 0]

    def flush(self, now: float | None = None) -> int:
        """Write accumulated whole seconds to the store. Returns rows written."""
        now = self._clock() if now is None else now
        with self._lock:
            rows, keep = [], defaultdict(float)
            for key, secs in self._pending.items():
                whole = int(secs)
                if whole > 0:
                    rows.append((*key, whole))
                if secs - whole > 0:
                    keep[key] = secs - whole   # carry fractions instead of dropping them
            self._pending = keep
            self._last_flush = now
        if rows:
            try:
                from memory import store
                store.add_habit_seconds(rows)
            except Exception as e:  # noqa: BLE001 — put it back, try next flush
                print(f"[AURA Habits] flush failed: {e}")
                with self._lock:
                    for d, h, a, secs in rows:
                        self._pending[(d, h, a)] += secs
                return 0
        return len(rows)

    def forget(self, app: str | None = None) -> None:
        """Drop unsaved time too, so 'forget' can't be undone by the next flush."""
        with self._lock:
            if app:
                for key in [k for k in self._pending if k[2] == app]:
                    del self._pending[key]
                if self._stretch_label == app:
                    self._stretch_label = None
            else:
                self._pending.clear()
                self._stretch_label = None

    def _run(self) -> None:
        print("[AURA Habits] tracker started")
        while True:
            try:
                now = self._clock()
                self.sample(now)
                if now - self._last_flush >= FLUSH_SECONDS:
                    self.flush(now)
            except Exception as e:  # noqa: BLE001 — never let the loop die
                print(f"[AURA Habits] sample skipped: {e}")
            time.sleep(SAMPLE_SECONDS)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._last_flush = self._clock()
        self._thread = threading.Thread(target=self._run, name="aura-habits", daemon=True)
        self._thread.start()


_tracker: HabitTracker | None = None


def get_tracker() -> HabitTracker:
    global _tracker
    if _tracker is None:
        _tracker = HabitTracker()
    return _tracker


def start() -> None:
    get_tracker().start()


def forget(app: str | None = None) -> int:
    """Wipe stored habits (all, or one app) and anything not yet saved."""
    get_tracker().forget(app)
    _prompt_cache["ts"] = 0.0
    from memory import store
    return store.clear_habits(app)


# ── what it adds up to ──────────────────────────────────────────────────────
def _day(offset: int, now: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(now - offset * 86400))


def _part_of_day(hours: list[int]) -> str:
    """'late night' / 'mornings' … from the hours an app is mostly used."""
    if not hours:
        return ""
    names = {"late night": range(0, 5), "early morning": range(5, 8),
             "mornings": range(8, 12), "afternoons": range(12, 17),
             "evenings": range(17, 21), "nights": range(21, 24)}
    votes: dict[str, int] = defaultdict(int)
    for h in hours:
        for name, span in names.items():
            if h in span:
                votes[name] += 1
    return max(votes, key=votes.get)


def summary(days: int = SUMMARY_DAYS, now: float | None = None,
            rows: list | None = None) -> dict[str, Any]:
    """Habits over the last `days` days, ready for the UI and the prompt.

    `rows` lets tests pass usage directly; otherwise stored + unsaved time.
    """
    now = time.time() if now is None else now
    today = _day(0, now)
    since = _day(days - 1, now)
    if rows is None:
        try:
            from memory import store
            rows = list(store.get_habit_usage(since))
        except Exception:  # noqa: BLE001
            rows = []
        rows += get_tracker().pending_rows()
    rows = [r for r in rows if r[0] >= since]

    per_app: dict[str, int] = defaultdict(int)
    per_app_days: dict[str, set] = defaultdict(set)
    per_app_hours: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    hours = [0] * 24
    today_apps: dict[str, int] = defaultdict(int)
    for day, hour, app, secs in rows:
        per_app[app] += secs
        per_app_days[app].add(day)
        per_app_hours[app][int(hour)] += secs
        hours[int(hour)] += secs
        if day == today:
            today_apps[app] += secs

    top = []
    for app, total in sorted(per_app.items(), key=lambda kv: -kv[1]):
        if total < MIN_TOP_SECONDS:
            continue
        by_hour = per_app_hours[app]
        # the hours that hold most of the use, in clock order
        peak = sorted(sorted(by_hour, key=lambda h: -by_hour[h])[:3])
        active = len(per_app_days[app])
        top.append({
            "app": app,
            "seconds": total,
            "days_used": active,
            "avg_per_day": total // max(1, active),
            "peak_hours": peak,
            "part_of_day": _part_of_day(peak),
        })
        if len(top) >= 8:
            break

    return {
        "days": days,
        "tracked_days": len({r[0] for r in rows}),
        "today": [{"app": a, "seconds": s}
                  for a, s in sorted(today_apps.items(), key=lambda kv: -kv[1])],
        "top": top,
        "hours": hours,
        "current": get_tracker().current(now),
    }


def _dur(secs: int) -> str:
    m = int(secs) // 60
    if m < 60:
        return f"{max(m, 1)}m"
    h, m = divmod(m, 60)
    return f"{h}h {m}m" if m else f"{h}h"


_HABIT_Q = re.compile(
    r"(?i)\b("
    r"my (?:habits?|routine|schedule|day|screen ?time|usage)|"
    r"screen ?time|how (?:much|long) (?:time )?(?:did|have|do) i (?:spend|spent|use|been)|"
    r"what (?:do|did) i (?:usually|mostly|normally|always)|"
    r"what (?:apps?|tools?|sites?) (?:do|did) i|"
    r"(?:most|least) used|time (?:on|in) (?:\w+ ){0,2}(?:today|this week)|"
    r"usual (?:setup|apps?|tools?)|wasting time|productive today"
    r")"
)


def is_habit_question(query: str) -> bool:
    return bool(query and _HABIT_Q.search(query))


_prompt_cache: dict[str, Any] = {"ts": 0.0, "full": "", "short": ""}


def _blocks(now: float) -> tuple[str, str]:
    s = summary(now=now)
    cur = s.get("current")
    right_now = (f"Right now: {cur['app']} for {_dur(cur['seconds'])}"
                 if cur and cur["seconds"] >= 60 else "")
    if not s["top"] and not s["today"]:
        return "", ""
    top_bits = []
    for t in s["top"][:4]:
        bit = f"{t['app']} ~{_dur(t['avg_per_day'])}/day"
        if t["part_of_day"]:
            bit += f", mostly {t['part_of_day']}"
        top_bits.append(bit)
    today = ", ".join(f"{t['app']} {_dur(t['seconds'])}" for t in s["today"][:4])

    head = ("HOW THEY USE THEIR COMPUTER (what you've noticed yourself — background "
            "to understand them and tailor help. Bring it up only when they ask or "
            "it clearly helps right now; never recite it):")
    lines = [head]
    if top_bits:
        lines.append(f"- Usually (last {s['days']} days): " + "; ".join(top_bits))
    if today:
        lines.append(f"- Today so far: {today}")
    if right_now:
        lines.append(f"- {right_now}")
    full = "\n".join(lines)

    usual = ", ".join(t["app"] for t in s["top"][:3])
    short_bits = [b for b in (right_now, f"usually in {usual}" if usual else "") if b]
    short = ("(What you've noticed about their routine — background only: "
             + "; ".join(short_bits) + ")") if short_bits else ""
    return full, short


def prompt_block(query: str = "", now: float | None = None) -> str:
    """Full habits when they ask about their habits/time, one line otherwise."""
    now = time.time() if now is None else now
    try:
        if not get_tracker().settings(now).get("enabled", True):
            return ""
        if now - _prompt_cache["ts"] > PROMPT_TTL:
            full, short = _blocks(now)
            _prompt_cache.update(ts=now, full=full, short=short)
    except Exception as e:  # noqa: BLE001 — habits are a bonus, never a blocker
        print(f"[AURA Habits] prompt block skipped: {e}")
        return ""
    if is_habit_question(query):
        # asked directly: rebuild so "right now" and today are exact
        try:
            full, short = _blocks(now)
            _prompt_cache.update(ts=now, full=full, short=short)
        except Exception:  # noqa: BLE001
            pass
        return _prompt_cache["full"] + (
            "\n(They asked about their habits. Answer from the above with real "
            "numbers. If it's empty or thin, say you haven't watched long enough yet.)"
            if _prompt_cache["full"] else
            "\n(They asked about their habits, but you haven't noticed enough yet — "
            "say so honestly.)"
        )
    return _prompt_cache["short"]
