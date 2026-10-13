"""
Tests for the "open X" guard in modules/command_handler.

The live bug, 2026-07-31 12:32 — mid-conversation about a project:

    shaurya: yes so lets start with wasabikiri upgrade disscussion.
    AURA:    I couldn't find with wasabikiri upgrade disscussion on your
             system. Try saying the full app name once.

The trigger test was `"start " in q` — anywhere in the message — so an ordinary
sentence using the word "start" was read as a command to launch an app called
"with wasabikiri upgrade disscussion".

Three guards, all needed: the verb must OPEN the message, what follows can't
start with a preposition, and an app name is short.

Run:  PYTHONPATH=. python test_launcher_guard.py
"""

from modules.command_handler import _launch_target

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {label}")
    else:
        failed += 1
        print(f"  ✗ {label}")


print("\n[real launch commands still work]")
for msg, want in [
    ("open chrome", "chrome"),
    ("open vs code", "vs code"),
    ("launch spotify", "spotify"),
    ("please open notepad", "notepad"),
    ("can you open discord", "discord"),
    ("hey aura, open steam", "steam"),
    ("run docker desktop", "docker desktop"),
    ("open chrome?", "chrome"),
]:
    got = _launch_target(msg)
    check(f"{msg!r} → {want!r}", got == want)


print("\n[conversation is not a command]")
for msg in [
    # The exact message from the transcript.
    "yes so lets start with wasabikiri upgrade disscussion.",
    "lets start with the dashboard fix",
    "start with the smaller file",
    "i'll start working on it now",
    "can we start the discussion about the portfolio",
    "run through the plan with me",
    "open to any ideas here",
    "launch day is next week so what should i prep",
    "should i start from scratch or refactor",
]:
    check(f"not a launch: {msg!r}", _launch_target(msg) is None)


print("\n[an app name is short]")
check("a whole sentence is never an app",
      _launch_target("open the file i was editing yesterday afternoon") is None)
check("four words is still plausible",
      _launch_target("open android studio dev channel") == "android studio dev channel")


print("\n" + "=" * 40)
print(f"{passed} passed, {failed} failed")
print("=" * 40)
