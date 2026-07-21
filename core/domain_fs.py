"""
core/domain_fs.py
-----------------
Real filesystem access for the AURA Domain's Code pane.

The Domain runs on YOUR machine, so this is deliberately not a sandbox: you can
browse any drive, open any repo and save edits in place. What it does refuse:

* writing into OS directories (Windows/System32, /etc, /usr, …)
* reading files that are obviously binary or huge (the editor would choke)
* path traversal games — every path is resolved to an absolute real path first

Everything returns plain dicts so the FastAPI layer can hand them straight to
the React file explorer.
"""

from __future__ import annotations

import os
import shutil
import stat
from datetime import datetime
from pathlib import Path
from typing import Any

# ── limits ──────────────────────────────────────────────────────────────────
MAX_READ_BYTES = 2_000_000        # 2 MB — beyond this the editor is useless
MAX_ENTRIES = 4000                # a directory listing cap, for sanity

# Directories that are never writable, no matter what the UI asks.
_PROTECTED = [
    "c:\\windows", "c:\\program files", "c:\\program files (x86)",
    "/etc", "/usr", "/bin", "/sbin", "/boot", "/sys", "/proc", "/dev",
]

# Folders we never descend into when building a tree — they're noise.
IGNORED_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", ".next", "dist", "build", ".idea",
    ".vscode", ".cache", "site-packages", ".turbo", "coverage",
}

# ext → editor language id (matches the frontend's highlighter map)
LANGS = {
    ".ts": "ts", ".tsx": "ts", ".js": "js", ".jsx": "js", ".mjs": "js",
    ".py": "py", ".pyw": "py", ".css": "css", ".scss": "css",
    ".json": "json", ".md": "md", ".markdown": "md",
    ".html": "html", ".htm": "html", ".yml": "yaml", ".yaml": "yaml",
    ".toml": "toml", ".sh": "sh", ".bat": "sh", ".ps1": "sh",
    ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp",
    ".java": "java", ".go": "go", ".rs": "rust", ".sql": "sql",
    ".txt": "txt", ".env": "txt", ".gitignore": "txt", ".cfg": "txt",
    ".ini": "txt", ".xml": "xml", ".csv": "csv",
}

TEXT_EXTS = set(LANGS)


class FsError(Exception):
    """Anything the caller did wrong — surfaced to the UI as a clean message."""


# ── helpers ──────────────────────────────────────────────────────────────────
def _resolve(path: str) -> Path:
    if not path or not str(path).strip():
        raise FsError("path required")
    try:
        p = Path(os.path.expanduser(str(path))).resolve()
    except Exception as e:  # noqa: BLE001
        raise FsError(f"bad path: {e}") from e
    return p


def _is_protected(p: Path) -> bool:
    s = str(p).replace("/", os.sep).lower()
    return any(s.startswith(prot.replace("/", os.sep)) for prot in _PROTECTED)


def _guard_write(p: Path) -> None:
    if _is_protected(p):
        raise FsError("that location is protected — pick a project folder instead")


def lang_of(name: str) -> str:
    return LANGS.get(Path(name).suffix.lower(), "txt")


def _looks_binary(p: Path) -> bool:
    """Cheap sniff: a NUL byte in the first 8 KB means binary."""
    if p.suffix.lower() in TEXT_EXTS:
        return False
    try:
        with p.open("rb") as fh:
            return b"\0" in fh.read(8192)
    except Exception:  # noqa: BLE001
        return True


def _entry(p: Path) -> dict[str, Any]:
    try:
        st = p.stat()
        size = st.st_size
        mtime = datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
        hidden = bool(st.st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN) \
            if hasattr(st, "st_file_attributes") else p.name.startswith(".")
    except Exception:  # noqa: BLE001
        size, mtime, hidden = 0, None, p.name.startswith(".")
    is_dir = p.is_dir()
    return {
        "name": p.name or str(p),
        "path": str(p),
        "dir": is_dir,
        "size": 0 if is_dir else size,
        "mtime": mtime,
        "hidden": hidden,
        "lang": None if is_dir else lang_of(p.name),
    }


# ── public API ───────────────────────────────────────────────────────────────
def roots() -> list[dict[str, Any]]:
    """Sensible starting points: home, desktop, drives (Windows) or / (POSIX)."""
    out: list[dict[str, Any]] = []
    home = Path.home()
    for label, p in (
        ("Home", home),
        ("Desktop", home / "Desktop"),
        ("Documents", home / "Documents"),
        ("Downloads", home / "Downloads"),
    ):
        if p.exists():
            out.append({"label": label, "path": str(p)})

    if os.name == "nt":
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            drive = Path(f"{letter}:\\")
            if drive.exists():
                out.append({"label": f"{letter}:", "path": str(drive)})
    else:
        out.append({"label": "/", "path": "/"})
    return out


def list_dir(path: str, show_hidden: bool = False) -> dict[str, Any]:
    p = _resolve(path)
    if not p.exists():
        raise FsError("that folder no longer exists")
    if not p.is_dir():
        raise FsError("not a folder")

    entries: list[dict[str, Any]] = []
    try:
        for child in p.iterdir():
            if len(entries) >= MAX_ENTRIES:
                break
            e = _entry(child)
            if e["hidden"] and not show_hidden:
                continue
            entries.append(e)
    except PermissionError as e:
        raise FsError("permission denied") from e

    entries.sort(key=lambda e: (not e["dir"], e["name"].lower()))
    return {
        "path": str(p),
        "parent": str(p.parent) if p.parent != p else None,
        "entries": entries,
    }


def tree(path: str, depth: int = 2) -> dict[str, Any]:
    """A shallow project tree for the explorer sidebar. Skips IGNORED_DIRS."""
    root = _resolve(path)
    if not root.is_dir():
        raise FsError("not a folder")

    def walk(p: Path, level: int) -> list[dict[str, Any]]:
        if level > depth:
            return []
        out: list[dict[str, Any]] = []
        try:
            children = sorted(
                p.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower())
            )
        except (PermissionError, OSError):
            return []
        for c in children[:400]:
            if c.name in IGNORED_DIRS or c.name.startswith("."):
                continue
            node = _entry(c)
            if c.is_dir():
                node["children"] = walk(c, level + 1)
            out.append(node)
        return out

    node = _entry(root)
    node["children"] = walk(root, 1)
    return node


def read_file(path: str) -> dict[str, Any]:
    p = _resolve(path)
    if not p.exists() or not p.is_file():
        raise FsError("file not found")
    size = p.stat().st_size
    if size > MAX_READ_BYTES:
        raise FsError(f"file is {size // 1024} KB — too large to open here")
    if _looks_binary(p):
        raise FsError("binary file — nothing to edit")
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            raise FsError(f"could not decode: {e}") from e
    return {
        "path": str(p), "name": p.name, "lang": lang_of(p.name),
        "content": text, "size": size,
    }


def write_file(path: str, content: str) -> dict[str, Any]:
    p = _resolve(path)
    _guard_write(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    # newline="" keeps whatever line endings the editor sent — no CRLF surprises
    with p.open("w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    return {"ok": True, "path": str(p), "size": p.stat().st_size}


def create(path: str, is_dir: bool = False) -> dict[str, Any]:
    p = _resolve(path)
    _guard_write(p)
    if p.exists():
        raise FsError("already exists")
    if is_dir:
        p.mkdir(parents=True)
    else:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()
    return {"ok": True, "path": str(p), "dir": is_dir}


def rename(path: str, new_name: str) -> dict[str, Any]:
    p = _resolve(path)
    _guard_write(p)
    if not new_name or any(ch in new_name for ch in '\\/:*?"<>|'):
        raise FsError("invalid name")
    target = p.parent / new_name
    if target.exists():
        raise FsError("a file with that name already exists")
    p.rename(target)
    return {"ok": True, "path": str(target)}


def delete(path: str) -> dict[str, Any]:
    p = _resolve(path)
    _guard_write(p)
    if not p.exists():
        raise FsError("already gone")
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()
    return {"ok": True}


def search(path: str, query: str, limit: int = 100) -> list[dict[str, Any]]:
    """Filename search under a folder — the explorer's quick-open."""
    root = _resolve(path)
    q = (query or "").lower().strip()
    if not q:
        return []
    hits: list[dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")]
        for fn in filenames:
            if q in fn.lower():
                hits.append(_entry(Path(dirpath) / fn))
                if len(hits) >= limit:
                    return hits
    return hits
