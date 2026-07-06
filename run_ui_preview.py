# run_ui_preview.py
"""
Standalone preview of the new AURA main window with mock data.
Does NOT touch the existing app (main.py) — run this to iterate on
visuals only:

    python run_ui_preview.py

Hotkeys: 1 idle · 2 listening · 3 thinking · 4 speaking · 5 focus · 6 alert
"""

import sys

from PySide6.QtWidgets import QApplication

from ui.aura_window import AuraWindow
from ui.mock_driver import run_demo

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = AuraWindow(quit_on_close=True)
    win.resize(1280, 800)
    win.show()
    run_demo(win)
    sys.exit(app.exec())
