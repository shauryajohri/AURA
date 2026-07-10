# ui/memory_panel.py
"""
Memory panel — a window into everything AURA has chosen to remember, and
the place to curate it.

Three sections, all reading/writing the same memory.store backend the rest
of AURA uses (so a fact captured mid-conversation shows up here, and a fact
you delete here is gone from future prompts):

  1. What AURA knows about you  — durable user_facts. Fully editable:
     add, edit-in-place, delete. This is the memory that gets injected into
     every reply, so it's the one worth curating.
  2. Saved notes                — the knowledge table (things you asked AURA
     to save). View + delete.
  3. Session history            — the "last time you were..." recaps. View +
     delete.

AURA still decides what to auto-save (see modules/fact_extractor); this panel
is the "editable after" half of that deal.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QLineEdit, QPushButton, QFrame,
)
from PySide6.QtCore import Qt, QTimer

from ui.theme import (
    VOID_BLACK, EVENT_VIOLET, ACCRETION_BLUE, ION_CYAN,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_DIM,
    panel_stylesheet, display_font, body_font, mono_font,
)


class GlassPanel(QFrame):
    def __init__(self, radius=20, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"QFrame {{ {panel_stylesheet(radius)} }}")


def _delete_button(on_click) -> QPushButton:
    btn = QPushButton("✕")
    btn.setFixedSize(24, 24)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: transparent; color: {TEXT_DIM};
            border: none; border-radius: 4px; font-size: 12px;
        }}
        QPushButton:hover {{ color: #ff5c6e; background: rgba(255,92,110,0.1); }}
    """)
    btn.clicked.connect(on_click)
    return btn


class FactRow(QFrame):
    """One durable fact: an inline-editable field + delete. The field saves
    on Enter or when it loses focus, so editing feels like editing a note."""

    def __init__(self, fact_id: int, fact: str, category: str,
                 on_edit, on_delete, parent=None):
        super().__init__(parent)
        self._id = fact_id
        self._original = fact
        self._on_edit = on_edit
        self._on_delete = on_delete

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 10, 6)
        layout.setSpacing(10)

        if category:
            tag = QLabel(category.upper())
            tag.setFont(mono_font(7))
            tag.setFixedWidth(64)
            tag.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; border: none;")
            layout.addWidget(tag)

        self._field = QLineEdit(fact)
        self._field.setFont(body_font(13))
        self._field.setStyleSheet(f"""
            QLineEdit {{
                background: transparent; border: none;
                color: {TEXT_PRIMARY}; padding: 4px 2px;
            }}
            QLineEdit:focus {{
                background: rgba(255,255,255,0.04);
                border-radius: 6px;
            }}
        """)
        self._field.editingFinished.connect(self._commit)
        layout.addWidget(self._field, stretch=1)

        layout.addWidget(_delete_button(lambda: self._on_delete(self._id)))

        self.setStyleSheet(f"""QFrame {{
                background-color: rgba(255,255,255,0.03);
                border: 1px solid {EVENT_VIOLET};
                border-radius: 10px;
            }}
        """)

    def _commit(self):
        new = self._field.text().strip()
        if new and new != self._original:
            self._original = new
            self._on_edit(self._id, new)


class ReadRow(QFrame):
    """A read-only memory row (note or session recap): title + subtext + delete."""

    def __init__(self, entry_id: int, title: str, subtitle: str,
                 on_delete, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 10, 8)
        layout.setSpacing(10)

        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title or "(untitled)")
        t.setFont(body_font(13))
        t.setWordWrap(True)
        t.setStyleSheet(f"color: {TEXT_PRIMARY}; background: transparent; border: none;")
        col.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setFont(body_font(10))
            s.setWordWrap(True)
            s.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; border: none;")
            col.addWidget(s)
        layout.addLayout(col, stretch=1)

        layout.addWidget(_delete_button(lambda: on_delete(entry_id)))

        self.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(255,255,255,0.03);
                border: 1px solid {EVENT_VIOLET};
                border-radius: 10px;
            }}
        """)


class _Section(QWidget):
    """A titled list block with an optional count."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        head = QHBoxLayout()
        self._title = QLabel(title)
        self._title.setFont(display_font(13))
        self._title.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent;")
        head.addWidget(self._title)
        head.addStretch()
        self._count = QLabel("")
        self._count.setFont(mono_font(10))
        self._count.setStyleSheet(f"color: {TEXT_DIM}; background: transparent;")
        head.addWidget(self._count)
        lay.addLayout(head)

        self._base_title = title
        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        lay.addLayout(self.body)

    def set_count(self, n: int):
        self._count.setText(str(n))

    def clear(self):
        while self.body.count():
            item = self.body.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def add(self, widget: QWidget):
        self.body.addWidget(widget)

    def add_empty(self, text: str):
        lbl = QLabel(text)
        lbl.setFont(body_font(11))
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {TEXT_DIM}; background: transparent; border: none;")
        self.body.addWidget(lbl)


class MemoryPanel(QWidget):
    """Full Memory view — swaps into the center stack when 'Memory' nav is
    selected. Talks directly to memory.store."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

        # Light auto-refresh so facts captured during a conversation appear
        # here without leaving and re-entering the panel.
        self._auto = QTimer(self)
        self._auto.timeout.connect(lambda: self.refresh() if self.isVisible() else None)
        self._auto.start(6000)

    def showEvent(self, event):
        self.refresh()
        super().showEvent(event)

    # ── UI ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        panel = GlassPanel(radius=20)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        header_row = QHBoxLayout()
        header = QLabel("Memory")
        header.setFont(display_font(18))
        header.setStyleSheet(f"color: {TEXT_PRIMARY};")
        header_row.addWidget(header)
        header_row.addStretch()
        sub = QLabel("What AURA remembers — edit freely")
        sub.setFont(mono_font(10))
        sub.setStyleSheet(f"color: {TEXT_DIM};")
        header_row.addWidget(sub)
        layout.addLayout(header_row)

        # Add-a-fact row (facts are the curated, injected memory)
        layout.addWidget(self._build_add_row())

        # Scrollable stack of the three sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        stack = QVBoxLayout(container)
        stack.setContentsMargins(0, 0, 4, 0)
        stack.setSpacing(18)

        self._facts_section = _Section("What AURA knows about you")
        self._notes_section = _Section("Saved notes")
        self._sessions_section = _Section("Session history")
        stack.addWidget(self._facts_section)
        stack.addWidget(self._notes_section)
        stack.addWidget(self._sessions_section)
        stack.addStretch()

        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)
        outer.addWidget(panel, stretch=1)

    def _build_add_row(self) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        self._add_input = QLineEdit()
        self._add_input.setPlaceholderText("Add something AURA should remember...")
        self._add_input.setFont(body_font(13))
        self._add_input.setFixedHeight(38)
        self._add_input.setStyleSheet(f"""QLineEdit {{
                background-color: rgba(255,255,255,0.04);
                border: 1px solid {EVENT_VIOLET};
                border-radius: 10px; padding: 0 14px; color: {TEXT_PRIMARY};
            }}
            QLineEdit:focus {{ border: 1px solid {ACCRETION_BLUE}; }}
        """)
        self._add_input.returnPressed.connect(self._on_add)

        add_btn = QPushButton("Remember")
        add_btn.setFixedSize(96, 38)
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCRETION_BLUE}; color: {VOID_BLACK};
                border: none; border-radius: 10px; font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {ION_CYAN}; }}
        """)
        add_btn.clicked.connect(self._on_add)

        rl.addWidget(self._add_input, stretch=1)
        rl.addWidget(add_btn)
        return row

    # ── Backend calls ─────────────────────────────────────────────────────
    def _on_add(self):
        text = self._add_input.text().strip()
        if not text:
            return
        from memory.store import save_user_fact
        save_user_fact(text, "manual")
        self._add_input.clear()
        self.refresh()

    def _on_edit_fact(self, fact_id: int, new_text: str):
        from memory.store import update_user_fact
        update_user_fact(fact_id, new_text)

    def _on_delete_fact(self, fact_id: int):
        from memory.store import delete_user_fact
        delete_user_fact(fact_id)
        self.refresh()

    def _on_delete_note(self, entry_id: int):
        from memory.store import delete_knowledge
        delete_knowledge(entry_id)
        self.refresh()

    def _on_delete_snapshot(self, snap_id: int):
        from memory.store import delete_snapshot
        delete_snapshot(snap_id)
        self.refresh()

    # ── Render ─────────────────────────────────────────────────────────────
    def refresh(self):
        self._render_facts()
        self._render_notes()
        self._render_sessions()

    def _render_facts(self):
        from memory.store import get_user_facts_full
        self._facts_section.clear()
        try:
            rows = get_user_facts_full()
        except Exception:
            rows = []
        self._facts_section.set_count(len(rows))
        if not rows:
            self._facts_section.add_empty(
                "Nothing yet. Chat with AURA and it'll remember the durable "
                "stuff — or add something above.")
            return
        for fact_id, fact, category, _created in rows:
            self._facts_section.add(FactRow(
                fact_id, fact, category or "",
                self._on_edit_fact, self._on_delete_fact))

    def _render_notes(self):
        from memory.store import get_all_knowledge
        self._notes_section.clear()
        try:
            rows = get_all_knowledge()
        except Exception:
            rows = []
        self._notes_section.set_count(len(rows))
        if not rows:
            self._notes_section.add_empty("No saved notes yet.")
            return
        for entry_id, title, summary, created in rows:
            subtitle = (summary or "").strip()
            if created:
                stamp = str(created)[:10]
                subtitle = f"{subtitle}  ·  {stamp}" if subtitle else stamp
            self._notes_section.add(ReadRow(
                entry_id, title, subtitle, self._on_delete_note))

    def _render_sessions(self):
        from memory.store import get_all_snapshots
        self._sessions_section.clear()
        try:
            rows = get_all_snapshots()
        except Exception:
            rows = []
        self._sessions_section.set_count(len(rows))
        if not rows:
            self._sessions_section.add_empty("No past sessions recorded yet.")
            return
        for snap_id, app, summary, created in rows:
            title = (summary or "a session").strip()
            bits = []
            if app and app != "unknown":
                bits.append(app)
            if created:
                bits.append(str(created)[:16].replace("T", " "))
            self._sessions_section.add(ReadRow(
                snap_id, title, "  ·  ".join(bits), self._on_delete_snapshot))
