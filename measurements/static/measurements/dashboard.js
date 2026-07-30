const initialElement = document.querySelector("#reading-history");
const initialReadings = initialElement ? JSON.parse(initialElement.textContent) : [];
const thresholdElement = document.querySelector("#condition-thresholds");
const conditionThresholds = thresholdElement ? JSON.parse(thresholdElement.textContent) : {};
const endpoints = document.querySelector("#endpoints").dataset;
const rangeStart = document.querySelector("#range-start");
const rangeEnd = document.querySelector("#range-end");
const sparklineState = new WeakMap();
let rangeDescription = "Last 24 hours";

const metricConfig = {
  temperature_c: { label: "Temperature", unit: "°C", decimals: 1, stableSlope: 0.3 },
  relative_humidity: { label: "Relative humidity", unit: "%", decimals: 1, stableSlope: 1 },
  pressure_hpa: { label: "Atmospheric pressure", unit: "hPa", decimals: 1, stableSlope: 0.5 },
};
const trendWindows = [6, 12, 30];

const metricRows = Object.fromEntries(
  Object.keys(metricConfig).map(metric => [
    metric,
    initialReadings
      .filter(reading => Number.isFinite(reading[metric]))
      .map(reading => ({ recorded_at: reading.recorded_at, value: reading[metric] })),
  ]),
);

function pointsToPath(points) {
  return points.map(([x, y], index) =>
    `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
}

function plot(values, width, height) {
  if (!values.length) return { points: [], min: 0, max: 0 };
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const margin = Math.max((rawMax - rawMin) * 0.15, Math.abs(rawMax) * 0.002, 0.2);
  const min = rawMin - margin;
  const max = rawMax + margin;
  return {
    min,
    max,
    points: values.map((value, index) => [
      values.length === 1 ? width / 2 : (index / (values.length - 1)) * width,
      height - ((value - min) / (max - min)) * height,
    ]),
  };
}

function formatTime(value) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatAxisTime(value) {
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(value));
}

function regressionSlope(rows) {
  if (rows.length < 2) return null;
  const origin = new Date(rows[0].recorded_at).getTime();
  const points = rows.map(row => [
    (new Date(row.recorded_at).getTime() - origin) / 3_600_000,
    row.value,
  ]);
  const meanX = points.reduce((sum, point) => sum + point[0], 0) / points.length;
  const meanY = points.reduce((sum, point) => sum + point[1], 0) / points.length;
  const denominator = points.reduce((sum, point) => sum + ((point[0] - meanX) ** 2), 0);
  if (!denominator) return null;
  return points.reduce(
    (sum, point) => sum + (point[0] - meanX) * (point[1] - meanY),
    0,
  ) / denominator;
}

function renderTrend(card, metric, rows) {
  const summary = card.querySelector("[data-trend-summary]");
  const detail = card.querySelector("[data-trend-detail]");
  if (rows.length < 2) {
    summary.textContent = "Trend · Waiting";
    detail.textContent = "";
    return;
  }
  const latestTime = new Date(rows.at(-1).recorded_at).getTime();
  const slopes = trendWindows.map(minutes => regressionSlope(
    rows.filter(row => new Date(row.recorded_at).getTime() >= latestTime - minutes * 60_000),
  ));
  const available = slopes.filter(Number.isFinite);
  if (!available.length) {
    summary.textContent = "Trend · Waiting";
    detail.textContent = "";
    return;
  }
  const threshold = metricConfig[metric].stableSlope;
  const directions = available.map(slope => (
    Math.abs(slope) < threshold ? 0 : Math.sign(slope)
  ));
  const rising = directions.filter(direction => direction > 0).length;
  const falling = directions.filter(direction => direction < 0).length;
  let label = "Stable";
  if (rising > falling && rising >= 2) label = "Rising";
  else if (falling > rising && falling >= 2) label = "Falling";
  else if (rising && falling) label = "Mixed";
  summary.textContent = `Trend · ${label}`;
  detail.textContent = trendWindows.map((minutes, index) => {
    const slope = slopes[index];
    const value = Number.isFinite(slope) ? `${slope >= 0 ? "+" : ""}${slope.toFixed(1)}` : "—";
    return `${minutes}m ${value}`;
  }).join(" · ") + ` ${metricConfig[metric].unit}/h`;
}

function conditionForValue(metric, value) {
  const limits = conditionThresholds[metric];
  if (!limits || !Number.isFinite(value)) return null;
  if (value <= limits.red_min || value >= limits.red_max) {
    return { level: "red", label: "Damage threshold" };
  }
  if (value < limits.green_min || value > limits.green_max) {
    return { level: "orange", label: "Approaching limit" };
  }
  return { level: "green", label: "Optimal" };
}

function renderCondition(card, metric, value) {
  const indicator = card.querySelector(".condition-indicator");
  if (!indicator) return;
  const condition = conditionForValue(metric, value);
  card.classList.remove("condition--green", "condition--orange", "condition--red");
  if (!condition) {
    indicator.textContent = "No reading";
    return;
  }
  card.classList.add(`condition--${condition.level}`);
  indicator.textContent = condition.label;
}

function localInputValue(date) {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function setRange(hours) {
  if (hours === "all") {
    rangeStart.value = "";
    rangeEnd.value = "";
    rangeDescription = "All recorded data";
    return;
  }
  const start = new Date(Date.now() - Number(hours) * 3_600_000);
  rangeStart.value = localInputValue(start);
  rangeEnd.value = "";
  rangeDescription = {
    24: "Last 24 hours",
    168: "Last 7 days",
    720: "Last 30 days",
  }[hours] || `Last ${hours} hours`;
}

function rangeQuery(metric) {
  const params = new URLSearchParams({ metric });
  if (rangeStart.value) params.set("start", rangeStart.value);
  if (rangeEnd.value) params.set("end", rangeEnd.value);
  return params;
}

function renderMetric(card) {
  const metric = card.dataset.metric;
  const config = metricConfig[metric];
  const rows = metricRows[metric];
  const values = rows.map(row => row.value);
  const svg = card.querySelector(".sparkline");
  const axisLabels = card.querySelectorAll(".chart-x-axis span");
  svg.setAttribute("viewBox", "0 0 400 180");
  if (!values.length) {
    card.querySelector(".metric__value").textContent = "—";
    card.querySelector(".sparkline__line").removeAttribute("d");
    card.querySelector(".sparkline__area").removeAttribute("d");
    card.querySelectorAll("[data-scale]").forEach(label => { label.textContent = ""; });
    axisLabels.forEach(label => { label.textContent = ""; });
    renderCondition(card, metric, NaN);
    renderTrend(card, metric, rows);
    sparklineState.set(svg, { points: [], rows, metric });
    return;
  }
  card.querySelector(".metric__value").textContent = values.at(-1).toFixed(config.decimals);
  renderTrend(card, metric, rows);
  const axisRows = [rows[0], rows[Math.floor((rows.length - 1) / 2)], rows.at(-1)];
  axisLabels.forEach((label, index) => {
    label.textContent = formatAxisTime(axisRows[index].recorded_at);
  });
  renderCondition(card, metric, values.at(-1));
  const { points, min, max } = plot(values, 400, 180);
  card.querySelector('[data-scale="max"]').textContent = max.toFixed(config.decimals);
  card.querySelector('[data-scale="mid"]').textContent = ((min + max) / 2).toFixed(config.decimals);
  card.querySelector('[data-scale="min"]').textContent = min.toFixed(config.decimals);
  const path = pointsToPath(points);
  card.querySelector(".sparkline__line").setAttribute("d", path);
  card.querySelector(".sparkline__area").setAttribute("d", `${path} L400,180 L0,180 Z`);
  sparklineState.set(svg, { points, rows, metric });
}

function renderMetrics() {
  document.querySelectorAll(".metric").forEach(renderMetric);
}

function nearestPointIndex(event, element, count) {
  const bounds = element.getBoundingClientRect();
  const x = Math.max(0, Math.min(bounds.width, event.clientX - bounds.left));
  return Math.max(0, Math.min(count - 1, Math.round((x / bounds.width) * (count - 1))));
}

function showPoint(card, event) {
  const svg = card.querySelector(".sparkline");
  const state = sparklineState.get(svg);
  if (!state?.points.length) return;
  const index = nearestPointIndex(event, svg, state.points.length);
  const [x, y] = state.points[index];
  const row = state.rows[index];
  const config = metricConfig[state.metric];
  const condition = conditionForValue(state.metric, row.value);
  const point = svg.querySelector(".sparkline__point");
  const crosshair = svg.querySelector(".sparkline__crosshair");
  point.setAttribute("cx", x);
  point.setAttribute("cy", y);
  crosshair.setAttribute("x1", x);
  crosshair.setAttribute("x2", x);
  crosshair.setAttribute("y1", 0);
  crosshair.setAttribute("y2", 180);
  svg.classList.add("is-inspecting");

  const tooltip = card.querySelector(".chart-tooltip");
  const svgBounds = svg.getBoundingClientRect();
  const cardBounds = card.getBoundingClientRect();
  const tooltipX = svgBounds.left - cardBounds.left + (x / 400) * svgBounds.width;
  const safeTooltipX = Math.max(76, Math.min(cardBounds.width - 76, tooltipX));
  tooltip.innerHTML = `<strong>${row.value.toFixed(config.decimals)} ${config.unit}</strong><small>${formatTime(row.recorded_at)}</small>${condition ? `<small>${condition.label}</small>` : ""}`;
  tooltip.style.left = `${safeTooltipX}px`;
  tooltip.style.top = `${svgBounds.top - cardBounds.top + (y / 180) * svgBounds.height}px`;
  tooltip.classList.add("is-visible");
  card.classList.add("is-inspecting");
}

function hidePoint(card) {
  card.querySelector(".sparkline").classList.remove("is-inspecting");
  card.querySelector(".chart-tooltip").classList.remove("is-visible");
  card.classList.remove("is-inspecting");
}

document.querySelectorAll(".metric").forEach(card => {
  const svg = card.querySelector(".sparkline");
  const tooltip = card.querySelector(".chart-tooltip");
  let scrubPointer = null;
  let dismissedPointer = null;

  svg.addEventListener("pointerdown", event => {
    if (card.classList.contains("is-inspecting")) {
      dismissedPointer = event.pointerId;
      hidePoint(card);
      return;
    }
    scrubPointer = event.pointerId;
    svg.setPointerCapture?.(event.pointerId);
    showPoint(card, event);
  });
  svg.addEventListener("pointermove", event => {
    if (event.pointerId === dismissedPointer) return;
    if (event.pointerType === "mouse" || event.pointerId === scrubPointer) {
      showPoint(card, event);
    }
  });
  svg.addEventListener("pointerup", event => {
    if (event.pointerId === dismissedPointer) {
      dismissedPointer = null;
      return;
    }
    if (event.pointerId !== scrubPointer) return;
    svg.releasePointerCapture?.(event.pointerId);
    scrubPointer = null;
    showPoint(card, event);
  });
  svg.addEventListener("pointercancel", event => {
    if (event.pointerId === dismissedPointer) dismissedPointer = null;
    if (event.pointerId === scrubPointer) scrubPointer = null;
    hidePoint(card);
  });
  svg.addEventListener("pointerleave", event => {
    if (event.pointerType === "mouse" && scrubPointer === null) hidePoint(card);
  });
  tooltip.addEventListener("pointerdown", event => {
    event.stopPropagation();
    hidePoint(card);
  });
  tooltip.addEventListener("keydown", event => {
    if (event.key === "Enter" || event.key === " " || event.key === "Escape") {
      event.preventDefault();
      hidePoint(card);
      svg.focus();
    }
  });
});

document.addEventListener("pointerdown", event => {
  const selectedCard = event.target.closest(".metric");
  document.querySelectorAll(".metric.is-inspecting").forEach(card => {
    if (card !== selectedCard) hidePoint(card);
  });
});

function describeRange() {
  if (rangeDescription) return rangeDescription;
  if (!rangeStart.value && !rangeEnd.value) return "All recorded data";
  if (rangeStart.value && rangeEnd.value) {
    return `${formatTime(rangeStart.value)} – ${formatTime(rangeEnd.value)}`;
  }
  return rangeStart.value ? `Since ${formatTime(rangeStart.value)}` : `Until ${formatTime(rangeEnd.value)}`;
}

async function loadRange() {
  const requests = Object.keys(metricConfig).map(async metric => {
    const response = await fetch(`${endpoints.historyUrl}?${rangeQuery(metric)}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "History request failed.");
    metricRows[metric] = payload.readings;
  });
  await Promise.all(requests);
  document.querySelector("#active-range-label").textContent = describeRange();
  renderMetrics();
}

const rangeDialog = document.querySelector("#range-dialog");
document.querySelector("#range-button").addEventListener("click", () => rangeDialog.showModal());
document.querySelectorAll(".range-presets button").forEach(button => {
  button.addEventListener("click", () => setRange(button.dataset.hours));
});
[rangeStart, rangeEnd].forEach(input => {
  input.addEventListener("input", event => {
    if (event.isTrusted) rangeDescription = "";
  });
});
document.querySelector("#range-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (event.submitter?.value === "cancel") {
    rangeDialog.close();
    return;
  }
  const error = document.querySelector("#range-error");
  if (rangeStart.value && rangeEnd.value && rangeStart.value > rangeEnd.value) {
    error.textContent = "The start of the range must be before the end.";
    return;
  }
  error.textContent = "";
  rangeDialog.close();
  try {
    await loadRange();
  } catch (requestError) {
    document.querySelector("#active-range-label").textContent = requestError.message;
  }
});

const downloadDialog = document.querySelector("#download-dialog");
const downloadForm = document.querySelector("#download-form");
const downloadRangeSelect = document.querySelector("#download-range-select");
const downloadCustomRange = document.querySelector("#download-custom-range");
document.querySelector("#download-csv").addEventListener("click", () => {
  downloadRangeSelect.value = "current";
  document.querySelector("#download-start").value = rangeStart.value;
  document.querySelector("#download-end").value = rangeEnd.value;
  downloadCustomRange.hidden = true;
  document.querySelector("#download-error").textContent = "";
  downloadDialog.showModal();
});
downloadRangeSelect.addEventListener("change", () => {
  downloadCustomRange.hidden = downloadRangeSelect.value !== "custom";
});
downloadForm.addEventListener("submit", event => {
  event.preventDefault();
  if (event.submitter?.value === "cancel") {
    downloadDialog.close();
    return;
  }
  const metrics = [...downloadForm.querySelectorAll("[name=download-metric]:checked")]
    .map(input => input.value);
  const error = document.querySelector("#download-error");
  if (!metrics.length) {
    error.textContent = "Select at least one data type.";
    return;
  }
  const params = new URLSearchParams({ metrics: metrics.join(",") });
  const selection = downloadRangeSelect.value;
  let start = "";
  let end = "";
  if (selection === "current") {
    start = rangeStart.value;
    end = rangeEnd.value;
  } else if (selection === "custom") {
    start = document.querySelector("#download-start").value;
    end = document.querySelector("#download-end").value;
  } else if (selection !== "all") {
    const endDate = new Date();
    start = localInputValue(new Date(endDate.getTime() - Number(selection) * 3_600_000));
    end = localInputValue(endDate);
  }
  if (start && end && start > end) {
    error.textContent = "The start of the range must be before the end.";
    return;
  }
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  downloadDialog.close();
  window.location.assign(`${endpoints.csvUrl}?${params}`);
});

const aboutDialog = document.querySelector("#about-dialog");
document.querySelector("#about-button").addEventListener("click", () => aboutDialog.showModal());
document.querySelector("#about-close").addEventListener("click", () => aboutDialog.close());

const resetExportDialog = document.querySelector("#reset-export-dialog");
const resetConfirmDialog = document.querySelector("#reset-confirm-dialog");
const resetConfirmation = document.querySelector("#reset-confirmation");
const resetPassword = document.querySelector("#reset-password");
document.querySelector("#reset-button").addEventListener("click", () => {
  aboutDialog.close();
  resetExportDialog.showModal();
});
document.querySelector("#reset-export-form").addEventListener("submit", event => {
  event.preventDefault();
  resetExportDialog.close();
  if (event.submitter?.value !== "continue") return;
  resetConfirmation.value = "";
  resetPassword.value = "";
  document.querySelector("#reset-error").textContent = "";
  resetConfirmDialog.showModal();
  resetConfirmation.focus();
});
document.querySelector("#reset-confirm-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (event.submitter?.value !== "reset") {
    resetConfirmDialog.close();
    return;
  }
  const error = document.querySelector("#reset-error");
  if (resetConfirmation.value !== "RESET") {
    error.textContent = "Type RESET exactly to confirm.";
    return;
  }
  if (!resetPassword.value) {
    error.textContent = "Enter the reset password.";
    return;
  }
  const submitButton = event.submitter;
  submitButton.disabled = true;
  error.textContent = "";
  const formData = new FormData(event.currentTarget);
  formData.set("acknowledge_export", "yes");
  try {
    const response = await fetch(endpoints.resetUrl, {
      method: "POST",
      body: formData,
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Reset failed.");
    Object.keys(metricRows).forEach(metric => { metricRows[metric] = []; });
    renderMetrics();
    document.querySelector("#last-recorded").textContent = "Waiting for first reading";
    resetConfirmDialog.close();
  } catch (requestError) {
    error.textContent = requestError.message;
  } finally {
    submitButton.disabled = false;
  }
});

setRange(24);
loadRange();

const connectionStatus = document.querySelector("#connection-status");
const socketUrl = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/readings/`;
let socket;
let reconnectTimer;
let reconnectAttempt = 0;
let pageClosing = false;

function receiveReading(event) {
  const reading = JSON.parse(event.data);
  if (reading.kind !== "environment") return;
  const observedAt = new Date(reading.recorded_at);
  const start = rangeStart.value ? new Date(rangeStart.value) : undefined;
  const end = rangeEnd.value ? new Date(rangeEnd.value) : undefined;
  if ((!start || observedAt >= start) && (!end || observedAt <= end)) {
    Object.keys(metricConfig).forEach(metric => {
      metricRows[metric].push({ recorded_at: reading.recorded_at, value: reading[metric] });
    });
  }
  document.querySelector("#last-recorded").textContent = `Last reading ${formatTime(reading.recorded_at)}`;
  renderMetrics();
}

function scheduleReconnect() {
  if (pageClosing || reconnectTimer) return;
  const base = Math.min(30_000, 1_000 * (2 ** reconnectAttempt));
  const delay = Math.round(base * (0.8 + Math.random() * 0.4));
  reconnectAttempt += 1;
  connectionStatus.textContent = navigator.onLine
    ? `Reconnecting in ${Math.max(1, Math.round(delay / 1000))}s`
    : "Offline · waiting for network";
  reconnectTimer = window.setTimeout(() => {
    reconnectTimer = undefined;
    connectSocket();
  }, delay);
}

function connectSocket() {
  if (pageClosing || !navigator.onLine) return scheduleReconnect();
  if (socket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.readyState)) return;
  connectionStatus.textContent = reconnectAttempt ? "Reconnecting" : "Connecting";
  socket = new WebSocket(socketUrl);
  socket.addEventListener("open", () => {
    reconnectAttempt = 0;
    connectionStatus.textContent = "Live · 3 minute cadence";
    document.body.classList.add("is-live");
  });
  socket.addEventListener("message", receiveReading);
  socket.addEventListener("close", () => {
    document.body.classList.remove("is-live");
    scheduleReconnect();
  });
  socket.addEventListener("error", () => socket.close());
}

window.addEventListener("online", () => {
  if (reconnectTimer) window.clearTimeout(reconnectTimer);
  reconnectTimer = undefined;
  connectSocket();
});
window.addEventListener("offline", () => {
  connectionStatus.textContent = "Offline · waiting for network";
  document.body.classList.remove("is-live");
  socket?.close();
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") connectSocket();
});
window.addEventListener("pagehide", () => {
  pageClosing = true;
  if (reconnectTimer) window.clearTimeout(reconnectTimer);
  socket?.close();
});

connectSocket();
