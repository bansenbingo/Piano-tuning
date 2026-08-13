# Audio Waveform Analyzer

Flask web application that uploads a WAV file, applies a zero-phase band-pass
noise filter, then uses the Fourier transform to locate the most energetic
frequencies and fits each one to a sine wave. The fitted components are
reported as an analytical function expression and visualized interactively.

## Local setup

```bash
cd AudioWaveformAnalyzer
conda env create -f environment.yml
conda activate audio-waveform-analyzer
python app.py
```

Open <http://127.0.0.1:5000/> after the server starts. If port 5000 is already
in use (macOS AirPlay commonly occupies it), choose another port:

```bash
FLASK_PORT=5001 python app.py
```

Plotly.js is served locally from the installed Plotly package, so the
visualizations work without an external CDN.

## Current scope

- Upload-only WAV input.
- A zero-phase Butterworth band-pass filter removes low-frequency rumble and
  high-frequency hiss before decomposition. The low/high cutoffs are adjustable
  in the UI and default to 20 Hz and 12 kHz for single-note piano recordings.
- WAV decomposition into a configurable number of sine waves:
  - Hann-windowed real FFT with `scipy.signal.find_peaks` picks the dominant
    frequencies, refined to sub-bin accuracy by parabolic interpolation.
  - A linear least-squares fit recovers each component's amplitude and phase,
    then each component is written as `A·sin(2π·f·t + φ)`.
- Interactive Plotly visualizations for the filtered versus raw waveform, the
  filtered waveform versus its reconstruction, the spectrum with detected
  peaks, and every individual component waveform.
- A "fit function" panel that prints the summed analytical expression and each
  component's expression.

## Converting audio to WAV

If your recording is not yet a WAV file, convert it first (the source sample
rate and channel count are preserved, and output is uncompressed `pcm_f32le`):

```bash
conda activate audio-waveform-analyzer
python tools/convert_audio_to_wav.py data/piano data/piano_wav
```

M4A/AAC is already lossy before conversion; converting it to WAV cannot restore
information removed by AAC, but it avoids adding another lossy generation. Once
converted, upload the resulting WAV file through the web UI.
