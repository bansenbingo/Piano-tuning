"""WAV decoding helpers for the Flask application."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf


class AudioReadError(RuntimeError):
    """Raised when a WAV file cannot be decoded."""


def read_wav_mono(path: Path, *, max_samples: int | None = None) -> tuple[np.ndarray, int]:
    """Decode a WAV file to a float64 mono signal and its sample rate."""

    try:
        data, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception as exc:  # soundfile raises several backend-specific errors.
        raise AudioReadError(f"Unable to read {path.name}: {exc}") from exc

    mono = data.mean(axis=1).astype(np.float64)
    if max_samples and mono.size > max_samples:
        mono = mono[:max_samples]
    return mono, int(sample_rate)
