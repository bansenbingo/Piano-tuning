"""Audio format conversion helpers shared by the web and CLI workflows."""

from __future__ import annotations

import subprocess
from pathlib import Path


class AudioConversionError(RuntimeError):
    """Raised when FFmpeg cannot decode an uploaded audio file."""


def convert_to_wav(source: Path, destination: Path, *, overwrite: bool = True) -> None:
    """Decode ``source`` to uncompressed 32-bit float WAV without resampling."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-y" if overwrite else "-n", "-i", str(source), "-map", "0:a:0",
        "-vn", "-sn", "-dn", "-c:a", "pcm_f32le", "-map_metadata", "0",
        str(destination),
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        raise AudioConversionError("FFmpeg is unavailable; install it and ensure it is on PATH.") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or "unknown FFmpeg error"
        raise AudioConversionError(f"Unable to convert {source.name} to WAV: {detail}")
