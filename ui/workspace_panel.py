# ui/workspace_panel.py
"""
Developer Workspace — Phase 1 of the AURA roadmap ("make the UI feel like
an engineering workspace"). This is NOT a second AURA app; it's a page
inside the same window that turns AURA into a lightweight coding platform:

    Today's Mission | Project Selector | Git Integration
    File Explorer    | Terminal Panel

Reached via the sidebar's "Workspace" nav item, or the "Aura App" shortcut
chip in the center panel (CenterPanel.openWorkspaceRequested).

Everything here talks to the real filesystem/git of the selected project
root (defaults to the AURA repo itself) — no mock data, except the project
list, which is the fixed set from the roadmap until a real project
registry exists.
"""

import os
import subprocess

from PySide6.QtCore import Qt, QProcess
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTabWidget,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ui import theme
from ui.code_review_panel import CodeReviewPanel
from ui.widgets import GlassPanel

# name -> path relative to nothing in particular; only "AURA" resolves to a
# real, existing directory today. Others are placeholders until Phase 2
# (Project Scanner) exists — picking one just shows "not found on disk".
_AURA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS = {
    "AURA": _AURA_ROOT,
    "Smart City": os.path.join(os.path.dirname(_AURA_ROOT), "Smart City"),
    "Portfolio": os.path.join(os.path.dirname(_AURA_ROOT), "Portfolio"),
}


def _label(text: str, size: int = 9, color: str = None, mono: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(theme.mono_font(size) if mono else theme.body_font(size))
    lbl.setStyleSheet(
        f"color: {color or theme.TEXT_SECONDARY}; background: transparent; border: none;"
    )
    return lbl


class WorkspacePanel(QWidget):
    """Aura's coding platform: mission, projects, git, files, terminal."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root = PROJECTS["AURA"]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        outer.addWidget(self._build_header())
        outer.addWidget(self._build_mission_and_project())

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(self._tab_style())

        files_tab = QWidget()
        body = QHBoxLayout(files_tab)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        body.addWidget(self._build_file_explorer(), 4)

        right_col = QVBoxLayout()
        right_col.setSpacing(10)
        right_col.addWidget(self._build_git_panel())
        right_col.addWidget(self._build_terminal_panel(), 1)
        body.addLayout(right_col, 6)

        self._tabs.addTab(files_tab, "Files & Git")

        self.code_review = CodeReviewPanel(self._root)
        self._tabs.addTab(self.code_review, "Code Review")

        outer.addWidget(self._tabs, 1)

        self.refresh()

    @staticmethod
    def _tab_style() -> str:
        return f"""
            QTabWidget::pane {{ border: none; }}
            QTabBar::tab {{
                background: rgba(255,255,255,0.03);
                color: {theme.TEXT_SECONDARY};
                border: 1px solid {theme.EVENT_VIOLET};
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 6px 16px;
                margin-right: 4px;
            }}
            QTabBar::tab:selected {{
                background: {theme.GLASS_BG};
                color: {theme.TEXT_PRIMARY};
            }}
        """

    # ── header ───────────────────────────────────────────────────────────
    def _build_header(self) -> QWidget:
        panel = GlassPanel(radius=14)
        lay = QHBoxLayout(panel)
        lay.setContentsMargins(14, 10, 14, 10)
        title = QLabel("🛠  Developer Workspace")
        title.setFont(theme.display_font(14))
        title.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; background: transparent; border: none;")
        sub = _label("Aura's coding platform — not a second app, a workspace inside this one", 9)
        lay.addWidget(title)
        lay.addSpacing(10)
        lay.addWidget(sub)
        lay.addStretch()
        refresh_btn = QPushButton("⟳ Refresh")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setFixedHeight(28)
        refresh_btn.setStyleSheet(self._btn_style())
        refresh_btn.clicked.connect(self.refresh)
        lay.addWidget(refresh_btn)
        return panel

    # ── mission + project selector ──────────────────────────────────────
    def _build_mission_and_project(self) -> QWidget:
        panel = GlassPanel(radius=14)
        lay = QHBoxLayout(panel)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(14)

        mission_col = QVBoxLayout()
        mission_col.setSpacing(2)
        mission_col.addWidget(_label("TODAY'S MISSION", 8, theme.TEXT_DIM, mono=True))
        self._mission_edit = QLineEdit("Wire up the Developer Workspace")
        self._mission_edit.setFont(theme.body_font(11))
        self._mission_edit.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; color: {theme.TEXT_PRIMARY}; }}"
        )
        mission_col.addWidget(self._mission_edit)
        lay.addLayout(mission_col, 3)

        proj_col = QVBoxLayout()
        proj_col.setSpacing(2)
        proj_col.addWidget(_label("PROJECT", 8, theme.TEXT_DIM, mono=True))
        self._project_combo = QComboBox()
        self._project_combo.addItems(list(PROJECTS.keys()) + ["+ New Project…"])
        self._project_combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: rgba(255,255,255,0.04);
                border: 1px solid {theme.EVENT_VIOLET};
                border-radius: 8px;
                color: {theme.TEXT_PRIMARY};
                padding: 4px 8px;
            }}
            """
        )
        self._project_combo.currentTextChanged.connect(self._on_project_changed)
        proj_col.addWidget(self._project_combo)
        lay.addLayout(proj_col, 2)

        return panel

    def _on_project_changed(self, name: str):
        if name == "+ New Project…":
            return  # Phase 2: real project registry; no-op placeholder for now
        path = PROJECTS.get(name)
        if path:
            self._root = path
            self.code_review.set_root(path)
            self.refresh()

    def set_mission(self, text: str):
        self._mission_edit.setText(text)

    # ── file explorer ────────────────────────────────────────────────────
    def _build_file_explorer(self) -> QWidget:
        panel = GlassPanel(radius=14)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        lay.addWidget(_label("FILE EXPLORER", 8, theme.TEXT_DIM, mono=True))

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setStyleSheet(
            f"""
            QTreeWidget {{
                background: transparent; border: none; color: {theme.TEXT_SECONDARY};
            }}
            QTreeWidget::item {{ padding: 2px; }}
            QTreeWidget::item:selected {{ background-color: rgba(91,127,255,0.18); }}
            """
        )
        self._tree.itemExpanded.connect(self._lazy_populate)
        lay.addWidget(self._tree, 1)
        return panel

    def _populate_tree(self):
        self._tree.clear()
        if not os.path.isdir(self._root):
            self._tree.addTopLevelItem(QTreeWidgetItem([f"(not found: {self._root})"]))
            return
        root_item = QTreeWidgetItem([os.path.basename(self._root) or self._root])
        self._tree.addTopLevelItem(root_item)
        self._fill_children(root_item, self._root)
        root_item.setExpanded(True)

    def _fill_children(self, item: QTreeWidgetItem, path: str):
        try:
            entries = sorted(
                os.listdir(path),
                key=lambda n: (not os.path.isdir(os.path.join(path, n)), n.lower()),
            )
        except OSError:
            return
        for name in entries:
            if name.startswith(".") or name in ("__pycache__", "node_modules"):
                continue
            full = os.path.join(path, name)
            child = QTreeWidgetItem([("📁 " if os.path.isdir(full) else "📄 ") + name])
            child.setData(0, Qt.UserRole, full)
            item.addChild(child)
            if os.path.isdir(full):
                # dummy child so the expand arrow shows; real contents are
                # lazy-loaded in _lazy_populate to keep this cheap
                child.addChild(QTreeWidgetItem(["…"]))

    def _lazy_populate(self, item: QTreeWidgetItem):
        if item.childCount() == 1 and item.child(0).text(0) == "…":
            path = item.data(0, Qt.UserRole)
            item.takeChildren()
            if path:
                self._fill_children(item, path)

    # ── git integration ──────────────────────────────────────────────────
    def _build_git_panel(self) -> QWidget:
        panel = GlassPanel(radius=14)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)
        lay.addWidget(_label("GIT INTEGRATION", 8, theme.TEXT_DIM, mono=True))
        self._git_branch = _label("—", 10, theme.TEXT_PRIMARY, mono=True)
        self._git_status = _label("—", 9)
        self._git_commit = _label("—", 9)
        lay.addWidget(self._git_branch)
        lay.addWidget(self._git_status)
        lay.addWidget(self._git_commit)
        return panel

    def _refresh_git(self):
        def run(*args):
            try:
                return subprocess.run(
                    ["git", "-C", self._root, *args],
                    capture_output=True, text=True, timeout=5,
                ).stdout.strip()
            except Exception:
                return ""

        if not os.path.isdir(os.path.join(self._root, ".git")):
            self._git_branch.setText("Not a git repository")
            self._git_status.setText("")
            self._git_commit.setText("")
            return

        branch = run("rev-parse", "--abbrev-ref", "HEAD") or "?"
        dirty = run("status", "--porcelain")
        status_text = "● Uncommitted changes" if dirty else "✓ Clean"
        status_color = theme.ALERT_ORANGE if dirty else theme.FOCUS_GREEN
        last_commit = run("log", "-1", "--format=%h  %s") or "(no commits yet)"

        self._git_branch.setText(f"⎇ {branch}")
        self._git_status.setText(status_text)
        self._git_status.setStyleSheet(
            f"color: {status_color}; background: transparent; border: none;"
        )
        self._git_commit.setText(last_commit)

    # ── terminal panel ───────────────────────────────────────────────────
    def _build_terminal_panel(self) -> QWidget:
        panel = GlassPanel(radius=14)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        lay.addWidget(_label("TERMINAL", 8, theme.TEXT_DIM, mono=True))

        self._term_output = QTextEdit()
        self._term_output.setReadOnly(True)
        self._term_output.setFont(theme.mono_font(10))
        self._term_output.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: rgba(0,0,0,0.35);
                border: 1px solid {theme.EVENT_VIOLET};
                border-radius: 8px;
                color: {theme.ION_CYAN};
                padding: 8px;
            }}
            """
        )
        lay.addWidget(self._term_output, 1)

        row = QHBoxLayout()
        self._term_input = QLineEdit()
        self._term_input.setPlaceholderText("Run a command in this project...")
        self._term_input.setFont(theme.mono_font(10))
        self._term_input.setStyleSheet(
            f"""
            QLineEdit {{
                background-color: rgba(255,255,255,0.04);
                border: 1px solid {theme.EVENT_VIOLET};
                border-radius: 8px;
                padding: 6px 10px;
                color: {theme.TEXT_PRIMARY};
            }}
            """
        )
        self._term_input.returnPressed.connect(self._run_command)
        run_btn = QPushButton("Run")
        run_btn.setCursor(Qt.PointingHandCursor)
        run_btn.setStyleSheet(self._btn_style())
        run_btn.clicked.connect(self._run_command)
        row.addWidget(self._term_input, 1)
        row.addWidget(run_btn)
        lay.addLayout(row)

        self._process = None
        return panel

    def _run_command(self):
        cmd = self._term_input.text().strip()
        if not cmd:
            return
        self._term_input.clear()
        self._term_output.append(f"$ {cmd}")

        proc = QProcess(self)
        proc.setWorkingDirectory(self._root)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(lambda p=proc: self._on_proc_output(p))
        proc.finished.connect(lambda code, _status, p=proc: self._on_proc_finished(p, code))
        if os.name == "nt":
            proc.start("cmd", ["/c", cmd])
        else:
            proc.start("/bin/sh", ["-c", cmd])
        self._process = proc

    def _on_proc_output(self, proc: QProcess):
        data = bytes(proc.readAllStandardOutput()).decode(errors="replace")
        if data:
            self._term_output.append(data.rstrip("\n"))

    def _on_proc_finished(self, proc: QProcess, code: int):
        self._term_output.append(f"[exit {code}]")

    # ── shared ───────────────────────────────────────────────────────────
    @staticmethod
    def _btn_style() -> str:
        return f"""
            QPushButton {{
                background-color: {theme.GLASS_BG if hasattr(theme, 'GLASS_BG') else 'rgba(255,255,255,0.04)'};
                border: 1px solid {theme.EVENT_VIOLET};
                border-radius: 8px;
                color: {theme.TEXT_SECONDARY};
                padding: 4px 12px;
            }}
            QPushButton:hover {{
                border: 1px solid {theme.ACCRETION_BLUE};
                color: {theme.TEXT_PRIMARY};
            }}
        """

    def refresh(self):
        self._populate_tree()
        self._refresh_git()
