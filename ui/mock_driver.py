# ui/mock_driver.py
"""
Scripted demo that makes the UI feel alive without the brain attached:
plays through a realistic conversation, moves presence states, drops a
plan card, starts a focus session, and fires a reminder toast.

Purely additive — delete this file (and its import in run_ui_preview.py)
once the real event_bus is wired in.
"""

from PySide6.QtCore import QTimer

from ui.aura_window import AuraWindow
from ui.state import AuraState


def run_demo(win: AuraWindow):
    bus, chat = win.bus, win.chat

    plan = [
        ("11:00 AM", "Internship Work", True),
        ("02:00 PM", "DSA Practice", True),
        ("05:30 PM", "Qt Learning", False),
        ("08:00 PM", "Japanese Study", False),
    ]

    script = [
        (400,  lambda: bus.set_state(AuraState.SPEAKING)),
        (600,  lambda: chat.add_message(
            "Good evening, Shaurya! 🌙\nWhat shall we accomplish today?",
            "AURA", "10:42 PM")),
        (1600, lambda: bus.set_state(AuraState.IDLE)),
        (2400, lambda: chat.add_message(
            "What's on my plan for today?", "You", "10:42 PM")),
        (2500, lambda: bus.set_state(AuraState.THINKING)),
        (3600, lambda: bus.set_state(AuraState.SPEAKING)),
        (3700, lambda: chat.add_message(
            "Here's your plan for today:", "AURA", "10:42 PM")),
        (3800, lambda: chat.add_plan_card(plan)),
        (4000, lambda: chat.add_message(
            "Would you like me to start with the next task?",
            "AURA", "10:42 PM")),
        (5000, lambda: bus.set_state(AuraState.LISTENING)),
        (6000, lambda: chat.add_message(
            "Yes, start DSA practice.", "You", "10:43 PM")),
        (6100, lambda: bus.set_state(AuraState.THINKING)),
        (7200, lambda: bus.set_state(AuraState.SPEAKING)),
        (7300, lambda: chat.add_message(
            "Alright! Opening your DSA sheet and setting a 90-minute "
            "focus timer.", "AURA", "10:43 PM")),
        (7500, lambda: chat.add_focus_card(
            "Focus Session Started", "Ends at 03:30 PM")),
        (8200, lambda: bus.set_state(AuraState.FOCUS)),
        (9500, lambda: chat.show_reminder(
            "You planned to revise arrays today. Shall I set a reminder "
            "for 7 PM?")),
    ]

    for delay, action in script:
        QTimer.singleShot(delay, action)
