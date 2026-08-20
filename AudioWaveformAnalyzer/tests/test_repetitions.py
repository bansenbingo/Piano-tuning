"""Tests for repeated-note segmentation and robust aggregation."""

from __future__ import annotations

import numpy as np

from analyzer.repetitions import combine_repeated_note, split_repeated_note


def _repeated_tone(sample_rate: int = 8_000) -> tuple[np.ndarray, int]:
    duration = 0.42
    starts = [0.12, 0.72, 1.32]
    size = int(2.0 * sample_rate)
    recording = np.zeros(size)
    time = np.arange(int(duration * sample_rate)) / sample_rate
    tone = np.sin(2 * np.pi * 440.0 * time) * np.exp(-3.5 * time)
    for index, start in enumerate(starts):
        offset = int(start * sample_rate)
        recording[offset : offset + tone.size] += (1.0 + index * 0.12) * tone
    return recording, sample_rate


def test_split_repeated_note_detects_requested_attack_count():
    recording, sample_rate = _repeated_tone()

    result = split_repeated_note(recording, sample_rate, 3)

    assert len(result["segments"]) == 3
    assert result["onsets"].size == 3
    assert np.allclose(result["onsets"] / sample_rate, [0.12, 0.72, 1.32], atol=0.05)
    assert len({segment.size for segment in result["segments"]}) == 1


def test_combine_repeated_note_aligns_and_reduces_an_isolated_glitch():
    recording, sample_rate = _repeated_tone()
    split = split_repeated_note(recording, sample_rate, 3)
    segments = split["segments"]
    segments[1][500] += 10.0

    combined = combine_repeated_note(segments, sample_rate)

    assert len(combined["offsets"]) == 3
    assert combined["signal"].size <= segments[0].size
    assert abs(combined["signal"][500]) < 2.0
