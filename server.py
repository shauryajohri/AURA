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
from typing import Any, Callable

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from core.brain import process_streaming

app = FastAPI(title="AURA Bridge")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

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


@app.on_event("startup")
async def _on_startup() -> None:
    global MAIN_LOOP
    MAIN_LOOP = asyncio.get_running_loop()
    _init_director()
    _start_auto_chat()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "aura-bridge", "clients": str(len(CLIENTS))}


# ============================================================================
# REST API (sidebar views)
# ============================================================================
def _task_dict(row: Any) -> dict[str, Any]:
    # tasks columns: id, title, priority, status, created_at, done_at
    r = list(row)
    return {
        "id": r[0], "title": r[1], "priority": r[2],
        "status": r[3], "created_at": r[4],
        "done_at": r[5] if len(r) > 5 else None,
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
    tid = store.add_task(title, body.get("priority", "medium"))
    return {"ok": True, "id": tid}


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
    {"id": "gpt4o", "name": "GPT-4o"},
    {"id": "gemini", "name": "Gemini 1.5 Pro"},
    {"id": "llama", "name": "Llama 3.3 70B"},
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


async def _run_streaming(ws: WebSocket, brain_call: Callable[[Callable[[str], None]], str]) -> None:
    """Run a blocking brain call in a thread, streaming its on_chunk output."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_chunk(chunk: str) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, chunk)

    def run() -> str:
        try:
            return brain_call(on_chunk)
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

    await _send(ws, {"type": "done", "payload": {"text": full or "", "model": model}})
    await _send(ws, {"type": "state", "payload": {"state": "idle"}})


async def _dispatch(ws: WebSocket, text: str) -> None:
    """Route one user message through the Director, then act on the directive."""
    if DIRECTOR is None:
        # Fallback: raw brain if the Director failed to init.
        await _run_streaming(ws, lambda oc: process_streaming(text, on_chunk=oc))
        return

    try:
        directive = DIRECTOR.handle(text)
    except Exception as exc:  # noqa: BLE001
        traceback.print_exc()
        await _send(ws, {"type": "error", "payload": {"message": str(exc)}})
        return

    kind = getattr(directive, "kind", "chat")

    if kind == "reply":
        # Instant local answer (mode ack, /help, options menu) - no LLM.
        await _send(ws, {"type": "push", "payload": {"text": directive.text, "source": "reply"}})
        await _send(ws, {"type": "state", "payload": {"state": "idle"}})
        return

    if kind == "llm_once":
        await _run_streaming(
            ws,
            lambda oc: process_streaming(directive.user, on_chunk=oc, system_prompt=directive.system),
        )
        return

    if kind in ("execute_prompt", "generate"):
        await _run_streaming(
            ws,
            lambda oc: process_streaming(directive.text, on_chunk=oc, intent_hint="CODING"),
        )
        return

    if kind == "plan":
        # Build a plan via the prompt engine and return it as a message.
        # (The interactive approve/run panel is a later milestone; for now the
        # plan text is delivered so nothing is silently dropped.)
        def build_plan(oc: Callable[[str], None]) -> str:
            try:
                from core.prompt_engine import PromptEngine
                res = PromptEngine().process(directive.text)
                out = getattr(res, "text", None) or getattr(res, "prompt", None) or str(res)
            except Exception as e:  # noqa: BLE001
                out = f"(planner unavailable: {e})"
            oc(out)
            return out
        await _run_streaming(ws, build_plan)
        return

    # "chat" - normal streaming conversation
    intent = getattr(directive, "intent", "") or None
    body = getattr(directive, "text", "") or text
    await _run_streaming(ws, lambda oc: process_streaming(body, on_chunk=oc, intent_hint=intent))


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
