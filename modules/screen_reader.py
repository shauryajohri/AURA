import pygetwindow as gw
import mss
import pytesseract
from PIL import Image
import pyperclip
import os

# tesseract path
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def get_active_window() -> str:
    try:
        win = gw.getActiveWindow()
        if win:
            return win.title
        return "unknown"
    except:
        return "unknown"

def take_screenshot() -> Image.Image:
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
        return img

def extract_text_from_screen() -> str:
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