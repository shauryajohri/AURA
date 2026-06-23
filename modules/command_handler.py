import difflib
import os
import subprocess
import time
from pathlib import Path

from modules import screen_reader
from modules.csv_handler import LOOK_AT_PATTERN, STATUS_TRIGGERS

APP_CACHE_TTL = 300
EXECUTABLE_EXTENSIONS = {".exe", ".bat", ".cmd", ".com"}
SHORTCUT_EXTENSIONS = {".lnk", ".url"}

_app_cache = {}
_last_scan_time = 0


def _clean_name(name: str) -> str:
    name = Path(name).stem.lower()
    for token in [" app", " shortcut", " launcher", " browser"]:
        name = name.replace(token, "")
    return " ".join(name.replace("_", " ").replace("-", " ").split())


def _add_candidate(index: dict, name: str, path: str):
    clean = _clean_name(name)
    if not clean or not path:
        return

    index.setdefault(clean, path)
    compact = clean.replace(" ", "")
    if compact != clean:
        index.setdefault(compact, path)


def _safe_iterdir(folder: Path):
    try:
        yield from folder.iterdir()
    except Exception:
        return


def _scan_path_apps(index: dict):
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        if not folder:
            continue
        path_folder = Path(folder)
        if not path_folder.exists():
            continue
        for item in _safe_iterdir(path_folder):
            if item.is_file() and item.suffix.lower() in EXECUTABLE_EXTENSIONS:
                _add_candidate(index, item.name, str(item))


def _scan_start_menu(index: dict):
    folders = [
        Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("PUBLIC", "")) / "Desktop",
        Path.home() / "Desktop",
    ]
    for folder in folders:
        if not folder.exists():
            continue
        try:
            for item in folder.rglob("*"):
                if item.is_file() and item.suffix.lower() in SHORTCUT_EXTENSIONS:
                    _add_candidate(index, item.name, str(item))
        except Exception:
            continue


def _scan_common_install_dirs(index: dict):
    roots = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("APPDATA"),
    ]
    skip_dirs = {
        "windows", "microsoft", "packages", "temp", "cache", "__pycache__",
        "node_modules", "python", "site-packages"
    }

    for root in [Path(r) for r in roots if r]:
        if not root.exists():
            continue

        for current, dirs, files in os.walk(root):
            current_path = Path(current)
            depth = len(current_path.relative_to(root).parts)
            if depth > 4:
                dirs[:] = []
                continue

            dirs[:] = [
                d for d in dirs
                if d.lower() not in skip_dirs and not d.startswith(".")
            ]

            for filename in files:
                path = current_path / filename
                if path.suffix.lower() in EXECUTABLE_EXTENSIONS:
                    _add_candidate(index, filename, str(path))


def _scan_app_paths(index: dict):
    try:
        import winreg
    except Exception:
        return

    registry_roots = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
    ]

    for hive, key_path in registry_roots:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    app_key_name = winreg.EnumKey(key, i)
                    with winreg.OpenKey(key, app_key_name) as app_key:
                        app_path = winreg.QueryValue(app_key, None)
                        _add_candidate(index, app_key_name, app_path)
        except Exception:
            continue


def scan_apps(force: bool = False) -> dict:
    global _app_cache, _last_scan_time

    now = time.time()
    if _app_cache and not force and now - _last_scan_time < APP_CACHE_TTL:
        return _app_cache

    index = {}
    _scan_app_paths(index)
    _scan_start_menu(index)
    _scan_path_apps(index)
    _scan_common_install_dirs(index)

    _app_cache = index
    _last_scan_time = now
    print(f"[AURA] App scan indexed {len(index)} launch targets")
    return _app_cache


def _find_app(app_name: str) -> tuple[str, str] | None:
    query = _clean_name(app_name)
    if not query:
        return None

    apps = scan_apps()
    compact_query = query.replace(" ", "")

    for key in [query, compact_query]:
        if key in apps:
            return key, apps[key]

    for key, path in apps.items():
        if query in key or compact_query in key.replace(" ", ""):
            return key, path

    matches = difflib.get_close_matches(query, apps.keys(), n=1, cutoff=0.74)
    if matches:
        match = matches[0]
        return match, apps[match]

    return None


def _launch(path: str):
    if path.lower().endswith(tuple(SHORTCUT_EXTENSIONS)):
        os.startfile(path)
    else:
        subprocess.Popen([path], shell=False)


def open_app(app_name: str) -> str:
    app_name_clean = app_name.strip()
    found = _find_app(app_name_clean)

    if found:
        matched_name, path = found
        try:
            _launch(path)
            return f"Opening {matched_name.title()}."
        except Exception as e:
            return f"I found {matched_name}, but couldn't open it: {e}"

    try:
        subprocess.Popen([app_name_clean], shell=False)
        return f"Trying to open {app_name_clean}."
    except Exception:
        pass

    try:
        subprocess.Popen([app_name_clean + ".exe"], shell=False)
        return f"Trying to open {app_name_clean}."
    except Exception:
        return f"I couldn't find {app_name_clean} on your system. Try saying the full app name once."


def handle_command(query: str) -> str | None:
    q = query.lower()

    open_triggers = [
        "can you open ", "please open ", "can u open ",
        "open ", "launch ", "start ", "run "
    ]
    look_match = LOOK_AT_PATTERN.search(q)
    if look_match:
        target = look_match.group("target").strip()
        action = look_match.group("action").strip()
        window = screen_reader.find_window(target)
        if not window:
            return f"I can't find a window for {target} right now."
        screen_reader.set_current_focus(window.title, action)
        context = screen_reader.get_screen_context(target)
        # TODO: hand `context["visible_text"]` to your LLM/thinking module
        # along with `action` to actually do the debugging analysis.
        return f"Looking at {window.title} now to {action}."

    if any(trigger in q for trigger in STATUS_TRIGGERS):
        return screen_reader.describe_current_focus()
    for trigger in open_triggers:
        if trigger in q:
            app_name = q.split(trigger, 1)[1].strip("?. ")
            return open_app(app_name)

    return None
