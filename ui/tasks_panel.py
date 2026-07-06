# aura_ui/tasks_panel.py
"""
Tasks panel — reads and writes through the same memory.store backend that
the chat command path ("add task ...") already uses, so a task added via
chat shows up here, and one added here shows up if you ask AURA about
your tasks. No separate task list, no separate state.

Row shape from memory.store (sqlite columns, in order):
    id | title | priority | status | created_at | done_at
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QLineEdit, QPushButton, QFrame, QCheckBox, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal

from ui.theme import (
    VOID_BLACK, NEBULA_PURPLE, EVENT_VIOLET, ACCRETION_BLUE, ION_CYAN,
    STARLIGHT_WHITE, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_DIM,
    panel_stylesheet, display_font, body_font, mono_font
)

COL_ID, COL_TITLE, COL_PRIORITY, COL_STATUS, COL_CREATED, COL_DONE = range(6)


class GlassPanel(QFrame):
    def __init__(self, radius=20, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QFrame {{ {panel_stylesheet(radius)} }}")


class TaskRow(QFrame):
    """A single task line: checkbox, title, delete button."""

    def __init__(self, task_row: tuple, on_toggle, on_delete, parent=None):
        super().__init__(parent)
        self._id = task_row[COL_ID]
        self._title = task_row[COL_TITLE]
        self._done = task_row[COL_STATUS] == "done"
        self._on_toggle = on_toggle
        self._on_delete = on_delete

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 10, 8)
        layout.setSpacing(10)

        self._checkbox = QCheckBox()
        self._checkbox.setChecked(self._done)
        self._checkbox.setCursor(Qt.PointingHandCursor)
        self._checkbox.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border: 1px solid {EVENT_VIOLET};
                border-radius: 4px;
                background: rgba(255,255,255,0.03);
            }}
            QCheckBox::indicator:checked {{
                background: {ACCRETION_BLUE};
                border-color: {ACCRETION_BLUE};
            }}
        """)
        self._checkbox.stateChanged.connect(self._toggle)
        layout.addWidget(self._checkbox)

        self._label = QLabel(self._title)
        self._label.setFont(body_font(13))
        self._label.setWordWrap(True)
        self._apply_label_style()
        layout.addWidget(self._label, stretch=1)

        delete_btn = QPushButton("✕")
        delete_btn.setFixedSize(24, 24)
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_DIM};
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                color: #ff5c6e;
                background: rgba(255, 92, 110, 0.1);
            }}
        """)
        delete_btn.clicked.connect(lambda: self._on_delete(self._id))
        layout.addWidget(delete_btn)

        self.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(255,255,255,0.03);
                border: 1px solid {EVENT_VIOLET};
                border-radius: 10px;
            }}
        """)

    def _apply_label_style(self):
        if self._done:
            self._label.setStyleSheet(f"color: {TEXT_DIM}; text-decoration: line-through;")
        else:
            self._label.setStyleSheet(f"color: {TEXT_PRIMARY};")

    def _toggle(self, _state):
        self._done = self._checkbox.isChecked()
        self._apply_label_style()
        self._on_toggle(self._id, self._done)


class TasksPanel(QWidget):
    """
    Full Tasks view — replaces chat in the center+right area when selected.
    Talks directly to memory.store; no internal task cache beyond what's
    needed to redraw rows after add/complete/delete.
    """

    countsChanged = Signal(int, int)   # (done, total) — feeds the stats chip

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

        # Live refresh while visible, so tasks added/completed via chat
        # ("add task ...") show up here without reopening the panel.
        self._auto_refresh = QTimer(self)
        self._auto_refresh.timeout.connect(
            lambda: self.refresh() if self.isVisible() else None
        )
        self._auto_refresh.start(5000)

    def showEvent(self, event):
        self.refresh()
        super().showEvent(event)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        panel = GlassPanel(radius=20)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        header = QLabel("Tasks")
        header.setFont(display_font(18))
        header.setStyleSheet(f"color: {TEXT_PRIMARY};")
        header_row.addWidget(header)
        header_row.addStretch()

        self._summary_label = QLabel("")
        self._summary_label.setFont(mono_font(11))
        self._summary_label.setStyleSheet(f"color: {TEXT_DIM};")
        header_row.addWidget(self._summary_label)
        layout.addLayout(header_row)

        layout.addWidget(self._build_add_row())

        self._list_scroll = QScrollArea()
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setStyleSheet("background: transparent; border: none;")
        self._list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        list_container = QWidget()
        list_container.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(list_container)
        self._list_layout.setSpacing(8)
        self._list_layout.addStretch()
        self._list_scroll.setWidget(list_container)

        layout.addWidget(self._list_scroll, stretch=1)
        outer.addWidget(panel, stretch=1)

    def _build_add_row(self) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        self._add_input = QLineEdit()
        self._add_input.setPlaceholderText("Add a task...")
        self._add_input.setFont(body_font(13))
        self._add_input.setFixedHeight(38)
        self._add_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: rgba(255,255,255,0.04);
                border: 1px solid {EVENT_VIOLET};
                border-radius: 10px;
                padding: 0 14px;
                color: {TEXT_PRIMARY};
            }}
            QLineEdit:focus {{ border: 1px solid {ACCRETION_BLUE}; }}
        """)
        self._add_input.returnPressed.connect(self._on_add)

        add_btn = QPushButton("Add")
        add_btn.setFixedSize(64, 38)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCRETION_BLUE};
                color: {VOID_BLACK};
                border: none;
                border-radius: 10px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {ION_CYAN}; }}
        """)
        add_btn.clicked.connect(self._on_add)

        row_layout.addWidget(self._add_input, stretch=1)
        row_layout.addWidget(add_btn)
        return row

    # ── Backend calls ───────────────────────────────────────────────────
    def _on_add(self):
        title = self._add_input.text().strip()
        if not title:
            return
        from memory.store import add_task
        add_task(title)
        self._add_input.clear()
        self.refresh()

    def _on_toggle(self, task_id: int, done: bool):
        from memory.store import complete_task, uncomplete_task
        if done:
            complete_task(task_id)
        else:
            uncomplete_task(task_id)
        self.refresh()

    def _on_delete(self, task_id: int):
        from memory.store import delete_task
        delete_task(task_id)
        self.refresh()

    # ── Render ────────────────────────────────────────────────────────────
    def refresh(self):
        from memory.store import get_tasks

        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        rows = get_tasks()
        pending_count = sum(1 for r in rows if r[COL_STATUS] != "done")
        done_count = len(rows) - pending_count
        self._summary_label.setText(f"{pending_count} pending · {done_count} done")
        self.countsChanged.emit(done_count, len(rows))

        if not rows:
            empty = QLabel("No tasks yet. Add one above, or just tell AURA.")
            empty.setFont(body_font(12))
            empty.setStyleSheet(f"color: {TEXT_DIM};")
            empty.setWordWrap(True)
            self._list_layout.insertWidget(0, empty)
            return

        # Pending first, then done — already ordered that way by
        # get_tasks()'s "status DESC" when called with no filter is NOT
        # guaranteed ('pending' vs 'done' DESC sorts done before pending
        # alphabetically reversed), so sort explicitly here instead of
        # relying on the SQL ordering.
        ordered = sorted(rows, key=lambda r: r[COL_STATUS] == "done")
        for i, task_row in enumerate(ordered):
            row_widget = TaskRow(task_row, self._on_toggle, self._on_delete)
            self._list_layout.insertWidget(i, row_widget)