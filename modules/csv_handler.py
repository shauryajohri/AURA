import datetime
import csv
import os
import random
import re
from urllib import response
from modules import screen_reader

LOOK_AT_PATTERN = re.compile(r"look at (?P<target>.+?) and (?P<action>.+)", re.IGNORECASE)
STATUS_TRIGGERS = ["what are you doing", "what are you looking at"]

CSV_PATH = os.path.join("config", "quick_responses.csv")
NO_ACTION = {"", "none", "null"}

def load_responses() -> dict:
    responses = {}
    try:
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                trigger = row.get("trigger", "").lower().strip()
                response = row.get("response", "").strip()
                action = row.get("action", "").strip()
                if not trigger or (not response and action.lower() in NO_ACTION):
                    continue
                if trigger not in responses:
                    responses[trigger] = []
                responses[trigger].append({
                    "response": response,
                    "action": action
                })
    except FileNotFoundError:
        print("[AURA] CSV file not found")
    except Exception as e:
        print(f"[AURA] CSV load error: {e}")
    return responses

_responses = load_responses()
total_entries = sum(len(v) for v in _responses.values())
print(f"[AURA] CSV loaded: {total_entries} entries ({len(_responses)} unique triggers)")

def check_csv(query: str) -> str | None:
    query_clean = query.lower().strip()

    if query_clean in _responses:
        print(f"[DEBUG] CSV match: '{query_clean}'")
        return _process(query_clean)

    return None

def _process(trigger: str) -> str:
    entries = _responses[trigger]
    action_entries = [
        entry for entry in entries
        if entry.get("action", "").strip().lower() not in NO_ACTION
    ]
    text_entries = [
        entry for entry in entries
        if entry.get("response", "").strip()
    ]

    entry = action_entries[0] if action_entries else random.choice(text_entries)
    action = entry.get("action", "").strip()
    response = action if action.lower() not in NO_ACTION else entry["response"]

    if response == "TIME_FUNCTION":
        now = datetime.datetime.now()
        return f"It's {now.strftime('%I:%M %p')}."

    if response == "DATE_FUNCTION":
        now = datetime.datetime.now()
        return f"Today is {now.strftime('%A, %d %B %Y')}."

    if response.startswith("OPEN_"):
        from modules.command_handler import open_app  # deferred import avoids a circular import
        app_name = response[len("OPEN_"):].replace("_", " ")
        return open_app(app_name)

    if response == "SAVE_CLIPBOARD":
        from modules.knowledge import save_from_clipboard
        return save_from_clipboard()

    if response == "LIST_SAVED":
        from modules.knowledge import list_saved
        return list_saved()

    if response == "FOREX_REPORT":
        try:
            from modules.forex_report import generate_report
            return generate_report()
        except Exception as e:
            return f"Forex report unavailable: {str(e)}"

    if response == "LIST_TASKS":
        from modules.tasks import handle_list_tasks
        return handle_list_tasks()

    if response == "WHAT_TODO":
        from modules.tasks import handle_what_to_do
        return handle_what_to_do("")

    return response
