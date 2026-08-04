# core/git_ops.py
"""
Write-side git operations — the companion to core.domain.git_scan (read-side).

git_scan answers "what does this repo look like?". This module answers "commit
and publish it", which is a different risk class entirely, so the rules here
are deliberately conservative:

  • Nothing runs without an explicit `confirm=True`. `preview()` is the safe
    default and is what any UI should call first.
  • No force pushes. Ever. Not exposed, not reachable by argument.
  • No `git add -A` on an unknown tree — `preview()` shows the exact file list
    the caller is agreeing to before anything is staged.
  • Protected branches (main/master) require `allow_protected=True` on top of
    `confirm`, so pushing to main is always a second, separate decision.
  • Every function returns a plain dict — REST can serialize it and a Qt panel
    can render it without either one knowing about the other.

This exists because the Code Review panel's "Push to Main Codebase" button was
a placeholder that only ever opened a "not wired up yet" dialog.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

# Branches that need a second, explicit opt-in before a push is allowed.
PROTECTED = {"main", "master", "prod", "production", "release"}

# Hard ceiling on a single staged changeset. A commit far larger than this is
# almost always an accident (a stray venv/, a node_modules/, a build output),
# so it stops and asks rather than publishing it.
MAX_FILES_WITHOUT_OVERRIDE = 200


def _git(root: str, *args: str, timeout: int = 60) -> tuple[bool, str]:
    """Run one git command in `root`. Returns (ok, stdout-or-stderr)."""
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


def _is_repo(root: str) -> bool:
    ok, out = _git(root, "rev-parse", "--is-inside-work-tree")
    return ok and out.strip() == "true"


def _parse_status(porcelain: str) -> list[dict[str, str]]:
    """Turn `git status --porcelain` into rows the UI can list."""
    rows: list[dict[str, str]] = []
    for line in porcelain.splitlines():
        if len(line) < 4:
            continue
        x, y, path = line[0], line[1], line[3:].strip()
        # Renames arrive as "old -> new"; the new name is what gets committed.
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if x == "?" and y == "?":
            state = "untracked"
        elif x == "D" or y == "D":
            state = "deleted"
        elif x == "A" or y == "A":
            state = "added"
        elif x == "R":
            state = "renamed"
        else:
            state = "modified"
        rows.append({"path": path.strip('"'), "state": state, "staged": x not in " ?"})
    return rows


def preview(root: str) -> dict[str, Any]:
    """What WOULD be committed and pushed. Read-only — changes nothing.

    Every UI should call this first and show the result to the user; `commit`
    and `push` refuse to run without an explicit confirmation anyway.
    """
    root = os.path.abspath(root or ".")
    if not os.path.isdir(root):
        return {"ok": False, "error": f"no such folder: {root}"}
    if not _is_repo(root):
        return {"ok": False, "error": "not a git repository", "is_repo": False}

    # `rev-parse --abbrev-ref HEAD` fails on an unborn HEAD (a fresh repo with
    # no commits yet), so fall back to --show-current, which handles that case.
    ok_b, branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    branch = branch.strip() if ok_b else ""
    if not branch:
        ok_b2, branch2 = _git(root, "branch", "--show-current")
        branch = branch2.strip() if ok_b2 else ""
    ok_s, status = _git(root, "status", "--porcelain")
    files = _parse_status(status) if ok_s else []

    # How far ahead/behind we are, when an upstream is configured.
    ahead = behind = 0
    has_upstream = False
    ok_u, upstream = _git(root, "rev-parse", "--abbrev-ref", "@{upstream}")
    if ok_u and upstream.strip():
        has_upstream = True
        ok_c, counts = _git(root, "rev-list", "--left-right", "--count", "@{upstream}...HEAD")
        if ok_c:
            parts = counts.split()
            if len(parts) == 2:
                behind, ahead = int(parts[0]), int(parts[1])

    ok_r, remotes = _git(root, "remote")
    remote_list = [r for r in (remotes.split() if ok_r else []) if r]

    return {
        "ok": True,
        "is_repo": True,
        "root": root,
        "branch": branch,
        "protected": branch.lower() in PROTECTED,
        "files": files,
        "file_count": len(files),
        "clean": not files,
        "has_upstream": has_upstream,
        "upstream": upstream.strip() if ok_u else "",
        "ahead": ahead,
        "behind": behind,
        "remotes": remote_list,
        "can_push": bool(remote_list),
        "oversized": len(files) > MAX_FILES_WITHOUT_OVERRIDE,
    }


def commit(
    root: str,
    message: str,
    confirm: bool = False,
    paths: list[str] | None = None,
    allow_oversized: bool = False,
) -> dict[str, Any]:
    """Stage and commit. Refuses to do anything unless `confirm=True`.

    `paths` limits the commit to specific files; omitting it stages every
    change reported by `preview()` — which the caller has, by contract,
    already shown to the user.
    """
    if not confirm:
        return {"ok": False, "error": "commit requires confirm=True", "preview": preview(root)}
    message = (message or "").strip()
    if not message:
        return {"ok": False, "error": "commit message required"}

    pre = preview(root)
    if not pre.get("ok"):
        return pre
    if pre["clean"]:
        return {"ok": False, "error": "nothing to commit", "preview": pre}
    if pre["oversized"] and not allow_oversized:
        return {
            "ok": False,
            "error": (f"{pre['file_count']} changed files exceeds the "
                      f"{MAX_FILES_WITHOUT_OVERRIDE}-file safety limit — "
                      "check for build output or a missing .gitignore"),
            "preview": pre,
        }

    root = pre["root"]
    if paths:
        ok, out = _git(root, "add", "--", *paths)
    else:
        ok, out = _git(root, "add", "-A")
    if not ok:
        return {"ok": False, "error": f"git add failed: {out}"}

    ok, out = _git(root, "commit", "-m", message)
    if not ok:
        return {"ok": False, "error": f"git commit failed: {out}"}

    ok_s, sha = _git(root, "rev-parse", "--short", "HEAD")
    return {
        "ok": True,
        "sha": sha.strip() if ok_s else "",
        "message": message,
        "files": pre["file_count"],
        "output": out.strip(),
    }


def push(
    root: str,
    confirm: bool = False,
    allow_protected: bool = False,
    remote: str = "origin",
) -> dict[str, Any]:
    """Push the current branch. Never forces.

    Pushing to a protected branch (main/master/…) needs `allow_protected=True`
    as well as `confirm=True` — two separate, deliberate decisions.
    """
    if not confirm:
        return {"ok": False, "error": "push requires confirm=True", "preview": preview(root)}

    pre = preview(root)
    if not pre.get("ok"):
        return pre
    if not pre["can_push"]:
        return {"ok": False, "error": "no git remote configured", "preview": pre}
    if pre["protected"] and not allow_protected:
        return {
            "ok": False,
            "error": f"'{pre['branch']}' is a protected branch — "
                     "pass allow_protected=True to push to it",
            "preview": pre,
        }
    if not pre["files"] and pre["ahead"] == 0 and pre["has_upstream"]:
        return {"ok": False, "error": "nothing to push — already up to date", "preview": pre}

    root, branch = pre["root"], pre["branch"]
    # First push of a new branch needs -u to create the upstream ref.
    args = ["push", remote, branch] if pre["has_upstream"] else ["push", "-u", remote, branch]
    ok, out = _git(root, *args, timeout=180)
    if not ok:
        return {"ok": False, "error": f"git push failed: {out}", "preview": pre}

    return {
        "ok": True,
        "branch": branch,
        "remote": remote,
        "pushed": pre["ahead"] or None,
        "output": out.strip(),
    }


def commit_and_push(
    root: str,
    message: str,
    confirm: bool = False,
    allow_protected: bool = False,
    allow_oversized: bool = False,
) -> dict[str, Any]:
    """The whole trip, for the Code Review panel's one-button flow."""
    c = commit(root, message, confirm=confirm, allow_oversized=allow_oversized)
    if not c.get("ok"):
        return c
    p = push(root, confirm=confirm, allow_protected=allow_protected)
    return {"ok": p.get("ok", False), "commit": c, "push": p,
            "error": p.get("error", "")}


# ============================================================================
# Read-side extras for the Git panel: history, branches, diffs.
# Everything below is READ-ONLY except `checkout`, `stage`/`unstage` and
# `pull`, which are all explicitly requested by a click in the UI.
# ============================================================================

def log(root: str, limit: int = 40) -> dict[str, Any]:
    """Recent commits: sha, author, relative date, subject."""
    root = os.path.abspath(root or ".")
    if not _is_repo(root):
        return {"ok": False, "error": "not a git repository", "commits": []}
    # \x1f between fields, \x1e between records — safe against commit
    # messages that contain literally any punctuation.
    fmt = "%h\x1f%an\x1f%ar\x1f%s\x1e"
    ok, out = _git(root, "log", f"--max-count={max(1, min(200, limit))}", f"--pretty=format:{fmt}")
    if not ok:
        # A repo with no commits yet isn't an error worth shouting about.
        return {"ok": True, "commits": [], "note": out.strip()}
    commits = []
    for rec in out.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        parts = rec.split("\x1f")
        if len(parts) < 4:
            continue
        commits.append({"sha": parts[0], "author": parts[1], "when": parts[2], "subject": parts[3]})
    return {"ok": True, "commits": commits}


def branches(root: str) -> dict[str, Any]:
    """Local branches + which one is checked out."""
    root = os.path.abspath(root or ".")
    if not _is_repo(root):
        return {"ok": False, "error": "not a git repository", "branches": []}
    ok, out = _git(root, "branch", "--format=%(refname:short)")
    names = [b.strip() for b in (out.splitlines() if ok else []) if b.strip()]
    ok_c, cur = _git(root, "branch", "--show-current")
    return {
        "ok": True,
        "branches": names,
        "current": cur.strip() if ok_c else "",
        "protected": sorted(PROTECTED),
    }


def checkout(root: str, branch: str, create: bool = False) -> dict[str, Any]:
    """Switch branches. Refuses when the tree is dirty — an unexpected
    carry-over of uncommitted work between branches is how people lose it."""
    root = os.path.abspath(root or ".")
    branch = (branch or "").strip()
    if not branch:
        return {"ok": False, "error": "branch name required"}
    pre = preview(root)
    if not pre.get("ok"):
        return pre
    if not pre["clean"]:
        return {"ok": False, "error": "commit or stash your changes before switching branches",
                "preview": pre}
    args = ["checkout", "-b", branch] if create else ["checkout", branch]
    ok, out = _git(root, *args)
    if not ok:
        return {"ok": False, "error": out.strip()}
    return {"ok": True, "branch": branch, "output": out.strip()}


def pull(root: str, remote: str = "origin") -> dict[str, Any]:
    """Fetch + fast-forward. `--ff-only` on purpose: AURA should never create
    a surprise merge commit or drop you into a conflicted tree unasked."""
    root = os.path.abspath(root or ".")
    if not _is_repo(root):
        return {"ok": False, "error": "not a git repository"}
    ok, out = _git(root, "pull", "--ff-only", remote, timeout=180)
    if not ok:
        return {"ok": False, "error": out.strip(),
                "hint": "fast-forward failed — the branches have diverged, merge manually"}
    return {"ok": True, "output": out.strip() or "Already up to date."}


def stage(root: str, paths: list[str] | None = None, unstage: bool = False) -> dict[str, Any]:
    """Stage or unstage specific paths (all changes when `paths` is empty)."""
    root = os.path.abspath(root or ".")
    if not _is_repo(root):
        return {"ok": False, "error": "not a git repository"}
    if unstage:
        args = ["restore", "--staged"] + (list(paths) if paths else ["."])
    else:
        args = ["add"] + (["--", *paths] if paths else ["-A"])
    ok, out = _git(root, *args)
    if not ok:
        return {"ok": False, "error": out.strip()}
    return {"ok": True, "preview": preview(root)}


def diff(root: str, path: str = "", staged: bool = False) -> dict[str, Any]:
    """Unified diff for one file (or the whole tree when `path` is empty)."""
    root = os.path.abspath(root or ".")
    if not _is_repo(root):
        return {"ok": False, "error": "not a git repository", "diff": ""}
    args = ["diff", "--no-color"]
    if staged:
        args.append("--staged")
    if path:
        args += ["--", path]
    ok, out = _git(root, *args)
    if not ok:
        return {"ok": False, "error": out.strip(), "diff": ""}
    # Untracked files have no diff at all; show the file so "what changed" is
    # never mysteriously blank.
    if not out.strip() and path:
        full = os.path.join(root, path)
        if os.path.isfile(full):
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as fh:
                    body = fh.read(60_000)
                out = "\n".join("+" + line for line in body.splitlines()[:800])
            except Exception:  # noqa: BLE001
                pass
    return {"ok": True, "diff": out[:200_000], "path": path, "staged": staged}
