"""
core/guard/models.py
--------------------
The three ONNX files Buddy Lock runs on, and how they get onto the machine.

None of them are committed: two are ~40 MB and all are someone else's
release artifacts. They're fetched once, on first use, into models/guard/
(gitignored) and verified by SHA-256 so a truncated download or a swapped
file can never quietly become the thing that decides who AURA talks to.

    python -m core.guard.models        # fetch everything up front

Why these three
---------------
face_detect   YuNet (OpenCV Zoo). Tiny, fast, built for exactly this:
              find faces in a webcam frame. Runs natively in cv2.
face_embed    SFace (OpenCV Zoo). 128-d identity embedding, native cv2.
              Same person scored 0.75-0.97, different people <= 0.12 in
              the samples this was tuned on.
voice_embed   NeMo TitaNet-small via sherpa-onnx. Picked over five other
              speaker models after a side-by-side on real recordings: it
              was the only small model with a clean gap between the owner
              (>= 0.69) and impostors (<= 0.40). No PyTorch needed.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_DIR = os.environ.get("AURA_GUARD_MODEL_DIR") or os.path.join(ROOT, "models", "guard")

_ZOO = "opencv/opencv_zoo/main/models"
_SHERPA = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
           "speaker-recongition-models")  # (sic — that's the real tag name)

MODELS: dict[str, dict] = {
    "face_detect": {
        "file": "face_detection_yunet_2023mar.onnx",
        "sha256": "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        "urls": [
            f"https://media.githubusercontent.com/media/{_ZOO}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
            f"https://github.com/{_ZOO.replace('/main/', '/raw/main/')}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        ],
    },
    "face_embed": {
        "file": "face_recognition_sface_2021dec.onnx",
        "sha256": "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
        "urls": [
            f"https://media.githubusercontent.com/media/{_ZOO}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
            f"https://github.com/{_ZOO.replace('/main/', '/raw/main/')}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        ],
    },
    "voice_embed": {
        "file": "nemo_en_titanet_small.onnx",
        "sha256": "ad4a1802485d8b34c722d2a9d04249662f2ece5d28a7a039063ca22f515a789e",
        "urls": [f"{_SHERPA}/nemo_en_titanet_small.onnx"],
    },
}

_lock = threading.Lock()


class ModelUnavailable(RuntimeError):
    """The model isn't on disk and couldn't be fetched (offline, blocked)."""


def path_for(name: str) -> str:
    return os.path.join(MODEL_DIR, MODELS[name]["file"])


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _valid(name: str, path: str) -> bool:
    if not os.path.isfile(path) or os.path.getsize(path) < 100_000:
        return False  # a 378-byte JSON error page is not a model
    want = MODELS[name].get("sha256")
    return want is None or _sha256(path) == want


def is_present(name: str) -> bool:
    return _valid(name, path_for(name))


def ensure(name: str, timeout: float = 120.0) -> str:
    """Return the local path to a model, downloading it the first time.

    Raises ModelUnavailable with a human-readable reason if it can't be had.
    """
    path = path_for(name)
    if _valid(name, path):
        return path
    with _lock:
        if _valid(name, path):  # another thread just fetched it
            return path
        os.makedirs(MODEL_DIR, exist_ok=True)
        errors = []
        for url in MODELS[name]["urls"]:
            fd, tmp = tempfile.mkstemp(dir=MODEL_DIR, suffix=".part")
            os.close(fd)
            try:
                print(f"[Guard] downloading {MODELS[name]['file']} …")
                req = urllib.request.Request(url, headers={"User-Agent": "AURA-guard"})
                with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as out:
                    while True:
                        block = r.read(1 << 20)
                        if not block:
                            break
                        out.write(block)
                if not _valid(name, tmp):
                    raise ValueError("download failed verification (size/sha256)")
                os.replace(tmp, path)
                print(f"[Guard] ready: {path}")
                return path
            except Exception as e:  # noqa: BLE001 - try the next mirror
                errors.append(f"{url}: {e}")
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
        raise ModelUnavailable(
            f"couldn't fetch {MODELS[name]['file']} — put it in {MODEL_DIR} by hand. "
            + " | ".join(errors))


if __name__ == "__main__":
    for key in MODELS:
        try:
            print(f"{key:12} {ensure(key)}")
        except ModelUnavailable as e:
            print(f"{key:12} FAILED — {e}")
