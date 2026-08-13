"""Tests for the sinusoidal decomposition pipeline."""

from __future__ import annotations

import math

import numpy as np
import pytest

from analyzer.decomposition import DecompositionError, decompose


def _phase_difference(first: float, second: float) -> float:
    """Return the signed angular difference, wrapped to [-pi, pi]."""

    return (first - second + math.pi) % (2 * math.pi) - math.pi


def _synthetic_signal(
    frequencies: list[float],
    amplitudes: list[float],
    phases: list[float],
    sample_rate: int = 48_000,
    duration: float = 1.0,
) -> np.ndarray:
    time = np.arange(int(sample_rate * duration), dtype=np.float64) / sample_rate
    signal = np.zeros_like(time)
    for frequency, amplitude, phase in zip(frequencies, amplitudes, phases):
        signal += amplitude * np.sin(2 * math.pi * frequency * time + phase)
    return signal


def test_decompose_recovers_three_sines():
    frequencies = [440.0, 880.0, 1320.0]
    amplitudes = [0.8, 0.35, 0.12]
    phases = [0.3, -1.2, 2.0]
    signal = _synthetic_signal(frequencies, amplitudes, phases)

    result = decompose(signal, 48_000, 3)

    assert len(result["components"]) == 3
    assert result["expression"].startswith("s(t) = ")
    assert result["reconstruction"].shape == signal.shape

    for expected_frequency, expected_amplitude, expected_phase in zip(
        frequencies, amplitudes, phases
    ):
        component = min(
            result["components"], key=lambda item: abs(item["frequency"] - expected_frequency)
        )
        assert component["frequency"] == pytest.approx(expected_frequency, abs=0.5)
        assert component["amplitude"] == pytest.approx(expected_amplitude, abs=1e-3)
        assert abs(_phase_difference(component["phase"], expected_phase)) < 1e-2


def test_decompose_rejects_invalid_inputs():
    with pytest.raises(DecompositionError):
        decompose(np.zeros(3), 48_000, 3)

    with pytest.raises(DecompositionError):
        decompose(np.zeros(100), 48_000, 0)
