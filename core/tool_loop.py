"""
Run AURA's tools before she answers (parse-and-loop, model-agnostic).

One extra small-model call on an eligible turn: the model sees the tool
catalogue and either asks for something or says `TOOL: none`. We run what it
asked for, feed the result back, and repeat up to MAX_STEPS. Whatever the
tools returned becomes a context block on the REAL answer — the model still
writes the reply itself, it just writes it informed.

Gated hard by should_run(): a coding / work / repo turn is worth the round
trip; "hey" is not. The whole thing is best-effort — any failure returns ""
and the turn proceeds exactly as it did before this module existed.
"""

from __future__ import annotations

from core import tools

# Each step is a sequential planner call before the visible answer starts —
# 2 covers the common case (repo_state + one search) without stacking latency.
MAX_STEPS = 2

# Intents that already have their own context path or never need a lookup.
# RECALL is routed through process() which pulls work_recall itself.
_SKIP_INTENTS = {"CASUAL", "PERSONAL", "COMMAND", "SAVE", "REMINDER", "RECALL"}
_ALWAYS_INTENTS = {"CODING", "RESEARCH", "PLAN", "SEARCH"}

# For the in-between intents (EXPLAIN, DISCUSSION, unclassified), only run when
# the message actually points at the work.
_WORK_HINTS = (
    "repo", "codebase", "code base", "the code", "this file", "that file",
    ".py", ".tsx", ".ts", "function", "endpoint", "route", "commit", "branch",
    "refactor", "bug", "regression", "server.py", "brain.py", "component",
    "we built", "we added", "we changed", "we wrote", "this project",
    "the project", "our code", "the room", "the picker", "the dock",
)


def should_run(query: str, intent: str) -> bool:
    q = (query or "").strip().lower()
    if len(q) < 8:
        return False
    if intent in _ALWAYS_INTENTS:
        return True
    if intent in _SKIP_INTENTS:
        return False
    return any(h in q for h in _WORK_HINTS)


# The verb is FETCH, never "tool"/"call"/"function": Groq's gpt-oss models
# read that vocabulary as a cue to emit a NATIVE tool call, which the API
# then 400s because this path sends no tools array.
_SYS = """You gather facts for AURA before she replies. Reply with ONE line of plain text, nothing else:
  FETCH: <name> <json-params>

Names you may fetch:
{catalogue}

Rules:
- One line per step. After a RESULT line you may fetch again or stop.
- Stop by writing exactly:  FETCH: none
- Fetch ONLY what THIS message needs. If it needs nothing, write FETCH: none.
- Never write prose, explanation, or the answer. Only a FETCH line."""


def gather_context(query: str, intent: str) -> str:
    """Return a context block from lookup results, or "" if nothing was fetched."""
    if not should_run(query, intent):
        return ""
    try:
        from core.ai_router import call_planner
    except Exception:  # noqa: BLE001
        return ""

    sys = _SYS.format(catalogue=tools.catalogue())
    transcript = (
        f"USER MESSAGE: {query}\n\n"
        "First line — what do you need? (FETCH: none if nothing)"
    )
    collected: list[tuple[str, dict, str]] = []

    for _ in range(MAX_STEPS):
        try:
            reply = call_planner(transcript, system=sys)
        except Exception:  # noqa: BLE001
            break
        if not reply or reply in {"RATE_LIMIT", "CONNECTION_ERROR", "ERROR"}:
            break
        parsed = tools.parse_tool_call(reply)
        if not parsed or parsed[0] == "none":
            break
        name, args = parsed
        if name not in tools.TOOLS:
            # nudge once, then give up rather than spin
            transcript += f"\n{reply.strip()}\nRESULT: unknown name. Use one of: {', '.join(tools.TOOLS)} or FETCH: none.\n"
            continue
        _announce(name, args)
        result = tools.run_tool(name, args)
        collected.append((name, args, result))
        transcript += (
            f"\nFETCH: {name} {args}\nRESULT: {result}\n\n"
            "Next line — another FETCH, or FETCH: none."
        )

    if not collected:
        return ""

    out = []
    for name, args, result in collected:
        arg = str(args.get("query") or args.get("name") or "").strip()
        label = f"{name}({arg})" if arg else name
        out.append(f"[{label}]\n{result}")
    return "\n\n".join(out)


def _announce(name: str, args: dict) -> None:
    """Best-effort 'what AURA is doing' ping so the lookup isn't invisible."""
    try:
        from core import activity
        pretty = {
            "repo_state": "Checking the repo…",
            "search_code": "Searching the codebase…",
            "recall_project": "Recalling the project…",
            "list_rooms": "Checking rooms…",
        }.get(name, "Looking something up…")
        activity.emit(pretty, "memory")
    except Exception:  # noqa: BLE001
        pass
