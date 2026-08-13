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
const denoisePanel = document.querySelector("#denoise-panel");

function escapeHtml(value) {
  return String(value).replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char],
  );
}

function renderResults(payload) {
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
analyzeBtn.addEventListener("click", analyze);
