const elements = {
  healthPill: document.getElementById("healthPill"),
  moistureReadings: document.getElementById("moistureReadings"),
  refreshBtn: document.getElementById("refreshBtn"),
  waterNote: document.getElementById("waterNote"),
  hardwareState: document.getElementById("hardwareState"),
  pumpToggle: document.getElementById("pumpToggle"),
  valveToggle: document.getElementById("valveToggle"),
  stopBtn: document.getElementById("stopBtn"),
};
const waterButtons = [...document.querySelectorAll("button[data-seconds]")];
const state = { hardware: {}, operation: {}, online: false, busy: false };
let statusVersion = 0;
let commandVersion = 0;

async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch(path, {
      ...options,
      headers: options.body ? { "Content-Type": "application/json" } : {},
      cache: "no-store",
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Request failed: ${response.status}`);
    return data;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("Request timed out. Device state is unconfirmed; check status or use Stop all.");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function render() {
  const hw = state.hardware;
  const operation = state.operation;
  const available = state.online && hw.ready;
  const locked = !available || state.busy;
  const cycle = operation.mode === "watering";
  const volumeButton = document.getElementById("volumeBtn");
  if (volumeButton) volumeButton.disabled = locked || operation.active || !state.flow?.configured || !state.flow?.calibrated || hw.pump_on !== false || hw.valve_open !== false;
  waterButtons.forEach((button) => {
    button.disabled = locked || operation.active || hw.pump_on !== false || hw.valve_open !== false;
  });
  elements.pumpToggle.disabled = locked || cycle || (!hw.pump_on && hw.valve_open !== true);
  elements.valveToggle.disabled = locked || cycle || hw.pump_on !== false;
  elements.pumpToggle.textContent = hw.pump_on ? "Stop pump" : "Start pump";
  elements.valveToggle.textContent = hw.valve_open ? "Close valve" : "Open valve";
  elements.healthPill.textContent = state.online ? "API: online" : "API: offline";
  elements.healthPill.classList.toggle("ok", state.online);
  if (!state.online) {
    elements.hardwareState.textContent = "Status unavailable. Displayed readings may be outdated.";
    elements.waterNote.textContent = "Device state is unknown. Stop all remains available.";
    return;
  }
  const label = (value, yes, no) => value === true ? yes : value === false ? no : "unknown";
  const mode = hw.simulated ? "SIMULATION" : hw.ready ? "GPIO ready" : "unavailable";
  elements.hardwareState.textContent = `Pump: ${label(hw.pump_on, "on", "off")} | Valve: ${label(hw.valve_open, "open", "closed")} | ${mode}${hw.error ? ` | ${hw.error}` : ""}`;
  if (operation.error || hw.error) {
    elements.waterNote.textContent = operation.error || hw.error;
  } else if (operation.active) {
    elements.waterNote.textContent = `${cycle ? "Watering" : "Manual control"}: ${operation.remaining_seconds}s remaining${hw.simulated ? " (simulation)" : ""}`;
  } else {
    const messages = { completed: "Watering completed.", cancelled: "Stopped.", stopped: "Stopped.", timeout: "Manual safety timeout: outputs switched off.", failed: "Operation failed.", sensor_error: "Stopped: invalid moisture reading." };
    elements.waterNote.textContent = messages[operation.last_result] || "Idle";
  }
}

async function refreshStatus() {
  const version = ++statusVersion;
  try {
    const data = await api("/api/status");
    if (version !== statusVersion) return;
    state.hardware = data.hardware;
    state.operation = data.operation;
    state.flow = data.flow;
    state.automation = data.automation;
    state.online = true;
  } catch (error) {
    if (version !== statusVersion) return;
    state.online = false;
  }
  render();
}

async function refreshMoisture() {
  try {
    const data = await api("/api/moisture");
    if (data.simulated) {
      elements.moistureReadings.textContent = "Simulation: no physical readings.";
      return;
    }
    elements.moistureReadings.textContent = data.readings.length
      ? data.readings.map((value, index) => {
        const sample = data.samples?.find((item) => item.channel === data.channels[index]);
        return `CH${data.channels[index]}: ${Number.isFinite(value) ? value.toFixed(3) : "n/a"}${Number.isFinite(sample?.moisture_percent) ? ` (${sample.moisture_percent.toFixed(1)}%)` : ""}`;
      }).join(" | ")
      : "No readings available.";
  } catch (error) {
    elements.moistureReadings.textContent = "Read failed.";
  }
}

async function command(path, body) {
  if (state.busy && path !== "/api/stop") return;
  const version = ++commandVersion;
  ++statusVersion; // Ignore status requests started before this command.
  state.busy = true;
  render();
  let failure = null;
  try {
    await api(path, { method: "POST", ...(body ? { body: JSON.stringify(body) } : {}) });
  } catch (error) {
    failure = error.message;
  } finally {
    if (version === commandVersion) {
      await refreshStatus();
      // A Stop command may have arrived while refreshing the earlier command.
      if (version === commandVersion) {
        state.busy = false;
        render();
        if (failure) elements.waterNote.textContent = failure;
      }
    }
  }
}

waterButtons.forEach((button) => {
  button.addEventListener("click", () => command("/api/water", { seconds: Number(button.dataset.seconds), zone: 0 }));
});
elements.pumpToggle.addEventListener("click", () => command("/api/pump", { on: !state.hardware.pump_on }));
elements.valveToggle.addEventListener("click", () => command("/api/valve", { open: !state.hardware.valve_open }));
elements.stopBtn.addEventListener("click", () => command("/api/stop"));
elements.refreshBtn.addEventListener("click", refreshMoisture);

async function poll() {
  if (!state.busy) await Promise.all([refreshStatus(), refreshMoisture()]);
  setTimeout(poll, 1000);
}

render();
poll();
