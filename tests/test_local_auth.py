"""
Launch-token test (local_auth.py) against the REAL server app, so the
middleware order is tested too: CORS → launch token → Buddy Lock → routes.

What must hold:
  * /api/* and /ws refuse anything without the token, or with a wrong one
  * the right token gets through, on 127.0.0.1 / localhost / [::1] only
  * a 401 still carries CORS headers, so AURA's window can read why
  * CORS preflights, the OAuth callback, /health, the public /web demo and the
    static site keep working without a token
  * the token file is owner-only and holds exactly the live token

Runs offline on a throwaway DB and vault; never starts the background loops.

Run:  PYTHONPATH=. python tests/test_local_auth.py
"""

import os
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# throwaway DB + Buddy Lock vault before anything binds to the real ones
_TMP = tempfile.mkdtemp(prefix="aura_local_auth_")
os.environ["AURA_GUARD_VAULT"] = os.path.join(_TMP, "buddy.json")
os.environ.pop("AURA_TOKEN", None)

import memory.store as mstore  # noqa: E402
mstore.DB_PATH = os.path.join(_TMP, "test.db")
mstore.init_db()
mstore.init_tasks()
from core.domain import brain_store  # noqa: E402
brain_store.DB_PATH = mstore.DB_PATH
brain_store._connect = mstore._connect

from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

import local_auth  # noqa: E402
import server  # noqa: E402

TOKEN = local_auth.TOKEN
GOOD = {"X-Aura-Token": TOKEN}
WS = "ws://127.0.0.1:8760/ws"

# No `with`: the lifespan (proactive loops, token file in the real repo) stays off.
client = TestClient(server.app, base_url="http://127.0.0.1:8760")

_fails: list[str] = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'} — {label}")
    if not cond:
        _fails.append(label)


# ── 1. REST needs the token ────────────────────────────────────────────────
print("\n[1] /api/* without, with a wrong, and with the right token")
r = client.get("/api/guard/status")
check(r.status_code == 401, f"no token → 401 (got {r.status_code})")
check(r.json().get("auth") is False and r.json().get("ok") is False, "401 body says why")
r = client.get("/api/guard/status", headers={"X-Aura-Token": "x" * 43})
check(r.status_code == 401, "wrong token → 401")
r = client.get("/api/guard/status", headers={"X-Aura-Token": TOKEN[:-1]})
check(r.status_code == 401, "token minus one char → 401")
r = client.get("/api/guard/status", headers=GOOD)
check(r.status_code == 200 and "active" in r.json(), "right token → 200 with the real body")
r = client.post("/api/tasks", json={"title": "should never be stored"})
check(r.status_code == 401, "a write without the token never reaches the store")
check(not any(t[1] == "should never be stored" for t in mstore.get_tasks()),
      "…and nothing was written")
r = client.post("/api/domain/shell/run", json={"cmd": "echo hi"})
check(r.status_code == 401, "Domain shell without the token → 401")
r = client.get("/api/tasks", headers={"x-aura-token": TOKEN})
check(r.status_code == 200, "header name is case-insensitive")


# ── 2. loopback Host only ──────────────────────────────────────────────────
print("\n[2] Host header")
for host, want in [("127.0.0.1:8760", 200), ("localhost:8760", 200), ("[::1]:8760", 200),
                   ("evil.example:8760", 403), ("127.0.0.1.evil.example", 403), ("", 403)]:
    r = client.get("/api/guard/status", headers={**GOOD, "Host": host})
    check(r.status_code == want, f"Host {host!r} → {want} (got {r.status_code})")


# ── 3. CORS ────────────────────────────────────────────────────────────────
print("\n[3] CORS: AURA's own origins only, and refusals stay readable")
pre = {"Access-Control-Request-Method": "POST",
       "Access-Control-Request-Headers": "content-type,x-aura-token"}
for origin in ["null", "http://localhost:5173", "http://127.0.0.1:5173"]:
    r = client.options("/api/tasks", headers={"Origin": origin, **pre})
    check(r.status_code == 200 and r.headers.get("access-control-allow-origin") == origin,
          f"preflight from {origin} allowed")
    check("x-aura-token" in r.headers.get("access-control-allow-headers", "").lower(),
          f"preflight from {origin} allows the token header")
r = client.options("/api/tasks", headers={"Origin": "https://evil.example", **pre})
check(r.status_code == 400 and "access-control-allow-origin" not in r.headers,
      "preflight from another site refused")
r = client.get("/api/tasks", headers={"Origin": "https://evil.example", **GOOD})
check("access-control-allow-origin" not in r.headers, "another site can't read responses")
r = client.get("/api/tasks", headers={"Origin": "null"})
check(r.status_code == 401 and r.headers.get("access-control-allow-origin") == "null",
      "a 401 to the packaged app carries CORS headers (CORS wraps the gate)")


# ── 4. what stays open ─────────────────────────────────────────────────────
print("\n[4] open surfaces")
r = client.get("/health")
check(r.status_code == 200, "/health needs no token")
r = client.get("/api/connectors/callback/github", params={"error": "access_denied"})
check(r.status_code == 200 and "text/html" in r.headers.get("content-type", ""),
      "OAuth callback reachable by the provider's redirect")
r = client.get("/api/connectors/github/auth")
check(r.status_code == 401, "…but starting OAuth needs the token")
for path in ["/web/api/session", "/", "/index.html", "/apis", "/wsx"]:
    check(local_auth.verdict({"type": "http", "method": "GET", "path": path,
                              "headers": [(b"host", b"evil.example")]}) is None,
          f"{path} is not a private surface")
for path in ["/api", "/api/", "/api/tasks", "/ws"]:
    check(local_auth.is_private(path), f"{path} is private")


# ── 5. websocket ───────────────────────────────────────────────────────────
print("\n[5] /ws")


def ws_refused(**kw) -> bool:
    try:
        with client.websocket_connect(kw.pop("url", WS), **kw) as ws:
            ws.receive_json()
        return False
    except WebSocketDisconnect as e:
        return e.code == 1008
    except Exception:  # noqa: BLE001 - handshake rejected outright
        return True


check(ws_refused(), "no subprotocol → refused")
check(ws_refused(subprotocols=["aura"]), "no token → refused")
check(ws_refused(subprotocols=["aura", "aura-token." + "y" * 43]), "wrong token → refused")
check(ws_refused(subprotocols=["aura", "aura-token." + TOKEN],
                 headers={"host": "evil.example:8760"}), "right token, foreign Host → refused")
with client.websocket_connect(WS, subprotocols=["aura", "aura-token." + TOKEN]) as ws:
    check(ws.accepted_subprotocol == "aura", "right token → accepted, echoes 'aura'")
    first = ws.receive_json()
    check(first.get("type") == "state", "…and the chat protocol starts as usual")


# ── 6. the token itself ────────────────────────────────────────────────────
print("\n[6] token source and file")
check(len(TOKEN) >= 43, "random token is 256 bits (43 urlsafe chars)")
check(not local_auth.token_ok("") and not local_auth.token_ok(None), "empty never matches")
os.environ["AURA_TOKEN"] = "short"
check(local_auth._new_token() != "short", "a short AURA_TOKEN is ignored")
os.environ["AURA_TOKEN"] = "z" * 43
check(local_auth._new_token() == "z" * 43, "Electron's AURA_TOKEN is used")
os.environ.pop("AURA_TOKEN")
check(local_auth._new_token() != local_auth._new_token(), "a fresh one every start")

f = Path(_TMP) / "memory" / "session.token"
check(local_auth.write_token_file(f), "token file written")
check(f.read_text(encoding="utf-8") == TOKEN, "file holds exactly the live token")
if os.name == "posix":
    check(stat.S_IMODE(f.stat().st_mode) == 0o600, "file is owner-only (0600)")
check(local_auth.write_token_file(f) and f.read_text(encoding="utf-8") == TOKEN,
      "rewriting replaces it cleanly")
check(not (Path(_TMP) / "memory" / "session.tmp").exists(), "no temp file left behind")


print("\n" + ("ALL PASS ✅" if not _fails else f"FAILURES ({len(_fails)}): {_fails}"))
sys.exit(1 if _fails else 0)
