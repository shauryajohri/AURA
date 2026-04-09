import subprocess
import os

# common apps — add more anytime
APP_MAP = {
    "chrome":      "chrome.exe",
    "notepad":     "notepad.exe",
    "calculator":  "calc.exe",
    "comet":       "comet.exe",
    "pycharm":     "pycharm64.exe",
    "vs code":     "code.exe",
    "vscode":      "code.exe",
    "spotify":     "spotify.exe",
    "discord":     "discord.exe",
    "whatsapp":    "whatsapp.exe",
    "telegram":    "telegram.exe",
    "excel":       "excel.exe",
    "word":        "winword.exe",
    "powerpoint":  "powerpnt.exe",
    "vlc":         "vlc.exe",
    "explorer":    "explorer.exe",
    "task manager":"taskmgr.exe",
    "cmd":         "cmd.exe",
    "powershell":  "powershell.exe",
}

def open_app(app_name: str) -> str:
    app_name_clean = app_name.lower().strip()

    # check known apps first
    for key, exe in APP_MAP.items():
        if key in app_name_clean:
            try:
                subprocess.Popen(exe)
                return f"Opening {key.title()}."
            except FileNotFoundError:
                return f"Couldn't find {key.title()} on your system."

    # try running it directly as typed
    try:
        subprocess.Popen(app_name_clean + ".exe")
        return f"Trying to open {app_name_clean}."
    except:
        return f"I couldn't find {app_name_clean} on your system. Is it installed?"

def handle_command(query: str) -> str | None:
    q = query.lower()

    # open app commands
    open_triggers = ["open ", "launch ", "start ", "run ", "can u open ",
                     "can you open ", "please open "]
    for trigger in open_triggers:
        if trigger in q:
            app_name = q.split(trigger, 1)[1].strip("?. ")
            return open_app(app_name)

    return None  # not a command we handle