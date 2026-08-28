"""Tests for the band-pass noise filter."""

from __future__ import annotations

import numpy as np
import pytest

from analyzer.filtering import FilterError, denoise


def test_denoise_removes_dc_and_high_frequency_components():
    sample_rate = 48_000
    time = np.arange(sample_rate, dtype=np.float64) / sample_rate
    signal = 1.0 + np.sin(2 * np.pi * 440.0 * time) + 0.5 * np.sin(2 * np.pi * 20_000.0 * time)

    filtered = denoise(signal, sample_rate, lowcut_hz=20.0, highcut_hz=12_000.0)

    assert filtered.shape == signal.shape
    assert abs(float(np.mean(filtered))) < 0.05  # DC offset removed by the high-pass edge.
    assert float(np.std(filtered)) < float(np.std(signal))


def test_denoise_rejects_invalid_cutoffs():
    signal = np.zeros(100)
    with pytest.raises(FilterError):
        denoise(signal, 48_000, lowcut_hz=-1.0)
    with pytest.raises(FilterError):
        denoise(signal, 48_000, lowcut_hz=12_000.0, highcut_hz=20.0)
