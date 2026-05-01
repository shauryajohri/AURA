import csv
import os
import datetime
import random

CSV_PATH = os.path.join("config", "quick_responses.csv")

def load_responses() -> dict:
    responses = {}
    try:
        with open(CSV_PATH, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                trigger = row["trigger"].lower().strip()
                if trigger not in responses:
                    responses[trigger] = []
                responses[trigger].append({
                    "response": row["response"],
                    "action": row["action"]
                })
    except FileNotFoundError:
        print("[AURA] CSV file not found")
    return responses

_responses = load_responses()

def check_csv(query: str) -> str | None:
    query_clean = query.lower().strip()
    if query_clean in _responses:
        print(f"[DEBUG] CSV match: '{query_clean}'")
        # pick random response from all options for this trigger
        entry = random.choice(_responses[query_clean])
        return _process(entry)
    print(f"[DEBUG] No CSV match → LLM")
    return None

def _process(entry: dict) -> str:
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
            return "Couldn't find Chrome."

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
    

    return response