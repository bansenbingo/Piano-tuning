"""Tests for automatic M4A-to-WAV upload processing."""

from __future__ import annotations

from pathlib import Path

from app import create_app


def test_m4a_upload_is_converted_before_analysis():
    app = create_app()
    source = Path(__file__).parents[1] / "data" / "piano" / "C.m4a"

    with source.open("rb") as audio:
        response = app.test_client().post(
            "/api/analyze",
            data={
                "file": (audio, source.name),
                "num_components": "2",
                "denoise": "0",
            },
            content_type="multipart/form-data",
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["input_format"] == "m4a"
    assert payload["converted_to_wav"] is True
    assert payload["processing_format"] == "wav"
    assert payload["num_components"] == 2
