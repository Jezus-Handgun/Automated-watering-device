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
      (max * (1 - i / 4)).toFixed(percent ? 0 : 2),
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
    new Date(first).toLocaleString(),
  );
  svgElement(
    "text",
    { x: 875, y: 245, fill: "#b8c4c7", "font-size": 12, "text-anchor": "end" },
    new Date(last).toLocaleString(),
  );
}

function appendRuns(items) {
  for (const row of items) {
    const tr = document.createElement("tr");
    for (const value of [
      row.id,
      new Date(row.created_at).toLocaleString(),
      row.source,
      row.status,
      row.elapsed_seconds == null ? "—" : row.elapsed_seconds.toFixed(1),
      row.pulses ?? "—",
      row.delivered_ml ?? "—",
      row.error || "—",
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
    li.textContent = `${new Date(row.created_at).toLocaleString()} · ${row.kind}: ${row.message}`;
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
  feature.automationStatus.textContent = `${data.hardware.simulated ? "SYMULACJA · " : ""}${reasons[auto.reason] || auto.reason} · budżet ${auto.daily_used_seconds}/${auto.daily_limit_seconds} s · przerwa ${auto.soak_remaining_seconds} s${auto.sampling_active ? "" : " · zbieranie pomiarów nie działa"}`;
  feature.flowStatus.textContent = !data.flow.configured
    ? "Ustaw FLOW_PIN w konfiguracji urządzenia, aby podłączyć przepływomierz."
    : data.flow.calibrated
      ? `Kalibracja: ${data.flow.pulses_per_liter.toFixed(2)} impulsów/l.`
      : "Wejście impulsowe aktywne. Przed odmierzaniem w ml wykonaj kalibrację.";
  const run = data.operation;
  feature.volumeProgress.textContent =
    run.active && run.pulses !== null
      ? `${run.pulses} impulsów · ${run.delivered_ml ?? "brak kalibracji"} ml${run.target_ml ? ` / ${run.target_ml} ml` : ""}`
      : "";
  const moisture = await api("/api/moisture");
  feature.sampleTime.textContent = moisture.sampled_at
    ? `Ostatni zapisany pomiar: ${new Date(moisture.sampled_at).toLocaleString()}`
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
