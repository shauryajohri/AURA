"""
AURA Remote — the phone's way in.

A second, tiny server that runs next to the main bridge. It does NOT reuse
server.py's port. The main bridge (127.0.0.1:8760) serves /ws, which runs the
real brain against shaurya's memory with no auth. That must never be reachable
from the network. This server holds only the remote-control routes, and every
one of them needs the token.

    GET  /                       the phone page (remote_ui/index.html)
    GET  /remote/api/status      is the laptop active? (presence gate)
    POST /remote/api/command     {"text": "..."} → job (declined | pending | running | done | failed | stopped)
    GET  /remote/api/jobs/{id}   poll a running vision job
    GET  /remote/api/jobs/{id}/screen   the laptop screen AURA last looked at (JPEG)
    POST /remote/api/jobs/{id}/approve
    POST /remote/api/jobs/{id}/cancel
    POST /remote/api/stop        abort the running job (between steps / keystroke chunks)
    GET  /remote/api/jobs        recent jobs

Auth: header `Authorization: Bearer <AURA_REMOTE_TOKEN>` (or `X-Aura-Token`).
After 10 bad tokens in 10 minutes an IP is locked out for 10 minutes.

There is also `local_router`, mounted on the main bridge at /api/remote, so the
desktop UI (localhost only) can pause remote control and see what ran.

Env
---
  AURA_REMOTE_TOKEN         required to enable; at least 16 characters
  AURA_REMOTE_HOST          bind address (default 0.0.0.0 — same Wi-Fi / Tailscale)
  AURA_REMOTE_PORT          default 8761
  AURA_REMOTE_CONFIRM       risky (default) | all | none
  AURA_REMOTE_ALLOW_SHELL   "1" lets AURA plan run_shell steps (always asks first)
  AURA_REMOTE_MAX_IDLE_MIN  decline if the laptop has been idle longer (0 = off)
  AURA_REMOTE_VISION        auto (default) | off — use the vision loop for non-trivial commands
  AURA_VISION_MAX_STEPS     look-act rounds per command (default 15)

Run standalone:  python remote_api.py
"""

from __future__ import annotations

import os
import secrets
import threading
import time
import traceback
from collections import deque
from pathlib import Path

from fastapi import APIRouter, Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response

from core import remote_control as rc
from core import vision_agent

HERE = Path(__file__).resolve().parent
UI_PATH = HERE / "remote_ui" / "index.html"

MIN_TOKEN_LEN = 16
FAIL_LIMIT = 10
FAIL_WINDOW = 600

_FAILS: dict[str, deque[float]] = {}
_FAILS_LOCK = threading.Lock()


def _token() -> str:
    return (os.getenv("AURA_REMOTE_TOKEN") or "").strip()


def enabled() -> tuple[bool, str]:
    tok = _token()
    if not tok:
        return False, "AURA_REMOTE_TOKEN is not set"
    if len(tok) < MIN_TOKEN_LEN:
        return False, f"AURA_REMOTE_TOKEN must be at least {MIN_TOKEN_LEN} characters"
    return True, ""


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def require_token(request: Request) -> None:
    ok, why = enabled()
    if not ok:
        raise HTTPException(503, f"remote control disabled: {why}")
    ip = _client_ip(request)
    now = time.time()
    with _FAILS_LOCK:
        hits = _FAILS.setdefault(ip, deque())
        while hits and now - hits[0] > FAIL_WINDOW:
            hits.popleft()
        if len(hits) >= FAIL_LIMIT:
            raise HTTPException(429, "too many bad tokens, try again later")
    given = request.headers.get("x-aura-token", "")
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        given = auth[7:]
    if not given or not secrets.compare_digest(given.strip().encode(), _token().encode()):
        with _FAILS_LOCK:
            _FAILS.setdefault(ip, deque()).append(now)
        raise HTTPException(401, "bad token")


router = APIRouter(prefix="/remote/api", tags=["remote"], dependencies=[Depends(require_token)])


def _job_or_404(job) -> dict:
    if job is None:
        raise HTTPException(404, "unknown job")
    return job.public()


@router.get("/status")
def status() -> dict:
    gate = rc.presence()
    gate["confirm_mode"] = rc.confirm_mode()
    gate["shell_allowed"] = rc.shell_allowed()
    gate["vision"], gate["vision_why"] = vision_agent.available()
    return gate


@router.post("/command")
def command(body: dict = Body(...)) -> dict:
    return rc.submit(str(body.get("text") or "")).public()


@router.get("/jobs/{job_id}")
def job(job_id: str) -> dict:
    return _job_or_404(rc.get_job(job_id))


@router.get("/jobs/{job_id}/screen")
def job_screen(job_id: str) -> Response:
    img = rc.latest_screen(job_id)
    if img is None:
        raise HTTPException(404, "no screenshot for that job")
    return Response(img, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/jobs/{job_id}/approve")
def approve(job_id: str) -> dict:
    return _job_or_404(rc.approve(job_id))


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: str) -> dict:
    return _job_or_404(rc.cancel(job_id))


@router.post("/stop")
def stop() -> dict:
    rc.stop()
    return {"ok": True}


@router.get("/jobs")
def jobs() -> dict:
    return {"jobs": rc.recent_jobs()}


# Desktop-side controls, mounted on the main (localhost) bridge.
local_router = APIRouter(prefix="/api/remote", tags=["remote-local"])


@local_router.get("")
def local_state() -> dict:
    ok, why = enabled()
    return {"enabled": ok, "why": why, "paused": rc.is_paused(),
            "port": int(os.getenv("AURA_REMOTE_PORT", "8761")),
            "presence": rc.presence(), "jobs": rc.recent_jobs()}


@local_router.put("")
def local_update(body: dict = Body(...)) -> dict:
    if "paused" in body:
        rc.set_paused(bool(body["paused"]))
    if body.get("stop"):
        rc.stop()
    return local_state()


def build_app() -> FastAPI:
    app = FastAPI(title="AURA Remote", docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(router)

    @app.get("/", include_in_schema=False)
    def page():
        return FileResponse(UI_PATH, media_type="text/html")

    return app


_server_thread: threading.Thread | None = None


def start_in_background() -> bool:
    """Called by server.py at startup. No-op (returns False) unless a token is set."""
    global _server_thread
    ok, why = enabled()
    if not ok:
        print(f"[AURA remote] off — {why}")
        return False
    if _server_thread and _server_thread.is_alive():
        return True
    import uvicorn

    host = os.getenv("AURA_REMOTE_HOST", "0.0.0.0")
    port = int(os.getenv("AURA_REMOTE_PORT", "8761"))
    config = uvicorn.Config(build_app(), host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None  # main thread owns signals

    def _run():
        try:
            server.run()
        except Exception:  # noqa: BLE001
            traceback.print_exc()

    _server_thread = threading.Thread(target=_run, name="aura-remote", daemon=True)
    _server_thread.start()
    print(f"[AURA remote] phone control on http://{host}:{port}/")
    return True


if __name__ == "__main__":
    import uvicorn

    ok, why = enabled()
    if not ok:
        raise SystemExit(f"remote control disabled: {why}")
    uvicorn.run(build_app(), host=os.getenv("AURA_REMOTE_HOST", "0.0.0.0"),
                port=int(os.getenv("AURA_REMOTE_PORT", "8761")))
