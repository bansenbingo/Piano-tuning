"""Convert source audio to uncompressed 32-bit float WAV without resampling."""

from __future__ import annotations

import argparse
from pathlib import Path

from analyzer.conversion import convert_to_wav

SUPPORTED_SUFFIXES = {".m4a", ".mp3", ".wav"}


def convert_file(source: Path, destination: Path, *, overwrite: bool = False) -> None:
    """Decode one file to WAV while retaining its source rate and channel count."""

    convert_to_wav(source, destination, overwrite=overwrite)


def convert_directory(source_dir: Path, destination_dir: Path, *, overwrite: bool = False) -> int:
    """Convert supported audio files and return the number of generated WAVs."""

    sources = sorted(
        (path for path in source_dir.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES),
        key=lambda path: path.name.casefold(),
    )
    for source in sources:
        destination = destination_dir / f"{source.stem}.wav"
        convert_file(source, destination, overwrite=overwrite)
    return len(sources)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Directory containing M4A/MP3/WAV files")
    parser.add_argument("destination", type=Path, help="Directory for generated WAV files")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing WAV files")
    args = parser.parse_args()
    count = convert_directory(args.source, args.destination, overwrite=args.overwrite)
    print(f"Converted {count} file(s) to {args.destination}")


if __name__ == "__main__":
    main()
