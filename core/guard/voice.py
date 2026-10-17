"""
core/guard/voice.py
-------------------
"Is that my buddy talking?" — speaker verification for voice messages.

The renderer already captures the mic and can encode an utterance as a
16 kHz mono WAV (it does exactly that for the speech-to-text fallback), so the
same bytes ride along with each voice message. Here they're trimmed to the
parts that are actually speech, turned into a TitaNet speaker embedding, and
compared with the owner's enrolled voice. Audio is never stored.

Short utterances are not trusted. Below MIN_VOICED_S of real speech the
embedding is too noisy to mean anything, so `embed()` returns no embedding and
the guard falls back to the camera — a quick "yes" doesn't lock anyone out, it
just gets checked the same way typing is.
"""

from __future__ import annotations

import io
import threading
import wave
from dataclasses import dataclass

from core.guard import models

RATE = 16000
FRAME = 480                 # 30 ms at 16 kHz
MIN_VOICED_S = 1.0          # less speech than this → don't judge by voice
MAX_SECONDS = 20            # cap what's analysed; a ramble adds nothing


@dataclass
class VoiceSample:
    embedding: list[float] | None   # None when there wasn't enough speech
    voiced_seconds: float


def decode_wav(data: bytes):
    """WAV bytes → float32 mono samples at 16 kHz."""
    import numpy as np
    with wave.open(io.BytesIO(data)) as w:
        ch, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(min(w.getnframes(), rate * MAX_SECONDS))
    if width == 2:
        a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 1:
        a = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128.0
    elif width == 4:
        a = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported WAV sample width: {width}")
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    if rate != RATE and len(a):
        # Linear resample — speaker embeddings are robust to it and it keeps
        # this free of scipy/librosa.
        n = int(len(a) * RATE / rate)
        a = np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)
    return a


def speech_only(a):
    """Drop the silence around and between words (energy VAD).

    The threshold is relative to the loud end of the clip (speech sits within
    ~20 dB of its peaks; room tone sits below), with an absolute floor so a
    silent clip doesn't promote its own hiss to "speech".
    """
    import numpy as np
    n = len(a) // FRAME
    if n == 0:
        return a[:0]
    frames = a[: n * FRAME].reshape(n, FRAME)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    thr = max(0.004, 0.12 * float(np.percentile(rms, 95)))
    keep = rms > thr
    # one frame of hangover each side so word edges aren't clipped
    keep = keep | np.roll(keep, 1) | np.roll(keep, -1)
    return frames[keep].reshape(-1)


class VoiceEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._extractor = None
        self._error = ""

    def available(self) -> tuple[bool, str]:
        if self._extractor is not None:
            return True, ""
        if self._error:
            return False, self._error
        try:
            try:
                import sherpa_onnx
            except ImportError as e:
                raise RuntimeError("sherpa-onnx isn't installed — run: pip install sherpa-onnx") from e
            cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=models.ensure("voice_embed"), num_threads=2)
            if not cfg.validate():
                raise RuntimeError("speaker model failed to load")
            self._extractor = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)
            return True, ""
        except Exception as e:  # noqa: BLE001
            self._error = str(e)
            return False, self._error

    def reset(self) -> None:
        self._error = ""

    def embed(self, wav_bytes: bytes) -> VoiceSample:
        ok, why = self.available()
        if not ok:
            raise RuntimeError(why)
        import numpy as np

        speech = speech_only(decode_wav(wav_bytes))
        voiced = len(speech) / RATE
        if voiced < MIN_VOICED_S:
            return VoiceSample(None, voiced)
        with self._lock:
            stream = self._extractor.create_stream()
            stream.accept_waveform(RATE, speech)
            stream.input_finished()
            vec = np.asarray(self._extractor.compute(stream), dtype=np.float32)
        n = float(np.linalg.norm(vec)) or 1.0
        return VoiceSample((vec / n).tolist(), voiced)


ENGINE = VoiceEngine()
