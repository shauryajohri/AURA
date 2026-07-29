# core/quest_verify.py
"""
Screenshot verification for `proof` quests.

Some commitments leave evidence on screen. "LeetCode 2 questions" is either
done or it isn't, and the page says which — so AURA looks instead of taking
your word for it. Others ("exercise") leave no trace a computer can read, and
pretending to verify those would be theatre; those are `manual` and you tick
them yourself.

Flow:
    capture the screen  →  ask a vision model  →  parse a strict verdict
                                                   ↓
                          PASS → complete the quest
                          FAIL → say what was actually visible, stay open

Two failure modes are kept strictly apart, because conflating them would mean
rejecting real work over an API hiccup:

    "I looked and it isn't done"      → verdict fail, quest stays open
    "I couldn't look at all"          → error, quest untouched, say so plainly

Nothing here raises. A verification feature that crashes the quest board is
worse than one that occasionally says "ask me again".
"""

from __future__ import annotations

import base64
import io
import re
from typing import Any

from memory import store

# Keep the image small enough to send quickly but readable enough that a
# problem title or an "Accepted" badge survives.
MAX_WIDTH = 1400
JPEG_QUALITY = 72

_SYSTEM = (
    "You verify whether a screenshot shows a task as COMPLETED. "
    "You are strict and literal: report only what is actually visible. "
    "Never assume, never give the benefit of the doubt, and never invent "
    "detail that isn't in the image."
)

_PROMPT = """Look at this screenshot and decide whether this task is done.

TASK: {title}
{count_line}
Answer in EXACTLY this format, nothing else:

VERDICT: PASS or FAIL
EVIDENCE: one sentence describing what you can literally see that supports it

Rules:
- PASS only if the screenshot clearly shows the task completed.
- If it shows partial progress, that is FAIL — say how much you can see.
- If the screenshot is unrelated to the task, that is FAIL.
- If the image is too blurry or cluttered to tell, that is FAIL.
"""


def _capture_jpeg_b64() -> tuple[str | None, str]:
    """Grab the screen as base64 JPEG. Returns (b64, error)."""
    try:
        from modules.screen_reader import take_screenshot
    except Exception as e:  # noqa: BLE001
        return None, f"screen capture unavailable: {e}"
    try:
        img = take_screenshot()
        if img is None:
            return None, "screen capture returned nothing (mss/Pillow missing?)"
        # Downscale wide screens — a 4K grab is slow to upload and no more
        # legible once the model has resized it anyway.
        if getattr(img, "width", 0) > MAX_WIDTH:
            ratio = MAX_WIDTH / float(img.width)
            img = img.resize((MAX_WIDTH, max(1, int(img.height * ratio))))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=JPEG_QUALITY)
        return base64.b64encode(buf.getvalue()).decode("ascii"), ""
    except Exception as e:  # noqa: BLE001
        return None, f"could not capture the screen: {e}"


_VERDICT_RE = re.compile(r"VERDICT\s*:\s*(PASS|FAIL)", re.IGNORECASE)
_EVIDENCE_RE = re.compile(r"EVIDENCE\s*:\s*(.+)", re.IGNORECASE)


def parse_verdict(raw: str) -> dict[str, Any]:
    """Read the model's answer into {passed, evidence, parsed}.

    `parsed=False` means the reply didn't follow the format. That is treated
    as NOT verified — a model rambling instead of answering is not evidence
    that the work is done.
    """
    text = (raw or "").strip()
    if not text:
        return {"passed": False, "evidence": "", "parsed": False}

    m = _VERDICT_RE.search(text)
    ev = _EVIDENCE_RE.search(text)
    evidence = (ev.group(1).strip() if ev else "").strip()
    if not evidence:
        # No EVIDENCE line — use the first sentence that isn't the verdict.
        for line in text.splitlines():
            line = line.strip()
            if line and not _VERDICT_RE.search(line):
                evidence = line
                break
    evidence = re.sub(r"\s+", " ", evidence)[:240]

    if not m:
        # No verdict line at all. Fall back to a plain reading, but only
        # accept an unambiguous yes.
        low = text.lower()
        if low.startswith("pass") or "clearly shows" in low:
            return {"passed": True, "evidence": evidence, "parsed": False}
        return {"passed": False, "evidence": evidence, "parsed": False}

    return {
        "passed": m.group(1).upper() == "PASS",
        "evidence": evidence,
        "parsed": True,
    }


def verify_quest(quest_id: int, image_b64: str | None = None) -> dict[str, Any]:
    """Verify one proof quest against a screenshot.

    Returns a dict the UI can render directly:
        {ok, verdict, evidence, error, completed, title}
    `ok=False` means AURA could not look (no key, rate limit, capture failed) —
    distinct from `verdict="fail"`, which means she looked and it wasn't done.
    """
    board = store.get_quest_board()
    quest = next((q for q in board["quests"] if q["id"] == quest_id), None)
    if quest is None:
        return {"ok": False, "error": "no such quest", "verdict": "",
                "evidence": "", "completed": False, "title": ""}

    title = quest["title"]
    if quest.get("kind") != "proof":
        return {"ok": False, "title": title, "verdict": "", "evidence": "",
                "completed": bool(quest["completed"]),
                "error": f"'{title}' isn't a screenshot-verified quest — "
                         + ("it's tracked by time." if quest.get("kind") == "time"
                            else "just mark it done yourself.")}

    from core.ai_router import call_vision, vision_available
    if not vision_available():
        return {"ok": False, "title": title, "verdict": "", "evidence": "",
                "completed": False,
                "error": "No OpenRouter key for the vision model — set "
                         "OPENROUTER_KEY_CHAT (or OPENROUTER_API_KEY) in .env."}

    if not image_b64:
        image_b64, err = _capture_jpeg_b64()
        if not image_b64:
            return {"ok": False, "title": title, "verdict": "", "evidence": "",
                    "completed": False, "error": err}

    count = int(quest.get("target_count") or 0)
    count_line = (f"It requires {count} of them to be finished."
                  if count else "")
    raw = call_vision(
        _PROMPT.format(title=title, count_line=count_line),
        image_b64,
        system=_SYSTEM,
    )

    if raw in ("RATE_LIMIT", "CONNECTION_ERROR", "NO_VISION_KEY"):
        friendly = {
            "RATE_LIMIT": "Vision model is rate-limited right now — try again "
                          "in a minute.",
            "CONNECTION_ERROR": "Couldn't reach the vision model.",
            "NO_VISION_KEY": "No API key configured for the vision model.",
        }[raw]
        # Deliberately NOT a fail: AURA never got to look, so the quest is
        # untouched and you aren't penalised for her outage.
        return {"ok": False, "title": title, "verdict": "", "evidence": "",
                "completed": False, "error": friendly}

    result = parse_verdict(raw)
    passed = result["passed"]

    if passed:
        try:
            # Record it in the same ledger auto-detection writes to, so the
            # day's history shows HOW each item was credited.
            store.record_quest_item(
                quest_id, f"screenshot:{result['evidence'][:80] or 'verified'}",
                source="screenshot", day=board["day"])
            store.complete_quest(quest_id, day=board["day"])
            store.update_quest(quest_id, proof_note=result["evidence"][:240])
        except Exception as e:  # noqa: BLE001
            print(f"[QuestVerify] could not mark complete: {e}")
    else:
        try:
            store.update_quest(quest_id, proof_note=result["evidence"][:240])
        except Exception:  # noqa: BLE001
            pass

    return {
        "ok": True,
        "title": title,
        "verdict": "pass" if passed else "fail",
        "evidence": result["evidence"],
        "parsed": result["parsed"],
        "completed": passed,
        "error": "",
    }


def spoken_result(res: dict[str, Any]) -> str:
    """One line for chat/voice."""
    if not res.get("ok"):
        return res.get("error") or "Couldn't check that one."
    if res.get("verdict") == "pass":
        return f"{res['title']} — verified. {res.get('evidence', '')}".strip()
    ev = res.get("evidence") or "I couldn't see it finished."
    return f"Not yet on {res['title']}. {ev} Send another when it's done."
