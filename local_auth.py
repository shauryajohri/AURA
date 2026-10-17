"""
Launch token — the brain only takes orders from AURA's own window.

server.py listens on 127.0.0.1, but "only this machine" is not "only AURA":
every web page open in a browser on this laptop can send requests to
127.0.0.1:8760 too. Before this module the private surfaces (/api/* and /ws)
answered all of them, so a hostile page could chat with AURA, run shell
commands through the Domain routes, read memory, or enroll its own face in
Buddy Lock. An origin allowlist can't fix that alone: the packaged app loads
from file:// and so arrives as `Origin: null`, which is exactly what a
sandboxed iframe on any website sends as well.

So every start of the brain picks a fresh random secret, and the private
surfaces require it:

  * REST  /api/*  → header  `X-Aura-Token: <token>`
  * WS    /ws     → subprotocols `["aura", "aura-token.<token>"]`
                    (browsers can't set headers on a WebSocket, and a
                    subprotocol keeps the token out of uvicorn's access log,
                    where a ?token= query string would land)

Web pages never learn the token: it lives in this process, in an env var
(when Electron starts the brain itself it chooses the token and passes it as
AURA_TOKEN) and in `memory/session.token`, readable only by this user. The
Electron main process hands it to the renderer over IPC; in development the
Vite dev server serves it to its own page (frontend/vite.config.ts).

Left open on purpose:
  * OPTIONS                               CORS preflights carry no headers
  * GET /api/connectors/callback/{p}      the OAuth provider redirects the
                                          browser here; a navigation can't
                                          carry a header. It is guarded by the
                                          OAuth `state` check instead.
  * everything outside /api and /ws       /health, the public /web/api demo
                                          (never touches personal data) and
                                          the static landing page

The private surfaces also refuse any Host header that isn't loopback, so a
DNS-rebinding page (evil.example resolving to 127.0.0.1) is turned away even
before the token is checked.
"""

from __future__ import annotations

import hmac
import os
import re
import secrets
from pathlib import Path

from starlette.responses import JSONResponse

HEADER = "x-aura-token"
SUBPROTOCOL = "aura"
_WS_PREFIX = "aura-token."

TOKEN_FILE = Path(__file__).resolve().parent / "memory" / "session.token"

# Exact origins the UI is served from. "null" is the packaged Electron app
# (file://). Allowing it in CORS is safe only because the token is required:
# a sandboxed iframe also sends "null" but has no token to send.
ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173", "null"]

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

# Private surfaces that must stay reachable without the header.
_OPEN_ROUTES = [re.compile(r"^/api/connectors/callback/[^/]+/?$")]


def _new_token() -> str:
    env = os.getenv("AURA_TOKEN", "").strip()
    # Electron passes a 43-char token. Refuse anything short enough to guess
    # rather than silently running with a weak secret.
    if len(env) >= 32:
        return env
    if env:
        print("[AURA auth] AURA_TOKEN is too short (< 32 chars) — ignoring it")
    return secrets.token_urlsafe(32)


TOKEN = _new_token()


def write_token_file(path: Path = TOKEN_FILE) -> bool:
    """Leave the token where AURA's own window can find it when it didn't
    start this brain. Written atomically, owner-only. Best effort: if the
    disk refuses, a brain started by Electron still works (it has the env)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(TOKEN)
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass  # Windows: the file inherits the user-profile ACL
        return True
    except OSError as e:
        print(f"[AURA auth] could not write {path}: {e}")
        return False


def token_ok(candidate: str | None) -> bool:
    return bool(candidate) and hmac.compare_digest(
        candidate.encode("utf-8", "ignore"), TOKEN.encode("utf-8"))


def _header(scope, name: str) -> str | None:
    want = name.encode("latin-1")
    for k, v in scope.get("headers") or []:
        if k.lower() == want:
            return v.decode("latin-1")
    return None


def host_ok(scope) -> bool:
    host = (_header(scope, "host") or "").strip().lower()
    if host.startswith("["):                       # [::1]:8760
        name = host[1:].split("]", 1)[0]
    else:
        name = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    return name in _LOOPBACK_HOSTS


def is_private(path: str) -> bool:
    return path == "/ws" or path.startswith("/ws/") or path == "/api" or path.startswith("/api/")


def _ws_token(scope) -> str | None:
    for p in scope.get("subprotocols") or []:
        if p.startswith(_WS_PREFIX):
            return p[len(_WS_PREFIX):]
    return None


def accept_subprotocol(scope) -> str | None:
    """The subprotocol to echo when accepting /ws. A browser that offered
    protocols drops the connection unless the server picks one of them."""
    return SUBPROTOCOL if SUBPROTOCOL in (scope.get("subprotocols") or []) else None


def verdict(scope) -> tuple[int, str] | None:
    """None = let it through; otherwise (status, reason)."""
    path = scope.get("path", "")
    if not is_private(path):
        return None
    if scope.get("type") == "http":
        if scope.get("method") == "OPTIONS":
            return None
        if not host_ok(scope):
            return 403, "AURA's private API only answers on 127.0.0.1."
        if any(r.match(path) for r in _OPEN_ROUTES):
            return None
        if not token_ok(_header(scope, HEADER)):
            return 401, "Missing or wrong launch token — only AURA's own window can use this."
        return None
    if scope.get("type") == "websocket":
        if not host_ok(scope):
            return 403, "bad host"
        if not token_ok(_ws_token(scope)):
            return 401, "bad token"
    return None


class LaunchTokenMiddleware:
    """Pure ASGI, so streamed responses and websockets pass through
    untouched. Register it AFTER GuardMiddleware and BEFORE CORSMiddleware:
    the middleware added last is outermost, so the order is
    CORS → launch token → Buddy Lock → app. CORS has to wrap this so a 401
    still carries the headers the renderer needs to read it, and an
    unauthenticated request never reaches Buddy Lock (which would otherwise
    let it feed frames to the camera check)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        refusal = verdict(scope) if scope.get("type") in ("http", "websocket") else None
        if refusal is None:
            await self.app(scope, receive, send)
            return
        status, reason = refusal
        if scope["type"] == "http":
            await JSONResponse({"ok": False, "auth": False, "error": reason},
                               status_code=status)(scope, receive, send)
            return
        # Refuse the handshake before accepting: uvicorn answers HTTP 403.
        message = await receive()
        if message.get("type") == "websocket.connect":
            await send({"type": "websocket.close", "code": 1008, "reason": reason})
