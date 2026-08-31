"""
AURA on the web — the public, sandboxed face of AURA.

Why this exists
---------------
`server.py` is AURA's *private* bridge: its WebSocket runs the real
ConversationDirector, which reads and writes shaurya's own SQLite memory,
watches his screen, and can be told to run code. None of that may be exposed
to a stranger on the internet.

So the website gets its own surface. Same brain path (`core.ai_router` →
Groq), same personality, but:

  * **no writes to the personal store** — a web visitor's turns live in RAM,
    in a per-session object that expires; nothing touches memory/store.py.
  * **no reads of the personal store** — the demo's "memory" is the visitor's
    own session facts, not shaurya's; the Project Brain preview serves a
    curated snapshot (`web/demo_project.json`) unless
    `AURA_WEB_LIVE_DOMAIN=1` explicitly opts the real graph in.
  * **no tools** — no filesystem, no shell, no screen, no git.
  * **budgeted** — per-session message cap, per-IP rate limit, small model by
    default, so a demo tab can never eat the quota the desktop app needs.

Surfaces (all under /web/api)
-----------------------------
  GET  /web/api/session          session handshake: id, limits, model, flags
  POST /web/api/chat             SSE stream: state → chunk* → done | error
  POST /web/api/reset            forget this session's transcript + facts
  GET  /web/api/memory           session facts + notes
  POST /web/api/memory/facts     remember a fact for this session
  DEL  /web/api/memory/facts/{i} forget one
  POST /web/api/memory/notes     jot a note
  GET  /web/api/domain/projects  Project Brain preview: project list
  GET  /web/api/domain/project/{pid}  overview + features + timeline + graph

The static landing page is mounted by `mount_site(app)` at "/" (served from
the `web/` directory next to this file).

Env
---
  AURA_WEB_MODEL        model id for the demo (default: gpt-oss-20b)
  AURA_WEB_MSG_LIMIT    messages per session   (default: 20)
  AURA_WEB_IP_PER_MIN   requests per IP/minute (default: 30)
  AURA_WEB_TTL_MIN      idle session lifetime  (default: 45)
  AURA_WEB_LIVE_DOMAIN  "1" → serve the REAL Project Brain (self-host only)
  AURA_WEB_SITE         "0" → don't mount the static site
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Iterable

from fastapi import APIRouter, Body, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/web/api", tags=["web"])

HERE = Path(__file__).resolve().parent
SITE_DIR = HERE / "web"

# ---------------------------------------------------------------------------
# Budget knobs
# ---------------------------------------------------------------------------
DEMO_MODEL = os.getenv("AURA_WEB_MODEL", "openai/gpt-oss-20b")
MSG_LIMIT = int(os.getenv("AURA_WEB_MSG_LIMIT", "20"))
IP_PER_MIN = int(os.getenv("AURA_WEB_IP_PER_MIN", "30"))
SESSION_TTL = int(os.getenv("AURA_WEB_TTL_MIN", "45")) * 60
MAX_SESSIONS = 500
MAX_TURNS = 12          # transcript window handed to the model
MAX_FACTS = 12
MAX_INPUT_CHARS = 1200

LIVE_DOMAIN = os.getenv("AURA_WEB_LIVE_DOMAIN", "") == "1"


# ---------------------------------------------------------------------------
# Sessions (RAM only — deliberately not persisted)
# ---------------------------------------------------------------------------
class WebSession:
    __slots__ = ("id", "created", "seen", "turns", "facts", "notes", "used")

    def __init__(self, sid: str) -> None:
        self.id = sid
        self.created = time.time()
        self.seen = time.time()
        self.turns: list[tuple[str, str]] = []   # (role, text)
        self.facts: list[dict[str, Any]] = []
        self.notes: list[dict[str, Any]] = []
        self.used = 0

    def touch(self) -> None:
        self.seen = time.time()

    def remaining(self) -> int:
        return max(0, MSG_LIMIT - self.used)

    def public(self) -> dict[str, Any]:
        return {
            "session": self.id,
            "used": self.used,
            "remaining": self.remaining(),
            "limit": MSG_LIMIT,
            "fact_count": len(self.facts),
            "note_count": len(self.notes),
        }


_SESSIONS: dict[str, WebSession] = {}
_SESSION_LOCK = threading.Lock()
_IP_HITS: dict[str, deque[float]] = {}


def _sweep() -> None:
    now = time.time()
    dead = [k for k, s in _SESSIONS.items() if now - s.seen > SESSION_TTL]
    for k in dead:
        _SESSIONS.pop(k, None)
    if len(_SESSIONS) > MAX_SESSIONS:
        oldest = sorted(_SESSIONS.values(), key=lambda s: s.seen)
        for s in oldest[: len(_SESSIONS) - MAX_SESSIONS]:
            _SESSIONS.pop(s.id, None)


def _session(token: str | None, create: bool = True) -> WebSession:
    with _SESSION_LOCK:
        _sweep()
        if token and token in _SESSIONS:
            s = _SESSIONS[token]
            s.touch()
            return s
        if not create:
            raise HTTPException(404, "unknown session")
        sid = secrets.token_urlsafe(12)
        s = WebSession(sid)
        _SESSIONS[sid] = s
        return s


def _rate_limit(request: Request) -> None:
    ip = (request.client.host if request.client else "?") or "?"
    now = time.time()
    hits = _IP_HITS.setdefault(ip, deque())
    while hits and now - hits[0] > 60:
        hits.popleft()
    if len(hits) >= IP_PER_MIN:
        raise HTTPException(429, "Too many requests — give it a minute.")
    hits.append(now)
    if len(_IP_HITS) > 2000:                      # keep the dict from growing
        for k in [k for k, v in _IP_HITS.items() if not v][:1000]:
            _IP_HITS.pop(k, None)


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------
_WEB_ADDON = """

YOU ARE RUNNING AS THE PUBLIC WEB DEMO OF AURA.
- The person talking to you is a visitor trying AURA in a browser tab, not your owner.
- You have NO screen access, NO file access, NO terminal, NO voice here. If asked
  for any of those, say plainly that they live in the desktop app and move on.
- Your memory here is this browser session only. You remember what they told you
  in this tab; you know nothing about them from before it.
- Never claim to have done something you cannot do here.
- Be the same AURA: dry, direct, useful. Do not sell the product. No marketing voice.
"""

_INTENT_HINTS: list[tuple[tuple[str, ...], str]] = [
    (("code", "function", "bug", "error", "python", "javascript", "regex",
      "sql", "refactor", "stack trace", "compile", "typescript"), "CODING"),
    (("explain", "what is", "how does", "difference between", "why does",
      "teach me", "eli5"), "EXPLAIN"),
    (("plan", "roadmap", "architecture", "design a", "how should i build",
      "approach"), "PLAN"),
    (("compare", "research", "pros and cons", "trade-off", "tradeoff"), "RESEARCH"),
]


def _guess_intent(text: str) -> str:
    low = text.lower()
    for needles, intent in _INTENT_HINTS:
        if any(n in low for n in needles):
            return intent
    return "CASUAL"


def _facts_block(s: WebSession) -> str:
    if not s.facts:
        return ""
    lines = [f"- {f['fact']}" for f in s.facts[-MAX_FACTS:]]
    return (
        "\n\nWHAT THIS VISITOR HAS TOLD YOU TO REMEMBER (this session only):\n"
        + "\n".join(lines)
    )


def _notes_block(s: WebSession) -> str:
    if not s.notes:
        return ""
    lines = [f"- {n['text']}" for n in s.notes[-6:]]
    return "\n\nNOTES THEY SAVED IN THIS SESSION:\n" + "\n".join(lines)


def _build_system(s: WebSession) -> str:
    try:
        from core.personality import DONNA_SYSTEM_PROMPT
        base = DONNA_SYSTEM_PROMPT
    except Exception:  # noqa: BLE001
        base = "You are AURA, a sharp, dry, useful AI companion."
    return base + _WEB_ADDON + _facts_block(s) + _notes_block(s)


def _build_prompt(s: WebSession, text: str) -> str:
    if not s.turns:
        return text
    lines = []
    for role, body in s.turns[-MAX_TURNS:]:
        who = "User" if role == "user" else "AURA"
        lines.append(f"{who}: {body}")
    lines.append(f"User: {text}")
    lines.append("AURA:")
    return "CONVERSATION SO FAR:\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Chat (SSE)
# ---------------------------------------------------------------------------
def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def _stream_worker(gen: Iterable[str], loop: asyncio.AbstractEventLoop,
                   q: asyncio.Queue) -> None:
    def put(item):
        try:
            loop.call_soon_threadsafe(q.put_nowait, item)
        except RuntimeError:      # loop closed — client vanished
            pass
    try:
        for chunk in gen:
            put(("chunk", chunk))
    except Exception as e:  # noqa: BLE001
        put(("error", f"{type(e).__name__}: {e}"))
    finally:
        put(("eof", ""))


@router.get("/session")
async def web_session(x_aura_session: str | None = Header(default=None)) -> dict[str, Any]:
    s = _session(x_aura_session)
    return {
        **s.public(),
        "model": DEMO_MODEL,
        "live_domain": LIVE_DOMAIN,
        "capabilities": {
            "chat": True, "memory": True, "domain": True,
            "voice": False, "screen": False, "files": False, "terminal": False,
        },
    }


@router.post("/reset")
async def web_reset(x_aura_session: str | None = Header(default=None)) -> dict[str, Any]:
    s = _session(x_aura_session)
    s.turns.clear()
    s.facts.clear()
    s.notes.clear()
    s.used = 0
    return s.public()


@router.post("/chat")
async def web_chat(request: Request,
                   payload: dict = Body(...),
                   x_aura_session: str | None = Header(default=None)):
    _rate_limit(request)
    s = _session(x_aura_session)

    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "empty message")
    if len(text) > MAX_INPUT_CHARS:
        text = text[:MAX_INPUT_CHARS]
    if s.remaining() <= 0:
        raise HTTPException(429, "demo limit reached")

    s.used += 1
    intent = _guess_intent(text)
    system = _build_system(s)
    prompt = _build_prompt(s, text)

    try:
        from core import ai_router
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"brain unavailable: {e}") from e

    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    gen = ai_router.call_groq_streaming(
        prompt, system=system, intent=intent, model=DEMO_MODEL
    )
    threading.Thread(target=_stream_worker, args=(gen, loop, q), daemon=True).start()

    async def events():
        yield _sse("state", {"state": "thinking", "intent": intent, "model": DEMO_MODEL})
        parts: list[str] = []
        failed = ""
        started = False
        while True:
            kind, body = await q.get()
            if kind == "eof":
                break
            if kind == "error":
                failed = body
                break
            if body in ("RATE_LIMIT", "CONNECTION_ERROR"):
                failed = body
                break
            if not started:
                started = True
                yield _sse("state", {"state": "speaking"})
            parts.append(body)
            yield _sse("chunk", {"text": body})

        raw = "".join(parts).strip()
        if failed or not raw:
            msg = {
                "RATE_LIMIT": "The free-tier model is rate-limited right now. "
                              "Give it twenty seconds and ask again.",
                "CONNECTION_ERROR": "I can't reach the model from here. "
                                    "Check the server's API key.",
            }.get(failed, "Something broke on the way back. Try again.")
            s.used = max(0, s.used - 1)          # don't charge for a failure
            yield _sse("error", {"message": msg, "code": failed or "empty"})
            return

        try:
            from core.ai_router import sanitize_text
            final = sanitize_text(raw, text) or raw
        except Exception:  # noqa: BLE001
            final = raw

        s.turns.append(("user", text))
        s.turns.append(("aura", final))
        del s.turns[:-MAX_TURNS * 2]

        yield _sse("done", {
            "text": final, "model": DEMO_MODEL, "intent": intent,
            **s.public(),
        })

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "X-Aura-Session": s.id,
        },
    )


# ---------------------------------------------------------------------------
# Session memory (facts + notes) — the demo's honest version of memory/store.py
# ---------------------------------------------------------------------------
@router.get("/memory")
async def web_memory(x_aura_session: str | None = Header(default=None)) -> dict[str, Any]:
    s = _session(x_aura_session)
    return {**s.public(), "facts": s.facts, "notes": s.notes}


@router.post("/memory/facts")
async def web_add_fact(request: Request,
                       payload: dict = Body(...),
                       x_aura_session: str | None = Header(default=None)) -> dict[str, Any]:
    _rate_limit(request)
    s = _session(x_aura_session)
    fact = (payload.get("fact") or "").strip()
    if not fact:
        raise HTTPException(400, "empty fact")
    if len(s.facts) >= MAX_FACTS:
        raise HTTPException(429, f"demo keeps {MAX_FACTS} facts — delete one first")
    entry = {
        "id": secrets.token_hex(4),
        "fact": fact[:240],
        "category": (payload.get("category") or "general").strip()[:24] or "general",
        "created_at": time.strftime("%Y-%m-%d %H:%M"),
    }
    s.facts.append(entry)
    return {**s.public(), "fact": entry, "facts": s.facts}


@router.delete("/memory/facts/{fact_id}")
async def web_del_fact(fact_id: str,
                       x_aura_session: str | None = Header(default=None)) -> dict[str, Any]:
    s = _session(x_aura_session)
    s.facts = [f for f in s.facts if f["id"] != fact_id]
    return {**s.public(), "facts": s.facts}


@router.post("/memory/notes")
async def web_add_note(request: Request,
                       payload: dict = Body(...),
                       x_aura_session: str | None = Header(default=None)) -> dict[str, Any]:
    _rate_limit(request)
    s = _session(x_aura_session)
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "empty note")
    if len(s.notes) >= 20:
        raise HTTPException(429, "demo keeps 20 notes")
    entry = {
        "id": secrets.token_hex(4),
        "text": text[:600],
        "created_at": time.strftime("%Y-%m-%d %H:%M"),
    }
    s.notes.append(entry)
    return {**s.public(), "note": entry, "notes": s.notes}


# ---------------------------------------------------------------------------
# Project Brain preview (read-only)
# ---------------------------------------------------------------------------
_DEMO_CACHE: dict[str, Any] | None = None


def _demo_data() -> dict[str, Any]:
    global _DEMO_CACHE
    if _DEMO_CACHE is None:
        path = SITE_DIR / "demo_project.json"
        try:
            _DEMO_CACHE = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            _DEMO_CACHE = {"projects": []}
    return _DEMO_CACHE


def _live_projects() -> list[dict[str, Any]] | None:
    if not LIVE_DOMAIN:
        return None
    try:
        from core.domain import brain_store
        return [
            {"id": p["id"], "name": p["name"], "root": "", "repo_url": ""}
            for p in brain_store.list_projects()
        ]
    except Exception:  # noqa: BLE001
        return None


@router.get("/domain/projects")
async def web_projects() -> dict[str, Any]:
    live = _live_projects()
    if live is not None:
        return {"projects": live, "source": "live"}
    return {
        "projects": [
            {"id": p["id"], "name": p["name"], "summary": p.get("summary", "")}
            for p in _demo_data().get("projects", [])
        ],
        "source": "sample",
    }


@router.get("/domain/project/{pid}")
async def web_project(pid: str) -> dict[str, Any]:
    if LIVE_DOMAIN:
        try:
            from core.domain import brain_store, progress
            proj = brain_store.get_project(pid)
            if proj:
                return {
                    "source": "live",
                    "project": {"id": proj["id"], "name": proj["name"],
                                "summary": proj.get("summary", "")},
                    "overall": progress.overall(pid),
                    "features": progress.feature_progress(pid),
                    "blocker": progress.biggest_blocker(pid),
                    "counts": brain_store.counts(pid),
                    "timeline": [],
                    "graph": {"nodes": [], "edges": []},
                }
        except Exception:  # noqa: BLE001
            pass
    for p in _demo_data().get("projects", []):
        if p["id"] == pid:
            return {"source": "sample", **p}
    raise HTTPException(404, "no such project")


# ---------------------------------------------------------------------------
# Static site
# ---------------------------------------------------------------------------
def mount_site(app) -> bool:
    """Mount the marketing site at "/". Call AFTER every API router."""
    if os.getenv("AURA_WEB_SITE", "1") != "1":
        return False
    if not SITE_DIR.is_dir():
        print(f"[AURA web] site directory missing: {SITE_DIR}")
        return False
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(SITE_DIR), html=True), name="aura-site")
    print(f"[AURA web] landing site mounted at / from {SITE_DIR}")
    return True
