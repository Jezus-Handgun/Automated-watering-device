const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8");
const idle = () => ({
  hardware: { ready: true, simulated: true, pump_on: false, valve_open: false, error: null },
  operation: { active: false, mode: "idle", remaining_seconds: 0, last_result: null },
});
const tick = () => new Promise((resolve) => setImmediate(resolve));

async function setup() {
  const makeElement = () => ({ textContent: "", disabled: false, handlers: {},
    classList: { toggle() {} }, addEventListener(name, handler) { this.handlers[name] = handler; } });
  const elements = Object.fromEntries(["healthPill", "moistureReadings", "refreshBtn", "waterNote", "hardwareState", "pumpToggle", "valveToggle", "stopBtn"].map((id) => [id, makeElement()]));
  const buttons = [5, 15, 30].map((seconds) => ({ ...makeElement(), dataset: { seconds: String(seconds) } }));
  const calls = [];
  let status = idle();
  let override = null;
  const context = vm.createContext({
    AbortController,
    setTimeout: () => 1,
    clearTimeout: () => {},
    document: { getElementById: (id) => elements[id], querySelectorAll: () => buttons },
    fetch: async (url, options) => {
      calls.push({ url, options });
      if (override) {
        const response = override(url, options);
        if (response) return response;
      }
      const data = url === "/api/status" ? status : url === "/api/moisture"
        ? { simulated: true, channels: [0], readings: [null] } : { status: "ok" };
      return { ok: true, json: async () => data };
    },
  });
  vm.runInContext(source, context);
  await tick();
  return { elements, buttons, calls, context,
    setStatus: (value) => { status = value; },
    intercept: (fn) => { override = fn; },
    run: (code) => vm.runInContext(code, context) };
}

test("same-origin API, simulation label and manual interlocks", async () => {
  const app = await setup();
  assert(app.calls.every(({ url }) => url.startsWith("/api/")));
  assert.match(app.elements.hardwareState.textContent, /SYMULACJA/);
  assert.equal(app.elements.pumpToggle.disabled, true);
  assert.equal(app.elements.valveToggle.disabled, false);
  assert.equal(app.buttons[0].disabled, false);
  assert.equal(app.elements.stopBtn.disabled, false);
});

test("active operation displays progress and locks controls", async () => {
  const app = await setup();
  const status = idle();
  status.hardware.pump_on = status.hardware.valve_open = true;
  status.operation = { active: true, mode: "watering", remaining_seconds: 12 };
  app.setStatus(status);
  await app.run("refreshStatus()");
  assert.match(app.elements.waterNote.textContent, /pozostało 12 s/);
  assert(app.buttons.every((button) => button.disabled));
  assert.equal(app.elements.pumpToggle.disabled, true);
  assert.equal(app.elements.valveToggle.disabled, true);
  assert.equal(app.elements.stopBtn.disabled, false);
});

test("lost connection disables starts and keeps stop available", async () => {
  const app = await setup();
  app.intercept((url) => url === "/api/status" ? Promise.reject(new Error("offline")) : null);
  await app.run("refreshStatus()");
  assert.match(app.elements.healthPill.textContent, /brak połączenia/);
  assert(app.buttons.every((button) => button.disabled));
  assert.equal(app.elements.stopBtn.disabled, false);
  assert.match(app.elements.waterNote.textContent, /nieznany/);
});

test("duplicate clicks blocked, stop can interrupt a pending request", async () => {
  const app = await setup();
  let finishStart;
  app.intercept((url) => url === "/api/water" ? new Promise((resolve) => { finishStart = resolve; }) : null);
  const start = app.buttons[0].handlers.click();
  await app.buttons[1].handlers.click();
  assert.equal(app.calls.filter(({ url }) => url === "/api/water").length, 1);
  await app.elements.stopBtn.handlers.click();
  assert.equal(app.calls.filter(({ url }) => url === "/api/stop").length, 1);
  finishStart({ ok: true, json: async () => ({ status: "accepted" }) });
  await start;
  assert.equal(app.run("state.busy"), false);
});

test("a status response from before a command cannot overwrite newer state", async () => {
  const app = await setup();
  let finishOld;
  let interceptOnce = true;
  app.intercept((url) => {
    if (url === "/api/status" && interceptOnce) {
      interceptOnce = false;
      return new Promise((resolve) => { finishOld = resolve; });
    }
    return null;
  });
  const old = app.run("refreshStatus()");
  const status = idle();
  status.operation = { active: true, mode: "watering", remaining_seconds: 5 };
  status.hardware.pump_on = status.hardware.valve_open = true;
  app.setStatus(status);
  await app.buttons[0].handlers.click();
  finishOld({ ok: true, json: async () => idle() });
  await old;
  assert.match(app.elements.waterNote.textContent, /pozostało 5 s/);
  assert(app.buttons.every((button) => button.disabled));
});

test("sensor labels use actual configured channels", async () => {
  const app = await setup();
  app.intercept((url) => url === "/api/moisture" ? Promise.resolve({ ok: true,
    json: async () => ({ simulated: false, channels: [2, 5], readings: [0.25, null] }) }) : null);
  await app.run("refreshMoisture()");
  assert.equal(app.elements.moistureReadings.textContent, "Kanał 2: 0,250 | Kanał 5: brak danych");
});
