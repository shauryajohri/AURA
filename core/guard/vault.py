"""
core/guard/vault.py
-------------------
Who AURA's buddy is, on disk: memory/guard/buddy.json (gitignored).

Holds embeddings only — numbers derived from the enrollment frames and
recordings, never the frames or recordings themselves — plus a salted PBKDF2
hash of the backup PIN. Written atomically so a crash mid-save can't leave a
half-file that locks the owner out.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import secrets
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VAULT_PATH = os.environ.get("AURA_GUARD_VAULT") or os.path.join(ROOT, "memory", "guard", "buddy.json")

MAX_FACE_SAMPLES = 12
MAX_VOICE_SAMPLES = 8
PIN_ITERATIONS = 200_000

DEFAULTS = {
    "version": 1,
    "enabled": False,
    "owner_name": "",
    "face": [],    # unit-length SFace embeddings
    "voice": [],   # unit-length TitaNet embeddings
    "pin": None,   # {"salt": hex, "hash": hex, "iterations": n}
    "tuning": {
        # Cosine similarity needed to call a face / voice the owner's.
        # Face: SFace's published threshold is 0.363; this is stricter.
        # Voice: impostors stayed <= 0.40 in testing, the owner >= 0.69.
        "face_threshold": 0.42,
        "voice_threshold": 0.55,
    },
    "updated_at": None,
}


class Vault:
    def __init__(self, path: str = VAULT_PATH) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._data = self._read()

    # ── io ─────────────────────────────────────────────────────────────────
    def _read(self) -> dict:
        data = copy.deepcopy(DEFAULTS)
        try:
            with open(self.path, encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                tuning = {**data["tuning"], **(stored.get("tuning") or {})}
                data.update(stored)
                data["tuning"] = tuning
        except FileNotFoundError:
            pass
        except Exception as e:  # noqa: BLE001
            # A corrupt vault must not silently become "no owner, guard off" —
            # that would be the easiest bypass there is. Keep the guard ON
            # with nothing enrolled; only the PIN-less reset path recovers.
            print(f"[Guard] vault unreadable ({e}) — staying locked")
            data["enabled"] = True
            data["corrupt"] = True
        return data

    def _write(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f)
        os.replace(tmp, self.path)

    # ── reads ──────────────────────────────────────────────────────────────
    @property
    def enabled(self) -> bool:
        return bool(self._data.get("enabled"))

    @property
    def corrupt(self) -> bool:
        return bool(self._data.get("corrupt"))

    @property
    def owner_name(self) -> str:
        return self._data.get("owner_name") or "my buddy"

    @property
    def faces(self) -> list:
        return list(self._data.get("face") or [])

    @property
    def voices(self) -> list:
        return list(self._data.get("voice") or [])

    @property
    def has_pin(self) -> bool:
        return bool(self._data.get("pin"))

    def tuning(self, key: str) -> float:
        return float(self._data["tuning"].get(key, DEFAULTS["tuning"][key]))

    def summary(self) -> dict:
        return {
            "enabled": self.enabled,
            "owner_name": self._data.get("owner_name") or "",
            "face_samples": len(self.faces),
            "voice_samples": len(self.voices),
            "has_pin": self.has_pin,
            "corrupt": self.corrupt,
            "updated_at": self._data.get("updated_at"),
        }

    # ── writes ─────────────────────────────────────────────────────────────
    def set_owner_name(self, name: str) -> None:
        with self._lock:
            self._data["owner_name"] = (name or "").strip()[:40]
            self._write()

    def add_faces(self, embeddings: list, replace: bool = False) -> int:
        with self._lock:
            base = [] if replace else self.faces
            self._data["face"] = (base + list(embeddings))[-MAX_FACE_SAMPLES:]
            self._write()
            return len(self._data["face"])

    def add_voices(self, embeddings: list) -> int:
        with self._lock:
            self._data["voice"] = (self.voices + list(embeddings))[-MAX_VOICE_SAMPLES:]
            self._write()
            return len(self._data["voice"])

    def clear_voice(self) -> None:
        with self._lock:
            self._data["voice"] = []
            self._write()

    def set_pin(self, pin: str) -> None:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, PIN_ITERATIONS)
        with self._lock:
            self._data["pin"] = {"salt": salt.hex(), "hash": digest.hex(),
                                 "iterations": PIN_ITERATIONS}
            self._data.pop("pin_lockout", None)  # a new PIN starts clean
            self._write()

    def pin_lockout(self) -> tuple[int, float]:
        """(wrong attempts so far, blocked-until timestamp)."""
        rec = self._data.get("pin_lockout") or {}
        return int(rec.get("failures", 0)), float(rec.get("blocked_until", 0.0))

    def set_pin_lockout(self, failures: int, blocked_until: float) -> None:
        with self._lock:
            if failures or blocked_until:
                self._data["pin_lockout"] = {"failures": failures, "blocked_until": blocked_until}
            else:
                self._data.pop("pin_lockout", None)
            self._write()

    def check_pin(self, pin: str) -> bool:
        rec = self._data.get("pin")
        if not rec or not pin:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(rec["salt"]),
                                     int(rec.get("iterations", PIN_ITERATIONS)))
        return hmac.compare_digest(digest.hex(), rec["hash"])

    def set_enabled(self, on: bool) -> None:
        with self._lock:
            self._data["enabled"] = bool(on)
            self._data.pop("corrupt", None)
            self._write()

    def reset(self) -> None:
        """Forget the owner entirely (faces, voice, PIN) and switch off."""
        with self._lock:
            self._data = copy.deepcopy(DEFAULTS)
            self._write()
