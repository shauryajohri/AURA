"""
Room routing (server.py _route_room, core/room_router.py) against the REAL
server app and socket.

What must hold:
  * a message stays in the chat it was typed into: "+ New chat", then a
    message that clearly belongs to Coding, files THAT chat under Coding — it
    is not swapped for Coding's last chat and that chat's history
  * a chat the user opened (new, picked from the list, a room entered) is
    never left for another room
  * slash commands and /prompt buffer lines never route
  * a chat AURA chose can still be moved, and then the 'room' event carries
    the new chat's transcript from before this turn, so the UI can show it
  * every filing or move is announced to the UI with a note

Runs offline on a throwaway DB and vault; never starts the background loops.
The model is never called: the brain's entry point is replaced by a stand-in
that records which chat was active when the turn ran.

Run:  PYTHONPATH=. python3 tests/test_room_routing.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# throwaway DB + Buddy Lock vault before anything binds to the real ones
_TMP = tempfile.mkdtemp(prefix="aura_room_routing_")
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

import local_auth  # noqa: E402
import server  # noqa: E402
from core import brain  # noqa: E402

WS = "ws://127.0.0.1:8760/ws"
PROTOCOLS = ["aura", "aura-token." + local_auth.TOKEN]

# No `with`: the lifespan (proactive loops, token file in the real repo) stays off.
client = TestClient(server.app, base_url="http://127.0.0.1:8760",
                    headers={"X-Aura-Token": local_auth.TOKEN})
server._init_director()          # /prompt mode lives in the Director
server._voice_is_on = lambda: False

# Without the lifespan there is no loop to broadcast on; keep what was sent.
EVENTS: list[dict] = []
server.broadcast = lambda msg: EVENTS.append(msg)

# What the brain would have answered from: the active chat and its history.
SEEN: list[dict] = []


def fake_process_streaming(query, on_chunk=None, on_code=None, **_kw):
    sid = mstore.active_session_id()
    SEEN.append({"chat": sid, "room": (mstore.active_room() or {}).get("name"),
                 "history": [m for _, m, _ in mstore.get_session_messages(sid)]})
    if on_chunk:
        on_chunk("ok")
    mstore.save_conversation("user", query)
    mstore.save_conversation("aura", "ok")
    return "ok"


server.process_streaming = fake_process_streaming

_fails: list[str] = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'} — {label}")
    if not cond:
        _fails.append(label)


def say(ws, text) -> list[dict]:
    """Send one message; return its room events (what the UI was told)."""
    n = len(EVENTS)
    ws.send_json({"type": "message", "payload": {"text": text}})
    answered = False
    while True:
        f = ws.receive_json()
        if f.get("type") in ("done", "push", "error"):
            answered = True
        if answered and f.get("type") == "state" and f["payload"].get("state") == "idle":
            break
    return [e["payload"] for e in EVENTS[n:] if e.get("type") == "room"]


def active() -> int:
    return client.get("/api/chats").json()["active"]


def room_of(chat_id) -> str | None:
    return (mstore.session_room(chat_id) or {}).get("name")


def texts(chat_id) -> list[str]:
    return [m["text"] for m in client.get(f"/api/chats/{chat_id}/messages").json()["messages"]]


ROOMS = {r["name"]: r["id"] for r in client.get("/api/rooms").json()["rooms"]}

with client.websocket_connect(WS, subprotocols=PROTOCOLS) as ws:
    ws.receive_json()   # state
    ws.receive_json()   # mode

    # ── 1. an unfiled chat is filed, not swapped ───────────────────────────
    print("\n[1] first message in an unfiled chat")
    a = active()
    ev = say(ws, "my python script BLUEFIN keeps throwing a KeyError in the parser")
    check(active() == a, "the message stayed in the open chat")
    check(room_of(a) == "Coding", "…which is now filed under Coding")
    check(len(ev) == 1 and ev[0]["chat_id"] == a and ev[0].get("moved") is False and ev[0]["auto"],
          "UI told: same chat, not moved")
    check(len(ev) == 1 and "Coding" in ev[0]["note"] and "messages" not in ev[0],
          "…with a note naming the room, and no transcript to swap in")

    # ── 2. "+ New chat" keeps the next message (the reported bug) ──────────
    print("\n[2] + New chat, then a message that belongs in Coding")
    brain._history.append({"role": "user", "text": "BLUEFIN from the old chat"})
    b = client.post("/api/chats", json={}).json()["id"]
    check(b != a and active() == b, "a new chat is open")
    check(not brain._history, "opening it dropped the old chat's in-RAM turns")
    ev = say(ws, "how do I reverse a list in python?")
    check(active() == b, "still in the new chat after the message (was: back in the old one)")
    check(SEEN[-1]["chat"] == b and SEEN[-1]["history"] == [],
          "answered in the new chat, with none of the old chat's turns")
    check(texts(b)[:1] == ["how do I reverse a list in python?"], "the turn was saved in the new chat")
    check(len(texts(a)) == 2, "the old chat got nothing")
    check(room_of(b) == "Coding" and SEEN[-1]["room"] == "Coding",
          "the new chat was filed under Coding before the answer, so the brief applied")
    check(len(ev) == 1 and ev[0]["chat_id"] == b and ev[0].get("moved") is False,
          "UI told: filed, same chat")

    # ── 3. slash commands and /prompt buffer lines don't route ─────────────
    print("\n[3] slash commands and the /prompt buffer")
    c = client.post("/api/chats", json={}).json()["id"]
    check(say(ws, "/code") == [] and active() == c and room_of(c) is None,
          "'/code' moved nothing and filed nothing")
    say(ws, "/code_end")
    say(ws, "/prompt")
    check(getattr(server.DIRECTOR, "mode", "") == "PROMPT", "in /prompt mode")
    ev = say(ws, "write a python api with a database and docker deploy")
    check(ev == [] and active() == c and room_of(c) is None, "a buffered /prompt line moved nothing")
    say(ws, "/prompt clear")
    say(ws, "/prompt_end")

    # ── 4. a chat the user opened is never left ────────────────────────────
    print("\n[4] chats the user opened")
    p = client.post(f"/api/rooms/{ROOMS['Personal']}/enter").json()["active"]
    check(room_of(p) == "Personal", "entered Personal")
    ev = say(ws, "how do I fix this python error in my api endpoint?")
    check(ev == [] and active() == p and SEEN[-1]["chat"] == p,
          "a coding question in an entered room stays in its chat")
    check(room_of(p) == "Personal", "…and the chat keeps its room")
    client.post(f"/api/chats/{a}/activate")
    ev = say(ws, "I'm so tired after the gym, what food helps recovery?")
    check(ev == [] and active() == a and SEEN[-1]["chat"] == a,
          "a personal message in a chat picked from the list stays there")

    # ── 5. a chat AURA chose can move, visibly ─────────────────────────────
    print("\n[5] a chat the user didn't pick (e.g. the one open at startup)")
    server._PICKED_CHAT = None      # as after a restart
    before = client.get(f"/api/chats/{p}/messages").json()["messages"]
    ev = say(ws, "I'm so tired after the gym, what food helps recovery?")
    check(active() == p and SEEN[-1]["chat"] == p, "moved to Personal's chat")
    check(len(ev) == 1 and ev[0].get("moved") is True and ev[0]["chat_id"] == p
          and ev[0]["from_room_id"] == ROOMS["Coding"], "UI told: moved, from Coding")
    check(len(ev) == 1 and ev[0].get("messages") == before,
          "…with that chat's transcript from before this turn (no duplicate of the message)")
    check(len(ev) == 1 and "Personal" in ev[0]["note"], "…and a note naming the room")

    # ── 6. no signal, no event ─────────────────────────────────────────────
    print("\n[6] an ordinary message")
    d = client.post("/api/chats", json={}).json()["id"]
    check(say(ws, "what's a good name for a cat?") == [] and active() == d and room_of(d) is None,
          "no room, no move, no note")


print("\n" + ("ALL PASS ✅" if not _fails else f"FAILURES ({len(_fails)}): {_fails}"))
sys.exit(1 if _fails else 0)
