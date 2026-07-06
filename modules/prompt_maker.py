"""
modules/prompt_maker.py
-----------------------
The /prompt session backend. Lines accumulate locally — ZERO LLM calls
while drafting, no conversation-history pollution. /prompt_end sends one
clean call (see finalize_payload); the controller stores the result back
via ConversationDirector.note_prompt_result so save/export work on it.

Saved prompts live in their own `prompts` table (self-created, so no
init_db changes needed).
"""

import time

PROMPT_ENGINEER_SYSTEM = """You are an expert prompt engineer. The user gives you rough notes describing what they want an AI prompt to do. Produce ONE final, optimized prompt ready to paste into any LLM.

Rules:
- Output ONLY the final prompt text. No preamble, no explanation, no quotes around it.
- Structure it well: role, task, constraints, output format — whichever apply.
- Keep every requirement from the notes; sharpen vague parts; remove redundancy.
- If the notes imply examples or output format, include a section for them."""


class PromptSession:
    def __init__(self):
        self.lines = []
        self.last_result = None   # set by controller after /prompt_end builds

    # ── buffering ─────────────────────────────────────────────────────────
    def add(self, text: str) -> int:
        self.lines.append(text)
        return len(self.lines)

    def clear(self):
        self.lines = []

    def is_empty(self) -> bool:
        return not self.lines

    def buffer_text(self) -> str:
        return "\n".join(self.lines)

    # ── finalize ──────────────────────────────────────────────────────────
    def finalize_payload(self) -> tuple[str, str]:
        """(system, user) for the single build call."""
        user = ("Rough prompt notes:\n\n" + self.buffer_text() +
                "\n\nBuild the final optimized prompt.")
        return PROMPT_ENGINEER_SYSTEM, user

    # ── save / export ─────────────────────────────────────────────────────
    def _content_for_output(self) -> str | None:
        """Prefer the built result; fall back to the raw buffer."""
        if self.last_result:
            return self.last_result
        if self.lines:
            return self.buffer_text()
        return None

    def save(self) -> tuple[bool, str]:
        content = self._content_for_output()
        if not content:
            return False, "Nothing to save — build one with /prompt first."
        try:
            title = (self.lines[0][:60] if self.lines else content[:60])
            save_prompt(title, content)
            return True, f"[prompt] saved: “{title}”"
        except Exception as e:
            return False, f"[prompt] save failed: {e}"

    def export_clipboard(self) -> tuple[bool, str]:
        content = self._content_for_output()
        if not content:
            return False, "Nothing to export — build one with /prompt first."
        try:
            import pyperclip
            pyperclip.copy(content)
            return True, "[prompt] copied to clipboard."
        except Exception as e:
            return False, f"[prompt] export failed: {e}"


# ── storage (self-contained; creates its own table) ──────────────────────────

def _conn():
    from memory.store import _connect
    conn = _connect()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS prompts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TEXT
        )
    ''')
    return conn


def save_prompt(title: str, content: str) -> int:
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO prompts (title, content, created_at) VALUES (?, ?, ?)',
        (title, content, time.strftime("%Y-%m-%dT%H:%M:%S")),
    )
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def get_prompts(limit: int = 20) -> list:
    conn = _conn()
    cur = conn.cursor()
    cur.execute('SELECT id, title, content, created_at FROM prompts '
                'ORDER BY id DESC LIMIT ?', (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows
