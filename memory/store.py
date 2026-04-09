import sqlite3
import datetime
import os
DB_PATH = os.path.join(os.path.dirname(__file__), "aura_memory.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS knowledge (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            content     TEXT NOT NULL,
            summary     TEXT,
            tags        TEXT,
            source      TEXT DEFAULT 'user',
            created_at  TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reminders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            text        TEXT NOT NULL,
            remind_at   TEXT NOT NULL,
            done        INTEGER DEFAULT 0,
            created_at  TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            role        TEXT NOT NULL,
            message     TEXT NOT NULL,
            created_at  TEXT
        )
    ''')

    conn.commit()
    conn.close()


def save_entry(title: str, content: str, summary: str = "",
               tags: str = "general", source: str = "user"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO knowledge (title, content, summary, tags, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (title, content, summary, tags, source,
          datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()
    print(f"[AURA Memory] Saved: {title}")


def search_entries(query: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT title, summary, tags, created_at, content
        FROM knowledge
        WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?
        ORDER BY created_at DESC
        LIMIT 5
    ''', (f'%{query}%', f'%{query}%', f'%{query}%'))
    results = cursor.fetchall()
    conn.close()
    return results


def get_recent(limit: int = 5) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT title, summary, tags, created_at
        FROM knowledge
        ORDER BY created_at DESC
        LIMIT ?
    ''', (limit,))
    results = cursor.fetchall()
    conn.close()
    return results


def save_reminder(text: str, remind_at: datetime.datetime):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO reminders (text, remind_at, created_at)
        VALUES (?, ?, ?)
    ''', (text, remind_at.isoformat(),
          datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()
    print(f"[AURA Memory] Reminder set: {text}")


def get_due_reminders() -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()
    cursor.execute('''
        SELECT id, text FROM reminders
        WHERE remind_at <= ? AND done = 0
    ''', (now,))
    results = cursor.fetchall()
    conn.close()
    return results


def mark_reminder_done(reminder_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('UPDATE reminders SET done=1 WHERE id=?', (reminder_id,))
    conn.commit()
    conn.close()

def save_conversation(role: str, message: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO conversations (role, message, created_at)
        VALUES (?, ?, ?)
    ''', (role, message, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_recent_conversations(limit: int = 10) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT role, message, created_at
        FROM conversations
        ORDER BY created_at DESC
        LIMIT ?
    ''', (limit,))
    results = cursor.fetchall()
    conn.close()
    return list(reversed(results))

# initialize database on import
init_db()