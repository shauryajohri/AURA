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

def save_conversation(role: str, message: str):
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO conversations (role, message, created_at)
        VALUES (?, ?, ?)
    ''', (role, message, datetime.datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_recent_conversations(limit: int = 10) -> list:
    conn = _connect()
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
    conn.close()

def add_task(title: str, priority: str = "medium") -> int:
    import time
    conn = _connect()
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
    conn = _connect()
    cursor = conn.cursor()
    if status:
        cursor.execute('SELECT * FROM tasks WHERE status=? ORDER BY created_at', (status,))
    else:
        cursor.execute('SELECT * FROM tasks ORDER BY status DESC, created_at')
    results = cursor.fetchall()
    conn.close()
    return results

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

def update_task(task_id: int, title: str = None, priority: str = None):
    conn = _connect()
    try:
        if title is not None and title.strip():
            conn.execute('UPDATE tasks SET title=? WHERE id=?', (title.strip(), task_id))
        if priority is not None:
            conn.execute('UPDATE tasks SET priority=? WHERE id=?', (priority, task_id))
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


init_db()
init_tasks()
