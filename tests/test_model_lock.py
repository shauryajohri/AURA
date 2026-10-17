"""
Model locks without a GUI toolkit (core/model_lock.py).

Locks used to live in PySide6's QSettings, so without PySide6 every chat turn
died on the import and /api/models answered 500. They live in the app_settings
table now. What must hold, with PySide6 NOT importable:

  * lock / unlock / toggle work and survive a restart (they're in the DB)
  * chat routing resolves its model candidates, skips locked ones, streams
  * /api/models lists the roster; toggle works by id or by name
  * toggling a name that isn't a model is refused and stores nothing
  * old QSettings locks are carried over once when PySide6 IS there

Runs offline on a throwaway DB; the model call is stubbed.

Run:  PYTHONPATH=. python tests/test_model_lock.py
"""

import importlib
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# No PySide6, whatever this machine has installed: importing it now raises.
sys.modules["PySide6"] = None
sys.modules["PySide6.QtCore"] = None

# throwaway DB + Buddy Lock vault before anything binds to the real ones
_TMP = tempfile.mkdtemp(prefix="aura_model_lock_")
os.environ["AURA_GUARD_VAULT"] = os.path.join(_TMP, "buddy.json")
os.environ.pop("AURA_TOKEN", None)

import memory.store as mstore  # noqa: E402
mstore.DB_PATH = os.path.join(_TMP, "test.db")
mstore.init_db()
mstore.init_tasks()
from core.domain import brain_store  # noqa: E402
brain_store.DB_PATH = mstore.DB_PATH
brain_store._connect = mstore._connect
from core import personality_state  # noqa: E402
personality_state.DB_PATH = mstore.DB_PATH
from modules import relationship_engine  # noqa: E402
relationship_engine.STATE_FILE = os.path.join(_TMP, "relationship_state.json")

_fails: list[str] = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'} — {label}")
    if not cond:
        _fails.append(label)


def finish():
    print("\n" + ("ALL PASS ✅" if not _fails else f"FAILURES ({len(_fails)}): {_fails}"))
    sys.exit(1 if _fails else 0)


def stored():
    return mstore.get_settings().get("models.locked")


# ── 1. the lock store itself ───────────────────────────────────────────────
print("\n[1] model_lock without PySide6")
try:
    from core import model_lock
except ImportError as e:
    check(False, f"core.model_lock imports without PySide6 ({e})")
    finish()
check(True, "core.model_lock imports without PySide6")
check(not model_lock.is_locked("Gemma 4 31B"), "fresh DB: nothing locked")
check(stored() == [], "first read records an empty list (no QSettings to carry over)")
check(model_lock.toggle("Gemma 4 31B") is True, "toggle → locked")
check(model_lock.is_locked("Gemma 4 31B"), "is_locked agrees")
check(stored() == ["Gemma 4 31B"], "stored in app_settings as models.locked")
model_lock.set_locked("GPT-OSS 20B", True)
names = ["Gemma 4 31B", "GPT-OSS 20B", "GPT-OSS 120B"]
check(model_lock.locked_models(names) == {"Gemma 4 31B", "GPT-OSS 20B"}, "locked_models")
check(model_lock.unlocked_models(names) == {"GPT-OSS 120B"}, "unlocked_models")
model_lock.set_locked("GPT-OSS 20B", False)
model_lock.set_locked("GPT-OSS 20B", False)
check(stored() == ["Gemma 4 31B"], "unlocking twice is harmless")
model_lock = importlib.reload(model_lock)
check(model_lock.is_locked("Gemma 4 31B"), "lock survives a restart (module reload)")
check(model_lock.toggle("Gemma 4 31B") is False and stored() == [], "toggle back → unlocked")

mstore.set_settings({"models.locked": "Gemma"})
check(not model_lock.is_locked("G"), "a junk value reads as nothing locked, not letters")
mstore.set_settings({"models.locked": []})


# ── 2. chat routing ────────────────────────────────────────────────────────
print("\n[2] ai_router resolves candidates without PySide6")
from core import ai_router as ar  # noqa: E402
from core import model_router as mr  # noqa: E402

CALLS = []


def fake_stream(prompt, system="", intent="CASUAL", model=None):
    CALLS.append(model)
    yield "Hello "
    yield "there."


ar.call_groq_streaming = fake_stream

try:
    cands = ar._resolve_candidates("CASUAL", None)
except Exception as e:  # noqa: BLE001
    cands = None
    print(f"    {type(e).__name__}: {e}")
check(bool(cands) and cands[0][0] == "Gemma 4 31B", "CASUAL → Gemma first, then the Groq chain")
check(ar.resolve_model("CODING") == mr.MODELS["Laguna M.1"], "CODING → Laguna")
try:
    out = "".join(ar.route_streaming("CASUAL", "hi"))
except Exception as e:  # noqa: BLE001
    out = f"{type(e).__name__}: {e}"
check("Hello" in out and CALLS == [mr.MODELS["Gemma 4 31B"]],
      f"route_streaming streams from the routed model ({out!r})")

model_lock.set_locked("Gemma 4 31B", True)
CALLS.clear()
out = "".join(ar.route_streaming("CASUAL", "hi"))
check(CALLS == [mr.MODELS["GPT-OSS 120B"]], "a locked model is skipped: Groq answers instead")
for n in mr.MODELS:
    model_lock.set_locked(n, True)
CALLS.clear()
out = "".join(ar.route_streaming("CASUAL", "hi"))
check(out == ar._ALL_LOCKED_MSG and not CALLS, "everything locked → the locked message, no call")
for n in mr.MODELS:
    model_lock.set_locked(n, False)


# ── 3. REST ────────────────────────────────────────────────────────────────
print("\n[3] /api/models and toggle")
from fastapi.testclient import TestClient  # noqa: E402

import local_auth  # noqa: E402
import server  # noqa: E402

GOOD = {"X-Aura-Token": local_auth.TOKEN}
# No `with`: the lifespan (proactive loops, token file in the real repo) stays off.
client = TestClient(server.app, base_url="http://127.0.0.1:8760",
                    raise_server_exceptions=False)

r = client.get("/api/models", headers=GOOD)
check(r.status_code == 200, f"GET /api/models → 200 (got {r.status_code})")
models = r.json().get("models", []) if r.status_code == 200 else []
check(len(models) == len(server._MODELS) and not any(m["locked"] for m in models),
      "full roster, nothing locked")

r = client.post("/api/models/gemma/toggle", headers=GOOD)
check(r.status_code == 200 and r.json() == {"ok": True, "name": "Gemma 4 31B", "locked": True},
      "toggle by node id")
r = client.get("/api/models", headers=GOOD)
check(r.status_code == 200 and next(m for m in r.json()["models"] if m["id"] == "gemma")["locked"],
      "GET reflects the lock")
check(model_lock.is_locked("Gemma 4 31B"), "…and so does the router's view")
r = client.post("/api/models/Gemma 4 31B/toggle", headers=GOOD)
check(r.status_code == 200 and r.json().get("locked") is False, "toggle by display name")

for bad in ["not-a-model", "%F0%9F%A4%96", "gemma "]:
    r = client.post(f"/api/models/{bad}/toggle", headers=GOOD)
    check(r.status_code == 200 and r.json().get("ok") is False,
          f"unknown name {bad!r} refused ({r.status_code} {r.text[:60]})")
check(stored() == [], "…and nothing was stored for them")


# ── 4. carrying old QSettings locks over ──────────────────────────────────
print("\n[4] one-time carry-over from QSettings (PySide6 present)")
QS = {"locked/Gemma 4 31B": "true", "locked/GPT-OSS 20B": "false", "other/x": "true"}


class FakeQSettings:
    """Just the QSettings surface model_lock reads; values are strings, the
    way the Windows registry backend hands them back."""

    def __init__(self, org, app):
        assert (org, app) == ("AURA", "Models")
        self._group = ""

    def beginGroup(self, g):
        self._group = g + "/"

    def endGroup(self):
        self._group = ""

    def childKeys(self):
        return [k[len(self._group):] for k in QS if k.startswith(self._group)]

    def value(self, key, default=None, type=None):
        v = QS.get(self._group + key, default)
        return (str(v).lower() == "true") if type is bool else v


qtcore = types.ModuleType("PySide6.QtCore")
qtcore.QSettings = FakeQSettings
pyside = types.ModuleType("PySide6")
pyside.QtCore = qtcore
sys.modules["PySide6"], sys.modules["PySide6.QtCore"] = pyside, qtcore

mstore.DB_PATH = os.path.join(_TMP, "upgraded.db")   # a database from before
check(model_lock.is_locked("Gemma 4 31B"), "a lock saved in QSettings is honoured")
check(not model_lock.is_locked("GPT-OSS 20B"), "an unlocked QSettings entry stays unlocked")
check(stored() == ["Gemma 4 31B"], "carried into app_settings")
QS["locked/GPT-OSS 120B"] = "true"
model_lock.set_locked("Gemma 4 31B", False)
check(stored() == [] and not model_lock.is_locked("GPT-OSS 120B"),
      "runs once: later QSettings changes and unlocks don't bring locks back")

sys.modules["PySide6"] = None
sys.modules["PySide6.QtCore"] = None


finish()
