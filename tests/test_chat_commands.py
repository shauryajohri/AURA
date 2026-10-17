"""
Chat command shortcuts (core/brain.py + modules/tasks.py), parsed directly and
driven through the REAL /ws path with the model stubbed out.

What must hold:
  * an ordinary sentence that merely contains "i need to", "todo", "finished",
    "completed", "done with", "afk" (kafka), "gold" (golden ratio) or "check
    for errors" reaches the model and leaves every task as it was
  * a Director-wrapped payload (/plan, /research and its sticky mode, /code,
    /prompt ... /prompt_end) is never read as a command
  * an attached file or fenced code is never read as a command
  * "done with X" / "delete task X" act on the task X names, ask "Which task?"
    when that is unclear, and never delete on a weak match
  * the explicit forms still work: add task, remind me to, mark X done,
    done with X, delete task X, gold price, eurusd, afk, any errors

Runs offline on a throwaway DB and vault; never starts the background loops.

Run:  PYTHONPATH=. python tests/test_chat_commands.py
"""

import os
import queue
import sys
import tempfile
import threading
import time
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# throwaway DB + Buddy Lock vault before anything binds to the real ones
_TMP = tempfile.mkdtemp(prefix="aura_chat_commands_")
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

# The quick-quote module needs `ta` and the network; the routing is what's
# under test, so it answers with a marker.
_forex = types.ModuleType("modules.forex_report")
_forex.get_quick_price = lambda q: "FOREX-QUOTE"
sys.modules["modules.forex_report"] = _forex

from fastapi.testclient import TestClient  # noqa: E402

import core.ai_router as ai_router  # noqa: E402
import local_auth  # noqa: E402
import server  # noqa: E402
from core import brain  # noqa: E402
from modules import command_handler, error_detector, tasks  # noqa: E402

# No model: every turn that reaches it gets this answer, and is counted.
MODEL_CALLS: list[str] = []


def _fake_stream(intent, prompt, system_prompt=None, model=None):
    MODEL_CALLS.append(prompt)
    yield "MODEL-ANSWER."


brain.route_streaming = _fake_stream
brain.call_classifier = lambda p: "CASUAL"
brain.call_claude = lambda *a, **k: "NONE"
ai_router.call_planner = lambda *a, **k: "FETCH: none"
error_detector.handle_error_check = lambda q: "ERROR-CHECK"
command_handler.describe_afk_status = lambda: "AFK-STATUS"
server._voice_is_on = lambda: False
server._init_director()   # the lifespan normally does this; it stays off here

_fails: list[str] = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'} — {label}")
    if not cond:
        _fails.append(label)


def reset(*titles):
    for t in mstore.get_tasks():
        mstore.delete_task(t[0])
    for t in titles:
        mstore.add_task(t)


def titles(status=None):
    return [t[1] for t in mstore.get_tasks(status)]


# ── 1. What counts as a task command ───────────────────────────────────────
print("\n[1] task commands open the message; mentions are not commands")
for text, action, name in [
    ("add task pay rent", "add", "pay rent"),
    ("Add a new task: buy milk", "add", "buy milk"),
    ("remind me to stretch", "add", "stretch"),
    ("new task call mom", "add", "call mom"),
    ("aura, add task water the plants", "add", "water the plants"),
    ("mark pay rent as done", "complete", "pay rent"),
    ("mark done pay rent", "complete", "pay rent"),
    ("complete task pay rent", "complete", "pay rent"),
    ("done with pay rent", "complete", "pay rent"),
    ("I'm done with pay rent", "complete", "pay rent"),
    ("I\u2019m done with pay rent", "complete", "pay rent"),
    ("delete task pay rent", "remove", "pay rent"),
    ("remove the task pay rent", "remove", "pay rent"),
    ("cancel task pay rent", "remove", "pay rent"),
]:
    got = tasks.parse_command(text)
    check(got is not None and got[:2] == (action, name), f"{text!r} → {action} {name!r} (got {got})")
for text in [
    "I need to prepare for an interview tomorrow, any tips?",
    "my todo app idea is kinda dumb right?",
    "what's a good todo list app?",
    "I finished my essay, can you help me write a conclusion?",
    "I finished the movie last night, it was great",
    "have you ever completed a marathon?",
    "how many quests have I completed today?",
    "honestly I'm done with the whole thing for today",
    "can you delete task lists in jira?",
    "add tasks to the sprint board",
    "remind me tomorrow",
]:
    check(tasks.parse_command(text) is None, f"{text!r} is not a command")

print("\n[1b] the other shortcuts match whole words / the whole message")
for text, rx, want in [
    ("is kafka better than rabbitmq?", brain._AFK_RE, False),
    ("afk?", brain._AFK_RE, True),
    ("was I afk just now", brain._AFK_RE, True),
    ("what is the golden ratio", brain._FOREX_RE, False),
    ("i love my golden retriever", brain._FOREX_RE, False),
    ("should I prepare for goldman sachs interviews?", brain._FOREX_RE, False),
    ("is gold price up today?", brain._FOREX_RE, True),
    ("what's the price of gold", brain._FOREX_RE, True),
    ("xauusd", brain._FOREX_RE, True),
    ("what's eurusd at", brain._FOREX_RE, True),
    ("how's EUR/USD", brain._FOREX_RE, True),
    ("how do I check for errors in a bash script?", brain._ERROR_CHECK_RE, False),
    ("can you check for errors in my reasoning here: 2+2=5", brain._ERROR_CHECK_RE, False),
    ("any errors?", brain._ERROR_CHECK_RE, True),
    ("check for errors", brain._ERROR_CHECK_RE, True),
    ("is there an error?", brain._ERROR_CHECK_RE, True),
    ("errors?", brain._ERROR_CHECK_RE, True),
    ("any errors in my code?", brain._ERROR_CHECK_RE, True),
]:
    hit = bool(rx.search(text))
    check(hit == want, f"{text!r} {'matches' if want else 'does not match'}")
check(brain._command_text(None) is None, "no typed text → no shortcuts")
check(brain._command_text("add task x\n\nAttached `a.py`:\n```\nx\n```") is None,
      "a message carrying an attached file → no shortcuts")
check(brain._command_text("add task review [attached file: a.pdf]") is None,
      "a message carrying a binary attachment → no shortcuts")
check(brain._command_text("  add task x ") == "add task x", "plain text passes through")


# ── 2. Which task a command means ──────────────────────────────────────────
print("\n[2] the named task, or a question — never a guess")
for order in (("Fix a bug in login", "Pay rent"), ("Pay rent", "Fix a bug in login")):
    reset(*order)
    out = tasks.handle_remove_task("remove task pay rent")
    check(titles() == ["Fix a bug in login"], f"'remove task pay rent' deletes Pay rent only, order {order} ({out!r})")
reset("Fix a bug in login", "Call the dentist")
out = tasks.handle_complete_task("done with call the dentist")
check(titles("done") == ["Call the dentist"], f"'done with call the dentist' completes the dentist ({out!r})")
reset("Write the quarterly report", "Fix login bug", "Call the dentist")
out = tasks.handle_remove_task("delete task about the weather")
check(len(titles()) == 3 and "Couldn't find" in out, f"'delete task about the weather' deletes nothing ({out!r})")
reset("Pay rent", "Call the dentist")
out = tasks.handle_remove_task("delete task call the dentist")
check(titles() == ["Pay rent"], "'delete task call the dentist' deletes the dentist when it isn't first")
reset("Fix login bug", "Fix signup bug")
out = tasks.handle_complete_task("done with fix bug")
check(not titles("done") and out.startswith("Which task?") and "Fix login bug" in out and "Fix signup bug" in out,
      f"two equally good matches → asks, lists both ({out!r})")
reset("Fix login bug")
out = tasks.handle_remove_task("delete task login")
check(titles() == ["Fix login bug"] and out.startswith("Which task?"),
      f"one word of a three-word title is too weak to delete → asks ({out!r})")
out = tasks.handle_remove_task("delete task fix login bug")
check(titles() == [], "the full name deletes it")
reset("Write the quarterly report")
tasks.handle_complete_task("done with the report")
check(titles("done") == ["Write the quarterly report"], "a unique partial name is enough to complete")
reset("Call the dentist", "Call mom")
tasks.handle_complete_task("done with call the dentst")
check(titles("done") == ["Call the dentist"], "a typo in a longer word still finds it")
reset("Write the quarterly report", "Fix login bug")
check(tasks.handle_task_command("I'm done with the whole thing for today") is None,
      "'I'm done with <no task>' is conversation, not a command")
check(tasks.handle_task_command("mark my words, it'll be done") is None,
      "'mark ... done' that names no task is conversation")
check(not titles("done"), "...and nothing was completed")
tasks.handle_add_task("add a task to buy milk")
check("Buy milk" in titles(), "'add a task to buy milk' → 'Buy milk'")


# ── 3. Through /ws ─────────────────────────────────────────────────────────
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


print("\n[3] ordinary sentences reach the model and change no task")
reset("Write the quarterly report", "Fix login bug", "Call the dentist")
for text in [
    "I need to prepare for an interview tomorrow, any tips?",
    "is kafka better than rabbitmq?",
    "what is the golden ratio",
    "my todo app idea is kinda dumb right?",
    "I finished my essay, can you help me write a conclusion?",
    "I finished the movie last night, it was great",
    "honestly I'm done with the whole thing for today",
    "have you ever completed a marathon?",
    "how many quests have I completed today?",
    "how do I check for errors in a bash script?",
    "can you check for errors in my reasoning here: 2+2=5",
]:
    out = say(text)
    check(out == "MODEL-ANSWER.", f"{text!r} → model (got {out!r})")
check(titles("pending") == ["Write the quarterly report", "Fix login bug", "Call the dentist"],
      "every task still there and still pending")

print("\n[4] workspace modes and /prompt are never read as commands")
reset()
for text, want in [("/plan a todo app with offline sync", "model"), ("/plan_end", None),
                   ("/research how kafka handles partitions", "model"),
                   ("is kafka better than rabbitmq?", "model"),        # sticky mode
                   ("done with kafka, what about rabbitmq?", "model"),
                   ("/research_end", None),
                   ("/code write a todo list component in react", "model"), ("/code_end", None),
                   ("/prompt", None),
                   ("I need to write cold emails to investors", "captured"),
                   ("/prompt_end", "model")]:
    out = say(text)
    if want == "model":
        check(out == "MODEL-ANSWER.", f"{text!r} → model (got {str(out)[:60]!r})")
    elif want == "captured":
        check("[prompt] line" in (out or ""), f"{text!r} → buffered by /prompt")
check(titles() == [], f"no task was created ({titles()})")
check(server.DIRECTOR.mode == "NORMAL", "back in normal mode")

print("\n[5] an attached file or fenced code is never a command")
attached = ("Attached `loader.py`:\n```\ndef load(path):\n"
            "    # TODO: handle missing files\n    return open(path).read()\n```")
for text in [attached + "\n\nWhat does this code do?",
             "add task review this\n\n" + attached,
             "done with this?\n```\nprint('finished')\n```"]:
    out = say(text)
    check(out == "MODEL-ANSWER.", f"{text[:30]!r}... → model (got {str(out)[:60]!r})")
check(titles() == [], "no task was created")

print("\n[6] the explicit forms still work")
reset()
n = len(MODEL_CALLS)
check(say("add task pay rent") == "Added 'Pay rent' to your tasks.", "add task")
check(say("remind me to stretch") == "Added 'Stretch' to your tasks.", "remind me to")
check(say("new task: call the dentist") == "Added 'Call the dentist' to your tasks.", "new task:")
# The Director plans this one as a code request ("write" + "api"); the typed
# command still wins instead of the compiled plan becoming the task title.
check(say("Add task write the API docs") == "Added 'Write the api docs' to your tasks.",
      "add task survives the Director's code-request routing")
check(say("mark pay rent as done") == "Marked 'Pay rent' as done.", "mark X as done")
check(say("I'm done with the dentist") == "Marked 'Call the dentist' as done.", "I'm done with X")
check(say("delete task stretch") == "Removed 'Stretch' from your list.", "delete task X")
check(titles("pending") == ["Write the api docs"] and titles("done") == ["Pay rent", "Call the dentist"],
      f"task list is exactly right ({titles('pending')}, {titles('done')})")
check(say("is gold price up today?") == "FOREX-QUOTE", "gold price → quote")
check(say("what's eurusd at") == "FOREX-QUOTE", "eurusd → quote")
check(say("afk?") == "AFK-STATUS", "afk? → status")
check(say("any errors?") == "ERROR-CHECK", "any errors? → error check")
check(len(MODEL_CALLS) == n, "none of those reached the model")

print("\n[7] the brain runs no shortcut on text it wasn't told the user typed")
reset()
n = len(MODEL_CALLS)
brain.process_streaming("add task pay rent")
check(titles() == [] and len(MODEL_CALLS) == n + 1, "no user_text → the model answers, no task")
brain.process_streaming("You are in planning mode.\n\nUser request: add task pay rent",
                        intent_hint="PLAN", user_text="/plan add task pay rent")
check(titles() == [], "a wrapped payload with a slash command typed → no task")

_cm.__exit__(None, None, None)
print("\n" + ("ALL PASS ✅" if not _fails else f"FAILURES ({len(_fails)}): {_fails}"))
sys.exit(1 if _fails else 0)
