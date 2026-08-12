"""Minimal Flask entry point for the audio waveform analyzer."""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, render_template

from .audio_io import AudioProbeError, list_audio_files


PROJECT_DIR = Path(__file__).resolve().parent.parent
PIANO_DIR = PROJECT_DIR / "data" / "piano"


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
        return jsonify({"status": "ok", "version": "2.0.0"})

    @app.get("/api/samples")
    def samples():
        try:
            return jsonify({"samples": list_audio_files(PIANO_DIR)})
        except (AudioProbeError, FileNotFoundError) as exc:
            return jsonify({"error": str(exc)}), 503

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("FLASK_PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )
