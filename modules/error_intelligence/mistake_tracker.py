# modules/error_intelligence/mistake_tracker.py
"""
Mistake tracker — the memory behind "Today's Mistakes" and the "semicolons
down 83%" trend.

Persists to memory/mistake_log.json (same folder + style as
relationship_state.json). One record per error id:

    {
      "missing_semicolon": {
        "total": 42,
        "daily": {"2026-07-08": 12, "2026-07-07": 9, ...},
        "last_seen": 1783486699.0
      },
      ...
    }

Design notes:
- Daily buckets keyed by ISO date make both the "today" count and the trend
  window trivial, and keep the file human-readable/inspectable.
- Writes are atomic (temp file + replace) so a crash mid-write can't corrupt
  the log — this runs inside a live desktop app.
- All reads/writes are defensive: a missing or corrupt file resets to empty
  rather than crashing AURA.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from datetime import date, datetime, timedelta

_DEFAULT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "memory", "mistake_log.json"
)

_LOCK = threading.Lock()


def _today_str() -> str:
    return date.today().isoformat()


class MistakeTracker:
    def __init__(self, path: str | None = None):
        self.path = os.path.abspath(path or _DEFAULT_PATH)
        self._data: dict = {}
        self._load()

    # ── persistence ────────────────────────────────────────────────────────
    def _load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                self._data = json.load(fh)
            if not isinstance(self._data, dict):
                self._data = {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._data = {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        # Atomic write: dump to a temp file in the same dir, then replace.
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    # ── recording ────────────────────────────────────────────────────────
    def record(self, entry_id: str, label: str = "") -> tuple[int, int]:
        """Log one occurrence of `entry_id`. Returns (count_today, total)
        *including* this occurrence — the reply layer uses count_today to pick
        an escalation tier."""
        with _LOCK:
            rec = self._data.setdefault(
                entry_id, {"total": 0, "daily": {}, "label": label, "last_seen": 0.0}
            )
            if label and not rec.get("label"):
                rec["label"] = label
            today = _today_str()
            rec["daily"][today] = rec["daily"].get(today, 0) + 1
            rec["total"] = rec.get("total", 0) + 1
            rec["last_seen"] = time.time()
            self._save()
            return rec["daily"][today], rec["total"]

    # ── queries ────────────────────────────────────────────────────────────
    def count_today(self, entry_id: str) -> int:
        rec = self._data.get(entry_id)
        if not rec:
            return 0
        return rec.get("daily", {}).get(_today_str(), 0)

    def total(self, entry_id: str) -> int:
        rec = self._data.get(entry_id)
        return rec.get("total", 0) if rec else 0

    def today_summary(self) -> list[dict]:
        """For the 'Today's Mistakes' panel. Sorted most-frequent first.
        Each item: {id, label, count}."""
        today = _today_str()
        rows = []
        for entry_id, rec in self._data.items():
            count = rec.get("daily", {}).get(today, 0)
            if count > 0:
                rows.append(
                    {
                        "id": entry_id,
                        "label": rec.get("label") or entry_id,
                        "count": count,
                    }
                )
        rows.sort(key=lambda r: r["count"], reverse=True)
        return rows

    def trend(self, entry_id: str, window_days: int = 7) -> dict | None:
        """Compare the most recent `window_days` against the `window_days`
        immediately before it. Returns a dict describing the change, or None
        if there isn't enough history to say anything honest.

        {
          "recent": 5, "previous": 30,
          "delta_pct": -83.3, "direction": "down", "label": ...
        }
        A negative delta_pct on an *error* count is good news, so the UI can
        render "down 83% — nice."
        """
        rec = self._data.get(entry_id)
        if not rec:
            return None
        daily = rec.get("daily", {})
        if not daily:
            return None

        today = date.today()
        recent = _sum_window(daily, today, 0, window_days)
        previous = _sum_window(daily, today, window_days, window_days)

        if previous == 0:
            # No baseline to compare against — don't fabricate a percentage.
            if recent == 0:
                return None
            return {
                "recent": recent,
                "previous": 0,
                "delta_pct": None,
                "direction": "new",
                "label": rec.get("label") or entry_id,
            }

        delta_pct = (recent - previous) / previous * 100.0
        direction = "flat"
        if delta_pct <= -5:
            direction = "down"
        elif delta_pct >= 5:
            direction = "up"
        return {
            "recent": recent,
            "previous": previous,
            "delta_pct": round(delta_pct, 1),
            "direction": direction,
            "label": rec.get("label") or entry_id,
        }

    def all_trends(self, window_days: int = 7) -> list[dict]:
        out = []
        for entry_id in self._data:
            t = self.trend(entry_id, window_days)
            if t:
                t["id"] = entry_id
                out.append(t)
        # Biggest improvements first (most negative delta), Nones last.
        out.sort(key=lambda t: (t["delta_pct"] is None, t.get("delta_pct") or 0))
        return out

    def reset(self) -> None:
        """Wipe all history (used by tests and a possible 'clear stats' action)."""
        with _LOCK:
            self._data = {}
            self._save()


def _sum_window(daily: dict, anchor: date, offset_days: int, span_days: int) -> int:
    """Sum counts for the span of `span_days` ending `offset_days` before
    `anchor`. offset=0 → the most recent span including today."""
    total = 0
    start = offset_days
    for i in range(start, start + span_days):
        day = (anchor - timedelta(days=i)).isoformat()
        total += daily.get(day, 0)
    return total
