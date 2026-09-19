"""
Render the website's spoken lines in AURA's web voice.

Every clip is rendered from the words the visitor reads, so the audio can
never drift from the page:

  hero-1..3    the hero bands in website/index.html (headline + subline)
  tour-<id>    the tour LINES in website/assets/site.js

Text goes through web_api._speakable, the same speech prep the live /tts
endpoint uses, in web_api.VOICE, the same voice.

    python tools/render_site_voice.py              # every clip, stale ones removed
    python tools/render_site_voice.py tour-code    # just the named clips
"""

from __future__ import annotations

import asyncio
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SITE = ROOT / "website"
OUT = SITE / "assets" / "voice"


def hero_lines() -> dict[str, str]:
    page = (SITE / "index.html").read_text(encoding="utf-8")
    lines = {}
    for m in re.finditer(r'data-voice="(hero-\d+)"', page):
        rest = page[m.end():]
        parts = [re.search(r"<h[12][^>]*>(.*?)</h[12]>", rest, re.S),
                 re.search(r'<p class="sub">(.*?)</p>', rest, re.S)]
        lines[m.group(1)] = " ".join(
            html.unescape(re.sub(r"<[^>]+>", "", p.group(1))).strip() for p in parts if p)
    return lines


def tour_lines() -> dict[str, str]:
    js = (SITE / "assets" / "site.js").read_text(encoding="utf-8")
    block = js[js.index("const LINES = ["):]
    block = block[:block.index("];")]
    return {f"tour-{m.group(1)}": json.loads(m.group(2))
            for m in re.finditer(r"\{\s*id:\s*'([\w-]+)',\s*text:\s*(\"(?:[^\"\\]|\\.)*\")", block)}


async def render(names: list[str]) -> None:
    import edge_tts
    from web_api import VOICE, _speakable

    lines = {**hero_lines(), **tour_lines()}
    unknown = [n for n in names if n not in lines]
    if unknown:
        raise SystemExit(f"unknown clip: {', '.join(unknown)}")
    OUT.mkdir(parents=True, exist_ok=True)
    for key, text in lines.items():
        if names and key not in names:
            continue
        spoken = _speakable(text, max_sentences=12, max_chars=2000)
        await edge_tts.Communicate(spoken, voice=VOICE).save(str(OUT / f"{key}.mp3"))
        print(f"{key:15s} {spoken}")
    if not names:
        for old in OUT.glob("*.mp3"):
            if old.stem not in lines:
                old.unlink()
                print(f"removed stale {old.name}")


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    asyncio.run(render(sys.argv[1:]))
