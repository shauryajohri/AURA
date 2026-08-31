# modules/interestingness_engine.py
# Interestingness Engine — "Just because I noticed something doesn't mean it's worth saying."

import re
import time
import json
import os
from collections import defaultdict

# ── Threshold ─────────────────────────────────────────────────────────────────
INTERRUPT_THRESHOLD = 20   # score must exceed this to allow speaking

# ── Memory file ───────────────────────────────────────────────────────────────
MEMORY_FILE = os.path.join(os.path.dirname(__file__), "..", "memory", "observation_memory.json")

# ── Scoring table ─────────────────────────────────────────────────────────────
SCORES = {
    "traceback":              30,
    "build_failed":           28,
    "build_success_streak":   25,
    "todo_stale":             25,
    "circular_import":        40,
    "same_function_edited":   20,
    "repeated_file_this_week":15,
    "file_changed":            5,
    "new_error_keyword":      22,
    "same_error_repeated":    10,
    "user_returned":          10,
    "stack_overflow_open":     8,
    "new_file_opened":         6,
    "long_idle_then_active":  10,
    "generic_code_visible":    0,
    "nothing_changed":         0,
}

# ── Error / frustration keywords ──────────────────────────────────────────────
ERROR_KEYWORDS = [
    "traceback", "error", "exception", "failed", "failure",
    "syntaxerror", "typeerror", "nameerror", "attributeerror",
    "importerror", "valueerror", "crash", "cannot", "undefined",
    "not found", "denied", "timeout", "exit code 1",
]

BUILD_SUCCESS_KEYWORDS = ["build successful", "compiled successfully", "tests passed", "all tests"]
BUILD_FAIL_KEYWORDS    = ["build failed", "compilation error", "exit code 1", "make: ***"]
TODO_PATTERN           = re.compile(r"#\s*todo", re.IGNORECASE)
FUNCTION_PATTERN       = re.compile(r"def\s+(\w+)\s*\(", re.IGNORECASE)
IMPORT_ERROR_PATTERN   = re.compile(r"circular import|import error|cannot import", re.IGNORECASE)


# ── Observation Memory ────────────────────────────────────────────────────────

class ObservationMemory:
    """
    Remembers what AURA has seen across ticks and sessions.
    Tracks: file visit counts, error history, function edit counts, last seen signatures.
    """
    def __init__(self):
        self.data = self._load()

    def _load(self) -> dict:
        try:
            if os.path.exists(MEMORY_FILE):
                with open(MEMORY_FILE) as f:
                    return json.load(f)
        except Exception as e:
            print(f"[InterestingnessEngine] Memory load error: {e}")
        return {
            "file_visits": {},        # filename -> list of timestamps
            "error_signatures": {},   # error_text_hash -> count
            "function_edits": {},     # function_name -> count this session
            "last_signature": "",     # last screen signature
            "last_file": "",          # last active file name
            "last_seen_errors": [],   # error keywords seen last tick
            "session_start": time.time(),
        }

    def _save(self):
        try:
            os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
            with open(MEMORY_FILE, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"[InterestingnessEngine] Memory save error: {e}")

    def record_file_visit(self, filename: str):
        if not filename or filename == "unknown":
            return
        visits = self.data["file_visits"].get(filename, [])
        visits.append(time.time())
        # Keep only last 30 days
        cutoff = time.time() - (30 * 86400)
        visits = [v for v in visits if v > cutoff]
        self.data["file_visits"][filename] = visits
        self._save()

    def file_visit_count_this_week(self, filename: str) -> int:
        cutoff = time.time() - (7 * 86400)
        visits = self.data["file_visits"].get(filename, [])
        return sum(1 for v in visits if v > cutoff)

    def record_function_edit(self, fn_name: str):
        count = self.data["function_edits"].get(fn_name, 0)
        self.data["function_edits"][fn_name] = count + 1
        self._save()

    def get_function_edit_count(self, fn_name: str) -> int:
        return self.data["function_edits"].get(fn_name, 0)

    def reset_function_edits(self):
        self.data["function_edits"] = {}
        self._save()

    def set_last_signature(self, sig: str):
        self.data["last_signature"] = sig
        self._save()

    def get_last_signature(self) -> str:
        return self.data.get("last_signature", "")

    def set_last_file(self, filename: str):
        self.data["last_file"] = filename
        self._save()

    def get_last_file(self) -> str:
        return self.data.get("last_file", "")

    def set_last_seen_errors(self, errors: list):
        self.data["last_seen_errors"] = errors
        self._save()

    def get_last_seen_errors(self) -> list:
        return self.data.get("last_seen_errors", [])


# ── Observation ───────────────────────────────────────────────────────────────

def _extract_filename(window_title: str) -> str:
    """Pull filename from VS Code style title: 'brain.py - AURA - Visual Studio Code'"""
    parts = window_title.split(" - ")
    if parts:
        name = parts[0].strip()
        if "." in name:
            return name
    return ""


def _extract_functions(text: str) -> list:
    return FUNCTION_PATTERN.findall(text)


def _extract_errors(text: str) -> list:
    text_lower = text.lower()
    return [kw for kw in ERROR_KEYWORDS if kw in text_lower]


def _make_signature(ctx: dict) -> str:
    app = re.sub(r"\s+", " ", ctx.get("app", "")).lower().strip()
    text = ctx.get("visible_text", "")[:200].lower()
    return f"{app}|{text}"


# ── Interestingness Engine ────────────────────────────────────────────────────

class InterestingnessEngine:
    def __init__(self):
        self.memory = ObservationMemory()
        self._last_tick_time = time.time()
        self._consecutive_silent_ticks = 0
        self._build_fail_count = 0

    def score(self, ctx: dict, idle_seconds: float = 0) -> dict:
        """
        Main method. Takes screen context, returns:
        {
            "score": int,
            "reasons": [str, ...],
            "should_interrupt": bool,
            "observation": dict   ← structured facts for LLM prompt
        }
        """
        text         = ctx.get("visible_text", "")
        text_lower   = text.lower()
        app          = ctx.get("app", "unknown")
        filename     = _extract_filename(app)
        sig          = _make_signature(ctx)
        last_sig     = self.memory.get_last_signature()
        last_file    = self.memory.get_last_file()
        last_errors  = self.memory.get_last_seen_errors()

        total_score = 0
        reasons     = []
        observation = {
            "app":      app,
            "filename": filename,
            "errors":   [],
            "functions":[],
            "changed":  False,
            "facts":    [],
        }

        # ── Nothing changed ────────────────────────────────────────────────
        if sig == last_sig:
            self._consecutive_silent_ticks += 1
            return {
                "score": 0,
                "reasons": ["nothing changed"],
                "should_interrupt": False,
                "observation": observation,
            }
        self._consecutive_silent_ticks = 0
        observation["changed"] = True

        # ── File tracking ──────────────────────────────────────────────────
        if filename:
            self.memory.record_file_visit(filename)
            week_visits = self.memory.file_visit_count_this_week(filename)

            if filename != last_file:
                total_score += SCORES["file_changed"]
                reasons.append(f"switched to {filename}")
                observation["facts"].append(f"opened {filename}")

            if week_visits >= 5:
                total_score += SCORES["repeated_file_this_week"]
                reasons.append(f"{filename} opened {week_visits}x this week")
                observation["facts"].append(f"{filename} revisited {week_visits} times this week")

        # ── Error detection ────────────────────────────────────────────────
        current_errors = _extract_errors(text)
        observation["errors"] = current_errors

        if current_errors:
            new_errors = [e for e in current_errors if e not in last_errors]

            if "traceback" in current_errors:
                total_score += SCORES["traceback"]
                reasons.append("traceback visible")
                observation["facts"].append("traceback on screen")

            elif new_errors:
                total_score += SCORES["new_error_keyword"]
                reasons.append(f"new errors: {', '.join(new_errors)}")
                observation["facts"].append(f"new errors appeared: {', '.join(new_errors)}")

            elif current_errors == last_errors:
                total_score += SCORES["same_error_repeated"]
                reasons.append("same error still on screen")
                observation["facts"].append("same error persisting")

        # ── Circular import ────────────────────────────────────────────────
        if IMPORT_ERROR_PATTERN.search(text):
            total_score += SCORES["circular_import"]
            reasons.append("circular import detected")
            observation["facts"].append("circular import error visible")

        # ── Build status ───────────────────────────────────────────────────
        if any(kw in text_lower for kw in BUILD_FAIL_KEYWORDS):
            self._build_fail_count += 1
            total_score += SCORES["build_failed"]
            reasons.append("build failed")
            observation["facts"].append("build failed")

        if any(kw in text_lower for kw in BUILD_SUCCESS_KEYWORDS):
            if self._build_fail_count >= 2:
                total_score += SCORES["build_success_streak"]
                reasons.append(f"build succeeded after {self._build_fail_count} failures")
                observation["facts"].append(f"build finally succeeded after {self._build_fail_count} attempts")
            self._build_fail_count = 0

        # ── Function edits ─────────────────────────────────────────────────
        functions = _extract_functions(text)
        observation["functions"] = functions

        for fn in functions:
            self.memory.record_function_edit(fn)
            count = self.memory.get_function_edit_count(fn)
            if count >= 5:
                total_score += SCORES["same_function_edited"]
                reasons.append(f"{fn}() edited {count} times this session")
                observation["facts"].append(f"{fn}() has been modified {count} times this session")

        # ── TODO detection ─────────────────────────────────────────────────
        if TODO_PATTERN.search(text):
            total_score += SCORES["todo_stale"]
            reasons.append("TODO comment visible")
            observation["facts"].append("TODO comment on screen — possibly stale")

        # ── Stack Overflow ─────────────────────────────────────────────────
        if "stackoverflow" in app.lower() or "stackoverflow" in text_lower:
            total_score += SCORES["stack_overflow_open"]
            reasons.append("StackOverflow open")
            observation["facts"].append("StackOverflow open — looking something up")

        # ── User returned after idle ───────────────────────────────────────
        if idle_seconds > 120 and sig != last_sig:
            total_score += SCORES["long_idle_then_active"]
            reasons.append(f"returned after {int(idle_seconds/60)}min idle")
            observation["facts"].append(f"user was away for {int(idle_seconds/60)} minutes")

        # ── Update memory ──────────────────────────────────────────────────
        self.memory.set_last_signature(sig)
        self.memory.set_last_file(filename)
        self.memory.set_last_seen_errors(current_errors)

        should_interrupt = total_score >= INTERRUPT_THRESHOLD

        print(f"[InterestingnessEngine] Score: {total_score} | Reasons: {reasons} | Interrupt: {should_interrupt}")

        return {
            "score":            total_score,
            "reasons":          reasons,
            "should_interrupt": should_interrupt,
            "observation":      observation,
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
_engine = InterestingnessEngine()

def get_engine() -> InterestingnessEngine:
    return _engine