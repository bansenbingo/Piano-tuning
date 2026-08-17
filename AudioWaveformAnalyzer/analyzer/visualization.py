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
FOREGROUND = "#181818"
MUTED = "#777777"
GRID = "#dedede"
BACKGROUND = "#ffffff"
ACCENT = "#737373"
ORIGINAL = "#181818"

PALETTE = [
    "#181818",
    "#525252",
    "#737373",
    "#a3a3a3",
    "#303030",
    "#626262",
    "#858585",
    "#b5b5b5",
    "#454545",
    "#919191",
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
    # Default to a piano-focused span so the detected partials do not collapse
    # into a narrow strip next to the 20 kHz Nyquist range.
    max_frequency = max(frequencies, default=0.0)
    display_limit = min(sample_rate / 2.0, max(2_000.0, max_frequency * 1.25))
    visible = frequencies_axis <= display_limit
    display_frequencies = frequencies_axis[visible]
    display_magnitude = magnitude[visible]
    if display_magnitude.size > PLOT_MAX_POINTS:
        indices = np.linspace(0, display_magnitude.size - 1, PLOT_MAX_POINTS).astype(int)
        display_frequencies = display_frequencies[indices]
        display_magnitude = display_magnitude[indices]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=display_frequencies,
            y=display_magnitude,
            name="幅度谱",
            mode="lines",
            line={"color": ORIGINAL, "width": 1},
        )
    )

    if frequencies:
        marker_magnitudes = np.interp(frequencies, frequencies_axis, magnitude).tolist()
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
    fig.update_xaxes(range=[0, display_limit])
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


def build_phasor_figure(components: list[dict[str, Any]]) -> go.Figure:
    """Plot fitted sine waves as vectors whose magnitude and angle are A and phi."""

    fig = go.Figure()
    max_amplitude = max((float(component["amplitude"]) for component in components), default=1.0)
    for component in components:
        index = int(component["index"])
        amplitude = float(component["amplitude"])
        phase = float(component["phase"])
        color = PALETTE[(index - 1) % len(PALETTE)]
        real = amplitude * np.cos(phase)
        imaginary = amplitude * np.sin(phase)
        fig.add_trace(go.Scatter(
            x=[0, real], y=[0, imaginary], mode="lines+markers+text",
            name=f"#{index} · {float(component['frequency']):.3f} Hz",
            text=[None, f"#{index}"], textposition="top right",
            line={"color": color, "width": 2.5},
            marker={"color": color, "size": [4, 8], "symbol": ["circle", "triangle-up"]},
            hovertemplate=(f"分量 #{index}<br>频率：{float(component['frequency']):.6f} Hz"
                           f"<br>幅值：{amplitude:.6f}<br>相位：{phase:.6f} rad<extra></extra>"),
        ))
    axis_limit = max_amplitude * 1.25 if max_amplitude > 0 else 1.0
    fig.update_layout(
        xaxis_title="实部（幅值 · cos(相位)）", yaxis_title="虚部（幅值 · sin(相位)）",
        height=500, legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
    )
    fig.update_xaxes(range=[-axis_limit, axis_limit], scaleanchor="y", scaleratio=1)
    fig.update_yaxes(range=[-axis_limit, axis_limit])
    return _style(fig, "分解正弦波相量矢量图")
