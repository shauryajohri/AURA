"""
No API key, and which model answered (core/ai_router.py routing + key checks,
core/brain.py, server.py done frame + /api/status, the planet mapping in
frontend/src/hooks/useAuraSocket.ts), driven through the REAL routing and /ws
with only the HTTP layer faked.

What must hold:
  * with no provider key, a chat / coding / research turn makes NO provider
    request and says how to add a key, not "Connection trouble — one sec."
  * a model whose key is missing is never called, so with only some keys the
    turn goes to a model that has one, or says how to add one
  * /api/status says keys_missing and stops claiming Groq runs everything
  * the done frame's model is the model that answered THIS turn: '' for an
    error, a fallback line, the no-key line and a shortcut, never the stale
    last model
  * every routed model id lights its own planet (GPT-OSS is not GPT-4o)

Runs offline on a throwaway DB and vault; never starts the background loops.

Run:  PYTHONPATH=. python tests/test_no_key.py
"""

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# throwaway DB + Buddy Lock vault before anything binds to the real ones
_TMP = tempfile.mkdtemp(prefix="aura_no_key_")
os.environ["AURA_GUARD_VAULT"] = os.path.join(_TMP, "buddy.json")
os.environ.pop("AURA_TOKEN", None)

import memory.store as mstore  # noqa: E402
mstore.DB_PATH = os.path.join(_TMP, "test.db")
mstore.init_db()
mstore.init_tasks()
mstore.init_quests()
from core.domain import brain_store  # noqa: E402
brain_store.DB_PATH = mstore.DB_PATH
brain_store._connect = mstore._connect
# every chat turn bumps the relationship engine, which saves to memory/
from modules import relationship_engine  # noqa: E402
relationship_engine.STATE_FILE = os.path.join(_TMP, "relationship_state.json")

# Lock state is not under test: nothing is locked, and the real store is
# never read (it needs a GUI toolkit that a backend-only install lacks).
try:
    from core import model_lock  # noqa: E402
except ImportError:
    import core  # noqa: E402
    model_lock = types.ModuleType("core.model_lock")
    sys.modules["core.model_lock"] = core.model_lock = model_lock
model_lock.is_locked = lambda name: False

from fastapi.testclient import TestClient  # noqa: E402

import core.ai_router as ai_router  # noqa: E402
import local_auth  # noqa: E402
import server  # noqa: E402
from core import activity, model_router  # noqa: E402

GEMMA = model_router.MODELS["Gemma 4 31B"]
OSS_120 = model_router.MODELS["GPT-OSS 120B"]
OSS_20 = model_router.MODELS["GPT-OSS 20B"]
NO_KEY = ai_router.NO_KEY_MSG
TROUBLE = "Connection trouble — one sec."
LOST = "Lost my train of thought there — say that again?"


# ── the HTTP layer is the only fake ─────────────────────────────────────────
# Every provider call (chat stream, classifier, planner, side calls) goes
# through ai_router's own requests.post, so this sees all of them.
POSTS: list[dict] = []
REPLY: dict = {}   # model id -> reply text, or an HTTP error status


class _Resp:
    def __init__(self, status, content=""):
        self.status_code = status
        self.text = '{"error": "denied"}' if status >= 400 else ""
        self._content = content

    def json(self):
        if self.status_code >= 400:
            return {"error": {"message": "denied"}}
        return {"choices": [{"message": {"content": self._content}}]}

    def iter_lines(self):
        yield ("data: " + json.dumps({"choices": [{"delta": {"content": self._content}}]})).encode()
        yield b"data: [DONE]"


def _post(url, headers=None, json=None, timeout=None, stream=False):  # noqa: A002
    body = json or {}
    POSTS.append({"url": url, "model": body.get("model"), "stream": bool(body.get("stream")),
                  "auth": (headers or {}).get("Authorization", "")})
    if body.get("stream"):
        r = REPLY.get(body.get("model"), "Doing fine, thanks.")
        return _Resp(r) if isinstance(r, int) else _Resp(200, r)
    system = body["messages"][0]["content"]
    return _Resp(200, "CASUAL" if "classifier" in system else "NONE")


ai_router.requests = types.SimpleNamespace(post=_post)

ACTIVITY: list[str] = []
activity.set_sink(lambda ev: ACTIVITY.append(ev.get("text", "")))

server._voice_is_on = lambda: False
server._init_director()   # the lifespan normally does this; it stays off here


def keys(groq=None, shared=None, chat=None, coding=None, research=None):
    """Set the provider keys the router sees (the real .env never matters)."""
    ai_router.GROQ_API_KEY = groq
    ai_router.OPENROUTER_API_KEY = shared
    ai_router._OPENROUTER_MODEL_KEYS = {
        model_router.MODELS["Laguna M.1"]: coding or shared,
        model_router.MODELS["Nemotron 3 Super"]: research or shared,
        GEMMA: chat or shared,
    }


_fails: list[str] = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'} — {label}")
    if not cond:
        _fails.append(label)


client = TestClient(server.app, base_url="http://127.0.0.1:8760")
HDR = {"X-Aura-Token": local_auth.TOKEN}
_cm = client.websocket_connect("ws://127.0.0.1:8760/ws",
                               subprotocols=["aura", "aura-token." + local_auth.TOKEN])
ws = _cm.__enter__()
_frames: queue.Queue = queue.Queue()


def _reader():
    try:
        while True:
            _frames.put(ws.receive_json())
    except Exception:  # noqa: BLE001
        _frames.put({"type": "_closed"})


threading.Thread(target=_reader, daemon=True).start()
time.sleep(0.3)
while not _frames.empty():
    _frames.get()


def turn(text, timeout=20.0):
    """One turn; returns (done text, done model) — (None, None) if no done."""
    ws.send_json({"type": "message", "payload": {"text": text}})
    got, end = [], time.time() + timeout
    while time.time() < end:
        try:
            f = _frames.get(timeout=0.2)
        except queue.Empty:
            continue
        got.append(f)
        if f.get("type") == "_closed":
            break
        if (f.get("type") == "state" and f["payload"].get("state") == "idle"
                and any(g.get("type") in ("done", "push", "error") for g in got)):
            break
    done = next((f["payload"] for f in got if f.get("type") == "done"), None)
    return (done["text"], done.get("model")) if done else (None, None)


def streamed_models(since):
    return [p["model"] for p in POSTS[since:] if p["stream"]]


# ── 1. No key at all ───────────────────────────────────────────────────────
print("\n[1] no key: no provider request, and the reply says how to add one")
keys()
st = client.get("/api/status", headers=HDR).json()
check(st.get("keys_missing") is True, f"/api/status keys_missing is true ({st.get('keys_missing')!r})")
check("running on Groq" not in st.get("openrouter", ""), f"status doesn't claim Groq runs ({st.get('openrouter')!r})")
check(st.get("last_model") == "", f"no model has answered yet ({st.get('last_model')!r})")
for msg in ["hey", "what's the capital of France?", "write a python function to reverse a string"]:
    n0, a0 = len(POSTS), len(ACTIVITY)
    t0 = time.time()
    done, model = turn(msg)
    check(done == NO_KEY, f"{msg!r} → the setup line (got {done!r})")
    check(model == "", f"{msg!r}: no model on the chip (got {model!r})")
    check(len(POSTS) == n0, f"{msg!r}: no provider request ({[p['url'] for p in POSTS[n0:]]})")
    check(not any("unavailable" in a for a in ACTIVITY[a0:]), f"{msg!r}: no 'unavailable — falling back' lines")
    check(time.time() - t0 < 5, f"{msg!r}: answered at once")
for name, call in [("classifier", lambda: ai_router.call_classifier("hi")),
                   ("planner", lambda: ai_router.call_planner("hi", "sys")),
                   ("side call", lambda: ai_router.call_groq("hi")),
                   ("raw call", lambda: ai_router.call_groq_raw("hi", "sys"))]:
    n0 = len(POSTS)
    out = call()
    check(out == "CONNECTION_ERROR" and len(POSTS) == n0, f"{name}: same sentinel as before, no request ({out!r})")
check(ai_router.route("CASUAL", "hi") == "NO_KEY", "route() says NO_KEY")
keys(groq="your-groq-key-here")
check(ai_router.keys_missing(), "a leftover .env placeholder is not a key")
n0 = len(POSTS)
done, _ = turn("hey")
check(done == NO_KEY and len(POSTS) == n0, f"...and the turn still says how to add one ({done!r})")
keys()
done, model = turn("add task buy milk")
check(done is not None and "Buy milk" in done and model == "", f"shortcuts still work, no model ({done!r}, {model!r})")
n0 = len(POSTS)
done, model = turn("/research quantum computing")
check(done == NO_KEY and model == "" and len(POSTS) == n0, f"/research → the setup line ({done!r})")
turn("/research_end")
turn("/prompt")
turn("a prompt that summarizes my unread emails")
n0 = len(POSTS)
done, model = turn("/prompt_end")
check(done == NO_KEY and model == "" and len(POSTS) == n0, f"/prompt_end → the setup line ({done!r})")

# ── 2. Some keys ───────────────────────────────────────────────────────────
print("\n[2] a model without a key is never called")
keys(groq="gsk-test")
st = client.get("/api/status", headers=HDR).json()
check(st.get("keys_missing") is False, "/api/status keys_missing is false with a Groq key")
check("running on Groq" in st.get("openrouter", ""), f"...and says Groq runs everything ({st.get('openrouter')!r})")
REPLY.clear()
n0 = len(POSTS)
done, model = turn("hey")
check(streamed_models(n0) == [OSS_120], f"Gemma (no OpenRouter key) is skipped, GPT-OSS 120B answers ({streamed_models(n0)})")
check(not any(p["auth"] == "Bearer None" for p in POSTS[n0:]), "no request goes out with 'Bearer None'")
check(done == "Doing fine, thanks." and model == OSS_120, f"done names the model that answered ({done!r}, {model!r})")
keys(coding="sk-or-coding")
st = client.get("/api/status", headers=HDR).json()
check(st.get("keys_missing") is False and "fall back to Groq)" not in st.get("openrouter", ""),
      f"OpenRouter-only status doesn't promise a Groq fallback ({st.get('openrouter')!r})")
n0 = len(POSTS)
done, model = turn("hey")
check(done == NO_KEY and model == "" and len(POSTS) == n0,
      f"chat with only a coding key: no candidate has a key → the setup line ({done!r})")

# ── 3. The chip names the model that answered this turn ────────────────────
print("\n[3] the done frame's model is this turn's, '' when none answered")
keys(groq="gsk-test", shared="sk-or-test")
REPLY.clear()
REPLY[GEMMA] = 503
n0 = len(POSTS)
done, model = turn("hey")
check(streamed_models(n0) == [GEMMA, OSS_120], f"Gemma fails, GPT-OSS 120B answers ({streamed_models(n0)})")
check(done == "Doing fine, thanks." and model == OSS_120, f"the fallback that answered is named ({model!r})")
REPLY.update({GEMMA: 503, OSS_120: 503, OSS_20: 503})
done, model = turn("hey")
check(done == TROUBLE, f"every model failing with keys present is still 'Connection trouble' ({done!r})")
check(model == "", f"...and claims no model (got {model!r}, last answer was {OSS_120})")
REPLY.clear()
REPLY[GEMMA] = "<think>They said hey. Keep it short.</think>"
done, model = turn("hey")
check(done == LOST and model == "", f"an all-deliberation reply is a fallback line, no model ({done!r}, {model!r})")
REPLY.clear()
done, model = turn("hey")
check(model == GEMMA, f"a clean answer names its model ({model!r})")
done, model = turn("add task call mom")
check(done is not None and "Call mom" in done and model == "", f"a shortcut after it claims no model ({model!r})")
st = client.get("/api/status", headers=HDR).json()
check(st.get("last_model") == GEMMA, f"/api/status last_model is still the last real answer ({st.get('last_model')!r})")

# ── 4. Every routed model lights its own planet ────────────────────────────
print("\n[4] modelIdToNode maps each routed id to the planet with its name")
node = shutil.which("node")
src = open(os.path.join(ROOT, "frontend", "src", "hooks", "useAuraSocket.ts"), encoding="utf-8").read()
m = re.search(r"function modelIdToNode\(model: string\): string \| null \{.*?\n\}\n", src, re.S)
check(m is not None, "modelIdToNode found in useAuraSocket.ts")
planets = dict(re.findall(r'\{ id: "(\w+)",\s*name: "([^"]+)"',
                          open(os.path.join(ROOT, "frontend", "src", "data", "models.ts"), encoding="utf-8").read()))
if not node or m is None:
    print("  SKIP — node is not installed")
else:
    fn = m.group(0).replace("(model: string): string | null", "(model)")
    ids = list(model_router.MODELS.values()) + [""]
    js = fn + f"\nconsole.log(JSON.stringify({json.dumps(ids)}.map(modelIdToNode)));"
    out = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=30)
    got = dict(zip(ids, json.loads(out.stdout or "[]")))
    for name, mid in model_router.MODELS.items():
        check(planets.get(got.get(mid)) == name, f"{mid} → {got.get(mid)!r} ({planets.get(got.get(mid))!r}, want {name!r})")
    check(got.get("") is None, "an empty model maps to no planet")

_cm.__exit__(None, None, None)
print("\n" + ("ALL PASS ✅" if not _fails else f"FAILURES ({len(_fails)}): {_fails}"))
sys.exit(1 if _fails else 0)
