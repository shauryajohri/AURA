import datetime
import re
from difflib import SequenceMatcher
from memory.store import (
    add_task, get_tasks, complete_task,
    delete_task, get_pending_tasks, get_task_summary
)
from core.ai_router import call_claude

# ── Chat task commands ───────────────────────────────────────────────────────
# A command has to OPEN the message. The old triggers were substrings found
# anywhere ("i need to", "todo", "finished", "completed"), so "I finished the
# movie last night" completed a task and "my todo app idea..." became one.
_LEAD = r"^(?:(?:hey\s+)?aura[\s,:]+)?(?:please\s+|pls\s+)?"
_COMMANDS = (
    # (action, soft, pattern). A "soft" phrasing is also plain speech ("I'm
    # done with the whole thing for today"), so it only counts as a command
    # when it names a pending task.
    ("add", False, re.compile(
        _LEAD + r"(?:add\s+(?:a\s+)?(?:new\s+)?task|new\s+task|remind\s+me\s+to)\b(?P<name>.*)$",
        re.I | re.S)),
    ("complete", False, re.compile(
        _LEAD + r"(?:mark\s+(?:as\s+)?done|(?:complete|finish|tick\s+off|check\s+off)\s+(?:the\s+)?task)\b(?P<name>.*)$",
        re.I | re.S)),
    ("complete", True, re.compile(
        _LEAD + r"mark\s+(?P<name>.+?)\s+(?:as\s+)?(?:done|complete|completed|finished)[\s.!]*$",
        re.I | re.S)),
    ("complete", True, re.compile(
        _LEAD + r"(?:i['\u2019]?m\s+|i\s+am\s+)?done\s+with\b(?P<name>.*)$",
        re.I | re.S)),
    ("remove", False, re.compile(
        _LEAD + r"(?:remove|delete|cancel)\s+(?:the\s+)?task\b(?P<name>.*)$",
        re.I | re.S)),
)

# Words that say nothing about WHICH task. Matching on them is how "done with
# call the dentist" used to complete "Fix a bug in login" ("a" is in "call").
_STOPWORDS = {
    "a", "an", "the", "and", "or", "to", "of", "in", "on", "at", "for", "with",
    "from", "by", "about", "up", "my", "me", "i", "im", "it", "its", "is", "be",
    "this", "that", "task", "tasks", "thing", "stuff", "please", "today", "now",
}


def parse_command(text: str):
    """(action, name, soft) when `text` opens with a task command, else None.
    action is "add", "complete" or "remove"; name is the rest of the message."""
    t = (text or "").strip()
    for action, soft, rx in _COMMANDS:
        m = rx.match(t)
        if m:
            return action, m.group("name").strip(" \t\n:;,.-!?\"'"), soft
    return None


def _words(text: str) -> list:
    text = text.lower().replace("'", "").replace("\u2019", "")
    return [w for w in re.findall(r"[a-z0-9]+", text) if w not in _STOPWORDS]


def _same(a: str, b: str) -> bool:
    # whole words; near misses only for longer ones ("dentst", "reports")
    return a == b or (min(len(a), len(b)) >= 4
                      and SequenceMatcher(None, a, b).ratio() >= 0.85)


def _score(said: list, title: list) -> float:
    """Half for how many of the user's words are in the title, half for how
    much of the title they cover."""
    if not said or not title:
        return 0.0
    hits = sum(any(_same(w, t) for t in title) for w in said) / len(said)
    cover = sum(any(_same(t, w) for w in said) for t in title) / len(title)
    return (hits + cover) / 2


def _match(name: str, tasks: list, need: float):
    """(task, candidates): the one task `name` clearly means, or None plus
    every task it might mean, best first."""
    said = _words(name)
    scored = sorted(((_score(said, _words(t[1])), t) for t in tasks),
                    key=lambda st: -st[0])
    scored = [(s, t) for s, t in scored if s > 0]
    if not scored:
        return None, []
    best = scored[0][0]
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    winner = scored[0][1] if best >= need and best - runner_up >= 0.2 else None
    return winner, [t for _, t in scored]


def _task_name(query: str) -> str:
    cmd = parse_command(query)
    return cmd[1] if cmd else (query or "").strip()


def _listed(tasks: list) -> str:
    return "\n".join([f"{t[0]}. {t[1]}" for t in tasks])


def handle_task_command(text: str) -> str | None:
    """Run `text` if it is a task command. None when it isn't one, so the
    message goes to the model like any other."""
    cmd = parse_command(text)
    if cmd is None:
        return None
    action, name, soft = cmd
    if soft and not _match(name, get_pending_tasks(), 1.0)[1]:
        return None   # names no pending task: it's just talk
    if action == "add":
        return handle_add_task(text)
    if action == "complete":
        return handle_complete_task(text)
    return handle_remove_task(text)


def handle_add_task(query: str) -> str:
    title = re.sub(r"^to\s+", "", _task_name(query), flags=re.I)  # "add a task to ..."
    if not title:
        return "What task should I add?"

    title = title.capitalize()
    add_task(title)
    return f"Added '{title}' to your tasks."

def handle_complete_task(query: str) -> str:
    # find which task to complete
    pending = get_pending_tasks()
    if not pending:
        return "No pending tasks to complete."

    task, candidates = _match(_task_name(query), pending, 0.6)
    if task:
        complete_task(task[0])
        return f"Marked '{task[1]}' as done."

    # not sure which one — ask, never guess
    if candidates:
        return f"Which task? Could be:\n{_listed(candidates)}"
    return f"Which task? Here's what's pending:\n{_listed(pending)}"

def handle_remove_task(query: str) -> str:
    pending = get_pending_tasks()
    if not pending:
        return "No tasks to remove."

    # Deleting can't be undone, so it needs a closer match than completing.
    task, candidates = _match(_task_name(query), pending, 0.75)
    if task:
        delete_task(task[0])
        return f"Removed '{task[1]}' from your list."

    if candidates:
        return f"Which task? Say its full name:\n{_listed(candidates)}"
    return "Couldn't find that task. Say the task name clearly."

def handle_what_to_do(query: str) -> str:
    pending = get_pending_tasks()
    if not pending:
        return "Nothing pending. You're all clear for today."

    # ask AI to prioritize
    task_list = "\n".join([f"- {t[1]}" for t in pending])
    response = call_claude(f"""
The user has these pending tasks:
{task_list}

Tell them which ONE to do first and why. Max 2 sentences. Be direct like a friend.
""")
    return response

def handle_list_tasks() -> str:
    pending = get_pending_tasks()
    done    = get_tasks('done')
    if not pending and not done:
        return "No tasks today. Tell me what you're planning."
    result = ""
    if pending:
        result += f"{len(pending)} pending: "
        result += ", ".join([t[1] for t in pending])
    if done:
        result += f". {len(done)} done: "
        result += ", ".join([t[1] for t in done])
    return result.strip()