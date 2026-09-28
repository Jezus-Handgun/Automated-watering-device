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
    if (!response.ok) throw new Error(data.error || `Żądanie nie powiodło się. Kod HTTP: ${response.status}`);
    return data;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("Przekroczono czas oczekiwania. Stan urządzeń jest nieznany. Sprawdź połączenie lub użyj przycisku „Zatrzymaj wszystko”.");
    }
    if (error instanceof TypeError) throw new Error("Nie udało się połączyć z serwerem. Sprawdź połączenie.");
    if (error instanceof SyntaxError) throw new Error("Serwer zwrócił niepoprawną odpowiedź.");
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
  const valveEnabled = hw.valve_enabled !== false;
  const valveOff = !valveEnabled || hw.valve_open === false;
  const lowWater = hw.water_level?.configured && hw.water_level.water_present !== true;
  const remainingBudget = state.automation
    ? Math.max(0, state.automation.daily_limit_seconds - state.automation.daily_used_seconds)
    : Infinity;
  const manualBudgetBlocked = !operation.active && remainingBudget < (operation.manual_timeout_seconds ?? 60);
  const volumeButton = document.getElementById("volumeBtn");
  if (volumeButton) volumeButton.disabled = locked || lowWater || operation.active || !state.flow?.configured || !state.flow?.calibrated || hw.pump_on !== false || !valveOff;
  waterButtons.forEach((button) => {
    button.disabled = locked || lowWater || operation.active || hw.pump_on !== false || !valveOff || Number(button.dataset.seconds) > remainingBudget;
  });
  elements.pumpToggle.disabled = locked || cycle || (!hw.pump_on && (lowWater || manualBudgetBlocked || (valveEnabled && hw.valve_open !== true)));
  elements.valveToggle.disabled = !valveEnabled || locked || cycle || hw.pump_on !== false || (!hw.valve_open && (lowWater || manualBudgetBlocked));
  elements.pumpToggle.textContent = hw.pump_on ? "Zatrzymaj pompę" : "Uruchom pompę";
  elements.valveToggle.textContent = !valveEnabled ? "Brak zaworu" : hw.valve_open ? "Zamknij zawór" : "Otwórz zawór";
  elements.healthPill.textContent = state.online ? "API: połączono" : "API: brak połączenia";
  elements.healthPill.classList.toggle("ok", state.online);
  if (!state.online) {
    elements.hardwareState.textContent = "Stan urządzeń jest niedostępny. Wyświetlane pomiary mogą być nieaktualne.";
    elements.waterNote.textContent = "Stan urządzeń jest nieznany. Przycisk „Zatrzymaj wszystko” pozostaje dostępny.";
    return;
  }
  const label = (value, yes, no) => value === true ? yes : value === false ? no : "nieznany";
  const mode = hw.simulated ? "SYMULACJA" : hw.ready ? "GPIO gotowe" : "niedostępne";
  elements.hardwareState.textContent = `Pompa: ${label(hw.pump_on, "włączona", "wyłączona")} | Zawór: ${valveEnabled ? label(hw.valve_open, "otwarty", "zamknięty") : "niezamontowany"} | ${mode}${hw.error ? ` | ${hw.error}` : ""}`;
  elements.hardwareState.textContent += hw.water_level?.configured
    ? ` | Woda: ${label(hw.water_level.water_present, "obecna", "brak (low_water)")}`
    : " | Poziom wody: brak czujnika";
  if (operation.error || hw.error) {
    elements.waterNote.textContent = operation.error || hw.error;
  } else if (lowWater) {
    elements.waterNote.textContent = "Start zablokowany (low_water): brak wody lub nieznany stan pływaka. Sprawdź zbiornik i przewód.";
  } else if (operation.active) {
    elements.waterNote.textContent = `${cycle ? "Podlewanie" : "Sterowanie ręczne"}: pozostało ${operation.remaining_seconds} s${hw.simulated ? " (symulacja)" : ""}`;
  } else {
    const messages = { low_water: "Zatrzymano podlewanie: brak potwierdzenia obecności wody (low_water).", completed: "Podlewanie zakończone.", cancelled: "Zatrzymano.", stopped: "Zatrzymano.", timeout: "Upłynął limit sterowania ręcznego. Wyłączono pompę i zawór.", failed: "Operacja nie powiodła się.", sensor_error: "Zatrzymano podlewanie: niepoprawny pomiar wilgotności." };
    elements.waterNote.textContent = messages[operation.last_result] || "Gotowość";
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
      elements.moistureReadings.textContent = "Symulacja: brak odczytów z rzeczywistych czujników.";
      return;
    }
    elements.moistureReadings.textContent = data.readings.length
      ? data.readings.map((value, index) => {
        const sample = data.samples?.find((item) => item.channel === data.channels[index]);
        return `Kanał ${data.channels[index]}: ${Number.isFinite(value) ? value.toLocaleString("pl-PL", {minimumFractionDigits: 3, maximumFractionDigits: 3}) : "brak danych"}${Number.isFinite(sample?.moisture_percent) ? ` (${sample.moisture_percent.toLocaleString("pl-PL", {minimumFractionDigits: 1, maximumFractionDigits: 1})}%)` : ""}`;
      }).join(" | ")
      : "Brak dostępnych pomiarów.";
  } catch (error) {
    elements.moistureReadings.textContent = "Nie udało się odczytać pomiarów.";
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
  button.addEventListener("click", () => { if (!button.disabled) return command("/api/water", { seconds: Number(button.dataset.seconds), zone: 0 }); });
});
elements.pumpToggle.addEventListener("click", () => { if (!elements.pumpToggle.disabled) return command("/api/pump", { on: !state.hardware.pump_on }); });
elements.valveToggle.addEventListener("click", () => { if (!elements.valveToggle.disabled) return command("/api/valve", { open: !state.hardware.valve_open }); });
elements.stopBtn.addEventListener("click", () => command("/api/stop"));
elements.refreshBtn.addEventListener("click", refreshMoisture);

async function poll() {
  if (!state.busy) await Promise.all([refreshStatus(), refreshMoisture()]);
  setTimeout(poll, 1000);
}

render();
poll();
