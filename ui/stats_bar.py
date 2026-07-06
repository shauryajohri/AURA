# ui/stats_bar.py
"""
Bottom strip: encouragement message + Focus Time / Completed Tasks /
Productivity chips. Values are mock for now; set_* methods exist so the
brain can feed real numbers later.
"""

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui import theme
from ui.widgets import GlassPanel


class _StatChip(GlassPanel):
    def __init__(self, icon: str, label: str, value: str, accent: str, parent=None):
        super().__init__(radius=12, parent=parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 8, 16, 8)
        lay.setSpacing(10)
        ic = QLabel(icon)
        ic.setFont(theme.display_font(13))
        ic.setStyleSheet(f"color: {accent}; background: transparent; border: none;")
        col = QVBoxLayout()
        col.setSpacing(0)
        lab = QLabel(label)
        lab.setFont(theme.body_font(8))
        lab.setStyleSheet(
            f"color: {theme.TEXT_DIM}; background: transparent; border: none;")
        self.value = QLabel(value)
        self.value.setFont(theme.display_font(12))
        self.value.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; background: transparent; border: none;")
        col.addWidget(lab)
        col.addWidget(self.value)
        lay.addWidget(ic)
        lay.addLayout(col)


class StatsBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        note_panel = GlassPanel(radius=12)
        note_lay = QHBoxLayout(note_panel)
        note_lay.setContentsMargins(16, 10, 16, 10)
        self.note = QLabel("Take breaks. You're doing great. I'm proud of you. 💜")
        self.note.setFont(theme.body_font(10))
        self.note.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; background: transparent; border: none;")
        note_lay.addWidget(self.note)
        lay.addWidget(note_panel, 1)

        self.model_chip = _StatChip("⚛", "Model", "—", theme.ION_CYAN)
        self.focus_chip = _StatChip("◷", "Focus Time", "2h 15m", theme.FOCUS_GREEN)
        self.tasks_chip = _StatChip("✓", "Completed Tasks", "0/0", theme.ACCRETION_BLUE)
        self.prod_chip = _StatChip("✦", "Productivity", "78%", theme.IDLE_PURPLE)
        lay.addWidget(self.model_chip)
        lay.addWidget(self.focus_chip)
        lay.addWidget(self.tasks_chip)
        lay.addWidget(self.prod_chip)

    # future brain hooks
    def set_model(self, text: str):
        self.model_chip.value.setText(text)

    def set_focus_time(self, text: str):
        self.focus_chip.value.setText(text)

    def set_tasks(self, text: str):
        self.tasks_chip.value.setText(text)

    def set_productivity(self, text: str):
        self.prod_chip.value.setText(text)

    def set_note(self, text: str):
        self.note.setText(text)
