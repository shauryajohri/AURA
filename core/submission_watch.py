# core/submission_watch.py
"""
Notice when a coding-platform submission is ACCEPTED, and which problem it was.

The point: "leetcode 2 questions" shouldn't need a screenshot at all if AURA
is already watching the screen. She sees the green Accepted, works out which
problem it belongs to, and ticks it off. The screenshot path stays as the
fallback for when this misses.

Two hard requirements, and they pull in opposite directions:

  1. NEVER count something that didn't happen. A false positive silently
     completes a quest the user didn't earn, which destroys the point of
     verification. So acceptance needs BOTH a platform signal and an
     acceptance signal — the bare word "Accepted" is worthless on its own
     (it appears in cookie banners, terms pages, and any article about
     accepting a job offer).

  2. NEVER count the same solve twice. The watcher samples every 30 seconds
     and that Accepted banner sits there until you navigate away, so an
     unguarded detector would credit one problem a dozen times. Each
     detection carries a problem IDENTITY, and the store's UNIQUE index does
     the deduplication.

Detection is pattern-based on the window title plus visible text. No model
call: this runs on every watch tick, and it needs to be free and instant.
"""

from __future__ import annotations

import re
from typing import Any

# platform id → (title/url markers, acceptance patterns)
PLATFORMS: dict[str, dict] = {
    "leetcode": {
        "label": "LeetCode",
        "markers": ("leetcode",),
        "accept": (
            r"\baccepted\b",
            r"\bruntime\s*[:\s]\s*\d+\s*ms\b",
            r"\bbeats\s+\d+(?:\.\d+)?%",
            r"\bsolution accepted\b",
        ),
        # "Two Sum II - Input Array Is Sorted - LeetCode"
        "title": r"^\s*(?:\d+\.\s*)?(?P<name>.+?)\s*[-–|]\s*(?:leetcode|力扣)",
    },
    "codeforces": {
        "label": "Codeforces",
        "markers": ("codeforces",),
        "accept": (r"\baccepted\b", r"\bhappy new year\b", r"\bpretests passed\b"),
        "title": r"^\s*(?:problem\s*)?(?P<name>.+?)\s*[-–|]\s*codeforces",
    },
    "hackerrank": {
        "label": "HackerRank",
        "markers": ("hackerrank",),
        "accept": (r"\bcongratulations\b", r"\byou solved (?:this )?challenge\b",
                   r"\btest cases passed\b", r"\ball tests passed\b"),
        "title": r"^\s*(?P<name>.+?)\s*[-–|]\s*hackerrank",
    },
    "codechef": {
        "label": "CodeChef",
        "markers": ("codechef",),
        "accept": (r"\baccepted\b", r"\bcorrect answer\b"),
        "title": r"^\s*(?P<name>.+?)\s*[-–|]\s*codechef",
    },
    "atcoder": {
        "label": "AtCoder",
        "markers": ("atcoder",),
        "accept": (r"\bac\b\s*[×x]?\s*\d*", r"\ball\s+ac\b", r"\baccepted\b"),
        "title": r"^\s*(?P<name>.+?)\s*[-–|]\s*atcoder",
    },
    "geeksforgeeks": {
        "label": "GeeksforGeeks",
        "markers": ("geeksforgeeks", "practice.geeksforgeeks"),
        "accept": (r"\bproblem solved successfully\b", r"\bcorrect answer\b",
                   r"\ball test cases passed\b"),
        "title": r"^\s*(?P<name>.+?)\s*[-–|]\s*(?:practice\s*)?geeksforgeeks",
    },
    "hackerearth": {
        "label": "HackerEarth",
        "markers": ("hackerearth",),
        "accept": (r"\ball test cases passed\b", r"\baccepted\b"),
        "title": r"^\s*(?P<name>.+?)\s*[-–|]\s*hackerearth",
    },
}

# Contexts where "Accepted" means something else entirely. Checked first —
# a cookie banner must never complete a quest.
_FALSE_FRIENDS = (
    "cookies", "cookie policy", "terms of service", "terms and conditions",
    "privacy policy", "accepted the offer", "accepted a job", "job offer",
    "accepted payment", "we accept", "accepted answer",   # stack overflow!
    "application accepted", "accepted into", "acceptance rate",
)


def _blob(ctx: dict[str, Any]) -> tuple[str, str]:
    title = str(ctx.get("title") or ctx.get("window_title") or "")
    body = str(ctx.get("visible_text") or ctx.get("text") or "")[:6000]
    app = str(ctx.get("app") or "")
    return f"{app} {title}".lower(), body.lower()


def _platform_of(head: str, body: str) -> str | None:
    for pid, meta in PLATFORMS.items():
        if any(m in head for m in meta["markers"]):
            return pid
    # The title may be truncated; fall back to the page text.
    for pid, meta in PLATFORMS.items():
        if any(m in body for m in meta["markers"]):
            return pid
    return None


def _problem_name(ctx: dict[str, Any], pid: str) -> str:
    """Identify the problem, so the same solve is only ever counted once."""
    raw_title = str(ctx.get("title") or ctx.get("window_title") or "").strip()
    pat = PLATFORMS[pid].get("title")
    if pat:
        m = re.search(pat, raw_title, re.IGNORECASE)
        if m:
            name = m.group("name").strip(" -–|·")
            # Strip a browser profile suffix like " - Comet" / " - Google Chrome"
            name = re.sub(r"\s*[-–|]\s*(comet|google chrome|chrome|firefox|"
                          r"edge|brave|arc|safari)\s*$", "", name,
                          flags=re.IGNORECASE).strip()
            if 2 < len(name) < 120:
                return name
    # No usable title — fall back to the whole title so it's at least stable
    # within one page, rather than returning something that collides.
    return raw_title[:120] or "unknown problem"


def detect_acceptance(ctx: dict[str, Any]) -> dict[str, Any] | None:
    """One screen sample → an accepted submission, or None.

    Returns {platform, label, problem, item} where `item` is the dedup key.
    """
    head, body = _blob(ctx)
    if not head.strip() and not body.strip():
        return None

    pid = _platform_of(head, body)
    if not pid:
        return None

    combined = f"{head}\n{body}"
    # Reject before matching: on a page about accepting cookies, "accepted"
    # is not a verdict.
    if any(f in combined for f in _FALSE_FRIENDS):
        return None

    meta = PLATFORMS[pid]
    if not any(re.search(p, combined, re.IGNORECASE) for p in meta["accept"]):
        return None

    # A rejection on screen beats an acceptance keyword elsewhere on the page:
    # the submissions list shows old "Accepted" rows while the current verdict
    # is "Wrong Answer", and the CURRENT verdict is what counts.
    if re.search(r"\b(wrong answer|time limit exceeded|runtime error|"
                 r"compilation error|memory limit exceeded|presentation error)\b",
                 combined, re.IGNORECASE):
        return None

    problem = _problem_name(ctx, pid)
    return {
        "platform": pid,
        "label": meta["label"],
        "problem": problem,
        "item": f"{pid}:{problem.lower()}",
    }


def describe(hit: dict[str, Any]) -> str:
    return f"{hit['problem']} on {hit['label']}"
