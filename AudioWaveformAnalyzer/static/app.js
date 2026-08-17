const PALETTE = [
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
];

const fileInput = document.querySelector("#file-input");
const denoiseToggle = document.querySelector("#denoise");
const lowcutInput = document.querySelector("#lowcut");
const highcutInput = document.querySelector("#highcut");
const numComponents = document.querySelector("#num-components");
const numValue = document.querySelector("#num-value");
const analyzeBtn = document.querySelector("#analyze-btn");
const status = document.querySelector("#status");
const emptyState = document.querySelector("#empty-state");
const results = document.querySelector("#results");

const metaTitle = document.querySelector("#meta-title");
const metaChips = document.querySelector("#meta-chips");
const expression = document.querySelector("#expression");
const componentList = document.querySelector("#component-list");
const frequencyList = document.querySelector("#frequency-list");
const markdownReport = document.querySelector("#markdown-report");
const copyFrequenciesButton = document.querySelector("#copy-frequencies");
const copyMarkdownButton = document.querySelector("#copy-markdown");
const downloadMarkdownButton = document.querySelector("#download-markdown");
const denoisePanel = document.querySelector("#denoise-panel");
const navigationItems = [...document.querySelectorAll(".topnav-item")];

let currentPayload = null;

function escapeHtml(value) {
  return String(value).replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char],
  );
}

function renderResults(payload) {
  currentPayload = payload;
  emptyState.hidden = true;
  results.hidden = false;

  metaTitle.textContent = `分析结果：${payload.filename}`;
  const chips = [
    payload.converted_to_wav ? "M4A → WAV" : "WAV",
    `${payload.sample_rate} Hz`,
    `${Number(payload.duration).toFixed(3)} s`,
    `${payload.num_samples} 采样`,
    `${payload.num_components} 个正弦波`,
  ];
  if (payload.filter.enabled) {
    chips.push(`降噪 ${payload.filter.lowcut_hz}–${payload.filter.highcut_hz} Hz`);
  }
  metaChips.innerHTML = chips
    .map((chip) => `<span class="chip">${escapeHtml(chip)}</span>`)
    .join("");

  expression.textContent = payload.expression;
  componentList.innerHTML = payload.components
    .map((component) => {
      const color = PALETTE[(component.index - 1) % PALETTE.length];
      return `<li><span class="dot" style="background:${color}"></span>${escapeHtml(
        component.expression,
      )}</li>`;
    })
    .join("");
  frequencyList.innerHTML = payload.components
    .map(
      (component) =>
        "<li><span>分量 #" + component.index + "</span><output>" +
        Number(component.frequency).toFixed(6) + " Hz</output></li>",
    )
    .join("");
  markdownReport.value = payload.markdown_report;

  const config = { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d"] };
  if (payload.figures.denoise) {
    denoisePanel.hidden = false;
    Plotly.react("denoise-plot", payload.figures.denoise.data, payload.figures.denoise.layout, config);
  } else {
    denoisePanel.hidden = true;
  }
  Plotly.react("wave-plot", payload.figures.wave.data, payload.figures.wave.layout, config);
  Plotly.react(
    "spectrum-plot",
    payload.figures.spectrum.data,
    payload.figures.spectrum.layout,
    config,
  );
  Plotly.react(
    "components-plot",
    payload.figures.components.data,
    payload.figures.components.layout,
    config,
  );
  Plotly.react("phasor-plot", payload.figures.phasor.data, payload.figures.phasor.layout, config);
  window.requestAnimationFrame(() => {
    document.querySelectorAll(".js-plotly-plot").forEach((plot) => Plotly.Plots.resize(plot));
  });
}

function setActiveNavigation(item) {
  navigationItems.forEach((navItem) => {
    const active = navItem === item;
    navItem.classList.toggle("active", active);
    if (active) navItem.setAttribute("aria-current", "page");
    else navItem.removeAttribute("aria-current");
  });
}

async function copyText(value, successMessage) {
  try {
    await navigator.clipboard.writeText(value);
    status.textContent = successMessage;
  } catch (error) {
    status.textContent = "无法访问剪贴板，请从文本框中手动复制。";
  }
}

function downloadMarkdown() {
  if (!currentPayload) return;
  const name = currentPayload.filename.replace(/\.[^.]+$/, "") || "audio-analysis";
  const blob = new Blob([markdownReport.value], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name + "-sinusoid-analysis.md";
  link.click();
  URL.revokeObjectURL(url);
}

async function analyze() {
  if (fileInput.files.length === 0) {
    status.textContent = "请先上传一个 WAV 或 M4A 文件。";
    return;
  }

  const form = new FormData();
  form.append("file", fileInput.files[0]);
  form.append("num_components", numComponents.value);
  form.append("denoise", denoiseToggle.checked ? "1" : "0");
  form.append("lowcut", lowcutInput.value);
  form.append("highcut", highcutInput.value);

  analyzeBtn.disabled = true;
  status.textContent = "正在分析…";
  try {
    const response = await fetch("/api/analyze", { method: "POST", body: form });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "分析失败");
    renderResults(payload);
    status.textContent = "";
  } catch (error) {
    status.textContent = error.message;
  } finally {
    analyzeBtn.disabled = false;
  }
}

numComponents.addEventListener("input", () => {
  numValue.textContent = numComponents.value;
});
navigationItems.forEach((item) => {
  item.addEventListener("click", () => setActiveNavigation(item));
});
analyzeBtn.addEventListener("click", analyze);
copyFrequenciesButton.addEventListener("click", () => {
  if (!currentPayload) return;
  const frequencies = currentPayload.components
    .map(
      (component) =>
        "#" + component.index + ": " + Number(component.frequency).toFixed(6) + " Hz",
    )
    .join("\n");
  copyText(frequencies, "频率已复制。");
});
copyMarkdownButton.addEventListener("click", () => {
  copyText(markdownReport.value, "Markdown 报告已复制。");
});
downloadMarkdownButton.addEventListener("click", downloadMarkdown);
