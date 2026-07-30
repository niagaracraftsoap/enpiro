const historyElement = document.querySelector("#reading-history");
const readings = historyElement
  ? JSON.parse(historyElement.textContent)
  : { environment: [], air_quality: [] };
const maxReadings = 48;

const metricConfig = {
  temperature_c: { decimals: 1 },
  relative_humidity: { decimals: 1, bounds: [0, 100] },
  pressure_hpa: { decimals: 1 },
  air_quality_percentage: { decimals: 0, bounds: [0, 100] },
};

function pointsToPath(points) {
  return points.map(([x, y], index) => `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
}

function project(values, count) {
  const sample = values.slice(-Math.min(values.length, 12));
  if (sample.length < 2) return Array(count).fill(sample.at(-1));

  const xMean = (sample.length - 1) / 2;
  const yMean = sample.reduce((sum, value) => sum + value, 0) / sample.length;
  let numerator = 0;
  let denominator = 0;
  sample.forEach((value, index) => {
    numerator += (index - xMean) * (value - yMean);
    denominator += (index - xMean) ** 2;
  });
  const slope = denominator ? numerator / denominator : 0;
  return Array.from({ length: count }, (_, index) => sample.at(-1) + slope * (index + 1));
}

function renderDial(dial) {
  const metric = dial.dataset.metric;
  const config = metricConfig[metric];
  const stream = metric === "air_quality_percentage"
    ? readings.air_quality
    : readings.environment;
  const usableStream = metric === "air_quality_percentage"
    ? stream.filter(reading => reading.valid)
    : stream;
  const values = usableStream.map(reading => reading[metric]).filter(Number.isFinite);
  const valueElement = dial.querySelector(".dial__value");

  if (!values.length) {
    valueElement.textContent = "—";
    dial.querySelectorAll("path, line, circle").forEach(element => element.removeAttribute("d"));
    dial.querySelector(".chart__point").style.display = "none";
    return;
  }

  valueElement.textContent = values.at(-1).toFixed(config.decimals);
  const forecastCount = Math.max(2, Math.min(8, Math.ceil(values.length / 4)));
  let forecast = project(values, forecastCount);
  if (config.bounds) {
    forecast = forecast.map(value => Math.max(config.bounds[0], Math.min(config.bounds[1], value)));
  }

  const allValues = [...values, ...forecast];
  const rawMin = Math.min(...allValues);
  const rawMax = Math.max(...allValues);
  const padding = Math.max((rawMax - rawMin) * .18, Math.abs(rawMax) * .006, 1);
  const min = rawMin - padding;
  const max = rawMax + padding;
  const width = 400;
  const height = 180;
  const nowX = width * .75;
  const toY = value => height - ((value - min) / (max - min)) * height;
  const historyPoints = values.map((value, index) => [
    values.length === 1 ? nowX : (index / (values.length - 1)) * nowX,
    toY(value),
  ]);
  const projectionPoints = [
    historyPoints.at(-1),
    ...forecast.map((value, index) => [
      nowX + ((index + 1) / forecast.length) * (width - nowX),
      toY(value),
    ]),
  ];

  const svg = dial.querySelector("svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  dial.querySelector(".chart__history").setAttribute("d", pointsToPath(historyPoints));
  dial.querySelector(".chart__projection").setAttribute("d", pointsToPath(projectionPoints));
  dial.querySelector(".chart__area").setAttribute(
    "d",
    `${pointsToPath(historyPoints)} L${nowX},${height} L0,${height} Z`,
  );
  const nowLine = dial.querySelector(".chart__now");
  nowLine.setAttribute("x1", nowX);
  nowLine.setAttribute("x2", nowX);
  nowLine.setAttribute("y1", 0);
  nowLine.setAttribute("y2", height);
  const point = dial.querySelector(".chart__point");
  point.style.display = "";
  point.setAttribute("cx", nowX);
  point.setAttribute("cy", historyPoints.at(-1)[1]);
}

function renderAllDials() {
  document.querySelectorAll(".dial").forEach(renderDial);
}

renderAllDials();

const socketScheme = location.protocol === "https:" ? "wss" : "ws";
const socket = new WebSocket(`${socketScheme}://${location.host}/ws/readings/`);
const connectionStatus = document.querySelector("#connection-status");

socket.addEventListener("open", () => {
  connectionStatus.textContent = "Live";
});
socket.addEventListener("close", () => {
  connectionStatus.textContent = "Offline";
});
socket.addEventListener("message", event => {
  const reading = JSON.parse(event.data);
  const stream = reading.kind === "air_quality"
    ? readings.air_quality
    : readings.environment;
  stream.push(reading);
  if (stream.length > maxReadings) stream.shift();
  renderAllDials();
});
