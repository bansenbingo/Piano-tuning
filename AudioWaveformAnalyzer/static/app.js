async function loadSamples() {
  const body = document.querySelector("#samples");
  try {
    const response = await fetch("/api/samples");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "读取失败");
    body.innerHTML = payload.samples.map((sample) => `
      <tr>
        <td>${sample.filename}</td>
        <td>${sample.codec || "-"}</td>
        <td>${sample.sample_rate ? `${sample.sample_rate} Hz` : "-"}</td>
        <td>${sample.channels || "-"}</td>
        <td>${sample.duration_seconds ? `${sample.duration_seconds.toFixed(2)} s` : "-"}</td>
      </tr>`).join("");
  } catch (error) {
    body.innerHTML = `<tr><td colspan="5">${error.message}</td></tr>`;
  }
}

loadSamples();
