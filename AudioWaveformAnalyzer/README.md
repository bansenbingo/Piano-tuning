# Audio Waveform Analyzer

Version 2.0 initializes the Python project for the audio-analysis work on the
`audio-waveform-analysis` branch.

The sample library in `data/piano/` contains the supplied piano-note recordings
in their original `.m4a` format. The application uses FFmpeg/ffprobe to inspect
and decode M4A/MP3 input, and NumPy/SciPy for later waveform, FFT, and sinusoidal
fitting features.

## Local setup

```bash
cd AudioWaveformAnalyzer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m analyzer.app
```

Open <http://127.0.0.1:5000/> after the server starts.

FFmpeg and `ffprobe` must be available on `PATH` for `.m4a` and `.mp3` files.

## Current scope

- Flask app skeleton with a health endpoint and piano-sample catalog.
- M4A sample inventory and metadata inspection through `ffprobe`.
- Reserved directories for uploaded files, generated analysis results, and
  technical documents under the repository-level `Reference/` directory.

FFT decomposition, curve fitting, plots, and export are planned for subsequent
`2.x` feature commits.
