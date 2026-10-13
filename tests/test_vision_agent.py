"""
Offline test for the vision loop: grid maths, pointing at elements and cells,
decision parsing, the loop with a scripted fake model, and vision jobs running
through remote_control in the background (approve, cancel, stop).

No display, no network, no tesseract. Screenshots are plain PIL images, OCR
elements are filled in by hand, and actions go to a recorder.

Run:  python -m tests.test_vision_agent
"""

import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from core import actions, remote_control as rc, vision_agent as va  # noqa: E402

rc.LOG_PATH = Path(tempfile.mkdtemp(prefix="aura_vision_test_")) / "log.jsonl"
va.SETTLE_SECONDS = 0

_fails = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'} — {label}")
    if not cond:
        _fails.append(label)


SEND = {"id": 1, "text": "Send", "box": (1700, 1000, 100, 40), "cell": "W13"}
SEARCH = {"id": 2, "text": "Search", "box": (100, 50, 200, 30), "cell": "C1"}


def make_screen(shade=30, elements=None, gui=(1920, 1080)):
    img = Image.new("RGB", (1920, 1080), (shade, shade, shade))
    s = va.build_screen(img, gui, window="Test Window")
    s.elements = list(elements if elements is not None else [SEND, SEARCH])
    return s


class Ctx:
    """Records what the loop asks for; answers questions from a script."""

    def __init__(self, answers=(), stop_after=None):
        self.answers = list(answers)
        self.questions = []
        self.records = []
        self.shown = 0
        self.stop_after = stop_after

    def check(self):
        if self.stop_after is not None and self.shown >= self.stop_after:
            return "laptop locked"
        return None

    def ask(self, q):
        self.questions.append(q)
        return self.answers.pop(0) if self.answers else False

    def record(self, desc, ok, result):
        self.records.append((desc, ok, result))

    def show(self, screen):
        self.shown += 1


def scripted(*replies):
    """Fake vision model: returns the replies in order, then FAIL."""
    queue = list(replies)
    seen = []

    def fn(prompt, image_b64, system="", max_tokens=0):
        seen.append(prompt)
        return queue.pop(0) if queue else "FAIL: script ran out"
    fn.seen = seen
    return fn


def changing_screens(elements=None):
    """Each capture looks different, so the stuck check never fires."""
    n = {"i": 0}

    def fn():
        n["i"] += 1
        return make_screen(shade=(n["i"] * 37) % 256, elements=elements)
    return fn


acted = []


def act(name, args):
    acted.append((name, args))
    return True, f"{name} ok"


def run(goal, ctx, replies, capture=None):
    acted.clear()
    return va.run(goal, ctx, capture_fn=capture or changing_screens(),
                  vision_fn=scripted(*replies), act_fn=act)


print("grid")
check(va.grid_rows(1920, 1080) == 14, "1920×1080 gives 14 rows")
check(va.cell_of(0, 0, 1920, 1080, 14) == "A1", "top-left is A1")
check(va.cell_of(1919, 1079, 1920, 1080, 14) == "X14", "bottom-right is X14")
check(va.cell_of(*va.cell_center("m7", 1920, 1080, 14), 1920, 1080, 14) == "M7",
      "cell centre maps back to the same cell (any case)")
for bad in ("Z1", "A0", "A15", "hello", ""):
    try:
        va.cell_center(bad, 1920, 1080, 14)
        check(False, f"{bad!r} is rejected")
    except actions.ActionError:
        check(True, f"{bad!r} is rejected")

print("screen")
s = make_screen()
check(bool(s.model_jpeg_b64), "model image built")
check(s.phone_jpeg[:2] == b"\xff\xd8", "phone image is a JPEG")
check(s.fingerprint == make_screen().fingerprint, "same picture, same fingerprint")
check(s.fingerprint != make_screen(shade=220).fingerprint, "different picture, different fingerprint")
check(s.window == "Test Window", "active window carried through")

print("pointing")
check(va.resolve_point({"element": 1}, make_screen()) == (1750, 1020), "element → centre of its box")
check(va.resolve_point({"element": "1"}, make_screen()) == (1750, 1020), "element id as a string works")
half = make_screen(gui=(960, 540))   # e.g. 200% display scaling
check(va.resolve_point({"element": 1}, half) == (875, 510), "scaled to pyautogui's coordinates")
check(va.resolve_point({"cell": "A1"}, make_screen()) == (40, 39), "cell → its centre")
for bad in ({"element": 99}, {"element": "x"}, {}, {"cell": "Z9"}):
    try:
        va.resolve_point(bad, make_screen())
        check(False, f"{bad} is rejected")
    except actions.ActionError:
        check(True, f"{bad} is rejected")

print("parsing")
check(va.parse_decision('DO: click {"element": 3}') == ("do", "click", {"element": 3}), "DO line")
check(va.parse_decision("Looking at it...\n**DONE: Sent it.**") == ("done", "Sent it.", {}),
      "DONE below a preamble, markdown stripped")
check(va.parse_decision("ASK: Send this?")[0] == "ask", "ASK line")
check(va.parse_decision("FAIL: login wall")[0] == "fail", "FAIL line")
check(va.parse_decision('DO: press {broken json')[1:] == ("press", {}), "bad JSON → no args")
check(va.parse_decision("I think we should click it") is None, "no decision line → None")

print("loop: happy path")
ctx = Ctx()
status, reply = run("send it", ctx, ['DO: click {"element": 1}', "DONE: Sent."])
check((status, reply) == ("done", "Sent."), "finishes on DONE")
check(acted == [("click", {"x": 1750, "y": 1020, "button": "left", "clicks": 1})],
      "clicked the element's real coordinates")
check(ctx.records and ctx.records[0][0] == "Click “Send”", "step recorded with the element's text")
check(ctx.shown == 2, "phone got a screenshot each round")

print("loop: model output it can't use")
ctx = Ctx()
fake = scripted("hmm, not sure", 'DO: teleport {}', 'DO: click {"element": 42}', "DONE: ok")
acted.clear()
status, _ = va.run("x", ctx, capture_fn=changing_screens(), vision_fn=fake, act_fn=act)
check(status == "done" and not acted, "junk, unknown action and a missing element run nothing")
check("not an action you have" in fake.seen[2] and "no element #42" in fake.seen[3],
      "each problem is fed back to the model")

print("loop: questions")
ctx = Ctx(answers=[True])
status, _ = run("post it", ctx, ["ASK: Post this?", 'DO: press {"key": "enter"}', "DONE: Posted."])
check(status == "done" and ctx.questions == ["Post this?"], "ASK approved → carries on")
check(acted == [("press", {"key": "enter"})], "the step after the approval ran")

ctx = Ctx(answers=[False])
status, _ = run("post it", ctx, ["ASK: Post this?", 'DO: press {"key": "enter"}'])
check(status == "cancelled" and not acted, "ASK denied → stops, nothing runs")

ctx = Ctx(answers=[False])
status, _ = run("close it", ctx, ["DO: close_window {}"])
check(status == "cancelled" and len(ctx.questions) == 1 and not acted,
      "risky action asks even if the model didn't")

ctx = Ctx(answers=[False])
status, _ = run("quit", ctx, ['DO: hotkey {"keys": ["alt", "f4"]}'])
check(status == "cancelled" and not acted, "alt+f4 asks too")

print("loop: stopping")
ctx = Ctx()
same = lambda: make_screen()  # noqa: E731
status, reply = run("x", ctx, ['DO: press {"key": "tab"}'] * 10, capture=same)
check(status == "failed" and "stuck" in reply, "screen that never changes → stuck")
check(len(acted) == va.MAX_STUCK, "stopped after MAX_STUCK steps that did nothing")

ctx = Ctx(stop_after=1)
status, reply = run("x", ctx, ['DO: press {"key": "tab"}'] * 5)
check(status == "stopped" and reply == "laptop locked" and len(acted) == 1,
      "laptop going inactive stops it before the next step")

for sentinel, word in (("RATE_LIMIT", "rate-limited"), ("NO_VISION_KEY", "key"),
                       ("CONNECTION_ERROR", "couldn't reach")):
    status, reply = run("x", Ctx(), [sentinel])
    check(status == "failed" and word in reply.lower(), f"{sentinel} → clear failure")

os.environ["AURA_VISION_MAX_STEPS"] = "3"
status, reply = run("x", Ctx(), ['DO: press {"key": "tab"}'] * 10)
check(status == "failed" and "ran out of steps (3)" in reply and len(acted) == 3, "step budget respected")
os.environ.pop("AURA_VISION_MAX_STEPS")

print("available()")
os.environ["AURA_REMOTE_VISION"] = "off"
check(va.available()[0] is False, "AURA_REMOTE_VISION=off turns it off")
os.environ.pop("AURA_REMOTE_VISION")

print("background jobs through remote_control")
actions.desktop_available = lambda: (True, "")
rc._session_locked = lambda: False
rc._idle_seconds = lambda: 5.0
rc.vision_agent.available = lambda: (True, "")
_real_run = va.run
script = []


def fake_run(goal, ctx):
    return _real_run(goal, ctx, capture_fn=changing_screens(),
                     vision_fn=scripted(*script), act_fn=act)


rc.vision_agent.run = fake_run


def wait_for(job, statuses, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if rc.get_job(job.id).status in statuses:
            return rc.get_job(job.id)
        time.sleep(0.02)
    return rc.get_job(job.id)


acted.clear()
script[:] = ['DO: click {"element": 2}', "DONE: Found it."]
job = rc.submit("find the search box and click it")
check(job.mode == "vision" and job.status == "running", "non-trivial command → vision job, returns at once")
job = wait_for(job, {"done", "failed"})
check(job.status == "done" and job.reply == "Found it.", "job finishes in the background")
check(job.results and job.results[0]["step"] == "Click “Search”", "steps show up on the job")
check(job.screen_version >= 1 and rc.latest_screen(job.id)[:2] == b"\xff\xd8",
      "the phone can fetch what AURA saw")

actions.ACTIONS["open_app"]["fn"] = lambda **kw: "opened"   # never launch a real app
acted.clear()
job = rc.submit("open spotify")
check(job.mode == "plan" and job.status == "done", "simple command still skips the vision loop")

acted.clear()
script[:] = ["ASK: Send the message?", 'DO: press {"key": "enter"}', "DONE: Sent."]
job = wait_for(rc.submit("reply ok to the last message"), {"pending"})
check(job.status == "pending" and job.question == "Send the message?", "question surfaces as pending")
rc.approve(job.id)
job = wait_for(job, {"done", "failed", "cancelled"})
check(job.status == "done" and acted == [("press", {"key": "enter"})], "approved → finishes")

acted.clear()
script[:] = ["ASK: Send the message?", 'DO: press {"key": "enter"}']
job = wait_for(rc.submit("reply ok to the last message"), {"pending"})
rc.cancel(job.id)
job = wait_for(job, {"done", "failed", "cancelled"})
check(job.status == "cancelled" and not acted, "cancelled → nothing sent")

acted.clear()
script[:] = ["ASK: Keep going?"]
job = wait_for(rc.submit("do a long thing"), {"pending"})
rc.stop()
job = wait_for(job, {"done", "failed", "cancelled", "stopped"})
check(job.status in {"cancelled", "stopped"} and not acted, "Stop while waiting on a question ends the job")

script[:] = ["ASK: Hold on?"]
first = wait_for(rc.submit("first long thing"), {"pending"})
second = rc.submit("second thing please")
check(second.status == "declined" and "still doing" in second.reply, "one job at a time")
rc.cancel(first.id)
wait_for(first, {"cancelled"})

os.environ["AURA_REMOTE_CONFIRM"] = "all"
acted.clear()
script[:] = ["DONE: ok"]
job = rc.submit("tidy my desktop")
check(job.status == "pending" and "start" in job.question.lower(), "confirm=all asks before starting")
rc.approve(job.id)
check(wait_for(job, {"done"}).status == "done", "…and runs once approved")
os.environ.pop("AURA_REMOTE_CONFIRM")

rc._session_locked = lambda: True
check(rc.submit("do something on screen").status == "declined", "locked laptop still declines first")

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    sys.exit(1)
print("all passed")
