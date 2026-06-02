import sqlite3
import datetime
import os
import csv
import os
import datetime
import random
from urllib import response

CSV_PATH = os.path.join("config", "quick_responses.csv")

def load_responses() -> dict:
    responses = {}
    try:
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "trigger" not in row:
                    continue
                trigger = row["trigger"].lower().strip()
                if trigger not in responses:
                    responses[trigger] = []
                responses[trigger].append({
                    "response": row["response"],
                    "action": row["action"]
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
    entry = random.choice(entries)
    response = entry["response"]

    if response == "TIME_FUNCTION":
        now = datetime.datetime.now()
        return f"It's {now.strftime('%I:%M %p')}."

    if response == "DATE_FUNCTION":
        now = datetime.datetime.now()
        return f"Today is {now.strftime('%A, %d %B %Y')}."

    if response == "OPEN_CHROME":
        import subprocess
        try:
            subprocess.Popen("chrome.exe")
            return "Opening Chrome."
        except:
            return "Couldn't find Chrome on your system."

    if response == "OPEN_NOTEPAD":
        import subprocess
        subprocess.Popen("notepad.exe")
        return "Opening Notepad."

    if response == "OPEN_CALCULATOR":
        import subprocess
        subprocess.Popen("calc.exe")
        return "Opening Calculator."

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