import sqlite3
import datetime
import os
DB_PATH = os.path.join(os.path.dirname(__file__), "aura_memory.db")


def _connect() -> sqlite3.Connection:
    """Thread-friendly connection: WAL journal + busy timeout so the many
    background loops (proactive, curiosity, attention, error_detector)
    don't hit 'database is locked'."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
    except Exception:
        pass
    return conn


def init_db():
    conn = _connect()
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
    conn = _connect()
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
    conn = _connect()
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
    conn = _connect()
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
    conn = _connect()
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
    conn = _connect()
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
    conn = _connect()
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
    conn = _connect()
    conn.execute('UPDATE reminders SET done=1 WHERE id=?', (reminder_id,))
    conn.commit()
    conn.close()

# ── Chat sessions ────────────────────────────────────────────────────────────
# Every message used to land in one endless `conversations` stream, which is
# how a question from 2026-08-07 ended up being answered on 2026-08-20: the
# "recent" turns were just the last N rows, and rows have no idea which
# conversation they belonged to. Sessions give that stream boundaries the user
# can see, name and switch between.
#
# The active session id lives in app_settings under "chat.active_session" —
# reusing the settings table rather than inventing another piece of state.

_ACTIVE_KEY = "chat.active_session"
# What the pre-sessions backlog gets called, so old messages stay reachable
# instead of being orphaned by the migration.
_LEGACY_TITLE = "Earlier conversations"


def _read_active_id(conn):
    """The stored active-session id, or None.

    Tolerates both storage shapes: this module writes the id raw ("5"), while
    set_settings() JSON-encodes everything ('"5"'). Reading either means a
    stray write through the generic settings API can't silently strand the
    user in a brand-new empty chat.
    """
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key=?", (_ACTIVE_KEY,)).fetchone()
    if not row or row[0] is None:
        return None
    raw = str(row[0]).strip().strip('"')
    return int(raw) if raw.isdigit() else None


def _ensure_chat_tables(conn) -> None:
    """Create chat_sessions, add conversations.session_id, and adopt any
    pre-existing messages into one legacy session. Idempotent."""
    try:
        # app_settings holds the active-session pointer, and this can run
        # before anything has touched the settings panel.
        conn.execute(_SETTINGS_DDL)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT,
                created_at  TEXT,
                updated_at  TEXT
            )
        ''')
        have = {r[1] for r in conn.execute("PRAGMA table_info(conversations)")}
        if "session_id" not in have:
            conn.execute("ALTER TABLE conversations ADD COLUMN session_id INTEGER")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id)")
        # Adopt orphans. Runs once in practice, but stays correct if some
        # older code path ever inserts without a session.
        orphans = conn.execute(
            "SELECT COUNT(*) FROM conversations WHERE session_id IS NULL").fetchone()[0]
        if orphans:
            row = conn.execute(
                "SELECT id FROM chat_sessions WHERE title=?", (_LEGACY_TITLE,)).fetchone()
            if row:
                legacy_id = row[0]
            else:
                now = datetime.datetime.now().isoformat()
                cur = conn.execute(
                    "INSERT INTO chat_sessions (title, created_at, updated_at) VALUES (?,?,?)",
                    (_LEGACY_TITLE, now, now))
                legacy_id = cur.lastrowid
            conn.execute(
                "UPDATE conversations SET session_id=? WHERE session_id IS NULL", (legacy_id,))
        conn.commit()
    except Exception:  # noqa: BLE001 — never let a migration take the app down
        pass


def _title_from(message: str) -> str:
    """A chat's name, taken from its first user message. Titles are editable,
    so this only has to be a reasonable starting point."""
    text = " ".join((message or "").split())
    if len(text) > 42:
        text = text[:42].rsplit(" ", 1)[0] + "…"
    return text or "New chat"


def active_session_id() -> int:
    """The chat messages are being written to, creating one on first use."""
    conn = _connect()
    try:
        _ensure_chat_tables(conn)
        sid = _read_active_id(conn)
        if sid is not None and conn.execute(
                "SELECT 1 FROM chat_sessions WHERE id=?", (sid,)).fetchone():
            return sid
        now = datetime.datetime.now().isoformat()
        cur = conn.execute(
            "INSERT INTO chat_sessions (title, created_at, updated_at) VALUES (?,?,?)",
            (None, now, now))
        sid = cur.lastrowid
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?,?)",
                     (_ACTIVE_KEY, str(sid)))
        conn.commit()
        return sid
    finally:
        conn.close()


def set_active_chat_session(session_id: int) -> bool:
    conn = _connect()
    try:
        _ensure_chat_tables(conn)
        if not conn.execute("SELECT 1 FROM chat_sessions WHERE id=?", (session_id,)).fetchone():
            return False
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?,?)",
                     (_ACTIVE_KEY, str(int(session_id))))
        conn.commit()
        return True
    finally:
        conn.close()


def create_chat_session(title: str = None) -> int:
    """Start a new chat and make it active.

    If the chat already open is empty and unnamed, that IS a new chat — hand
    it back instead of stacking another one. Otherwise every press of
    "+ New chat" (and every fresh boot) would leave another blank entry in
    the history list.
    """
    conn = _connect()
    try:
        _ensure_chat_tables(conn)
        if not (title or "").strip():
            current = _read_active_id(conn)
            if current is not None:
                row = conn.execute(
                    "SELECT (SELECT COUNT(*) FROM conversations WHERE session_id=s.id), s.title "
                    "FROM chat_sessions s WHERE s.id=?", (current,)).fetchone()
                if row and row[0] == 0 and not (row[1] or "").strip():
                    return current
        now = datetime.datetime.now().isoformat()
        cur = conn.execute(
            "INSERT INTO chat_sessions (title, created_at, updated_at) VALUES (?,?,?)",
            ((title or "").strip() or None, now, now))
        sid = cur.lastrowid
        conn.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?,?)",
                     (_ACTIVE_KEY, str(sid)))
        conn.commit()
        return sid
    finally:
        conn.close()


def rename_chat_session(session_id: int, title: str) -> bool:
    conn = _connect()
    try:
        _ensure_chat_tables(conn)
        clean = " ".join((title or "").split())[:80]
        if not clean:
            return False
        conn.execute("UPDATE chat_sessions SET title=? WHERE id=?", (clean, session_id))
        conn.commit()
        return True
    finally:
        conn.close()


def delete_chat_session(session_id: int) -> bool:
    """Delete a chat and its messages. If it was the active one, the next
    write simply starts a fresh session."""
    conn = _connect()
    try:
        _ensure_chat_tables(conn)
        conn.execute("DELETE FROM conversations WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM chat_sessions WHERE id=?", (session_id,))
        if _read_active_id(conn) == int(session_id):
            conn.execute("DELETE FROM app_settings WHERE key=?", (_ACTIVE_KEY,))
        conn.commit()
        return True
    finally:
        conn.close()


def list_chat_sessions(limit: int = 60) -> list:
    """[{id, title, created_at, updated_at, message_count, named}] newest
    first. `title` is never empty — an unnamed, empty chat reads "New chat"."""
    conn = _connect()
    try:
        _ensure_chat_tables(conn)
        rows = conn.execute('''
            SELECT s.id, s.title, s.created_at, s.updated_at,
                   (SELECT COUNT(*) FROM conversations c WHERE c.session_id = s.id),
                   (SELECT c.message FROM conversations c
                     WHERE c.session_id = s.id AND c.role='user'
                     ORDER BY c.id ASC LIMIT 1)
            FROM chat_sessions s
            ORDER BY s.updated_at DESC, s.id DESC
            LIMIT ?
        ''', (limit,)).fetchall()
        out = []
        for sid, title, created, updated, count, first in rows:
            out.append({
                "id": sid,
                "title": (title or "").strip() or (_title_from(first) if first else "New chat"),
                "created_at": created,
                "updated_at": updated,
                "message_count": count or 0,
                "named": bool((title or "").strip()),
            })
        return out
    finally:
        conn.close()


def get_session_messages(session_id: int, limit: int = 200) -> list:
    """[(role, message, created_at)] oldest first, for reopening a chat."""
    conn = _connect()
    try:
        _ensure_chat_tables(conn)
        rows = conn.execute('''
            SELECT role, message, created_at FROM conversations
            WHERE session_id=? ORDER BY id DESC LIMIT ?
        ''', (session_id, limit)).fetchall()
        return list(reversed(rows))
    finally:
        conn.close()


def save_conversation(role: str, message: str, session_id: int = None):
    sid = session_id if session_id is not None else active_session_id()
    conn = _connect()
    try:
        _ensure_chat_tables(conn)
        now = datetime.datetime.now().isoformat()
        conn.execute('''
            INSERT INTO conversations (role, message, created_at, session_id)
            VALUES (?, ?, ?, ?)
        ''', (role, message, now, sid))
        conn.execute("UPDATE chat_sessions SET updated_at=? WHERE id=?", (now, sid))
        # Name the chat after its first user message, so the history list is
        # readable without anyone having to name anything by hand.
        if role == "user":
            row = conn.execute(
                "SELECT title FROM chat_sessions WHERE id=?", (sid,)).fetchone()
            if row and not (row[0] or "").strip():
                conn.execute("UPDATE chat_sessions SET title=? WHERE id=?",
                             (_title_from(message), sid))
        conn.commit()
    finally:
        conn.close()


def get_recent_conversations(limit: int = 10, session_id: int = None) -> list:
    """Recent turns from ONE chat — the active one unless told otherwise.

    Scoped by session on purpose: this is what feeds AURA's prompt, and
    bleeding another conversation into it is exactly the bug that had her
    answering a 13-day-old question.
    """
    sid = session_id if session_id is not None else active_session_id()
    conn = _connect()
    try:
        _ensure_chat_tables(conn)
        # `id` is the tie-breaker, and it is NOT optional. save_conversation
        # writes the user turn and AURA's reply microseconds apart, and they
        # frequently land on the SAME created_at string — ordering by the
        # timestamp alone let the answer come back before the question, so the
        # transcript handed to the model read backwards.
        results = conn.execute('''
            SELECT role, message, created_at
            FROM conversations
            WHERE session_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
        ''', (sid, limit)).fetchall()
        return list(reversed(results))
    finally:
        conn.close()


# ── NEW: curiosity engine read-only helpers ──────────────────────────────────
# Additive only — nothing above this changes behavior. Both read from the
# existing `conversations` table, no schema changes.

def get_conversations_since(minutes: int = 60) -> list:
    """Conversations from the last N minutes — used by curiosity engine
    for pattern detection without re-reading the whole history each cycle."""
    conn = _connect()
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
    conn = _connect()
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
    _ensure_task_columns(conn)
    conn.close()


def _ensure_task_columns(conn):
    """Add later columns to existing installs.

    `bucket`: tasks are the backlog — things to do now or later — so they need
    a place on that axis. Priority already existed but answers a different
    question (how important), not (when).

    `due` / `project` / `origin`: a task manager needs deadlines and a home
    project, and AURA-suggested tasks must be distinguishable from ones you
    typed yourself (origin: "user" | "aura").
    """
    try:
        have = {r[1] for r in conn.execute("PRAGMA table_info(tasks)")}
        if not have:
            return
        adds = {
            "bucket": "TEXT DEFAULT 'now'",
            "due": "TEXT",
            "project": "TEXT",
            "origin": "TEXT DEFAULT 'user'",
        }
        changed = False
        for col, decl in adds.items():
            if col not in have:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {decl}")
                changed = True
        if changed:
            conn.commit()
    except Exception:  # noqa: BLE001
        pass


def add_task(title: str, priority: str = "medium", bucket: str = "now",
             due: str = None, project: str = None, origin: str = "user") -> int:
    import time
    conn = _connect()
    _ensure_task_columns(conn)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO tasks (title, priority, status, created_at, bucket, due, project, origin)
        VALUES (?, ?, 'pending', ?, ?, ?, ?, ?)
    ''', (title, priority, time.strftime("%Y-%m-%dT%H:%M:%S"),
          bucket if bucket in ("now", "later") else "now",
          due or None, project or None,
          origin if origin in ("user", "aura") else "user"))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return task_id

def get_tasks(status: str = None) -> list:
    """(id, title, priority, status, created_at, done_at, bucket, due, project, origin)."""
    conn = _connect()
    _ensure_task_columns(conn)
    cursor = conn.cursor()
    cols = ("id, title, priority, status, created_at, done_at, "
            "COALESCE(bucket, 'now'), due, project, COALESCE(origin, 'user')")
    if status:
        cursor.execute(f'SELECT {cols} FROM tasks WHERE status=? ORDER BY created_at', (status,))
    else:
        cursor.execute(f'SELECT {cols} FROM tasks ORDER BY status DESC, created_at')
    results = cursor.fetchall()
    conn.close()
    return results


def set_task_bucket(task_id: int, bucket: str):
    """Move a task between 'now' and 'later'."""
    if bucket not in ("now", "later"):
        return
    conn = _connect()
    try:
        _ensure_task_columns(conn)
        conn.execute('UPDATE tasks SET bucket=? WHERE id=?', (bucket, task_id))
        conn.commit()
    finally:
        conn.close()

def complete_task(task_id: int):
    conn = _connect()
    conn.execute('''
        UPDATE tasks SET status='done', done_at=?
        WHERE id=?
    ''', (datetime.datetime.now().isoformat(), task_id))
    conn.commit()
    conn.close()

def uncomplete_task(task_id: int):
    conn = _connect()
    conn.execute('''
        UPDATE tasks SET status='pending', done_at=NULL
        WHERE id=?
    ''', (task_id,))
    conn.commit()
    conn.close()

def delete_task(task_id: int):
    conn = _connect()
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
    conn = _connect()
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
    conn = _connect()
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
    conn = _connect()
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
    conn = _connect()
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
    conn = _connect()
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
    conn = _connect()
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

# ── V2.2: life-memory layer — small persistent facts about the user ─────────

_USER_FACTS_DDL = '''
    CREATE TABLE IF NOT EXISTS user_facts (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        fact       TEXT NOT NULL UNIQUE,
        category   TEXT,
        created_at TEXT
    )
'''


def save_user_fact(fact: str, category: str = "general"):
    """One small fact ('learning: dsa for placements'). UNIQUE → re-saying
    the same thing doesn't duplicate."""
    conn = _connect()
    try:
        conn.execute(_USER_FACTS_DDL)
        conn.execute(
            'INSERT OR IGNORE INTO user_facts (fact, category, created_at) VALUES (?, ?, ?)',
            (fact.strip(), category, datetime.datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_facts(limit: int = 12) -> list:
    conn = _connect()
    try:
        conn.execute(_USER_FACTS_DDL)
        cur = conn.cursor()
        cur.execute('SELECT fact FROM user_facts ORDER BY id DESC LIMIT ?', (limit,))
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


# ── Memory-panel CRUD: full rows + edit/delete for the in-app editor ─────────

def get_user_facts_full(limit: int = 300) -> list:
    """(id, fact, category, created_at) rows — the Memory panel needs ids to
    edit/delete individual facts (get_user_facts returns only strings)."""
    conn = _connect()
    try:
        conn.execute(_USER_FACTS_DDL)
        cur = conn.cursor()
        cur.execute(
            'SELECT id, fact, category, created_at FROM user_facts '
            'ORDER BY id DESC LIMIT ?', (limit,))
        return cur.fetchall()
    finally:
        conn.close()


def update_user_fact(fact_id: int, new_fact: str):
    """Edit a fact in place. The fact column is UNIQUE, so if the edit would
    collide with an existing fact we drop this row instead of raising."""
    new_fact = (new_fact or "").strip()
    if not new_fact:
        return
    conn = _connect()
    try:
        conn.execute('UPDATE user_facts SET fact=? WHERE id=?', (new_fact, fact_id))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.execute('DELETE FROM user_facts WHERE id=?', (fact_id,))
        conn.commit()
    finally:
        conn.close()


def delete_user_fact(fact_id: int):
    conn = _connect()
    try:
        conn.execute('DELETE FROM user_facts WHERE id=?', (fact_id,))
        conn.commit()
    finally:
        conn.close()


def get_all_knowledge(limit: int = 300) -> list:
    """(id, title, summary, created_at) for the saved-notes section."""
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        'SELECT id, title, summary, created_at FROM knowledge '
        'ORDER BY created_at DESC LIMIT ?', (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_knowledge(entry_id: int):
    conn = _connect()
    conn.execute('DELETE FROM knowledge WHERE id=?', (entry_id,))
    conn.commit()
    conn.close()


def get_all_snapshots(limit: int = 60) -> list:
    """(id, app, summary, created_at) for the session-recap section."""
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            'SELECT id, app, summary, created_at FROM session_snapshots '
            'ORDER BY created_at DESC LIMIT ?', (limit,))
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        rows = []   # table not created until first save_session_snapshot
    conn.close()
    return rows


def delete_snapshot(snap_id: int):
    conn = _connect()
    try:
        conn.execute('DELETE FROM session_snapshots WHERE id=?', (snap_id,))
        conn.commit()
    finally:
        conn.close()


# ── Saved links: the Sanctuary link vault ────────────────────────────────────
# name is user-editable; the UI derives the favicon from the url's domain.

_LINKS_DDL = '''
    CREATE TABLE IF NOT EXISTS saved_links (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT NOT NULL,
        url        TEXT NOT NULL,
        created_at TEXT
    )
'''


def add_link(name: str, url: str) -> int:
    conn = _connect()
    try:
        conn.execute(_LINKS_DDL)
        cur = conn.execute(
            'INSERT INTO saved_links (name, url, created_at) VALUES (?, ?, ?)',
            (name.strip(), url.strip(), datetime.datetime.now().isoformat()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_links(limit: int = 200) -> list:
    """(id, name, url, created_at) rows, newest first."""
    conn = _connect()
    try:
        conn.execute(_LINKS_DDL)
        cur = conn.execute(
            'SELECT id, name, url, created_at FROM saved_links ORDER BY id DESC LIMIT ?',
            (limit,),
        )
        return cur.fetchall()
    finally:
        conn.close()


def update_link(link_id: int, name: str = None, url: str = None):
    conn = _connect()
    try:
        conn.execute(_LINKS_DDL)
        if name is not None:
            conn.execute('UPDATE saved_links SET name=? WHERE id=?', (name.strip(), link_id))
        if url is not None:
            conn.execute('UPDATE saved_links SET url=? WHERE id=?', (url.strip(), link_id))
        conn.commit()
    finally:
        conn.close()


def delete_link(link_id: int):
    conn = _connect()
    try:
        conn.execute(_LINKS_DDL)
        conn.execute('DELETE FROM saved_links WHERE id=?', (link_id,))
        conn.commit()
    finally:
        conn.close()


# ── Task edit (the Sanctuary card edits titles in place) ─────────────────────

def update_task(task_id: int, title: str = None, priority: str = None,
                due: str = None, project: str = None):
    """Patch a task. `due`/`project` accept "" to CLEAR the field (None means
    "don't touch"), which is what the UI's clear buttons send."""
    conn = _connect()
    try:
        _ensure_task_columns(conn)
        if title is not None and title.strip():
            conn.execute('UPDATE tasks SET title=? WHERE id=?', (title.strip(), task_id))
        if priority is not None:
            conn.execute('UPDATE tasks SET priority=? WHERE id=?', (priority, task_id))
        if due is not None:
            conn.execute('UPDATE tasks SET due=? WHERE id=?', (due.strip() or None, task_id))
        if project is not None:
            conn.execute('UPDATE tasks SET project=? WHERE id=?', (project.strip() or None, task_id))
        conn.commit()
    finally:
        conn.close()


# ── Usage stats: the memory graph ────────────────────────────────────────────
# "How much did the user use AURA, and how much did AURA remember?"

def get_usage_stats(days: int = 7) -> dict:
    """Per-day counts for the last N days + lifetime totals.
    days: [{date, user_msgs, aura_msgs, facts_saved}] oldest→newest."""
    conn = _connect()
    try:
        conn.execute(_USER_FACTS_DDL)
        cur = conn.cursor()
        today = datetime.date.today()
        out = []
        for i in range(days - 1, -1, -1):
            day = today - datetime.timedelta(days=i)
            start, end = day.isoformat(), (day + datetime.timedelta(days=1)).isoformat()
            cur.execute("SELECT COUNT(*) FROM conversations WHERE role='user' AND created_at>=? AND created_at<?", (start, end))
            user_msgs = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM conversations WHERE role='aura' AND created_at>=? AND created_at<?", (start, end))
            aura_msgs = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM user_facts WHERE created_at>=? AND created_at<?", (start, end))
            facts = cur.fetchone()[0]
            out.append({"date": day.isoformat(), "user_msgs": user_msgs,
                        "aura_msgs": aura_msgs, "facts_saved": facts})

        cur.execute("SELECT COUNT(*) FROM conversations WHERE role='user'")
        total_user = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM user_facts")
        total_facts = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM knowledge")
        total_knowledge = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM tasks")
        total_tasks = cur.fetchone()[0]
        return {"days": out, "totals": {
            "user_messages": total_user, "facts": total_facts,
            "knowledge": total_knowledge, "tasks": total_tasks,
        }}
    finally:
        conn.close()


# ── App settings: blackhole / planets / voice / auto-chat knobs ──────────────
# Flat key→value store; the Sanctuary settings card reads & writes it, and any
# part of the app (React face or PySide) can read the same source of truth.

_SETTINGS_DDL = '''
    CREATE TABLE IF NOT EXISTS app_settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    )
'''

DEFAULT_SETTINGS = {
    # Blackhole core
    "blackhole.glow": 70,          # 0-100 bloom intensity
    "blackhole.particles": 60,     # 0-100 particle density
    "blackhole.rotation": 50,      # 0-100 disk rotation speed
    # Planets (model constellation)
    "planets.orbit_speed": 50,     # 0-100
    "planets.rings": True,         # premium models wear rings
    "planets.labels": True,        # show model names
    # Voice
    "voice.enabled": True,
    "voice.rate": 55,              # 0-100 speaking speed
    # Auto-chat (proactive / attention / curiosity pushes)
    "autochat.enabled": True,
    "autochat.frequency": 40,      # 0-100 how chatty AURA is on her own
}


def get_settings() -> dict:
    """Defaults overlaid with whatever has been saved."""
    import json as _json
    conn = _connect()
    try:
        conn.execute(_SETTINGS_DDL)
        cur = conn.execute('SELECT key, value FROM app_settings')
        saved = {}
        for k, v in cur.fetchall():
            try:
                saved[k] = _json.loads(v)
            except Exception:
                saved[k] = v
        return {**DEFAULT_SETTINGS, **saved}
    finally:
        conn.close()


def set_settings(patch: dict):
    """Merge a partial {key: value} update. Unknown keys are allowed —
    future panels can invent their own without a schema change."""
    import json as _json
    conn = _connect()
    try:
        conn.execute(_SETTINGS_DDL)
        for k, v in patch.items():
            conn.execute(
                'INSERT INTO app_settings (key, value) VALUES (?, ?) '
                'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                (str(k), _json.dumps(v)),
            )
        conn.commit()
    finally:
        conn.close()


# ── Quests: the daily board AURA actually watches ────────────────────────────
# A quest is a commitment that repeats every day ("2h Japanese", "2h DSA").
# Unlike a task it isn't ticked off by hand — core/quests.py accumulates real
# seconds from the screen watcher, and the quest completes itself when the
# target is met.
#
# Two tables, and the split matters: `quests` holds the definition (stable,
# edited rarely) while `quest_days` holds one row per quest per day. Keeping
# progress in its own table is what makes streaks, history and the 7-day chart
# a plain query instead of a migration every time the concept grows.

# Work past midnight still belongs to the day you started. Without this a 1am
# DSA session would land on tomorrow's board and yesterday would look skipped —
# which is exactly backwards for how a late-night dev actually works.
DAY_ROLLOVER_HOUR = 4

_QUESTS_DDL = '''
    CREATE TABLE IF NOT EXISTS quests (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        title          TEXT NOT NULL,
        target_minutes INTEGER NOT NULL DEFAULT 60,
        keywords       TEXT DEFAULT '',
        preset         TEXT DEFAULT 'custom',
        color          TEXT DEFAULT '#8b5cff',
        active         INTEGER DEFAULT 1,
        sort_order     INTEGER DEFAULT 0,
        created_at     TEXT,
        project_path   TEXT DEFAULT '',
        kind           TEXT DEFAULT 'manual',
        target_count   INTEGER DEFAULT 0,
        proof_note     TEXT DEFAULT ''
    )
'''


# Columns added after the first release. CREATE TABLE IF NOT EXISTS won't add
# them to an existing install, so they're ALTERed in. No-ops on a fresh DB.
_QUEST_LATE_COLUMNS = (
    ("project_path", "TEXT DEFAULT ''"),
    # No DEFAULT on `kind`: existing rows must come out NULL so the backfill
    # below can tell "never set" from "deliberately manual". Defaulting it to
    # 'manual' silently converted every existing TIMED quest into a manual one
    # and stopped it being tracked.
    ("kind", "TEXT"),                       # time | proof | manual
    ("target_count", "INTEGER DEFAULT 0"),  # e.g. 2 for "leetcode 2 questions"
    ("proof_note", "TEXT DEFAULT ''"),      # last verification verdict
)


def _ensure_quest_columns(conn):
    try:
        have = {r[1] for r in conn.execute("PRAGMA table_info(quests)")}
        if not have:
            return
        for col, decl in _QUEST_LATE_COLUMNS:
            if col not in have:
                conn.execute(f"ALTER TABLE quests ADD COLUMN {col} {decl}")
        # Backfill: a row that predates `kind` keeps behaving as it did.
        # A minutes target means it was being time-tracked.
        conn.execute(
            "UPDATE quests SET kind = CASE "
            "  WHEN COALESCE(target_minutes, 0) > 0 THEN 'time' "
            "  WHEN COALESCE(target_count, 0) > 0 THEN 'proof' "
            "  ELSE 'manual' END "
            "WHERE kind IS NULL OR kind = ''"
        )
        conn.commit()
    except Exception:  # noqa: BLE001
        pass

_QUEST_DAYS_DDL = '''
    CREATE TABLE IF NOT EXISTS quest_days (
        quest_id     INTEGER NOT NULL,
        day          TEXT NOT NULL,
        seconds      INTEGER DEFAULT 0,
        done_count   INTEGER DEFAULT 0,
        completed_at TEXT,
        PRIMARY KEY (quest_id, day)
    )
'''

# One row per distinct thing finished, e.g. one accepted LeetCode problem.
# The `item` key is what makes auto-detection safe: the watcher sees the same
# "Accepted" screen every 30 seconds, and without an identity per problem it
# would count one solve a dozen times. UNIQUE does the deduplication.
_QUEST_ITEMS_DDL = '''
    CREATE TABLE IF NOT EXISTS quest_items (
        quest_id  INTEGER NOT NULL,
        day       TEXT NOT NULL,
        item      TEXT NOT NULL,
        source    TEXT DEFAULT 'auto',
        noted_at  TEXT,
        UNIQUE (quest_id, day, item)
    )
'''


def _ensure_quest_day_columns(conn):
    try:
        have = {r[1] for r in conn.execute("PRAGMA table_info(quest_days)")}
        if have and "done_count" not in have:
            conn.execute("ALTER TABLE quest_days ADD COLUMN done_count INTEGER DEFAULT 0")
            conn.commit()
    except Exception:  # noqa: BLE001
        pass

# Time that was tracked but matched no quest. Stored per day so the board can
# honestly show where the hours went without labelling anything a "distraction".
_QUEST_OTHER_DDL = '''
    CREATE TABLE IF NOT EXISTS quest_unallocated (
        day     TEXT PRIMARY KEY,
        seconds INTEGER DEFAULT 0
    )
'''


def quest_day(when: datetime.datetime = None) -> str:
    """The quest-day (YYYY-MM-DD) a moment belongs to, honouring the 4am roll."""
    now = when or datetime.datetime.now()
    if now.hour < DAY_ROLLOVER_HOUR:
        now = now - datetime.timedelta(days=1)
    return now.strftime("%Y-%m-%d")


def init_quests():
    conn = _connect()
    try:
        conn.execute(_QUESTS_DDL)
        conn.execute(_QUEST_DAYS_DDL)
        conn.execute(_QUEST_OTHER_DDL)
        conn.execute(_QUEST_ITEMS_DDL)
        _ensure_quest_columns(conn)
        _ensure_quest_day_columns(conn)
        conn.commit()
    finally:
        conn.close()


def record_quest_item(quest_id: int, item: str, source: str = "auto",
                      day: str = None) -> tuple[int, bool]:
    """Credit ONE finished thing to a proof quest.

    Returns (new_count, was_new). `was_new` is False when this exact item was
    already counted today — which is the normal case, since the screen watcher
    keeps seeing the same accepted submission until you navigate away.
    """
    day = day or quest_day()
    item = (item or "").strip().lower()[:200]
    if not item:
        return get_quest_count(quest_id, day), False
    conn = _connect()
    try:
        conn.execute(_QUEST_ITEMS_DDL)
        conn.execute(_QUEST_DAYS_DDL)
        _ensure_quest_day_columns(conn)
        try:
            conn.execute(
                'INSERT INTO quest_items (quest_id, day, item, source, noted_at) '
                'VALUES (?, ?, ?, ?, ?)',
                (quest_id, day, item, source, datetime.datetime.now().isoformat()),
            )
        except sqlite3.IntegrityError:
            return get_quest_count(quest_id, day), False   # already counted
        n = conn.execute(
            'SELECT COUNT(*) FROM quest_items WHERE quest_id = ? AND day = ?',
            (quest_id, day),
        ).fetchone()[0]
        conn.execute(
            'INSERT INTO quest_days (quest_id, day, done_count) VALUES (?, ?, ?) '
            'ON CONFLICT(quest_id, day) DO UPDATE SET done_count = excluded.done_count',
            (quest_id, day, n),
        )
        conn.commit()
        return n, True
    finally:
        conn.close()


def get_quest_count(quest_id: int, day: str = None) -> int:
    day = day or quest_day()
    conn = _connect()
    try:
        conn.execute(_QUEST_ITEMS_DDL)
        row = conn.execute(
            'SELECT COUNT(*) FROM quest_items WHERE quest_id = ? AND day = ?',
            (quest_id, day),
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def get_quest_items(quest_id: int, day: str = None) -> list:
    """(item, source, noted_at) — what got counted, so the UI can show it."""
    day = day or quest_day()
    conn = _connect()
    try:
        conn.execute(_QUEST_ITEMS_DDL)
        return conn.execute(
            'SELECT item, source, noted_at FROM quest_items '
            ' WHERE quest_id = ? AND day = ? ORDER BY noted_at',
            (quest_id, day),
        ).fetchall()
    finally:
        conn.close()


def clear_quest_items(quest_id: int, day: str = None):
    day = day or quest_day()
    conn = _connect()
    try:
        conn.execute(_QUEST_ITEMS_DDL)
        conn.execute('DELETE FROM quest_items WHERE quest_id = ? AND day = ?',
                     (quest_id, day))
        conn.execute('UPDATE quest_days SET done_count = 0 '
                     ' WHERE quest_id = ? AND day = ?', (quest_id, day))
        conn.commit()
    finally:
        conn.close()


def add_quest(title: str, target_minutes: int = 0, keywords: str = "",
              preset: str = "custom", color: str = "#8b5cff",
              project_path: str = "", kind: str = "", target_count: int = 0) -> int:
    """Create a quest.

    `kind` decides how it completes, and it's the whole point of the type:
      time    — a duration was given; AURA tracks it and completes at target
      proof   — a countable deliverable; completed by a screenshot she checks
      manual  — nothing verifiable; you tick it off yourself
    Left blank, it's inferred from whether a duration or a count was supplied.
    """
    kind = (kind or "").strip().lower()
    if kind not in ("time", "proof", "manual"):
        kind = "time" if int(target_minutes or 0) > 0 else (
            "proof" if int(target_count or 0) > 0 else "manual")
    conn = _connect()
    try:
        conn.execute(_QUESTS_DDL)
        _ensure_quest_columns(conn)
        row = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM quests").fetchone()
        cur = conn.execute(
            'INSERT INTO quests (title, target_minutes, keywords, preset, color, '
            'active, sort_order, created_at, project_path, kind, target_count) '
            'VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)',
            (title.strip(), max(0, int(target_minutes)), keywords.strip(),
             preset, color, row[0], datetime.datetime.now().isoformat(),
             (project_path or "").strip(), kind, max(0, int(target_count or 0))),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_quests(active_only: bool = True) -> list:
    """(id, title, target_minutes, keywords, preset, color, active, sort_order,
    project_path)."""
    conn = _connect()
    try:
        conn.execute(_QUESTS_DDL)
        _ensure_quest_columns(conn)
        sql = ('SELECT id, title, target_minutes, keywords, preset, color, active, '
               'sort_order, COALESCE(project_path, \'\') FROM quests')
        if active_only:
            sql += ' WHERE active = 1'
        sql += ' ORDER BY sort_order, id'
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def update_quest(quest_id: int, **patch):
    allowed = {"title", "target_minutes", "keywords", "preset", "color",
               "active", "sort_order", "project_path", "kind", "target_count",
               "proof_note"}
    fields = {k: v for k, v in patch.items() if k in allowed and v is not None}
    if not fields:
        return
    conn = _connect()
    try:
        conn.execute(_QUESTS_DDL)
        _ensure_quest_columns(conn)
        sets = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE quests SET {sets} WHERE id = ?",
                     (*fields.values(), quest_id))
        conn.commit()
    finally:
        conn.close()


def delete_quest(quest_id: int):
    """Removes the quest AND its history — the UI confirms before calling."""
    conn = _connect()
    try:
        conn.execute(_QUESTS_DDL)
        conn.execute(_QUEST_DAYS_DDL)
        conn.execute('DELETE FROM quests WHERE id = ?', (quest_id,))
        conn.execute('DELETE FROM quest_days WHERE quest_id = ?', (quest_id,))
        conn.commit()
    finally:
        conn.close()


def add_quest_seconds(quest_id: int, seconds: int, day: str = None) -> int:
    """Credit real, verified seconds to a quest. Returns the new day total."""
    if seconds <= 0:
        return get_quest_seconds(quest_id, day)
    day = day or quest_day()
    conn = _connect()
    try:
        conn.execute(_QUEST_DAYS_DDL)
        conn.execute(
            'INSERT INTO quest_days (quest_id, day, seconds) VALUES (?, ?, ?) '
            'ON CONFLICT(quest_id, day) DO UPDATE SET seconds = seconds + excluded.seconds',
            (quest_id, day, int(seconds)),
        )
        conn.commit()
        row = conn.execute(
            'SELECT seconds FROM quest_days WHERE quest_id = ? AND day = ?',
            (quest_id, day),
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def get_quest_seconds(quest_id: int, day: str = None) -> int:
    day = day or quest_day()
    conn = _connect()
    try:
        conn.execute(_QUEST_DAYS_DDL)
        row = conn.execute(
            'SELECT seconds FROM quest_days WHERE quest_id = ? AND day = ?',
            (quest_id, day),
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def complete_quest(quest_id: int, day: str = None, undo: bool = False):
    day = day or quest_day()
    stamp = None if undo else datetime.datetime.now().isoformat()
    conn = _connect()
    try:
        conn.execute(_QUEST_DAYS_DDL)
        conn.execute(
            'INSERT INTO quest_days (quest_id, day, seconds, completed_at) '
            'VALUES (?, ?, 0, ?) '
            'ON CONFLICT(quest_id, day) DO UPDATE SET completed_at = excluded.completed_at',
            (quest_id, day, stamp),
        )
        conn.commit()
    finally:
        conn.close()


def add_unallocated_seconds(seconds: int, day: str = None) -> int:
    """Screen time that matched no quest. Recorded, never judged."""
    if seconds <= 0:
        return 0
    day = day or quest_day()
    conn = _connect()
    try:
        conn.execute(_QUEST_OTHER_DDL)
        conn.execute(
            'INSERT INTO quest_unallocated (day, seconds) VALUES (?, ?) '
            'ON CONFLICT(day) DO UPDATE SET seconds = seconds + excluded.seconds',
            (day, int(seconds)),
        )
        conn.commit()
        row = conn.execute(
            'SELECT seconds FROM quest_unallocated WHERE day = ?', (day,)
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def get_quest_board(day: str = None) -> dict:
    """Everything the Quests tab needs for one day, in a single round-trip."""
    day = day or quest_day()
    conn = _connect()
    try:
        conn.execute(_QUESTS_DDL)
        conn.execute(_QUEST_DAYS_DDL)
        conn.execute(_QUEST_OTHER_DDL)
        conn.execute(_QUEST_ITEMS_DDL)
        _ensure_quest_columns(conn)
        _ensure_quest_day_columns(conn)
        rows = conn.execute(
            'SELECT q.id, q.title, q.target_minutes, q.keywords, q.preset, q.color, '
            '       q.sort_order, COALESCE(d.seconds, 0), d.completed_at, '
            '       COALESCE(q.project_path, \'\'), COALESCE(q.kind, \'manual\'), '
            '       COALESCE(q.target_count, 0), COALESCE(q.proof_note, \'\'), '
            '       (SELECT COUNT(*) FROM quest_items i '
            '         WHERE i.quest_id = q.id AND i.day = ?) '
            '  FROM quests q '
            '  LEFT JOIN quest_days d ON d.quest_id = q.id AND d.day = ? '
            ' WHERE q.active = 1 '
            ' ORDER BY q.sort_order, q.id',
            (day, day),   # first `day` is the item-count subquery
        ).fetchall()
        other = conn.execute(
            'SELECT seconds FROM quest_unallocated WHERE day = ?', (day,)
        ).fetchone()
    finally:
        conn.close()

    quests = []
    for r in rows:
        target_s = int(r[2]) * 60
        done_s = int(r[7])
        kind = (r[10] or "manual").lower()
        timed = kind == "time" and target_s > 0
        want = int(r[11] or 0)
        have = int(r[13] or 0)
        # A proof quest completes when enough distinct items are counted —
        # whether they were auto-detected from the screen or verified from a
        # screenshot. Both routes land in the same ledger.
        count_done = kind == "proof" and want > 0 and have >= want
        # Only a `time` quest is measured against a clock. `proof` and `manual`
        # quests complete on a verified screenshot or on your own say-so, so a
        # progress bar would be meaningless for them — and crucially they must
        # never auto-complete just because time passed.
        quests.append({
            "id": r[0], "title": r[1], "target_minutes": r[2],
            "keywords": r[3] or "", "preset": r[4], "color": r[5],
            "sort_order": r[6], "project_path": r[9] or "",
            "kind": kind,
            "target_count": want,
            "done_count": have,
            "count_percent": min(100, round(have / want * 100)) if want else 0,
            "proof_note": r[12] or "",
            "seconds": done_s,
            "target_seconds": target_s,
            "untimed": not timed,
            "percent": min(100, round(done_s / target_s * 100)) if timed else 0,
            "remaining_seconds": max(0, target_s - done_s) if timed else 0,
            "overtime_seconds": max(0, done_s - target_s) if timed else 0,
            # Time quests complete on the clock, proof quests on the count,
            # manual quests only when you say so.
            "completed": (bool(r[8]) or done_s >= target_s) if timed
                         else (bool(r[8]) or count_done),
            "completed_at": r[8],
        })
    return {
        "day": day,
        "quests": quests,
        "unallocated_seconds": other[0] if other else 0,
    }


def get_quest_history(days: int = 30) -> list:
    """[{day, quest_id, seconds, completed}] for the last N quest-days."""
    start = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    conn = _connect()
    try:
        conn.execute(_QUEST_DAYS_DDL)
        rows = conn.execute(
            'SELECT day, quest_id, seconds, completed_at FROM quest_days '
            ' WHERE day >= ? ORDER BY day',
            (start,),
        ).fetchall()
    finally:
        conn.close()
    return [{"day": r[0], "quest_id": r[1], "seconds": r[2],
             "completed": bool(r[3])} for r in rows]


def get_quest_streak(quest_id: int, target_minutes: int = None) -> int:
    """Consecutive quest-days (ending yesterday or today) that hit the target.

    Today counts only if it's already done — an unfinished today shouldn't
    break a streak you might still complete this evening.

    For an untimed quest there's no target, so "showing up at all" is the bar:
    any day with time on it counts.
    """
    conn = _connect()
    try:
        conn.execute(_QUESTS_DDL)
        conn.execute(_QUEST_DAYS_DDL)
        if target_minutes is None:
            row = conn.execute(
                'SELECT target_minutes FROM quests WHERE id = ?', (quest_id,)
            ).fetchone()
            target_minutes = row[0] if row else 60
        rows = conn.execute(
            'SELECT day, seconds, completed_at FROM quest_days '
            ' WHERE quest_id = ? ORDER BY day DESC LIMIT 400',
            (quest_id,),
        ).fetchall()
    finally:
        conn.close()

    target_s = max(0, int(target_minutes or 0)) * 60
    if target_s <= 0:
        done = {r[0] for r in rows if int(r[1]) > 0 or bool(r[2])}
    else:
        done = {r[0] for r in rows if bool(r[2]) or int(r[1]) >= target_s}
    if not done:
        return 0

    today = quest_day()
    cursor = datetime.datetime.strptime(today, "%Y-%m-%d")
    if today not in done:
        cursor -= datetime.timedelta(days=1)   # today's still open — start at yesterday
    streak = 0
    while cursor.strftime("%Y-%m-%d") in done:
        streak += 1
        cursor -= datetime.timedelta(days=1)
    return streak


init_db()
init_tasks()
init_quests()
