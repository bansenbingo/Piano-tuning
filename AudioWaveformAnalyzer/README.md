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
conda env create -f environment.yml
conda activate audio-waveform-analyzer
python -m analyzer.app
```

Open <http://127.0.0.1:5000/> after the server starts.

FFmpeg and `ffprobe` must be available on `PATH` for `.m4a` and `.mp3` files.

The environment file installs Python and FFmpeg through conda-forge. Python
packages declared in `pyproject.toml`, including Plotly for interactive plots,
are installed with pip as part of environment creation.

## Current scope

- Flask app skeleton with a health endpoint and piano-sample catalog.
- M4A sample inventory and metadata inspection through `ffprobe`.
- Lossless-after-decoding 32-bit float WAV copies in `data/piano_wav/`; the
  original M4A files remain unchanged.
- Reserved directories for uploaded files, generated analysis results, and
  technical documents under the repository-level `Reference/` directory.

FFT decomposition, curve fitting, plots, and export are planned for subsequent
`2.x` feature commits.

## Converting audio to WAV

The conversion keeps the source sample rate and channel count (no `-ar` or
`-ac` conversion) and writes uncompressed `pcm_f32le` WAV files:

```bash
conda activate audio-waveform-analyzer
python tools/convert_audio_to_wav.py data/piano data/piano_wav
```

M4A/AAC is already lossy before conversion; converting it to WAV cannot restore
information removed by AAC, but it avoids adding another lossy generation.
