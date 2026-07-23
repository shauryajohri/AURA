"""
core.domain.git_scan
--------------------
Local-git reader for AURA Domain V2. No OAuth, no network — just the `git`
binary against a repo on disk. This is the Phase-2/Phase-6 data source:
commits, changed files, branches, languages.

Everything returns plain dicts so project_brain can turn them into graph nodes
and REST can serialize them directly. Safe on a non-git folder (returns
{"is_repo": False}).
"""

from __future__ import annotations

import os
import subprocess
from collections import Counter
from typing import Any

# file extension -> language label, for the language breakdown
_LANG = {
    ".py": "Python", ".pyi": "Python",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
    ".json": "JSON", ".md": "Markdown", ".html": "HTML", ".css": "CSS",
    ".scss": "CSS", ".c": "C", ".h": "C", ".cpp": "C++", ".hpp": "C++",
    ".cc": "C++", ".go": "Go", ".rs": "Rust", ".java": "Java",
    ".rb": "Ruby", ".sh": "Shell", ".yml": "YAML", ".yaml": "YAML",
    ".toml": "TOML", ".sql": "SQL", ".vue": "Vue", ".svelte": "Svelte",
}

_UNIT = "\x1f"   # record field separator we hand to git --pretty
_REC = "\x1e"    # record separator


def _git(root: str, *args: str, timeout: int = 30) -> tuple[bool, str]:
    """Run a git command in `root`. Returns (ok, stdout-or-stderr)."""
    try:
        p = subprocess.run(
            ["git", "-C", root, *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        return False, "git binary not found on PATH"
    except subprocess.TimeoutExpired:
        return False, f"git {' '.join(args)} timed out"
    except Exception as e:  # noqa: BLE001
        return False, str(e)
    if p.returncode != 0:
        return False, (p.stderr or p.stdout or "git error").strip()
    return True, p.stdout


def is_repo(root: str) -> bool:
    ok, out = _git(root, "rev-parse", "--is-inside-work-tree")
    return ok and out.strip() == "true"


def head(root: str) -> dict[str, Any]:
    """Current branch + short sha, best effort."""
    ok_b, branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    ok_s, sha = _git(root, "rev-parse", "--short", "HEAD")
    return {
        "branch": branch.strip() if ok_b else "",
        "sha": sha.strip() if ok_s else "",
    }


def branches(root: str) -> list[str]:
    ok, out = _git(root, "branch", "--format=%(refname:short)")
    if not ok:
        return []
    return [b.strip() for b in out.splitlines() if b.strip()]


def remote_url(root: str) -> str:
    ok, out = _git(root, "config", "--get", "remote.origin.url")
    return out.strip() if ok else ""


def commits(root: str, limit: int = 50) -> list[dict[str, Any]]:
    """Recent commits with the files each one touched.

    Returns newest-first. Each: {sha, subject, author, email, date, files[]}.
    """
    if not is_repo(root):
        return []
    fmt = _UNIT.join(["%H", "%h", "%s", "%an", "%ae", "%aI"]) + _REC
    # --name-only appends the changed paths after each record.
    ok, out = _git(
        root, "log", f"-n{limit}", "--name-only", f"--pretty=format:{fmt}",
    )
    if not ok:
        return []
    result: list[dict[str, Any]] = []
    for raw in out.split(_REC):
        raw = raw.strip("\n")
        if not raw.strip():
            continue
        head_line, _, files_blob = raw.partition("\n")
        parts = head_line.split(_UNIT)
        if len(parts) < 6:
            continue
        full, short, subject, author, email, date = parts[:6]
        files = [f.strip() for f in files_blob.splitlines() if f.strip()]
        result.append({
            "sha": short.strip(),
            "full_sha": full.strip(),
            "subject": subject.strip(),
            "author": author.strip(),
            "email": email.strip(),
            "date": date.strip(),
            "files": files,
        })
    return result


def status(root: str) -> dict[str, Any]:
    """Working-tree status: staged / unstaged / untracked counts."""
    ok, out = _git(root, "status", "--porcelain")
    if not ok:
        return {"clean": True, "changed": 0, "entries": []}
    entries = [ln for ln in out.splitlines() if ln.strip()]
    return {
        "clean": not entries,
        "changed": len(entries),
        "entries": [ln.strip() for ln in entries[:200]],
    }


def tracked_files(root: str) -> list[str]:
    ok, out = _git(root, "ls-files")
    if not ok:
        return []
    return [f.strip() for f in out.splitlines() if f.strip()]


def language_breakdown(files: list[str]) -> dict[str, int]:
    """{language: file-count} from a list of paths, biggest first."""
    counter: Counter[str] = Counter()
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        lang = _LANG.get(ext)
        if lang:
            counter[lang] += 1
    return dict(counter.most_common())


def contributors(cmts: list[dict[str, Any]]) -> dict[str, int]:
    """{author: commit-count} from a commit list."""
    counter: Counter[str] = Counter()
    for c in cmts:
        if c.get("author"):
            counter[c["author"]] += 1
    return dict(counter.most_common())


def scan(root: str, commit_limit: int = 50) -> dict[str, Any]:
    """One-shot local-git snapshot for the graph importer and dashboard.

    Never raises on a non-repo — returns {"is_repo": False, ...} so callers can
    still analyze the folder structure without git.
    """
    root = os.path.abspath(os.path.expanduser(root))
    if not os.path.isdir(root):
        return {"is_repo": False, "root": root, "error": "path not found"}
    if not is_repo(root):
        return {"is_repo": False, "root": root}
    files = tracked_files(root)
    cmts = commits(root, commit_limit)
    return {
        "is_repo": True,
        "root": root,
        "head": head(root),
        "branches": branches(root),
        "remote_url": remote_url(root),
        "file_count": len(files),
        "languages": language_breakdown(files),
        "commits": cmts,
        "contributors": contributors(cmts),
        "status": status(root),
    }
