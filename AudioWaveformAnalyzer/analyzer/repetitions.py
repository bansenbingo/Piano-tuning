"""Split and robustly combine repeated recordings of one piano note."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import signal

MIN_REPETITIONS = 1
MAX_REPETITIONS = 32
ENVELOPE_SECONDS = 0.02
MIN_ONSET_GAP_SECONDS = 0.08
ALIGNMENT_SECONDS = 0.08
MAX_ALIGNMENT_SECONDS = 0.012
LEVEL_SECONDS = 0.35


class RepetitionError(ValueError):
    """Raised when a repeated-note recording cannot be segmented reliably."""


def _validate_signal(x: np.ndarray, sample_rate: float) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    if x.ndim != 1 or x.size < 4:
        raise RepetitionError("Signal must be a one-dimensional array of at least 4 samples.")
    if not math.isfinite(float(sample_rate)) or sample_rate <= 0:
        raise RepetitionError("Sample rate must be a positive number.")
    return x


def _energy_envelope(x: np.ndarray, sample_rate: float) -> np.ndarray:
    window = max(3, round(ENVELOPE_SECONDS * sample_rate))
    kernel = np.full(window, 1.0 / window)
    return np.sqrt(np.convolve(np.square(x), kernel, mode="same"))


def _find_onsets(x: np.ndarray, sample_rate: float, repetitions: int) -> np.ndarray:
    envelope = _energy_envelope(x, sample_rate)
    min_gap = max(1, round(MIN_ONSET_GAP_SECONDS * sample_rate))
    noise_floor = float(np.percentile(envelope, 25))
    prominence = max(float(np.max(envelope) - noise_floor) * 0.08, np.finfo(float).eps)
    candidates, properties = signal.find_peaks(
        envelope,
        distance=min_gap,
        prominence=prominence,
    )
    if candidates.size < repetitions:
        raise RepetitionError(
            f"Detected {candidates.size} note attacks, but {repetitions} repeated notes were requested. "
            "Increase the gap between strikes or choose a smaller repeat count."
        )

    # Prominence favors attack transients over later resonances; then restore time order.
    strongest = np.argsort(properties["prominences"])[-repetitions:]
    onsets = np.sort(candidates[strongest])
    return onsets.astype(int)


def split_repeated_note(x: np.ndarray, sample_rate: float, repetitions: int) -> dict[str, Any]:
    """Split a recording containing ``repetitions`` strikes of the same note.

    Attack locations are derived from a short-time RMS envelope.  Every returned
    segment has one shared length, which prevents a longer decay in one take from
    dominating the subsequent robust aggregate.
    """

    x = _validate_signal(x, sample_rate)
    repetitions = int(repetitions)
    if not MIN_REPETITIONS <= repetitions <= MAX_REPETITIONS:
        raise RepetitionError(
            f"Repeat count must be between {MIN_REPETITIONS} and {MAX_REPETITIONS}."
        )
    if repetitions == 1:
        return {"segments": [x.copy()], "onsets": np.asarray([0]), "segment_samples": x.size}

    onsets = _find_onsets(x, sample_rate, repetitions)
    gaps = np.diff(onsets)
    segment_samples = int(np.min(gaps))
    min_samples = max(8, round(0.10 * sample_rate))
    if segment_samples < min_samples:
        raise RepetitionError("Repeated note attacks are too close together to form analysis segments.")
    if onsets[-1] + segment_samples > x.size:
        raise RepetitionError(
            "The last repeated note is incomplete. Record one full decay after the final strike."
        )

    segments = [x[start : start + segment_samples].copy() for start in onsets]
    return {"segments": segments, "onsets": onsets, "segment_samples": segment_samples}


def _best_offset(reference: np.ndarray, candidate: np.ndarray, sample_rate: float) -> int:
    """Find the candidate sample offset that maximizes normalized correlation."""

    window = min(reference.size, candidate.size, max(8, round(ALIGNMENT_SECONDS * sample_rate)))
    maximum = min(max(1, round(MAX_ALIGNMENT_SECONDS * sample_rate)), window // 3)
    ref = reference[:window]
    best_offset = 0
    best_score = -math.inf
    for offset in range(-maximum, maximum + 1):
        ref_start = max(0, -offset)
        candidate_start = max(0, offset)
        length = window - abs(offset)
        left = ref[ref_start : ref_start + length]
        right = candidate[candidate_start : candidate_start + length]
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        score = float(np.dot(left, right) / denominator) if denominator else -math.inf
        if score > best_score:
            best_score = score
            best_offset = offset
    return best_offset


def combine_repeated_note(segments: list[np.ndarray], sample_rate: float) -> dict[str, Any]:
    """Align, level-normalize, and samplewise-median repeated note segments."""

    if not segments:
        raise RepetitionError("At least one note segment is required.")
    prepared = [_validate_signal(segment, sample_rate) for segment in segments]
    common_size = min(segment.size for segment in prepared)
    prepared = [segment[:common_size] for segment in prepared]
    if len(prepared) == 1:
        return {"signal": prepared[0].copy(), "offsets": [0], "segment_samples": common_size}

    offsets = [0] + [_best_offset(prepared[0], segment, sample_rate) for segment in prepared[1:]]
    start = max(0, *[-offset for offset in offsets])
    stop = min(common_size, *[common_size - offset for offset in offsets])
    if stop - start < 8:
        raise RepetitionError("Repeated note segments do not overlap after alignment.")
    aligned = np.vstack(
        [segment[start + offset : stop + offset] for segment, offset in zip(prepared, offsets)]
    )

    level_samples = min(aligned.shape[1], max(8, round(LEVEL_SECONDS * sample_rate)))
    levels = np.sqrt(np.mean(np.square(aligned[:, :level_samples]), axis=1))
    target_level = float(np.median(levels[levels > np.finfo(float).eps]))
    if not math.isfinite(target_level) or target_level <= 0:
        raise RepetitionError("Repeated note segments contain no usable audio energy.")
    normalized = aligned * (target_level / np.maximum(levels, np.finfo(float).eps))[:, None]

    return {
        "signal": np.median(normalized, axis=0),
        "offsets": offsets,
        "segment_samples": int(stop - start),
    }
