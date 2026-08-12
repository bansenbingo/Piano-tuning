"""Audio metadata helpers used by the initial Flask application."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


class AudioProbeError(RuntimeError):
    """Raised when ffprobe cannot inspect an audio file."""


def probe_audio(path: Path) -> dict[str, object]:
    """Return stable, JSON-friendly metadata for an audio file."""

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_name,sample_rate,channels",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise AudioProbeError(f"Unable to inspect {path.name}: {exc}") from exc

    payload = json.loads(result.stdout)
    stream = (payload.get("streams") or [{}])[0]
    fmt = payload.get("format") or {}
    duration = fmt.get("duration")
    return {
        "filename": path.name,
        "format": path.suffix.lower().lstrip("."),
        "codec": stream.get("codec_name"),
        "sample_rate": int(stream["sample_rate"]) if stream.get("sample_rate") else None,
        "channels": int(stream["channels"]) if stream.get("channels") else None,
        "duration_seconds": round(float(duration), 6) if duration else None,
        "size_bytes": path.stat().st_size,
    }


def list_audio_files(directory: Path) -> list[dict[str, object]]:
    """Probe supported audio files in a directory, sorted by filename."""

    supported = {".m4a", ".mp3", ".wav"}
    files = sorted(
        (path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in supported),
        key=lambda path: path.name.casefold(),
    )
    return [probe_audio(path) for path in files]
