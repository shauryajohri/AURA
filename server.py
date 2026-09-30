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
import re
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

# Upgrades, reset and connected sources. Same reasoning as above: if AURA's
# self-editing machinery fails to import, AURA itself must still start — that
# is exactly the moment you need it running to roll the last upgrade back.
try:
    from system_api import router as system_router
    app.include_router(system_router)
    print("[AURA bridge] System API mounted (upgrades, reset, sources)")
except Exception:  # noqa: BLE001
    traceback.print_exc()

# Public web surface (/web/api/*) — the sandboxed demo behind the landing
# page. Deliberately separate from /ws: it never touches the personal store,
# has no tools, and is budgeted. The static site itself is mounted at the very
# BOTTOM of this file, because a mount at "/" swallows anything registered
# after it.
try:
    from web_api import mount_site as _mount_site, router as _web_router
    app.include_router(_web_router)
    print("[AURA bridge] Web demo API mounted at /web/api")
except Exception:  # noqa: BLE001
    _mount_site = None
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

    # Initialising the audio mixer costs a few hundred ms on Windows, and
    # paying it on the first spoken word made AURA's opening line land well
    # after its text had already appeared. Pay it up front instead.
    try:
        from modules import voice_output
        voice_output.prewarm()
    except Exception as e:  # noqa: BLE001
        print(f"[AURA bridge] audio prewarm skipped: {e}")

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
    try:
        from core import integrations, saved_info
        saved_info.set_sink(lambda payload: broadcast({"type": "saved", "payload": payload}))
        integrations.set_sink(lambda payload: broadcast({"type": "planets", "payload": payload}))
        print("[AURA bridge] Saved Info + planet install sinks attached")
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    try:
        from core import sources
        sources.set_sink(broadcast)      # already shaped as a {type, payload} frame
        sources.init()
        # Everything the user connected is brought up to date now, in the
        # background: opening AURA is the moment its picture of your work
        # should stop being yesterday's.
        sources.sync_all()
        print("[AURA bridge] Sources sink attached, launch sync started")
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


# The planets shown in the constellation + their live lock state. Every entry
# is a real, free model from core/model_router.MODELS — names are the
# model_lock keys, so locking one removes it from routing. Node ids match the
# frontend's data/models.ts; the old ids are kept so saved orbit slots and
# domain cards still resolve.
_MODELS = [
    {"id": "north", "name": "North Mini Code"},
    {"id": "laguna", "name": "Laguna XS 2.1"},
    {"id": "qwen", "name": "Qwen3.8 27B"},
    {"id": "nemotron", "name": "Nemotron 3 Super"},
    {"id": "dots", "name": "Dots 3 Note"},
    {"id": "gemma", "name": "Gemma 4 31B"},
    {"id": "nex", "name": "Nex N2.5 Pro"},
    {"id": "omni", "name": "Nemotron Nano Omni"},
    {"id": "ling", "name": "Ling 3.0 Flash VL"},
    {"id": "llama", "name": "GPT-OSS 120B"},
    {"id": "llama8b", "name": "GPT-OSS 20B"},
]


@app.get("/api/models")
async def api_models() -> dict[str, Any]:
    from core import model_lock, model_router
    groq_ids, last = set(), ""
    try:
        from core.ai_router import GROQ_MODEL_IDS, last_model_used
        groq_ids, last = GROQ_MODEL_IDS, last_model_used()
    except Exception:  # noqa: BLE001
        pass
    out = []
    for m in _MODELS:
        try:
            locked = model_lock.is_locked(m["name"])
        except Exception:  # noqa: BLE001
            locked = False
        model_id = model_router.MODELS.get(m["name"], "")
        out.append({
            **m,
            "locked": bool(locked),
            "model_id": model_id,
            "provider": "Groq" if model_id in groq_ids else "OpenRouter",
            "jobs": model_router.jobs_for(m["name"]),
        })
    # Planets installed from a pasted key or link (core/integrations).
    try:
        from core import integrations
        for m in integrations.installed_models():
            out.append({
                "id": m["planet_id"], "name": m["name"],
                "locked": bool(model_lock.is_locked(m["name"])),
                "model_id": m["wire"], "provider": m["label"],
                "jobs": model_router.jobs_for(m["name"]), "installed": True,
                "color": m["color"],
            })
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    if last.startswith("ext:"):
        last = model_router.name_for_id(last) or last
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


# ── Saved Info: links, PDFs and files AURA read for you (core/saved_info) ────
# Items are created by sharing in chat or from the page itself; scans run on
# worker threads and announce themselves as {"type": "saved"} websocket frames.
@app.get("/api/saved")
async def api_saved(kind: str = "") -> dict[str, Any]:
    from core import saved_info
    return {"items": saved_info.list_items(kind or None)}


@app.get("/api/saved/{item_id}")
async def api_saved_item(item_id: int) -> dict[str, Any]:
    from core import saved_info
    item = saved_info.get_item(item_id, with_content=True)
    return {"ok": bool(item), "item": item}


@app.post("/api/saved")
async def api_saved_add(req: Request) -> dict[str, Any]:
    """Save a link from the page. The scan runs in the background."""
    from core import saved_info
    body = await req.json()
    raw = str(body.get("url") or "").strip()
    urls = saved_info.extract_urls(raw if "://" in raw or raw.startswith("www.") else "https://" + raw)
    if not urls:
        return {"ok": False, "error": "that isn't a public web link"}
    item = saved_info.save_link(urls[0], origin="page")
    saved_info.scan_async(item["id"])
    return {"ok": True, "item": item}


@app.post("/api/saved/upload")
async def api_saved_upload(req: Request) -> dict[str, Any]:
    """A file from the dock or the page, as base64 JSON (no multipart
    dependency). Returns at once with status 'scanning'."""
    import base64 as _b64
    from core import saved_info
    body = await req.json()
    name = str(body.get("name") or "file").strip()[:160]
    raw = str(body.get("data") or "")
    if "," in raw[:80] and raw.lstrip().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        data = _b64.b64decode(raw, validate=False)
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "the file didn't arrive intact"}
    if not data:
        return {"ok": False, "error": "that file is empty"}
    try:
        item = saved_info.save_upload(name, data, str(body.get("mime") or ""),
                                      origin=str(body.get("origin") or "upload"))
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    saved_info.scan_async(item["id"])
    return {"ok": True, "item": item}


@app.post("/api/saved/{item_id}/rescan")
async def api_saved_rescan(item_id: int) -> dict[str, Any]:
    from core import saved_info
    item = saved_info.rescan(item_id)
    if not item:
        return {"ok": False, "error": "no such item"}
    return {"ok": True, "item": item}


@app.patch("/api/saved/{item_id}")
async def api_saved_update(item_id: int, req: Request) -> dict[str, Any]:
    from core import saved_info
    body = await req.json()
    item = saved_info.update_item(item_id, title=body.get("title"), pinned=body.get("pinned"),
                                  tags=body.get("tags"))
    return {"ok": bool(item), "item": item}


@app.delete("/api/saved/{item_id}")
async def api_saved_delete(item_id: int) -> dict[str, Any]:
    from core import saved_info
    return {"ok": saved_info.delete_item(item_id)}


@app.post("/api/saved/{item_id}/opened")
async def api_saved_opened(item_id: int) -> dict[str, Any]:
    from core import saved_info
    saved_info.mark_opened(item_id)
    return {"ok": True}


@app.get("/api/saved/{item_id}/file")
async def api_saved_file(item_id: int):
    """The stored copy of an uploaded (or downloaded) file, shown inline so a
    PDF opens in the browser's viewer."""
    from fastapi.responses import FileResponse, JSONResponse
    from core import saved_info
    found = saved_info.file_for(item_id)
    if not found:
        return JSONResponse({"ok": False, "error": "no stored file"}, status_code=404)
    path, name, mime = found
    saved_info.mark_opened(item_id)
    return FileResponse(path, media_type=mime, filename=name, content_disposition_type="inline")


# ── Planet installs: keys and links pasted in chat (core/integrations) ──────
@app.get("/api/integrations")
async def api_integrations() -> dict[str, Any]:
    from core import integrations
    return {"integrations": integrations.list_integrations(), "planets": integrations.planets(),
            "jobs": integrations.JOBS}


@app.get("/api/planets")
async def api_planets() -> dict[str, Any]:
    from core import integrations
    return {"planets": integrations.planets()}


@app.post("/api/integrations/proposals/{uid}/identify")
async def api_integration_identify(uid: str, req: Request) -> dict[str, Any]:
    """The card's follow-up answers — which service, a key, a base URL. The
    key travels here, never through the chat."""
    from core import integrations
    body = await req.json()
    try:
        prop = await asyncio.to_thread(
            integrations.identify, uid, body.get("provider") or None,
            body.get("key"), body.get("base_url") or None)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    finally:
        # Clears the "Checking …" line on the core — no chat turn ends this.
        broadcast({"type": "state", "payload": {"state": "idle"}})
    return {"ok": True, "proposal": prop}


@app.post("/api/integrations/proposals/{uid}/confirm")
async def api_integration_confirm(uid: str, req: Request) -> dict[str, Any]:
    from core import integrations
    body = await req.json()
    try:
        result = await asyncio.to_thread(
            integrations.confirm, uid, body.get("models") or [],
            str(body.get("position") or "backup"), body.get("search_jobs"))
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    finally:
        broadcast({"type": "state", "payload": {"state": "idle"}})
    msg = result.get("message") or ""
    if msg:
        # The outcome belongs in the conversation too, spoken like any reply.
        try:
            from memory import store
            store.save_conversation("aura", msg)
        except Exception:  # noqa: BLE001
            pass
        broadcast_push(msg, "install")
        if _voice_is_on():
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, lambda: _speak_reply(msg))
    return result


@app.post("/api/integrations/proposals/{uid}/dismiss")
async def api_integration_dismiss(uid: str) -> dict[str, Any]:
    from core import integrations
    return {"ok": integrations.dismiss(uid)}


@app.get("/api/integrations/proposals/{uid}")
async def api_integration_proposal(uid: str) -> dict[str, Any]:
    from core import integrations
    prop = integrations.get_proposal(uid)
    return {"ok": bool(prop), "proposal": prop}


@app.delete("/api/integrations/{integration_id}")
async def api_integration_uninstall(integration_id: int) -> dict[str, Any]:
    from core import integrations
    return {"ok": integrations.uninstall(integration_id)}


@app.post("/api/integrations/{integration_id}/test")
async def api_integration_retest(integration_id: int) -> dict[str, Any]:
    from core import integrations
    return {"ok": True, "results": await asyncio.to_thread(integrations.retest, integration_id)}


@app.patch("/api/integrations/models/{row_id}")
async def api_integration_model_update(row_id: int, req: Request) -> dict[str, Any]:
    from core import integrations
    body = await req.json()
    try:
        integrations.update_model(row_id, jobs=body.get("jobs"), position=body.get("position"))
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "planets": integrations.planets()}


@app.delete("/api/integrations/models/{row_id}")
async def api_integration_model_delete(row_id: int) -> dict[str, Any]:
    from core import integrations
    return {"ok": integrations.remove_model(row_id)}


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



# ── Rooms: what a chat is ABOUT ─────────────────────────────────────────────
# A chat is a boundary; a room is a subject. Rooms hold chats, and every chat
# in a room inherits the room's brief — which is the part a title taken from
# the first message can never carry.
@app.get("/api/rooms")
async def api_rooms() -> dict[str, Any]:
    from memory import store
    active = store.active_room()
    return {"rooms": store.list_rooms(), "active": active["id"] if active else None}


@app.post("/api/rooms")
async def api_room_new(req: Request) -> dict[str, Any]:
    from memory import store
    body = await req.json()
    try:
        rid = store.create_room(
            name=str(body.get("name") or ""),
            icon=str(body.get("icon") or "◈"),
            accent=str(body.get("accent") or "#6C6BFF"),
            topic=str(body.get("topic") or ""),
            keywords=body.get("keywords") or "",
            system_hint=str(body.get("system_hint") or ""),
            auto_switch=bool(body.get("auto_switch", True)),
        )
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "id": rid, "rooms": store.list_rooms()}


@app.patch("/api/rooms/{room_id}")
async def api_room_update(room_id: int, req: Request) -> dict[str, Any]:
    from memory import store
    body = await req.json()
    store.update_room(room_id, **body)
    return {"ok": True, "rooms": store.list_rooms()}


@app.delete("/api/rooms/{room_id}")
async def api_room_delete(room_id: int) -> dict[str, Any]:
    """The room goes; its chats stay, unfiled. Deleting a folder must never
    delete the conversations inside it."""
    from memory import store
    store.delete_room(room_id)
    return {"ok": True, "rooms": store.list_rooms(), "chats": store.list_chat_sessions()}


@app.get("/api/rooms/{room_id}/chats")
async def api_room_chats(room_id: int) -> dict[str, Any]:
    from memory import store
    return {"chats": store.room_sessions(room_id)}


@app.post("/api/rooms/{room_id}/enter")
async def api_room_enter(room_id: int) -> dict[str, Any]:
    """Entering a room resumes its most recent chat, or starts one there."""
    from memory import store
    if not store.get_room(room_id):
        return {"ok": False, "error": "no such room"}
    sid = store.enter_room(room_id)
    try:
        from core import brain
        brain.reset_history()
    except Exception:  # noqa: BLE001
        pass
    rows = store.get_session_messages(sid)
    broadcast({"type": "room", "payload": {"room_id": room_id, "chat_id": sid, "auto": False, "note": ""}})
    return {"ok": True, "room_id": room_id, "active": sid,
            "messages": [{"role": r, "text": m, "created_at": t} for r, m, t in rows]}


@app.post("/api/chats/{chat_id}/room")
async def api_chat_set_room(chat_id: int, req: Request) -> dict[str, Any]:
    """File a chat into a room (or out of one with room_id: null)."""
    from memory import store
    body = await req.json()
    store.set_session_room(chat_id, body.get("room_id"))
    return {"ok": True, "rooms": store.list_rooms(), "chats": store.list_chat_sessions()}


# ── Chats: named conversation sessions ──────────────────────────────────────
# One endless message stream had no boundaries, so "recent conversation" meant
# "the last N rows" and turns from weeks ago could pass for the live chat.
# A chat is a boundary the user can see, name and switch between — and the
# ACTIVE chat is what scopes the context AURA is given.
@app.get("/api/chats")
async def api_chats() -> dict[str, Any]:
    from memory import store
    return {"chats": store.list_chat_sessions(), "active": store.active_session_id()}


@app.post("/api/chats")
async def api_chat_new(req: Request) -> dict[str, Any]:
    from memory import store
    try:
        body = await req.json()
    except Exception:  # noqa: BLE001 — an empty body is a perfectly good "new chat"
        body = {}
    sid = store.create_chat_session(str(body.get("title") or "") or None)
    return {"ok": True, "id": sid, "chats": store.list_chat_sessions()}


@app.post("/api/chats/clear")
async def api_chats_clear() -> dict[str, Any]:
    """Wipe all chat history — every message and every chat session. Rooms
    stay (empty). The next message opens a fresh chat. Settings → Privacy
    calls this; it always confirms first."""
    from memory import store
    removed = store.clear_all_chats()
    try:
        from core import brain
        brain.reset_history()
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "removed": removed,
            "chats": store.list_chat_sessions(),
            "active": store.active_session_id(),
            "rooms": store.list_rooms()}


@app.get("/api/chats/{chat_id}/messages")
async def api_chat_messages(chat_id: int) -> dict[str, Any]:
    from memory import store
    rows = store.get_session_messages(chat_id)
    return {"messages": [{"role": r, "text": m, "created_at": t} for r, m, t in rows]}


@app.post("/api/chats/{chat_id}/activate")
async def api_chat_activate(chat_id: int) -> dict[str, Any]:
    """Switch chats. This moves AURA's CONTEXT too — the next thing she reads
    is this chat's history, not the one that was open before."""
    from memory import store
    if not store.set_active_chat_session(chat_id):
        return {"ok": False, "error": "no such chat"}
    # The in-RAM mirror belongs to the chat we just left; clearing it stops it
    # bleeding into the reopened one.
    try:
        from core import brain
        brain.reset_history()
    except Exception:  # noqa: BLE001
        pass
    rows = store.get_session_messages(chat_id)
    return {"ok": True, "active": chat_id,
            "messages": [{"role": r, "text": m, "created_at": t} for r, m, t in rows]}


@app.patch("/api/chats/{chat_id}")
async def api_chat_rename(chat_id: int, req: Request) -> dict[str, Any]:
    from memory import store
    body = await req.json()
    title = str(body.get("title") or "")
    if not store.rename_chat_session(chat_id, title):
        return {"ok": False, "error": "title required"}
    return {"ok": True, "chats": store.list_chat_sessions()}


@app.delete("/api/chats/{chat_id}")
async def api_chat_delete(chat_id: int) -> dict[str, Any]:
    from memory import store
    store.delete_chat_session(chat_id)
    try:
        from core import brain
        brain.reset_history()
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "chats": store.list_chat_sessions(),
            "active": store.active_session_id()}


# ── Voice: which voice AURA speaks with ─────────────────────────────────────
# The roster lives in modules/voice_output so the picker, the CLI tool and the
# speaking code can never drift apart. edge-tts voices are server-side, so
# "installing" a voice is just storing its name.
@app.get("/api/voice/voices")
async def api_voices() -> dict[str, Any]:
    from modules import voice_output
    selected = ""
    try:
        selected = voice_output.resolve_voice("normal")
    except Exception:  # noqa: BLE001
        selected = voice_output.FALLBACK_VOICE
    return {
        "voices": voice_output.VOICES,
        "selected": selected,
        "preview_line": voice_output.PREVIEW_LINE,
    }


@app.post("/api/voice/preview")
async def api_voice_preview(req: Request):
    """Render a sample of one voice and hand the mp3 straight to the browser.

    Runs in a thread: edge-tts is a blocking network call, and doing it on the
    event loop would stall every websocket AURA is streaming through.
    """
    from fastapi.responses import JSONResponse, Response as _Response
    from modules import voice_output

    body = await req.json()
    voice = str(body.get("voice") or "").strip()
    text = body.get("text") or None
    if not voice:
        return JSONResponse({"ok": False, "error": "voice required"}, status_code=400)

    loop = asyncio.get_running_loop()
    try:
        audio = await loop.run_in_executor(
            None, lambda: voice_output.render_preview(voice, text))
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        return JSONResponse({"ok": False, "error": str(e)}, status_code=502)

    return _Response(content=audio, media_type="audio/mpeg",
                     headers={"Cache-Control": "no-store"})


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
        # Groq Whisper first (free tier: large-v3-turbo, then large-v3); None
        # means neither could run, so Google's keyless recognizer takes over.
        try:
            from core.ai_router import transcribe_whisper
            text = transcribe_whisper(wav)
        except Exception as e:  # noqa: BLE001
            print(f"[AURA stt] whisper skipped: {e}")
            text = None
        if text is not None:
            return {"ok": True, "text": text, "error": ""}
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


def _voice_is_on() -> bool:
    """Checked BEFORE announcing the speaking state, so a muted AURA doesn't
    flash 'speaking' and needlessly gate the mic."""
    try:
        from modules import voice_output
        return bool(voice_output._voice_settings().get("enabled", True))
    except Exception:  # noqa: BLE001
        return False


def _speak_reply(text: str) -> None:
    """Say a chat answer out loud. Runs on a worker thread.

    Until now NOTHING spoke the replies: only the proactive and attention
    loops ever called TTS, so AURA greeted you out loud and then answered
    your actual questions in silence. This is the missing half.
    """
    try:
        from core.brain import speak_response
        speak_response(text, mode="CHAT")
    except Exception as e:  # noqa: BLE001 — a mute reply beats a broken turn
        print(f"[AURA bridge] TTS skipped: {e}")


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

    # Say it. `full` only — never the code blocks, because reading a diff
    # aloud helps nobody. The state stays "speaking" for the duration so the
    # UI shows it and the mic stays muted while she talks (otherwise she
    # hears herself and answers her own sentence).
    spoken = (full or "").strip()
    if spoken and _voice_is_on():
        await _send(ws, {"type": "state", "payload": {"state": "speaking"}})
        try:
            await loop.run_in_executor(None, lambda: _speak_reply(spoken))
        except Exception:  # noqa: BLE001
            traceback.print_exc()

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


def _route_room(text: str) -> None:
    """Move the conversation to the right room before the turn is processed.

    Order matters: the room decides which brief the prompt carries, so a
    switch applied afterwards would answer in the new room using the old
    room's instructions. Failure here is never fatal — a router that cannot
    decide leaves you exactly where you were.
    """
    try:
        from core import room_router
        from memory import store

        d = room_router.route(text)
        if not d.get("switch"):
            return
        sid = store.enter_room(d["room_id"])
        try:
            from core import brain
            brain.reset_history()
        except Exception:  # noqa: BLE001
            pass
        broadcast({"type": "room", "payload": {
            "room_id": d["room_id"], "chat_id": sid,
            "from_room_id": d.get("from_room_id"),
            "auto": True, "note": d.get("note", ""),
        }})
    except Exception as e:  # noqa: BLE001
        print(f"[AURA bridge] room routing skipped: {e}")


async def _say(ws: WebSocket, text: str) -> None:
    """Speak a reply that didn't come through _run_streaming, holding the
    speaking state so the mic doesn't hear her."""
    if not text or not _voice_is_on():
        return
    loop = asyncio.get_running_loop()
    await _send(ws, {"type": "state", "payload": {"state": "speaking"}})
    try:
        await loop.run_in_executor(None, lambda: _speak_reply(text))
    except Exception:  # noqa: BLE001
        traceback.print_exc()


async def _maybe_install(ws: WebSocket, text: str) -> bool:
    """An API key, or "install <link>", becomes an install card.

    Runs before anything else sees the message: a key must never reach the
    Director, a model, the room router or the chat log in the clear. The log
    gets a masked copy; the key itself goes into the pending proposal only.
    """
    try:
        from core import integrations
        req = integrations.detect_request(text)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return False
    if not req:
        return False
    print(f"[AURA bridge] install request: {req['masked_text'][:80]}")
    await _send(ws, {"type": "state", "payload": {"state": "thinking"}})
    try:
        prop = await asyncio.to_thread(integrations.propose, req)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        prop = {"message": f"I couldn't set that up — {exc}", "stage": "error"}
    message = prop.pop("message", "") or "Here's what I found."
    try:
        from memory import store
        store.save_conversation("user", req["masked_text"])
        store.save_conversation("aura", message)
    except Exception:  # noqa: BLE001
        pass
    card = prop if prop.get("id") and prop.get("stage") != "not_installable" else None
    await _send(ws, {"type": "install", "payload": {"text": message, "proposal": card,
                                                    "masked": req["masked_text"]}})
    await _say(ws, message)
    await _send(ws, {"type": "state", "payload": {"state": "idle"}})
    return True


def _canned(user_text: str, reply: str, on_chunk: Callable[[str], None]) -> str:
    """A reply that needs no model — still logged and streamed like one."""
    try:
        from memory import store
        store.save_conversation("user", user_text)
        store.save_conversation("aura", reply)
    except Exception:  # noqa: BLE001
        pass
    on_chunk(reply)
    return reply


_CODE_ASK = re.compile(
    r"(?i)\b(code|function|class|bug|error|implement|refactor|debug|compile|script|"
    r"port it|rewrite|unit test|stack ?trace)\b")


async def _capture_shared(ws: WebSocket, text: str, attachments: list,
                          asked: bool = False) -> str | None:
    """Save + read any links in the message and pick up attached uploads.

    Returns None when nothing was shared, "done" when the message was only
    the shared thing (answered here, no model needed), or an intent for the
    model turn that should follow ("EXPLAIN" / "CODING").
    """
    from core import saved_info
    urls = saved_info.extract_urls(text)
    ids = []
    for a in attachments or []:
        try:
            ids.append(int(a))
        except (TypeError, ValueError):
            pass
    if not urls and not ids:
        return None
    await _send(ws, {"type": "state", "payload": {"state": "thinking"}})
    items = await asyncio.to_thread(saved_info.capture, urls, ids[:5], 25.0)
    if not items:
        return None
    names = [n for it in items for n in (it.get("file_name"), it.get("title")) if n]
    if not asked and saved_info.is_bare_share(text, urls, names):
        reply = saved_info.share_reply(items)
        await _run_streaming(ws, lambda oc, occ: _canned(text, reply, oc))
        return "done"
    saved_info.arm_turn([it["id"] for it in items])
    return "CODING" if _CODE_ASK.search(text) else "EXPLAIN"


async def _dispatch(ws: WebSocket, text: str, attachments: list | None = None,
                    intent: str | None = None) -> None:
    """Route one user message through the Director, then act on the directive."""
    # 1. Keys and "install this" — before anything else can see the message.
    if await _maybe_install(ws, text):
        return

    # 2. Links and files shared with the message land in Saved Info.
    shared_intent = None
    try:
        shared_intent = await _capture_shared(ws, text, attachments or [], asked=intent == "EXPLAIN")
    except Exception:  # noqa: BLE001 — a failed save must not cost the reply
        traceback.print_exc()
    if shared_intent == "done":
        return

    # "Ask AURA" on a Saved Info item, or a question about something just
    # shared: answer it straight from the material. Skipping the Director
    # matters — its vague-ask guard would meet "what's this about?" with a
    # clarifying question when the thing is sitting right there. A workspace
    # mode (/research, /code …) still wins, so its framing applies.
    in_mode = DIRECTOR is not None and getattr(DIRECTOR, "mode", "NORMAL") not in ("NORMAL", "CHAT")
    pinned = "EXPLAIN" if intent == "EXPLAIN" else shared_intent
    if pinned and not in_mode:
        _route_room(text)
        await _run_streaming(ws, lambda oc, occ: process_streaming(
            text, on_chunk=oc, on_code=occ, intent_hint=pinned))
        return

    _route_room(text)

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
                payload = data.get("payload") or {}
                text = str(payload.get("text", "")).strip()
                attachments = payload.get("attachments") or []
                if not isinstance(attachments, list):
                    attachments = []
                # Only "EXPLAIN" can be pinned from the client (Saved Info's
                # Ask AURA) — the rest of routing stays the brain's call.
                intent = "EXPLAIN" if payload.get("intent") == "EXPLAIN" else None
                if not text:
                    await _send(ws, {"type": "error", "payload": {"message": "empty message"}})
                else:
                    await _dispatch(ws, text, attachments, intent)
            else:
                await _send(ws, {"type": "error", "payload": {"message": f"unknown type: {mtype}"}})
    except WebSocketDisconnect:
        print("[AURA bridge] client disconnected")
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    finally:
        CLIENTS.discard(ws)


# ----------------------------------------------------------------------------
# Static landing page — LAST. StaticFiles mounted at "/" matches every path
# Starlette hasn't already matched, so anything registered after it is dead.
# ----------------------------------------------------------------------------
if _mount_site is not None:
    try:
        _mount_site(app)
    except Exception:  # noqa: BLE001
        traceback.print_exc()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="127.0.0.1", port=8760, reload=False)
