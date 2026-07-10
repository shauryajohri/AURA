# ui/code_review_panel.py
"""
Code Review panel — the dual-pane view from the AURA Workbench mockup:
AURA's suggested code (read-only, left) next to your real file
(editable, right), with an explanation strip, a run console, and
workspace access indicators along the bottom.

Lives as a second tab inside WorkspacePanel ("Files & Git" | "Code Review").
Real filesystem I/O, real `python` execution via QProcess, and a real
call to core.ai_router for the "optimize" suggestion. The "Push to Main
Codebase" button is a placeholder — it does NOT run git push. Wire that
up deliberately later if you actually want AURA pushing commits.
"""

import os
import threading

from PySide6.QtCore import Qt, QObject, QProcess, Signal
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from ui import theme
from ui.widgets import GlassPanel


def _label(text: str, size: int = 9, color: str = None, mono: bool = False,
           bold: bool = False) -> QLabel:
    lbl = QLabel(text)
    font = theme.mono_font(size) if mono else theme.body_font(size)
    if bold:
        font.setBold(True)
    lbl.setFont(font)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(
        f"color: {color or theme.TEXT_SECONDARY}; background: transparent; border: none;"
    )
    return lbl


def _hex_to_rgb(hexcolor: str) -> str:
    h = hexcolor.lstrip("#")
    return ",".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def _tag(text: str, color: str, filled: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(theme.mono_font(8))
    bg = f"rgba({_hex_to_rgb(color)},0.15)" if filled else "transparent"
    lbl.setStyleSheet(
        f"color: {color}; background-color: {bg}; border: 1px solid {color};"
        f"border-radius: 6px; padding: 2px 8px;"
    )
    return lbl


class _AskSignals(QObject):
    done = Signal(str, str, str)   # explanation, language, code
    failed = Signal(str)


class CodeReviewPanel(QWidget):
    """Dual-pane read-only(AURA) / writable(you) code view + console."""

    def __init__(self, project_root: str, parent=None):
        super().__init__(parent)
        self._root = project_root
        self._current_path = ""
        self._process = None

        self._signals = _AskSignals()
        self._signals.done.connect(self._on_suggestion_ready)
        self._signals.failed.connect(self._on_suggestion_failed)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        outer.addWidget(self._build_file_row())

        body = QHBoxLayout()
        body.setSpacing(10)
        body.addWidget(self._build_aura_column(), 1)
        body.addWidget(self._build_your_column(), 1)
        outer.addLayout(body, 1)

        outer.addWidget(self._build_access_bar())

    # ── project root can change (project selector up in WorkspacePanel) ──
    def set_root(self, root: str):
        self._root = root
        self._project_label.setText(f"📁 {self._root}")

    # ── file row ─────────────────────────────────────────────────────────
    def _build_file_row(self) -> QWidget:
        panel = GlassPanel(radius=14)
        lay = QHBoxLayout(panel)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(8)
        lay.addWidget(_label("FILE", 8, theme.TEXT_DIM, mono=True))

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText(
            "Path relative to project root, e.g. modules/tasks.py"
        )
        self._path_edit.setFont(theme.mono_font(10))
        self._path_edit.setStyleSheet(
            f"""
            QLineEdit {{
                background-color: rgba(255,255,255,0.04);
                border: 1px solid {theme.EVENT_VIOLET};
                border-radius: 8px;
                padding: 5px 8px;
                color: {theme.TEXT_PRIMARY};
            }}
            """
        )
        self._path_edit.returnPressed.connect(self._load_file)
        lay.addWidget(self._path_edit, 1)

        browse_btn = QPushButton("Browse…")
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.setStyleSheet(self._btn_style())
        browse_btn.clicked.connect(self._browse_file)
        lay.addWidget(browse_btn)

        load_btn = QPushButton("Load")
        load_btn.setCursor(Qt.PointingHandCursor)
        load_btn.setStyleSheet(self._btn_style(accent=theme.ACCRETION_BLUE))
        load_btn.clicked.connect(self._load_file)
        lay.addWidget(load_btn)
        return panel

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open file", self._root)
        if path:
            try:
                rel = os.path.relpath(path, self._root)
            except ValueError:
                rel = path
            self._path_edit.setText(rel)
            self._load_file()

    def _load_file(self):
        rel = self._path_edit.text().strip()
        if not rel:
            return
        full = rel if os.path.isabs(rel) else os.path.join(self._root, rel)
        if not os.path.isfile(full):
            QMessageBox.warning(self, "Not found", f"No file at:\n{full}")
            return
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
            return
        self._current_path = full
        self._your_edit.setPlainText(content)
        self._aura_edit.setPlainText("")
        self._explanation.setText(
            "Loaded. Click “✨ Ask AURA to optimize” for a suggestion here."
        )
        self._console.clear()

    # ── AURA column (read-only) ─────────────────────────────────────────
    def _build_aura_column(self) -> QWidget:
        panel = GlassPanel(radius=14)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        header = QHBoxLayout()
        header.addWidget(_label("✦ AURA CODING AREA", 11, theme.TEXT_PRIMARY, bold=True))
        header.addStretch()
        header.addWidget(_tag("READ-ONLY", theme.TEXT_DIM))
        lay.addLayout(header)
        lay.addWidget(_label("AI Assistant Workspace (Read-Only)", 9))

        self._aura_edit = QPlainTextEdit()
        self._aura_edit.setReadOnly(True)
        self._aura_edit.setFont(theme.mono_font(10))
        self._aura_edit.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background-color: rgba(0,0,0,0.35);
                border: 1px solid {theme.EVENT_VIOLET};
                border-radius: 8px;
                color: {theme.ION_CYAN};
                padding: 8px;
            }}
            """
        )
        lay.addWidget(self._aura_edit, 1)

        ask_btn = QPushButton("✨ Ask AURA to Optimize")
        ask_btn.setCursor(Qt.PointingHandCursor)
        ask_btn.setStyleSheet(self._btn_style(accent=theme.IDLE_PURPLE))
        ask_btn.clicked.connect(self._ask_aura)
        lay.addWidget(ask_btn)

        lay.addWidget(_label("AURA EXPLANATION", 8, theme.TEXT_DIM, mono=True))
        self._explanation = _label(
            "Load a file, then click “✨ Ask AURA to optimize”.", 10
        )
        lay.addWidget(self._explanation)
        return panel

    def _ask_aura(self):
        if not self._current_path:
            QMessageBox.information(self, "No file loaded", "Load a file first.")
            return
        code = self._your_edit.toPlainText()
        if not code.strip():
            QMessageBox.information(self, "Empty file", "Nothing to optimize yet.")
            return
        self._aura_edit.setPlainText("// asking AURA…")
        self._explanation.setText("Thinking…")
        prompt = (
            f"Review and optimize this code from "
            f"{os.path.basename(self._current_path)}. Explain the change in "
            f"1-2 short sentences, then give the FULL optimized file.\n\n"
            f"```\n{code}\n```"
        )
        threading.Thread(target=self._ask_worker, args=(prompt,), daemon=True).start()

    def _ask_worker(self, prompt: str):
        try:
            from core.ai_router import route, extract_code_block
            raw = route("CODING", prompt)
            if not raw or raw in ("RATE_LIMIT", "CONNECTION_ERROR"):
                self._signals.failed.emit(raw or "No response")
                return
            chat_part, lang, code = extract_code_block(raw)
            if not code:
                self._signals.failed.emit("AURA didn't return a code block.")
                return
            self._signals.done.emit(chat_part or "Done.", lang, code)
        except Exception as e:
            self._signals.failed.emit(str(e))

    def _on_suggestion_ready(self, explanation: str, lang: str, code: str):
        self._aura_edit.setPlainText(code)
        self._explanation.setText(explanation)

    def _on_suggestion_failed(self, message: str):
        self._aura_edit.setPlainText("")
        self._explanation.setText(f"⚠ {message}")

    # ── Your column (writable) ──────────────────────────────────────────
    def _build_your_column(self) -> QWidget:
        panel = GlassPanel(radius=14)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        header = QHBoxLayout()
        header.addWidget(_label("◆ YOUR CODING AREA", 11, theme.TEXT_PRIMARY, bold=True))
        header.addStretch()
        header.addWidget(_tag("WRITABLE", theme.FOCUS_GREEN))
        lay.addLayout(header)
        lay.addWidget(_label("Your Workspace (Editable & Saveable)", 9))

        self._your_edit = QPlainTextEdit()
        self._your_edit.setFont(theme.mono_font(10))
        self._your_edit.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background-color: rgba(0,0,0,0.35);
                border: 1px solid {theme.EVENT_VIOLET};
                border-radius: 8px;
                color: {theme.TEXT_PRIMARY};
                padding: 8px;
            }}
            """
        )
        lay.addWidget(self._your_edit, 1)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("💾 Save")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(self._btn_style(accent=theme.FOCUS_GREEN))
        save_btn.clicked.connect(self._save_file)
        run_btn = QPushButton("▶ Run")
        run_btn.setCursor(Qt.PointingHandCursor)
        run_btn.setStyleSheet(self._btn_style(accent=theme.ACCRETION_BLUE))
        run_btn.clicked.connect(self._run_file)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(run_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        lay.addWidget(_label("OUTPUT / CONSOLE", 8, theme.TEXT_DIM, mono=True))
        self._console = QTextEdit()
        self._console.setReadOnly(True)
        self._console.setFont(theme.mono_font(9))
        self._console.setFixedHeight(120)
        self._console.setStyleSheet(
            f"""
            QTextEdit {{
                background-color: rgba(0,0,0,0.35);
                border: 1px solid {theme.EVENT_VIOLET};
                border-radius: 8px;
                color: {theme.FOCUS_GREEN};
                padding: 6px;
            }}
            """
        )
        lay.addWidget(self._console)
        return panel

    def _save_file(self):
        if not self._current_path:
            QMessageBox.information(self, "No file loaded", "Load a file first.")
            return
        try:
            with open(self._current_path, "w", encoding="utf-8") as f:
                f.write(self._your_edit.toPlainText())
            self._console.append(f"> Saved {self._current_path}")
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))

    def _run_file(self):
        if not self._current_path:
            QMessageBox.information(self, "No file loaded", "Load a file first.")
            return
        self._save_file()
        self._console.append(f"> Running {os.path.basename(self._current_path)}")
        proc = QProcess(self)
        proc.setWorkingDirectory(self._root)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(lambda p=proc: self._on_proc_output(p))
        proc.finished.connect(
            lambda code, _status, p=proc: self._console.append(f"> [exit {code}]")
        )
        proc.start("python", [self._current_path])
        self._process = proc

    def _on_proc_output(self, proc: QProcess):
        data = bytes(proc.readAllStandardOutput()).decode(errors="replace")
        if data:
            self._console.append(data.rstrip("\n"))

    # ── bottom access bar ────────────────────────────────────────────────
    def _build_access_bar(self) -> QWidget:
        panel = GlassPanel(radius=14)
        lay = QHBoxLayout(panel)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(20)

        proj_col = QVBoxLayout()
        proj_col.addWidget(_label("PROJECT ACCESS", 8, theme.TEXT_DIM, mono=True))
        self._project_label = _label(f"📁 {self._root}", 9, theme.TEXT_PRIMARY, mono=True)
        proj_col.addWidget(self._project_label)
        lay.addLayout(proj_col, 2)

        access_col = QVBoxLayout()
        access_col.addWidget(_label("ACCESS LEVEL", 8, theme.TEXT_DIM, mono=True))
        access_col.addWidget(_label("READ + WRITE (local)", 10, theme.FOCUS_GREEN, bold=True))
        lay.addLayout(access_col, 1)

        push_col = QVBoxLayout()
        push_col.addWidget(_label("PUSH PERMISSION", 8, theme.TEXT_DIM, mono=True))
        push_col.addWidget(_label("🔒 Off — placeholder", 10, theme.ALERT_ORANGE, bold=True))
        lay.addLayout(push_col, 1)

        push_btn = QPushButton("☁ Push to Main Codebase")
        push_btn.setCursor(Qt.PointingHandCursor)
        push_btn.setStyleSheet(self._btn_style(accent=theme.IDLE_PURPLE, filled=True))
        push_btn.clicked.connect(self._push_clicked)
        lay.addWidget(push_btn)
        return panel

    def _push_clicked(self):
        QMessageBox.information(
            self, "Push disabled",
            "Real git push isn't wired up yet — this button is a placeholder "
            "until you decide you want AURA running `git push` for you."
        )

    # ── shared style ─────────────────────────────────────────────────────
    @staticmethod
    def _btn_style(accent: str = None, filled: bool = False) -> str:
        accent = accent or theme.EVENT_VIOLET
        bg = accent if filled else "rgba(255,255,255,0.04)"
        color = theme.VOID_BLACK if filled else theme.TEXT_SECONDARY
        hover_color = theme.VOID_BLACK if filled else theme.TEXT_PRIMARY
        return f"""
            QPushButton {{
                background-color: {bg};
                border: 1px solid {accent};
                border-radius: 8px;
                color: {color};
                padding: 6px 14px;
            }}
            QPushButton:hover {{
                border: 1px solid {theme.ACCRETION_BLUE};
                color: {hover_color};
            }}
        """
