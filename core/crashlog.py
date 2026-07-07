"""AURA crash logging — make silent deaths diagnosable.

Normal Python exceptions in AURA are caught per-thread and shown via
`taskFailed`, so a crash that leaves NO traceback (like the one on
2026-07-07) is almost always a native/C-level crash (e.g. pygame's mixer
hit from two threads at once) or an exception raised in a thread that had
no handler. This installs three catch-alls so the *next* crash is written
to logs/aura_crash.log with a full traceback instead of vanishing:

  * faulthandler        — dumps C-level fatal signals (segfault, abort)
  * sys.excepthook      — uncaught exceptions on the main thread
  * threading.excepthook— uncaught exceptions in any background thread

Call install() once, as early as possible in main.
"""

import datetime
import faulthandler
import os
import sys
import threading
import traceback

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
_LOG_PATH = os.path.join(_LOG_DIR, "aura_crash.log")

_installed = False
_fault_file = None  # keep the faulthandler file handle alive for the process


def _timestamp() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _write(header: str, body: str):
    """Append one crash record to the log and echo it to stderr."""
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"\n{'=' * 70}\n{_timestamp()}  {header}\n{'-' * 70}\n")
            fh.write(body)
            fh.write("\n")
    except Exception:
        pass  # never let the crash logger itself crash the app
    # Always echo to the console too — the terminal is where the user looks.
    print(f"\n[AURA CRASH] {header} — logged to {_LOG_PATH}", file=sys.stderr)
    print(body, file=sys.stderr)


def _main_excepthook(exc_type, exc_value, exc_tb):
    body = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    _write("main-thread uncaught exception", body)
    # Preserve default behavior so nothing else changes.
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _thread_excepthook(args):
    thread_name = getattr(args.thread, "name", "?")
    body = "".join(
        traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
    )
    _write(f"exception in background thread '{thread_name}'", body)


def install():
    """Idempotently install all crash hooks. Safe to call more than once."""
    global _installed, _fault_file
    if _installed:
        return
    _installed = True

    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        # Route faulthandler's native-crash dumps to the same log file.
        _fault_file = open(_LOG_PATH, "a", encoding="utf-8")
        faulthandler.enable(file=_fault_file, all_threads=True)
    except Exception:
        # Fall back to stderr dumps if the file can't be opened.
        try:
            faulthandler.enable(all_threads=True)
        except Exception:
            pass

    sys.excepthook = _main_excepthook
    # threading.excepthook exists on Python 3.8+
    if hasattr(threading, "excepthook"):
        threading.excepthook = _thread_excepthook

    print(f"[AURA] Crash logging active → {_LOG_PATH}")
