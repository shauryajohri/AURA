"""
The vision loop — AURA looks at the laptop, does one thing, looks again.

    screenshot ─▶ find the text on screen (OCR boxes) ─▶ draw a lettered grid
         ▲                                                       │
         │                                                       ▼
    run the action ◀── one line back: DO / ASK / DONE / FAIL ◀── vision model

core/remote_control's blind planner guesses every step up front, which is fine
for "open spotify" but hopeless for "reply to the last message in WhatsApp".
Here the model sees the result of each step before choosing the next.

Pointing is the hard part. Free vision models are bad at pixel coordinates, so
the model never gives any. It points in one of two ways, and both turn into
real pixels on our side:
    * {"element": 12}   — a numbered piece of on-screen text from OCR (exact)
    * {"cell": "C7"}    — a square of the grid drawn over the screenshot, for
                          icons with no text (coarse, but good enough for a button)

Irreversible steps (sending, posting, paying, deleting) are the model's to flag
with ASK. Risky actions (see actions.risk_of) ask regardless of what the model
says. Both pause the loop until the phone answers.

The loop stops on: DONE, FAIL, the step budget, three steps in a row that
didn't change the screen, a denied ASK, the Stop button, or the laptop no
longer being active.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import string
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

from core import actions

GRID_COLS = 24                 # A..X
SEND_WIDTH = 1280              # screenshot width the model sees
MAX_ELEMENTS = 80
SETTLE_SECONDS = 0.8           # let the UI react before the next look
MAX_STUCK = 3


def max_steps() -> int:
    try:
        return max(1, min(int(os.getenv("AURA_VISION_MAX_STEPS", "15")), 40))
    except ValueError:
        return 15


# ---------------------------------------------------------------------------
# What the model sees
# ---------------------------------------------------------------------------
@dataclass
class Screen:
    width: int                       # screenshot pixels
    height: int
    scale_x: float                   # screenshot px → pyautogui px
    scale_y: float
    rows: int
    elements: list[dict] = field(default_factory=list)   # {id, text, box:(x,y,w,h), cell}
    model_jpeg_b64: str = ""         # downscaled + grid, for the model
    phone_jpeg: bytes = b""          # downscaled, no grid, for the phone
    fingerprint: str = ""            # tiny thumbnail hash: "did anything change?"
    window: str = ""


def col_label(i: int) -> str:
    return string.ascii_uppercase[i] if i < 26 else f"A{string.ascii_uppercase[i - 26]}"


def grid_rows(width: int, height: int) -> int:
    return max(4, round(GRID_COLS * height / max(width, 1)))


def cell_of(x: float, y: float, width: int, height: int, rows: int) -> str:
    c = min(GRID_COLS - 1, max(0, int(x / width * GRID_COLS)))
    r = min(rows - 1, max(0, int(y / height * rows)))
    return f"{col_label(c)}{r + 1}"


def cell_center(cell: str, width: int, height: int, rows: int) -> tuple[float, float]:
    m = re.fullmatch(r"\s*([A-Za-z]{1,2})\s*(\d{1,2})\s*", str(cell or ""))
    if not m:
        raise actions.ActionError(f"not a grid cell: {cell!r}")
    letters, row = m.group(1).upper(), int(m.group(2))
    labels = [col_label(i) for i in range(GRID_COLS)]
    if letters not in labels or not 1 <= row <= rows:
        raise actions.ActionError(f"cell {cell} is off the grid (A1–{labels[-1]}{rows})")
    c = labels.index(letters)
    return (c + 0.5) * width / GRID_COLS, (row - 0.5) * height / rows


def ocr_elements(img, rows: int) -> list[dict]:
    """Lines of on-screen text with their boxes, top to bottom. [] without tesseract."""
    try:
        import pytesseract
        from modules import screen_reader  # noqa: F401 — sets tesseract_cmd on Windows
        data = pytesseract.image_to_data(img.convert("L"), output_type=pytesseract.Output.DICT)
    except Exception:  # noqa: BLE001
        return []
    lines: dict[tuple, dict] = {}
    for i, word in enumerate(data.get("text", [])):
        word = (word or "").strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if not word or conf < 40 or not any(ch.isalnum() for ch in word):
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        ln = lines.setdefault(key, {"words": [], "x0": x, "y0": y, "x1": x + w, "y1": y + h})
        # A wide gap splits one OCR "line" into separate targets (menu bars).
        if ln["words"] and x - ln["x1"] > 3 * max(h, 8):
            key = key + (i,)
            ln = lines.setdefault(key, {"words": [], "x0": x, "y0": y, "x1": x + w, "y1": y + h})
        ln["words"].append(word)
        ln["x0"], ln["y0"] = min(ln["x0"], x), min(ln["y0"], y)
        ln["x1"], ln["y1"] = max(ln["x1"], x + w), max(ln["y1"], y + h)
    out = []
    for ln in sorted(lines.values(), key=lambda v: (v["y0"] // 10, v["x0"])):
        text = " ".join(ln["words"])[:60]
        box = (ln["x0"], ln["y0"], ln["x1"] - ln["x0"], ln["y1"] - ln["y0"])
        cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
        out.append({"id": len(out) + 1, "text": text, "box": box,
                    "cell": cell_of(cx, cy, img.width, img.height, rows)})
        if len(out) >= MAX_ELEMENTS:
            break
    return out


def _font(size: int):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=size)
    except TypeError:          # Pillow < 10.1
        return ImageFont.load_default()


def draw_grid(img, rows: int):
    """Faint grid with column letters along the top and row numbers down the left."""
    from PIL import Image, ImageDraw
    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    w, h = base.size
    font = _font(max(11, w // 100))
    line = (255, 0, 80, 70)
    for c in range(1, GRID_COLS):
        x = c * w / GRID_COLS
        d.line([(x, 0), (x, h)], fill=line, width=1)
    for r in range(1, rows):
        y = r * h / rows
        d.line([(0, y), (w, y)], fill=line, width=1)
    for c in range(GRID_COLS):
        x = (c + 0.5) * w / GRID_COLS
        d.rectangle([x - 8, 0, x + 8, 14], fill=(0, 0, 0, 160))
        d.text((x - 4, 0), col_label(c), fill=(255, 255, 255, 255), font=font)
    for r in range(rows):
        y = (r + 0.5) * h / rows
        d.rectangle([0, y - 7, 18, y + 7], fill=(0, 0, 0, 160))
        d.text((2, y - 7), str(r + 1), fill=(255, 255, 255, 255), font=font)
    return Image.alpha_composite(base, overlay).convert("RGB")


def _jpeg(img, quality: int = 70) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def build_screen(img, gui_size: tuple[int, int], window: str = "") -> Screen:
    """Everything the loop needs from one screenshot (pure: easy to test)."""
    width, height = img.size
    rows = grid_rows(width, height)
    small = img.convert("RGB").resize((SEND_WIDTH, max(1, round(height * SEND_WIDTH / width))))
    thumb = img.convert("L").resize((64, 36)).tobytes()
    return Screen(
        width=width, height=height,
        scale_x=gui_size[0] / width, scale_y=gui_size[1] / height,
        rows=rows,
        elements=ocr_elements(img, rows),
        model_jpeg_b64=base64.b64encode(_jpeg(draw_grid(small, rows))).decode(),
        phone_jpeg=_jpeg(small, 60),
        fingerprint=hashlib.md5(bytes(b // 16 for b in thumb)).hexdigest(),
        window=window,
    )


def capture() -> Screen:
    """Screenshot the primary monitor of the real laptop."""
    from modules import screen_reader
    img = screen_reader.take_screenshot()
    gui = actions._gui()
    return build_screen(img, tuple(gui.size()), screen_reader.get_active_window())


def resolve_point(args: dict, screen: Screen) -> tuple[int, int]:
    """{"element": n} | {"cell": "C7"} → pyautogui coordinates."""
    if args.get("element") is not None:
        try:
            n = int(args["element"])
        except (TypeError, ValueError):
            raise actions.ActionError(f"bad element {args['element']!r}") from None
        el = next((e for e in screen.elements if e["id"] == n), None)
        if el is None:
            raise actions.ActionError(f"there's no element #{n} on screen")
        x, y, w, h = el["box"]
        px, py = x + w / 2, y + h / 2
    elif args.get("cell"):
        px, py = cell_center(args["cell"], screen.width, screen.height, screen.rows)
    else:
        raise actions.ActionError('click needs {"element": N} or {"cell": "C7"}')
    return round(px * screen.scale_x), round(py * screen.scale_y)


# ---------------------------------------------------------------------------
# Talking to the model
# ---------------------------------------------------------------------------
_VISION_ACTIONS = ("open_app", "open_url", "focus_window", "type_text", "press",
                   "hotkey", "scroll", "click", "wait", "close_window")

_SYS = """You are AURA, operating your user's laptop for him. He asked you from his phone.
You see a screenshot of the laptop with a lettered grid: columns A–{last_col} across the top,
rows 1–{rows} down the left.

Reply with exactly ONE line, nothing else:
  DO: <action> <json-params>
  ASK: <short question>    before anything irreversible: sending a message or email,
                           posting, buying or paying, deleting, submitting a form
  DONE: <one sentence telling him what you did or what you found>
  FAIL: <why you can't do it>

Actions:
{catalogue}
  click {{"element": 12}} or {{"cell": "C7"}}  — add "clicks": 2 to double-click, "button": "right"

Rules:
- Click text by its element number from TEXT ON SCREEN. Use a grid cell only for icons with no text.
- Prefer keyboard shortcuts you're sure of (ctrl+l for the address bar, ctrl+t new tab).
- One action per reply. You'll get a fresh screenshot after it.
- If your last action changed nothing, try something different.
- Never type passwords, codes or payment details. If a login or captcha is in the way, FAIL.
- When the goal is done, or he asked a question you can now answer, reply DONE."""


def _catalogue() -> str:
    keep = [ln for ln in actions.catalogue().splitlines()
            if ln.split()[0] in _VISION_ACTIONS and ln.split()[0] != "click"]
    return "\n".join(keep)


def system_prompt(screen: Screen) -> str:
    return _SYS.format(last_col=col_label(GRID_COLS - 1), rows=screen.rows, catalogue=_catalogue())


def user_prompt(goal: str, screen: Screen, history: list[str], step: int, budget: int) -> str:
    els = "\n".join(f'  #{e["id"]} "{e["text"]}" @{e["cell"]}' for e in screen.elements) or "  (none read)"
    done = "\n".join(f"  {i + 1}. {h}" for i, h in enumerate(history[-12:])) or "  (nothing yet)"
    return (f"GOAL: {goal}\n"
            f"STEP {step} of {budget}\n"
            f"WHAT YOU'VE DONE:\n{done}\n"
            f"ACTIVE WINDOW: {screen.window or 'unknown'}\n"
            f"TEXT ON SCREEN (element: text @cell):\n{els}\n\n"
            "Your one line:")


_DECISION_RE = re.compile(r"(?i)^(do|fetch|action|ask|done|fail)\s*:\s*(.*)$")


def parse_decision(reply: str) -> tuple[str, str, dict] | None:
    """→ ("do", name, args) | ("ask"|"done"|"fail", text, {}) | None."""
    for raw in (reply or "").splitlines():
        line = raw.strip().strip("`*> -").strip()
        m = _DECISION_RE.match(line)
        if not m:
            continue
        kind, rest = m.group(1).lower(), m.group(2).strip()
        if kind in {"ask", "done", "fail"}:
            return kind, rest or kind, {}
        parts = rest.split(None, 1)
        if not parts:
            continue
        name = parts[0].strip().strip('"`,').lower()
        args: dict = {}
        if len(parts) > 1:
            try:
                parsed = json.loads(parts[1])
                if isinstance(parsed, dict):
                    args = parsed
            except Exception:  # noqa: BLE001
                pass
        return "do", name, args
    return None


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------
class Context(Protocol):
    def check(self) -> str | None: ...                    # reason to stop, or None
    def ask(self, question: str) -> bool: ...              # blocks until the phone answers
    def record(self, desc: str, ok: bool, result: str) -> None: ...
    def show(self, screen: Screen) -> None: ...            # latest screenshot for the phone


def run(goal: str, ctx: Context,
        capture_fn: Callable[[], Screen] = capture,
        vision_fn: Callable[..., str] | None = None,
        act_fn: Callable[[str, dict], tuple[bool, str]] = actions.run_action) -> tuple[str, str]:
    """Drive the laptop toward `goal`. → (status, reply); status is
    done | failed | stopped | cancelled."""
    if vision_fn is None:
        from core.ai_router import call_vision as vision_fn
    budget = max_steps()
    history: list[str] = []
    last_print = None
    stuck = 0

    for step in range(1, budget + 1):
        why = ctx.check()
        if why:
            return "stopped", why
        try:
            screen = capture_fn()
        except actions.Stopped:
            raise
        except Exception as e:  # noqa: BLE001
            return "failed", f"I couldn't take a screenshot of the laptop: {e}"
        ctx.show(screen)

        if last_print is not None and history:
            if screen.fingerprint == last_print:
                stuck += 1
                history[-1] += " (screen didn't change)"
                if stuck >= MAX_STUCK:
                    return "failed", "I'm stuck. The screen stopped changing, so I stopped before doing anything odd."
            else:
                stuck = 0
        last_print = screen.fingerprint

        reply = vision_fn(user_prompt(goal, screen, history, step, budget),
                          screen.model_jpeg_b64, system=system_prompt(screen), max_tokens=200)
        if reply in {"RATE_LIMIT", "CONNECTION_ERROR", "NO_VISION_KEY", "ERROR", ""}:
            return "failed", {
                "RATE_LIMIT": "My vision model is rate-limited right now. Try again in a minute.",
                "NO_VISION_KEY": "I don't have a vision model key on the laptop (OPENROUTER_KEY_CHAT).",
            }.get(reply, "I couldn't reach my vision model.")

        decision = parse_decision(reply)
        if decision is None:
            history.append("(you replied without a DO/ASK/DONE/FAIL line — reply with exactly one)")
            continue
        kind, a, args = decision
        if kind == "done":
            return "done", a
        if kind == "fail":
            return "failed", a
        if kind == "ask":
            if not ctx.ask(a):
                return "cancelled", "Okay, I stopped there and didn't do it."
            history.append(f"You asked “{a}” and he said yes.")
            continue

        name = a
        if name not in _VISION_ACTIONS:
            history.append(f"{name} → not an action you have")
            continue
        try:
            if name == "click":
                x, y = resolve_point(args, screen)
                run_args = {"x": x, "y": y, "button": args.get("button", "left"),
                            "clicks": args.get("clicks", 1)}
                el_id = _int(args.get("element"))
                el = next((e for e in screen.elements if e["id"] == el_id), None)
                desc = f"Click “{el['text']}”" if el else f"Click {args.get('cell')}"
            else:
                run_args = args
                desc = actions.describe(name, args)
        except actions.ActionError as e:
            history.append(f"{name} {json.dumps(args)} → {e}")
            continue

        if actions.risk_of(name, run_args) == "confirm" and not ctx.ask(f"OK to {desc[0].lower()}{desc[1:]}?"):
            return "cancelled", "Okay, I stopped there and didn't do it."

        ok, result = act_fn(name, run_args)
        ctx.record(desc, ok, result)
        history.append(f"{desc} → {'ok' if ok else result}")
        time.sleep(SETTLE_SECONDS)

    return "failed", f"I ran out of steps ({budget}) before finishing."


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def available() -> tuple[bool, str]:
    """Can the vision loop run here? (screenshot libs + a vision model key)."""
    if os.getenv("AURA_REMOTE_VISION", "auto").strip().lower() == "off":
        return False, "turned off (AURA_REMOTE_VISION=off)"
    try:
        import mss  # noqa: F401
        from PIL import Image  # noqa: F401
    except Exception:  # noqa: BLE001
        return False, "screenshot libraries missing (pip install mss Pillow)"
    try:
        from core.ai_router import vision_available
        if not vision_available():
            return False, "no vision model key"
    except Exception as e:  # noqa: BLE001
        return False, f"vision model unavailable ({e})"
    return True, ""
