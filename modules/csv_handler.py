import csv
import os
import datetime

CSV_PATH = os.path.join("config", "quick_responses.csv")

def load_responses() -> dict:
    responses = {}
    try:
        with open(CSV_PATH, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                trigger = row["trigger"].lower().strip()
                responses[trigger] = {
                    "response": row["response"],
                    "action": row["action"]
                }
    except FileNotFoundError:
        print("[AURA] CSV file not found")
    return responses

_responses = load_responses()

def check_csv(query: str) -> str | None:
    query_clean = query.lower().strip()

    # exact match first
    if query_clean in _responses:
        return _process(query_clean)

    # only match if trigger is more than 3 chars
    # and query starts with or equals the trigger
    for trigger in _responses:
        if len(trigger) > 3 and query_clean == trigger:
            return _process(trigger)

    return None  # no match — pass to Ollama

def _process(trigger: str) -> str:
    entry = _responses[trigger]
    response = entry["response"]

    # handle special functions
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
        from modules.forex_report import generate_report
    return generate_report()

    return response