"""
AURA voice preview / picker
===========================

edge-tts voices are SERVER-SIDE — there is nothing to download and no model
files to manage. Changing AURA's voice is just changing a name string. This
script lets you hear the realistic candidates in AURA's own words first, then
sets the winner for you.

Run it from the AURA folder with the venv active:

    python tools/voice_preview.py              # hear every candidate
    python tools/voice_preview.py --female     # only the female voices
    python tools/voice_preview.py --keep       # keep the .mp3 files
    python tools/voice_preview.py --set en-US-AvaMultilingualNeural

`--set` writes AURA_TTS_VOICE into your .env. voice_output.py reads it at
startup, so you can change AURA's voice any time without editing code —
just re-run with a different name and restart the server.

Requires: edge-tts and pygame (both already in AURA's requirements) and an
internet connection.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
OUT_DIR = ROOT / "voice_samples"

# ── Candidates ────────────────────────────────────────────────────────────
# The roster lives in modules/voice_output.VOICES — the SAME list the in-app
# picker (Settings → Voice) and the speaking code use. Imported rather than
# copied so this tool can never offer a voice the app doesn't know about.
sys.path.insert(0, str(ROOT))
try:
    from modules.voice_output import VOICES as _VOICES
    CANDIDATES: list[tuple[str, str, str]] = [
        (v["id"], v["gender"], f"{v['character']} ({v['accent']})") for v in _VOICES
    ]
except Exception as _e:  # noqa: BLE001
    # Standalone fallback: the tool still works if it's copied out of the repo.
    print(f"  (couldn't import the app's roster: {_e} — using the built-in list)")
    CANDIDATES = [
        ("en-US-AvaMultilingualNeural",    "female", "Bright, expressive, lively"),
        ("en-US-EmmaMultilingualNeural",   "female", "Warm and even"),
        ("en-GB-SoniaNeural",              "female", "Composed, understated (British)"),
        ("en-US-JennyNeural",              "female", "Friendly, familiar, neutral"),
        ("en-US-AndrewMultilingualNeural", "male",   "Relaxed, conversational"),
        ("en-US-BrianMultilingualNeural",  "male",   "Casual, easy pacing"),
        ("en-GB-RyanNeural",               "male",   "Least robotic (British)"),
        ("en-US-AriaNeural",               "female", "AURA's old voice — for comparison"),
    ]

# AURA's actual register, so you judge the voice doing the job it will do —
# a neutral "the quick brown fox" tells you nothing about how a tease lands.
SAMPLE_LINES = [
    "Hey. You've been on that same function for forty minutes — want me to take a look?",
    "It's two in the morning, mate. Whatever this is, it'll still be broken tomorrow.",
    "Build's green. Nineteen tests, all passing. Go get a coffee.",
]


def _fail(msg: str) -> None:
    print(f"\n  !! {msg}")
    sys.exit(1)


# ── Setting the voice ─────────────────────────────────────────────────────
def set_voice(voice: str) -> None:
    """Write AURA_TTS_VOICE=<voice> into .env, replacing any existing line."""
    known = {v for v, _, _ in CANDIDATES}
    if voice not in known:
        print(f"  note: '{voice}' isn't in the candidate list — setting it anyway.")
        print("        (any valid edge-tts voice name works)")

    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    out, replaced = [], False
    for line in lines:
        if line.strip().startswith("AURA_TTS_VOICE="):
            out.append(f"AURA_TTS_VOICE={voice}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        if out and out[-1].strip():
            out.append("")
        out.append("# AURA's speaking voice (any edge-tts voice name).")
        out.append(f"AURA_TTS_VOICE={voice}")

    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"\n  Set AURA_TTS_VOICE={voice} in .env")
    print("  Restart server.py for it to take effect.\n")


# ── Preview ───────────────────────────────────────────────────────────────
async def _render(voice: str, text: str, path: Path) -> None:
    import edge_tts
    await edge_tts.Communicate(text, voice=voice).save(str(path))


def _play(path: Path) -> None:
    try:
        import pygame
    except ModuleNotFoundError:
        print("     (pygame not installed — file saved, not played)")
        return
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(50)
        pygame.mixer.music.unload()
    except Exception as e:  # noqa: BLE001
        print(f"     (playback failed: {e} — the file is still on disk)")


def preview(only: str | None, keep: bool, line_index: int) -> None:
    try:
        import edge_tts  # noqa: F401
    except ModuleNotFoundError:
        _fail("edge-tts isn't installed. Run:  pip install edge-tts")

    picks = [c for c in CANDIDATES if only is None or c[1] == only]
    text = SAMPLE_LINES[line_index % len(SAMPLE_LINES)]

    OUT_DIR.mkdir(exist_ok=True)
    print("\n" + "=" * 68)
    print("  AURA voice preview")
    print("=" * 68)
    print(f'\n  Line: "{text}"\n')

    made: list[Path] = []
    for i, (voice, gender, why) in enumerate(picks, 1):
        print(f"  [{i}/{len(picks)}] {voice}  ({gender})")
        print(f"        {why}")
        path = OUT_DIR / f"{voice}.mp3"
        try:
            asyncio.run(_render(voice, text, path))
        except Exception as e:  # noqa: BLE001
            print(f"        !! could not render: {e}\n")
            continue
        made.append(path)
        _play(path)
        time.sleep(0.35)   # a beat between voices so they don't blur together
        print()

    print("=" * 68)
    if keep:
        print(f"  Samples kept in: {OUT_DIR}")
        print("  Replay any of them in your file manager to compare again.")
    else:
        for p in made:
            try:
                p.unlink()
            except OSError:
                pass
        try:
            OUT_DIR.rmdir()
        except OSError:
            pass
        print("  Samples deleted. Re-run with --keep to hold on to them.")

    print("\n  Heard one you like? Lock it in with:")
    print("      python tools/voice_preview.py --set <voice-name>")
    print("  e.g. python tools/voice_preview.py --set en-US-AvaMultilingualNeural\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Preview and set AURA's speaking voice.")
    ap.add_argument("--set", metavar="VOICE", help="write this voice into .env and exit")
    ap.add_argument("--female", action="store_true", help="preview female voices only")
    ap.add_argument("--male", action="store_true", help="preview male voices only")
    ap.add_argument("--keep", action="store_true", help="keep the sample .mp3 files")
    ap.add_argument("--line", type=int, default=0,
                    help="which sample line to speak (0-2)")
    args = ap.parse_args()

    if args.set:
        set_voice(args.set)
        return

    only = "female" if args.female else ("male" if args.male else None)
    preview(only, args.keep, args.line)


if __name__ == "__main__":
    main()
