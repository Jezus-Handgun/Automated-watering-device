const legacyMessages = {
  "enabled must be a JSON boolean.": "Włączenie automatyki musi mieć wartość logiczną true albo false.",
  "channel must be a configured moisture channel.": "Wybierz skonfigurowany kanał czujnika wilgotności.",
  "filter_samples must be odd.": "Liczba próbek filtra musi być nieparzysta.",
  "Thresholds must satisfy 0 <= start_percent < stop_percent <= 100.": "Progi muszą należeć do zakresu 0–100%, a próg rozpoczęcia musi być niższy od progu zakończenia.",
  "Dry and wet reference readings must differ by at least 0.01.": "Odczyty suchego i mokrego podłoża muszą różnić się o co najmniej 0,01.",
  "portion_mode must be time or volume; portion_ml must be 1–5000.": "Wybierz porcję odmierzaną czasem lub objętością; objętość musi wynosić od 1 do 5000 ml.",
  "flow_pulses_per_liter must be null or a number from 1 to 1000000.": "Liczba impulsów na litr musi być pusta lub wynosić od 1 do 1000000.",
  "Calibrate dry_raw and wet_raw before enabling automation.": "Przed włączeniem automatyki skalibruj czujnik dla suchego i mokrego podłoża.",
  "The portion timeout exceeds the daily time budget.": "Limit czasu porcji przekracza dzienny budżet podlewania.",
  "Volume automation requires a configured and calibrated flow meter.": "Automatyczne podlewanie według objętości wymaga skonfigurowanego i skalibrowanego przepływomierza.",
  "Missing or invalid sensor reading.": "Brak odczytu czujnika lub niepoprawny pomiar.",
  "Sensor reading at ADC limit; inspect the sensor.": "Odczyt osiągnął granicę zakresu przetwornika ADC. Sprawdź czujnik.",
  "Collecting fresh samples.": "Zbieranie nowych próbek.",
  "Application is shutting down.": "Aplikacja jest zamykana.",
  "History storage unavailable.": "Zapis historii jest niedostępny.",
  "Invalid JSON body.": "Niepoprawna treść żądania JSON.",
  "Field 'seconds' must be a JSON integer between 1 and 600.": "Czas podlewania musi być liczbą całkowitą od 1 do 600 sekund.",
  "Only zone 0 is supported; 'zone' must be the JSON integer 0.": "Obsługiwana jest tylko strefa 0. Numer strefy musi być liczbą całkowitą 0.",
  "volume_ml must be a finite number from 1 to 5000.": "Objętość musi być skończoną liczbą od 1 do 5000 ml.",
  "Provide run_id and measured_ml in a JSON object.": "Podaj numer cyklu i zmierzoną objętość w obiekcie JSON.",
  "Unknown history type.": "Nieznany rodzaj historii.",
  "MANUAL_TIMEOUT_SECONDS must be an integer from 1 to 600.": "MANUAL_TIMEOUT_SECONDS musi być liczbą całkowitą od 1 do 600.",
  "Cannot persist system event": "Nie udało się zapisać zdarzenia",
  "Hardware is unavailable or closed.": "Sprzęt jest niedostępny lub został wyłączony.",
  "Cannot persist watering result": "Nie udało się zapisać wyniku podlewania",
  "History storage unavailable; outputs switched off.": "Zapis historii jest niedostępny. Wyłączono pompę i zawór.",
  "No flow detected while the pump is running.": "Nie wykryto przepływu podczas pracy pompy.",
  "Target volume was not reached within the time limit.": "Nie osiągnięto zadanej objętości w wyznaczonym czasie.",
  "seconds must be an integer from 1 to 600.": "Czas podlewania musi być liczbą całkowitą od 1 do 600 sekund.",
  "Only zone 0 is supported.": "Obsługiwana jest tylko strefa 0.",
  "Another session is active. Stop it before starting watering.": "Inna sesja jest aktywna. Zatrzymaj ją przed rozpoczęciem podlewania.",
  "Volume control requires a configured and calibrated flow meter.": "Podlewanie według objętości wymaga skonfigurowanego i skalibrowanego przepływomierza.",
  "Watering is active. Use Stop all to cancel it.": "Podlewanie trwa. Użyj przycisku „Zatrzymaj wszystko”, aby je przerwać.",
  "Open the valve before starting the pump.": "Otwórz zawór przed uruchomieniem pompy.",
  "Stop the pump before closing the valve, or use Stop all.": "Zatrzymaj pompę przed zamknięciem zaworu lub użyj przycisku „Zatrzymaj wszystko”.",
  "Cannot persist disabled automation; inspect storage before restarting.": "Nie udało się zapisać wyłączenia automatyki. Sprawdź bazę danych przed ponownym uruchomieniem.",
  "Provide known settings fields in a non-empty JSON object.": "Podaj obsługiwane pola ustawień w niepustym obiekcie JSON.",
  "Stop watering before changing settings or calibration.": "Zatrzymaj podlewanie przed zmianą ustawień lub kalibracji.",
  "Provide a positive run_id and measured_ml from 1 to 100000.": "Podaj dodatni numer cyklu i zmierzoną objętość od 1 do 100000 ml.",
  "Choose a finished run with recorded pulses in the current hardware mode.": "Wybierz zakończony cykl z zapisanymi impulsami w bieżącym trybie sprzętu.",
  "Moisture reading became invalid.": "Pomiar wilgotności stał się niepoprawny.",
  "Sampling failed": "Nie udało się pobrać pomiarów",
  "HARDWARE_MODE must be real or simulation.": "HARDWARE_MODE musi mieć wartość real albo simulation.",
  "Pump and valve pins must be BCM integers from 0 to 27.": "Numery pinów BCM muszą być liczbami całkowitymi od 0 do 27.",
  "Pump, valve and flow meter must use different GPIO pins.": "Pompa, zawór i przepływomierz muszą używać różnych pinów GPIO.",
  "FLOW_PULL_UP must be a boolean.": "FLOW_PULL_UP musi mieć wartość logiczną.",
  "MCP3008 channels must be integers from 0 to 7.": "Kanały MCP3008 muszą być liczbami całkowitymi od 0 do 7.",
  "MCP3008 channels must not repeat.": "Kanały MCP3008 nie mogą się powtarzać.",
  "Actuator pins must not overlap the MCP3008 SPI pins (7–11).": "Piny urządzeń nie mogą pokrywać się z pinami SPI przetwornika MCP3008 (7–11).",
  "Hardware configuration requires integer pins/channels.": "Numery pinów i kanałów w konfiguracji sprzętu muszą być całkowite.",
  "MOISTURE_CHANNELS must be a comma-separated list.": "MOISTURE_CHANNELS musi być listą kanałów rozdzielonych przecinkami.",
  "FLOW_PULL_UP must be 0 or 1.": "FLOW_PULL_UP musi mieć wartość 0 albo 1.",
  "gpiozero is unavailable. Install the hardware dependencies.": "Biblioteka gpiozero jest niedostępna. Zainstaluj zależności obsługi sprzętu.",
  "Device is unavailable.": "Urządzenie jest niedostępne.",
  "GPIO/ADC access only; this does not verify water flow or physical device operation.": "Sprawdzono wyłącznie dostęp do GPIO/ADC. Nie potwierdza to przepływu wody ani fizycznego działania urządzeń.",
  "Database schema is newer than this application.": "Schemat bazy danych jest nowszy niż ta wersja aplikacji.",
  "Daily watering time budget exhausted.": "Wyczerpano dzienny budżet czasu podlewania.",
  "Application stopped before recording completion; volume is unknown.": "Aplikacja została zatrzymana przed zapisaniem wyniku. Objętość wody jest nieznana.",
  "Database schema updated; existing data preserved.": "Zaktualizowano schemat bazy danych. Zachowano dotychczasowe dane."
};
function polishMessage(message) {
  if (!message) return "—";
  if (legacyMessages[message]) return legacyMessages[message];
  const channel = message.match(/^CH(\d+): (.*)$/);
  if (channel) return `Kanał ${channel[1]}: ${polishMessage(channel[2])}`;
  const device = message.match(/^(pump|valve): (.*)$/);
  if (device) return `${device[1] === "pump" ? "Pompa" : "Zawór"}: ${polishMessage(device[2])}`;
  const recovery = message.match(/^Marked (\d+) unfinished sessions interrupted; reserved budgets retained\.$/);
  if (recovery) return `Oznaczono niedokończone sesje jako przerwane: ${recovery[1]}. Zachowano rezerwacje budżetu.`;
  for (const [prefix, translated] of [
    ["Hardware initialization failed:", "Nie udało się uruchomić sprzętu. Sprawdź konfigurację i połączenia."],
    ["GPIO state read failed:", "Nie udało się odczytać stanu GPIO."],
    ["Cannot switch", "Nie udało się przełączyć urządzenia."],
    ["Cannot persist sensor readings:", "Nie udało się zapisać pomiarów czujników."],
    ["Cannot record watering start:", "Nie udało się zapisać rozpoczęcia podlewania."],
    ["Sampling failed:", "Nie udało się pobrać pomiarów."]
  ]) if (message.startsWith(prefix)) return translated;
  return message;
}
const historyLabels = {
  manual: "ręczne", automatic: "automatyczne", legacy: "dane archiwalne",
  running: "w trakcie", completed: "zakończone", cancelled: "anulowane",
  stopped: "zatrzymane", timeout: "limit czasu", failed: "błąd",
  interrupted: "przerwane", sensor_error: "błąd czujnika",
  hardware_error: "błąd sprzętu", control_error: "błąd sterowania", recovery: "odzyskiwanie po restarcie"
};

const feature = Object.fromEntries(
  [
    "automationForm",
    "automationStatus",
    "settingsNote",
    "flowForm",
    "flowCalibrationForm",
    "flowStatus",
    "flowNote",
    "volumeForm",
    "volumeBtn",
    "volumeProgress",
    "historyForm",
    "moistureChart",
    "historyNote",
    "runsBody",
    "eventsList",
    "olderRuns",
    "olderEvents",
    "sampleTime",
  ].map((id) => [id, document.getElementById(id)]),
);
let savedSettings = null;
let runsCursor = null;
let eventsCursor = null;
let historyVersion = 0;
let browsingOlder = false;
let featurePollCount = 0;

function fillSettings(settings) {
  savedSettings = settings;
  for (const form of [feature.automationForm, feature.flowForm]) {
    for (const input of form.elements) {
      if (!(input.name in settings)) continue;
      if (input.type === "checkbox") input.checked = settings[input.name];
      else input.value = settings[input.name] ?? "";
    }
  }
}

function formValues(form) {
  const values = {};
  for (const input of form.elements) {
    if (!input.name) continue;
    values[input.name] =
      input.type === "checkbox"
        ? input.checked
        : input.type === "number"
          ? input.value === ""
            ? null
            : Number(input.value)
          : input.value;
  }
  return values;
}

async function saveForm(form, note, path = "/api/settings", method = "PUT") {
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    fillSettings(
      await api(path, { method, body: JSON.stringify(formValues(form)) }),
    );
    note.textContent = "Zapisano. Nowe pomiary użyją tych ustawień.";
    await refreshStatus();
    await updateFeatures();
  } catch (error) {
    note.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

feature.automationForm.addEventListener("submit", (event) => {
  event.preventDefault();
  saveForm(feature.automationForm, feature.settingsNote);
});
feature.flowForm.addEventListener("submit", (event) => {
  event.preventDefault();
  saveForm(feature.flowForm, feature.flowNote);
});
feature.flowCalibrationForm.addEventListener("submit", (event) => {
  event.preventDefault();
  saveForm(
    feature.flowCalibrationForm,
    feature.flowNote,
    "/api/flow/calibrate",
    "POST",
  );
});
feature.volumeForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (!feature.volumeBtn.disabled)
    command("/api/water", { ...formValues(feature.volumeForm), zone: 0 });
});
document.getElementById("stopBtn").addEventListener("click", () => {
  feature.automationForm.elements.enabled.checked = false;
  if (savedSettings) savedSettings.enabled = false;
});
feature.automationForm.elements.channel.addEventListener("change", () => {
  feature.automationForm.elements.dry_raw.value = "";
  feature.automationForm.elements.wet_raw.value = "";
  feature.automationForm.elements.enabled.checked = false;
  feature.settingsNote.textContent =
    "Nowy kanał wymaga osobnej kalibracji suchego i mokrego podłoża.";
});

for (const [id, field] of [
  ["captureDry", "dry_raw"],
  ["captureWet", "wet_raw"],
]) {
  document.getElementById(id).addEventListener("click", async () => {
    try {
      const data = await api("/api/moisture");
      const channel = Number(feature.automationForm.elements.channel.value);
      const raw = data.readings[data.channels.indexOf(channel)];
      if (
        data.simulated ||
        !Number.isFinite(raw) ||
        raw <= 0.001 ||
        raw >= 0.999
      )
        throw new Error("Brak poprawnego odczytu rzeczywistego czujnika.");
      feature.automationForm.elements[field].value = raw;
      feature.settingsNote.textContent =
        "Odczytano punkt odniesienia. Zapisz ustawienia po zebraniu obu punktów.";
    } catch (error) {
      feature.settingsNote.textContent = error.message;
    }
  });
}

function svgElement(name, attributes, text) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes))
    element.setAttribute(key, String(value));
  if (text !== undefined) element.textContent = text;
  feature.moistureChart.appendChild(element);
  return element;
}

function drawChart(rows) {
  feature.moistureChart.replaceChildren();
  const samples = [...rows].sort(
    (a, b) => Date.parse(a.created_at) - Date.parse(b.created_at),
  );
  const percent = samples.some((row) => Number.isFinite(row.moisture_percent));
  const field = percent ? "moisture_percent" : "raw_value";
  const max = percent ? 100 : 1;
  svgElement(
    "text",
    { x: 55, y: 20, fill: "#b8c4c7", "font-size": 14 },
    percent
      ? "Wilgotność względna (%)"
      : "Surowy odczyt ADC (0–1), bez kalibracji",
  );
  for (let i = 0; i <= 4; i++) {
    const y = 35 + i * 45;
    svgElement("line", { x1: 55, y1: y, x2: 875, y2: y, stroke: "#355158" });
    svgElement(
      "text",
      { x: 5, y: y + 5, fill: "#b8c4c7", "font-size": 13 },
      (max * (1 - i / 4)).toLocaleString("pl-PL", {minimumFractionDigits: percent ? 0 : 2, maximumFractionDigits: percent ? 0 : 2}),
    );
  }
  if (!samples.length) {
    svgElement(
      "text",
      { x: 300, y: 120, fill: "#b8c4c7" },
      "Brak pomiarów w tym zakresie.",
    );
    return;
  }
  const first = Date.parse(samples[0].created_at);
  const last = Date.parse(samples.at(-1).created_at);
  let segment = [];
  let previousTime = null;
  const flush = () => {
    if (segment.length === 1)
      svgElement("circle", {
        cx: segment[0][0],
        cy: segment[0][1],
        r: 3,
        fill: "#5fe1b0",
      });
    else if (segment.length)
      svgElement("polyline", {
        points: segment.map((p) => p.join(",")).join(" "),
        fill: "none",
        stroke: "#5fe1b0",
        "stroke-width": 2,
      });
    segment = [];
  };
  for (const row of samples) {
    const time = Date.parse(row.created_at);
    if (row.error || !Number.isFinite(row[field]) || !Number.isFinite(time)) {
      flush();
      previousTime = null;
      continue;
    }
    if (
      previousTime !== null &&
      time - previousTime >
        3 * (savedSettings?.sample_interval_seconds || 10) * 1000
    )
      flush();
    segment.push([
      55 + (820 * (time - first)) / Math.max(1, last - first),
      215 - (180 * row[field]) / max,
    ]);
    previousTime = time;
  }
  flush();
  svgElement(
    "text",
    { x: 55, y: 245, fill: "#b8c4c7", "font-size": 12 },
    new Date(first).toLocaleString("pl-PL"),
  );
  svgElement(
    "text",
    { x: 875, y: 245, fill: "#b8c4c7", "font-size": 12, "text-anchor": "end" },
    new Date(last).toLocaleString("pl-PL"),
  );
}

function appendRuns(items) {
  for (const row of items) {
    const tr = document.createElement("tr");
    for (const value of [
      row.id,
      new Date(row.created_at).toLocaleString("pl-PL"),
      historyLabels[row.source] || "nieznane źródło",
      historyLabels[row.status] || "nieznany wynik",
      row.elapsed_seconds == null ? "—" : row.elapsed_seconds.toLocaleString("pl-PL", {minimumFractionDigits: 1, maximumFractionDigits: 1}),
      row.pulses ?? "—",
      row.delivered_ml?.toLocaleString("pl-PL") ?? "—",
      polishMessage(row.error),
    ]) {
      const td = document.createElement("td");
      td.textContent = String(value);
      tr.appendChild(td);
    }
    feature.runsBody.appendChild(tr);
  }
}

function appendEvents(items) {
  for (const row of items) {
    const li = document.createElement("li");
    li.textContent = `${new Date(row.created_at).toLocaleString("pl-PL")} · ${historyLabels[row.kind] || "zdarzenie"}: ${polishMessage(row.message)}`;
    feature.eventsList.appendChild(li);
  }
}

async function refreshHistory() {
  const version = ++historyVersion;
  browsingOlder = false;
  try {
    const query = formValues(feature.historyForm);
    const [samples, runs, events] = await Promise.all([
      api(
        `/api/history/readings?channel=${query.channel}&hours=${query.hours}&limit=300`,
      ),
      api(`/api/history/runs?hours=${query.hours}&limit=30`),
      api(`/api/history/events?hours=${query.hours}&limit=20`),
    ]);
    if (version !== historyVersion) return;
    drawChart(samples.items);
    feature.runsBody.replaceChildren();
    appendRuns(runs.items);
    feature.eventsList.replaceChildren();
    appendEvents(events.items);
    runsCursor = runs.next_before;
    eventsCursor = events.next_before;
    feature.olderRuns.disabled = !runsCursor;
    feature.olderEvents.disabled = !eventsCursor;
    feature.historyNote.textContent = `${state.hardware.simulated ? "Historia symulacji. " : ""}Wykres: ${samples.items.length} ostatnich pomiarów z wybranego zakresu${samples.next_before ? " (limit 300)" : ""}. Przerwy oznaczają brak poprawnych danych.`;
  } catch (error) {
    if (version === historyVersion)
      feature.historyNote.textContent = error.message;
  }
}

feature.historyForm.addEventListener("submit", (event) => {
  event.preventDefault();
  refreshHistory();
});
for (const [button, kind, append] of [
  [feature.olderRuns, "runs", appendRuns],
  [feature.olderEvents, "events", appendEvents],
]) {
  button.addEventListener("click", async () => {
    const before = kind === "runs" ? runsCursor : eventsCursor;
    if (!before) return;
    const version = historyVersion;
    browsingOlder = true;
    button.disabled = true;
    try {
      const page = await api(
        `/api/history/${kind}?hours=${feature.historyForm.elements.hours.value}&before=${before}&limit=30`,
      );
      if (version !== historyVersion) return;
      append(page.items);
      if (kind === "runs") runsCursor = page.next_before;
      else eventsCursor = page.next_before;
    } catch (error) {
      feature.historyNote.textContent = error.message;
    } finally {
      button.disabled = !(kind === "runs" ? runsCursor : eventsCursor);
    }
  });
}

const reasons = {
  disabled: "wyłączona",
  waiting_for_valid_samples: "oczekiwanie na poprawne pomiary",
  collecting_samples: "zbieranie próbek",
  collecting_after_soak: "zbieranie nowych próbek po przerwie",
  watering: "podlewanie",
  soaking: "przerwa na wsiąknięcie",
  daily_limit: "wyczerpany dzienny budżet",
  moisture_sufficient: "wilgotność wystarczająca",
  manual_session: "sterowanie ręczne",
  hardware_or_storage_error: "błąd sprzętu lub zapisu",
  storage_error: "błąd zapisu",
};
async function updateFeatures() {
  const data = await api("/api/status");
  const auto = data.automation;
  feature.automationStatus.textContent = `${data.hardware.simulated ? "SYMULACJA · " : ""}${reasons[auto.reason] || polishMessage(auto.reason)} · budżet ${auto.daily_used_seconds}/${auto.daily_limit_seconds} s · przerwa ${auto.soak_remaining_seconds} s${auto.sampling_active ? "" : " · zbieranie pomiarów nie działa"}`;
  feature.flowStatus.textContent = !data.flow.configured
    ? "Ustaw FLOW_PIN w konfiguracji urządzenia, aby podłączyć przepływomierz."
    : data.flow.calibrated
      ? `Kalibracja: ${data.flow.pulses_per_liter.toLocaleString("pl-PL", {minimumFractionDigits: 2, maximumFractionDigits: 2})} impulsów/l.`
      : "Wejście impulsowe aktywne. Przed odmierzaniem w ml wykonaj kalibrację.";
  const run = data.operation;
  feature.volumeProgress.textContent =
    run.active && run.pulses !== null
      ? `${run.pulses} impulsów · ${run.delivered_ml?.toLocaleString("pl-PL") ?? "brak kalibracji"} ml${run.target_ml ? ` / ${run.target_ml.toLocaleString("pl-PL")} ml` : ""}`
      : "";
  const moisture = await api("/api/moisture");
  feature.sampleTime.textContent = moisture.sampled_at
    ? `Ostatni zapisany pomiar: ${new Date(moisture.sampled_at).toLocaleString("pl-PL")}`
    : "Brak zapisanych pomiarów.";
}

async function featurePoll() {
  try {
    if (!savedSettings) {
      fillSettings(await api("/api/settings"));
      feature.historyForm.elements.channel.value = savedSettings.channel;
      await refreshHistory();
    }
    await updateFeatures();
    if (++featurePollCount % 6 === 0 && !browsingOlder) await refreshHistory();
  } catch (error) {
    feature.automationStatus.textContent = error.message;
  }
  setTimeout(featurePoll, 5000);
}
featurePoll();
