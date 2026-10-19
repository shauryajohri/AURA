"""
guard_api.py — Buddy Lock over HTTP, plus the gate in front of the REST API.

    GET    /api/guard/status          who AURA is serving right now
    POST   /api/guard/prepare         load (first time: download) the models
    POST   /api/guard/frame           a camera frame → presence update
    POST   /api/guard/unlock/pin      PIN → 10-minute owner session
    POST   /api/guard/unlock/voice    a spoken line → same session, if it's their voice
    POST   /api/guard/enroll/face     3+ frames of the owner's face
    POST   /api/guard/enroll/voice    2+ recordings of the owner's voice
    POST   /api/guard/pin             set / change the backup PIN
    POST   /api/guard/enable|disable  switch the lock on / off
    POST   /api/guard/reset           forget the owner entirely
    POST   /api/guard/guest           owner lets a guest use AURA
    DELETE /api/guard/guest           end guest access
    POST   /api/guard/lock            lock right now

Anything that weakens the lock (disable, reset, re-enroll, change PIN, grant a
guest) needs the owner's face in a frame sent WITH the request, or the PIN —
"the owner was here a minute ago" is not enough for those.

Frames arrive as base64 JPEG, audio as base64 16 kHz WAV. Neither is stored.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import re
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.guard import get_guard

router = APIRouter()


class _QuietPresence(logging.Filter):
    """The presence loop posts a frame every few seconds; logging each one
    would bury everything else in the terminal and logs/brain.log."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "/api/guard/frame" not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(_QuietPresence())

MIN_ENROLL_FACES = 3
MIN_ENROLL_VOICES = 2
ENROLL_MIN_VOICED_S = 1.5
_PIN_RE = re.compile(r"^\d{4,12}$")


# ── helpers ────────────────────────────────────────────────────────────────
def b64bytes(raw: Any) -> bytes | None:
    """Decode base64, tolerating a data: URL prefix. None for junk."""
    if not raw or not isinstance(raw, str):
        return None
    if raw.lstrip().startswith("data:") and "," in raw[:80]:
        raw = raw.split(",", 1)[1]
    try:
        return base64.b64decode(raw, validate=False) or None
    except (binascii.Error, ValueError):
        return None


def _deny(msg: str, status: int = 403) -> JSONResponse:
    return JSONResponse({"ok": False, "error": msg}, status_code=status)


async def _owner_ok(body: dict) -> bool:
    """Sensitive actions: lock not active yet (first setup), or the owner
    proves it right now — face in this frame, or the PIN."""
    g = get_guard()
    if not g.active:
        return True
    frame = b64bytes(body.get("frame"))
    pin = str(body.get("pin") or "") or None
    return await asyncio.to_thread(g.verify_owner_now, frame, pin)


_OWNER_PROOF = "Show your face to the camera or enter your PIN to do that."


# ── status & presence ──────────────────────────────────────────────────────
@router.get("/api/guard/status")
async def guard_status() -> dict[str, Any]:
    from core.guard import face, voice
    st = get_guard().status()
    st["engines"] = {
        "face": {"ready": face.ENGINE._recognizer is not None, "error": face.ENGINE._error},
        "voice": {"ready": voice.ENGINE._extractor is not None, "error": voice.ENGINE._error},
    }
    return st


@router.post("/api/guard/prepare")
async def guard_prepare() -> dict[str, Any]:
    """Load both engines, downloading models the first time (~80 MB total).
    Slow once, instant after; the setup screen calls it before capturing."""
    from core.guard import face, voice
    face.ENGINE.reset()
    voice.ENGINE.reset()
    f_ok, f_err = await asyncio.to_thread(face.ENGINE.available)
    v_ok, v_err = await asyncio.to_thread(voice.ENGINE.available)
    return {"ok": f_ok, "face": {"ready": f_ok, "error": f_err},
            "voice": {"ready": v_ok, "error": v_err}}


@router.post("/api/guard/frame")
async def guard_frame(req: Request) -> dict[str, Any]:
    g = get_guard()
    body = await req.json()
    frame = b64bytes(body.get("frame"))
    seen: dict[str, Any] = {}
    if frame and (g.active or body.get("preview")):
        try:
            s = await asyncio.to_thread(g.observe, frame)
            seen = {"faces": s.faces, "owner": s.owner}
        except (RuntimeError, ValueError) as e:
            seen = {"error": str(e)}
    return {"ok": True, "seen": seen, "status": g.status()}


@router.post("/api/guard/unlock/pin")
async def guard_unlock_pin(req: Request):
    body = await req.json()
    ok, why = get_guard().unlock_pin(str(body.get("pin") or ""))
    if not ok:
        return _deny(why, 401)
    return {"ok": True, "status": get_guard().status()}


@router.post("/api/guard/unlock/voice")
async def guard_unlock_voice(req: Request):
    g = get_guard()
    body = await req.json()
    audio = b64bytes(body.get("audio"))
    if not audio:
        return _deny("no audio", 400)
    if not g.vault.voices:
        return _deny("Voice unlock isn't set up — enroll your voice in Settings first.", 400)
    if not g.active:
        return {"ok": True, "status": g.status()}
    ok, why = await asyncio.to_thread(g.unlock_voice, audio)
    if ok:
        return {"ok": True, "status": g.status()}
    return _deny("I need a little more — say a full sentence." if why == "short"
                 else "That didn't sound like you.", 401)


# ── enrollment ─────────────────────────────────────────────────────────────
@router.post("/api/guard/enroll/face")
async def guard_enroll_face(req: Request):
    from core.guard import face
    g = get_guard()
    body = await req.json()
    if not await _owner_ok(body):
        return _deny(_OWNER_PROOF)

    frames = [b64bytes(f) for f in (body.get("frames") or [])][:12]
    good, problems = [], []
    for i, fr in enumerate(frames):
        if not fr:
            problems.append(f"shot {i + 1}: empty")
            continue
        try:
            faces = await asyncio.to_thread(face.ENGINE.analyze, fr)
        except RuntimeError as e:
            return _deny(str(e), 503)
        except ValueError:
            problems.append(f"shot {i + 1}: not an image")
            continue
        if len(faces) != 1:
            problems.append(f"shot {i + 1}: {'no face' if not faces else 'more than one face'}")
        elif faces[0].box[2] < face.ENROLL_MIN_WIDTH:
            problems.append(f"shot {i + 1}: too far from the camera")
        else:
            good.append(faces[0].embedding)

    if len(good) < MIN_ENROLL_FACES:
        return JSONResponse({"ok": False, "accepted": len(good), "problems": problems,
                             "error": f"Only {len(good)} usable shots — need {MIN_ENROLL_FACES}. "
                                      "Sit closer, face the light, and make sure you're alone in frame."},
                            status_code=422)

    # Every shot must be the same person — a friend leaning in for one shot
    # would otherwise become part of "the owner".
    from core.guard.face import cosine
    ref = good[0]
    if any(cosine(ref, e) < 0.42 for e in good[1:]):
        return _deny("Those shots don't all look like the same person — try again alone.", 422)

    if body.get("owner_name"):
        g.vault.set_owner_name(str(body["owner_name"]))
    n = g.vault.add_faces(good, replace=bool(body.get("replace", True)))
    return {"ok": True, "accepted": len(good), "problems": problems, "face_samples": n,
            "status": g.status()}


@router.post("/api/guard/enroll/voice")
async def guard_enroll_voice(req: Request):
    from core.guard import voice
    g = get_guard()
    body = await req.json()
    if not await _owner_ok(body):
        return _deny(_OWNER_PROOF)

    clips = [b64bytes(a) for a in (body.get("audio") or [])][:8]
    good, problems = [], []
    for i, clip in enumerate(clips):
        if not clip:
            problems.append(f"clip {i + 1}: empty")
            continue
        try:
            sample = await asyncio.to_thread(voice.ENGINE.embed, clip)
        except RuntimeError as e:
            return _deny(str(e), 503)
        except Exception:  # noqa: BLE001 - wave.Error and friends
            problems.append(f"clip {i + 1}: unreadable audio")
            continue
        if sample.embedding is None or sample.voiced_seconds < ENROLL_MIN_VOICED_S:
            problems.append(f"clip {i + 1}: only {sample.voiced_seconds:.1f}s of speech")
        else:
            good.append(sample.embedding)

    if len(good) < MIN_ENROLL_VOICES:
        return JSONResponse({"ok": False, "accepted": len(good), "problems": problems,
                             "error": "Need at least two clear recordings — read the whole line, "
                                      "in your normal voice."}, status_code=422)
    g.vault.clear_voice()
    n = g.vault.add_voices(good)
    return {"ok": True, "accepted": len(good), "problems": problems, "voice_samples": n}


@router.delete("/api/guard/enroll/voice")
async def guard_forget_voice(req: Request):
    body = await req.json() if (await req.body()) else {}
    if not await _owner_ok(body):
        return _deny(_OWNER_PROOF)
    get_guard().vault.clear_voice()
    return {"ok": True}


@router.post("/api/guard/pin")
async def guard_set_pin(req: Request):
    g = get_guard()
    body = await req.json()
    new = str(body.get("new_pin") or "")
    if not _PIN_RE.match(new):
        return _deny("A PIN is 4–12 digits.", 400)
    if not await _owner_ok(body):
        return _deny(_OWNER_PROOF)
    g.vault.set_pin(new)
    return {"ok": True}


# ── on / off ───────────────────────────────────────────────────────────────
@router.post("/api/guard/enable")
async def guard_enable(req: Request):
    g = get_guard()
    body = await req.json() if (await req.body()) else {}
    if g.active:
        return {"ok": True, "status": g.status()}
    if len(g.vault.faces) < MIN_ENROLL_FACES:
        return _deny("Enroll your face first.", 400)
    if not g.vault.has_pin:
        return _deny("Set a backup PIN first — it's how you get in if the camera can't see you.", 400)
    if not await _owner_ok(body):
        return _deny(_OWNER_PROOF)
    g.vault.set_enabled(True)
    # Turning it on from the setup screen: the owner just enrolled in front of
    # the camera, so start them unlocked rather than locking them out.
    frame = b64bytes(body.get("frame"))
    if frame:
        try:
            await asyncio.to_thread(g.observe, frame)
        except (RuntimeError, ValueError):
            pass
    return {"ok": True, "status": g.status()}


@router.post("/api/guard/disable")
async def guard_disable(req: Request):
    g = get_guard()
    body = await req.json() if (await req.body()) else {}
    if not await _owner_ok(body):
        return _deny(_OWNER_PROOF)
    g.vault.set_enabled(False)
    g.revoke()
    return {"ok": True, "status": g.status()}


@router.post("/api/guard/reset")
async def guard_reset(req: Request):
    g = get_guard()
    body = await req.json() if (await req.body()) else {}
    if not g.vault.corrupt and not await _owner_ok(body):
        return _deny(_OWNER_PROOF)
    g.vault.reset()
    g.revoke()
    g.lock_now()
    return {"ok": True, "status": g.status()}


# ── guests ─────────────────────────────────────────────────────────────────
@router.post("/api/guard/guest")
async def guard_grant_guest(req: Request):
    from core.guard.commands import DEFAULT_MINUTES, MAX_MINUTES
    g = get_guard()
    body = await req.json() if (await req.body()) else {}
    if not g.active:
        return _deny("Buddy Lock is off — everyone can already talk to AURA.", 400)
    if not await _owner_ok(body):
        return _deny(_OWNER_PROOF)
    try:
        minutes = int(body.get("minutes") or DEFAULT_MINUTES)
    except (TypeError, ValueError):
        minutes = DEFAULT_MINUTES
    msg = g.grant(max(1, min(MAX_MINUTES, minutes)))
    return {"ok": True, "message": msg, "status": g.status()}


@router.delete("/api/guard/guest")
async def guard_revoke_guest() -> dict[str, Any]:
    g = get_guard()
    return {"ok": True, "message": g.revoke(), "status": g.status()}


@router.post("/api/guard/lock")
async def guard_lock() -> dict[str, Any]:
    g = get_guard()
    g.lock_now()
    return {"ok": True, "status": g.status()}


# ── the REST gate ──────────────────────────────────────────────────────────
# What a guest's Home screen needs to chat, and nothing of the owner's: no
# memory, chats, tasks, rooms, files, terminal or connectors.
GUEST_ALLOWED = {
    ("GET", "/api/settings"),
    ("GET", "/api/status"),
    ("GET", "/api/models"),
    ("GET", "/api/nature"),
    ("GET", "/api/voice/voices"),
    ("POST", "/api/voice/transcribe"),
}


def rest_verdict(method: str, path: str) -> tuple[int, dict] | None:
    """None = let it through; else (status, body) to refuse with."""
    if not path.startswith("/api/") or path.startswith("/api/guard/"):
        return None
    try:
        g = get_guard()
        if not g.active:
            return None
        role = g.role()
    except Exception as e:  # noqa: BLE001 - a broken guard fails CLOSED
        return 423, {"ok": False, "locked": True, "error": f"Buddy Lock error: {e}"}
    if role == "owner":
        return None
    if role == "guest":
        if (method, path) in GUEST_ALLOWED:
            return None
        return 403, {"ok": False, "guest": True,
                     "error": f"That's {g.owner_name()}'s — guests can only chat."}
    return 423, {"ok": False, "locked": True,
                 "error": f"AURA is locked — she only opens up for {g.owner_name()}."}


class GuardMiddleware:
    """Pure ASGI (not BaseHTTPMiddleware) so streamed responses and
    websockets pass through untouched. Register it BEFORE CORSMiddleware:
    the middleware added last is outermost, and CORS must wrap this so a
    refusal still carries the headers the renderer needs to read it."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("method") != "OPTIONS":
            verdict = rest_verdict(scope.get("method", "GET"), scope.get("path", ""))
            if verdict:
                status, body = verdict
                await JSONResponse(body, status_code=status)(scope, receive, send)
                return
        await self.app(scope, receive, send)
