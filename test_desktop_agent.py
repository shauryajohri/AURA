"""
Tests for core.desktop_agent — AURA operating the screen on request (/do).

Covered here:
  1. parsing: the model's reply → a validated action (or None)
  2. safety rules: block secrets, ask before risky steps, allow the rest
  3. the loop, on a fake screen with a scripted model:
       finishes on "done", asks the user on "ask"
       risky step → waits for Allow; Deny or no answer → stops
       password field → blocked
       Stop / Esc / moving the mouse → stops
       step limit, junk replies, missing vision key
  4. elements are clicked at their centre; coordinates map 0-1000 → pixels

Run:  PYTHONPATH=. python test_desktop_agent.py
"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import desktop_agent as D  # noqa: E402

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {label}")
    else:
        failed += 1
        print(f"  ✗ {label}")


print("\n[parsing the model's reply]")
P = D.parse_action
check("plain JSON", P('{"action":"click","element":3}')["element"] == 3)
check("JSON in a code fence", P('```json\n{"action":"key","keys":"ctrl+l"}\n```')["keys"] == "ctrl+l")
check("JSON after chatter", P('Sure! {"action":"done","message":"ok"}')["action"] == "done")
check("unknown action → None", P('{"action":"format_disk"}') is None)
check("click with no target → None", P('{"action":"click"}') is None)
check("type with no text → None", P('{"action":"type"}') is None)
check("coordinates are clamped", P('{"action":"click","x":5000,"y":-3}')["x"] == 1000)
check("risky flag kept", P('{"action":"click","element":1,"risky":true}')["risky"] is True)
check("not JSON → None", P("I would click the button") is None)
check("long text is capped",
      len(P('{"action":"type","text":"%s"}' % ("a" * 2000))["text"]) == D.MAX_TYPE_CHARS)


def obs(elements=None, app="Notepad"):
    return D.Observation(image_b64="x", width=2000, height=1000, app=app, title="t",
                         elements=elements or [])


SEND = D.Element(1, "Button", "Send", (100, 100, 200, 140))
PW = D.Element(2, "Edit", "", (0, 0, 10, 10), password=True)
NAME = D.Element(3, "Edit", "First name", (300, 300, 500, 340))
PIN = D.Element(4, "Edit", "Enter PIN", (0, 0, 10, 10))
OK = D.Element(5, "Button", "Next", (600, 600, 700, 640))

print("\n[safety rules]")
A = D.assess
o = obs([SEND, PW, NAME, PIN, OK])
check("typing a name is fine", A({"action": "type", "text": "Sam", "element": 3}, o)[0] == "ok")
check("clicking Next is fine", A({"action": "click", "element": 5}, o)[0] == "ok")
check("password field is blocked", A({"action": "type", "text": "x", "element": 2}, o)[0] == "block")
check("PIN field is blocked", A({"action": "type", "text": "1234", "element": 4}, o)[0] == "block")
check("card number is blocked",
      A({"action": "type", "text": "4111 1111 1111 1111"}, o)[0] == "block")
check("clicking Send asks first", A({"action": "click", "element": 1}, o)[0] == "confirm")
check("model-flagged risky asks first",
      A({"action": "click", "element": 5, "risky": True}, o)[0] == "confirm")
check("Delete key asks first", A({"action": "key", "keys": "shift+delete"}, o)[0] == "confirm")
check("Alt+F4 asks first", A({"action": "key", "keys": "alt+f4"}, o)[0] == "confirm")
check("typing in a terminal asks first",
      A({"action": "type", "text": "dir"}, obs(app="PowerShell"))[0] == "confirm")
check("'check every step' asks for a normal click",
      A({"action": "click", "element": 5}, o, confirm_all=True)[0] == "confirm")
check("done never needs permission", A({"action": "done"}, o)[0] == "ok")


class FakePlatform(D.Platform):
    def __init__(self, elements=None, app="Notepad"):
        self.elements = elements or [SEND, PW, NAME, OK]
        self.app = app
        self.log = []
        self.pos = (0, 0)
        self.escape = None

    def observe(self):
        return obs(self.elements, self.app)

    def click(self, x, y, button="left", clicks=1):
        self.log.append(("click", x, y, button, clicks))
        self.pos = (x, y)

    def type_text(self, text):
        self.log.append(("type", text))

    def press(self, keys):
        self.log.append(("key", keys))

    def scroll(self, amount, x=None, y=None):
        self.log.append(("scroll", amount))

    def open_app(self, name):
        self.log.append(("open", name))

    def mouse(self):
        return self.pos

    def watch_escape(self, on_escape):
        self.escape = on_escape
        return lambda: None


def scripted(*replies):
    it = iter(replies)
    return lambda prompt, img: next(it, '{"action":"done","message":"out of script"}')


def agent(platform, model):
    return D.DesktopAgent(platform_factory=lambda: platform, model=model,
                          sleep=lambda s: None, settle=0)


print("\n[the loop]")
fp = FakePlatform()
events = []
a = agent(fp, scripted('{"action":"click","element":3}',
                       '{"action":"type","text":"Sam","element":3}',
                       '{"action":"key","keys":"enter"}',
                       '{"action":"done","message":"filled the form"}'))
a.set_sink(events.append)
r = a.run("fill in my name")
check("finishes on done", r["state"] == "done" and r["message"] == "filled the form")
check("clicked the element's centre", fp.log[0] == ("click", 400, 320, "left", 1))
check("typing focuses the field, then types", fp.log[1][0] == "click" and fp.log[2] == ("type", "Sam"))
check("pressed enter", ("key", "enter") in fp.log)
check("every step was published", [e["state"] for e in events].count("running") >= 4)
check("published plain words", any(e.get("action") == 'type "Sam"' for e in events))

fp = FakePlatform()
r = agent(fp, scripted('{"action":"click","x":500,"y":250}')).run("click the middle")
check("coordinates map to real pixels", fp.log[0][1:3] == (1000, 250))

fp = FakePlatform()
r = agent(fp, scripted('{"action":"ask","message":"Which file?"}')).run("open my file")
check("ask hands the question back", r["state"] == "ask" and r["message"] == "Which file?")


print("\n[asking permission]")


def run_with_answer(answer, timeout=None):
    fp = FakePlatform()
    a = agent(fp, scripted('{"action":"click","element":1}', '{"action":"done","message":"sent"}'))
    seen = []

    def sink(e):
        seen.append(e)
        if e["state"] == "confirm" and answer is not None:
            threading.Timer(0.05, lambda: a.confirm(e["confirm_id"], answer)).start()

    a.set_sink(sink)
    old = D.CONFIRM_TIMEOUT
    if timeout is not None:
        D.CONFIRM_TIMEOUT = timeout
    try:
        return a.run("send the email"), fp, seen
    finally:
        D.CONFIRM_TIMEOUT = old


r, fp, seen = run_with_answer(True)
check("risky step asked first", any(e["state"] == "confirm" for e in seen))
check("the question names the action", any('click "Send"' in e.get("message", "") for e in seen))
check("Allow → it clicks and finishes", r["state"] == "done" and fp.log and fp.log[0][0] == "click")
r, fp, _ = run_with_answer(False)
check("Deny → stops without clicking", r["state"] == "stopped" and fp.log == [])
r, fp, _ = run_with_answer(None, timeout=0.1)
check("no answer → treated as no", r["state"] == "stopped" and fp.log == [])

fp = FakePlatform()
a = agent(fp, scripted('{"action":"click","element":5}'))
check("a stale confirm id is rejected", a.confirm("nope", True) is False)


print("\n[blocked and stopped]")
fp = FakePlatform()
r = agent(fp, scripted('{"action":"type","text":"hunter2","element":2}')).run("log in")
check("password field → stopped, nothing typed", r["state"] == "stopped" and fp.log == [])
check("says why", "password" in r["message"])

fp = FakePlatform()
a = agent(fp, None)


def model_then_stop(prompt, img):
    a.stop("you pressed Stop")
    return '{"action":"click","element":5}'


a._model = model_then_stop
r = a.run("anything")
check("Stop mid-step → nothing happens", r["state"] == "stopped" and fp.log == [])

fp = FakePlatform()
a = agent(fp, None)


def model_esc(prompt, img):
    fp.escape()
    return '{"action":"click","element":5}'


a._model = model_esc
r = a.run("anything")
check("Esc stops it", r["state"] == "stopped" and "Esc" in r["message"])

fp = FakePlatform()
calls = {"n": 0}


def model_user_moves(prompt, img):
    calls["n"] += 1
    if calls["n"] == 2:
        fp.pos = (1500, 900)      # the user grabbed the mouse
    return '{"action":"click","element":5}'


r = agent(fp, model_user_moves).run("click next twice")
check("moving the mouse hands control back",
      r["state"] == "stopped" and "mouse" in r["message"] and len(fp.log) == 1)

fp = FakePlatform()
r = agent(fp, lambda p, i: '{"action":"key","keys":"tab"}').run("loop forever")
check("step limit ends a runaway task", r["state"] == "failed" and len(fp.log) == D.MAX_STEPS)

fp = FakePlatform()
r = agent(fp, lambda p, i: "I'm not sure what to do").run("x")
check("junk replies give up after 3", r["state"] == "failed" and fp.log == [])

fp = FakePlatform()
r = agent(fp, lambda p, i: "NO_VISION_KEY").run("x")
check("no vision key → clear failure", r["state"] == "failed" and "API key" in r["message"])

r = D.DesktopAgent(platform_factory=lambda: (_ for _ in ()).throw(ImportError("No module named 'pyautogui'")),
                   model=scripted(), sleep=lambda s: None).run("x")
check("no pyautogui → install hint", r["state"] == "failed" and "pip install" in r["message"])


print("\n[one task at a time]")
gate = threading.Event()
fp = FakePlatform()


def slow_model(prompt, img):
    gate.wait(2)
    return '{"action":"done","message":"ok"}'


a = agent(fp, slow_model)
ok1, _ = a.start("first")
ok2, msg2 = a.start("second")
check("a second task is refused while busy", ok1 and not ok2 and "already" in msg2)
gate.set()
a._thread.join(2)
check("empty goal is refused", a.start("   ")[0] is False)


print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
