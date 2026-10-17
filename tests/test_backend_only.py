"""
Backend-only install (requirements-web.txt): the price feed (yfinance, ta,
pandas) and the clipboard (pyperclip) aren't installed. A forex question or a
clipboard save must get a reply saying what's missing, not an error frame.

Blocks those imports, then asks over the real /ws. Offline, throwaway DB.

Run:  PYTHONPATH=. python tests/test_backend_only.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# what a requirements-web.txt install lacks
for mod in ("yfinance", "ta", "pandas", "pyperclip"):
    sys.modules[mod] = None

_TMP = tempfile.mkdtemp(prefix="aura_backend_only_")
os.environ["AURA_GUARD_VAULT"] = os.path.join(_TMP, "buddy.json")

import memory.store as mstore  # noqa: E402
mstore.DB_PATH = os.path.join(_TMP, "test.db")
mstore.init_db()
mstore.init_tasks()

from fastapi.testclient import TestClient  # noqa: E402

import local_auth  # noqa: E402
import server  # noqa: E402
from core import brain  # noqa: E402

_fails: list[str] = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'} — {label}")
    if not cond:
        _fails.append(label)


print("\n[1] the helpers explain instead of raising")
try:
    quote = brain._forex_quote("gold price today")
except Exception as e:  # noqa: BLE001
    quote = f"{type(e).__name__}: {e}"
check("full install" in quote and "requirements.txt" in quote, f"forex: {quote!r}")
try:
    saved = brain._save_clipboard()
except Exception as e:  # noqa: BLE001
    saved = f"{type(e).__name__}: {e}"
check("full install" in saved, f"clipboard save: {saved!r}")

print("\n[2] a forex question over /ws gets that line, not an error frame")
client = TestClient(server.app, base_url="http://127.0.0.1:8760")
with client.websocket_connect("ws://127.0.0.1:8760/ws",
                              subprotocols=["aura", "aura-token." + local_auth.TOKEN]) as ws:
    ws.send_json({"type": "message", "payload": {"text": "what's the gold price today?"}})
    frames = []
    for _ in range(40):
        m = ws.receive_json()
        frames.append(m)
        if m.get("type") in ("done", "error"):
            break
kinds = [f.get("type") for f in frames]
done = next((f for f in frames if f.get("type") == "done"), {})
check("error" not in kinds, f"no error frame ({kinds})")
check("full install" in (done.get("payload") or {}).get("text", ""),
      f"done text explains ({(done.get('payload') or {}).get('text', '')[:80]!r})")


print("\n" + ("ALL PASS ✅" if not _fails else f"FAILURES ({len(_fails)}): {_fails}"))
sys.exit(1 if _fails else 0)
