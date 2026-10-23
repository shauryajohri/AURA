"""
Settings → Privacy actually does something (memory/store.py privacy_allows +
save_conversation, modules/screen_reader.py, core/brain.py transcript, and
frontend/src/components/Home/SettingsOverlay.tsx), driven through the REAL
/api/settings and /ws with only the HTTP layer and the screen faked.

What must hold:
  * a fresh /api/settings reports both privacy switches, on
  * Store Conversations off: no turn reaches the chat log — chat, shortcut or
    a direct save_conversation — yet the next prompt still sees the last turn
  * Screen Reading off: no screenshot, no OCR, no clipboard on a chat turn or
    a direct get_screen_context; quest verification can't grab the screen
  * both are read live: switching them back on works on the very next turn
  * the editor shows the privacy switches as switches (on), not sliders at 0,
    and labels the settings nothing reads yet instead of pretending

Runs offline on a throwaway DB and vault; never starts the background loops.
The editor check needs node and frontend/node_modules (npm install), and is
skipped without them.

Run:  PYTHONPATH=. python tests/test_privacy_settings.py
"""

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# throwaway DB + Buddy Lock vault before anything binds to the real ones
_TMP = tempfile.mkdtemp(prefix="aura_privacy_")
os.environ["AURA_GUARD_VAULT"] = os.path.join(_TMP, "buddy.json")
os.environ.pop("AURA_TOKEN", None)

import memory.store as mstore  # noqa: E402
mstore.DB_PATH = os.path.join(_TMP, "test.db")
mstore.init_db()
mstore.init_tasks()
mstore.init_quests()
from core.domain import brain_store  # noqa: E402
brain_store.DB_PATH = mstore.DB_PATH
brain_store._connect = mstore._connect
# every chat turn bumps the relationship engine, which saves to memory/
from modules import relationship_engine  # noqa: E402
relationship_engine.STATE_FILE = os.path.join(_TMP, "relationship_state.json")

# Lock state is not under test: nothing is locked, and the real store is
# never read (it needs a GUI toolkit that a backend-only install lacks).
try:
    from core import model_lock  # noqa: E402
except ImportError:
    import core  # noqa: E402
    model_lock = types.ModuleType("core.model_lock")
    sys.modules["core.model_lock"] = core.model_lock = model_lock
model_lock.is_locked = lambda name: False

from fastapi.testclient import TestClient  # noqa: E402

import core.ai_router as ai_router  # noqa: E402
import local_auth  # noqa: E402
import server  # noqa: E402
from core import model_router  # noqa: E402
import modules.screen_reader as sr  # noqa: E402


# ── the HTTP layer is the only fake on the model side ───────────────────────
PROMPTS: list[str] = []   # the user message of every streamed chat request


class _Resp:
    status_code = 200
    text = ""

    def __init__(self, content):
        self._content = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}

    def iter_lines(self):
        yield ("data: " + json.dumps({"choices": [{"delta": {"content": self._content}}]})).encode()
        yield b"data: [DONE]"


def _post(url, headers=None, json=None, timeout=None, stream=False):  # noqa: A002
    body = json or {}
    if body.get("stream"):
        PROMPTS.append(body["messages"][-1]["content"])
        return _Resp("Noted.")
    system = body["messages"][0]["content"]
    return _Resp("CASUAL" if "classifier" in system else "NONE")


ai_router.requests = types.SimpleNamespace(post=_post)
ai_router.GROQ_API_KEY = "gsk-test"
ai_router.OPENROUTER_API_KEY = "sk-or-test"
ai_router._OPENROUTER_MODEL_KEYS = {m: "sk-or-test" for m in model_router.MODELS.values()}

server._voice_is_on = lambda: False
server._init_director()   # the lifespan normally does this; it stays off here


# ── the screen is fake too, so every grab / OCR / clipboard read is counted ─
GRABS: list[int] = []
OCRS: list[int] = []
CLIPS: list[int] = []


class _Img:
    width, height = 200, 100

    def resize(self, size):
        return self


class _Sct:
    monitors = [None, {"left": 0, "top": 0, "width": 200, "height": 100}]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def grab(self, region):
        GRABS.append(1)
        return types.SimpleNamespace(size=(200, 100), rgb=b"")


_WIN = types.SimpleNamespace(title="main.py - Visual Studio Code")
sr.mss = types.SimpleNamespace(mss=lambda: _Sct())
sr.Image = types.SimpleNamespace(frombytes=lambda *a: _Img())
sr.pytesseract = types.SimpleNamespace(image_to_string=lambda img: OCRS.append(1) or "password = hunter2")
sr.pyperclip = types.SimpleNamespace(paste=lambda: CLIPS.append(1) or "copied secret")
sr.gw = types.SimpleNamespace(getActiveWindow=lambda: _WIN, getAllWindows=lambda: [_WIN])


_fails: list[str] = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'} — {label}")
    if not cond:
        _fails.append(label)


client = TestClient(server.app, base_url="http://127.0.0.1:8760")
HDR = {"X-Aura-Token": local_auth.TOKEN}
_cm = client.websocket_connect("ws://127.0.0.1:8760/ws",
                               subprotocols=["aura", "aura-token." + local_auth.TOKEN])
ws = _cm.__enter__()
_frames: queue.Queue = queue.Queue()


def _reader():
    try:
        while True:
            _frames.put(ws.receive_json())
    except Exception:  # noqa: BLE001
        _frames.put({"type": "_closed"})


threading.Thread(target=_reader, daemon=True).start()
time.sleep(0.3)
while not _frames.empty():
    _frames.get()


def turn(text, timeout=20.0):
    """One turn; returns the done text (None if no done frame came)."""
    ws.send_json({"type": "message", "payload": {"text": text}})
    got, end = [], time.time() + timeout
    while time.time() < end:
        try:
            f = _frames.get(timeout=0.2)
        except queue.Empty:
            continue
        got.append(f)
        if f.get("type") == "_closed":
            break
        if (f.get("type") == "state" and f["payload"].get("state") == "idle"
                and any(g.get("type") in ("done", "push", "error") for g in got)):
            break
    done = next((f["payload"] for f in got if f.get("type") == "done"), None)
    return done["text"] if done else None


def put(**privacy):
    patch = {f"privacy.{k}": v for k, v in privacy.items()}
    return client.put("/api/settings", headers=HDR, json={"settings": patch}).json()


def logged() -> list[str]:
    """Every message in the conversation log, across all chats."""
    conn = mstore._connect()
    try:
        return [r[0] for r in conn.execute("SELECT message FROM conversations")]
    finally:
        conn.close()


def screen_reads() -> tuple[int, int, int]:
    return len(GRABS), len(OCRS), len(CLIPS)


# ── 1. A fresh install reports both switches ───────────────────────────────
print("\n[1] /api/settings reports the privacy switches before anyone saves them")
s = FRESH = client.get("/api/settings", headers=HDR).json()["settings"]
check(s.get("privacy.store_conversations") is True, f"store_conversations defaults to on ({s.get('privacy.store_conversations')!r})")
check(s.get("privacy.screen_reading") is True, f"screen_reading defaults to on ({s.get('privacy.screen_reading')!r})")

# ── 2. Store Conversations off ─────────────────────────────────────────────
print("\n[2] Store Conversations off: nothing reaches the chat log")
check(put(store_conversations=False).get("ok") is True, "PUT privacy.store_conversations=false")
n0 = len(logged())
done = turn("secret: my locker code is 4471")
check(done == "Noted.", f"the chat turn is still answered ({done!r})")
done = turn("add task buy milk")
check(done is not None and "Buy milk" in done, f"shortcuts still work ({done!r})")
mstore.save_conversation("user", "a direct save")
rows = logged()
check(len(rows) == n0, f"no message was stored ({len(rows) - n0} new rows)")
check(not any("4471" in r for r in rows), "the secret is not in the log")
wm = json.dumps(mstore.get_working_memory() or {})
check("4471" not in wm and "Noted." not in wm,
      "...nor in working memory (no message or reply snippet on disk)")
p0 = len(PROMPTS)
turn("what's my locker code?")
check(any("4471" in p for p in PROMPTS[p0:]),
      "the next prompt still carries the previous turn (kept in RAM, not on disk)")
check(len(logged()) == n0, "...and that turn wasn't stored either")

print("\n[2b] switched back on, the very next turn is stored (no restart)")
put(store_conversations=True)
turn("back on the record")
rows = logged()
check(len(rows) == n0 + 2 and "back on the record" in rows, f"user + AURA turn stored ({len(rows) - n0} new rows)")

# ── 3. Screen Reading off ──────────────────────────────────────────────────
print("\n[3] Screen Reading off: no screenshot, no OCR, no clipboard")
check(put(screen_reading=False).get("ok") is True, "PUT privacy.screen_reading=false")
r0 = screen_reads()
done = turn("what am I looking at?")
check(done == "Noted.", f"the chat turn is still answered ({done!r})")
check(screen_reads() == r0, f"the chat turn read nothing off the screen (grab/OCR/clipboard {r0} → {screen_reads()})")
check(not any("hunter2" in p or "copied secret" in p for p in PROMPTS[-1:]), "no screen text or clipboard in the prompt")
done = turn("any errors?")
check(done is not None and "Screen reading is off" in done, f"the error check says why it can't look ({done!r})")
ctx = sr.get_screen_context()
check(ctx.get("visible_text") == "" and ctx.get("clipboard") == "",
      f"get_screen_context has no screen text or clipboard ({ctx!r})")
check(ctx.get("app") == _WIN.title, f"...but still knows the window title, which quests count by ({ctx.get('app')!r})")
check(sr.extract_text_from_screen() == "", "extract_text_from_screen returns nothing")
try:
    sr.take_screenshot()
    raised = ""
except RuntimeError as e:
    raised = str(e)
check("Privacy" in raised, f"take_screenshot refuses ({raised!r})")
from core.quest_verify import _capture_jpeg_b64  # noqa: E402
b64, err = _capture_jpeg_b64()
check(b64 is None and "screen reading is off" in err, f"quest verification can't grab the screen ({err!r})")
check(screen_reads() == r0, f"nothing above touched the screen ({r0} → {screen_reads()})")

print("\n[3b] switched back on, the next look reads the screen again (no restart)")
put(screen_reading=True)
ctx = sr.get_screen_context()
check(ctx.get("visible_text") == "password = hunter2" and ctx.get("clipboard") == "copied secret",
      f"screen text and clipboard are back ({ctx!r})")

# ── 4. privacy_allows ──────────────────────────────────────────────────────
print("\n[4] privacy_allows reads the switch the way the UI and a hand edit write it")
allows = getattr(mstore, "privacy_allows", lambda what: None)
mstore.set_settings({"privacy.screen_reading": "false"})
check(allows("screen_reading") is False, "the string 'false' means off")
mstore.set_settings({"privacy.screen_reading": True})
check(allows("screen_reading") is True, "true means on")
_db = mstore.DB_PATH
mstore.DB_PATH = _TMP   # a directory: sqlite can't open it
check(allows("store_conversations") is False, "an unreadable settings table means NO")
mstore.DB_PATH = _db

_cm.__exit__(None, None, None)

# ── 5. The editor ──────────────────────────────────────────────────────────
print("\n[5] SettingsOverlay renders switches as switches and labels the unwired ones")
FE = os.path.join(ROOT, "frontend")
OVERLAY = os.path.join(FE, "src", "components", "Home", "SettingsOverlay.tsx")
src = open(OVERLAY, encoding="utf-8").read()
m = re.search(r"const NOT_WIRED = new Set\(\[(.*?)\]\);", src, re.S)
check(m is not None, "NOT_WIRED found in SettingsOverlay.tsx")
not_wired = re.findall(r'"([\w.]+)"', m.group(1)) if m else []
# Every key in NOT_WIRED really is unread: nothing but the store's defaults
# and the editor itself names it. Wire one up and this tells you to unlabel it.
haystack = []
for base, exts in ((os.path.join(FE, "src"), (".ts", ".tsx")), (os.path.join(FE, "electron"), (".js", ".cjs", ".ts")),
                   (os.path.join(ROOT, "core"), (".py",)), (os.path.join(ROOT, "modules"), (".py",))):
    for d, _, files in os.walk(base):
        for f in files:
            if f.endswith(exts) and f not in ("SettingsOverlay.tsx", "settingsStore.ts"):
                haystack.append(open(os.path.join(d, f), encoding="utf-8", errors="ignore").read())
for f in ("server.py", "memory/store.py"):
    text = open(os.path.join(ROOT, f), encoding="utf-8").read()
    # memory/store.py's DEFAULT_SETTINGS is the backend's copy of the defaults
    # table (kept in step with settingsStore.ts), so it doesn't count as a read.
    text = re.sub(r"^DEFAULT_SETTINGS = \{.*?^\}", "", text, flags=re.S | re.M)
    haystack.append(text)
blob = "\n".join(haystack)
read_somewhere = [k for k in not_wired if k in blob]
check(not_wired and not read_somewhere, f"every NOT_WIRED key is unread elsewhere (read: {read_somewhere})")

node = shutil.which("node")
esbuild = os.path.join(FE, "node_modules", "esbuild")
if not node or not os.path.isdir(esbuild) or not os.path.isdir(os.path.join(FE, "node_modules", "react-dom")):
    print("  SKIP — node or frontend/node_modules is missing")
else:
    work = tempfile.mkdtemp(prefix="aura_overlay_")
    fresh = os.path.join(work, "fresh.json")
    empty = os.path.join(work, "empty.json")
    json.dump(FRESH, open(fresh, "w"))   # what /api/settings gave the fresh install in [1]
    json.dump({}, open(empty, "w"))
    cats = ["privacy", "general", "behavior", "developer", "experimental", "voice", "animations", "wallpaper", "planets"]
    fwd = lambda p: p.replace("\\", "/")  # noqa: E731
    entry = os.path.join(work, "entry.tsx")
    open(entry, "w", encoding="utf-8").write(f'''
import {{ readFileSync }} from "fs";
import {{ renderToStaticMarkup }} from "react-dom/server";
import SettingsOverlay from "{fwd(OVERLAY[:-4])}";
import {{ DEFAULT_LAYOUT }} from "{fwd(os.path.join(FE, "src", "components", "Home", "layoutTypes"))}";
const out: Record<string, Record<string, string>> = {{}};
for (const [name, file] of [["fresh", {json.dumps(fwd(fresh))}], ["empty", {json.dumps(fwd(empty))}]]) {{
  const settings = JSON.parse(readFileSync(file, "utf8"));
  out[name] = {{}};
  for (const cat of {json.dumps(cats)}) {{
    out[name][cat] = renderToStaticMarkup(
      <SettingsOverlay category={{cat as any}} settings={{settings}} layout={{DEFAULT_LAYOUT}}
        onSaveSettings={{() => {{}}}} onSaveLayout={{() => {{}}}} onClose={{() => {{}}}} />);
  }}
}}
console.log(JSON.stringify(out));
''')
    bundle = os.path.join(work, "bundle.cjs")
    build = f'''require({json.dumps(fwd(esbuild))}).buildSync({{
  entryPoints: [{json.dumps(fwd(entry))}], outfile: {json.dumps(fwd(bundle))},
  bundle: true, platform: "node", format: "cjs", jsx: "automatic",
  loader: {{ ".css": "empty" }}, nodePaths: [{json.dumps(fwd(os.path.join(FE, "node_modules")))}], logLevel: "error",
}});'''
    b = subprocess.run([node, "-e", build], capture_output=True, text=True, timeout=120)
    r = subprocess.run([node, bundle], capture_output=True, text=True, timeout=60) if b.returncode == 0 else b
    check(r.returncode == 0, f"the overlay renders ({(r.stderr or '').strip()[-300:]})")
    html = json.loads(r.stdout) if r.returncode == 0 else {}

    def rows(page):
        """{label: (kind, value, tagged, disabled)} for each control row."""
        out = {}
        for cls, body in re.findall(r'<div class="(setov__row[^"]*)">(.*?)</div>', page):
            label = re.search(r'setov__label">([^<]+)<', body).group(1)
            if "san-toggle" in body:
                kind, value = "toggle", "san-toggle--on" in body
            elif 'type="range"' in body:
                kind, value = "slider", int(re.search(r'setov__val">(\d+)<', body).group(1))
            else:
                kind, value = "other", None
            out[label] = (kind, value, "not active yet" in body, "disabled" in body)
        return out

    for name in ("fresh", "empty"):
        p = rows(html.get(name, {}).get("privacy", ""))
        for label in ("screen reading", "store conversations"):
            check(p.get(label, ("", None))[:2] == ("toggle", True),
                  f"{name} settings: '{label}' is a switch, on ({p.get(label)})")
            check(p.get(label, (0, 0, True, True))[2:] == (False, False),
                  f"{name} settings: '{label}' is live — not labelled, not disabled")
    for cat in cats:
        for label, (kind, value, tagged, disabled) in rows(html.get("fresh", {}).get(cat, "")).items():
            key = next((k for k in not_wired if k.split(".")[1].replace("_", " ") == label
                        and k.split(".")[0] in (cat, {"developer": "dev", "animations": "anim"}.get(cat))), None)
            want = key is not None
            check(tagged == want and disabled == want,
                  f"{cat}/{label}: {'labelled not active yet and disabled' if want else 'live, no label'} ({kind}={value!r})")
    b_ = rows(html.get("fresh", {}).get("behavior", ""))
    check(b_.get("proactive", ("", None))[:2] == ("toggle", True), f"a default-on unwired switch shows on, not a 0 slider ({b_.get('proactive')})")
    a_ = rows(html.get("fresh", {}).get("animations", ""))
    check(a_.get("intensity", ("", None))[:2] == ("slider", 70), f"an unwired slider shows its default, not 0 ({a_.get('intensity')})")
    hint = re.search(r'setov__hint">([^<]+)<', html.get("fresh", {}).get("privacy", ""))
    check(hint is not None and "saved to your history" in hint.group(1), f"the privacy preview says what the switches do ({hint and hint.group(1)!r})")

print("\n" + ("ALL PASS ✅" if not _fails else f"FAILURES ({len(_fails)}): {_fails}"))
sys.exit(1 if _fails else 0)
