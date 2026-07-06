# aura_ui/theme.py
"""
Shared design tokens for the AURA dashboard — palette, fonts, and the
glassmorphism panel style, kept in one place so every widget draws
from the same system instead of redefining colors inline.
"""

from PySide6.QtGui import QColor, QFont, QFontDatabase

# ── Palette (named for what they represent, not generic primary/accent) ──
VOID_BLACK      = "#05030D"   # window background, deep space
NEBULA_PURPLE   = "#1A1033"   # panel glass tint base
EVENT_VIOLET    = "#3D2B7A"   # borders, idle accents, mid-tone glow
ACCRETION_BLUE  = "#5B7FFF"   # listening state, links, active accents
ION_CYAN        = "#7FE8FF"   # speaking state, bright highlights
STARLIGHT_WHITE = "#F5F3FF"   # primary text, speaking core

TEXT_PRIMARY    = "#F5F3FF"
TEXT_SECONDARY  = "#A8A0C8"   # muted lavender-grey for secondary text
TEXT_DIM        = "#6B6490"   # timestamps, placeholders

# ── State colors (design philosophy: orb = emotion) ─────────────────────
IDLE_PURPLE     = "#8B3DFF"   # idle accent — black hole with purple ring
THINKING_SILVER = "#C9CCD8"   # white hole, breathing
SPEAKING_WHITE  = "#EAF2FF"   # speaking pulse
FOCUS_GREEN     = "#3DDC97"   # focus mode, stable minimal energy
ALERT_ORANGE    = "#FF7A3D"   # alerts — never full red
ERROR_RED       = "#FF4D5E"   # small accents only, never a full red orb

STATE_ACCENTS = {
    "idle":      IDLE_PURPLE,
    "listening": ACCRETION_BLUE,
    "thinking":  THINKING_SILVER,
    "speaking":  SPEAKING_WHITE,
    "focus":     FOCUS_GREEN,
    "alert":     ALERT_ORANGE,
}

# ── Model planet colors (from AI model indicator spec) ───────────────────
MODEL_COLORS = {
    "GPT-4o":       "#8B3DFF",  # purple
    "Gemini 1.5":   "#4D8DFF",  # blue
    "Claude 3.5":   "#E8E6F0",  # white/silver
    "Grok 2":       "#FF7A3D",  # orange
    "Local (LLM)":  "#FF4D5E",  # red
}

GLASS_BG        = "rgba(26, 16, 51, 0.55)"
GLASS_BORDER    = "rgba(125, 127, 255, 0.18)"


def panel_stylesheet(radius: int = 16) -> str:
    return f"""
        background-color: {GLASS_BG};
        border: 1px solid {GLASS_BORDER};
        border-radius: {radius}px;
    """


FONT_DISPLAY = "Space Grotesk"
FONT_BODY    = "Inter"
FONT_MONO    = "JetBrains Mono"


def resolve_font_family(preferred: str, fallback: str) -> str:
    """Falls back gracefully if the preferred font isn't installed on
    this machine, instead of silently rendering with a mismatched
    system default that breaks the type hierarchy."""
    available = QFontDatabase.families()
    return preferred if preferred in available else fallback


def display_font(size: int = 16, weight: int = QFont.DemiBold) -> QFont:
    family = resolve_font_family(FONT_DISPLAY, "Segoe UI")
    f = QFont(family, size)
    f.setWeight(weight)
    return f


def body_font(size: int = 13, weight: int = QFont.Normal) -> QFont:
    family = resolve_font_family(FONT_BODY, "Segoe UI")
    f = QFont(family, size)
    f.setWeight(weight)
    return f


def mono_font(size: int = 11) -> QFont:
    family = resolve_font_family(FONT_MONO, "Consolas")
    return QFont(family, size)