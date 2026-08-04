"""
AURA web bridge - FastAPI + WebSocket face for the AURA brain.

Additive entry point. Does NOT touch main.py or the PySide6 app; both can run
against the same core.brain.

Surfaces
--------
1. Chat over /ws, routed through ConversationDirector (same as the PySide app):
   slash-modes (/code /research /plan /discussion), /prompt, /help, mode acks,
   and the coding permission gate all work here.
2. Auto-chat: proactive + attention + curiosity loops broadcast to all clients.
3. REST API over memory/store.py + core.model_lock for the sidebar views:
   /api/tasks, /api/models, /api/facts, /api/status.

WebSocket protocol (JSON over /ws)
----------------------------------
Client -> Server: {"type":"message","payload":{"text":"..."}} | {"type":"ping"}
Server -> Client:
    {"type":"state","payload":{"state":"idle|thinking|speaking"}}
    {"type":"chunk","payload":{"text":"..."}}
    {"type":"done","payload":{"text":"...","model":"..."}}
    {"type":"push","payload":{"text":"...","source":"proactive|curiosity|greeting|reply"}}
    {"type":"mode","payload":{"mode":"CHAT|CODE|RESEARCH|DISCUSSION|PLAN"}}
    {"type":"presence","payload":{"state":"working|idle|afk"}}
    {"type":"error","payload":{"message":"..."}}

Run:  python server.py    (uvicorn on 127.0.0.1:8760)
"""

from __future__ import annotations

import asyncio
import json
import traceback
import warnings
from contextlib import asynccontextmanager
from typing import Any, Callable

# pygame (pulled in by voice output) still imports pkg_resources — not our
# code, not actionable here. Hide the warning before anything imports pygame.
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")

# ----------------------------------------------------------------------------
# Windows asyncio noise: when a browser tab closes, the proactor transport
# raises ConnectionResetError (WinError 10054) INSIDE the event loop callback
# — after our code already handled the disconnect cleanly. Harmless, loud,
# unfixable from user code except here: swallow only that exact case.
# ----------------------------------------------------------------------------
try:  # pragma: no cover - Windows only
    from asyncio.proactor_events import _ProactorBasePipeTransport

    _orig_call_connection_lost = _ProactorBasePipeTransport._call_connection_lost

    def _quiet_call_connection_lost(self, exc):  # noqa: ANN001
        try:
            _orig_call_connection_lost(self, exc)
        except ConnectionResetError:
            pass  # client vanished mid-shutdown — already disconnected

    _ProactorBasePipeTransport._call_connection_lost = _quiet_call_connection_lost
except ImportError:
    pass

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from core.brain import process_streaming


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Modern replacement for the deprecated @app.on_event('startup')."""
    global MAIN_LOOP
    MAIN_LOOP = asyncio.get_running_loop()
    _init_director()
    _init_v3()
    _start_auto_chat()
    yield


app = FastAPI(title="AURA Bridge", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# Domain routes (filesystem, terminal, GitHub, OAuth connectors) live in their
# own module — if one of them fails to import, the brain still comes up.
try:
    from domain_api import router as domain_router
    app.include_router(domain_router)
    # Project Brain graph (Domain V2) shares the memory DB — create its tables.
    from core.domain import brain_store as _brain_store
    _brain_store.init_db()
    print("[AURA bridge] Domain API mounted")
except Exception:  # noqa: BLE001
    traceback.print_exc()

_DONE = object()

CLIENTS: set[WebSocket] = set()
MAIN_LOOP: asyncio.AbstractEventLoop | None = None
_AUTO_STARTED = False

# One shared Director owns modes + slash commands + the permission gate.
DIRECTOR: Any = None


# ----------------------------------------------------------------------------
# Broadcast helpers (safe from any thread)
# ----------------------------------------------------------------------------
async def _safe_send(ws: WebSocket, data: str) -> None:
    try:
        await ws.send_text(data)
    except Exception:
        CLIENTS.discard(ws)


def broadcast(msg: dict[str, Any]) -> None:
    if MAIN_LOOP is None:
        return
    data = json.dumps(msg)
    for ws in list(CLIENTS):
        asyncio.run_coroutine_threadsafe(_safe_send(ws, data), MAIN_LOOP)


def broadcast_push(text: str, source: str) -> None:
    if text:
        broadcast({"type": "push", "payload": {"text": text, "source": source}})


# ----------------------------------------------------------------------------
# Auto-chat loops
# ----------------------------------------------------------------------------
def _start_auto_chat() -> None:
    global _AUTO_STARTED
    if _AUTO_STARTED:
        return
    _AUTO_STARTED = True

    from core.brain import speak_response, start_proactive
    from core.curiosity_engine import start_curiosity_loop

    def speak_fn(text: str) -> None:
        try:
            speak_response(text, mode="CHAT")
        except Exception as e:  # noqa: BLE001
            print(f"[AURA bridge] TTS skipped: {e}")

    try:
        start_proactive(
            speak_fn=speak_fn,
            on_suggestion_fn=lambda t: broadcast_push(t, "proactive"),
            on_presence_fn=lambda s: broadcast({"type": "presence", "payload": {"state": s}}),
        )
    except Exception:  # noqa: BLE001
        traceback.print_exc()

    try:
        start_curiosity_loop(
            speak_fn=speak_fn,
            on_curiosity_fn=lambda t: broadcast_push(t, "curiosity"),
        )
    except Exception:  # noqa: BLE001
        traceback.print_exc()

    print("[AURA bridge] auto-chat loops started")


def _init_v3() -> None:
    """Point the V3 engines' announcement sink at the websocket.

    The bridge is deliberately transport-agnostic — it just calls whatever
    sink it's given — so this is the only place that knows V3 output reaches
    the UI as a websocket frame.
    """
    try:
        from core import v3_bridge
        v3_bridge.set_sink(lambda payload: broadcast({"type": "v3", "payload": payload}))
        # Boot = the start of this coding session, so flow/fatigue clocks and
        # the session summary measure from now rather than from the epoch.
        v3_bridge.start_session()
        print("[AURA bridge] V3 intelligence sink attached")
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    try:
        from core import quests
        quests.set_sink(lambda payload: broadcast({"type": "quest", "payload": payload}))
        print("[AURA bridge] Quest sink attached")
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    try:
        from core import activity
        activity.set_sink(lambda payload: broadcast({"type": "activity", "payload": payload}))
        print("[AURA bridge] Activity sink attached")
    except Exception:  # noqa: BLE001
        traceback.print_exc()


def _init_director() -> None:
    global DIRECTOR
    if DIRECTOR is not None:
        return
    try:
        from core.conversation_director import ConversationDirector
        DIRECTOR = ConversationDirector(
            on_mode_changed=lambda m: broadcast({"type": "mode", "payload": {"mode": m}})
        )
        print("[AURA bridge] ConversationDirector ready")
    except Exception:  # noqa: BLE001
        traceback.print_exc()


# (startup now handled by the _lifespan context manager above)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "aura-bridge", "clients": str(len(CLIENTS))}


# ============================================================================
# REST API (sidebar views)
# ============================================================================
def _task_dict(row: Any) -> dict[str, Any]:
    # columns: id, title, priority, status, created_at, done_at, bucket,
    #          due, project, origin
    r = list(row)
    return {
        "id": r[0], "title": r[1], "priority": r[2],
        "status": r[3], "created_at": r[4],
        "done_at": r[5] if len(r) > 5 else None,
        "bucket": (r[6] if len(r) > 6 else "now") or "now",
        "due": r[7] if len(r) > 7 else None,
        "project": r[8] if len(r) > 8 else None,
        "origin": (r[9] if len(r) > 9 else "user") or "user",
    }


def _fact_dict(row: Any) -> dict[str, Any]:
    # user_facts columns: id, fact, category, created_at
    r = list(row)
    return {"id": r[0], "fact": r[1], "category": r[2] if len(r) > 2 else "general",
            "created_at": r[3] if len(r) > 3 else None}


@app.get("/api/tasks")
async def api_tasks() -> dict[str, Any]:
    from memory import store
    rows = store.get_tasks()
    return {"tasks": [_task_dict(r) for r in rows]}


@app.post("/api/tasks")
async def api_add_task(req: Request) -> dict[str, Any]:
    from memory import store
    body = await req.json()
    title = (body.get("title") or "").strip()
    if not title:
        return {"ok": False, "error": "title required"}
    tid = store.add_task(title, body.get("priority", "medium"),
                         body.get("bucket", "now"),
                         due=body.get("due"), project=body.get("project"),
                         origin=body.get("origin", "user"))
    try:
        from core import activity
        activity.emit(f"Task added: {title}", "task")
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "id": tid}


@app.post("/api/tasks/{task_id}/bucket")
async def api_task_bucket(task_id: int, req: Request) -> dict[str, Any]:
    """Move a task between Now and Later."""
    from memory import store
    body = await req.json()
    store.set_task_bucket(task_id, str(body.get("bucket", "now")))
    return {"ok": True}


@app.post("/api/tasks/{task_id}/promote")
async def api_promote_task(task_id: int, req: Request) -> dict[str, Any]:
    """Turn a task into a quest for today.

    Tasks are the backlog; quests are what you've committed to actually doing
    today with AURA watching. Promoting is the bridge between the two — the
    task is marked done because it has become the quest.
    """
    from core import quests
    from memory import store
    body = await req.json() if await req.body() else {}
    row = next((t for t in store.get_tasks() if t[0] == task_id), None)
    if row is None:
        return {"ok": False, "error": "no such task"}

    # The task title is already an explicit, deliberate name — use it VERBATIM.
    # Running it through parse_quest would strip filler words and turn
    # "Finish the quest matcher" into "Finish Matcher". The parser is for
    # free-typed input; here we only borrow its preset guess.
    from core.quest_presets import PRESETS, guess_preset
    title = row[1].strip()
    minutes = max(0, int(body.get("target_minutes") or 0))
    preset = guess_preset(title)
    qid = store.add_quest(
        title, minutes, "", preset,
        PRESETS.get(preset, PRESETS["custom"])["color"],
    )
    store.complete_task(task_id)
    return {"ok": True, "quest_id": qid, "title": title,
            "target_minutes": minutes}


@app.post("/api/tasks/{task_id}/complete")
async def api_complete_task(task_id: int) -> dict[str, Any]:
    from memory import store
    store.complete_task(task_id)
    return {"ok": True}


@app.post("/api/tasks/{task_id}/uncomplete")
async def api_uncomplete_task(task_id: int) -> dict[str, Any]:
    from memory import store
    store.uncomplete_task(task_id)
    return {"ok": True}


@app.delete("/api/tasks/{task_id}")
async def api_delete_task(task_id: int) -> dict[str, Any]:
    from memory import store
    store.delete_task(task_id)
    return {"ok": True}


# The models shown in the constellation + their live lock state.
_MODELS = [
    # Live roster — names match core/model_router.MODELS = the model_lock
    # keys, so locking these actually removes them from routing.
    {"id": "laguna", "name": "Laguna M.1"},
    {"id": "nemotron", "name": "Nemotron 3 Super"},
    {"id": "gemma", "name": "Gemma 4 31B"},
    {"id": "llama", "name": "Llama 3.3 70B"},
    {"id": "llama8b", "name": "Llama 3.1 8B"},
    # Display-only constellation planets (not currently routed).
    {"id": "gpt4o", "name": "GPT-4o"},
    {"id": "gemini", "name": "Gemini 1.5 Pro"},
    {"id": "claude", "name": "Claude 3.5"},
    {"id": "grok", "name": "Grok 2 (xAI)"},
]


@app.get("/api/models")
async def api_models() -> dict[str, Any]:
    from core import model_lock
    out = []
    for m in _MODELS:
        try:
            locked = model_lock.is_locked(m["name"])
        except Exception:  # noqa: BLE001
            locked = False
        out.append({**m, "locked": bool(locked)})
    last = ""
    try:
        from core.ai_router import last_model_used
        last = last_model_used()
    except Exception:  # noqa: BLE001
        pass
    return {"models": out, "last_model": last}


@app.post("/api/models/{name}/toggle")
async def api_toggle_lock(name: str) -> dict[str, Any]:
    from core import model_lock
    # accept either node id or display name
    disp = next((m["name"] for m in _MODELS if m["id"] == name or m["name"] == name), name)
    locked = model_lock.toggle(disp)
    return {"ok": True, "name": disp, "locked": bool(locked)}


@app.get("/api/facts")
async def api_facts() -> dict[str, Any]:
    from memory import store
    rows = store.get_user_facts_full(300)
    return {"facts": [_fact_dict(r) for r in rows]}


@app.post("/api/facts")
async def api_add_fact(req: Request) -> dict[str, Any]:
    from memory import store
    body = await req.json()
    fact = (body.get("fact") or "").strip()
    if not fact:
        return {"ok": False, "error": "fact required"}
    store.save_user_fact(fact, body.get("category", "general"))
    return {"ok": True}


@app.put("/api/facts/{fact_id}")
async def api_update_fact(fact_id: int, req: Request) -> dict[str, Any]:
    from memory import store
    body = await req.json()
    store.update_user_fact(fact_id, (body.get("fact") or "").strip())
    return {"ok": True}


@app.delete("/api/facts/{fact_id}")
async def api_delete_fact(fact_id: int) -> dict[str, Any]:
    from memory import store
    store.delete_user_fact(fact_id)
    return {"ok": True}


# ── Saved notes + session recaps: the other two thirds of the Memory panel ───
# The store has had these readers since the Qt panel; only the HTTP surface was
# missing, so the React Memory view could show facts but nothing else AURA
# remembers. Read + delete only on purpose: notes and recaps are WRITTEN by the
# brain (knowledge extraction, session snapshots), never typed in by hand.
def _note_dict(r) -> dict[str, Any]:
    return {"id": r[0], "title": r[1], "summary": r[2], "created_at": r[3]}


def _recap_dict(r) -> dict[str, Any]:
    return {"id": r[0], "app": r[1], "summary": r[2], "created_at": r[3]}


@app.get("/api/notes")
async def api_notes(limit: int = 300) -> dict[str, Any]:
    from memory import store
    return {"notes": [_note_dict(r) for r in store.get_all_knowledge(limit)]}


@app.delete("/api/notes/{note_id}")
async def api_delete_note(note_id: int) -> dict[str, Any]:
    from memory import store
    store.delete_knowledge(note_id)
    return {"ok": True}


@app.get("/api/recaps")
async def api_recaps(limit: int = 60) -> dict[str, Any]:
    from memory import store
    return {"recaps": [_recap_dict(r) for r in store.get_all_snapshots(limit)]}


@app.delete("/api/recaps/{recap_id}")
async def api_delete_recap(recap_id: int) -> dict[str, Any]:
    from memory import store
    store.delete_snapshot(recap_id)
    return {"ok": True}


# ── Saved links: the Sanctuary link vault ───────────────────────────────────
def _link_dict(r) -> dict[str, Any]:
    return {"id": r[0], "name": r[1], "url": r[2], "created_at": r[3]}


@app.get("/api/links")
async def api_links() -> dict[str, Any]:
    from memory import store
    return {"links": [_link_dict(r) for r in store.get_links()]}


@app.post("/api/links")
async def api_add_link(req: Request) -> dict[str, Any]:
    from memory import store
    body = await req.json()
    url = (body.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "url required"}
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    name = (body.get("name") or "").strip()
    if not name:
        # default name = the domain, cleaned up
        from urllib.parse import urlparse
        name = (urlparse(url).netloc or url).removeprefix("www.")
    lid = store.add_link(name, url)
    return {"ok": True, "id": lid, "name": name, "url": url}


@app.put("/api/links/{link_id}")
async def api_update_link(link_id: int, req: Request) -> dict[str, Any]:
    from memory import store
    body = await req.json()
    store.update_link(link_id, body.get("name"), body.get("url"))
    return {"ok": True}


@app.delete("/api/links/{link_id}")
async def api_delete_link(link_id: int) -> dict[str, Any]:
    from memory import store
    store.delete_link(link_id)
    return {"ok": True}


# ── Task edit (title/priority in place) ─────────────────────────────────────
@app.put("/api/tasks/{task_id}")
async def api_update_task(task_id: int, req: Request) -> dict[str, Any]:
    from memory import store
    body = await req.json()
    store.update_task(task_id, body.get("title"), body.get("priority"),
                      due=body.get("due"), project=body.get("project"))
    return {"ok": True}


# ── AI Task Assistant: conversation → clean, estimated tasks ────────────────
# Both routes are READ-ONLY suggestions. Nothing is stored until the user
# accepts a suggestion, which comes back through the normal POST /api/tasks.
@app.post("/api/tasks/extract")
async def api_extract_tasks(req: Request) -> dict[str, Any]:
    from core import task_assistant
    body = await req.json()
    text = str(body.get("text") or "")
    # No text supplied → read the recent conversation out of memory, which is
    # what "turn what we just discussed into tasks" actually means.
    if not text.strip():
        try:
            from memory import store
            # rows: (role, message, created_at), oldest → newest
            rows = store.get_recent_conversations(int(body.get("limit", 40)))
            text = "\n".join(f"{r[0]}: {r[1]}" for r in rows if len(r) > 1)
        except Exception:  # noqa: BLE001
            text = ""
    return task_assistant.extract(text, use_llm=bool(body.get("use_llm", True)))


@app.post("/api/tasks/rewrite")
async def api_rewrite_task(req: Request) -> dict[str, Any]:
    from core import task_assistant
    body = await req.json()
    return task_assistant.rewrite(str(body.get("title") or ""),
                                  use_llm=bool(body.get("use_llm", True)))


# ── Usage stats: memory graph data ──────────────────────────────────────────
@app.get("/api/stats")
async def api_stats() -> dict[str, Any]:
    from memory import store
    return store.get_usage_stats(7)


# ── App settings: blackhole / planets / voice / auto-chat ───────────────────
@app.get("/api/settings")
async def api_settings() -> dict[str, Any]:
    from memory import store
    return {"settings": store.get_settings()}


@app.put("/api/settings")
async def api_save_settings(req: Request) -> dict[str, Any]:
    from memory import store
    body = await req.json()
    patch = body.get("settings") or body
    if not isinstance(patch, dict):
        return {"ok": False, "error": "settings object required"}
    store.set_settings(patch)
    return {"ok": True, "settings": store.get_settings()}


# ── Voice: speech-to-text fallback for the browser ──────────────────────────
# The React mic prefers the browser's own Web Speech API. When that's missing
# or its network path dies, the frontend encodes the utterance as a 16 kHz mono
# WAV and posts it here instead. WAV (not webm) on purpose: speech_recognition
# reads it natively, so this needs no ffmpeg/pydub on the machine.
@app.post("/api/voice/transcribe")
async def api_transcribe(req: Request) -> dict[str, Any]:
    import base64
    import io

    body = await req.json()
    raw = body.get("audio") or ""
    if not raw:
        return {"ok": False, "text": "", "error": "no audio"}

    # Tolerate a data: URL prefix in case a caller sends one.
    if "," in raw[:64] and raw.lstrip().startswith("data:"):
        raw = raw.split(",", 1)[1]

    try:
        wav = base64.b64decode(raw)
    except Exception:
        return {"ok": False, "text": "", "error": "audio is not valid base64"}

    def _run() -> dict[str, Any]:
        try:
            import speech_recognition as sr
        except Exception:
            return {"ok": False, "text": "", "error": "speech_recognition not installed"}
        recognizer = sr.Recognizer()
        try:
            with sr.AudioFile(io.BytesIO(wav)) as source:
                audio = recognizer.record(source)
        except Exception as e:
            return {"ok": False, "text": "", "error": f"unreadable audio: {e}"}
        try:
            return {"ok": True, "text": recognizer.recognize_google(audio), "error": ""}
        except sr.UnknownValueError:
            # Silence or nothing intelligible — not an error, just no words.
            return {"ok": True, "text": "", "error": ""}
        except sr.RequestError as e:
            return {"ok": False, "text": "", "error": f"speech service unavailable: {e}"}

    # recognize_google is a blocking network call — keep it off the event loop
    # or it stalls the WebSocket that's streaming AURA's reply.
    return await asyncio.to_thread(_run)


# ── Nature: AURA's locked personality (auto / chill / focus / savage / …) ────
@app.get("/api/nature")
async def api_get_nature() -> dict[str, Any]:
    from core.nature import NATURES, get_nature
    return {
        "current": get_nature(),
        "natures": [
            {"id": k, "label": v["label"], "icon": v["icon"]}
            for k, v in NATURES.items()
        ],
    }


@app.put("/api/nature")
async def api_set_nature(req: Request) -> dict[str, Any]:
    from core.nature import get_nature, set_nature
    body = await req.json()
    ok = set_nature(str(body.get("nature", "")))
    return {"ok": ok, "current": get_nature()}


# ============================================================================
# Quests — daily commitments AURA verifies from the screen
# ============================================================================
@app.get("/api/quests")
async def api_quests() -> dict[str, Any]:
    """Today's board: progress, completion, pressure, unallocated time."""
    from core import quests
    return quests.board()


@app.post("/api/quests")
async def api_add_quest(req: Request) -> dict[str, Any]:
    """Create a quest. Accepts either structured fields or plain language
    ("japanese 2 hrs"), because that's how shaurya actually phrases them."""
    from core import quests
    from core.quest_presets import PRESETS
    from memory import store
    body = await req.json()

    text = (body.get("text") or "").strip()
    if text and not body.get("title"):
        return {"ok": True, "quest": quests.create_from_text(text)}

    title = (body.get("title") or "").strip()
    if not title:
        return {"ok": False, "error": "title required"}
    preset = body.get("preset") or "custom"
    qid = store.add_quest(
        title,
        # 0 / omitted = not time-tracked.
        int(body.get("target_minutes") or 0),
        (body.get("keywords") or "").strip(),
        preset,
        body.get("color") or PRESETS.get(preset, PRESETS["custom"])["color"],
        (body.get("project_path") or "").strip(),
        kind=(body.get("kind") or "").strip(),
        target_count=int(body.get("target_count") or 0),
    )
    return {"ok": True, "id": qid}


@app.post("/api/quests/{quest_id}/verify")
async def api_verify_quest(quest_id: int, req: Request) -> dict[str, Any]:
    """Verify a proof quest from a screenshot.

    With no body, AURA captures the screen herself. An `image` field (base64
    JPEG/PNG, no data: prefix) is used instead when the UI supplies one.
    """
    from core.quest_verify import verify_quest
    body = {}
    try:
        if await req.body():
            body = await req.json()
    except Exception:  # noqa: BLE001
        body = {}
    result = verify_quest(quest_id, image_b64=body.get("image") or None)
    # Tell the UI live, so the card updates even if the panel isn't focused.
    try:
        from core import quests as _q
        _q._publish({"kind": "verify", "quest_id": quest_id, **result})
    except Exception:  # noqa: BLE001
        pass
    return result


@app.get("/api/quests/{quest_id}/terms")
async def api_quest_terms(quest_id: int) -> dict[str, Any]:
    """Exactly what AURA watches for on this quest.

    The honest diagnostic: when a quest isn't filling up, this shows whether
    the problem is a missing keyword or something else, instead of leaving the
    matcher a black box.
    """
    from core import quests
    from memory import store
    q = next((x for x in store.get_quest_board()["quests"] if x["id"] == quest_id), None)
    if q is None:
        return {"ok": False, "error": "no such quest"}
    terms, anchors = quests.quest_terms(q)
    return {
        "ok": True,
        "anchors": sorted(anchors),
        "supporting": sorted(set(terms) - anchors),
        "project_path": q.get("project_path", ""),
        "harvested": quests.project_terms(q.get("project_path", "")),
    }


@app.put("/api/quests/{quest_id}")
async def api_update_quest(quest_id: int, req: Request) -> dict[str, Any]:
    from memory import store
    body = await req.json()
    store.update_quest(quest_id, **body)
    return {"ok": True}


@app.delete("/api/quests/{quest_id}")
async def api_delete_quest(quest_id: int) -> dict[str, Any]:
    from memory import store
    store.delete_quest(quest_id)
    return {"ok": True}


@app.post("/api/quests/{quest_id}/complete")
async def api_complete_quest(quest_id: int, req: Request) -> dict[str, Any]:
    """Manual override — for the days the watcher couldn't see the work
    (a textbook, a whiteboard, time away from the machine)."""
    from memory import store
    body = await req.json() if await req.body() else {}
    store.complete_quest(quest_id, undo=bool(body.get("undo", False)))
    return {"ok": True}


@app.post("/api/quests/{quest_id}/adjust")
async def api_adjust_quest(quest_id: int, req: Request) -> dict[str, Any]:
    """Add or remove minutes by hand, same reason as manual completion."""
    from memory import store
    body = await req.json()
    store.add_quest_seconds(quest_id, int(body.get("minutes", 0)) * 60)
    return {"ok": True, "seconds": store.get_quest_seconds(quest_id)}


@app.get("/api/quests/history")
async def api_quest_history(days: int = 30) -> dict[str, Any]:
    from memory import store
    rows = store.get_quest_history(days)
    streaks = {
        q[0]: store.get_quest_streak(q[0], q[2]) for q in store.get_quests()
    }
    return {"history": rows, "streaks": streaks}


@app.get("/api/quests/presets")
async def api_quest_presets() -> dict[str, Any]:
    from core.quest_presets import preset_list
    return {"presets": preset_list()}


# ============================================================================
# V3 intelligence — error knowledge base + developer session state
# ============================================================================
# Both engines live in modules/ and know nothing about HTTP; core/v3_bridge
# owns the glue. These routes are thin on purpose.
@app.get("/api/v3/snapshot")
async def api_v3_snapshot() -> dict[str, Any]:
    """Everything the Intelligence panel needs in one round-trip."""
    from core import v3_bridge
    return v3_bridge.snapshot()


@app.get("/api/v3/session")
async def api_v3_session() -> dict[str, Any]:
    from core import v3_bridge
    return {"session": v3_bridge.session()}


@app.get("/api/v3/mistakes")
async def api_v3_mistakes() -> dict[str, Any]:
    from core import v3_bridge
    return {"mistakes": v3_bridge.mistakes_today(), "trends": v3_bridge.trends()}


@app.post("/api/v3/explain")
async def api_v3_explain(req: Request) -> dict[str, Any]:
    """Classify an arbitrary error blob.

    `record` defaults to False so the Domain code panel can preview a
    classification without inflating today's mistake count.
    """
    from core import v3_bridge
    body = await req.json()
    return v3_bridge.explain_error(
        str(body.get("text", "")),
        language=body.get("language"),
        record=bool(body.get("record", False)),
    )


@app.post("/api/v3/build")
async def api_v3_build(req: Request) -> dict[str, Any]:
    """Report a build/test result — the Domain terminal calls this so runs
    outside the screen watcher still feed momentum and confidence."""
    from core import v3_bridge
    body = await req.json()
    line = v3_bridge.report_build(bool(body.get("success", False)))
    return {"ok": True, "spoken": line, "session": v3_bridge.session()}


@app.get("/api/status")
async def api_status() -> dict[str, Any]:
    out: dict[str, Any] = {"mode": getattr(DIRECTOR, "mode", "CHAT")}
    try:
        from core.ai_router import last_model_used, openrouter_status
        out["openrouter"] = openrouter_status()
        out["last_model"] = last_model_used()
    except Exception:  # noqa: BLE001
        pass
    return out


# ============================================================================
# Chat over WebSocket (Director-routed)
# ============================================================================
def _send(ws: WebSocket, msg: dict[str, Any]):
    return ws.send_text(json.dumps(msg))


async def _run_streaming(ws: WebSocket, brain_call: Callable[..., str]) -> None:
    """Run a blocking brain call in a thread, streaming its on_chunk output.

    brain_call receives (on_chunk, on_code). Code blocks arrive via on_code
    (the brain strips them out of the chat text), so they are re-emitted as
    fenced chunks AND appended to the final "done" text — otherwise the web
    UI would show "Here's the code:" with no code at all."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    code_blocks: list[str] = []

    def on_chunk(chunk: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, chunk)

    def on_code(lang: str, code: str) -> None:
        block = f"\n\n```{lang or 'text'}\n{code}\n```"
        code_blocks.append(block)
        on_chunk(block)

    def run() -> str:
        try:
            return brain_call(on_chunk, on_code)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)

    await _send(ws, {"type": "state", "payload": {"state": "thinking"}})
    worker = loop.run_in_executor(None, run)

    first = False
    while True:
        item = await queue.get()
        if item is _DONE:
            break
        if not first:
            await _send(ws, {"type": "state", "payload": {"state": "speaking"}})
            first = True
        await _send(ws, {"type": "chunk", "payload": {"text": item}})

    try:
        full = await worker
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        await _send(ws, {"type": "error", "payload": {"message": str(exc)}})
        await _send(ws, {"type": "state", "payload": {"state": "idle"}})
        return

    model = ""
    try:
        from core.ai_router import last_model_used
        model = last_model_used()
    except Exception:  # noqa: BLE001
        pass

    done_text = (full or "") + "".join(code_blocks)
    await _send(ws, {"type": "done", "payload": {"text": done_text, "model": model}})
    await _send(ws, {"type": "state", "payload": {"state": "idle"}})


# How AURA read each message → what lane she picked and why. Terminal only.
_REASON_LABEL = {
    "reply":          ("💬 INSTANT REPLY", "answered locally — no model call"),
    "chat":           ("🗣  CHAT",          "conversation"),
    "plan":           ("🛠  PLAN → BUILD",  "compiled a task plan, executing it"),
    "generate":       ("⌨  CODE",          "explicit code request → generating"),
    "execute_prompt": ("⌨  CODE",          "running the built prompt as a coding task"),
    "llm_once":       ("✍  PROMPT BUILD",  "one clean LLM call from /prompt"),
}
# how the intent tag maps to a human-readable "what she thought"
_INTENT_THOUGHT = {
    "PERSONAL":   "just talking — companion lane, no work pushed",
    "CODING":     "this is a coding task",
    "RESEARCH":   "wants a researched, structured report",
    "DISCUSSION": "wants me to pressure-test the idea",
    "PLAN":       "wants a step-by-step roadmap",
    "EXPLAIN":    "wants it explained, not coded",
    "SEARCH":     "wants information",
    "CASUAL":     "small talk",
}


def _log_reasoning(text: str, directive, kind: str) -> None:
    """Print how AURA interpreted the message: her current mode, the lane she
    chose (research / code / discussion / plan / chat), and the intent behind
    it. Backend visibility only — the user never sees this."""
    try:
        mode = getattr(DIRECTOR, "mode", "NORMAL")
        intent = getattr(directive, "intent", "") or ""
        label, why = _REASON_LABEL.get(kind, ("🗣  CHAT", "conversation"))
        thought = _INTENT_THOUGHT.get(intent, "")
        print("\n┌─ AURA reasoning ──────────────────────────────")
        print(f"│  heard : {text[:70]}")
        print(f"│  mode  : {mode}")
        print(f"│  lane  : {label}   ({why})")
        if intent:
            print(f"│  intent: {intent}" + (f"  — {thought}" if thought else ""))
        if kind == "reply":
            print(f"│  said  : {getattr(directive, 'text', '')[:70]}")
        print("└───────────────────────────────────────────────")
    except Exception:
        pass  # logging must never break dispatch


async def _dispatch(ws: WebSocket, text: str) -> None:
    """Route one user message through the Director, then act on the directive."""
    if DIRECTOR is None:
        # Fallback: raw brain if the Director failed to init.
        await _run_streaming(ws, lambda oc, occ: process_streaming(text, on_chunk=oc, on_code=occ))
        return

    try:
        directive = DIRECTOR.handle(text)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        await _send(ws, {"type": "error", "payload": {"message": str(exc)}})
        return

    kind = getattr(directive, "kind", "chat")
    _log_reasoning(text, directive, kind)

    if kind == "reply":
        # Instant local answer (mode ack, /help, options menu) - no LLM.
        await _send(ws, {"type": "push", "payload": {"text": directive.text, "source": "reply"}})
        await _send(ws, {"type": "state", "payload": {"state": "idle"}})
        return

    if kind == "llm_once":
        await _run_streaming(
            ws,
            lambda oc, occ: process_streaming(
                directive.user, on_chunk=oc, on_code=occ, system_prompt=directive.system),
        )
        return

    if kind in ("execute_prompt", "generate"):
        await _run_streaming(
            ws,
            lambda oc, occ: process_streaming(
                directive.text, on_chunk=oc, on_code=occ, intent_hint="CODING"),
        )
        return

    if kind == "plan":
        # Compile the plan via the prompt engine, then EXECUTE it. The plan
        # internals (intent analysis, execution steps, requirements) are
        # backend detail — they go to the terminal only. The user gets the
        # actual answer, never the compiled prompt.
        _PLAN_INTENT = {"CODING": "CODING", "RESEARCH": "RESEARCH", "PLANNING": "PLAN"}

        def run_plan(oc: Callable[[str], None], occ: Callable[[str, str], None]) -> str:
            try:
                from core.prompt_engine import PromptEngine
                res = PromptEngine().process(directive.text)
            except Exception as e:  # noqa: BLE001
                out = f"That planner path hit a snag ({e}) — try rephrasing it."
                oc(out)
                return out
            # Terminal-only visibility of what the engine decided.
            print("[AURA bridge] ── Execution plan (terminal only) ──")
            for k, v in res.summary_dict().items():
                print(f"    {k}: {v}")
            print("[AURA bridge] ─────────────────────────────────────")
            intent = _PLAN_INTENT.get(res.plan.domain, "PLAN")
            return process_streaming(
                res.prompt, on_chunk=oc, on_code=occ,
                system_prompt=res.system_prompt, model=res.model_id,
                intent_hint=intent,
            )
        await _run_streaming(ws, run_plan)
        return

    # "chat" - normal streaming conversation
    intent = getattr(directive, "intent", "") or None
    body = getattr(directive, "text", "") or text
    await _run_streaming(ws, lambda oc, occ: process_streaming(body, on_chunk=oc, on_code=occ, intent_hint=intent))


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    CLIENTS.add(ws)
    await _send(ws, {"type": "state", "payload": {"state": "idle"}})
    await _send(ws, {"type": "mode", "payload": {"mode": getattr(DIRECTOR, "mode", "CHAT")}})

    # No greeting-on-connect: the proactive loop already checks in after idle,
    # so a connect greeting was redundant (and doubled on reconnect).

    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await _send(ws, {"type": "error", "payload": {"message": "invalid JSON"}})
                continue

            mtype = data.get("type")
            if mtype == "ping":
                await _send(ws, {"type": "pong"})
            elif mtype == "message":
                text = (data.get("payload") or {}).get("text", "").strip()
                if not text:
                    await _send(ws, {"type": "error", "payload": {"message": "empty message"}})
                else:
                    await _dispatch(ws, text)
            else:
                await _send(ws, {"type": "error", "payload": {"message": f"unknown type: {mtype}"}})
    except WebSocketDisconnect:
        print("[AURA bridge] client disconnected")
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    finally:
        CLIENTS.discard(ws)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="127.0.0.1", port=8760, reload=False)
