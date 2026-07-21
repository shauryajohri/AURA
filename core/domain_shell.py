"""
core/domain_shell.py
--------------------
A real shell behind the Domain's Terminal tab.

Not a PTY (no curses, no vim, no interactive prompts) — it's a command runner
that keeps state between calls, which is what "works like a normal terminal"
actually means in day-to-day use:

* `cd` persists, so the next command runs where you left off
* env vars set with `set X=1` / `export X=1` persist for the session
* stdout and stderr come back merged, in order, with the exit code
* every command is capped by a timeout so a runaway `npm install` can't wedge
  the bridge — and long output is truncated rather than shipped whole

Interactive programs are refused up front with a useful message instead of
hanging forever waiting on stdin.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT = 60          # seconds per command
MAX_TIMEOUT = 600
MAX_OUTPUT = 200_000          # chars returned to the UI
MAX_HISTORY = 300

# Programs that sit waiting on stdin forever — refuse rather than hang.
_INTERACTIVE = {
    "vim", "vi", "nano", "emacs", "less", "more", "top", "htop",
    "python" , "python3", "node", "irb", "ipython", "psql", "mysql", "sqlite3",
    "ssh", "ftp", "telnet",
}


class ShellSession:
    def __init__(self, cwd: str | None = None) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.cwd = str(Path(cwd).resolve()) if cwd else str(Path.home())
        self.env: dict[str, str] = dict(os.environ)
        self.history: list[str] = []
        self.created = time.time()

    # ---- builtins handled in-process so state survives ---------------------
    def _builtin(self, line: str) -> dict[str, Any] | None:
        parts = line.strip().split(None, 1)
        if not parts:
            return {"output": "", "code": 0, "cwd": self.cwd}
        cmd = parts[0].lower()
        arg = parts[1].strip().strip('"') if len(parts) > 1 else ""

        if cmd == "cd":
            target = Path(os.path.expanduser(arg or str(Path.home())))
            if not target.is_absolute():
                target = Path(self.cwd) / target
            try:
                target = target.resolve(strict=True)
            except (OSError, FileNotFoundError):
                return {"output": f"cd: no such directory: {arg}\n", "code": 1, "cwd": self.cwd}
            if not target.is_dir():
                return {"output": f"cd: not a directory: {arg}\n", "code": 1, "cwd": self.cwd}
            self.cwd = str(target)
            return {"output": "", "code": 0, "cwd": self.cwd}

        if cmd in ("pwd", "cwd"):
            return {"output": self.cwd + "\n", "code": 0, "cwd": self.cwd}

        if cmd in ("clear", "cls"):
            return {"output": "", "code": 0, "cwd": self.cwd, "clear": True}

        if cmd in ("export", "set") and "=" in arg:
            k, _, v = arg.partition("=")
            self.env[k.strip()] = v.strip().strip('"')
            return {"output": "", "code": 0, "cwd": self.cwd}

        if cmd == "exit":
            return {"output": "session ended\n", "code": 0, "cwd": self.cwd, "closed": True}

        return None

    # ---- the real thing ----------------------------------------------------
    def run(self, line: str, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
        line = (line or "").strip()
        if not line:
            return {"output": "", "code": 0, "cwd": self.cwd}

        self.history.append(line)
        del self.history[:-MAX_HISTORY]

        builtin = self._builtin(line)
        if builtin is not None:
            return builtin

        # refuse things that would block on stdin
        try:
            first = (shlex.split(line, posix=os.name != "nt") or [""])[0]
        except ValueError:
            first = line.split()[0]
        base = Path(first).name.lower().removesuffix(".exe")
        if base in _INTERACTIVE and not any(
            f in line for f in (" -c", " --version", " -V", " --help", " -m ")
        ):
            return {
                "output": (
                    f"'{base}' is interactive — this terminal runs commands and "
                    f"returns their output, so it can't hold a live session.\n"
                    f"Try a one-shot form instead, e.g. {base} -c \"...\"\n"
                ),
                "code": 1, "cwd": self.cwd,
            }

        timeout = max(1, min(int(timeout or DEFAULT_TIMEOUT), MAX_TIMEOUT))
        started = time.time()
        try:
            proc = subprocess.run(
                line,
                shell=True,
                cwd=self.cwd,
                env=self.env,
                capture_output=True,
                timeout=timeout,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            code = proc.returncode
        except subprocess.TimeoutExpired as e:
            partial = ""
            for stream in (e.stdout, e.stderr):
                if stream:
                    partial += stream if isinstance(stream, str) else stream.decode("utf-8", "replace")
            out = partial + f"\n[timed out after {timeout}s]\n"
            code = 124
        except FileNotFoundError:
            out, code = f"command not found: {line.split()[0]}\n", 127
        except Exception as e:  # noqa: BLE001
            out, code = f"[shell error] {e}\n", 1

        truncated = False
        if len(out) > MAX_OUTPUT:
            out = out[:MAX_OUTPUT] + "\n[output truncated]\n"
            truncated = True

        return {
            "output": out,
            "code": code,
            "cwd": self.cwd,
            "ms": int((time.time() - started) * 1000),
            "truncated": truncated,
        }


# ── session registry ─────────────────────────────────────────────────────────
_SESSIONS: dict[str, ShellSession] = {}
MAX_SESSIONS = 8


def open_session(cwd: str | None = None) -> ShellSession:
    if len(_SESSIONS) >= MAX_SESSIONS:
        oldest = min(_SESSIONS.values(), key=lambda s: s.created)
        _SESSIONS.pop(oldest.id, None)
    s = ShellSession(cwd)
    _SESSIONS[s.id] = s
    return s


def get_session(sid: str | None, cwd: str | None = None) -> ShellSession:
    if sid and sid in _SESSIONS:
        return _SESSIONS[sid]
    return open_session(cwd)


def close_session(sid: str) -> bool:
    return _SESSIONS.pop(sid, None) is not None


def list_sessions() -> list[dict[str, Any]]:
    return [{"id": s.id, "cwd": s.cwd, "commands": len(s.history)} for s in _SESSIONS.values()]
