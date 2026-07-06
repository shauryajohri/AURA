"""
AURA UI — Execution Plan Panel
A PySide6 widget that shows the AURA execution plan and waits for user approval.

Drop this into your existing ui/ folder and integrate with AuraAppController.

Integration in app.py:
    from ui.execution_plan_panel import ExecutionPlanPanel
    # In your main window setup:
    self.plan_panel = ExecutionPlanPanel()
    self.plan_panel.approved.connect(self._on_plan_approved)
    self.plan_panel.rejected.connect(self._on_plan_rejected)
    self.plan_panel.edited.connect(self._on_plan_edited)
    layout.addWidget(self.plan_panel)  # or show as a sliding panel
"""

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QRect
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSizePolicy, QSpacerItem,
    QGraphicsOpacityEffect,
)


# ---------------------------------------------------------------------------
# Colour palette — matches a dark AURA aesthetic
# ---------------------------------------------------------------------------

COLORS = {
    "bg":           "#0f0f13",
    "surface":      "#17171f",
    "surface_hi":   "#1f1f2e",
    "border":       "#2a2a3d",
    "accent":       "#6c63ff",      # purple
    "accent_dim":   "#3d3870",
    "success":      "#3ddc97",
    "muted":        "#6b6b8a",
    "text":         "#e8e8f0",
    "text_dim":     "#8888a8",
    "warning":      "#f0a500",
    "danger":       "#ff5c6e",
    "step_done":    "#3ddc97",
    "step_pending": "#6b6b8a",
}

STYLESHEET = f"""
QWidget {{
    background: {COLORS['bg']};
    color: {COLORS['text']};
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
    font-size: 13px;
}}

#planPanel {{
    background: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 12px;
}}

#panelHeader {{
    background: {COLORS['surface_hi']};
    border-bottom: 1px solid {COLORS['border']};
    border-radius: 12px 12px 0 0;
    padding: 14px 18px;
}}

#headerTitle {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
    color: {COLORS['accent']};
}}

#goalLabel {{
    font-size: 16px;
    font-weight: 600;
    color: {COLORS['text']};
    padding: 16px 18px 4px 18px;
}}

#metaRow {{
    padding: 0 18px 12px 18px;
}}

#metaBadge {{
    background: {COLORS['accent_dim']};
    color: {COLORS['accent']};
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}

#sectionLabel {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    color: {COLORS['muted']};
    padding: 10px 18px 6px 18px;
}}

#stepWidget {{
    margin: 2px 14px;
    padding: 10px 14px;
    border-radius: 8px;
    background: {COLORS['bg']};
    border: 1px solid {COLORS['border']};
}}

#stepWidget[done="true"] {{
    border-color: {COLORS['success']}44;
    background: {COLORS['success']}08;
}}

#stepIcon[done="true"] {{
    color: {COLORS['success']};
    font-size: 14px;
}}

#stepIcon[done="false"] {{
    color: {COLORS['step_pending']};
    font-size: 14px;
}}

#stepTitle {{
    font-weight: 600;
    font-size: 13px;
}}

#stepDesc {{
    color: {COLORS['text_dim']};
    font-size: 12px;
}}

#fileChip {{
    background: {COLORS['surface_hi']};
    border: 1px solid {COLORS['border']};
    border-radius: 5px;
    padding: 3px 10px;
    font-size: 11px;
    font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
    color: {COLORS['text_dim']};
}}

#costRow {{
    padding: 8px 18px 14px 18px;
}}

#modelLabel {{
    font-size: 12px;
    color: {COLORS['text_dim']};
}}

#modelValue {{
    font-size: 12px;
    font-weight: 600;
    color: {COLORS['warning']};
}}

#costLabel {{
    font-size: 12px;
    color: {COLORS['text_dim']};
}}

#costValue {{
    font-size: 12px;
    font-weight: 600;
    color: {COLORS['success']};
}}

#divider {{
    background: {COLORS['border']};
    max-height: 1px;
    margin: 0 18px;
}}

#btnApprove {{
    background: {COLORS['accent']};
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 24px;
    font-size: 13px;
    font-weight: 600;
    min-width: 100px;
}}
#btnApprove:hover {{
    background: #7c74ff;
}}
#btnApprove:pressed {{
    background: {COLORS['accent_dim']};
}}

#btnEdit {{
    background: transparent;
    color: {COLORS['text_dim']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: 500;
}}
#btnEdit:hover {{
    border-color: {COLORS['accent']};
    color: {COLORS['text']};
}}

#btnCancel {{
    background: transparent;
    color: {COLORS['danger']};
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 13px;
}}
#btnCancel:hover {{
    border-color: {COLORS['danger']};
}}

#actionRow {{
    padding: 14px 18px 18px 18px;
}}
"""


# ---------------------------------------------------------------------------
# Step widget
# ---------------------------------------------------------------------------

class StepWidget(QFrame):
    def __init__(self, index: int, title: str, description: str, done: bool = False):
        super().__init__()
        self.setObjectName("stepWidget")
        self.setProperty("done", str(done).lower())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        icon = QLabel("✓" if done else "○")
        icon.setObjectName("stepIcon")
        icon.setProperty("done", str(done).lower())
        icon.setFixedWidth(20)
        icon.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(icon)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        title_lbl = QLabel(f"{index}. {title}")
        title_lbl.setObjectName("stepTitle")
        text_col.addWidget(title_lbl)

        desc_lbl = QLabel(description)
        desc_lbl.setObjectName("stepDesc")
        desc_lbl.setWordWrap(True)
        text_col.addWidget(desc_lbl)

        layout.addLayout(text_col)


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------

class ExecutionPlanPanel(QWidget):
    """
    Signals:
        approved(summary: dict)  — user clicked Approve
        edited(summary: dict)    — user clicked Edit (open edit dialog)
        rejected()               — user clicked Cancel
    """
    approved = Signal(dict)
    edited = Signal(dict)
    rejected = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._summary: dict = {}
        self.setStyleSheet(STYLESHEET)
        self.hide()

    def show_plan(self, summary: dict):
        """
        Call this with the dict from EngineResult.summary_dict()
        to display the panel. Renders as a centered overlay card on top
        of the parent window (docking it into a column layout squeezed
        every row into invisible slivers).
        """
        self._summary = summary
        self._build_ui(summary)

        parent = self.parentWidget()
        if parent is not None:
            width = min(620, max(420, parent.width() - 240))
            self.setFixedWidth(width)
            self.setMaximumHeight(parent.height() - 120)
            self.adjustSize()
            self.move(
                (parent.width() - self.width()) // 2,
                (parent.height() - self.height()) // 2,
            )
        self.show()
        self.raise_()

    def _build_ui(self, s: dict):
        outer = self.layout()
        if outer is None:
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
        else:
            while outer.count():
                item = outer.takeAt(0)
                widget = item.widget()
                child_layout = item.layout()
                if widget:
                    widget.deleteLater()
                elif child_layout:
                    self._clear_layout(child_layout)

        panel = QFrame()
        panel.setObjectName("planPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # --- Header ---
        header = QFrame()
        header.setObjectName("panelHeader")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(18, 12, 18, 12)
        title_lbl = QLabel("AURA EXECUTION PLAN")
        title_lbl.setObjectName("headerTitle")
        h_layout.addWidget(title_lbl)
        h_layout.addStretch()

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(24, 24)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(
            f"""
            QPushButton {{ background: transparent; border: none;
                           color: {COLORS['text_dim']}; font-size: 12px;
                           border-radius: 6px; }}
            QPushButton:hover {{ color: {COLORS['danger']};
                                 background: rgba(255, 92, 110, 0.12); }}
            """
        )
        btn_close.clicked.connect(self._on_cancel)   # close = cancel the plan
        h_layout.addWidget(btn_close)
        panel_layout.addWidget(header)

        # --- Goal ---
        goal_lbl = QLabel(s.get("goal", ""))
        goal_lbl.setObjectName("goalLabel")
        goal_lbl.setWordWrap(True)
        panel_layout.addWidget(goal_lbl)

        # --- Meta badges ---
        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(18, 0, 18, 12)
        meta_row.setSpacing(8)
        for text in [s.get("domain", ""), s.get("project", ""), s.get("complexity_label", "")]:
            if text:
                badge = QLabel(text)
                badge.setObjectName("metaBadge")
                meta_row.addWidget(badge)
        meta_row.addStretch()
        panel_layout.addLayout(meta_row)

        # --- Divider ---
        div = QFrame()
        div.setObjectName("divider")
        div.setFrameShape(QFrame.Shape.HLine)
        panel_layout.addWidget(div)

        # --- Steps ---
        steps_label = QLabel("STEPS")
        steps_label.setObjectName("sectionLabel")
        panel_layout.addWidget(steps_label)

        for step in s.get("steps", []):
            sw = StepWidget(
                index=step["index"],
                title=step["title"],
                description="",
                done=step.get("done", False),
            )
            panel_layout.addWidget(sw)

        # --- Files affected ---
        files = s.get("files_affected", [])
        if files:
            files_label = QLabel("FILES LIKELY AFFECTED")
            files_label.setObjectName("sectionLabel")
            panel_layout.addWidget(files_label)

            file_row = QHBoxLayout()
            file_row.setContentsMargins(18, 0, 18, 8)
            file_row.setSpacing(6)
            for f in files:
                chip = QLabel(f)
                chip.setObjectName("fileChip")
                file_row.addWidget(chip)
            file_row.addStretch()
            panel_layout.addLayout(file_row)

        # --- Divider ---
        div2 = QFrame()
        div2.setObjectName("divider")
        div2.setFrameShape(QFrame.Shape.HLine)
        panel_layout.addWidget(div2)

        # --- Model + Cost ---
        cost_row = QHBoxLayout()
        cost_row.setContentsMargins(18, 10, 18, 14)
        cost_row.setSpacing(20)

        model_lbl = QLabel("Model:")
        model_lbl.setObjectName("modelLabel")
        cost_row.addWidget(model_lbl)
        model_val = QLabel(s.get("model", "Claude"))
        model_val.setObjectName("modelValue")
        cost_row.addWidget(model_val)

        cost_lbl = QLabel("Est. Cost:")
        cost_lbl.setObjectName("costLabel")
        cost_row.addWidget(cost_lbl)
        cost_val = QLabel(s.get("estimated_cost", "~$0.03"))
        cost_val.setObjectName("costValue")
        cost_row.addWidget(cost_val)

        cost_row.addStretch()
        panel_layout.addLayout(cost_row)

        # --- Action buttons ---
        div3 = QFrame()
        div3.setObjectName("divider")
        div3.setFrameShape(QFrame.Shape.HLine)
        panel_layout.addWidget(div3)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(18, 14, 18, 18)
        action_row.setSpacing(8)

        btn_approve = QPushButton("▶  Approve")
        btn_approve.setObjectName("btnApprove")
        btn_approve.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_approve.clicked.connect(self._on_approve)

        btn_edit = QPushButton("✎  Edit Plan")
        btn_edit.setObjectName("btnEdit")
        btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_edit.clicked.connect(self._on_edit)

        btn_cancel = QPushButton("✕  Cancel")
        btn_cancel.setObjectName("btnCancel")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self._on_cancel)

        action_row.addWidget(btn_approve)
        action_row.addWidget(btn_edit)
        action_row.addStretch()
        action_row.addWidget(btn_cancel)
        panel_layout.addLayout(action_row)

        outer.addWidget(panel)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget:
                widget.deleteLater()
            elif child_layout:
                self._clear_layout(child_layout)
        layout.deleteLater()

    def _on_approve(self):
        self.hide()
        self.approved.emit(self._summary)

    def _on_edit(self):
        self.edited.emit(self._summary)

    def _on_cancel(self):
        self.hide()
        self.rejected.emit()
