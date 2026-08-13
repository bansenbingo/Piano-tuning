"""Decompose a mono audio signal into a sum of sinusoidal components.

The pipeline mirrors a typical Fourier-analysis teaching workflow:

1. Estimate the most energetic sinusoidal frequencies from the real FFT of a
   Hann-windowed signal using ``scipy.signal.find_peaks`` and parabolic peak
   interpolation for sub-bin frequency accuracy.
2. Fit ``c_i * cos(w_i * t) + s_i * sin(w_i * t)`` for every selected
   frequency with an ordinary least-squares solve. Chunked normal equations keep
   memory bounded for longer recordings.
3. Convert each fitted pair to the equivalent sine form
   ``A_i * sin(2*pi*f_i*t + phi_i)`` and assemble the analytical expression.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import signal

MIN_FREQ_HZ = 20.0
MAX_COMPONENTS = 50
MAX_FIT_SAMPLES = 400_000
PEAK_MIN_DISTANCE_HZ = 5.0
PEAK_HEIGHT_RATIO = 1e-4
RIDGE_EPS = 1e-9
CHUNK_SAMPLES = 20_000


class DecompositionError(ValueError):
    """Raised when a signal cannot be decomposed into sinusoids."""


def _prepare_signal(x: np.ndarray, sample_rate: float) -> tuple[np.ndarray, float]:
    """Validate, center, and optionally anti-alias resample a mono signal."""

    x = np.asarray(x, dtype=np.float64)
    if x.ndim != 1:
        raise DecompositionError("Signal must be one-dimensional.")
    if x.size < 4:
        raise DecompositionError("Signal is too short to analyze.")
    if not math.isfinite(float(sample_rate)) or sample_rate <= 0:
        raise DecompositionError("Sample rate must be a positive number.")

    original_size = x.size
    x = x - float(np.mean(x))  # Remove the DC offset before fitting sinusoids.

    if x.size > MAX_FIT_SAMPLES:
        x = signal.resample(x, MAX_FIT_SAMPLES)
        sample_rate = sample_rate * (x.size / original_size)

    return x, sample_rate


def _refine_peak(frequencies: np.ndarray, magnitude: np.ndarray, peak_index: int) -> float:
    """Refine a spectrum peak to sub-bin resolution via parabolic interpolation."""

    if peak_index <= 0 or peak_index >= magnitude.size - 1:
        return float(frequencies[peak_index])

    spacing = float(frequencies[1] - frequencies[0])
    lower = math.log(max(float(magnitude[peak_index - 1]), 1e-30))
    center = math.log(max(float(magnitude[peak_index]), 1e-30))
    upper = math.log(max(float(magnitude[peak_index + 1]), 1e-30))
    denominator = lower - 2.0 * center + upper
    if abs(denominator) < 1e-12:
        return float(frequencies[peak_index])

    offset = 0.5 * (lower - upper) / denominator
    offset = float(np.clip(offset, -0.5, 0.5))
    return float(frequencies[peak_index]) + offset * spacing


def _detect_frequencies(x: np.ndarray, sample_rate: float, num_components: int) -> list[float]:
    """Return the ``num_components`` most energetic frequencies, low to high."""

    size = x.size
    windowed = x * signal.windows.hann(size, sym=False)
    spectrum = np.fft.rfft(windowed)
    magnitude = np.abs(spectrum)
    frequencies = np.fft.rfftfreq(size, 1.0 / sample_rate)

    first_bin = int(np.searchsorted(frequencies, MIN_FREQ_HZ))
    min_distance_bins = max(1, math.ceil(PEAK_MIN_DISTANCE_HZ * size / sample_rate))
    peaks, _ = signal.find_peaks(
        magnitude,
        distance=min_distance_bins,
        height=float(magnitude.max()) * PEAK_HEIGHT_RATIO,
    )
    peaks = peaks[peaks >= first_bin]
    if peaks.size == 0:
        raise DecompositionError("No sinusoidal peaks found in the signal.")

    peaks = peaks[np.argsort(magnitude[peaks])[::-1]][:num_components]
    peaks = peaks[np.argsort(frequencies[peaks])]
    return [_refine_peak(frequencies, magnitude, int(index)) for index in peaks]


def _fit_sinusoids(x: np.ndarray, sample_rate: float, frequencies: list[float]) -> np.ndarray:
    """Least-squares fit cosine/sine pairs for each frequency.

    Returns interleaved coefficients ``[c_0, s_0, c_1, s_1, ...]`` so that each
    component equals ``c_i * cos(w_i * t) + s_i * sin(w_i * t)``.
    """

    size = x.size
    time = np.arange(size, dtype=np.float64) / sample_rate
    column_count = 2 * len(frequencies)
    ata = np.zeros((column_count, column_count), dtype=np.float64)
    aty = np.zeros(column_count, dtype=np.float64)

    for start in range(0, size, CHUNK_SAMPLES):
        stop = min(start + CHUNK_SAMPLES, size)
        block_time = time[start:stop]
        block_signal = x[start:stop]
        columns = []
        for frequency in frequencies:
            omega = 2.0 * math.pi * frequency
            columns.append(np.cos(omega * block_time))
            columns.append(np.sin(omega * block_time))
        block = np.column_stack(columns)
        ata += block.T @ block
        aty += block.T @ block_signal

    ridge = RIDGE_EPS * (float(np.trace(ata)) / column_count if column_count else 1.0)
    return np.linalg.solve(ata + ridge * np.eye(column_count), aty)


def _format_component(frequency: float, amplitude: float, phase: float) -> str:
    return f"{amplitude:.5g}·sin(2π·{frequency:.3f}·t + {phase:.3f})"


def _format_sum(components: list[dict[str, Any]]) -> str:
    if not components:
        return "s(t) = 0"
    return "s(t) = " + " + ".join(component["expression"] for component in components)


def decompose(x: np.ndarray, sample_rate: float, num_components: int) -> dict[str, Any]:
    """Split ``x`` into ``num_components`` sine waves and describe them analytically.

    Returns the centered analysis signal, its effective sample rate, the fitted
    component metadata, per-component waveforms, the summed reconstruction, and
    the printable analytical expression.
    """

    num_components = int(num_components)
    if num_components < 1:
        raise DecompositionError("At least one component is required.")
    num_components = min(num_components, MAX_COMPONENTS)

    signal_centered, analysis_rate = _prepare_signal(x, float(sample_rate))
    frequencies = _detect_frequencies(signal_centered, analysis_rate, num_components)
    coefficients = _fit_sinusoids(signal_centered, analysis_rate, frequencies)

    time = np.arange(signal_centered.size, dtype=np.float64) / analysis_rate
    components: list[dict[str, Any]] = []
    component_waves: list[np.ndarray] = []

    for index, frequency in enumerate(frequencies):
        omega = 2.0 * math.pi * frequency
        cosine = float(coefficients[2 * index])
        sine = float(coefficients[2 * index + 1])
        amplitude = math.hypot(cosine, sine)
        phase = math.atan2(cosine, sine)  # Converts c*cos + s*sin to A*sin(wt+phi).
        component_waves.append(cosine * np.cos(omega * time) + sine * np.sin(omega * time))
        components.append(
            {
                "index": index + 1,
                "frequency": frequency,
                "amplitude": amplitude,
                "phase": phase,
                "expression": _format_component(frequency, amplitude, phase),
            }
        )

    reconstruction = (
        np.sum(component_waves, axis=0) if component_waves else np.zeros_like(signal_centered)
    )

    return {
        "signal": signal_centered,
        "sample_rate": analysis_rate,
        "components": components,
        "component_waves": component_waves,
        "reconstruction": reconstruction,
        "expression": _format_sum(components),
    }
