import datetime
from memory.store import (
    add_task, get_tasks, complete_task,
    delete_task, get_pending_tasks, get_task_summary
)
from core.ai_router import call_claude

def handle_add_task(query: str) -> str:
    query_clean = query.lower()
    for prefix in ["add task", "add a task", "new task",
                   "i need to", "remind me to", "todo"]:
        query_clean = query_clean.replace(prefix, "").strip()

    if not query_clean:
        return "What task should I add?"

    title = query_clean.strip().capitalize()
    add_task(title)
    return f"Added '{title}' to your tasks."

def handle_complete_task(query: str) -> str:
    # find which task to complete
    pending = get_pending_tasks()
    if not pending:
        return "No pending tasks to complete."

    query_lower = query.lower()
    for task in pending:
        if any(word in query_lower for word in task[1].lower().split()):
            complete_task(task[0])
            return f"Marked '{task[1]}' as done."

    # if no match found list tasks
    task_list = "\n".join([f"{t[0]}. {t[1]}" for t in pending])
    return f"Which task? Here's what's pending:\n{task_list}"

def handle_remove_task(query: str) -> str:
    pending = get_pending_tasks()
    if not pending:
        return "No tasks to remove."

    query_lower = query.lower()
    for task in pending:
        if any(word in query_lower for word in task[1].lower().split()):
            delete_task(task[0])
            return f"Removed '{task[1]}' from your list."

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