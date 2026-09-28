const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../features.js"), "utf8");

function element(tag = "div") {
  return { tag, textContent: "", value: "", checked: false, disabled: false,
    children: [], handlers: {}, attributes: {},
    addEventListener(name, fn) { this.handlers[name] = fn; },
    appendChild(child) { this.children.push(child); },
    replaceChildren(...children) { this.children = children; },
    setAttribute(name, value) { this.attributes[name] = value; },
  };
}
const defaults = { enabled: false, channel: 0, dry_raw: null, wet_raw: null,
  start_percent: 30, stop_percent: 50, sample_interval_seconds: 10, filter_samples: 3,
  portion_seconds: 5, soak_seconds: 300, daily_limit_seconds: 120, portion_mode: "time",
  portion_ml: 50, flow_pulses_per_liter: null, no_flow_timeout_seconds: 5 };
async function setup() {
  const elements = new Map();
  const get = (id) => { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); };
  function form(id, fields) {
    const form = get(id);
    const controls = fields.map((name) => {
      const input = element("input"); input.name = name;
      input.type = name === "enabled" ? "checkbox" : name === "portion_mode" ? "select-one" : "number";
      return input;
    });
    for (const input of controls) controls[input.name] = input;
    form.elements = controls;
    const submit = element("button"); form.querySelector = () => submit;
  }
  form("automationForm", Object.keys(defaults).filter((key) => !["flow_pulses_per_liter", "no_flow_timeout_seconds"].includes(key)));
  form("flowForm", ["flow_pulses_per_liter", "no_flow_timeout_seconds"]);
  form("flowCalibrationForm", ["run_id", "measured_ml"]);
  form("pumpCalibrationForm", ["run_id", "measured_ml"]);
  form("volumeForm", ["seconds", "volume_ml"]);
  form("historyForm", ["channel", "hours"]);
  get("historyForm").elements.hours.value = "24";
  const calls = [], commands = [];
  let settings = { ...defaults };
  let override;
  const context = vm.createContext({
    document: { getElementById: get, createElement: element, createElementNS: (_, tag) => element(tag) },
    state: { hardware: { simulated: true } }, setTimeout: () => 1,
    refreshStatus: async () => {}, command: (...args) => commands.push(args),
    api: async (path, options) => {
      calls.push({ path, options });
      if (override) { const value = override(path, options); if (value) return value; }
      if (path === "/api/settings") {
        if (options) settings = { ...settings, ...JSON.parse(options.body) };
        return { ...settings };
      }
      if (path.startsWith("/api/history/")) return { items: [], next_before: null };
      if (path === "/api/status") return { hardware: { simulated: true }, operation: { active: false },
        automation: { reason: "disabled", daily_used_seconds: 0, daily_limit_seconds: 120, soak_remaining_seconds: 0, sampling_active: true },
        flow: { configured: false, calibrated: false } };
      if (path === "/api/moisture") return { simulated: false, channels: [0], readings: [0.7], sampled_at: null };
    },
  });
  vm.runInContext(source, context);
  await new Promise((resolve) => setImmediate(resolve));
  return { get, calls, commands, run: (code) => vm.runInContext(code, context), intercept: (fn) => { override = fn; } };
}

test("loads settings without inventing calibration and draws empty history", async () => {
  const app = await setup();
  assert.equal(app.get("automationForm").elements.dry_raw.value, "");
  assert.equal(app.get("automationForm").elements.enabled.checked, false);
  assert.match(app.get("flowStatus").textContent, /FLOW_PIN/);
  assert(app.get("moistureChart").children.some((child) => child.textContent.includes("Brak pomiarów")));
});

test("settings form sends numeric references, boolean enable and null empty values", async () => {
  const app = await setup();
  const form = app.get("automationForm");
  form.elements.dry_raw.value = "0.9";
  form.elements.wet_raw.value = "0.1";
  form.elements.enabled.checked = true;
  await app.run("saveForm(feature.automationForm, feature.settingsNote)");
  const sent = JSON.parse(app.calls.find((call) => call.options?.method === "PUT").options.body);
  assert.equal(sent.dry_raw, 0.9);
  assert.equal(sent.enabled, true);
  assert.match(app.get("settingsNote").textContent, /Zapisano/);
});

test("stop clears the automation checkbox", async () => {
  const app = await setup();
  app.get("automationForm").elements.enabled.checked = true;
  app.get("stopBtn").handlers.click();
  assert.equal(app.get("automationForm").elements.enabled.checked, false);
});

test("volume form respects disabled controls and sends a bounded time", async () => {
  const app = await setup();
  const form = app.get("volumeForm");
  form.elements.seconds.value = "30"; form.elements.volume_ml.value = "50";
  app.get("volumeBtn").disabled = true;
  form.handlers.submit({ preventDefault() {} });
  assert.equal(app.commands.length, 0);
  app.get("volumeBtn").disabled = false;
  form.handlers.submit({ preventDefault() {} });
  assert.equal(app.commands[0][0], "/api/water");
  assert.equal(app.commands[0][1].seconds, 30);
  assert.equal(app.commands[0][1].volume_ml, 50);
});

test("chart does not bridge invalid readings", async () => {
  const app = await setup();
  app.run(`drawChart([
    {created_at:'2026-09-22T10:00:00Z', moisture_percent:20, error:null},
    {created_at:'2026-09-22T10:00:10Z', moisture_percent:null, error:'invalid'},
    {created_at:'2026-09-22T10:00:20Z', moisture_percent:40, error:null}
  ])`);
  const shapes = app.get("moistureChart").children;
  assert.equal(shapes.filter((child) => child.tag === "polyline").length, 0);
  assert.equal(shapes.filter((child) => child.tag === "circle").length, 2);
});

test("server validation errors are displayed without reporting success", async () => {
  const app = await setup();
  app.intercept((_, options) => options?.method === "PUT" ? Promise.reject(new Error("Calibrate first")) : null);
  await app.run("saveForm(feature.automationForm, feature.settingsNote)");
  assert.equal(app.get("settingsNote").textContent, "Calibrate first");
});


test("history translates stored English statuses and messages without changing records", async () => {
  const app = await setup();
  app.run(`appendRuns([{id:1, created_at:'2026-09-23T10:00:00Z', source:'manual', status:'failed', elapsed_seconds:1.5, pulses:0, delivered_ml:null, error:'No flow detected while the pump is running.'}])`);
  const cells = app.get("runsBody").children[0].children;
  assert.equal(cells[2].textContent, "ręczne");
  assert.equal(cells[3].textContent, "błąd");
  assert.equal(cells[4].textContent, "1,5");
  assert.match(cells[9].textContent, /Nie wykryto przepływu/);
  app.run(`appendEvents([{created_at:'2026-09-23T10:00:00Z', kind:'sensor_error', message:'CH0: Missing or invalid sensor reading.'}])`);
  assert.match(app.get("eventsList").children[0].textContent, /błąd czujnika: Kanał 0: Brak odczytu/);
});

test("pump calibration posts numeric run and measured volume", async () => {
  const app = await setup();
  const form = app.get("pumpCalibrationForm");
  form.elements.run_id.value = "7";
  form.elements.measured_ml.value = "20";
  app.intercept((path) => path === "/api/pump/calibrate" ? {...defaults, pump_ml_per_second:2} : null);
  await app.run('saveForm(feature.pumpCalibrationForm, feature.pumpNote, "/api/pump/calibrate", "POST")');
  const request = app.calls.find(call => call.path === "/api/pump/calibrate");
  assert.deepEqual(JSON.parse(request.options.body), {run_id:7, measured_ml:20});
  assert.match(app.get("pumpNote").textContent, /Zapisano/);
});

test("history separates measured and estimated volumes and labels low water", async () => {
  const app = await setup();
  app.run(`appendRuns([{id:1, created_at:'2026-09-28T10:00:00Z', source:'manual', status:'low_water', elapsed_seconds:3, pump_seconds:2, delivered_ml:null, estimated_ml:5, error:null}])`);
  const cells = app.get("runsBody").children[0].children;
  assert.match(cells[3].textContent, /low_water/);
  assert.equal(cells[5].textContent, "2");
  assert.equal(cells[7].textContent, "—");
  assert.equal(cells[8].textContent, "5");
});

test("uncalibrated pump has no invented estimate, volume mode disabled, UTC budget explicit", async () => {
  const app = await setup();
  assert.match(app.get("pumpStatus").textContent, /nieznana/);
  assert.equal(app.get("volumeModeOption").disabled, true);
  assert.match(app.get("automationStatus").textContent, /UTC.*wszystkie tryby/);
});

test("live progress separates estimate and measurement and locks calibration while running", async () => {
  const app = await setup();
  app.intercept(path => path === "/api/status" ? {
    hardware: {simulated:true}, automation: {reason:"watering"},
    flow: {configured:false, calibrated:false}, pump: {ml_per_second:2},
    operation: {active:true, delivered_ml:null, estimated_ml:4, pump_seconds:2, pulses:null}
  } : null);
  await app.run("updateFeatures()");
  assert.match(app.get("volumeProgress").textContent, /Pomiar przepływomierza: brak ml.*Szacunek pompy: 4 ml/);
  assert.match(app.get("pumpStatus").textContent, /nie pomiar/);
  assert.equal(app.get("pumpCalibrationForm").querySelector().disabled, true);
});
