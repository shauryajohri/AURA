"""
core/nature.py
--------------
V2.3 — user-selectable AURA natures.

"Auto" (default) = no overlay: the existing intent lanes (PERSONAL / CASUAL /
CODING) shift tone dynamically — that behavior IS auto mode.

A manual nature is a LOCK: its overlay is appended to the system prompt on
every call and explicitly overrides conflicting tone rules, so AURA cannot
drift out of it no matter what the task is. Selection persists across
restarts (tiny self-created settings table).
"""

NATURES = {
    "auto": {
        "label": "Auto",
        "icon": "🟢",
        "overlay": "",
    },
    "chill": {
        "label": "Chill",
        "icon": "😎",
        "overlay": """

NATURE LOCK — CHILL (user-selected; overrides ANY conflicting tone rules above):
Laid-back friend energy no matter the task. Slow-night vibes, jokes welcome,
zero productivity pushing. Even code questions get answered relaxed —
competent but never intense. Do not deviate until the user changes nature.""",
    },
    "focus": {
        "label": "Focus",
        "icon": "🎯",
        "overlay": """

NATURE LOCK — FOCUS (user-selected; overrides ANY conflicting tone rules above):
All business. Minimal words, direct answers, no teasing, no small talk,
no questions unless essential to the task. Code and results first.
Do not deviate until the user changes nature.""",
    },
    "savage": {
        "label": "Savage",
        "icon": "🔥",
        "overlay": """

NATURE LOCK — SAVAGE (user-selected; overrides ANY conflicting tone rules above):
Roast mode. Heavy banter, merciless (never cruel) teasing, dry burns.
Still genuinely helpful — roast the code AND fix it. The user asked for
this. Do not deviate until the user changes nature.""",
    },
    "professional": {
        "label": "Professional",
        "icon": "👔",
        "overlay": """

NATURE LOCK — PROFESSIONAL (user-selected; overrides ANY conflicting tone rules above):
Polite, articulate, complete sentences. No slang, no teasing, no sarcasm.
Suitable for screen shares, demos, and presentations.
Do not deviate until the user changes nature.""",
    },
}

DEFAULT = "auto"
_current = None   # lazy-loaded cache


# ── persistence (tiny self-created kv table) ─────────────────────────────────

_SETTINGS_DDL = '''
    CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    )
'''


def _load() -> str:
    try:
        from memory.store import _connect
        conn = _connect()
        try:
            conn.execute(_SETTINGS_DDL)
            row = conn.execute(
                "SELECT value FROM settings WHERE key='nature'").fetchone()
            return row[0] if row and row[0] in NATURES else DEFAULT
        finally:
            conn.close()
    except Exception:
        return DEFAULT


def get_nature() -> str:
    global _current
    if _current is None:
        _current = _load()
    return _current


def set_nature(name: str) -> bool:
    global _current
    if name not in NATURES:
        return False
    _current = name
    try:
        from memory.store import _connect
        conn = _connect()
        try:
            conn.execute(_SETTINGS_DDL)
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('nature', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (name,))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"[AURA Nature] persist failed (in-memory only): {e}")
    # relationship block toggles with auto/manual — refresh it immediately
    try:
        from core.ai_router import _rel_cache
        _rel_cache["ts"] = 0.0
    except Exception:
        pass
    print(f"[AURA] Nature set: {NATURES[name]['label']}"
          + ("" if name == "auto" else " (locked)"))
    return True


def overlay() -> str:
    """The system-prompt overlay for the current nature ('' on auto)."""
    return NATURES[get_nature()]["overlay"]


def describe() -> str:
    n = NATURES[get_nature()]
    return f"{n['icon']} {n['label']}"
