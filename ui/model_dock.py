# ui/model_dock.py
"""
The model lock/unlock control row that sits above the cosmos.

One chip per model. Click a chip to toggle it:
  · UNLOCKED → chip glows in the model's color; planet orbits near the core.
  · LOCKED   → chip dims with a 🔒; planet drifts out to the edge, parked
               and unused.

Emits `lockChanged(name, locked)` so the cosmos can re-target that planet's
orbit. State is persisted by ui.model_lock, so this just reflects/toggles it.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton

from ui import theme
from core import model_lock
from ui.cosmos_panel import CosmosPanel


class ModelDock(QWidget):
    lockChanged = Signal(str, bool)   # (model name, is_locked)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._chips = {}   # name → (button, color)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 0, 2, 0)
        lay.setSpacing(8)

        caption = QLabel("MODELS")
        caption.setFont(theme.mono_font(8))
        caption.setStyleSheet(
            f"color: {theme.TEXT_DIM}; background: transparent; border: none;")
        lay.addWidget(caption)

        for name, _role, color, *_ in CosmosPanel.PLANETS:
            btn = QPushButton()
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(28)
            btn.clicked.connect(lambda _=False, n=name: self._toggle(n))
            self._chips[name] = (btn, color)
            lay.addWidget(btn)

        lay.addStretch()

        hint = QLabel("tap to lock · locked models idle at the edge")
        hint.setFont(theme.body_font(8))
        hint.setStyleSheet(
            f"color: {theme.TEXT_DIM}; background: transparent; border: none;")
        lay.addWidget(hint)

        self._refresh()

    def _toggle(self, name: str):
        locked = model_lock.toggle(name)
        self._style_chip(name)
        self.lockChanged.emit(name, locked)

    def _refresh(self):
        for name in self._chips:
            self._style_chip(name)

    def _style_chip(self, name: str):
        btn, color = self._chips[name]
        locked = model_lock.is_locked(name)
        if locked:
            btn.setText(f"🔒 {name}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(255,255,255,0.02);
                    border: 1px solid {theme.GLASS_BORDER};
                    border-radius: 14px;
                    color: {theme.TEXT_DIM};
                    padding: 0 12px; font-size: 11px;
                }}
                QPushButton:hover {{ border: 1px solid {theme.TEXT_SECONDARY};
                                     color: {theme.TEXT_SECONDARY}; }}
            """)
        else:
            btn.setText(f"●  {name}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(91,127,255,0.10);
                    border: 1px solid {color};
                    border-radius: 14px;
                    color: {theme.TEXT_PRIMARY};
                    padding: 0 12px; font-size: 11px;
                }}
                QPushButton:hover {{ background: rgba(91,127,255,0.20); }}
            """)
