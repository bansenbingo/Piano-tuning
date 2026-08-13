"""Build Plotly figures for the sinusoidal decomposition results."""

from __future__ import annotations

from typing import Any

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

PLOT_MAX_POINTS = 3000

FONT_FAMILY = (
    "ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', "
    "Roboto, 'Helvetica Neue', Arial, sans-serif"
)
FOREGROUND = "#1a1f2c"
MUTED = "#6b7280"
GRID = "#e7e9ec"
BACKGROUND = "#ffffff"
ACCENT = "#d8f249"
ORIGINAL = "#1a1f2c"

PALETTE = [
    "#d8f249",
    "#2f80ed",
    "#eb5757",
    "#27ae60",
    "#9b51e0",
    "#f2994a",
    "#00b8d9",
    "#ff6b9d",
    "#6b7280",
    "#8d6e63",
]


def _downsample_arrays(
    sample_rate: float, *arrays: np.ndarray
) -> tuple[np.ndarray, list[np.ndarray]]:
    """Return a shared time axis plus uniformly downsampled copies for plotting."""

    size = arrays[0].size
    time = np.arange(size, dtype=np.float64) / sample_rate
    prepared = [np.asarray(array, dtype=np.float64) for array in arrays]
    if size > PLOT_MAX_POINTS:
        indices = np.linspace(0, size - 1, PLOT_MAX_POINTS).astype(int)
        time = time[indices]
        prepared = [array[indices] for array in prepared]
    return time, prepared


def _style(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(
        title={"text": title, "font": {"size": 15, "color": FOREGROUND}},
        font={"family": FONT_FAMILY, "color": FOREGROUND, "size": 12},
        paper_bgcolor=BACKGROUND,
        plot_bgcolor=BACKGROUND,
        margin={"l": 48, "r": 20, "t": 52, "b": 40},
        hoverlabel={"font": {"family": FONT_FAMILY}},
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        linecolor=GRID,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        linecolor=GRID,
    )
    return fig


def build_wave_figure(
    sample_rate: float, original: np.ndarray, reconstruction: np.ndarray
) -> go.Figure:
    time, (original_plot, reconstruction_plot) = _downsample_arrays(
        sample_rate, original, reconstruction
    )
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=time,
            y=original_plot,
            name="原波形",
            mode="lines",
            line={"color": ORIGINAL, "width": 1.1},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=time,
            y=reconstruction_plot,
            name="正弦波拟合",
            mode="lines",
            line={"color": ACCENT, "width": 1.6, "dash": "dash"},
        )
    )
    fig.update_layout(
        xaxis_title="时间 (s)",
        yaxis_title="幅值",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
    )
    return _style(fig, "原音频波形与正弦波拟合")


def build_denoise_figure(sample_rate: float, raw: np.ndarray, filtered: np.ndarray) -> go.Figure:
    time, (raw_plot, filtered_plot) = _downsample_arrays(sample_rate, raw, filtered)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=time,
            y=raw_plot,
            name="滤波前",
            mode="lines",
            line={"color": MUTED, "width": 1.1},
        )
    )
    fig.add_trace(
        go.Scatter(
            x=time,
            y=filtered_plot,
            name="滤波后",
            mode="lines",
            line={"color": ACCENT, "width": 1.5},
        )
    )
    fig.update_layout(
        xaxis_title="时间 (s)",
        yaxis_title="幅值",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
    )
    return _style(fig, "降噪滤波前后对比")


def _spectrum(sample_rate: float, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    size = x.size
    windowed = x * np.hanning(size)
    magnitude = np.abs(np.fft.rfft(windowed))
    frequencies = np.fft.rfftfreq(size, 1.0 / sample_rate)
    return frequencies, magnitude


def build_spectrum_figure(sample_rate: float, x: np.ndarray, frequencies: list[float]) -> go.Figure:
    frequencies_axis, magnitude = _spectrum(sample_rate, x)
    if magnitude.size > PLOT_MAX_POINTS:
        indices = np.linspace(0, magnitude.size - 1, PLOT_MAX_POINTS).astype(int)
        frequencies_axis = frequencies_axis[indices]
        magnitude = magnitude[indices]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=frequencies_axis,
            y=magnitude,
            name="幅度谱",
            mode="lines",
            line={"color": ORIGINAL, "width": 1},
        )
    )

    if frequencies:
        bin_width = float(sample_rate / x.size)
        indices = np.clip(
            np.rint(np.asarray(frequencies) / bin_width),
            0,
            magnitude.size - 1,
        ).astype(int)
        marker_magnitudes = [magnitude[int(index)] for index in indices]
        fig.add_trace(
            go.Scatter(
                x=frequencies,
                y=marker_magnitudes,
                name="检测频率",
                mode="markers",
                marker={"color": ACCENT, "size": 8, "line": {"color": FOREGROUND, "width": 1}},
            )
        )

    fig.update_layout(
        xaxis_title="频率 (Hz)",
        yaxis_title="幅度（对数）",
        yaxis_type="log",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
    )
    return _style(fig, "频谱与检测到的正弦波频率")


def build_components_figure(
    sample_rate: float,
    component_waves: list[np.ndarray],
    components: list[dict[str, Any]],
) -> go.Figure:
    count = len(component_waves)
    if count == 0:
        return _style(go.Figure(), "正弦波分量")

    labels = [
        f"{component['frequency']:.1f} Hz · A={component['amplitude']:.3f}"
        for component in components
    ]
    fig = make_subplots(
        rows=count,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        subplot_titles=labels,
    )

    for row, (wave, component) in enumerate(zip(component_waves, components), start=1):
        time, [wave_plot] = _downsample_arrays(sample_rate, wave)
        color = PALETTE[(component["index"] - 1) % len(PALETTE)]
        fig.add_trace(
            go.Scatter(
                x=time,
                y=wave_plot,
                name=f"#{component['index']}",
                mode="lines",
                line={"color": color, "width": 1.1},
                showlegend=False,
            ),
            row=row,
            col=1,
        )

    fig.update_layout(height=max(340, count * 105))
    if count:
        fig.update_xaxes(title_text="时间 (s)", row=count, col=1)
        fig.update_yaxes(title_text="幅值", row=(count + 1) // 2, col=1)
    return _style(fig, "拆分后的正弦波分量")
