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


def analyze_conversation_patterns(limit: int = 50) -> dict:
    """Extract patterns from recent conversations for personality awareness"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT role, message FROM conversations
        ORDER BY created_at DESC
        LIMIT ?
    ''', (limit,))

    conversations = list(reversed(cursor.fetchall()))
    conn.close()

    if not conversations:
        return {
            'topics': [],
            'preferred_style': 'brief',
            'humor_score': 5,
            'tech_level': 'intermediate'
        }

    # Extract topics from conversation
    topics = []
    tech_keywords = {
        'code', 'bug', 'error', 'debug', 'function', 'variable', 'class',
        'api', 'database', 'server', 'javascript', 'python', 'react', 'node'
    }
    casual_indicators = {'how are you', 'what are you', 'tell me about'}
    coding_count = 0
    casual_count = 0
    question_count = 0

    for role, message in conversations:
        if role == 'user':
            lower = message.lower()
            question_count += lower.count('?')

            for keyword in tech_keywords:
                if keyword in lower:
                    coding_count += 1
                    if keyword not in topics:
                        topics.append(keyword)

            for casual in casual_indicators:
                if casual in lower:
                    casual_count += 1

    # Infer preferences
    total = len(conversations) // 2
    tech_ratio = coding_count / max(total, 1)
    casual_ratio = casual_count / max(total, 1)

    preferred_style = "detailed" if tech_ratio > 0.3 else "brief"
    humor_score = min(10, max(1, 7 - int(tech_ratio * 5)))
    tech_level = "advanced" if tech_ratio > 0.5 else ("intermediate" if tech_ratio > 0.2 else "beginner")

    return {
        'topics': list(set(topics)),
        'preferred_style': preferred_style,
        'humor_score': humor_score,
        'tech_level': tech_level,
        'coding_frequency': round(tech_ratio, 2),
        'question_frequency': round(question_count / max(len(conversations), 1), 2)
    }


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


# ── NEW: curiosity engine read-only helpers ──────────────────────────────────
# Additive only — nothing above this changes behavior. Both read from the
# existing `conversations` table, no schema changes.

def get_conversations_since(minutes: int = 60) -> list:
    """Conversations from the last N minutes — used by curiosity engine
    for pattern detection without re-reading the whole history each cycle."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cutoff = (datetime.datetime.now() - datetime.timedelta(minutes=minutes)).isoformat()
    cursor.execute('''
        SELECT role, message, created_at
        FROM conversations
        WHERE created_at >= ?
        ORDER BY created_at ASC
    ''', (cutoff,))
    results = cursor.fetchall()
    conn.close()
    return results


def count_recent_restarts(window_minutes: int = 60, keyword: str = "restart") -> int:
    """Lightweight pattern-curiosity helper: counts how many user messages
    in the recent window mention restart/rerun/crash-adjacent language."""
    rows = get_conversations_since(window_minutes)
    keywords = [keyword] if keyword != "restart" else [
        "restart", "rerun", "crash", "crashed", "won't start", "keeps failing"
    ]
    return sum(
        1 for role, msg, _ in rows
        if role == "user" and any(k in msg.lower() for k in keywords)
    )


# initialize database on import
init_db()

def init_tasks():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            priority    TEXT DEFAULT 'medium',
            status      TEXT DEFAULT 'pending',
            created_at  TEXT,
            done_at     TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS interaction_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            aura_response TEXT NOT NULL,
            user_follow_up TEXT NOT NULL,
            frequency INTEGER DEFAULT 1,
            success_rate REAL DEFAULT 0.5,
            last_seen TEXT
        )
    ''')

    conn.commit()
    conn.close()

def add_task(title: str, priority: str = "medium") -> int:
    import time
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO tasks (title, priority, status, created_at)
        VALUES (?, ?, 'pending', ?)
    ''', (title, priority, time.strftime("%Y-%m-%dT%H:%M:%S")))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return task_id

def get_tasks(status: str = None) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if status:
        cursor.execute('SELECT * FROM tasks WHERE status=? ORDER BY created_at', (status,))
    else:
        cursor.execute('SELECT * FROM tasks ORDER BY status DESC, created_at')
    results = cursor.fetchall()
    conn.close()
    return results

def complete_task(task_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        UPDATE tasks SET status='done', done_at=?
        WHERE id=?
    ''', (datetime.datetime.now().isoformat(), task_id))
    conn.commit()
    conn.close()

def uncomplete_task(task_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        UPDATE tasks SET status='pending', done_at=NULL
        WHERE id=?
    ''', (task_id,))
    conn.commit()
    conn.close()

def delete_task(task_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('DELETE FROM tasks WHERE id=?', (task_id,))
    conn.commit()
    conn.close()

def get_pending_tasks() -> list:
    return get_tasks(status='pending')

def get_task_summary() -> str:
    pending = get_tasks('pending')
    done    = get_tasks('done')
    if not pending:
        return "No pending tasks. All clear."
    summary = f"{len(pending)} tasks pending, {len(done)} done today. "
    summary += "Pending: " + ", ".join([t[1] for t in pending])
    return summary

def log_interaction_pattern(aura_response: str, user_follow_up: str, success: bool = True):
    """Log a follow-up pattern to learn from user behavior"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT id, frequency, success_rate FROM interaction_patterns
        WHERE aura_response=? AND user_follow_up=?
    ''', (aura_response[:100], user_follow_up[:100]))

    existing = cursor.fetchone()

    if existing:
        pattern_id, freq, rate = existing
        new_freq = freq + 1
        new_success = ((rate * freq) + (1 if success else 0)) / new_freq
        cursor.execute('''
            UPDATE interaction_patterns
            SET frequency=?, success_rate=?, last_seen=?
            WHERE id=?
        ''', (new_freq, new_success, datetime.datetime.now().isoformat(), pattern_id))
    else:
        cursor.execute('''
            INSERT INTO interaction_patterns
            (aura_response, user_follow_up, frequency, success_rate, last_seen)
            VALUES (?, ?, 1, ?, ?)
        ''', (aura_response[:100], user_follow_up[:100], 1.0 if success else 0.0,
              datetime.datetime.now().isoformat()))

    conn.commit()
    conn.close()

def get_learned_follow_ups(aura_response: str, limit: int = 3) -> list:
    """Get the most likely follow-ups based on learned patterns"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT user_follow_up, frequency, success_rate
        FROM interaction_patterns
        WHERE aura_response LIKE ?
        ORDER BY (frequency * success_rate) DESC
        LIMIT ?
    ''', (f"%{aura_response[:50]}%", limit))

    results = cursor.fetchall()
    conn.close()

    return results if results else []

def save_session_snapshot(app: str, summary: str, topics: list):
    """Save what user was doing when AURA closes"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS session_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            app         TEXT,
            summary     TEXT,
            topics      TEXT,
            created_at  TEXT
        )
    ''')
    cursor.execute('''
        INSERT INTO session_snapshots (app, summary, topics, created_at)
        VALUES (?, ?, ?, ?)
    ''', (app, summary, ",".join(topics), datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()
    print(f"[AURA Memory] Session snapshot saved")


def get_last_session() -> dict | None:
    """Retrieve what user was doing in the last session"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            SELECT app, summary, topics, created_at
            FROM session_snapshots
            ORDER BY created_at DESC
            LIMIT 1
        ''')
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "app": row[0],
            "summary": row[1],
            "topics": row[2].split(",") if row[2] else [],
            "created_at": row[3]
        }
    except:
        conn.close()
        return None


def save_working_memory(data: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS working_memory (
            id         INTEGER PRIMARY KEY,
            data       TEXT NOT NULL,
            updated_at TEXT
        )
    ''')
    cursor.execute('''
        INSERT OR REPLACE INTO working_memory (id, data, updated_at)
        VALUES (1, ?, ?)
    ''', (data, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_working_memory() -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS working_memory (
                id         INTEGER PRIMARY KEY CHECK (id = 1),
                data       TEXT NOT NULL,
                updated_at TEXT
            )
        ''')
        cursor.execute('SELECT data FROM working_memory WHERE id=1')
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        import json
        return json.loads(row[0])
    except:
        conn.close()
        return None

init_db()
init_tasks()
