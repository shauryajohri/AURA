import os

try:
    import pygetwindow as gw
except ModuleNotFoundError:
    gw = None

try:
    import mss
except ModuleNotFoundError:
    mss = None

try:
    import pytesseract
except ModuleNotFoundError:
    pytesseract = None

try:
    from PIL import Image
except ModuleNotFoundError:
    Image = None

try:
    import pyperclip
except ModuleNotFoundError:
    pyperclip = None

# tesseract path
if pytesseract is not None:
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def get_active_window() -> str:
    if gw is None:
        return "unknown"

    try:
        win = gw.getActiveWindow()
        if win:
            return win.title
        return "unknown"
    except Exception:
        return "unknown"


def list_window_titles() -> list:
    """All open window titles (lowercased, non-empty). Used to detect ambient
    context like a music player or a meeting app being open in the background."""
    if gw is None:
        return []
    try:
        return [w.title.lower() for w in gw.getAllWindows() if w.title and w.title.strip()]
    except Exception:
        return []
# Common shorthand people use when naming apps out loud; extend as needed.
WINDOW_NAME_ALIASES = {
    "vs": "visual studio code",
    "vscode": "visual studio code",
    "vs code": "visual studio code",
    "chrome": "google chrome",
}

def find_window(name_fragment: str):
    """Find an open window whose title contains name_fragment, case-insensitive,
    regardless of whether it's currently focused. Checks common spoken
    shorthand (e.g. "vs" -> "visual studio code") before a direct match."""
    if gw is None:
        return None

    name_fragment = name_fragment.lower().strip()
    candidates = [WINDOW_NAME_ALIASES.get(name_fragment, name_fragment), name_fragment]

    try:
        windows = gw.getAllWindows()
    except Exception:
        return None

    for candidate in candidates:
        for win in windows:
            if win.title and candidate in win.title.lower():
                return win
    return None


# Tracks what Aura is currently doing, so it can answer "what are you doing?"
_current_focus = {"app": None, "action": None}

def set_current_focus(app: str, action: str):
    _current_focus["app"] = app
    _current_focus["action"] = action

def describe_current_focus() -> str:
    if _current_focus["app"]:
        return f"I'm currently {_current_focus['action']} in {_current_focus['app']}."
    return f"I'm just keeping an eye on what you're doing — right now that's {get_active_window()}."

def take_screenshot(window=None):
    if mss is None or Image is None:
        raise RuntimeError("screen capture dependencies are not installed")

    with mss.mss() as sct:
        if window is not None:
            if window.isMinimized:
                window.restore()
            region = {"left": window.left, "top": window.top,
                      "width": window.width, "height": window.height}
        else:
            region = sct.monitors[1]

        screenshot = sct.grab(region)
        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
        return img

def extract_text_from_screen(window=None) -> str:
    if pytesseract is None:
        return ""

    try:
        img = take_screenshot(window)
        img = img.resize((img.width // 2, img.height // 2))
        text = pytesseract.image_to_string(img)
        text = ' '.join(text.split())
        return text[:1000]
    except Exception as e:
        # Tesseract failures dump a wall of internal diagnostics — keep one line.
        msg = " ".join(str(e).split())
        print(f"[AURA Screen] OCR error: {msg[:120]}{'…' if len(msg) > 120 else ''}")
        return ""

def get_clipboard() -> str:
    if pyperclip is None:
        return ""

    try:
        return pyperclip.paste()[:500]
    except:
        return ""

_OWN_WINDOW_MARKERS = ("aura", "prime core online")
_last_external = {"app": "unknown", "visible_text": "", "ts": 0.0}
_EXTERNAL_STALE_SECONDS = 600   # forget what was on screen after 10 min


def get_screen_context(target_app_name: str = None) -> dict:
    import time as _t
    window = find_window(target_app_name) if target_app_name else None
    app = window.title if window else get_active_window()
    visible = extract_text_from_screen(window)

    app_low = (app or "").lower()
    if any(m in app_low for m in _OWN_WINDOW_MARKERS):
        # Focused window is AURA itself. Its own chat text must NEVER be fed
        # back as "the user's screen" — it read its own UI and hallucinated a
        # "keyboard mishap" from the user's rendered message. Report the last
        # real app instead (blanked if too old).
        stale = (_t.time() - _last_external["ts"]) > _EXTERNAL_STALE_SECONDS
        return {
            "app": "unknown" if stale else _last_external["app"],
            "visible_text": "" if stale else _last_external["visible_text"],
            "clipboard": get_clipboard(),
            "note": "user is focused on the AURA window (talking to you)",
        }

    _last_external["app"] = app
    _last_external["visible_text"] = visible or ""
    _last_external["ts"] = _t.time()
    return {"app": app, "visible_text": visible, "clipboard": get_clipboard()}
