"""
AURA's action tools — the *do* side, next to core/tools.py's read-only *fetch* side.

core/tools.py is read-only on purpose. These are the tools that change the
world: open an app, type into the focused window, press a hotkey, run a shell
command. They are driven by core/remote_control (a command sent from the
phone), never by the ordinary chat tool loop. So a casual chat turn can never
end with AURA pressing keys on its own.

Every action carries a risk level:
    "safe"    — runs as part of a plan without asking
    "confirm" — the whole plan waits until the phone approves it

Risk depends on the action AND its args: `hotkey ctrl+s` is safe,
`hotkey alt+f4` is not. See risk_of().

Every action degrades to a short result string. A missing dependency
(pyautogui on a headless box, say) comes back as "<name> failed: …", never as
an exception, so one bad step reports itself instead of crashing the job.

Kill switches:
    * pyautogui.FAILSAFE — slam the mouse into a screen corner to abort
    * STOP (threading.Event) — set by the phone's Stop button; checked
      between steps and between keystroke chunks
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
import threading
import time
import webbrowser

STOP = threading.Event()

MAX_TEXT_LEN = 4000        # longest single type_text
MAX_WAIT_SECONDS = 10
SHELL_TIMEOUT = 60
MAX_RESULT_LEN = 1200

# Key combos that close, delete, kill or log out. Order inside a combo doesn't
# matter, so each entry is a frozenset of normalised key names.
_RISKY_COMBOS = {
    frozenset({"alt", "f4"}),
    frozenset({"ctrl", "w"}),
    frozenset({"ctrl", "shift", "w"}),
    frozenset({"ctrl", "q"}),
    frozenset({"ctrl", "alt", "delete"}),
    frozenset({"ctrl", "shift", "esc"}),
    frozenset({"shift", "delete"}),
    frozenset({"win", "l"}),
    frozenset({"win", "x"}),
    frozenset({"win", "r"}),
    frozenset({"cmd", "q"}),
    frozenset({"cmd", "w"}),
}
_RISKY_KEYS = {"delete", "del"}

_KEY_ALIASES = {
    "control": "ctrl", "ctl": "ctrl", "windows": "win", "super": "win",
    "command": "cmd", "return": "enter", "escape": "esc", "del": "delete",
    "pgup": "pageup", "pgdn": "pagedown", "option": "alt",
}


class ActionError(RuntimeError):
    pass


class Stopped(RuntimeError):
    """Raised mid-action when STOP is set."""


# ---------------------------------------------------------------------------
# Lazy dependency access — importing this module must work on any box.
# ---------------------------------------------------------------------------
def _gui():
    try:
        import pyautogui  # noqa: WPS433
    except Exception as e:  # noqa: BLE001 — ImportError, or no display
        raise ActionError(f"desktop control unavailable ({e.__class__.__name__}: {e})") from e
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    return pyautogui


def desktop_available() -> tuple[bool, str]:
    """Can this machine actually be driven? (pyautogui importable + a display)."""
    try:
        gui = _gui()
        gui.size()
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _check_stop() -> None:
    if STOP.is_set():
        raise Stopped("stopped")


def _norm_key(k: str) -> str:
    k = str(k or "").strip().lower()
    return _KEY_ALIASES.get(k, k)


def _keys_arg(keys) -> list[str]:
    if isinstance(keys, str):
        keys = re.split(r"\s*\+\s*|\s+", keys.strip())
    return [_norm_key(k) for k in (keys or []) if str(k).strip()]


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
def _open_app(name: str = "", **_) -> str:
    if not name.strip():
        raise ActionError("no app name")
    from modules.command_handler import open_app
    return open_app(name)


def _open_url(url: str = "", **_) -> str:
    url = url.strip()
    if url and not re.match(r"(?i)^https?://", url):
        url = "https://" + url
    if not re.match(r"(?i)^https?://[^\s/$.?#][^\s]*$", url):
        raise ActionError(f"not a web address: {url!r}")
    webbrowser.open(url, new=2)
    return f"Opened {url}."


def _focus_window(title: str = "", **_) -> str:
    from modules import screen_reader
    win = screen_reader.find_window(title)
    if win is None:
        raise ActionError(f"no open window matches {title!r}")
    try:
        if win.isMinimized:
            win.restore()
        win.activate()
    except Exception:  # noqa: BLE001
        # Windows refuses SetForegroundWindow from a background process
        # unless it just received input; a stray alt tap unlocks it.
        gui = _gui()
        gui.press("alt")
        win.activate()
    time.sleep(0.3)
    return f"Focused {win.title}."


def _close_window(title: str = "", **_) -> str:
    if title:
        _focus_window(title)
    from modules import screen_reader
    current = screen_reader.get_active_window()
    if current and "aura" in current.lower():
        raise ActionError("refusing to close AURA's own window")
    _gui().hotkey("alt", "f4")
    return f"Closed {current or 'the active window'}."


def _type_text(text: str = "", **_) -> str:
    if not text:
        raise ActionError("nothing to type")
    text = text[:MAX_TEXT_LEN]
    gui = _gui()
    if text.isascii():
        # Chunked so the Stop button can land mid-paragraph.
        for i in range(0, len(text), 40):
            _check_stop()
            gui.write(text[i:i + 40], interval=0.01)
    else:
        # pyautogui.write only knows ASCII — paste anything else.
        import pyperclip
        previous = None
        try:
            previous = pyperclip.paste()
        except Exception:  # noqa: BLE001
            pass
        pyperclip.copy(text)
        gui.hotkey("command" if platform.system() == "Darwin" else "ctrl", "v")
        time.sleep(0.2)
        if previous is not None:
            try:
                pyperclip.copy(previous)
            except Exception:  # noqa: BLE001
                pass
    return f"Typed {len(text)} characters."


def _press(key: str = "", times: int = 1, **_) -> str:
    key = _norm_key(key)
    if not key:
        raise ActionError("no key")
    times = max(1, min(int(times or 1), 20))
    gui = _gui()
    for _i in range(times):
        _check_stop()
        gui.press(key)
    return f"Pressed {key}" + (f" ×{times}." if times > 1 else ".")


def _hotkey(keys=None, **_) -> str:
    combo = _keys_arg(keys)
    if not combo:
        raise ActionError("no keys")
    _gui().hotkey(*combo)
    return f"Pressed {'+'.join(combo)}."


def _click(x=None, y=None, button: str = "left", clicks: int = 1, **_) -> str:
    gui = _gui()
    button = button if button in {"left", "right", "middle"} else "left"
    clicks = max(1, min(int(clicks or 1), 3))
    if x is None or y is None:
        gui.click(button=button, clicks=clicks)
        return f"Clicked {button} where the mouse is."
    w, h = gui.size()
    x, y = int(x), int(y)
    if not (0 <= x < w and 0 <= y < h):
        raise ActionError(f"({x}, {y}) is off-screen ({w}×{h})")
    gui.click(x=x, y=y, button=button, clicks=clicks)
    return f"Clicked {button} at ({x}, {y})."


def _scroll(amount: int = -5, **_) -> str:
    amount = max(-50, min(int(amount or 0), 50))
    _gui().scroll(amount * 100)
    return f"Scrolled {'up' if amount > 0 else 'down'} {abs(amount)}."


def _wait(seconds: float = 1, **_) -> str:
    seconds = max(0.0, min(float(seconds or 0), MAX_WAIT_SECONDS))
    end = time.time() + seconds
    while (left := end - time.time()) > 0:
        _check_stop()
        time.sleep(min(0.2, left))
    return f"Waited {seconds:g}s."


def _read_screen(**_) -> str:
    from modules import screen_reader
    title = screen_reader.get_active_window()
    text = ""
    try:
        text = screen_reader.extract_text_from_screen()
    except Exception:  # noqa: BLE001
        pass
    out = f"Active window: {title}"
    if text:
        out += f"\nVisible text: {text}"
    return out


def _run_shell(command: str = "", **_) -> str:
    command = command.strip()
    if not command:
        raise ActionError("no command")
    proc = subprocess.run(
        command, shell=True, capture_output=True, text=True,
        timeout=SHELL_TIMEOUT, cwd=os.path.expanduser("~"),
    )
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return f"exit {proc.returncode}" + (f"\n{out}" if out else "")


ACTIONS: dict[str, dict] = {
    "open_app":     {"fn": _open_app,     "risk": "safe",    "args": '{"name": "chrome"}',
                     "help": "launch an installed app by name"},
    "open_url":     {"fn": _open_url,     "risk": "safe",    "args": '{"url": "https://..."}',
                     "help": "open a web page in the default browser"},
    "focus_window": {"fn": _focus_window, "risk": "safe",    "args": '{"title": "part of the window title"}',
                     "help": "bring an already-open window to the front"},
    "type_text":    {"fn": _type_text,    "risk": "safe",    "args": '{"text": "..."}',
                     "help": "type text into the focused window (does NOT press enter)"},
    "press":        {"fn": _press,        "risk": "safe",    "args": '{"key": "enter", "times": 1}',
                     "help": "press one key: enter, tab, esc, up, down, space, f5, ..."},
    "hotkey":       {"fn": _hotkey,       "risk": "safe",    "args": '{"keys": ["ctrl", "s"]}',
                     "help": "press a key combination"},
    "scroll":       {"fn": _scroll,       "risk": "safe",    "args": '{"amount": -5}',
                     "help": "scroll the focused window (negative = down)"},
    "click":        {"fn": _click,        "risk": "safe",    "args": '{"x": 100, "y": 200}',
                     "help": "click at screen coordinates — ONLY if you know them exactly"},
    "wait":         {"fn": _wait,         "risk": "safe",    "args": '{"seconds": 2}',
                     "help": "pause, e.g. while an app or page loads (max 10)"},
    "read_screen":  {"fn": _read_screen,  "risk": "safe",    "args": "{}",
                     "help": "report the active window and the text visible on screen"},
    "close_window": {"fn": _close_window, "risk": "confirm", "args": '{"title": "optional"}',
                     "help": "close a window (the active one if no title)"},
    "run_shell":    {"fn": _run_shell,    "risk": "confirm", "args": '{"command": "..."}',
                     "help": "run a shell command in the home folder (60s limit)"},
}


def catalogue() -> str:
    return "\n".join(
        f"  {n} {a['args']}  — {a['help']}" + ("  [asks first]" if a["risk"] == "confirm" else "")
        for n, a in ACTIONS.items()
    )


def risk_of(name: str, args: dict | None) -> str:
    """'safe' or 'confirm' for one step. Unknown actions are 'confirm' (and
    will fail anyway) so nothing unrecognised ever runs unasked."""
    spec = ACTIONS.get(name)
    if not spec:
        return "confirm"
    if spec["risk"] == "confirm":
        return "confirm"
    args = args or {}
    if name == "hotkey" and frozenset(_keys_arg(args.get("keys"))) in _RISKY_COMBOS:
        return "confirm"
    if name == "press" and _norm_key(args.get("key", "")) in _RISKY_KEYS:
        return "confirm"
    return "safe"


def describe(name: str, args: dict | None) -> str:
    """One human line for the phone: 'Type “hello”', 'Press ctrl+s'."""
    a = args or {}
    if name == "open_app":
        return f"Open {a.get('name', '?')}"
    if name == "open_url":
        return f"Open {a.get('url', '?')}"
    if name == "focus_window":
        return f"Switch to {a.get('title', '?')}"
    if name == "type_text":
        t = str(a.get("text", ""))
        return f"Type “{t[:60]}{'…' if len(t) > 60 else ''}”"
    if name == "press":
        n = int(a.get("times") or 1)
        return f"Press {a.get('key', '?')}" + (f" ×{n}" if n > 1 else "")
    if name == "hotkey":
        return f"Press {'+'.join(_keys_arg(a.get('keys')))}"
    if name == "scroll":
        amt = int(a.get("amount") or 0)
        return f"Scroll {'up' if amt > 0 else 'down'}"
    if name == "click":
        return f"Click at ({a.get('x')}, {a.get('y')})" if a.get("x") is not None else "Click"
    if name == "wait":
        return f"Wait {a.get('seconds', 1)}s"
    if name == "read_screen":
        return "Read the screen"
    if name == "close_window":
        return f"Close {a.get('title') or 'the active window'}"
    if name == "run_shell":
        return f"Run `{a.get('command', '?')}`"
    return f"{name} {a}"


def run_action(name: str, args: dict | None) -> tuple[bool, str]:
    """Execute one action → (ok, result). Never raises except Stopped."""
    spec = ACTIONS.get(name)
    if not spec:
        return False, f"no such action '{name}'"
    _check_stop()
    clean = {k: (v[:MAX_TEXT_LEN] if isinstance(v, str) else v) for k, v in (args or {}).items()}
    try:
        out = spec["fn"](**clean)
        return True, (str(out or "done").strip())[:MAX_RESULT_LEN]
    except Stopped:
        raise
    except subprocess.TimeoutExpired:
        return False, f"{name} timed out after {SHELL_TIMEOUT}s"
    except Exception as e:  # noqa: BLE001 — includes pyautogui.FailSafeException
        if e.__class__.__name__ == "FailSafeException":
            STOP.set()
            raise Stopped("mouse fail-safe triggered") from e
        return False, f"{name} failed: {e}"
