"""
core/github_status.py
---------------------
Live repo vitals for the Domain dashboard's project cards.

Works unauthenticated (60 req/hour, plenty for a dashboard) and automatically
uses the GitHub connector's OAuth token when one is present, which raises the
limit to 5000/hour and lets private repos resolve.

Results are cached for 10 minutes so flipping between dashboard tabs doesn't
burn the rate limit.
"""

from __future__ import annotations

import re
import time
from typing import Any

import requests

CACHE_TTL = 600
TIMEOUT = 12
_cache: dict[str, tuple[float, dict[str, Any]]] = {}

_RE = re.compile(
    r"(?:github\.com[/:])(?P<owner>[\w.\-]+)/(?P<repo>[\w.\-]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def parse_repo(url: str) -> tuple[str, str] | None:
    """github.com/owner/repo (https, ssh, with or without .git) -> (owner, repo)."""
    if not url:
        return None
    m = _RE.search(url.strip())
    if not m:
        # bare "owner/repo" is fine too
        bare = url.strip().strip("/")
        if bare.count("/") == 1 and " " not in bare:
            owner, repo = bare.split("/")
            return owner, repo
        return None
    return m.group("owner"), m.group("repo")


def _headers() -> dict[str, str]:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "AURA-Domain"}
    try:
        from core.connectors import access_token
        h["Authorization"] = f"Bearer {access_token('github')}"
    except Exception:  # noqa: BLE001
        pass  # unauthenticated is fine
    return h


def repo_status(url: str, force: bool = False) -> dict[str, Any]:
    parsed = parse_repo(url)
    if not parsed:
        return {"ok": False, "error": "not a GitHub URL"}
    owner, repo = parsed
    key = f"{owner}/{repo}".lower()

    hit = _cache.get(key)
    if hit and not force and time.time() - hit[0] < CACHE_TTL:
        return hit[1]

    try:
        r = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers=_headers(), timeout=TIMEOUT,
        )
        if r.status_code == 404:
            return {"ok": False, "error": "repo not found (or private without auth)"}
        if r.status_code == 403:
            return {"ok": False, "error": "GitHub rate limit — connect GitHub to raise it"}
        r.raise_for_status()
        d = r.json()

        out: dict[str, Any] = {
            "ok": True,
            "full_name": d.get("full_name"),
            "url": d.get("html_url"),
            "description": d.get("description"),
            "private": d.get("private"),
            "stars": d.get("stargazers_count", 0),
            "forks": d.get("forks_count", 0),
            "open_issues": d.get("open_issues_count", 0),
            "language": d.get("language"),
            "default_branch": d.get("default_branch"),
            "pushed_at": d.get("pushed_at"),
            "archived": d.get("archived", False),
        }

        # last commit message — the single most useful line on a project card
        try:
            c = requests.get(
                f"https://api.github.com/repos/{owner}/{repo}/commits",
                headers=_headers(), params={"per_page": 1}, timeout=TIMEOUT,
            )
            if c.ok and c.json():
                top = c.json()[0]
                out["last_commit"] = {
                    "message": (top.get("commit", {}).get("message") or "").split("\n")[0][:120],
                    "author": (top.get("commit", {}).get("author") or {}).get("name"),
                    "date": (top.get("commit", {}).get("author") or {}).get("date"),
                    "url": top.get("html_url"),
                }
        except Exception:  # noqa: BLE001
            pass

        _cache[key] = (time.time(), out)
        return out

    except requests.RequestException as e:
        return {"ok": False, "error": f"github unreachable: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
