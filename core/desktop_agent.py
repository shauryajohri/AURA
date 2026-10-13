"""
core/desktop_agent.py
---------------------
"Do it for me": AURA operates the computer in front of the user, on request.

The loop, one step at a time:

    look      screenshot + the clickable parts of the window in front
              (Windows UI Automation), each numbered on the screenshot
    decide    a vision model picks ONE action — preferably "click element 12"
              rather than raw coordinates, which free models get wrong
    check     safety rules: some actions are blocked outright, risky ones
              wait for the user to press Allow
    act       mouse / keyboard via pyautogui
    repeat    until the model says done, the user stops it, or a limit hits

Safety, built in from the start:
  · Esc stops instantly (global hotkey), and so does the Stop button.
  · Moving the mouse yourself = you took over; AURA stops.
  · pyautogui's fail-safe: slam the mouse into a screen corner to abort.
  · Never types into password fields or types card numbers — blocked.
  · Delete / send / pay / buy / post / close / terminal commands and anything
    the model itself flags as risky → asks first. No answer in time = no.
  · Hard limits on steps and total time.
  · Every step is published, so the always-on-top control bar shows exactly
    what she's doing.

Everything platform-specific (observing, acting, the Esc hook) sits behind
small interfaces so the loop and the safety rules are testable anywhere.
"""

from __future__ import annotations

import base64
import io
import json
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

MAX_STEPS = 25
MAX_SECONDS = 5 * 60
CONFIRM_TIMEOUT = 60.0
SETTLE_SECONDS = 0.8          # let the UI react before the next look
MAX_ELEMENTS = 60
ELEMENT_BUDGET_SECONDS = 1.5  # UIA walks can crawl on huge windows
MAX_WIDTH = 1280              # screenshot width sent to the model
TAKEOVER_PIXELS = 40          # mouse moved this far by someone else = takeover
MAX_TYPE_CHARS = 500

ACTIONS = {"click", "double_click", "right_click", "type", "key", "scroll",
           "open_app", "wait", "done", "ask"}

# ── safety ──────────────────────────────────────────────────────────────────
_RISKY_WORDS = re.compile(
    r"(?i)\b("
    r"delete|remove|erase|wipe|discard|trash|empty|uninstall|format|reset|"
    r"send|submit|post|publish|reply all|share|"
    r"pay|payment|buy|purchase|order|checkout|check out|subscribe|donate|transfer|"
    r"sign out|log ?out|shut ?down|restart|power off|close without saving|"
    r"don'?t save|overwrite|replace all|confirm|accept|agree|install"
    r")\b"
)
_RISKY_KEYS = {"delete", "del", "shift+delete", "shift+del", "alt+f4",
               "ctrl+shift+delete", "ctrl+alt+delete", "win+l"}
_TERMINALS = {"terminal", "powershell", "command prompt", "cmd", "windows terminal"}
_CARD_RE = re.compile(r"(?:\d[ -]?){13,19}")
_SECRET_HINT = re.compile(r"(?i)\b(password|passcode|pin|cvv|cvc|otp|2fa|secret)\b")


@dataclass
class Element:
    id: int
    kind: str           # Button, Edit, Hyperlink …
    name: str
    box: tuple[int, int, int, int]   # left, top, right, bottom (screen pixels)
    password: bool = False

    @property
    def center(self) -> tuple[int, int]:
        l, t, r, b = self.box
        return (l + r) // 2, (t + b) // 2

    def describe(self) -> str:
        name = f" '{self.name}'" if self.name else ""
        pw = " (password field)" if self.password else ""
        return f"[{self.id}] {self.kind}{name}{pw}"


@dataclass
class Observation:
    image_b64: str                 # annotated JPEG for the model
    width: int                     # real screen size, for coordinate mapping
    height: int
    app: str = ""                  # e.g. "Chrome", from core.habits naming
    title: str = ""
    elements: list[Element] = field(default_factory=list)

    def element(self, eid: Any) -> Element | None:
        try:
            eid = int(eid)
        except (TypeError, ValueError):
            return None
        return next((e for e in self.elements if e.id == eid), None)


def parse_action(raw: str) -> dict[str, Any] | None:
    """The model's reply → a validated action dict, or None if unusable."""
    if not raw:
        return None
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        text = text[start:end + 1]
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    action = str(data.get("action", "")).strip().lower().replace(" ", "_")
    if action not in ACTIONS:
        return None
    out: dict[str, Any] = {
        "action": action,
        "thought": str(data.get("thought") or "")[:300],
        "risky": data.get("risky") is True,
    }
    if data.get("element") is not None:
        try:
            out["element"] = int(data["element"])
        except (TypeError, ValueError):
            pass
    for axis in ("x", "y"):
        if data.get(axis) is not None:
            try:
                out[axis] = max(0, min(1000, int(float(data[axis]))))
            except (TypeError, ValueError):
                pass
    for key in ("text", "keys", "message", "app", "direction"):
        if data.get(key) is not None:
            out[key] = str(data[key])
    try:
        out["amount"] = max(1, min(15, int(data.get("amount", 3))))
    except (TypeError, ValueError):
        out["amount"] = 3

    # Each action needs its own fields; a click with no target is unusable.
    if action in {"click", "double_click", "right_click"} and "element" not in out \
            and not ("x" in out and "y" in out):
        return None
    if action == "type" and not out.get("text"):
        return None
    if action == "key" and not out.get("keys"):
        return None
    if action == "open_app" and not (out.get("app") or out.get("text")):
        return None
    if action == "type":
        out["text"] = out["text"][:MAX_TYPE_CHARS]
    return out


def assess(action: dict[str, Any], obs: Observation, confirm_all: bool = False
           ) -> tuple[str, str]:
    """('ok' | 'confirm' | 'block', why). Pure — no side effects."""
    kind = action["action"]
    if kind in {"done", "ask", "wait"}:
        return "ok", ""
    el = obs.element(action.get("element"))
    text = action.get("text", "")
    keys = (action.get("keys") or "").lower().replace(" ", "")

    # Hard blocks: secrets are the user's to type, always.
    if kind == "type":
        if el and el.password:
            return "block", "that's a password field — you type passwords, not me"
        if _CARD_RE.search(text):
            return "block", "that looks like a card number — I won't type payment details"
        if _SECRET_HINT.search(f"{el.name if el else ''}"):
            return "block", "that field asks for a secret — you type that part"

    if action.get("risky"):
        return "confirm", "this step could have consequences"
    if kind == "key" and (keys in _RISKY_KEYS or keys.endswith("+delete")):
        return "confirm", f"pressing {action.get('keys')}"
    target = " ".join(filter(None, [el.name if el else "", text,
                                    action.get("app", "")]))
    hit = _RISKY_WORDS.search(target)
    if hit and kind in {"click", "double_click", "right_click", "type", "open_app"}:
        return "confirm", f"it involves '{hit.group(0)}'"
    if obs.app.lower() in _TERMINALS and kind in {"type", "key"}:
        return "confirm", "running something in a terminal"
    if confirm_all and kind not in {"scroll"}:
        return "confirm", "you asked me to check every step"
    return "ok", ""


def describe_action(action: dict[str, Any], obs: Observation | None = None) -> str:
    """Plain words for the control bar: 'click "Send"', 'type "hello"'."""
    kind = action["action"]
    el = obs.element(action.get("element")) if obs else None
    target = f'"{el.name}"' if el and el.name else (
        f"{el.kind.lower()}" if el else "a spot on screen")
    if kind in {"click", "double_click", "right_click"}:
        verb = {"click": "click", "double_click": "double-click",
                "right_click": "right-click"}[kind]
        return f"{verb} {target}"
    if kind == "type":
        shown = action["text"] if len(action["text"]) <= 60 else action["text"][:57] + "…"
        return f'type "{shown}"'
    if kind == "key":
        return f"press {action['keys']}"
    if kind == "scroll":
        return f"scroll {action.get('direction', 'down')}"
    if kind == "open_app":
        return f"open {action.get('app') or action.get('text')}"
    if kind == "wait":
        return "wait for the screen"
    return kind


# ── the model ───────────────────────────────────────────────────────────────
SYSTEM = """You are AURA, operating the user's Windows computer to finish a task they asked for.
Each turn you see a screenshot. Numbered boxes mark clickable parts of the window in front; the same numbers are listed as ELEMENTS.
Reply with ONE JSON object and nothing else:
{"thought": "<one short sentence>", "action": "<action>", ...fields}

Actions:
- {"action":"click","element":12}      (or "double_click" / "right_click")
- {"action":"click","x":500,"y":300}   only if no element fits; x,y are 0-1000 across the screen
- {"action":"type","text":"hello","element":7}   element optional; types into what's focused or that field
- {"action":"key","keys":"ctrl+l"}     e.g. enter, tab, esc, ctrl+c, alt+tab, win
- {"action":"scroll","direction":"down","amount":3,"element":4}
- {"action":"open_app","app":"notepad"}   opens an app via the Start menu
- {"action":"wait"}                     the screen is still loading
- {"action":"done","message":"<what you did, one sentence>"}
- {"action":"ask","message":"<question>"}  you need the user to decide or do something

Rules:
- Prefer elements over coordinates, and keyboard shortcuts when they're reliable.
- Set "risky": true for anything that sends, deletes, buys, posts or can't be undone.
- Never type passwords, card numbers or one-time codes — use "ask" instead.
- Ignore AURA's own control bar at the top of the screen.
- If you're stuck or the task is impossible, use "ask" or "done" and say why. Don't loop.
"""


def build_prompt(goal: str, obs: Observation, history: list[str], step: int) -> str:
    els = "\n".join(e.describe() for e in obs.elements) or "(none found — use coordinates or the keyboard)"
    hist = "\n".join(f"{i + 1}. {h}" for i, h in enumerate(history[-8:])) or "(nothing yet)"
    return (
        f"TASK: {goal}\n\n"
        f"STEP {step} of at most {MAX_STEPS}.\n"
        f"WINDOW IN FRONT: {obs.app or 'unknown'} — {obs.title[:120] or 'untitled'}\n\n"
        f"DONE SO FAR:\n{hist}\n\n"
        f"ELEMENTS:\n{els}\n\n"
        "What is the single next action? JSON only."
    )


def _vision_model(prompt: str, image_b64: str) -> str:
    from core.ai_router import call_vision
    return call_vision(prompt, image_b64, system=SYSTEM, max_tokens=300, timeout=60)


# ── the platform: look, act, stop ───────────────────────────────────────────
class Platform:
    """What the loop needs from the machine. Windows impl below; fakes in tests."""

    def observe(self) -> Observation: ...
    def click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> None: ...
    def type_text(self, text: str) -> None: ...
    def press(self, keys: str) -> None: ...
    def scroll(self, amount: int, x: int | None = None, y: int | None = None) -> None: ...
    def open_app(self, name: str) -> None: ...
    def mouse(self) -> tuple[int, int]: ...
    def watch_escape(self, on_escape: Callable[[], None]) -> Callable[[], None]: ...


class WindowsPlatform(Platform):
    _UIA_KINDS = {
        "ButtonControl": "Button", "EditControl": "Edit", "HyperlinkControl": "Link",
        "MenuItemControl": "MenuItem", "ListItemControl": "ListItem",
        "TabItemControl": "Tab", "CheckBoxControl": "CheckBox",
        "RadioButtonControl": "Radio", "ComboBoxControl": "ComboBox",
        "TreeItemControl": "TreeItem", "DocumentControl": "Document",
        "SplitButtonControl": "Button",
    }

    def __init__(self):
        import pyautogui  # noqa: F401 — fail early with a clear message
        self._pg = pyautogui
        pyautogui.FAILSAFE = True    # mouse into a corner aborts
        pyautogui.PAUSE = 0.05
        self._injecting = False

    # look
    def observe(self) -> Observation:
        from modules.screen_reader import take_screenshot
        from core.habits import foreground, label_for
        exe, title = foreground()
        img = take_screenshot()
        width, height = img.size
        elements = self._elements()
        return Observation(
            image_b64=_annotate(img, elements), width=width, height=height,
            app=label_for(exe, title) or "", title=title, elements=elements,
        )

    def _elements(self) -> list[Element]:
        try:
            import uiautomation as auto
        except Exception:  # noqa: BLE001 — no UIA: coordinates + keyboard only
            return []
        out: list[Element] = []
        deadline = time.time() + ELEMENT_BUDGET_SECONDS
        try:
            root = auto.GetForegroundControl()
            queue = [(root, 0)] if root else []
            while queue and len(out) < MAX_ELEMENTS and time.time() < deadline:
                ctrl, depth = queue.pop(0)
                kind = self._UIA_KINDS.get(getattr(ctrl, "ControlTypeName", ""))
                if kind and depth > 0:
                    try:
                        r = ctrl.BoundingRectangle
                        if r.width() > 2 and r.height() > 2 and not ctrl.IsOffscreen:
                            out.append(Element(
                                id=len(out) + 1, kind=kind,
                                name=(ctrl.Name or "").strip()[:60],
                                box=(r.left, r.top, r.right, r.bottom),
                                password=bool(getattr(ctrl, "IsPassword", False)),
                            ))
                    except Exception:  # noqa: BLE001
                        pass
                if depth < 14:
                    try:
                        queue.extend((c, depth + 1) for c in ctrl.GetChildren())
                    except Exception:  # noqa: BLE001
                        pass
        except Exception as e:  # noqa: BLE001
            print(f"[AURA Agent] UI Automation skipped: {e}")
        return out

    # act — every input is flagged so our own Esc presses don't stop us
    def _do(self, fn: Callable[[], None]) -> None:
        self._injecting = True
        try:
            fn()
        finally:
            time.sleep(0.05)
            self._injecting = False

    def click(self, x, y, button="left", clicks=1):
        self._do(lambda: self._pg.click(x=x, y=y, button=button, clicks=clicks, interval=0.08))

    def type_text(self, text):
        if text.isascii():
            self._do(lambda: self._pg.write(text, interval=0.015))
            return
        # pyautogui can't type non-ASCII; paste it instead and put the
        # clipboard back the way we found it.
        import pyperclip
        old = pyperclip.paste()
        pyperclip.copy(text)
        self._do(lambda: self._pg.hotkey("ctrl", "v"))
        time.sleep(0.1)
        pyperclip.copy(old)

    def press(self, keys):
        parts = [k.strip().lower() for k in keys.replace(" ", "").split("+") if k.strip()]
        alias = {"win": "winleft", "windows": "winleft", "return": "enter",
                 "escape": "esc", "del": "delete", "control": "ctrl"}
        parts = [alias.get(p, p) for p in parts]
        self._do(lambda: self._pg.hotkey(*parts))

    def scroll(self, amount, x=None, y=None):
        self._do(lambda: self._pg.scroll(amount * 120, x=x, y=y))

    def open_app(self, name):
        def go():
            self._pg.press("winleft")
            time.sleep(0.7)
            self._pg.write(name, interval=0.02)
            time.sleep(0.9)
            self._pg.press("enter")
        self._do(go)

    def mouse(self):
        p = self._pg.position()
        return int(p[0]), int(p[1])

    def watch_escape(self, on_escape):
        try:
            import keyboard
        except Exception:  # noqa: BLE001
            print("[AURA Agent] 'keyboard' not installed — Esc won't stop me; use Stop")
            return lambda: None

        def handler():
            if not self._injecting:
                on_escape()
        hook = keyboard.add_hotkey("esc", handler, suppress=False)
        return lambda: keyboard.remove_hotkey(hook)


def _annotate(img, elements: list[Element]) -> str:
    """Draw numbered boxes on the screenshot, downscale, return JPEG base64."""
    from PIL import ImageDraw
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)
    for e in elements:
        l, t, r, b = e.box
        draw.rectangle([l, t, r, b], outline=(255, 0, 170), width=2)
        tag = str(e.id)
        tw = 8 * len(tag) + 6
        draw.rectangle([l, t, l + tw, t + 16], fill=(255, 0, 170))
        draw.text((l + 3, t + 2), tag, fill=(255, 255, 255))
    if img.width > MAX_WIDTH:
        ratio = MAX_WIDTH / float(img.width)
        img = img.resize((MAX_WIDTH, max(1, int(img.height * ratio))))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ── the loop ────────────────────────────────────────────────────────────────
class DesktopAgent:
    """Runs one task at a time in a background thread and publishes every step."""

    def __init__(
        self,
        platform_factory: Callable[[], Platform] | None = None,
        model: Callable[[str, str], str] = _vision_model,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        settle: float = SETTLE_SECONDS,
    ):
        self._platform_factory = platform_factory or WindowsPlatform
        self._model, self._clock, self._sleep, self._settle = model, clock, sleep, settle
        self._sink: Callable[[dict], None] | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._confirm_event = threading.Event()
        self._confirm_answer = False
        self._confirm_id: str | None = None
        self._thread: threading.Thread | None = None
        self._stop_reason = "you stopped me"
        self.state: dict[str, Any] = {"state": "idle"}

    # ── wiring ─────────────────────────────────────────────────────────────
    def set_sink(self, fn: Callable[[dict], None] | None) -> None:
        self._sink = fn

    def _publish(self, **payload: Any) -> None:
        self.state = {**payload}
        if self._sink:
            try:
                self._sink(dict(payload))
            except Exception:  # noqa: BLE001 — the UI must never break the run
                pass

    def busy(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ── controls ───────────────────────────────────────────────────────────
    def start(self, goal: str, confirm_all: bool = False) -> tuple[bool, str]:
        goal = " ".join((goal or "").split())[:400]
        if not goal:
            return False, "Tell me what to do, e.g. /do open notepad and write a shopping list."
        with self._lock:
            if self.busy():
                return False, "I'm already doing something — stop that first (Esc)."
            self._stop.clear()
            self._thread = threading.Thread(
                target=self.run, args=(goal, confirm_all), name="aura-agent", daemon=True)
            self._thread.start()
        return True, "On it — I'll take the screen. Press Esc or move the mouse to stop me."

    def stop(self, reason: str = "you stopped me") -> None:
        self._stop_reason = reason
        self._stop.set()
        self._confirm_answer = False
        self._confirm_event.set()

    def confirm(self, confirm_id: str | None, allow: bool) -> bool:
        if not self._confirm_id or (confirm_id and confirm_id != self._confirm_id):
            return False
        self._confirm_answer = bool(allow)
        self._confirm_event.set()
        return True

    def _ask_permission(self, goal: str, step: int, text: str, why: str) -> bool:
        self._confirm_id = uuid.uuid4().hex[:8]
        self._confirm_answer = False
        self._confirm_event.clear()
        self._publish(state="confirm", goal=goal, step=step, action=text,
                      message=f"Allow me to {text}? ({why})", confirm_id=self._confirm_id)
        answered = self._confirm_event.wait(CONFIRM_TIMEOUT)
        allowed = answered and self._confirm_answer and not self._stop.is_set()
        self._confirm_id = None
        return allowed

    # ── the run ────────────────────────────────────────────────────────────
    def run(self, goal: str, confirm_all: bool = False) -> dict[str, Any]:
        self._stop_reason = "you stopped me"
        try:
            platform = self._platform_factory()
        except Exception as e:  # noqa: BLE001
            return self._finish("failed", goal, 0,
                                f"I can't control the screen here ({e}). "
                                "On Windows, install: pip install pyautogui uiautomation mss Pillow")
        unhook = lambda: None  # noqa: E731
        try:
            unhook = platform.watch_escape(lambda: self.stop("you pressed Esc"))
        except Exception as e:  # noqa: BLE001
            print(f"[AURA Agent] Esc hook unavailable: {e}")
        try:
            with _uia_thread():
                return self._loop(platform, goal, confirm_all)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "FailSafe" in type(e).__name__:
                return self._finish("stopped", goal, 0, "you hit the screen corner, so I stopped")
            return self._finish("failed", goal, 0, f"something went wrong: {msg[:160]}")
        finally:
            try:
                unhook()
            except Exception:  # noqa: BLE001
                pass

    def _loop(self, platform: Platform, goal: str, confirm_all: bool) -> dict[str, Any]:
        started = self._clock()
        history: list[str] = []
        last_mouse: tuple[int, int] | None = None
        bad_replies = 0
        self._publish(state="running", goal=goal, step=0, action="looking at the screen",
                      message="")

        for step in range(1, MAX_STEPS + 1):
            if self._stop.is_set():
                return self._finish("stopped", goal, step - 1, self._stop_reason)
            if self._clock() - started > MAX_SECONDS:
                return self._finish("failed", goal, step - 1,
                                    "that took too long, so I stopped — try a smaller step")
            if last_mouse is not None and _moved(platform.mouse(), last_mouse):
                return self._finish("stopped", goal, step - 1,
                                    "you moved the mouse, so I handed control back")

            obs = platform.observe()
            raw = self._model(build_prompt(goal, obs, history, step), obs.image_b64)
            if self._stop.is_set():
                return self._finish("stopped", goal, step - 1, self._stop_reason)
            if raw in {"RATE_LIMIT", "CONNECTION_ERROR", "NO_VISION_KEY"}:
                why = {"NO_VISION_KEY": "there's no API key for the vision model "
                                        "(set OPENROUTER_API_KEY)",
                       "RATE_LIMIT": "the vision model is rate-limited right now",
                       "CONNECTION_ERROR": "I couldn't reach the vision model"}[raw]
                return self._finish("failed", goal, step - 1, f"I can't see the screen: {why}")
            action = parse_action(raw)
            if action is None:
                bad_replies += 1
                history.append("(your last reply wasn't valid JSON — reply with ONE JSON object)")
                if bad_replies >= 3:
                    return self._finish("failed", goal, step - 1,
                                        "the vision model kept giving me nonsense, so I stopped")
                continue
            bad_replies = 0

            if action["action"] == "done":
                return self._finish("done", goal, step - 1,
                                    action.get("message") or "done")
            if action["action"] == "ask":
                return self._finish("ask", goal, step - 1,
                                    action.get("message") or "I need you for this part")

            # The model can take seconds; if they grabbed the mouse meanwhile,
            # acting on a screen they're now using would fight them.
            if last_mouse is not None and _moved(platform.mouse(), last_mouse):
                return self._finish("stopped", goal, step - 1,
                                    "you moved the mouse, so I handed control back")

            text = describe_action(action, obs)
            verdict, why = assess(action, obs, confirm_all)
            if verdict == "block":
                return self._finish("stopped", goal, step - 1, why)
            if verdict == "confirm":
                if not self._ask_permission(goal, step, text, why):
                    reason = self._stop_reason if self._stop.is_set() else \
                        f"you didn't allow \"{text}\", so I stopped there"
                    return self._finish("stopped", goal, step - 1, reason)
                last_mouse = None   # they just used the mouse to click Allow

            self._publish(state="running", goal=goal, step=step, action=text,
                          message=action.get("thought", ""))
            self._execute(platform, action, obs)
            history.append(text)
            last_mouse = platform.mouse()   # baseline: any move after this is the user
            self._sleep(self._settle if action["action"] != "wait" else 2.0)

        return self._finish("failed", goal, MAX_STEPS,
                            f"I ran out of steps ({MAX_STEPS}) — it may be partly done")

    def _execute(self, platform: Platform, action: dict[str, Any], obs: Observation) -> None:
        kind = action["action"]
        el = obs.element(action.get("element"))
        if el:
            x, y = el.center
        elif "x" in action and "y" in action:
            x = int(action["x"] / 1000 * obs.width)
            y = int(action["y"] / 1000 * obs.height)
        else:
            x = y = None
        if kind in {"click", "double_click", "right_click"}:
            platform.click(x, y, button="right" if kind == "right_click" else "left",
                           clicks=2 if kind == "double_click" else 1)
        elif kind == "type":
            if el:
                platform.click(x, y)   # focus the field first
            platform.type_text(action["text"])
        elif kind == "key":
            platform.press(action["keys"])
        elif kind == "scroll":
            amount = action.get("amount", 3)
            platform.scroll(amount if action.get("direction") == "up" else -amount, x, y)
        elif kind == "open_app":
            platform.open_app(action.get("app") or action.get("text", ""))

    def _finish(self, state: str, goal: str, steps: int, message: str) -> dict[str, Any]:
        result = {"state": state, "goal": goal, "step": steps, "action": "",
                  "message": message}
        self._publish(**result)
        return result


def _moved(now: tuple[int, int], before: tuple[int, int]) -> bool:
    return abs(now[0] - before[0]) > TAKEOVER_PIXELS or abs(now[1] - before[1]) > TAKEOVER_PIXELS


class _uia_thread:
    """COM must be initialised per thread for UI Automation; no-op elsewhere."""

    def __enter__(self):
        self._ctx = None
        if sys.platform == "win32":
            try:
                import uiautomation as auto
                self._ctx = auto.UIAutomationInitializerInThread()
                self._ctx.__enter__()
            except Exception:  # noqa: BLE001
                self._ctx = None
        return self

    def __exit__(self, *exc):
        if self._ctx is not None:
            try:
                self._ctx.__exit__(*exc)
            except Exception:  # noqa: BLE001
                pass
        return False


_agent: DesktopAgent | None = None


def get_agent() -> DesktopAgent:
    global _agent
    if _agent is None:
        _agent = DesktopAgent()
    return _agent


def settings() -> dict[str, bool]:
    try:
        from memory import store
        s = store.get_settings()
    except Exception:  # noqa: BLE001
        s = {}
    return {"enabled": s.get("agent.enabled", True) is not False,
            "confirm_all": s.get("agent.confirm_all", False) is True}


def start_task(goal: str) -> tuple[bool, str]:
    cfg = settings()
    if not cfg["enabled"]:
        return False, ("Screen control is off. Turn on \"let AURA control my screen\" "
                       "in Settings → Behavior first.")
    return get_agent().start(goal, confirm_all=cfg["confirm_all"])
