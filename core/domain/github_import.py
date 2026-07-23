"""
core.domain.github_import
-------------------------
"Log in with GitHub, then let AURA pull a repo into a project." This is the
ONLY place the GitHub OAuth token is used for Domain projects — it lists the
user's repos and clones a chosen one locally, after which the existing
local-git pipeline (analyzer + git_scan + project_brain) takes over. The token
never leaks into any other AURA feature.

Flow:
    is_connected()                -> has the user authorised GitHub?
    list_repos()                  -> their repos (name, private, language, ...)
    import_repo(full_name)        -> clone locally + build the project graph

Cloning (rather than reading via the API) is deliberate: it reuses everything
built last session and gives real static analysis + full commit history for
free. Clones live under <repo_root>/domain_projects/ so they're contained.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Any

from core.domain import project_brain

# where cloned project repos are kept — a sibling of the AURA source tree
_PROJECTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "domain_projects",
)


def projects_dir() -> str:
    os.makedirs(_PROJECTS_DIR, exist_ok=True)
    return _PROJECTS_DIR


# ── connection / listing ─────────────────────────────────────────────────────
def is_connected() -> bool:
    """True once the user has completed the GitHub OAuth handshake."""
    try:
        from core import connectors
        return bool(connectors.status("github").get("connected"))
    except Exception:
        return False


def account() -> str:
    try:
        from core import connectors
        return connectors.status("github").get("account") or ""
    except Exception:
        return ""


def list_repos(limit: int = 100) -> dict[str, Any]:
    """The user's repos, newest-updated first. Uses the existing github token
    via connectors._get. Returns {ok, connected, repos[]}."""
    if not is_connected():
        return {"ok": False, "connected": False,
                "error": "GitHub not connected — authorise it first"}
    from core import connectors
    try:
        data = connectors._get(
            f"https://api.github.com/user/repos?sort=updated&per_page={min(limit,100)}"
            "&affiliation=owner,collaborator,organization_member",
            "github",
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "connected": True, "error": f"GitHub API failed: {e}"}
    repos = [{
        "name": r.get("name"),
        "full_name": r.get("full_name"),
        "private": bool(r.get("private")),
        "description": r.get("description") or "",
        "language": r.get("language") or "",
        "default_branch": r.get("default_branch") or "main",
        "updated_at": r.get("updated_at") or "",
        "clone_url": r.get("clone_url") or "",
        "html_url": r.get("html_url") or "",
    } for r in (data or []) if isinstance(r, dict)]
    return {"ok": True, "connected": True, "account": account(), "repos": repos}


# ── cloning ──────────────────────────────────────────────────────────────────
def _safe_name(full_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", full_name)


def _authed_url(clone_url: str, token: str) -> str:
    """Inject the OAuth token so private repos clone non-interactively."""
    if clone_url.startswith("https://") and token:
        return clone_url.replace("https://", f"https://x-access-token:{token}@", 1)
    return clone_url


def clone_repo(full_name: str, clone_url: str = "", branch: str = "",
               force: bool = False) -> dict[str, Any]:
    """Clone (or update) a repo locally. Returns {ok, path}."""
    if not is_connected():
        return {"ok": False, "error": "GitHub not connected"}
    from core import connectors
    try:
        token = connectors.access_token("github")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"no GitHub token: {e}"}

    if not clone_url:
        clone_url = f"https://github.com/{full_name}.git"
    dest = os.path.join(projects_dir(), _safe_name(full_name))

    # already cloned -> pull latest instead of re-cloning
    if os.path.isdir(os.path.join(dest, ".git")) and not force:
        try:
            subprocess.run(["git", "-C", dest, "pull", "--ff-only"],
                           capture_output=True, text=True, timeout=120)
        except Exception:
            pass
        return {"ok": True, "path": dest, "updated": True}

    if os.path.isdir(dest) and force:
        shutil.rmtree(dest, ignore_errors=True)

    args = ["git", "clone", "--depth", "50"]
    if branch:
        args += ["--branch", branch]
    args += [_authed_url(clone_url, token), dest]
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        return {"ok": False, "error": "git binary not found on PATH"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "git clone timed out"}
    if p.returncode != 0:
        # never surface the token in an error string
        err = (p.stderr or "clone failed").replace(token, "***") if token else p.stderr
        return {"ok": False, "error": err.strip()[:300]}
    # scrub the token from the stored remote so it isn't persisted on disk
    try:
        subprocess.run(["git", "-C", dest, "remote", "set-url", "origin", clone_url],
                       capture_output=True, text=True, timeout=30)
    except Exception:
        pass
    return {"ok": True, "path": dest, "updated": False}


# ── the one-call import ──────────────────────────────────────────────────────
def import_repo(full_name: str, clone_url: str = "", name: str = "",
                branch: str = "", force: bool = False) -> dict[str, Any]:
    """Log-in-gated: clone `full_name` locally and build the full project graph
    (analysis + commit history). Returns {ok, project, analysis, git}."""
    cl = clone_repo(full_name, clone_url=clone_url, branch=branch, force=force)
    if not cl.get("ok"):
        return cl
    proj_name = name or full_name.split("/")[-1]
    try:
        built = project_brain.import_from_folder(proj_name, cl["path"])
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"import failed after clone: {e}",
                "path": cl["path"]}
    # remember the origin on the project
    from core.domain import brain_store
    brain_store.update_project(built["project"]["id"], repo_url=(
        clone_url or f"https://github.com/{full_name}"),
        meta={"github_full_name": full_name})
    return {"ok": True, "cloned_to": cl["path"], "updated": cl.get("updated", False),
            **built}
