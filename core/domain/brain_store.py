"""
core.domain.brain_store
-----------------------
The persistence spine of AURA Domain V2 — a small knowledge GRAPH stored in the
same SQLite database the rest of AURA already uses (memory/aura_memory.db).

Three tables:

    domain_projects   one row per project (a repo / workspace)
    domain_nodes      every "thing": idea, discussion, decision, feature,
                      task, file, commit, test, milestone
    domain_edges      typed links between nodes (led_to, implements, affects,
                      completes, depends_on, belongs_to, rejected_alt ...)

Everything upstream (project_brain, planning, git_scan, analyzer, progress)
reads and writes through this module, so the graph is the single source of
truth. Deliberately dependency-free apart from stdlib + the shared connection.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from typing import Any, Iterable

# Reuse AURA's existing DB + WAL/busy-timeout connection so the Domain graph
# lives alongside memory and never fights the background loops for the file.
try:
    from memory.store import _connect, DB_PATH  # type: ignore
except Exception:  # pragma: no cover - standalone/import-order safety net
    DB_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "memory", "aura_memory.db",
    )

    def _connect() -> sqlite3.Connection:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=10000")
        except Exception:
            pass
        return conn


# ── vocabulary ───────────────────────────────────────────────────────────────
# Kept as plain sets (not enums) so callers stay stringly-typed and the API
# surface is trivial to hit from REST without imports.
NODE_TYPES = {
    "project", "idea", "discussion", "decision", "feature",
    "task", "file", "commit", "test", "milestone",
}
EDGE_TYPES = {
    "led_to",       # idea/discussion -> decision/feature (causal chain)
    "belongs_to",   # task -> feature, feature -> project
    "implements",   # commit/file -> task/feature
    "affects",      # commit -> file/feature
    "completes",    # commit -> task
    "depends_on",   # task -> task
    "rejected_alt", # decision -> rejected alternative (a decision node)
    "relates_to",   # generic association
    "authored",     # commit -> (author stored in meta) ; reserved
}

# Task lifecycle used by progress.py.
TASK_STATES = {"planning", "todo", "in_progress", "blocked", "done", "rejected"}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


# ── schema ───────────────────────────────────────────────────────────────────
def init_db() -> None:
    """Create the Domain tables if they don't exist. Safe to call repeatedly;
    server.py should call this once on boot (alongside memory.store.init_db)."""
    conn = _connect()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS domain_projects (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            root        TEXT,
            repo_url    TEXT,
            meta        TEXT DEFAULT '{}',
            created_at  TEXT,
            updated_at  TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS domain_nodes (
            id          TEXT PRIMARY KEY,
            project     TEXT NOT NULL,
            type        TEXT NOT NULL,
            title       TEXT NOT NULL,
            body        TEXT DEFAULT '',
            status      TEXT DEFAULT '',
            meta        TEXT DEFAULT '{}',
            created_at  TEXT,
            updated_at  TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS domain_edges (
            id          TEXT PRIMARY KEY,
            project     TEXT NOT NULL,
            src         TEXT NOT NULL,
            dst         TEXT NOT NULL,
            type        TEXT NOT NULL,
            meta        TEXT DEFAULT '{}',
            created_at  TEXT
        )
    """)
    # Indices for the two hot paths: "all nodes of a type in a project" and
    # "edges touching a node".
    c.execute("CREATE INDEX IF NOT EXISTS idx_nodes_proj_type ON domain_nodes(project, type)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_edges_src ON domain_edges(src)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_edges_dst ON domain_edges(dst)")
    conn.commit()
    conn.close()


def _loads(s: str | None) -> dict:
    if not s:
        return {}
    try:
        return json.loads(s)
    except Exception:
        return {}


def _row_to_node(r: sqlite3.Row | tuple) -> dict[str, Any]:
    return {
        "id": r[0], "project": r[1], "type": r[2], "title": r[3],
        "body": r[4], "status": r[5], "meta": _loads(r[6]),
        "created_at": r[7], "updated_at": r[8],
    }


def _row_to_edge(r: sqlite3.Row | tuple) -> dict[str, Any]:
    return {
        "id": r[0], "project": r[1], "src": r[2], "dst": r[3],
        "type": r[4], "meta": _loads(r[5]), "created_at": r[6],
    }


def _row_to_project(r: sqlite3.Row | tuple) -> dict[str, Any]:
    return {
        "id": r[0], "name": r[1], "root": r[2], "repo_url": r[3],
        "meta": _loads(r[4]), "created_at": r[5], "updated_at": r[6],
    }


# ── projects ─────────────────────────────────────────────────────────────────
def create_project(name: str, root: str = "", repo_url: str = "",
                   meta: dict | None = None) -> dict[str, Any]:
    init_db()
    pid = _uid("proj")
    now = _now()
    conn = _connect()
    conn.execute(
        "INSERT INTO domain_projects (id, name, root, repo_url, meta, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (pid, name, root, repo_url, json.dumps(meta or {}), now, now),
    )
    conn.commit()
    conn.close()
    return get_project(pid)


def get_project(pid: str) -> dict[str, Any] | None:
    conn = _connect()
    r = conn.execute("SELECT * FROM domain_projects WHERE id=?", (pid,)).fetchone()
    conn.close()
    return _row_to_project(r) if r else None


def list_projects() -> list[dict[str, Any]]:
    init_db()
    conn = _connect()
    rows = conn.execute("SELECT * FROM domain_projects ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [_row_to_project(r) for r in rows]


def update_project(pid: str, **fields) -> dict[str, Any] | None:
    p = get_project(pid)
    if not p:
        return None
    meta = fields.pop("meta", None)
    if meta is not None:
        merged = {**p["meta"], **meta}
        fields["meta"] = json.dumps(merged)
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values())
    conn = _connect()
    conn.execute(
        f"UPDATE domain_projects SET {sets}, updated_at=? WHERE id=?",
        (*vals, _now(), pid),
    )
    conn.commit()
    conn.close()
    return get_project(pid)


def _touch_project(pid: str) -> None:
    conn = _connect()
    conn.execute("UPDATE domain_projects SET updated_at=? WHERE id=?", (_now(), pid))
    conn.commit()
    conn.close()


# ── nodes ────────────────────────────────────────────────────────────────────
def add_node(project: str, type: str, title: str, body: str = "",
             status: str = "", meta: dict | None = None) -> dict[str, Any]:
    if type not in NODE_TYPES:
        raise ValueError(f"unknown node type {type!r} (want one of {sorted(NODE_TYPES)})")
    init_db()
    nid = _uid("n")
    now = _now()
    conn = _connect()
    conn.execute(
        "INSERT INTO domain_nodes (id, project, type, title, body, status, meta, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (nid, project, type, title, body, status, json.dumps(meta or {}), now, now),
    )
    conn.commit()
    conn.close()
    _touch_project(project)
    return get_node(nid)


def get_node(nid: str) -> dict[str, Any] | None:
    conn = _connect()
    r = conn.execute("SELECT * FROM domain_nodes WHERE id=?", (nid,)).fetchone()
    conn.close()
    return _row_to_node(r) if r else None


def update_node(nid: str, **fields) -> dict[str, Any] | None:
    n = get_node(nid)
    if not n:
        return None
    meta = fields.pop("meta", None)
    if meta is not None:
        fields["meta"] = json.dumps({**n["meta"], **meta})
    if not fields:
        return n
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values())
    conn = _connect()
    conn.execute(
        f"UPDATE domain_nodes SET {sets}, updated_at=? WHERE id=?",
        (*vals, _now(), nid),
    )
    conn.commit()
    conn.close()
    _touch_project(n["project"])
    return get_node(nid)


def delete_node(nid: str) -> bool:
    n = get_node(nid)
    if not n:
        return False
    conn = _connect()
    conn.execute("DELETE FROM domain_nodes WHERE id=?", (nid,))
    conn.execute("DELETE FROM domain_edges WHERE src=? OR dst=?", (nid, nid))
    conn.commit()
    conn.close()
    return True


def nodes(project: str, type: str | None = None,
          status: str | None = None) -> list[dict[str, Any]]:
    init_db()
    q = "SELECT * FROM domain_nodes WHERE project=?"
    args: list[Any] = [project]
    if type:
        q += " AND type=?"
        args.append(type)
    if status:
        q += " AND status=?"
        args.append(status)
    q += " ORDER BY created_at ASC"
    conn = _connect()
    rows = conn.execute(q, args).fetchall()
    conn.close()
    return [_row_to_node(r) for r in rows]


def find_node(project: str, type: str, **meta_match) -> dict[str, Any] | None:
    """First node of a type whose meta matches all given keys — used to
    de-dupe file/commit nodes on re-scan (e.g. find by meta.sha)."""
    for n in nodes(project, type):
        if all(n["meta"].get(k) == v for k, v in meta_match.items()):
            return n
    return None


# ── edges ────────────────────────────────────────────────────────────────────
def add_edge(project: str, src: str, dst: str, type: str,
             meta: dict | None = None) -> dict[str, Any]:
    if type not in EDGE_TYPES:
        raise ValueError(f"unknown edge type {type!r} (want one of {sorted(EDGE_TYPES)})")
    init_db()
    eid = _uid("e")
    conn = _connect()
    conn.execute(
        "INSERT INTO domain_edges (id, project, src, dst, type, meta, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (eid, project, src, dst, type, json.dumps(meta or {}), _now()),
    )
    conn.commit()
    conn.close()
    return {"id": eid, "project": project, "src": src, "dst": dst,
            "type": type, "meta": meta or {}, "created_at": _now()}


def edges(project: str, type: str | None = None) -> list[dict[str, Any]]:
    q = "SELECT * FROM domain_edges WHERE project=?"
    args: list[Any] = [project]
    if type:
        q += " AND type=?"
        args.append(type)
    conn = _connect()
    rows = conn.execute(q, args).fetchall()
    conn.close()
    return [_row_to_edge(r) for r in rows]


def edges_of(nid: str, direction: str = "both") -> list[dict[str, Any]]:
    """Edges touching a node. direction: 'out' (src=nid), 'in' (dst=nid), 'both'."""
    conn = _connect()
    if direction == "out":
        rows = conn.execute("SELECT * FROM domain_edges WHERE src=?", (nid,)).fetchall()
    elif direction == "in":
        rows = conn.execute("SELECT * FROM domain_edges WHERE dst=?", (nid,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM domain_edges WHERE src=? OR dst=?", (nid, nid)
        ).fetchall()
    conn.close()
    return [_row_to_edge(r) for r in rows]


def neighbors(nid: str, edge_type: str | None = None,
              direction: str = "both") -> list[dict[str, Any]]:
    """Nodes one hop from `nid`, optionally filtered by edge type/direction."""
    out: list[dict[str, Any]] = []
    for e in edges_of(nid, direction):
        if edge_type and e["type"] != edge_type:
            continue
        other = e["dst"] if e["src"] == nid else e["src"]
        n = get_node(other)
        if n:
            out.append({**n, "_via": e["type"]})
    return out


# Which end of each edge type is the "parent"/origin when tracing why a node
# exists. INCOMING led_to means "X led to cur" (parent = src). OUTGOING
# belongs_to/implements means "cur belongs to / implements Y" (parent = dst).
_PARENT_IN = {"led_to"}                    # follow src of an incoming edge
_PARENT_OUT = {"belongs_to", "implements"}  # follow dst of an outgoing edge


def _parent_of(nid: str, seen: set[str]) -> dict[str, Any] | None:
    """The single best 'origin' node one hop toward the cause of `nid`."""
    # prefer causal (led_to) links, then structural (belongs_to/implements)
    for e in edges_of(nid, "in"):
        if e["type"] in _PARENT_IN and e["src"] not in seen:
            p = get_node(e["src"])
            if p:
                return p
    for e in edges_of(nid, "out"):
        if e["type"] in _PARENT_OUT and e["dst"] not in seen:
            p = get_node(e["dst"])
            if p:
                return p
    return None


def trace_back(nid: str, edge_types: Iterable[str] | None = None,
               max_hops: int = 12) -> list[dict[str, Any]]:
    """Walk the causal chain BACKWARD from a node to reconstruct 'why this
    exists'. Follows incoming led_to and outgoing belongs_to/implements so a
    task climbs task -> feature -> discussion -> idea. Oldest-first, cycle-safe.

    `edge_types` is accepted for API compatibility but the per-type direction
    rules above take precedence."""
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    cur = get_node(nid)
    hops = 0
    while cur and cur["id"] not in seen and hops < max_hops:
        seen.add(cur["id"])
        chain.append(cur)
        cur = _parent_of(cur["id"], seen)
        hops += 1
    chain.reverse()
    return chain


def counts(project: str) -> dict[str, int]:
    """Node counts per type — quick vitals for a dashboard."""
    conn = _connect()
    rows = conn.execute(
        "SELECT type, COUNT(*) FROM domain_nodes WHERE project=? GROUP BY type",
        (project,),
    ).fetchall()
    conn.close()
    return {t: n for t, n in rows}


def wipe_project(pid: str) -> None:
    """Delete a project and everything under it. Mostly for tests/re-import."""
    conn = _connect()
    conn.execute("DELETE FROM domain_nodes WHERE project=?", (pid,))
    conn.execute("DELETE FROM domain_edges WHERE project=?", (pid,))
    conn.execute("DELETE FROM domain_projects WHERE id=?", (pid,))
    conn.commit()
    conn.close()
