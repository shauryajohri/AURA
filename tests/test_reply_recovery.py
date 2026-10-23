"""
Replies that used to be thrown away or lost (core/ai_router.py stream filter,
core/brain.py process_streaming + the CODING lane, core/response_composer.py),
driven through the REAL route_streaming and /ws with only the provider stubbed.

What must hold:
  * a reasoning leak that hands over to its answer ("So answer: Hi there…",
    "Final answer: …", "We can say something like: "…"") streams the answer,
    the same text sanitize_text gives for the whole reply, at any chunk size
  * a reply that is ALL deliberation says "Lost my train of thought", not
    "Connection trouble"; a real provider failure still says "Connection
    trouble"
  * a clean reply streams exactly as the model wrote it
  * CODING lane: "Here's the X:" + code, or code alone, never shows, stores or
    speaks the "lost my train of thought" line; meta prose around the code is
    filtered; a cut opener leaves no lowercase start
  * CODING lane: the stored turn is exactly the "done" text the UI got (chat
    line + fenced code), and the next prompt's transcript carries the code

Runs offline on a throwaway DB and vault; never starts the background loops.

Run:  PYTHONPATH=. python tests/test_reply_recovery.py
"""

import os
import queue
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# throwaway DB + Buddy Lock vault before anything binds to the real ones
_TMP = tempfile.mkdtemp(prefix="aura_reply_recovery_")
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
from core.response_composer import compose_text  # noqa: E402

# The provider is the only thing stubbed: route_streaming and its stream
# filter run for real. One model in the chain, never locked.
STREAM: dict = {"chunks": []}
PROMPTS: list[str] = []


def _fake_provider(prompt, system=None, intent="CASUAL", model=None):
    PROMPTS.append(prompt)
    yield from STREAM["chunks"]


ai_router.call_groq_streaming = _fake_provider
ai_router._resolve_candidates = lambda intent, model: [("Stub", "stub/model")]
ai_router.has_key = lambda model_id=None: True   # no real keys here; the stub answers
ai_router.call_planner = lambda *a, **k: "FETCH: none"
ai_router.call_groq_raw = lambda *a, **k: ""   # side calls (fact extraction…)
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


def feed(raw, size=0):
    STREAM["chunks"] = [raw[i:i + size] for i in range(0, len(raw), size)] if size else [raw]


def stream(raw, size=0):
    feed(raw, size)
    return "".join(ai_router.route_streaming("CASUAL", "hi"))


LOST = "Lost my train of thought there — say that again?"

# ── 1. The stream recovers the answer after the seam ──────────────────────
print("\n[1] a leak that hands over to its answer streams the answer")
for raw, want in [
    ("The user wants a greeting. So answer: Hi there, good to see you.", "Hi there, good to see you."),
    ("The user says hi. So we can say: Hey! Long time no see.", "Hey! Long time no see."),
    ("We need to respond casually. Final answer: Not much, just here with you.",
     "Not much, just here with you."),
    ("The user is asking what's up. We can say something like: \"Just hanging out — you?\"",
     "Just hanging out — you?"),
    ("So answer: It's 3 PM in Tokyo right now.", "It's 3 PM in Tokyo right now."),
    ("The user asks how I am. We can say something like: \"Just hanging out — you?\"",
     "Just hanging out — you?"),
]:
    check(ai_router.sanitize_text(raw) == want, f"sanitize_text agrees on {raw[:40]!r}")
    for size in (1, 6, 7, 0):
        got = stream(raw, size)
        check(got == want, f"chunk {size or 'all'}: {raw[:40]!r} → {got!r}")
    feed(raw, 6)
    got = brain.process_streaming("what's up buddy", intent_hint="CASUAL")
    check(got == want, f"process_streaming shows the answer ({got!r})")

print("\n[1b] clean replies stream exactly as written")
for raw in ["Hi there, good to see you.",
            "# Plan\n\n1. Do X.\n2. Do Y.\n\n- one\n- two\n",
            "Here's how:\n```python\ndef f(x):\n    return x * 2\n```\nThat doubles it."]:
    for size in (1, 6, 0):
        check(stream(raw, size) == raw, f"chunk {size or 'all'}: {raw[:30]!r} unchanged")
raw = "The user asks for code. We need to answer.\nHere:\n```python\ndef f(x):\n    return x\n```\nDone."
want = "Here:\n```python\ndef f(x):\n    return x\n```\nDone."
for size in (1, 6, 0):
    check(stream(raw, size) == want, f"chunk {size or 'all'}: preamble peeled, code kept byte-for-byte")
# One ordinary sentence inside a monologue: the peel would start on it, but
# sanitize_text bins the whole thing (density rule). Arriving in one piece,
# the stream holds it back; arriving piecemeal it can't see what follows, so
# the final pass is what decides.
raw = "The user says hi. Hey there. The user is nice. They want a reply."
check(ai_router.sanitize_text(raw) == "", "a mostly-meta reply is all deliberation to sanitize_text")
check(stream(raw) == "", "in one chunk the stream holds it back too")
for size in (1, 6, 0):
    check(ai_router.sanitize_text(stream(raw, size)) == "", f"chunk {size or 'all'}: the final pass agrees")
    feed(raw, size)
    check(brain.process_streaming("hey", intent_hint="CASUAL") == LOST,
          f"chunk {size or 'all'}: process_streaming → 'lost my train of thought'")

# ── 2. Empty is not a connection problem ──────────────────────────────────
print("\n[2] nothing left after filtering → 'lost my train of thought'")
for raw in ["The user says hi. We need to respond in one sentence. No emoji.",
            "<think>keep it short</think>"]:
    feed(raw, 6)
    got = brain.process_streaming("hey", intent_hint="CASUAL")
    check(got == LOST, f"{raw[:40]!r} → {got!r}")
STREAM["chunks"] = ["CONNECTION_ERROR"]
check(brain.process_streaming("hey", intent_hint="CASUAL") == "Connection trouble — one sec.",
      "a provider failure is still 'Connection trouble'")
STREAM["chunks"] = ["RATE_LIMIT"]
check(brain.process_streaming("hey", intent_hint="CASUAL") == "Hit my rate limit — give me a moment.",
      "a rate limit is still the rate-limit line")

# ── 3. The composer never buries code under the fallback line ─────────────
print("\n[3] composer: neutral intro with code, capitals after a cut opener")
try:
    check(compose_text("Here's the C program:", "CODING", with_code=True) == "Here you go:",
          "'Here's the C program:' with code → 'Here you go:'")
    check(compose_text("", "CODING", with_code=True) == "Here you go:", "code with no line → 'Here you go:'")
except TypeError as e:
    check(False, f"compose_text takes with_code ({e})")
check("lost my train" in compose_text("", "CODING").lower(), "no code and no line → still the fallback")
check(compose_text("Sure, the time complexity is O(n).", "CODING") == "The time complexity is O(n).",
      "'Sure, the time…' → 'The time…'")
check(compose_text("Here's the fix: the loop was off by one.", "CODING") == "The loop was off by one.",
      "'Here's the fix: the loop…' → 'The loop…'")
check(compose_text("Sure, iOS handles that for you.", "CASUAL") == "iOS handles that for you.",
      "an identifier like iOS keeps its case")
check(compose_text("Sure, print() returns None.", "CODING") == "print() returns None.",
      "print() keeps its case")
check(compose_text("the loop was off by one.", "CODING") == "the loop was off by one.",
      "no opener cut → text left alone")

# ── 4. CODING lane through /ws ─────────────────────────────────────────────
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


def say(text, timeout=20.0):
    """One turn; returns the reply text (a 'done' frame, else a 'push')."""
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
    for kind in ("done", "push"):
        for f in got:
            if f.get("type") == kind:
                return f["payload"]["text"]
    return None


def last_aura_row():
    rows = [r for r in mstore.get_recent_conversations(50) if r[0] == "aura"]
    return rows[-1][1] if rows else None


print("\n[4] CODING lane: shown, stored and spoken text")
say("/code")
C_PROG = "```c\n#include <stdio.h>\nint main(){printf(\"hi\");return 0;}\n```"
for label, raw, ask, want in [
    ("intro + code", "Here's the C program:\n" + C_PROG, "hello world in c", "Here you go:\n\n" + C_PROG),
    ("code only", C_PROG, "hello world in c again", "Here you go:\n\n" + C_PROG),
    ("meta after the code", "Here's the code:\n```python\nprint(1)\n```\n"
     "The user wants it short so we need to keep it to one line.",
     "print one in python", "Here you go:\n\n```python\nprint(1)\n```"),
    ("closing line kept", "Here's the function:\n```python\ndef rev(s):\n    return s[::-1]\n```\n"
     "Call it with any string.", "write a python function to reverse a string",
     "Call it with any string.\n\n```python\ndef rev(s):\n    return s[::-1]\n```"),
]:
    feed(raw)
    done = say(ask)
    check(done == want, f"{label}: done {done!r}")
    check(last_aura_row() == done, f"{label}: the stored turn is the done text")
feed("Sure, the time complexity is O(n).")
done = say("what's the complexity of that?")
check(done == "The time complexity is O(n).", f"no lowercase start ({done!r})")

print("\n[5] the follow-up prompt carries the code")
feed("Here's the function:\n```python\ndef rev(s):\n    return s[::-1]\n```")
say("reverse a string in python")
feed("It's O(n).")
PROMPTS.clear()
say("what's the complexity of that?")
check(bool(PROMPTS) and "return s[::-1]" in PROMPTS[-1], "the transcript shows the code it is about")
big = "```python\n" + "\n".join(f"x{i} = {i}" for i in range(400)) + "\n```"
feed("Here's the table:\n" + big)
say("make me a big table in python")
feed("Sure.")
PROMPTS.clear()
say("and the last line?")
p = PROMPTS[-1] if PROMPTS else ""
check("x0 = 0" in p and "x399 = 399" not in p, "a long code reply is cut, not dropped")
check(p.count("```") % 2 == 0, "...and the cut closes its fence")
say("/code_end")

_cm.__exit__(None, None, None)
print("\n" + ("ALL PASS ✅" if not _fails else f"FAILURES ({len(_fails)}): {_fails}"))
sys.exit(1 if _fails else 0)
