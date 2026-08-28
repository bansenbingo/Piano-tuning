"""Noise-reduction filtering for single-note piano recordings."""

from __future__ import annotations

import numpy as np
from scipy import signal

DEFAULT_LOWCUT_HZ = 20.0
DEFAULT_HIGHCUT_HZ = 12_000.0


class FilterError(ValueError):
    """Raised when the band-pass parameters are invalid."""


def denoise(
    x: np.ndarray,
    sample_rate: float,
    lowcut_hz: float = DEFAULT_LOWCUT_HZ,
    highcut_hz: float = DEFAULT_HIGHCUT_HZ,
) -> np.ndarray:
    """Return a zero-phase band-pass filtered copy of a mono signal.

    The high-pass edge removes DC drift and low-frequency rumble while the
    low-pass edge removes high-frequency hiss; ``sosfiltfilt`` preserves phase
    so the fitted sine phases remain meaningful.
    """

    x = np.asarray(x, dtype=np.float64)
    if x.ndim != 1 or x.size < 4:
        raise FilterError("Signal must be a one-dimensional array of at least 4 samples.")

    nyquist = 0.5 * float(sample_rate)
    low = float(lowcut_hz)
    high = float(highcut_hz)
    if low <= 0:
        raise FilterError("Low cutoff frequency must be positive.")
    high = min(high, 0.95 * nyquist)
    if low >= high:
        raise FilterError("Low cutoff frequency must be below the high cutoff frequency.")

    sos = signal.butter(4, [low, high], btype="bandpass", fs=float(sample_rate), output="sos")
    return signal.sosfiltfilt(sos, x)
