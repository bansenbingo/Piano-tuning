"""Top-level Flask launcher for `python app.py`."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import plotly
from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from analyzer.audio_io import AudioReadError, read_wav_mono
from analyzer.conversion import AudioConversionError, convert_to_wav
from analyzer.decomposition import DecompositionError, decompose
from analyzer.filtering import FilterError, denoise
from analyzer.reporting import build_markdown_report
from analyzer.visualization import (
    build_components_figure,
    build_denoise_figure,
    build_phasor_figure,
    build_spectrum_figure,
    build_wave_figure,
)

PROJECT_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = PROJECT_DIR / "data" / "uploads"
PLOTLY_JS = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
SUPPORTED_UPLOAD_EXTENSIONS = {".wav", ".m4a"}


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(PROJECT_DIR / "templates"),
        static_folder=str(PROJECT_DIR / "static"),
    )

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "version": "2.5.0"})

    @app.get("/vendor/plotly.min.js")
    def plotly_js():
        return send_file(PLOTLY_JS, mimetype="application/javascript", max_age=3600)

    @app.post("/api/analyze")
    def analyze():
        try:
            num_components = int(request.form.get("num_components", "5"))
        except ValueError:
            return jsonify({"error": "num_components must be an integer."}), 400

        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return jsonify({"error": "A WAV or M4A file is required."}), 400

        filename = secure_filename(upload.filename)
        extension = Path(filename).suffix.lower()
        if extension not in SUPPORTED_UPLOAD_EXTENSIONS:
            return jsonify({"error": "Only WAV and M4A files are supported."}), 400
        path = UPLOAD_DIR / filename
        upload.save(path)

        converted = extension == ".m4a"
        try:
            if converted:
                with tempfile.TemporaryDirectory(dir=UPLOAD_DIR, prefix="m4a_to_wav_") as temp_dir:
                    wav_path = Path(temp_dir) / f"{Path(filename).stem}.wav"
                    convert_to_wav(path, wav_path)
                    signal_mono, sample_rate = read_wav_mono(wav_path)
            else:
                signal_mono, sample_rate = read_wav_mono(path)
        except (AudioConversionError, AudioReadError) as exc:
            return jsonify({"error": str(exc)}), 400

        filter_enabled = request.form.get("denoise", "1").lower() in {"1", "true", "on", "yes"}
        try:
            lowcut_hz = float(request.form.get("lowcut", "20"))
            highcut_hz = float(request.form.get("highcut", "12000"))
        except ValueError:
            return jsonify({"error": "Filter cutoff frequencies must be numbers."}), 400

        try:
            filtered_signal = (
                denoise(signal_mono, sample_rate, lowcut_hz, highcut_hz)
                if filter_enabled
                else signal_mono
            )
            result = decompose(filtered_signal, sample_rate, num_components)
        except (FilterError, DecompositionError) as exc:
            return jsonify({"error": str(exc)}), 422

        figures = {
            "wave": build_wave_figure(
                result["sample_rate"], result["signal"], result["reconstruction"]
            ),
            "spectrum": build_spectrum_figure(
                result["sample_rate"],
                result["signal"],
                [component["frequency"] for component in result["components"]],
            ),
            "components": build_components_figure(
                result["sample_rate"], result["component_waves"], result["components"]
            ),
            "phasor": build_phasor_figure(result["components"]),
        }
        if filter_enabled:
            figures["denoise"] = build_denoise_figure(sample_rate, signal_mono, filtered_signal)

        return jsonify(
            {
                "filename": filename,
                "input_format": extension.lstrip("."),
                "converted_to_wav": converted,
                "processing_format": "wav",
                "sample_rate": sample_rate,
                "num_samples": int(signal_mono.size),
                "duration": round(signal_mono.size / sample_rate, 6),
                "analysis_sample_rate": round(float(result["sample_rate"]), 3),
                "num_components": len(result["components"]),
                "model": result["model"],
                "components": result["components"],
                "expression": result["expression"],
                "markdown_report": build_markdown_report(
                    filename,
                    result["components"],
                    result["expression"],
                    result["sample_rate"],
                    signal_mono.size / sample_rate,
                ),
                "filter": {
                    "enabled": filter_enabled,
                    "lowcut_hz": lowcut_hz,
                    "highcut_hz": min(highcut_hz, 0.95 * sample_rate / 2),
                },
                "figures": {name: fig.to_plotly_json() for name, fig in figures.items()},
            }
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )
