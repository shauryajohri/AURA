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
    except:
        return "unknown"

def take_screenshot():
    if mss is None or Image is None:
        raise RuntimeError("screen capture dependencies are not installed")

    with mss.mss() as sct:
        monitor = sct.monitors[1]
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
        return img

def extract_text_from_screen() -> str:
    if pytesseract is None:
        return ""

    try:
        img = take_screenshot()
        # resize for faster OCR
        img = img.resize((img.width // 2, img.height // 2))
        text = pytesseract.image_to_string(img)
        # clean up
        text = ' '.join(text.split())
        return text[:1000]  # limit to 1000 chars
    except Exception as e:
        print(f"[AURA Screen] OCR error: {e}")
        return ""

def get_clipboard() -> str:
    if pyperclip is None:
        return ""

    try:
        return pyperclip.paste()[:500]
    except:
        return ""

def get_screen_context() -> dict:
    return {
        "app": get_active_window(),
        "visible_text": extract_text_from_screen(),
        "clipboard": get_clipboard()
    }
