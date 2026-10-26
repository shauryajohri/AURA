"""
Tests for AURA's voice — how she sounds, not what she says.

Covered here:
  1. two voices, Ava and Sonia, each with its own fixed tuning
  2. the saved pick wins; a pick from the old roster falls back to the default
  3. one steady tuning per voice: the mood of a line never shifts the pitch
  4. text is cleaned for the ear (decimals, questions, emoji, snake_case)
  5. replies are spoken in whole sentences, not comma-sized fragments
  6. "bye" answers with a goodbye, not the action name

Runs on a THROWAWAY DB and a fake edge-tts. No network, never touches real
memory.

Run:  PYTHONPATH=. python test_voice.py
"""

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))   # csv_handler reads config/ relative to cwd

_TMP = tempfile.mkdtemp(prefix="aura_voice_")
os.environ["AURA_TEST_DB"] = os.path.join(_TMP, "test.db")

import memory.store as mstore  # noqa: E402
mstore.DB_PATH = os.environ["AURA_TEST_DB"]
mstore.init_db()

from modules import voice_output as vo  # noqa: E402
from modules.speech_planner import plan  # noqa: E402

AVA = "en-US-AvaMultilingualNeural"
SONIA = "en-GB-SoniaNeural"

passed = failed = 0


def check(label, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {label}")
    else:
        failed += 1
        print(f"  ✗ {label}")


def pick(voice_id):
    mstore.set_settings({"voice.name": voice_id})
    vo._settings_cache = (0.0, {})


print("\n[the roster]")
check("exactly Ava and Sonia", [v["id"] for v in vo.VOICES] == [AVA, SONIA])
check("Ava is the fallback", vo.FALLBACK_VOICE == AVA)
check("each voice has its own tuning",
      vo.prosody(AVA) != vo.prosody(SONIA)
      and all(v["rate"].endswith("%") and v["pitch"].endswith("Hz") for v in vo.VOICES))
check("a voice outside the roster speaks stock",
      vo.prosody("en-US-JennyNeural") == {"rate": "+0%", "pitch": "+0Hz"})


print("\n[which voice she uses]")
pick("")
check("nothing saved → the default", vo.resolve_voice() == vo.DEFAULT_VOICE)
pick(SONIA)
check("saved Sonia → Sonia", vo.resolve_voice() == SONIA)
pick(AVA)
check("saved Ava → Ava", vo.resolve_voice() == AVA)
pick("en-US-JennyNeural")
check("a pick from the old roster → the default", vo.resolve_voice() == vo.DEFAULT_VOICE)
pick("   ")
check("blank → the default", vo.resolve_voice() == vo.DEFAULT_VOICE)


print("\n[one steady tuning per voice]")
calls = []


class _FakeCommunicate:
    def __init__(self, text, voice, rate, pitch):
        calls.append({"text": text, "voice": voice, "rate": rate, "pitch": pitch})

    async def save(self, path):
        pass


_real = vo.edge_tts
vo.edge_tts = type("fake_edge_tts", (), {"Communicate": _FakeCommunicate})
try:
    pick(SONIA)
    for line in ("Build failed with a crash.", "Great, all done and saved!", "bruh."):
        asyncio.run(vo._generate(line, os.path.join(_TMP, "x.mp3")))
    asyncio.run(vo._generate("preview", os.path.join(_TMP, "y.mp3"), voice=AVA))
finally:
    vo.edge_tts = _real
check("speaks with the chosen voice", all(c["voice"] == SONIA for c in calls[:3]))
check("the same rate and pitch whatever the mood",
      len({(c["rate"], c["pitch"]) for c in calls[:3]}) == 1)
check("that tuning is the voice's own (slider at its default)",
      (calls[0]["rate"], calls[0]["pitch"]) == (vo.prosody(SONIA)["rate"], vo.prosody(SONIA)["pitch"]))
check("a preview uses the previewed voice's tuning",
      calls[3]["voice"] == AVA and calls[3]["pitch"] == vo.prosody(AVA)["pitch"])


print("\n[cleaned for the ear]")
check("decimals stay whole", vo.clean_text("Python 3.12 is out.") == "Python 3.12 is out.")
check("questions keep their question mark", vo.clean_text("Done already?") == "Done already?")
check("speak() still caps at two sentences",
      vo.clean_text("One. Two? Three!") == "One. Two?")
check("a planned chunk keeps every sentence",
      vo.clean_text("One. Two? Three!", max_sentences=None) == "One. Two? Three!")
check("emoji aren't read out", vo.clean_text("Nice work \U0001F60F") == "Nice work.")
check("snake_case is read as words", vo.clean_text("call my_func") == "call my func.")
check("a clause ending on a comma isn't closed with a full stop",
      vo.clean_text("and if that fails,") == "and if that fails,")


print("\n[whole sentences, not fragments]")
reply = ("Paste it, and tell me your base case first, because I already have "
         "a suspicion and it's not flattering.")
chunks = plan(reply, "CHAT")
check("a normal sentence is one chunk", len(chunks) == 1 and chunks[0].text == reply)
chunks = plan("Yep. That's the off-by-one in your second loop.", "CHAT")
check("a one-word sentence rides with the next", len(chunks) == 1)
long = ("Okay so the thing is, when you call fetch inside the loop without awaiting it, "
        "every request fires at once, the server rate-limits you after the first twenty, "
        "and the rest come back as 429s which your catch block silently swallows, "
        "so it looks like nothing happened at all. Await them in batches.")
chunks = plan(long, "CHAT")
check("a very long sentence breaks at a comma", 2 <= len(chunks) <= 4
      and all(c.text.endswith((",", ".", "!", "?")) for c in chunks))
check("nothing is lost or reordered",
      " ".join(c.text for c in chunks).split() == long.split())


print("\n[quick responses]")
from modules.csv_handler import check_csv  # noqa: E402
bye = check_csv("bye")
check("bye says goodbye, not EXIT", bye and bye.upper() != "EXIT")


print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
