"""Tests for the sinusoidal decomposition pipeline."""

from __future__ import annotations

import math

import numpy as np
import pytest

from analyzer.decomposition import DecompositionError, decompose
from analyzer.reporting import build_markdown_report
from analyzer.visualization import build_phasor_figure


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
    assert result["model"]["inharmonicity"] == pytest.approx(0.0, abs=1e-6)

    for expected_frequency, expected_amplitude, expected_phase in zip(
        frequencies, amplitudes, phases
    ):
        component = min(
            result["components"], key=lambda item: abs(item["frequency"] - expected_frequency)
        )
        assert component["frequency"] == pytest.approx(expected_frequency, abs=0.5)
        assert component["amplitude"] == pytest.approx(expected_amplitude, abs=1e-3)
        assert abs(_phase_difference(component["phase"], expected_phase)) < 1e-2


def test_decompose_outputs_consecutive_inharmonic_partials():
    fundamental = 220.0
    inharmonicity = 0.0008
    ranks = np.arange(1, 5, dtype=np.float64)
    frequencies = (ranks * fundamental * np.sqrt(1.0 + inharmonicity * ranks**2)).tolist()
    signal = _synthetic_signal(frequencies, [0.8, 0.35, 0.2, 0.1], [0.1, -0.4, 1.0, 2.1])

    result = decompose(signal, 48_000, 4)

    assert result["model"]["formula"] == "f_n = n·F0·√(1 + B·n²)"
    assert result["model"]["fundamental_frequency"] == pytest.approx(fundamental, abs=0.5)
    assert result["model"]["inharmonicity"] == pytest.approx(inharmonicity, abs=2e-4)
    assert [component["partial_rank"] for component in result["components"]] == [1, 2, 3, 4]
    for rank, component, expected_frequency in zip(ranks.astype(int), result["components"], frequencies):
        assert component["frequency"] == pytest.approx(expected_frequency, abs=0.5)
        assert f"f_{rank}" in component["frequency_formula"]


def test_decompose_rejects_invalid_inputs():
    with pytest.raises(DecompositionError):
        decompose(np.zeros(3), 48_000, 3)

    with pytest.raises(DecompositionError):
        decompose(np.zeros(100), 48_000, 0)


def test_report_includes_frequencies_and_equations_without_svg():
    result = decompose(_synthetic_signal([440.0], [0.8], [0.3]), 48_000, 1)
    report = build_markdown_report(
        "tone.wav", result["components"], result["expression"], 48_000, 1.0
    )

    assert "# 音频正弦波分解报告" in report
    assert "频率 (Hz)" in report
    assert result["components"][0]["expression"] in report
    assert "<svg" not in report
    assert "分解正弦波相量矢量图" not in report
    assert len(build_phasor_figure(result["components"]).data) == 1
