const initialElement = document.querySelector("#reading-history");
const initialReadings = initialElement ? JSON.parse(initialElement.textContent) : [];
const thresholdElement = document.querySelector("#condition-thresholds");
const conditionThresholds = thresholdElement ? JSON.parse(thresholdElement.textContent) : {};
const endpoints = document.querySelector("#endpoints").dataset;
const rangeStart = document.querySelector("#range-start");
const rangeEnd = document.querySelector("#range-end");
const sparklineState = new WeakMap();
let rangeDescription = "Last 12 hours";
let rollingRangeHours = 12;
const observations = new Map();

const metricConfig = {
  temperature_c: { label: "Temperature", unit: "°C", decimals: 1, stableSlope: 0.3 },
  relative_humidity: { label: "Relative humidity", unit: "%", decimals: 1, stableSlope: 1 },
  pressure_hpa: { label: "Atmospheric pressure", unit: "hPa", decimals: 1, stableSlope: 0.5 },
};
const trendWindows = [6, 12, 30];
const missingAfterMs = 10 * 60_000;
const rangePreferenceKey = "graph-range";

const metricRows = Object.fromEntries(
  Object.keys(metricConfig).map(metric => [
    metric,
    initialReadings
      .filter(reading => Number.isFinite(reading[metric]))
      .map(reading => ({ recorded_at: reading.recorded_at, value: reading[metric] })),
  ]),
);

function validObservation(reading) {
  return reading
    && Number.isFinite(new Date(reading.recorded_at).getTime())
    && Object.keys(metricConfig).every(metric => Number.isFinite(reading[metric]));
}

function mergeObservations(readings) {
  readings.filter(validObservation).forEach(reading => {
    observations.set(reading.recorded_at, reading);
  });
}

function selectedBounds() {
  const start = rangeStart.value ? new Date(rangeStart.value).getTime() : -Infinity;
  const end = rangeEnd.value ? new Date(rangeEnd.value).getTime() : Infinity;
  return { start, end };
}

function rebuildMetricRows() {
  const { start, end } = selectedBounds();
  const selected = [...observations.values()]
    .filter(reading => {
      const timestamp = new Date(reading.recorded_at).getTime();
      return timestamp >= start && timestamp <= end;
    })
    .sort((left, right) => (
      new Date(left.recorded_at).getTime() - new Date(right.recorded_at).getTime()
    ));
  Object.keys(metricConfig).forEach(metric => {
    metricRows[metric] = selected.map(reading => ({
      recorded_at: reading.recorded_at,
      value: reading[metric],
    }));
  });
}

function pointsToPath(points) {
  return points.map(([x, y], index) =>
    `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
}

function wavePath(start, end) {
  const distance = end[0] - start[0];
  if (distance <= 0) return "";
  const steps = Math.max(3, Math.ceil(distance / 10));
  const commands = [`M${start[0].toFixed(2)},${start[1].toFixed(2)}`];
  for (let step = 1; step < steps; step += 1) {
    const ratio = step / steps;
    const x = start[0] + distance * ratio;
    const baseline = start[1] + (end[1] - start[1]) * ratio;
    const roughness = (step % 2 ? -1 : 1) * (2.5 + (step % 3));
    commands.push(`L${x.toFixed(2)},${(baseline + roughness).toFixed(2)}`);
  }
  commands.push(`L${end[0].toFixed(2)},${end[1].toFixed(2)}`);
  return commands.join(" ");
}

function graphPaths(rows, points) {
  if (!rows.length) {
    return {
      observed: "",
      area: "",
      missing: wavePath([0, 90], [400, 90]),
    };
  }
  const segments = [];
  const missing = [];
  let segment = [points[0]];
  const firstTime = new Date(rows[0].recorded_at).getTime();
  const timeBounds = chartTimeBounds(rows);
  if (firstTime - timeBounds.start > missingAfterMs && points[0][0] > 0) {
    missing.push(wavePath([0, points[0][1]], points[0]));
  }
  for (let index = 1; index < rows.length; index += 1) {
    const elapsed = (
      new Date(rows[index].recorded_at).getTime()
      - new Date(rows[index - 1].recorded_at).getTime()
    );
    if (elapsed > missingAfterMs) {
      segments.push(segment);
      missing.push(wavePath(points[index - 1], points[index]));
      segment = [points[index]];
    } else {
      segment.push(points[index]);
    }
  }
  segments.push(segment);

  const latestTime = new Date(rows.at(-1).recorded_at).getTime();
  if (timeBounds.end - latestTime > missingAfterMs && points.at(-1)[0] < 400) {
    missing.push(wavePath(points.at(-1), [400, points.at(-1)[1]]));
  }
  return {
    observed: segments.map(pointsToPath).join(" "),
    area: segments
      .filter(item => item.length > 1)
      .map(item => `${pointsToPath(item)} L${item.at(-1)[0].toFixed(2)},180 L${item[0][0].toFixed(2)},180 Z`)
      .join(" "),
    missing: missing.join(" "),
  };
}

function chartTimeBounds(rows) {
  const selected = selectedBounds();
  const firstTime = new Date(rows[0].recorded_at).getTime();
  const lastTime = new Date(rows.at(-1).recorded_at).getTime();
  return {
    start: Number.isFinite(selected.start) ? selected.start : firstTime,
    end: Number.isFinite(selected.end)
      ? selected.end
      : rollingRangeHours !== null ? Date.now() : lastTime,
  };
}

function plot(rows, width, height) {
  const values = rows.map(row => row.value);
  if (!values.length) return { points: [], min: 0, max: 0 };
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const margin = Math.max((rawMax - rawMin) * 0.15, Math.abs(rawMax) * 0.002, 0.2);
  const min = rawMin - margin;
  const max = rawMax + margin;
  const { start: firstTime, end: lastTime } = chartTimeBounds(rows);
  const timeSpan = lastTime - firstTime;
  return {
    min,
    max,
    points: values.map((value, index) => [
      values.length === 1
        ? width / 2
        : timeSpan
          ? ((new Date(rows[index].recorded_at).getTime() - firstTime) / timeSpan) * width
          : width / 2,
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

function utcQueryValue(localValue) {
  return localValue ? new Date(localValue).toISOString() : "";
}

function selectRangePreset(hours) {
  document.querySelectorAll(".range-presets button").forEach(button => {
    const selected = button.dataset.hours === String(hours);
    button.classList.toggle("is-selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
}

function setRange(hours) {
  selectRangePreset(hours);
  if (hours === "all") {
    rollingRangeHours = null;
    rangeStart.value = "";
    rangeEnd.value = "";
    rangeDescription = "All recorded data";
    return;
  }
  rollingRangeHours = Number(hours);
  const start = new Date(Date.now() - Number(hours) * 3_600_000);
  rangeStart.value = localInputValue(start);
  rangeEnd.value = "";
  rangeDescription = {
    24: "Last 24 hours",
    168: "Last 7 days",
    720: "Last 30 days",
  }[hours] || `Last ${hours} hours`;
}

function currentRangePreference() {
  if (rollingRangeHours !== null) {
    return { mode: "rolling", hours: rollingRangeHours };
  }
  if (!rangeStart.value && !rangeEnd.value) return { mode: "all" };
  return {
    mode: "custom",
    start: rangeStart.value,
    end: rangeEnd.value,
  };
}

function restoreRangePreference(preference) {
  if (preference?.mode === "rolling"
      && Number.isFinite(preference.hours)
      && preference.hours > 0) {
    setRange(preference.hours);
    return;
  }
  if (preference?.mode === "all") {
    setRange("all");
    return;
  }
  if (preference?.mode === "custom") {
    const startIsValid = !preference.start
      || Number.isFinite(new Date(preference.start).getTime());
    const endIsValid = !preference.end
      || Number.isFinite(new Date(preference.end).getTime());
    const orderIsValid = !preference.start
      || !preference.end
      || preference.start <= preference.end;
    if (startIsValid && endIsValid && orderIsValid) {
      rollingRangeHours = null;
      rangeStart.value = preference.start || "";
      rangeEnd.value = preference.end || "";
      rangeDescription = "";
      selectRangePreset(null);
      return;
    }
  }
  setRange(12);
}

async function persistRangePreference() {
  try {
    await window.EnpiroDataCache?.putPreference(
      rangePreferenceKey,
      currentRangePreference(),
    );
  } catch (_cacheError) {
    // The selected range still applies for this session if storage is unavailable.
  }
}

function rangeQuery() {
  const params = new URLSearchParams({ metric: "all" });
  if (rangeStart.value) params.set("start", utcQueryValue(rangeStart.value));
  if (rangeEnd.value) params.set("end", utcQueryValue(rangeEnd.value));
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
    card.querySelector(".sparkline__missing").setAttribute("d", wavePath([0, 90], [400, 90]));
    card.querySelectorAll("[data-scale]").forEach(label => { label.textContent = ""; });
    axisLabels.forEach(label => { label.textContent = ""; });
    renderCondition(card, metric, NaN);
    renderTrend(card, metric, rows);
    sparklineState.set(svg, { points: [], rows, metric });
    return;
  }
  card.querySelector(".metric__value").textContent = values.at(-1).toFixed(config.decimals);
  renderTrend(card, metric, rows);
  const timeBounds = chartTimeBounds(rows);
  const axisTimes = [
    timeBounds.start,
    timeBounds.start + ((timeBounds.end - timeBounds.start) / 2),
    timeBounds.end,
  ];
  axisLabels.forEach((label, index) => {
    label.textContent = formatAxisTime(axisTimes[index]);
  });
  renderCondition(card, metric, values.at(-1));
  const { points, min, max } = plot(rows, 400, 180);
  card.querySelector('[data-scale="max"]').textContent = max.toFixed(config.decimals);
  card.querySelector('[data-scale="mid"]').textContent = ((min + max) / 2).toFixed(config.decimals);
  card.querySelector('[data-scale="min"]').textContent = min.toFixed(config.decimals);
  const paths = graphPaths(rows, points);
  card.querySelector(".sparkline__line").setAttribute("d", paths.observed);
  card.querySelector(".sparkline__area").setAttribute("d", paths.area);
  card.querySelector(".sparkline__missing").setAttribute("d", paths.missing);
  sparklineState.set(svg, { points, rows, metric });
}

function renderMetrics() {
  document.querySelectorAll(".metric").forEach(renderMetric);
}

function nearestTimestampPointIndex(event, element, points) {
  const bounds = element.getBoundingClientRect();
  const x = Math.max(0, Math.min(400, ((event.clientX - bounds.left) / bounds.width) * 400));
  return points.reduce((nearest, point, index) => (
    Math.abs(point[0] - x) < Math.abs(points[nearest][0] - x) ? index : nearest
  ), 0);
}

function chartPointerX(event, element) {
  const bounds = element.getBoundingClientRect();
  return Math.max(0, Math.min(400, ((event.clientX - bounds.left) / bounds.width) * 400));
}

function interpolatedPointY(points, x) {
  if (x <= points[0][0]) return points[0][1];
  if (x >= points.at(-1)[0]) return points.at(-1)[1];
  const rightIndex = points.findIndex(point => point[0] >= x);
  const left = points[rightIndex - 1];
  const right = points[rightIndex];
  const distance = right[0] - left[0];
  if (!distance) return right[1];
  const progress = (x - left[0]) / distance;
  const smoothProgress = progress * progress * (3 - (2 * progress));
  return left[1] + ((right[1] - left[1]) * smoothProgress);
}

function showPoint(card, event) {
  const svg = card.querySelector(".sparkline");
  const state = sparklineState.get(svg);
  if (!state?.points.length) return;
  const index = nearestTimestampPointIndex(event, svg, state.points);
  const selectedX = state.points[index][0];
  const markerX = chartPointerX(event, svg);
  const markerY = interpolatedPointY(state.points, markerX);
  const row = state.rows[index];
  const config = metricConfig[state.metric];
  const condition = conditionForValue(state.metric, row.value);
  const pointer = svg.querySelector(".sparkline__pointer");
  const crosshair = svg.querySelector(".sparkline__crosshair");
  const placeBelow = markerY < 24;
  pointer.textContent = placeBelow ? "▲" : "▼";
  pointer.setAttribute("x", markerX);
  pointer.setAttribute("y", placeBelow ? markerY + 20 : markerY - 6);
  crosshair.setAttribute("x1", selectedX);
  crosshair.setAttribute("x2", selectedX);
  crosshair.setAttribute("y1", 0);
  crosshair.setAttribute("y2", 180);
  svg.classList.add("is-inspecting");

  const tooltip = card.querySelector(".chart-tooltip");
  const svgBounds = svg.getBoundingClientRect();
  const cardBounds = card.getBoundingClientRect();
  const chartBounds = card.querySelector(".metric__chart").getBoundingClientRect();
  const pointerX = Math.max(
    svgBounds.left,
    Math.min(svgBounds.right, event.clientX),
  );
  const tooltipX = pointerX - cardBounds.left;
  const safeTooltipX = Math.max(76, Math.min(cardBounds.width - 76, tooltipX));
  const detail = [
    formatTime(row.recorded_at),
    condition?.label,
  ].filter(Boolean).join(" · ");
  tooltip.innerHTML = `<strong>${row.value.toFixed(config.decimals)} ${config.unit}</strong><small>${detail}</small>`;
  tooltip.style.left = `${safeTooltipX}px`;
  tooltip.style.top = `${chartBounds.top - cardBounds.top}px`;
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

function markDisplayedRangeStale() {
  document.querySelectorAll(".metric").forEach(card => {
    card.classList.add("is-refreshing");
  });
}

async function loadRange({ showStale = false } = {}) {
  if (rollingRangeHours !== null) setRange(rollingRangeHours);
  if (showStale) markDisplayedRangeStale();
  const response = await fetch(`${endpoints.historyUrl}?${rangeQuery()}`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail || "History request failed.");
  const completeReadings = payload.readings.filter(validObservation);
  const fetchedTimes = new Set(completeReadings.map(reading => reading.recorded_at));
  const { start, end } = selectedBounds();
  const removedTimes = [...observations.values()]
    .filter(reading => {
      const timestamp = new Date(reading.recorded_at).getTime();
      return timestamp >= start && timestamp <= end && !fetchedTimes.has(reading.recorded_at);
    })
    .map(reading => reading.recorded_at);
  removedTimes.forEach(recordedAt => observations.delete(recordedAt));
  mergeObservations(completeReadings);
  await window.EnpiroDataCache?.deleteMany(removedTimes);
  await window.EnpiroDataCache?.putMany(completeReadings);
  rebuildMetricRows();
  document.querySelector("#active-range-label").textContent = describeRange();
  renderMetrics();
  document.querySelectorAll(".metric.is-refreshing").forEach(card => {
    card.classList.remove("is-refreshing");
  });
}

const rangeDialog = document.querySelector("#range-dialog");
document.querySelector("#range-button").addEventListener("click", () => rangeDialog.showModal());
document.querySelectorAll(".range-presets button").forEach(button => {
  button.addEventListener("click", () => setRange(button.dataset.hours));
});
[rangeStart, rangeEnd].forEach(input => {
  input.addEventListener("input", event => {
    if (event.isTrusted) {
      rangeDescription = "";
      rollingRangeHours = null;
      selectRangePreset(null);
    }
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
    await loadRange({ showStale: true });
    await persistRangePreference();
  } catch (requestError) {
    document.querySelector("#active-range-label").textContent = requestError.message;
    document.querySelectorAll(".metric.is-refreshing").forEach(card => {
      card.classList.remove("is-refreshing");
    });
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
  if (start) params.set("start", utcQueryValue(start));
  if (end) params.set("end", utcQueryValue(end));
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
    observations.clear();
    try {
      await window.EnpiroDataCache?.clear();
    } catch (_cacheError) {
      // The server reset succeeded even if browser storage is unavailable.
    }
    renderMetrics();
    document.querySelector("#last-recorded").textContent = "Waiting for first reading";
    resetConfirmDialog.close();
  } catch (requestError) {
    error.textContent = requestError.message;
  } finally {
    submitButton.disabled = false;
  }
});

async function initializeData() {
  mergeObservations(initialReadings);
  try {
    mergeObservations(await window.EnpiroDataCache?.getAll() || []);
  } catch (_cacheError) {
    // Private browsing modes may make IndexedDB unavailable; the network remains usable.
  }
  try {
    restoreRangePreference(
      await window.EnpiroDataCache?.getPreference(rangePreferenceKey),
    );
  } catch (_cacheError) {
    restoreRangePreference(null);
  }
  rebuildMetricRows();
  document.querySelector("#active-range-label").textContent = describeRange();
  renderMetrics();
  const latest = [...observations.values()].sort((left, right) => (
    new Date(left.recorded_at).getTime() - new Date(right.recorded_at).getTime()
  )).at(-1);
  if (latest) {
    document.querySelector("#last-recorded").textContent = (
      `Last reading ${formatTime(latest.recorded_at)}`
    );
  }
  await loadRange();
}

const connectionStatus = document.querySelector("#connection-status");
const socketUrl = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/readings/`;
let socket;
let reconnectTimer;
let reconnectAttempt = 0;
let pageClosing = false;

async function acceptReading(reading) {
  if (reading.kind !== "environment") return;
  mergeObservations([reading]);
  try {
    await window.EnpiroDataCache?.putMany([reading]);
  } catch (_cacheError) {
    // Continue showing live data if durable browser storage is unavailable.
  }
  if (rollingRangeHours !== null) setRange(rollingRangeHours);
  rebuildMetricRows();
  document.querySelector("#active-range-label").textContent = describeRange();
  document.querySelector("#last-recorded").textContent = `Last reading ${formatTime(reading.recorded_at)}`;
  renderMetrics();
}

function receiveReading(event) {
  acceptReading(JSON.parse(event.data));
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
    const resumedConnection = reconnectAttempt > 0;
    reconnectAttempt = 0;
    connectionStatus.textContent = "Live · 3 minute cadence";
    document.body.classList.add("is-live");
    if (resumedConnection) {
      loadRange().catch(() => {
        // Cached observations remain visible while a history request is unavailable.
      });
    }
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
  resumeLiveData();
});
window.addEventListener("offline", () => {
  connectionStatus.textContent = "Offline · waiting for network";
  document.body.classList.remove("is-live");
  socket?.close();
});
async function resumeLiveData() {
  connectSocket();
  try {
    await loadRange();
  } catch (_requestError) {
    // Cached observations remain visible until connectivity returns.
  }
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") resumeLiveData();
});
window.addEventListener("pagehide", () => {
  pageClosing = true;
  if (reconnectTimer) window.clearTimeout(reconnectTimer);
  socket?.close();
});

initializeData().catch(requestError => {
  document.querySelector("#active-range-label").textContent = requestError.message;
});
connectSocket();
