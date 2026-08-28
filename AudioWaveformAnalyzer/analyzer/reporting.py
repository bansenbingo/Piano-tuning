"""Create text-only Markdown reports for sinusoidal decomposition results."""

from __future__ import annotations

from typing import Any


def _safe_text(value: object) -> str:
    """Escape text for a Markdown table cell."""

    return str(value).replace("|", "\\|").replace("\n", " ")


def build_markdown_report(filename: str, components: list[dict[str, Any]], expression: str, sample_rate: float, duration: float) -> str:
    """Build a portable text-only Markdown report."""

    rows = [
        "| 编号 | 正弦波函数方程 | 频率 (Hz) | 幅值 | 相位 (rad) |",
        "| ---: | --- | ---: | ---: | ---: |",
    ]
    for component in components:
        rows.append(
            "| {index} | `{expression}` | {frequency:.6f} | {amplitude:.6f} | {phase:.6f} |".format(
                index=int(component["index"]), expression=_safe_text(component["expression"]),
                frequency=float(component["frequency"]), amplitude=float(component["amplitude"]),
                phase=float(component["phase"]),
            )
        )
    return "\n".join([
        "# 音频正弦波分解报告", "", f"- 文件：`{_safe_text(filename)}`",
        f"- 采样率：{sample_rate:.3f} Hz", f"- 时长：{duration:.6f} s",
        f"- 分解分量数：{len(components)}", "", "## 总拟合方程", "",
        f"`{_safe_text(expression)}`", "", "## 各正弦波函数方程与频率", "",
        *rows, "",
    ])
