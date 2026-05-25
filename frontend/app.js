const API_BASE = "";

const elements = {
  healthPill: document.getElementById("healthPill"),
  moistureReadings: document.getElementById("moistureReadings"),
  refreshBtn: document.getElementById("refreshBtn"),
  waterNote: document.getElementById("waterNote"),
  hardwareState: document.getElementById("hardwareState"),
  pumpToggle: document.getElementById("pumpToggle"),
  valveToggle: document.getElementById("valveToggle"),
};

const state = {
  pumpOn: false,
  valveOpen: false,
  hardwareAvailable: false,
};

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
    },
    ...options,
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed: ${response.status}`);
  }

  return response.json();
}

async function checkHealth() {
  try {
    const data = await api("/api/health");
    elements.healthPill.textContent = `API: ${data.status}`;
    elements.healthPill.classList.add("ok");
  } catch (error) {
    elements.healthPill.textContent = "API: offline";
    elements.healthPill.classList.remove("ok");
  }
}

function renderMoisture(readings) {
  if (!readings || readings.length === 0) {
    elements.moistureReadings.textContent = "No readings available.";
    return;
  }

  const lines = readings.map((value, index) => {
    const text = Number.isFinite(value) ? value.toFixed(3) : "n/a";
    return `CH${index}: ${text}`;
  });
  elements.moistureReadings.textContent = lines.join(" | ");
}

function renderHardwareState() {
  const pump = state.pumpOn ? "on" : "off";
  const valve = state.valveOpen ? "open" : "closed";
  const availability = state.hardwareAvailable ? "ready" : "simulated";
  elements.hardwareState.textContent = `Pump: ${pump} | Valve: ${valve} | ${availability}`;
}

async function refreshStatus() {
  try {
    const data = await api("/api/status");
    const hardware = data.hardware || {};
    state.pumpOn = Boolean(hardware.pump_on);
    state.valveOpen = Boolean(hardware.valve_open);
    state.hardwareAvailable = Boolean(hardware.available);
    renderHardwareState();
  } catch (error) {
    elements.hardwareState.textContent = "Status unavailable.";
  }
}

async function refreshMoisture() {
  try {
    const data = await api("/api/moisture");
    renderMoisture(data.readings || []);
  } catch (error) {
    elements.moistureReadings.textContent = "Read failed.";
  }
}

async function waterFor(seconds) {
  elements.waterNote.textContent = `Watering for ${seconds}s...`;
  try {
    await api("/api/water", {
      method: "POST",
      body: JSON.stringify({ seconds }),
    });
    await refreshStatus();
    elements.waterNote.textContent = "Done.";
  } catch (error) {
    elements.waterNote.textContent = "Water command failed.";
  }
}

async function toggleDevice(device) {
  const isPump = device === "pump";
  const on = isPump ? !state.pumpOn : !state.valveOpen;
  const path = isPump ? "/api/pump" : "/api/valve";
  const payload = isPump ? { on } : { open: on };

  try {
    await api(path, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    await refreshStatus();
  } catch (error) {
    elements.hardwareState.textContent = "Toggle failed.";
  }
}

function bindEvents() {
  document.querySelectorAll("button[data-seconds]").forEach((button) => {
    button.addEventListener("click", () => {
      const seconds = Number(button.dataset.seconds || 5);
      waterFor(seconds);
    });
  });

  elements.refreshBtn.addEventListener("click", async () => {
    await refreshMoisture();
  });

  elements.pumpToggle.addEventListener("click", () => toggleDevice("pump"));
  elements.valveToggle.addEventListener("click", () => toggleDevice("valve"));
}

async function start() {
  bindEvents();
  await checkHealth();
  await refreshStatus();
  await refreshMoisture();
  setInterval(() => {
    refreshStatus();
    refreshMoisture();
  }, 10000);
}

start();
