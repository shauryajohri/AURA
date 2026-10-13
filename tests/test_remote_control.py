"""
Offline test for phone remote control: presence gate, planning, confirmation,
execution, stop, and token auth. No display, no network, no real keystrokes:
every action function is swapped for a recorder.

Run:  python -m tests.test_remote_control
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import actions, remote_control as rc  # noqa: E402

rc.LOG_PATH = Path(tempfile.mkdtemp(prefix="aura_remote_test_")) / "log.jsonl"

_fails = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'} — {label}")
    if not cond:
        _fails.append(label)


# --- fakes ------------------------------------------------------------------
calls = []
state = {"locked": False, "desktop": True}


def _recorder(name):
    def fn(**kw):
        calls.append((name, kw))
        return f"{name} ok"
    return fn


for _name in actions.ACTIONS:
    actions.ACTIONS[_name]["fn"] = _recorder(_name)
actions.desktop_available = lambda: (state["desktop"], "" if state["desktop"] else "no display")
rc._session_locked = lambda: state["locked"]
rc._idle_seconds = lambda: 30.0
rc._laptop_snapshot = lambda: "OS: test"


def reset():
    calls.clear()
    state.update(locked=False, desktop=True)
    rc.set_paused(False)
    os.environ.pop("AURA_REMOTE_CONFIRM", None)
    os.environ.pop("AURA_REMOTE_MAX_IDLE_MIN", None)


print("presence gate")
reset()
check(rc.presence()["active"], "unlocked laptop with a desktop is active")
state["locked"] = True
job = rc.submit("open chrome")
check(job.status == "declined" and "locked" in job.reply.lower(), "locked laptop → declined")
check(not calls, "declined job ran nothing")
reset()
state["desktop"] = False
check(rc.submit("open chrome").status == "declined", "no desktop → declined")
reset()
rc.set_paused(True)
check(rc.submit("open chrome").status == "declined", "paused → declined")
reset()
os.environ["AURA_REMOTE_MAX_IDLE_MIN"] = "0.1"   # 6s, fake idle is 30s
check(rc.submit("open chrome").status == "declined", "idle past the limit → declined")

print("quick plans (no model)")
reset()
steps, _ = rc.quick_plan("Aura, open spotify please")
check([s["name"] for s in steps] == ["open_app"] and steps[0]["args"]["name"] == "spotify", "open spotify → open_app")
steps, _ = rc.quick_plan("open github.com")
check(steps[0]["name"] == "open_url", "open github.com → open_url")
steps, _ = rc.quick_plan("search for flights to goa")
check(steps[0]["name"] == "open_url" and "flights+to+goa" in steps[0]["args"]["url"], "search → google url")
check(rc.quick_plan("open chrome and search cats") is None, "compound command → model")

print("execution")
reset()
job = rc.submit("open chrome")
check(job.status == "done", f"safe plan runs straight away ({job.status})")
check(calls == [("open_app", {"name": "chrome"})], "the right action ran")
check(rc.LOG_PATH.exists() and rc.LOG_PATH.read_text().strip(), "job logged")

print("confirmation")
reset()
job = rc.submit("close this window")
check(job.status == "pending" and not calls, "close_window waits for approval")
job = rc.approve(job.id)
check(job.status == "done" and calls and calls[0][0] == "close_window", "approved → runs")
reset()
job = rc.submit("close this window")
rc.cancel(job.id)
check(rc.get_job(job.id).status == "cancelled" and not calls, "cancelled → nothing ran")
reset()
os.environ["AURA_REMOTE_CONFIRM"] = "all"
check(rc.submit("open chrome").status == "pending", "confirm=all holds safe plans too")
reset()
os.environ["AURA_REMOTE_CONFIRM"] = "none"
check(rc.submit("close this window").status == "pending", "confirm=none still asks for risky steps")
reset()
job = rc.submit("close this window")
state["locked"] = True
check(rc.approve(job.id).status == "declined" and not calls, "locked between plan and approve → declined")

print("risk levels")
check(actions.risk_of("hotkey", {"keys": ["ctrl", "s"]}) == "safe", "ctrl+s is safe")
check(actions.risk_of("hotkey", {"keys": "Alt+F4"}) == "confirm", "alt+f4 asks")
check(actions.risk_of("press", {"key": "delete"}) == "confirm", "delete asks")
check(actions.risk_of("run_shell", {"command": "dir"}) == "confirm", "shell asks")
check(actions.risk_of("made_up", {}) == "confirm", "unknown action asks")

print("model plan parsing")
reset()
steps, say = rc.parse_plan(
    'DO: open_app {"name": "notepad"}\n'
    'DO: wait {"seconds": 2}\n'
    'DO: type_text {"text": "hi"}\n'
    'DO: run_shell {"command": "del *"}\n'
    'DO: teleport {}\n'
    "SAY: Writing it in Notepad."
)
check([s["name"] for s in steps] == ["open_app", "wait", "type_text"],
      "unknown actions and shell (not allowed) are dropped")
check(say == "Writing it in Notepad.", "SAY captured")
os.environ["AURA_REMOTE_ALLOW_SHELL"] = "1"
steps, _ = rc.parse_plan('DO: run_shell {"command": "dir"}')
check(steps and steps[0]["risk"] == "confirm", "shell allowed by env, still confirm-level")
os.environ.pop("AURA_REMOTE_ALLOW_SHELL")

print("failure + stop")
reset()
actions.ACTIONS["focus_window"]["fn"] = lambda **kw: (_ for _ in ()).throw(actions.ActionError("no window"))
job = rc.execute(rc.Job(id="f1", text="t", say="", steps=[
    rc._step("focus_window", {"title": "x"}), rc._step("type_text", {"text": "hi"})]))
check(job.status == "failed" and not calls, "a failing step stops the rest")
actions.ACTIONS["focus_window"]["fn"] = _recorder("focus_window")


def _locks(**kw):
    calls.append(("wait", kw))
    state["locked"] = True
    return "ok"


reset()
actions.ACTIONS["wait"]["fn"] = _locks
job = rc.execute(rc.Job(id="s1", text="t", say="", steps=[
    rc._step("wait", {}), rc._step("type_text", {"text": "hi"})]))
check(job.status == "stopped" and len(calls) == 1, "locking mid-job stops it")
actions.ACTIONS["wait"]["fn"] = _recorder("wait")

reset()
actions.STOP.set()
try:
    actions.run_action("press", {"key": "a"})
    check(False, "STOP aborts actions")
except actions.Stopped:
    check(True, "STOP aborts actions")
actions.STOP.clear()

print("token auth")
try:
    from fastapi.testclient import TestClient
    import remote_api

    os.environ["AURA_REMOTE_TOKEN"] = "short"
    client = TestClient(remote_api.build_app())
    check(client.get("/remote/api/status").status_code == 503, "short token → disabled")
    os.environ["AURA_REMOTE_TOKEN"] = "x" * 32
    check(client.get("/remote/api/status").status_code == 401, "no token → 401")
    check(client.get("/remote/api/status", headers={"Authorization": "Bearer nope"}).status_code == 401,
          "wrong token → 401")
    ok = client.get("/remote/api/status", headers={"Authorization": "Bearer " + "x" * 32})
    check(ok.status_code == 200 and ok.json()["active"], "right token → status")
    reset()
    r = client.post("/remote/api/command", json={"text": "open notepad"},
                    headers={"X-Aura-Token": "x" * 32})
    check(r.status_code == 200 and r.json()["status"] == "done", "command over HTTP runs")
    check(client.get("/").status_code == 200, "phone page served")
    for _ in range(remote_api.FAIL_LIMIT):
        client.get("/remote/api/status", headers={"Authorization": "Bearer bad"})
    check(client.get("/remote/api/status", headers={"Authorization": "Bearer " + "x" * 32}).status_code == 429,
          "repeated bad tokens → locked out")
except ImportError as e:
    print(f"  SKIP — fastapi test client unavailable ({e})")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    sys.exit(1)
print("all passed")
