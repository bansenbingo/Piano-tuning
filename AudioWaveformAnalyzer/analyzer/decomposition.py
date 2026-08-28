"""Decompose a piano note into inharmonic partials.

Every emitted partial follows the stiff-string law from Rigaud, David and
Daudet, *A Parametric Model of Piano Tuning* (DAFx-11, 2011):

``f_n = n * F0 * sqrt(1 + B * n**2)``.

The analyser estimates the flexible-string fundamental ``F0`` and the
non-negative inharmonicity coefficient ``B`` from FFT peaks, then fits the
amplitude and phase of the requested consecutive partial ranks.  This keeps
the returned waveforms physically related instead of treating every strong
spectrum peak as an unrelated sine wave.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import optimize, signal

MIN_FREQ_HZ = 20.0
MAX_COMPONENTS = 50
MAX_FIT_SAMPLES = 400_000
PEAK_MIN_DISTANCE_HZ = 5.0
PEAK_HEIGHT_RATIO = 1e-4
RIDGE_EPS = 1e-9
CHUNK_SAMPLES = 20_000
MAX_INHARMONICITY = 0.1
MODEL_SCORE_TOLERANCE_HZ = 2.5
MAX_MODEL_PEAKS = 96
MAX_MODEL_RANK = 12


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


def _spectral_peaks(
    x: np.ndarray, sample_rate: float
) -> tuple[np.ndarray, np.ndarray]:
    """Return refined FFT-peak frequencies and their magnitudes."""

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

    strongest = peaks[np.argsort(magnitude[peaks])[::-1][:MAX_MODEL_PEAKS]]
    strongest = strongest[np.argsort(frequencies[strongest])]
    refined = np.asarray(
        [_refine_peak(frequencies, magnitude, int(index)) for index in strongest], dtype=np.float64
    )
    return refined, magnitude[strongest]


def _partial_frequency(fundamental: float, inharmonicity: float, rank: int) -> float:
    """Return ``f_n = n F0 sqrt(1 + B n²)`` for one positive partial rank."""

    return rank * fundamental * math.sqrt(1.0 + inharmonicity * rank * rank)


def _model_frequencies(
    fundamental: float, inharmonicity: float, num_components: int
) -> list[float]:
    return [
        _partial_frequency(fundamental, inharmonicity, rank)
        for rank in range(1, num_components + 1)
    ]


def _nearest_peak(
    peak_frequencies: np.ndarray, target: float
) -> tuple[float, int]:
    """Return the closest detected peak to ``target`` and its array index."""

    right = int(np.searchsorted(peak_frequencies, target))
    if right == 0:
        index = 0
    elif right == peak_frequencies.size:
        index = peak_frequencies.size - 1
    else:
        left = right - 1
        index = left if target - peak_frequencies[left] <= peak_frequencies[right] - target else right
    return float(peak_frequencies[index]), index


def _candidate_fundamentals(
    peak_frequencies: np.ndarray, num_components: int, nyquist: float
) -> np.ndarray:
    """Generate F0 candidates by assigning detected peaks to possible ranks."""

    max_rank = min(max(num_components, 6), MAX_MODEL_RANK)
    values: list[float] = []
    for frequency in peak_frequencies:
        for rank in range(1, max_rank + 1):
            fundamental = float(frequency) / rank
            if MIN_FREQ_HZ <= fundamental < nyquist:
                values.append(fundamental)
    if not values:
        raise DecompositionError("Could not derive a plausible fundamental frequency.")
    return np.unique(np.asarray(values, dtype=np.float64))


def _model_score(
    fundamental: float,
    inharmonicity: float,
    peak_frequencies: np.ndarray,
    peak_magnitudes: np.ndarray,
    num_components: int,
) -> float:
    """Score how well a candidate stiff-string model is supported by FFT peaks."""

    normalized = peak_magnitudes / max(float(np.max(peak_magnitudes)), 1e-30)
    score = 0.0
    matched = 0
    modeled_ranks = min(num_components, MAX_MODEL_RANK)
    for rank, expected in enumerate(
        _model_frequencies(fundamental, inharmonicity, modeled_ranks), start=1
    ):
        observed, index = _nearest_peak(peak_frequencies, expected)
        # A small relative allowance accommodates high partials and short recordings.
        tolerance = max(MODEL_SCORE_TOLERANCE_HZ, expected * 0.002)
        distance = abs(observed - expected)
        if distance <= tolerance:
            matched += 1
            score += float(normalized[index]) * math.exp(-0.5 * (distance / tolerance) ** 2)

    # A model representing just one coincidental peak must not win over a harmonic series.
    return score + 0.05 * matched


def _estimate_inharmonic_model(
    x: np.ndarray, sample_rate: float, num_components: int
) -> tuple[float, float]:
    """Estimate ``(F0, B)`` from FFT peaks with a robust stiff-string fit."""

    peak_frequencies, peak_magnitudes = _spectral_peaks(x, sample_rate)
    nyquist = sample_rate / 2.0
    candidates = _candidate_fundamentals(peak_frequencies, num_components, nyquist)
    # Include zero for harmonic signals, then cover piano-scale B values logarithmically.
    inharmonicity_grid = np.concatenate(([0.0], np.logspace(-7, -1, 49)))

    best_score = -math.inf
    best_model: tuple[float, float] | None = None
    for fundamental in candidates:
        for inharmonicity in inharmonicity_grid:
            frequencies = _model_frequencies(fundamental, float(inharmonicity), num_components)
            if frequencies[-1] >= nyquist:
                continue
            score = _model_score(
                fundamental,
                float(inharmonicity),
                peak_frequencies,
                peak_magnitudes,
                num_components,
            )
            if score > best_score:
                best_score = score
                best_model = (float(fundamental), float(inharmonicity))

    if best_model is None:
        raise DecompositionError("Requested partial ranks exceed the available frequency range.")

    initial_fundamental, initial_inharmonicity = best_model
    ranks: list[int] = []
    observed_frequencies: list[float] = []
    modeled_ranks = min(num_components, MAX_MODEL_RANK)
    for rank, expected in enumerate(
        _model_frequencies(initial_fundamental, initial_inharmonicity, modeled_ranks), start=1
    ):
        observed, _ = _nearest_peak(peak_frequencies, expected)
        tolerance = max(MODEL_SCORE_TOLERANCE_HZ, expected * 0.002)
        if abs(observed - expected) <= tolerance:
            ranks.append(rank)
            observed_frequencies.append(observed)

    if num_components == 1 or len(ranks) < 2:
        # B is not identifiable from one partial; retain the harmonic model in that case.
        return initial_fundamental, 0.0

    rank_array = np.asarray(ranks, dtype=np.float64)
    observed_array = np.asarray(observed_frequencies, dtype=np.float64)

    def residual(parameters: np.ndarray) -> np.ndarray:
        fundamental, inharmonicity = parameters
        expected = rank_array * fundamental * np.sqrt(1.0 + inharmonicity * rank_array**2)
        # Relative residuals avoid the highest partial dominating the robust fit.
        return (expected - observed_array) / np.maximum(observed_array, 1.0)

    fit = optimize.least_squares(
        residual,
        x0=np.asarray([initial_fundamental, initial_inharmonicity]),
        bounds=([MIN_FREQ_HZ, 0.0], [nyquist, MAX_INHARMONICITY]),
        loss="soft_l1",
        f_scale=1e-4,
    )
    return float(fit.x[0]), float(fit.x[1])


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


def _format_component(
    rank: int, fundamental: float, inharmonicity: float, frequency: float, amplitude: float, phase: float
) -> str:
    return (
        f"f_{rank}={rank}·F0·√(1+B·{rank}²)={frequency:.3f} Hz; "
        f"{amplitude:.5g}·sin(2π·f_{rank}·t + {phase:.3f})"
    )


def _format_sum(
    components: list[dict[str, Any]], fundamental: float, inharmonicity: float
) -> str:
    if not components:
        return "s(t) = 0"
    return (
        "s(t) = Σ A_n·sin(2π·[n·F0·√(1+B·n²)]·t + φ_n), "
        f"n=1…{len(components)}; F0={fundamental:.6f} Hz, B={inharmonicity:.6g}"
    )


def decompose(x: np.ndarray, sample_rate: float, num_components: int) -> dict[str, Any]:
    """Return consecutive stiff-string partial waves for a mono piano note.

    ``num_components`` is the number of ranks to return, so the output always
    contains ``f_1`` through ``f_n`` under one shared ``F0`` and ``B`` model.
    """

    num_components = int(num_components)
    if num_components < 1:
        raise DecompositionError("At least one component is required.")
    num_components = min(num_components, MAX_COMPONENTS)

    signal_centered, analysis_rate = _prepare_signal(x, float(sample_rate))
    fundamental, inharmonicity = _estimate_inharmonic_model(
        signal_centered, analysis_rate, num_components
    )
    frequencies = _model_frequencies(fundamental, inharmonicity, num_components)
    coefficients = _fit_sinusoids(signal_centered, analysis_rate, frequencies)

    time = np.arange(signal_centered.size, dtype=np.float64) / analysis_rate
    components: list[dict[str, Any]] = []
    component_waves: list[np.ndarray] = []

    for index, frequency in enumerate(frequencies):
        rank = index + 1
        omega = 2.0 * math.pi * frequency
        cosine = float(coefficients[2 * index])
        sine = float(coefficients[2 * index + 1])
        amplitude = math.hypot(cosine, sine)
        phase = math.atan2(cosine, sine)  # Converts c*cos + s*sin to A*sin(wt+phi).
        component_waves.append(cosine * np.cos(omega * time) + sine * np.sin(omega * time))
        components.append(
            {
                "index": index + 1,
                "partial_rank": rank,
                "frequency": frequency,
                "frequency_formula": (
                    f"f_{rank} = {rank}·F0·√(1 + B·{rank}²) = {frequency:.6f} Hz"
                ),
                "amplitude": amplitude,
                "phase": phase,
                "expression": _format_component(
                    rank, fundamental, inharmonicity, frequency, amplitude, phase
                ),
            }
        )

    reconstruction = (
        np.sum(component_waves, axis=0) if component_waves else np.zeros_like(signal_centered)
    )

    return {
        "signal": signal_centered,
        "sample_rate": analysis_rate,
        "model": {
            "fundamental_frequency": fundamental,
            "inharmonicity": inharmonicity,
            "formula": "f_n = n·F0·√(1 + B·n²)",
        },
        "components": components,
        "component_waves": component_waves,
        "reconstruction": reconstruction,
        "expression": _format_sum(components, fundamental, inharmonicity),
    }
