"""
core/connectors.py
------------------
OAuth connectors for the Domain's Documentation tab: Figma and Microsoft 365
(PowerPoint / Excel / Word, all via Microsoft Graph), plus optional GitHub.

Design notes
------------
* Credentials (client id/secret) are pasted once in the Domain's Connectors UI
  and live in the same tiny `settings` kv table core/nature.py uses. They can
  also come from .env — env wins on first run, the DB wins after you edit it.
* Tokens are stored with their expiry and refreshed automatically on use, so
  the UI never has to think about it.
* The OAuth redirect comes back to the local bridge itself
  (http://127.0.0.1:8760/api/connectors/callback/<provider>) — no public
  callback server needed. Register exactly that URL in the provider console.
* Every network call is wrapped: a dead connector degrades to
  {"connected": false, "error": "..."} instead of taking a route down.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import requests

# Default to localhost rather than 127.0.0.1 because that's what the provider
# consoles will actually accept: Azure's portal refuses an http://127.0.0.1
# reply URL in the UI (manifest-only), and Figma's callback field expects a
# hostname too. The bridge itself still binds 127.0.0.1 — browsers resolve
# localhost to it. If yours resolves to IPv6 first and the callback page fails
# to load, set AURA_BRIDGE_ORIGIN (see docs/CONNECTORS.md).
BRIDGE_ORIGIN = os.getenv("AURA_BRIDGE_ORIGIN", "http://localhost:8760")
TIMEOUT = 20


# ── provider definitions ─────────────────────────────────────────────────────
PROVIDERS: dict[str, dict[str, Any]] = {
    "figma": {
        "label": "Figma",
        "icon": "◆",
        "color": "#f24e1e",
        "blurb": "Pull design files and frames straight into a roadmap.",
        "authorize": "https://www.figma.com/oauth",
        "token": "https://api.figma.com/v1/oauth/token",
        "scope": "file_read",
        "env_id": "FIGMA_CLIENT_ID",
        "env_secret": "FIGMA_CLIENT_SECRET",
        "docs": "https://www.figma.com/developers/api#oauth2",
    },
    "microsoft": {
        "label": "Microsoft 365",
        "icon": "▤",
        "color": "#2b7cd3",
        "blurb": "Word, Excel and PowerPoint files from OneDrive / SharePoint.",
        "authorize": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scope": "offline_access User.Read Files.ReadWrite.All Sites.Read.All",
        "env_id": "MS_CLIENT_ID",
        "env_secret": "MS_CLIENT_SECRET",
        "docs": "https://learn.microsoft.com/graph/auth-v2-user",
    },
    "github": {
        "label": "GitHub",
        "icon": "⎇",
        "color": "#8b949e",
        "blurb": "Live repo status on the dashboard: commits, issues, stars.",
        "authorize": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",
        "scope": "repo read:user",
        "env_id": "GITHUB_CLIENT_ID",
        "env_secret": "GITHUB_CLIENT_SECRET",
        "docs": "https://docs.github.com/apps/oauth-apps",
    },
}

# in-flight CSRF states: state -> (provider, created_at)
_PENDING: dict[str, tuple[str, float]] = {}
STATE_TTL = 600


# ── kv persistence (shares core/nature.py's settings table) ──────────────────
_DDL = "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"


def _kv_get(key: str) -> str | None:
    try:
        from memory.store import _connect
        conn = _connect()
        try:
            conn.execute(_DDL)
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row[0] if row else None
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return None


def _kv_set(key: str, value: str) -> None:
    try:
        from memory.store import _connect
        conn = _connect()
        try:
            conn.execute(_DDL)
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        print(f"[AURA connectors] persist failed: {e}")


def _kv_del(key: str) -> None:
    try:
        from memory.store import _connect
        conn = _connect()
        try:
            conn.execute(_DDL)
            conn.execute("DELETE FROM settings WHERE key=?", (key,))
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        pass


def _check(provider: str) -> dict[str, Any]:
    p = PROVIDERS.get(provider)
    if not p:
        raise ValueError(f"unknown connector: {provider}")
    return p


# ── credentials ──────────────────────────────────────────────────────────────
def get_credentials(provider: str) -> tuple[str, str]:
    p = _check(provider)
    cid = _kv_get(f"conn.{provider}.client_id") or os.getenv(p["env_id"], "")
    sec = _kv_get(f"conn.{provider}.client_secret") or os.getenv(p["env_secret"], "")
    return cid.strip(), sec.strip()


def set_credentials(provider: str, client_id: str, client_secret: str) -> None:
    _check(provider)
    _kv_set(f"conn.{provider}.client_id", (client_id or "").strip())
    _kv_set(f"conn.{provider}.client_secret", (client_secret or "").strip())


def redirect_uri(provider: str) -> str:
    return f"{BRIDGE_ORIGIN}/api/connectors/callback/{provider}"


# ── tokens ───────────────────────────────────────────────────────────────────
def _tokens(provider: str) -> dict[str, Any]:
    raw = _kv_get(f"conn.{provider}.tokens")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return {}


def _save_tokens(provider: str, data: dict[str, Any]) -> None:
    expires_in = data.get("expires_in")
    if expires_in:
        try:
            data["expires_at"] = time.time() + float(expires_in) - 60
        except (TypeError, ValueError):
            pass
    old = _tokens(provider)
    # a refresh response often omits refresh_token — keep the one we have
    if not data.get("refresh_token") and old.get("refresh_token"):
        data["refresh_token"] = old["refresh_token"]
    _kv_set(f"conn.{provider}.tokens", json.dumps(data))


def disconnect(provider: str) -> None:
    _check(provider)
    _kv_del(f"conn.{provider}.tokens")


# ── OAuth dance ──────────────────────────────────────────────────────────────
def auth_url(provider: str) -> str:
    p = _check(provider)
    cid, _ = get_credentials(provider)
    if not cid:
        raise ValueError(f"{p['label']} needs a client ID first")

    # prune expired states so the dict can't grow forever
    now = time.time()
    for st in [k for k, (_, t) in _PENDING.items() if now - t > STATE_TTL]:
        _PENDING.pop(st, None)

    state = secrets.token_urlsafe(24)
    _PENDING[state] = (provider, now)

    params = {
        "client_id": cid,
        "redirect_uri": redirect_uri(provider),
        "scope": p["scope"],
        "state": state,
        "response_type": "code",
    }
    if provider == "figma":
        params["response_type"] = "code"
    if provider == "microsoft":
        params["response_mode"] = "query"
        params["prompt"] = "select_account"
    return f"{p['authorize']}?{urlencode(params)}"


def exchange_code(provider: str, code: str, state: str) -> dict[str, Any]:
    p = _check(provider)
    expected = _PENDING.pop(state, None)
    if not expected or expected[0] != provider:
        raise ValueError("state mismatch — restart the connection from AURA")

    cid, sec = get_credentials(provider)
    data = {
        "client_id": cid,
        "client_secret": sec,
        "redirect_uri": redirect_uri(provider),
        "code": code,
        "grant_type": "authorization_code",
    }
    headers = {"Accept": "application/json"}
    if provider == "figma":
        # Figma wants the client credentials as HTTP Basic auth
        res = requests.post(
            p["token"], data=data, headers=headers, auth=(cid, sec), timeout=TIMEOUT
        )
    else:
        res = requests.post(p["token"], data=data, headers=headers, timeout=TIMEOUT)

    if res.status_code >= 400:
        raise ValueError(f"{p['label']} rejected the code: {res.text[:300]}")
    tok = res.json()
    if "access_token" not in tok:
        raise ValueError(f"no access token in response: {str(tok)[:200]}")
    _save_tokens(provider, tok)
    return tok


def _refresh(provider: str) -> dict[str, Any]:
    p = _check(provider)
    tok = _tokens(provider)
    rt = tok.get("refresh_token")
    if not rt:
        raise ValueError("no refresh token — reconnect this app")
    cid, sec = get_credentials(provider)
    data = {
        "client_id": cid,
        "client_secret": sec,
        "refresh_token": rt,
        "grant_type": "refresh_token",
    }
    if provider == "microsoft":
        data["scope"] = p["scope"]
    res = requests.post(
        p["token"], data=data, headers={"Accept": "application/json"}, timeout=TIMEOUT
    )
    if res.status_code >= 400:
        raise ValueError(f"refresh failed: {res.text[:200]}")
    new = res.json()
    _save_tokens(provider, new)
    return new


def access_token(provider: str) -> str:
    tok = _tokens(provider)
    if not tok.get("access_token"):
        raise ValueError("not connected")
    exp = tok.get("expires_at")
    if exp and time.time() >= float(exp) and tok.get("refresh_token"):
        tok = _refresh(provider)
    return tok["access_token"]


# ── status ───────────────────────────────────────────────────────────────────
def status(provider: str) -> dict[str, Any]:
    p = _check(provider)
    cid, sec = get_credentials(provider)
    tok = _tokens(provider)
    exp = tok.get("expires_at")
    return {
        "id": provider,
        "label": p["label"],
        "icon": p["icon"],
        "color": p["color"],
        "blurb": p["blurb"],
        "docs": p["docs"],
        "redirect_uri": redirect_uri(provider),
        "configured": bool(cid and sec),
        "connected": bool(tok.get("access_token")),
        "expires_at": exp,
        "expired": bool(exp and time.time() >= float(exp) and not tok.get("refresh_token")),
        "account": tok.get("_account"),
    }


def status_all() -> list[dict[str, Any]]:
    return [status(k) for k in PROVIDERS]


# ── provider calls used by the Documentation tab ─────────────────────────────
def _get(url: str, provider: str, **kw) -> Any:
    # All three providers accept OAuth bearer tokens (Figma's personal-access
    # header X-Figma-Token is only for PATs, which we don't use here).
    header = {
        "Authorization": f"Bearer {access_token(provider)}",
        "Accept": "application/json",
    }
    res = requests.get(url, headers=header, timeout=TIMEOUT, **kw)
    if res.status_code == 401:
        _refresh(provider)
        header["Authorization"] = f"Bearer {access_token(provider)}"
        res = requests.get(url, headers=header, timeout=TIMEOUT, **kw)
    res.raise_for_status()
    return res.json()


def me(provider: str) -> dict[str, Any]:
    """Whoami — used to label a connected account in the UI."""
    if provider == "figma":
        u = _get("https://api.figma.com/v1/me", provider)
        name = u.get("email") or u.get("handle") or "Figma user"
    elif provider == "microsoft":
        u = _get("https://graph.microsoft.com/v1.0/me", provider)
        name = u.get("userPrincipalName") or u.get("displayName") or "Microsoft user"
    elif provider == "github":
        u = _get("https://api.github.com/user", provider)
        name = u.get("login") or "GitHub user"
    else:
        return {}
    tok = _tokens(provider)
    tok["_account"] = name
    _kv_set(f"conn.{provider}.tokens", json.dumps(tok))
    return {"account": name, "raw": u}


# Graph file kinds the Documentation tab cares about
_OFFICE = {
    ".docx": "word", ".doc": "word",
    ".xlsx": "excel", ".xls": "excel", ".csv": "excel",
    ".pptx": "powerpoint", ".ppt": "powerpoint",
}


def list_documents(provider: str, query: str = "") -> list[dict[str, Any]]:
    """Files you can attach to a project's documentation."""
    out: list[dict[str, Any]] = []

    if provider == "microsoft":
        if query:
            url = ("https://graph.microsoft.com/v1.0/me/drive/root/search"
                   f"(q='{requests.utils.quote(query)}')")
        else:
            url = "https://graph.microsoft.com/v1.0/me/drive/recent"
        data = _get(url, provider)
        for it in data.get("value", [])[:60]:
            name = it.get("name", "")
            ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
            kind = _OFFICE.get(ext)
            if not kind:
                continue
            out.append({
                "id": it.get("id"),
                "name": name,
                "kind": kind,
                "url": it.get("webUrl"),
                "modified": it.get("lastModifiedDateTime"),
                "size": it.get("size"),
            })

    elif provider == "figma":
        # Figma has no "list all my files" endpoint — projects are reached via
        # teams. We surface recent files per project for every team the token
        # can see; if none are configured we return an empty, explained list.
        team_ids = [t.strip() for t in (_kv_get("conn.figma.team_ids") or "").split(",") if t.strip()]
        for tid in team_ids:
            try:
                projects = _get(f"https://api.figma.com/v1/teams/{tid}/projects", provider)
            except Exception:  # noqa: BLE001
                continue
            for proj in projects.get("projects", [])[:10]:
                try:
                    files = _get(
                        f"https://api.figma.com/v1/projects/{proj['id']}/files", provider
                    )
                except Exception:  # noqa: BLE001
                    continue
                for f in files.get("files", [])[:30]:
                    out.append({
                        "id": f.get("key"),
                        "name": f.get("name"),
                        "kind": "figma",
                        "url": f"https://www.figma.com/file/{f.get('key')}",
                        "modified": f.get("last_modified"),
                        "thumbnail": f.get("thumbnail_url"),
                        "project": proj.get("name"),
                    })

    elif provider == "github":
        data = _get("https://api.github.com/user/repos?sort=updated&per_page=30", provider)
        for r in data:
            out.append({
                "id": str(r.get("id")),
                "name": r.get("full_name"),
                "kind": "repo",
                "url": r.get("html_url"),
                "modified": r.get("pushed_at"),
            })

    return out


def set_figma_teams(team_ids: str) -> None:
    _kv_set("conn.figma.team_ids", (team_ids or "").strip())


def get_figma_teams() -> str:
    return _kv_get("conn.figma.team_ids") or ""
