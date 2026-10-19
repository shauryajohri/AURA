"""
core/guard/face.py
------------------
"Who is in front of the camera?" — detection + identity embeddings.

The frame arrives as JPEG bytes from the renderer (the browser owns the
camera, exactly like it owns the mic for voice). It is decoded, analysed and
dropped: no frame is ever written to disk. What persists is only the 128-d
embedding of the owner's face, made at enrollment.

Pure OpenCV (YuNet + SFace) — no dlib, no PyTorch, installs cleanly on
Windows with `pip install opencv-python-headless`.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from core.guard import models

# Longest side the detector sees. Webcam frames are 640-1280 wide; 640 keeps
# detection ~15 ms on a laptop CPU and faces at arm's length stay well above
# YuNet's minimum size.
MAX_SIDE = 640
DETECT_SCORE = 0.80
# A face this narrow (px, after scaling to MAX_SIDE) is someone across the
# room — it can count as "present" but it's too small to enroll from.
ENROLL_MIN_WIDTH = 90


@dataclass
class Face:
    box: tuple[int, int, int, int]       # x, y, w, h in the analysed frame
    score: float                         # detector confidence
    embedding: list[float] = field(repr=False)  # unit-length SFace vector

    @property
    def area(self) -> int:
        return self.box[2] * self.box[3]


def cosine(a, b) -> float:
    """Cosine similarity of two embeddings (both are stored unit-length, but
    normalise anyway — a hand-edited vault shouldn't be able to skew it)."""
    import numpy as np
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(a @ b) / (na * nb)


def best_match(embedding, enrolled: list) -> float:
    """Highest similarity against any enrolled sample. Max (not mean) because
    enrollment deliberately covers several angles — the frontal sample should
    win for a frontal face, the turned one for a turned face."""
    return max((cosine(embedding, e) for e in enrolled), default=0.0)


class FaceEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._detector = None
        self._recognizer = None
        self._error = ""

    # ── lifecycle ──────────────────────────────────────────────────────────
    def available(self) -> tuple[bool, str]:
        """(ok, reason). Loads lazily; a failure is remembered so a missing
        package doesn't re-raise on every frame."""
        if self._recognizer is not None:
            return True, ""
        if self._error:
            return False, self._error
        try:
            self._load()
            return True, ""
        except Exception as e:  # noqa: BLE001
            self._error = str(e)
            return False, self._error

    def _load(self) -> None:
        try:
            import cv2
        except ImportError as e:
            raise RuntimeError("opencv isn't installed — run: pip install opencv-python-headless") from e
        create_det = getattr(cv2, "FaceDetectorYN", None)
        create_rec = getattr(cv2, "FaceRecognizerSF", None)
        if create_det is None or create_rec is None:
            raise RuntimeError(f"OpenCV {cv2.__version__} is too old for face ID — need 4.8+")
        det_path = models.ensure("face_detect")
        rec_path = models.ensure("face_embed")
        self._detector = create_det.create(det_path, "", (320, 320), DETECT_SCORE, 0.3, 50)
        self._recognizer = create_rec.create(rec_path, "")

    def reset(self) -> None:
        """Forget a cached failure — e.g. after the user installs opencv."""
        self._error = ""

    # ── analysis ───────────────────────────────────────────────────────────
    def analyze(self, image_bytes: bytes) -> list[Face]:
        """Every face in the frame, largest first. Raises ValueError for an
        undecodable image and RuntimeError if the engine can't load."""
        ok, why = self.available()
        if not ok:
            raise RuntimeError(why)
        import cv2
        import numpy as np

        img = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("frame is not a decodable image")
        h, w = img.shape[:2]
        scale = MAX_SIDE / max(h, w)
        if scale < 1:
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            h, w = img.shape[:2]

        out: list[Face] = []
        # cv2.dnn nets are not safe to run concurrently — one frame at a time.
        with self._lock:
            self._detector.setInputSize((w, h))
            _, rows = self._detector.detect(img)
            for row in rows if rows is not None else []:
                aligned = self._recognizer.alignCrop(img, row)
                vec = self._recognizer.feature(aligned).flatten().astype(np.float32)
                n = float(np.linalg.norm(vec)) or 1.0
                x, y, bw, bh = (int(v) for v in row[:4])
                out.append(Face(box=(x, y, bw, bh), score=float(row[-1]),
                                embedding=(vec / n).tolist()))
        out.sort(key=lambda f: f.area, reverse=True)
        return out


ENGINE = FaceEngine()
