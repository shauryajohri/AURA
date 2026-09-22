"""
core/system_reset.py — giving AURA a clean slate.

Reset is scoped, not all-or-nothing: wiping the conversations you're tired of
should not cost you the facts AURA has learned about you, and clearing settings
should not delete your projects. Each scope below is one checkbox in
Settings → Reset AURA.

Whatever the scope, the database is copied first. A reset you regret is a file
copy away from being undone, and the backup path comes back in the response so
it can be said out loud rather than buried in a log.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import time
from typing import Any

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_HERE, "memory", "aura_memory.db")
BACKUP_DIR = os.path.join(_HERE, "memory", "resets")
SAVED_FILES = os.path.join(_HERE, "memory", "saved_files")
PATCH_STORE = os.path.join(_HERE, "memory", "patches")


# Each scope names the tables it empties and the folders it clears. Tables that
# don't exist are skipped silently — AURA's schema has grown over time and an
# older database simply won't have all of them.
SCOPES: dict[str, dict[str, Any]] = {
    "chats": {
        "label": "Conversations",
        "desc": "Every chat and its messages. Rooms stay.",
        "tables": ["conversations", "chat_sessions"],
        "dirs": [],
    },
    "memory": {
        "label": "What AURA knows about you",
        "desc": "Learned facts, notes, recaps, session snapshots and working memory.",
        "tables": ["user_facts", "knowledge", "session_snapshots",
                   "working_memory", "interaction_patterns", "personality_state"],
        "dirs": [],
    },
    "saved": {
        "label": "Saved Info",
        "desc": "Saved links, PDFs and documents, including the stored copies.",
        "tables": ["saved_info", "saved_links"],
        "dirs": [SAVED_FILES],
    },
    "rooms": {
        "label": "Rooms",
        "desc": "Room folders. The chats inside them survive, unfiled.",
        "tables": ["chat_rooms"],
        "dirs": [],
    },
    "sources": {
        "label": "Connected sources",
        "desc": "Your GitHub link and any synced document sources.",
        "tables": ["sources"],
        "dirs": [],
    },
    "projects": {
        "label": "Domain projects",
        "desc": "Projects and their knowledge graph. Your actual code on disk is untouched.",
        "tables": ["domain_nodes", "domain_edges", "domain_projects"],
        "dirs": [],
    },
    "tasks": {
        "label": "Tasks and quests",
        "desc": "Everything on the task board and the quest log.",
        "tables": ["tasks", "quests", "quest_items", "quest_days",
                   "quest_unallocated", "reminders"],
        "dirs": [],
    },
    "upgrades": {
        "label": "Upgrade history",
        "desc": "Proposed and applied code upgrades. Applied ones can no longer be rolled back.",
        "tables": [],
        "dirs": [PATCH_STORE],
    },
    "settings": {
        "label": "Settings",
        "desc": "Appearance, voice and behaviour, back to defaults.",
        "tables": ["app_settings", "settings"],
        "dirs": [],
    },
}


def scopes() -> list[dict]:
    """What can be reset, for the UI."""
    return [{"id": k, "label": v["label"], "desc": v["desc"]} for k, v in SCOPES.items()]


def _backup() -> str:
    """Copy the database aside. Returns the path, or "" if there was nothing
    to copy."""
    if not os.path.isfile(DB_PATH):
        return ""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    dest = os.path.join(BACKUP_DIR, f"aura_memory_{time.strftime('%Y%m%d_%H%M%S')}.db")
    # sqlite3's own backup API, not a file copy: a copy taken while a write is
    # in flight can land mid-transaction and restore as a corrupt database.
    src = sqlite3.connect(DB_PATH, timeout=10)
    try:
        out = sqlite3.connect(dest)
        with out:
            src.backup(out)
        out.close()
    finally:
        src.close()
    return dest


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {r[0] for r in rows}


def reset(selected: list[str]) -> dict:
    """Clear the named scopes. Returns what was cleared and where the backup went."""
    chosen = [s for s in selected if s in SCOPES]
    if not chosen:
        return {"ok": False, "error": "nothing was selected"}

    try:
        backup = _backup()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"couldn't back up the database first: {e}"}

    cleared: list[str] = []
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        present = _tables(conn)
        with conn:
            for scope in chosen:
                for table in SCOPES[scope]["tables"]:
                    if table in present:
                        conn.execute(f"DELETE FROM {table}")
                cleared.append(scope)
        conn.execute("VACUUM")
    finally:
        conn.close()

    for scope in chosen:
        for folder in SCOPES[scope]["dirs"]:
            shutil.rmtree(folder, ignore_errors=True)
            os.makedirs(folder, exist_ok=True)

    # The brain caches conversation history in memory; without this the old
    # turns keep answering until the next restart.
    if "chats" in chosen:
        try:
            from core import brain
            brain.reset_history()
        except Exception:  # noqa: BLE001
            pass

    # Rebuild whatever schema the wipe emptied, so the next call doesn't meet
    # a missing table.
    try:
        from memory import store
        store.init_db()
        store.init_tasks()
    except Exception:  # noqa: BLE001
        pass

    return {"ok": True, "cleared": cleared, "backup": backup,
            "labels": [SCOPES[s]["label"] for s in cleared]}
