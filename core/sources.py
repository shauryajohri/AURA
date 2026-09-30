"""
core/sources.py — the things AURA keeps in step with.

You hand AURA a link once and it stays current: a GitHub profile or repo, a
folder of documents, a single PDF or page. Every time AURA opens, each source
is re-read in the background, so what it knows about your work is what's true
today rather than what was true the day you pasted the link.

A source can belong to a room. Entering that room hands AURA that source's
context, which is what makes "the Coding room knows my repos" work without you
re-explaining anything.

What sync actually does, per kind:
    github  profile → the list of public repos, refreshed
            repo    → the repo pulled to latest if it has been cloned, and its
                      data files (README, manifests) re-read
    docs    a folder → every document in it, extracted and summarised; new and
                      changed files picked up, deleted ones dropped
    link    a page or file on the web → re-fetched and re-summarised

Extraction is not reimplemented here. core/saved_info already knows how to pull
text out of a PDF, a .docx and an HTML page, so a document source registers its
files there and this module only tracks what belongs to which source.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import threading
import time
from typing import Any, Callable

import requests

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_HERE, "memory", "aura_memory.db")

GITHUB_API = "https://api.github.com"
DOC_EXT = {".pdf", ".docx", ".doc", ".txt", ".md", ".rtf", ".pptx", ".xlsx", ".csv"}
MAX_DOCS_PER_SYNC = 40

# Files that tell you what a repo IS, in the order they're worth reading.
DATA_FILES = [
    "README.md", "readme.md", "README.rst", "README.txt",
    "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml",
    "go.mod", "pom.xml", "build.gradle", "Gemfile", "composer.json",
    "CLAUDE.md", "CONTRIBUTING.md",
]

_sink: Callable[[dict], None] | None = None
_syncing: set[int] = set()
_lock = threading.Lock()


def set_sink(fn: Callable[[dict], None]) -> None:
    """Where to push live updates (the websocket broadcaster)."""
    global _sink
    _sink = fn


def _publish(source: dict | None = None) -> None:
    if _sink:
        try:
            _sink({"type": "sources", "payload": {"sources": list_sources(),
                                                  "changed": source}})
        except Exception:  # noqa: BLE001
            pass


def _activity(text: str) -> None:
    try:
        from core import activity
        activity.emit(text, "sources")
    except Exception:  # noqa: BLE001
        pass


# ── storage ─────────────────────────────────────────────────────────────────
def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                kind        TEXT NOT NULL,
                url         TEXT NOT NULL,
                label       TEXT DEFAULT '',
                room_id     INTEGER,
                auto_sync   INTEGER DEFAULT 1,
                status      TEXT DEFAULT 'idle',
                detail      TEXT DEFAULT '',
                meta        TEXT DEFAULT '{}',
                last_sync   TEXT DEFAULT '',
                created_at  TEXT DEFAULT ''
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sources_room ON sources(room_id)")


def _row(r: sqlite3.Row) -> dict:
    try:
        meta = json.loads(r["meta"] or "{}")
    except Exception:  # noqa: BLE001
        meta = {}
    return {
        "id": r["id"], "kind": r["kind"], "url": r["url"], "label": r["label"],
        "room_id": r["room_id"], "auto_sync": bool(r["auto_sync"]),
        "status": r["status"], "detail": r["detail"], "meta": meta,
        "last_sync": r["last_sync"], "created_at": r["created_at"],
    }


def list_sources(room_id: int | None = None) -> list[dict]:
    init()
    sql = "SELECT * FROM sources"
    args: tuple = ()
    if room_id is not None:
        sql += " WHERE room_id = ?"
        args = (room_id,)
    sql += " ORDER BY id"
    with _conn() as conn:
        return [_row(r) for r in conn.execute(sql, args)]


def get(source_id: int) -> dict | None:
    init()
    with _conn() as conn:
        r = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    return _row(r) if r else None


def _update(source_id: int, **fields) -> dict | None:
    if "meta" in fields and not isinstance(fields["meta"], str):
        fields["meta"] = json.dumps(fields["meta"])
    cols = ", ".join(f"{k} = ?" for k in fields)
    with _conn() as conn:
        conn.execute(f"UPDATE sources SET {cols} WHERE id = ?",
                     (*fields.values(), source_id))
    return get(source_id)


# ── working out what a link is ──────────────────────────────────────────────
_GH_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[A-Za-z0-9-]+)"
    r"(?:/(?P<repo>[A-Za-z0-9._-]+))?/?",
    re.I,
)


def classify(raw: str) -> dict:
    """What kind of source a pasted string is, and its canonical form."""
    text = (raw or "").strip().strip("<>").rstrip("/")
    if not text:
        return {"kind": "", "url": "", "error": "nothing to add"}

    # a real folder or file on this machine
    if os.path.isdir(text):
        return {"kind": "docs", "url": os.path.realpath(text),
                "label": os.path.basename(text.rstrip("/\\")) or text}
    if os.path.isfile(text):
        return {"kind": "link", "url": os.path.realpath(text),
                "label": os.path.basename(text)}

    gh = _GH_RE.match(text)
    if gh:
        owner, repo = gh.group("owner"), gh.group("repo")
        # github.com/features etc. are not accounts
        if owner.lower() in {"features", "about", "pricing", "settings", "orgs", "topics"}:
            return {"kind": "link", "url": text, "label": text}
        if repo:
            repo = re.sub(r"\.git$", "", repo)
            return {"kind": "github", "url": f"https://github.com/{owner}/{repo}",
                    "label": f"{owner}/{repo}", "meta": {"owner": owner, "repo": repo}}
        return {"kind": "github", "url": f"https://github.com/{owner}",
                "label": owner, "meta": {"owner": owner, "repo": ""}}

    if "://" not in text:
        text = "https://" + text
    if not re.match(r"^https?://[^\s/]+\.[^\s/]+", text):
        return {"kind": "", "url": "", "error": "that isn't a link or a folder I can reach"}
    return {"kind": "link", "url": text, "label": re.sub(r"^https?://(www\.)?", "", text)[:60]}


# ── add / remove ────────────────────────────────────────────────────────────
def add(raw: str, label: str = "", room_id: int | None = None,
        auto_sync: bool = True) -> dict:
    init()
    info = classify(raw)
    if info.get("error"):
        return {"ok": False, "error": info["error"]}

    with _conn() as conn:
        dup = conn.execute("SELECT id FROM sources WHERE url = ?", (info["url"],)).fetchone()
        if dup:
            return {"ok": False, "error": "that one is already connected",
                    "source": get(dup["id"])}
        cur = conn.execute(
            "INSERT INTO sources (kind, url, label, room_id, auto_sync, status, meta, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (info["kind"], info["url"], label or info.get("label", ""), room_id,
             1 if auto_sync else 0, "idle", json.dumps(info.get("meta", {})),
             time.strftime("%Y-%m-%d %H:%M:%S")),
        )
        sid = cur.lastrowid

    source = get(sid)
    _publish(source)
    sync_async(sid)
    return {"ok": True, "source": source}


def remove(source_id: int) -> dict:
    init()
    with _conn() as conn:
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    _publish()
    return {"ok": True}


def update(source_id: int, label: str | None = None, room_id: Any = "keep",
           auto_sync: bool | None = None) -> dict:
    fields: dict[str, Any] = {}
    if label is not None:
        fields["label"] = label
    if room_id != "keep":
        fields["room_id"] = room_id
    if auto_sync is not None:
        fields["auto_sync"] = 1 if auto_sync else 0
    if not fields:
        return {"ok": True, "source": get(source_id)}
    source = _update(source_id, **fields)
    _publish(source)
    return {"ok": bool(source), "source": source}


# ── GitHub ──────────────────────────────────────────────────────────────────
def _gh_headers() -> dict:
    """Authorised when the user has connected GitHub, anonymous otherwise.
    Anonymous still works for public repos — it is just rate-limited, which is
    fine for a once-per-launch sync."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "AURA"}
    try:
        from core import connectors
        if connectors.status("github").get("connected"):
            token = connectors.access_token("github")
            if token:
                headers["Authorization"] = f"Bearer {token}"
    except Exception:  # noqa: BLE001
        pass
    return headers


def _gh_get(path: str) -> Any:
    r = requests.get(GITHUB_API + path, headers=_gh_headers(), timeout=20)
    if r.status_code == 404:
        raise ValueError("GitHub says that doesn't exist (or is private and not connected)")
    if r.status_code == 403 and "rate limit" in r.text.lower():
        raise ValueError("GitHub rate limit — connect GitHub in Settings to raise it")
    r.raise_for_status()
    return r.json()


def _sync_github(source: dict) -> dict:
    owner = source["meta"].get("owner") or ""
    repo = source["meta"].get("repo") or ""
    if not owner:
        gh = _GH_RE.match(source["url"])
        owner = gh.group("owner") if gh else ""
        repo = (gh.group("repo") or "") if gh else ""
    if not owner:
        return {"status": "error", "detail": "couldn't read an account out of that link"}

    if repo:
        data = _gh_get(f"/repos/{owner}/{repo}")
        repos = [data]
    else:
        repos = _gh_get(f"/users/{owner}/repos?sort=updated&per_page=100") or []

    listed = []
    for r in repos:
        if not isinstance(r, dict) or not r.get("full_name"):
            continue
        listed.append({
            "full_name": r["full_name"],
            "name": r.get("name") or "",
            "description": r.get("description") or "",
            "language": r.get("language") or "",
            "default_branch": r.get("default_branch") or "main",
            "updated_at": r.get("updated_at") or "",
            "pushed_at": r.get("pushed_at") or "",
            "clone_url": r.get("clone_url") or "",
            "html_url": r.get("html_url") or "",
            "private": bool(r.get("private")),
            "stars": r.get("stargazers_count") or 0,
        })
    listed.sort(key=lambda x: x.get("pushed_at") or "", reverse=True)

    # Data files for the repos AURA has actually cloned: those are the ones
    # being worked on, and their README/manifest is what makes AURA able to
    # talk about the project rather than just name it.
    from core.domain import github_import
    root = github_import.projects_dir()
    for entry in listed[:25]:
        local = os.path.join(root, re.sub(r"[^A-Za-z0-9._-]", "_", entry["full_name"]))
        if os.path.isdir(os.path.join(local, ".git")):
            entry["local"] = local
            entry["pulled"] = _git_pull(local)
            entry["data"] = _read_data_files(local)

    meta = dict(source["meta"])
    meta.update({"owner": owner, "repo": repo, "repos": listed})
    cloned = sum(1 for e in listed if e.get("local"))
    detail = (f"{len(listed)} repo{'s' if len(listed) != 1 else ''}"
              + (f", {cloned} cloned locally" if cloned else ""))
    return {"status": "ok", "detail": detail, "meta": meta}


def _git_pull(path: str) -> str:
    try:
        out = subprocess.run(["git", "-C", path, "pull", "--ff-only"],
                             capture_output=True, text=True, timeout=120)
        line = (out.stdout or out.stderr or "").strip().splitlines()
        return line[-1][:120] if line else ""
    except Exception as e:  # noqa: BLE001
        return f"pull failed: {e}"


def _read_data_files(root: str) -> dict[str, str]:
    """The handful of files that describe a project, trimmed to a size AURA can
    actually carry into a prompt."""
    found: dict[str, str] = {}
    for name in DATA_FILES:
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                found[name] = f.read(4000)
        except Exception:  # noqa: BLE001
            continue
        if len(found) >= 4:
            break
    return found


def clone(source_id: int, full_name: str) -> dict:
    """Bring a repo down to disk so it can be opened, prompted and edited.

    Public repos clone anonymously; private ones need GitHub connected. An
    already-cloned repo is pulled instead, so this is safe to call twice.
    """
    source = get(source_id)
    if not source:
        return {"ok": False, "error": "no such source"}
    from core.domain import github_import

    root = github_import.projects_dir()
    dest = os.path.join(root, re.sub(r"[^A-Za-z0-9._-]", "_", full_name))
    if os.path.isdir(os.path.join(dest, ".git")):
        return {"ok": True, "path": dest, "updated": _git_pull(dest), "already": True}

    url = f"https://github.com/{full_name}.git"
    try:
        from core import connectors
        if connectors.status("github").get("connected"):
            token = connectors.access_token("github")
            if token:
                url = f"https://x-access-token:{token}@github.com/{full_name}.git"
    except Exception:  # noqa: BLE001
        pass

    _activity(f"Cloning {full_name}…")
    try:
        out = subprocess.run(["git", "clone", "--depth", "50", url, dest],
                             capture_output=True, text=True, timeout=600)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"clone failed: {e}"}
    if out.returncode != 0:
        err = (out.stderr or "").strip().splitlines()
        # the token must never travel back to the UI inside an error string
        msg = err[-1] if err else "clone failed"
        return {"ok": False, "error": re.sub(r"https://[^@]+@", "https://", msg)[:200]}

    sync_async(source_id)
    return {"ok": True, "path": dest}


# ── documents ───────────────────────────────────────────────────────────────
def _sync_docs(source: dict) -> dict:
    """A watched folder. New and changed documents go through Saved Info's
    extractor; files that have gone away are forgotten."""
    from core import saved_info

    folder = source["url"]
    if not os.path.isdir(folder):
        return {"status": "error", "detail": "that folder isn't there any more"}

    known: dict[str, dict] = dict(source["meta"].get("files") or {})
    seen: set[str] = set()
    added = changed = 0

    for base, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in sorted(files):
            if os.path.splitext(name.lower())[1] not in DOC_EXT:
                continue
            path = os.path.join(base, name)
            rel = os.path.relpath(path, folder).replace("\\", "/")
            seen.add(rel)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            stamp = f"{int(stat.st_mtime)}:{stat.st_size}"
            prev = known.get(rel)
            if prev and prev.get("stamp") == stamp:
                continue
            if len(seen) > MAX_DOCS_PER_SYNC:
                break
            try:
                with open(path, "rb") as f:
                    data = f.read()
                item = saved_info.save_upload(name, data, "", origin="source")
                saved_info.scan_async(item["id"])
                known[rel] = {"stamp": stamp, "item": item["id"], "name": name}
                if prev:
                    changed += 1
                else:
                    added += 1
            except Exception:  # noqa: BLE001
                continue

    for rel in list(known):
        if rel not in seen:
            known.pop(rel, None)

    meta = dict(source["meta"])
    meta["files"] = known
    bits = [f"{len(known)} document{'s' if len(known) != 1 else ''}"]
    if added:
        bits.append(f"{added} new")
    if changed:
        bits.append(f"{changed} updated")
    return {"status": "ok", "detail": ", ".join(bits), "meta": meta}


def _sync_link(source: dict) -> dict:
    """One page or file. Re-read every sync so a document that changed at the
    other end doesn't leave AURA quoting last month's version."""
    from core import saved_info

    url = source["url"]
    meta = dict(source["meta"])
    try:
        if os.path.isfile(url):
            with open(url, "rb") as f:
                data = f.read()
            item = saved_info.save_upload(os.path.basename(url), data, "", origin="source")
        else:
            item = saved_info.save_link(url, origin="source")
        saved_info.scan_async(item["id"])
        meta["item"] = item["id"]
        title = item.get("title") or source["label"]
        return {"status": "ok", "detail": f"read: {title}"[:120], "meta": meta}
    except ValueError as e:
        return {"status": "error", "detail": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "detail": f"couldn't read it: {e}"}


# ── syncing ─────────────────────────────────────────────────────────────────
_HANDLERS = {"github": _sync_github, "docs": _sync_docs, "link": _sync_link}


def sync(source_id: int) -> dict:
    """Bring one source up to date. Safe to call from any thread; a source
    already syncing is left alone."""
    source = get(source_id)
    if not source:
        return {"ok": False, "error": "no such source"}
    with _lock:
        if source_id in _syncing:
            return {"ok": True, "source": source, "note": "already syncing"}
        _syncing.add(source_id)

    _publish(_update(source_id, status="syncing"))
    _activity(f"Syncing {source['label'] or source['url']}…")
    try:
        handler = _HANDLERS.get(source["kind"])
        result = handler(source) if handler else {"status": "error",
                                                  "detail": "I don't know how to sync that"}
    except ValueError as e:
        result = {"status": "error", "detail": str(e)}
    except Exception as e:  # noqa: BLE001
        result = {"status": "error", "detail": f"sync failed: {e}"}
    finally:
        with _lock:
            _syncing.discard(source_id)

    fields = {"status": result.get("status", "error"),
              "detail": result.get("detail", "")[:400],
              "last_sync": time.strftime("%Y-%m-%d %H:%M:%S")}
    if "meta" in result:
        fields["meta"] = result["meta"]
    updated = _update(source_id, **fields)
    _publish(updated)
    return {"ok": fields["status"] == "ok", "source": updated}


def sync_async(source_id: int) -> None:
    threading.Thread(target=sync, args=(source_id,), daemon=True).start()


def sync_all(only_auto: bool = True) -> None:
    """Every source, one after another on one background thread. Sequential on
    purpose: a launch that fires eight git pulls at once makes the first
    seconds of AURA feel broken."""
    def run() -> None:
        for s in list_sources():
            if only_auto and not s["auto_sync"]:
                continue
            sync(s["id"])
    threading.Thread(target=run, daemon=True).start()


# ── what AURA is told ───────────────────────────────────────────────────────
def context_for_room(room_id: int | None, limit_chars: int = 2600) -> str:
    """The block handed to the model when a room's sources should be in play.
    Empty when the room has none, so nothing is spent on rooms that aren't
    wired to anything."""
    rows = list_sources(room_id) if room_id is not None else []
    if not rows:
        return ""

    lines: list[str] = []
    for s in rows:
        if s["status"] != "ok":
            continue
        if s["kind"] == "github":
            repos = s["meta"].get("repos") or []
            if not repos:
                continue
            lines.append(f"GitHub ({s['label']}):")
            for r in repos[:12]:
                bit = f"  • {r['full_name']}"
                if r.get("language"):
                    bit += f" [{r['language']}]"
                if r.get("description"):
                    bit += f" — {r['description'][:90]}"
                if r.get("local"):
                    bit += "  (cloned locally)"
                lines.append(bit)
        elif s["kind"] == "docs":
            files = s["meta"].get("files") or {}
            if not files:
                continue
            names = [v.get("name", k) for k, v in list(files.items())[:12]]
            lines.append(f"Documents ({s['label']}): " + ", ".join(names))
        elif s["kind"] == "link":
            lines.append(f"Link ({s['label']}): {s['url']}")

    if not lines:
        return ""
    block = "CONNECTED SOURCES FOR THIS ROOM:\n" + "\n".join(lines)
    return block[:limit_chars]


def repos() -> list[dict]:
    """Every repo AURA knows about across all GitHub sources, de-duplicated —
    what the Domain's repo picker lists."""
    out: dict[str, dict] = {}
    for s in list_sources():
        if s["kind"] != "github":
            continue
        for r in s["meta"].get("repos") or []:
            r = dict(r)
            r["source_id"] = s["id"]
            out.setdefault(r["full_name"], r)
    return sorted(out.values(), key=lambda r: r.get("pushed_at") or "", reverse=True)
