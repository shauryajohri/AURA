"""
The Prompt Maker (/prompt ... /prompt_end), driven through the REAL /ws path
with only the provider stubbed (server.py llm_once branch,
core/conversation_director.py, modules/prompt_maker.py).

What must hold:
  * /prompt_end is one clean call with the prompt-engineer system and the
    buffered notes, not a chat turn: the built prompt arrives whole (every
    sentence, the ones about "the user" too, line breaks kept), and the
    streamed text is exactly the final text
  * the built prompt is recorded: "run" / "2" execute it as a coding task,
    /prompt save stores it (not the raw notes), and the chat log keeps it
  * a failed build says so, records nothing, and leaves "run" as plain chat

Runs offline on a throwaway DB and vault; never starts the background loops.

Run:  PYTHONPATH=. python tests/test_prompt_maker.py
"""

import os
import queue
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# throwaway DB + Buddy Lock vault before anything binds to the real ones
_TMP = tempfile.mkdtemp(prefix="aura_prompt_maker_")
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

from fastapi.testclient import TestClient  # noqa: E402

import core.ai_router as ai_router  # noqa: E402
import local_auth  # noqa: E402
import server  # noqa: E402
from core import brain  # noqa: E402
from modules.prompt_maker import PROMPT_ENGINEER_SYSTEM, get_prompts  # noqa: E402

# A built prompt the chat filters used to wreck: it talks about "the user",
# runs past two sentences and has line breaks.
BUILT = ("You are an executive assistant. Your job is to summarize the user's unread "
         "emails every morning.\n\nConstraints:\n- Write in a formal tone.\n"
         "- Group items by sender.\n- Flag anything urgent.\n\n"
         "Output format: bullet points, one per email.")
CODE = "Here's the code:\n```python\nprint('inbox')\n```"

# The provider is the only thing stubbed. The build may only reach the model
# through the raw call; the chat stream answers it too, so a regression shows
# up as a wrong reply rather than a crash.
RAW: dict = {"answer": BUILT}
CALLS: list[tuple] = []   # (kind, intent, system, prompt)


def _fake_raw(prompt, system, max_tokens=1024, temperature=0.4, model=None):
    if system != PROMPT_ENGINEER_SYSTEM:
        return ""   # side calls (fact extraction…)
    CALLS.append(("raw", None, system, prompt))
    return RAW["answer"]


def _fake_stream(prompt, system=ai_router.DONNA_SYSTEM_PROMPT, intent="CASUAL", model=None):
    CALLS.append(("stream", intent, system, prompt))
    if system == PROMPT_ENGINEER_SYSTEM:
        yield BUILT
    else:
        yield CODE if intent == "CODING" else "MODEL-ANSWER."


ai_router.call_groq_raw = _fake_raw
ai_router.call_groq_streaming = _fake_stream
ai_router._resolve_candidates = lambda intent, model: [("Stub", "stub/model")]
ai_router.call_planner = lambda *a, **k: "FETCH: none"
ai_router.call_groq = lambda *a, **k: "NONE"
brain.call_classifier = lambda p: "CASUAL"
brain.call_claude = lambda *a, **k: "NONE"
server._voice_is_on = lambda: False
server._init_director()   # the lifespan normally does this; it stays off here

_fails: list[str] = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'} — {label}")
    if not cond:
        _fails.append(label)


client = TestClient(server.app, base_url="http://127.0.0.1:8760")
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
    """One turn; returns (streamed chunks joined, done text, push text)."""
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
    chunks = "".join(f["payload"]["text"] for f in got if f.get("type") == "chunk")
    done = next((f["payload"]["text"] for f in got if f.get("type") == "done"), None)
    push = next((f["payload"]["text"] for f in got if f.get("type") == "push"), None)
    return chunks, done, push


def build(*notes):
    """/prompt, the notes, /prompt_end. Returns /prompt_end's turn."""
    turn("/prompt")
    for n in notes:
        turn(n)
    return turn("/prompt_end")


def last_stream():
    s = [c for c in CALLS if c[0] == "stream"]
    return s[-1] if s else None


def last_aura_row():
    rows = [r for r in mstore.get_recent_conversations(50) if r[0] == "aura"]
    return rows[-1][1] if rows else None


# ── 1. The build arrives whole ─────────────────────────────────────────────
print("\n[1] /prompt_end shows the whole built prompt")
CALLS.clear()
chunks, done, _ = build("a prompt that summarizes the user's unread emails each morning",
                        "make it formal and use bullet points")
check(done == BUILT, f"done is the built prompt, every sentence and line ({done!r})")
check(chunks == done, "the streamed text is exactly the done text")
raws = [c for c in CALLS if c[0] == "raw"]
check(len(raws) == 1 and "make it formal and use bullet points" in raws[0][3],
      "one clean call with the prompt-engineer system and the notes")
check(last_stream() is None, "no chat turn was made for the build")
check(last_aura_row() == BUILT, "the chat log keeps the whole built prompt")
check(server.DIRECTOR.prompt_session.last_result == BUILT, "the Director has the built prompt")

# ── 2. What comes after a build uses it ────────────────────────────────────
print("\n[2] run / 2 execute the built prompt; /prompt save stores it")
_, done, _ = turn("run")
ls = last_stream()
check(ls is not None and ls[1] == "CODING" and BUILT in ls[3],
      "'run' sends the built prompt as a coding task")
check(done is not None and "print('inbox')" in done, f"...and shows the code ({done!r})")
_, _, push = turn("/prompt save")
saved = get_prompts(1)
check(bool(saved) and saved[0][2] == BUILT, f"/prompt save stores the built prompt ({push!r})")
CALLS.clear()
build("a prompt for a code reviewer")
turn("2")
ls = last_stream()
check(ls is not None and ls[1] == "CODING" and BUILT in ls[3], "'2' runs it too")
CALLS.clear()
turn("run")
ls = last_stream()
check(ls is not None and ls[1] != "CODING", "the offer is used up after one run")

# ── 3. A failed build records nothing ──────────────────────────────────────
print("\n[3] a failed build says so and records nothing")
server.DIRECTOR.prompt_session.last_result = None
for sentinel, want in [("RATE_LIMIT", "Hit my rate limit — give me a moment."),
                       ("CONNECTION_ERROR", "Connection trouble — one sec."),
                       ("", "Connection trouble — one sec.")]:
    RAW["answer"] = sentinel
    _, done, _ = build("a prompt for a travel planner")
    check(done == want, f"{sentinel or 'empty'} → {want!r} (got {done!r})")
    check(server.DIRECTOR.prompt_session.last_result is None, f"{sentinel or 'empty'}: nothing recorded")
    check(last_aura_row() != sentinel, f"{sentinel or 'empty'}: the sentinel is not in the chat log")
    CALLS.clear()
    turn("run")
    ls = last_stream()
    check(ls is not None and ls[1] != "CODING", f"{sentinel or 'empty'}: 'run' is plain chat afterwards")
RAW["answer"] = BUILT

_cm.__exit__(None, None, None)
print("\n" + ("ALL PASS ✅" if not _fails else f"FAILURES ({len(_fails)}): {_fails}"))
sys.exit(1 if _fails else 0)
