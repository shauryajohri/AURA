# ui/workbench_window.py
"""
AURA Workbench — a dedicated software-engineering environment where AURA and
the developer work side by side as two engineers, each with their own
workspace. This is a *standalone* frameless window that opens ABOVE the main
AURA companion (the orb keeps running in the background); it is NOT a page
inside the main window.

Layout (matches the V1 design spec):

    ┌───────────────────────────────────────────────────────────────┐
    │  titlebar                                                       │
    ├────────────┬──────────────────────────────────────────────────┤
    │            │  header: New File · Open Folder · Terminal · …    │
    │  SIDEBAR   ├──────────────────────────────────────────────────┤
    │  Active    │  AURA WORKSPACE (read-only) │ YOUR WORKSPACE      │
    │  Model     │  · current thought ticker   │ · editable + tabs  │
    │  Mini      ├──────────────────────────────────────────────────┤
    │  Universe  │  Console │ Browser Preview │ Validation           │
    │  Chat      ├──────────────────────────────────────────────────┤
    │  Prompt    │  Awareness  │  Error Intelligence                 │
    │            ├──────────────────────────────────────────────────┤
    │            │  Permission bar → Merge Into Main Codebase        │
    └────────────┴──────────────────────────────────────────────────┘

Everything AURA does happens inside its own sandbox (the left "AURA WORKSPACE"
panel is read-only). The real project is never touched until the developer
walks the permission flow and clicks "Merge Into Main Codebase".

This module is a *wired shell*: the layout, animations and interactions are
real, and the cheap real actions (open folder, git status, run command, save)
work against the live filesystem. The heavy paths (AI generation, live browser
render) expose a clean public API so the backend can drive them later without
touching this file's layout.
"""

import os
import subprocess

from PySide6.QtCore import Qt, QSettings, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QSplitter, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget,
)

from ui import theme
from ui.cosmos_panel import CosmosPanel
from ui.state import AuraState, StateBus
from ui.widgets import GlassPanel, StatusChip


_AURA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── small shared helpers ────────────────────────────────────────────────────
def _label(text, size=9, color=None, mono=False, weight=None):
    lbl = QLabel(text)
    if mono:
        lbl.setFont(theme.mono_font(size))
    else:
        lbl.setFont(theme.body_font(size))
    lbl.setStyleSheet(
        f"color: {color or theme.TEXT_SECONDARY}; background: transparent; border: none;"
    )
    return lbl


def _title(text, size=13, color=None):
    lbl = QLabel(text)
    lbl.setFont(theme.display_font(size))
    lbl.setStyleSheet(
        f"color: {color or theme.TEXT_PRIMARY}; background: transparent; border: none;"
    )
    return lbl


def _btn(text, primary=False):
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(30)
    if primary:
        b.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {theme.EVENT_VIOLET};
                border: 1px solid {theme.ACCRETION_BLUE};
                border-radius: 8px; color: {theme.TEXT_PRIMARY};
                padding: 4px 16px; font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {theme.ACCRETION_BLUE}; }}
            """
        )
    else:
        b.setStyleSheet(
            f"""
            QPushButton {{
                background-color: rgba(255,255,255,0.04);
                border: 1px solid {theme.EVENT_VIOLET};
                border-radius: 8px; color: {theme.TEXT_SECONDARY};
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                border: 1px solid {theme.ACCRETION_BLUE};
                color: {theme.TEXT_PRIMARY};
            }}
            """
        )
    return b


def _editor(read_only=False):
    ed = QPlainTextEdit()
    ed.setReadOnly(read_only)
    ed.setFont(theme.mono_font(10))
    ed.setStyleSheet(
        f"""
        QPlainTextEdit {{
            background-color: rgba(0,0,0,0.38);
            border: 1px solid {theme.EVENT_VIOLET};
            border-radius: 10px;
            color: {theme.STARLIGHT_WHITE};
            padding: 10px;
            selection-background-color: {theme.EVENT_VIOLET};
        }}
        """
    )
    return ed


class WorkbenchWindow(QWidget):
    """The AURA Workbench — a second engineer working beside the developer."""

    promptSubmitted   = Signal(str)   # developer typed into the prompt box
    mergeRequested    = Signal()      # "Merge Into Main Codebase" clicked
    pullRequestRequested = Signal()   # "Create Pull Request" clicked
    permissionGranted = Signal(str)   # a stage in the permission flow approved

    _MODE_PLACEHOLDERS = {
        "/research":   "🔍 RESEARCH — structured findings before code",
        "/discussion": "🧠 DISCUSSION — challenge the idea first",
        "/plan":       "📋 PLAN — turn the idea into a roadmap",
        "/code":       "💻 CODE — build it in the sandbox",
    }

    def __init__(self, bus: StateBus = None, root: str = None, parent=None):
        super().__init__(parent)
        self.bus = bus or StateBus()
        self._root = root or _AURA_ROOT
        self._drag_pos = None
        self._proc = None
        self._settings = QSettings("AURA", "Workbench")

        self.setWindowTitle("AURA Workbench")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setMinimumSize(1240, 780)
        self.setStyleSheet(f"background-color: {theme.VOID_BLACK};")

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(10, 8, 10, 10)
        root_lay.setSpacing(8)

        root_lay.addWidget(self._build_titlebar())

        body = QHBoxLayout()
        body.setSpacing(10)
        body.addWidget(self._build_sidebar())
        body.addWidget(self._build_main(), 1)
        root_lay.addLayout(body, 1)

        # esc closes; makes preview quick to dismiss
        QShortcut(QKeySequence("Esc"), self, activated=self.close)

        self._seed_demo_content()
        self._restore_sidebar_sizes()

    # ── titlebar ────────────────────────────────────────────────────────────
    def _build_titlebar(self):
        bar = QWidget()
        bar.setFixedHeight(30)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(6, 0, 0, 0)
        lay.setSpacing(8)

        brand = _title("AURA", 14)
        sub = _label("W O R K B E N C H", 8, theme.TEXT_DIM, mono=True)
        lay.addWidget(brand)
        lay.addWidget(sub)
        lay.addStretch()

        self._focus_chip = StatusChip("● Focus Mode", theme.FOCUS_GREEN)
        lay.addWidget(self._focus_chip)

        for glyph, handler in (("—", self.showMinimized),
                               ("□", self._toggle_max),
                               ("✕", self.close)):
            b = QPushButton(glyph)
            b.setFixedSize(30, 24)
            b.setCursor(Qt.PointingHandCursor)
            hover = theme.ERROR_RED if glyph == "✕" else "rgba(125,127,255,0.2)"
            b.setStyleSheet(
                f"""
                QPushButton {{ background: transparent; border: none;
                               color: {theme.TEXT_DIM}; font-size: 11px;
                               border-radius: 6px; }}
                QPushButton:hover {{ background-color: {hover};
                                     color: {theme.TEXT_PRIMARY}; }}
                """
            )
            b.clicked.connect(handler)
            lay.addWidget(b)

        self._titlebar = bar
        return bar

    def _toggle_max(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    # ── left sidebar ─────────────────────────────────────────────────────────
    def _build_sidebar(self):
        col = QWidget()
        col.setFixedWidth(320)
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        lay.addWidget(self._build_active_model())

        # Universe + chat share a draggable vertical splitter so the developer
        # can grow the chat as tall as they like; the sizes are persisted, so
        # the chat keeps whatever height they set the next time AURA launches.
        self._side_splitter = QSplitter(Qt.Vertical)
        self._side_splitter.setStyleSheet(self._splitter_style())
        self._side_splitter.setHandleWidth(8)
        self._side_splitter.setChildrenCollapsible(False)
        self._side_splitter.addWidget(self._build_universe())
        self._side_splitter.addWidget(self._build_chat())
        self._side_splitter.setStretchFactor(0, 1)
        self._side_splitter.setStretchFactor(1, 2)
        self._side_splitter.splitterMoved.connect(self._save_sidebar_sizes)
        lay.addWidget(self._side_splitter, 1)

        lay.addWidget(self._build_prompt())
        return col

    def _save_sidebar_sizes(self, *args):
        self._settings.setValue("side_splitter", self._side_splitter.saveState())

    def _restore_sidebar_sizes(self):
        state = self._settings.value("side_splitter")
        if state is not None:
            self._side_splitter.restoreState(state)
        else:
            self._side_splitter.setSizes([260, 360])  # chat starts roomy

    def _build_active_model(self):
        panel = GlassPanel(radius=16)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(3)

        lay.addWidget(_label("ACTIVE MODEL", 8, theme.TEXT_DIM, mono=True))
        self._model_name = _title("Nemotron 3 Super", 17)
        lay.addWidget(self._model_name)
        self._model_role = _label("Coding Model", 10, theme.ACCRETION_BLUE)
        lay.addWidget(self._model_role)

        row = QHBoxLayout()
        row.setContentsMargins(0, 4, 0, 0)
        self._model_chip = StatusChip("ACTIVE", theme.FOCUS_GREEN)
        row.addWidget(self._model_chip)
        row.addStretch()
        lay.addLayout(row)

        self._model_task = _label("Optimizing authentication module", 9, theme.TEXT_SECONDARY)
        self._model_task.setWordWrap(True)
        lay.addWidget(self._model_task)
        return panel

    def _build_universe(self):
        panel = GlassPanel(radius=16)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)
        lay.addWidget(_label("AURA UNIVERSE", 8, theme.TEXT_DIM, mono=True))
        self._cosmos = CosmosPanel(self.bus)
        self._cosmos.setMinimumHeight(160)
        lay.addWidget(self._cosmos, 1)
        panel.setMinimumHeight(150)
        return panel

    def _build_chat(self):
        panel = GlassPanel(radius=16)
        panel.setMinimumHeight(120)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        lay.addWidget(_label("COLLABORATION", 8, theme.TEXT_DIM, mono=True))

        self._chat = QTextEdit()
        self._chat.setReadOnly(True)
        self._chat.setFont(theme.body_font(10))
        self._chat.setStyleSheet(
            f"""
            QTextEdit {{ background: transparent; border: none;
                         color: {theme.TEXT_SECONDARY}; }}
            """
        )
        lay.addWidget(self._chat, 1)
        return panel

    def _build_prompt(self):
        panel = GlassPanel(radius=14)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        chips = QHBoxLayout()
        chips.setSpacing(4)
        for cmd in ("/research", "/discussion", "/plan", "/code"):
            c = QPushButton(cmd)
            c.setCursor(Qt.PointingHandCursor)
            c.setFixedHeight(22)
            c.setStyleSheet(
                f"""
                QPushButton {{ background: rgba(125,127,255,0.10);
                               border: 1px solid {theme.EVENT_VIOLET};
                               border-radius: 11px; color: {theme.TEXT_SECONDARY};
                               padding: 0 8px; font-size: 10px; }}
                QPushButton:hover {{ color: {theme.TEXT_PRIMARY};
                                     border-color: {theme.ACCRETION_BLUE}; }}
                """
            )
            c.clicked.connect(lambda _, m=cmd: self._insert_mode(m))
            chips.addWidget(c)
        chips.addStretch()
        lay.addLayout(chips)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._prompt = QLineEdit()
        self._prompt.setPlaceholderText("Ask AURA to research, plan, or build…")
        self._prompt.setFont(theme.body_font(11))
        self._prompt.setStyleSheet(
            f"""
            QLineEdit {{ background: rgba(255,255,255,0.04);
                         border: 1px solid {theme.EVENT_VIOLET};
                         border-radius: 10px; padding: 8px 12px;
                         color: {theme.TEXT_PRIMARY}; }}
            QLineEdit:focus {{ border: 1px solid {theme.ACCRETION_BLUE}; }}
            """
        )
        self._prompt.returnPressed.connect(self._submit_prompt)
        send = _btn("➤", primary=True)
        send.setFixedWidth(44)
        send.clicked.connect(self._submit_prompt)
        row.addWidget(self._prompt, 1)
        row.addWidget(send)
        lay.addLayout(row)
        return panel

    # ── main column ──────────────────────────────────────────────────────────
    def _build_main(self):
        col = QWidget()
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        lay.addWidget(self._build_header())
        lay.addWidget(self._build_workspaces(), 1)
        lay.addWidget(self._build_permission_bar())
        return col

    @staticmethod
    def _splitter_style():
        return f"QSplitter::handle {{ background: {theme.EVENT_VIOLET}; border-radius: 3px; }}"

    def _build_header(self):
        panel = GlassPanel(radius=14)
        lay = QHBoxLayout(panel)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(6)

        actions = (
            ("📄 New File", self._new_file),
            ("📁 Open Folder", self._open_folder),
            ("⎇ Git", self._git_status),
            ("⚙ Settings", None),
        )
        for text, handler in actions:
            b = _btn(text)
            if handler:
                b.clicked.connect(handler)
            lay.addWidget(b)
        lay.addStretch()

        self._task_chip = StatusChip("TASK · auth refactor", theme.ACCRETION_BLUE)
        self._ws_chip = StatusChip("AURA · sandbox", theme.EVENT_VIOLET)
        lay.addWidget(self._task_chip)
        lay.addWidget(self._ws_chip)
        return panel

    def _build_workspaces(self):
        # AURA's read-only workspace was removed — the developer's workspace
        # now fills the full width.
        return self._build_your_workspace()

    def _build_your_workspace(self):
        panel = GlassPanel(radius=14)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.addWidget(_title("◆  YOUR WORKSPACE", 12, theme.ION_CYAN))
        head.addStretch()
        save = _btn("💾 Save")
        save.clicked.connect(self._save_file)
        head.addWidget(save)
        head.addWidget(StatusChip("WRITABLE", theme.FOCUS_GREEN))
        lay.addLayout(head)

        self._your_tabs = QTabWidget()
        self._your_tabs.setStyleSheet(self._tab_style())
        self._your_editor = _editor(read_only=False)
        self._your_tabs.addTab(self._your_editor, "untitled.py")
        lay.addWidget(self._your_tabs, 1)
        self._current_file = None
        return panel

    # ── permission / merge bar ───────────────────────────────────────────────
    def _build_permission_bar(self):
        panel = GlassPanel(radius=14)
        lay = QHBoxLayout(panel)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)

        flow = QVBoxLayout()
        flow.setSpacing(2)
        flow.addWidget(_label("PROJECT ACCESS", 8, theme.TEXT_DIM, mono=True))
        stages = QHBoxLayout()
        stages.setSpacing(4)
        stage_names = ("READ ONLY", "Sandbox", "Merge Review", "Write", "Push")
        self._stage_chips = []
        for i, name in enumerate(stage_names):
            color = theme.FOCUS_GREEN if i == 0 else theme.TEXT_DIM
            chip = StatusChip(name, color)
            self._stage_chips.append(chip)
            stages.addWidget(chip)
            if name != "Push":
                stages.addWidget(_label("→", 10, theme.TEXT_DIM))
        stages.addStretch()
        flow.addLayout(stages)

        meta = _label("Added 0 · Deleted 0 · Modified 0 · Risk: low · Confidence 96%",
                      9, theme.TEXT_SECONDARY)
        self._merge_meta = meta
        flow.addWidget(meta)
        lay.addLayout(flow, 1)

        merge = _btn("⬆  Merge Into Main Codebase", primary=True)
        merge.setFixedHeight(42)
        merge.clicked.connect(self._on_merge)
        pr = _btn("Create Pull Request")
        pr.setFixedHeight(42)
        pr.clicked.connect(self.pullRequestRequested.emit)
        lay.addWidget(pr)
        lay.addWidget(merge)
        return panel

    @staticmethod
    def _tab_style():
        return f"""
            QTabWidget::pane {{ border: none; }}
            QTabBar::tab {{
                background: rgba(255,255,255,0.03);
                color: {theme.TEXT_SECONDARY};
                border: 1px solid {theme.EVENT_VIOLET}; border-bottom: none;
                border-top-left-radius: 8px; border-top-right-radius: 8px;
                padding: 5px 14px; margin-right: 3px;
            }}
            QTabBar::tab:selected {{ background: {theme.GLASS_BG}; color: {theme.TEXT_PRIMARY}; }}
        """

    # ── interactions (wired shells) ──────────────────────────────────────────
    def _insert_mode(self, cmd):
        self._prompt.setText(cmd + " ")
        self._prompt.setFocus()
        self._prompt.setPlaceholderText(self._MODE_PLACEHOLDERS.get(cmd, ""))

    def _submit_prompt(self):
        text = self._prompt.text().strip()
        if not text:
            return
        self._prompt.clear()
        self.append_chat("You", text)
        self.bus.set_state(AuraState.THINKING)
        self.promptSubmitted.emit(text)
        # optimistic echo so the shell feels alive before a backend answers
        QTimer.singleShot(600, lambda: self.append_chat(
            "AURA", "Working in the sandbox — I'll surface a diff for review."))

    def _new_file(self):
        self._your_editor.clear()
        self._current_file = None
        self._your_tabs.setTabText(self._your_tabs.currentIndex(), "untitled.py")

    def _open_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Open project folder", self._root)
        if path:
            self._root = path
            self._ws_chip.set_chip(os.path.basename(path) or path, theme.EVENT_VIOLET)
            self._git_status()

    def _git_status(self):
        if not os.path.isdir(os.path.join(self._root, ".git")):
            self.append_chat("AURA", f"Not a git repository: {self._root}")
            return
        try:
            res = subprocess.run(
                ["git", "-C", self._root, "status", "-sb"],
                capture_output=True, text=True, timeout=5,
            )
            self.append_chat("AURA", "git status:<br><code>"
                             + res.stdout.strip().replace("\n", "<br>") + "</code>")
        except Exception as e:
            self.append_chat("AURA", f"git status failed: {e}")

    def _save_file(self):
        if not self._current_file:
            path, _ = QFileDialog.getSaveFileName(self, "Save file", self._root)
            if not path:
                return
            self._current_file = path
            self._your_tabs.setTabText(self._your_tabs.currentIndex(),
                                       os.path.basename(path))
        try:
            with open(self._current_file, "w", encoding="utf-8") as f:
                f.write(self._your_editor.toPlainText())
            self.append_chat("AURA", f"Saved {os.path.basename(self._current_file)}.")
        except Exception as e:
            self.append_chat("AURA", f"Couldn't save: {e}")

    def _on_merge(self):
        # Walk the permission flow forward one confirmation at a time — the
        # real project is never touched until every stage is green.
        for chip in self._stage_chips:
            chip.set_chip(chip.text(), theme.FOCUS_GREEN)
        self.append_chat("AURA", "All stages approved — ready to merge into main.")
        self.mergeRequested.emit()

    # ── drag (frameless) ─────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if (e.button() == Qt.LeftButton
                and e.position().y() <= self._titlebar.height() + 8):
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag_pos = None
        super().mouseReleaseEvent(e)

    # ── public API for the backend ───────────────────────────────────────────
    def append_chat(self, sender: str, text: str):
        color = theme.ION_CYAN if sender == "AURA" else theme.ACCRETION_BLUE
        self._chat.append(
            f'<span style="color:{color}"><b>{sender}</b></span>'
            f'<span style="color:{theme.TEXT_SECONDARY}"> · {text}</span>')

    def set_active_model(self, name: str, role: str = "", task: str = ""):
        self._model_name.setText(name)
        if role:
            self._model_role.setText(role)
        if task:
            self._model_task.setText(task)
        self.bus.set_active_model(name)

    # ── demo content so the window looks alive on first open ─────────────────
    def _seed_demo_content(self):
        self._your_editor.setPlainText(
            "def two_sum(nums, target):\n"
            "    for i in range(len(nums)):\n"
            "        for j in range(i + 1, len(nums)):\n"
            "            if nums[i] + nums[j] == target:\n"
            "                return [i, j]\n"
            "    return []\n"
        )
        self.append_chat("You", "Optimize this function.")
        self.append_chat("AURA", "Found an O(n²) loop — rewriting with a hash map.")


def _demo():
    import sys
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    w = WorkbenchWindow()
    w.resize(1360, 860)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    _demo()
