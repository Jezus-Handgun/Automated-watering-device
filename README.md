# Automated watering device

Raspberry Pi watering controller with a Flask web panel, automatic soil-based
watering, configurable Hall flow-meter input, and SQLite history.

The agreed changes and their implementation status are recorded in
[PLAN_ZMIAN.md](PLAN_ZMIAN.md). Features 1–8 are implemented; physical calibration
and validation must use the actual sensor, pump and flow meter.

## Run locally

Requirements: Python 3.12+ and uv.

```bash
uv venv
uv pip install -r backend/requirements.txt
HARDWARE_MODE=simulation uv run --no-sync python backend/run.py
```

Windows PowerShell:

```powershell
$env:HARDWARE_MODE = "simulation"
uv run --no-sync python backend/run.py
```

Open **http://localhost:5000/**, or `http://<server-ip>:5000/` on another device.
The panel and API share one address. SQLite is created/migrated automatically.
The sampling worker starts with the process and keeps recording measurements
with no browser open. Stop with `Ctrl+C`.

For a configured Raspberry Pi, use `HARDWARE_MODE=real` (the default), enable SPI
and provide GPIO permissions. Missing GPIO is an error, never a silent switch to
simulation. Simulation does not fabricate sensor measurements or flow pulses;
it records explicitly marked missing samples until a test injects readings.

Use **one process** per device. The runner disables Flask's debugger/reloader and
handles SIGINT/SIGTERM. A deployment that imports `create_app()` directly must
call `start_services(app)` once to start sampling, and `close_app(app)` on exit.
The Flask server remains a development server. Authentication and production
server setup are separate planned tasks.

## Automatic watering

Automation starts **disabled**. Configure it in the panel and save settings:

1. Select the connected moisture channel.
2. Record raw dry and wet reference readings for your sensor and substrate. Use
   the capture buttons or enter readings in the 0–1 ADC range. Both polarities
   are supported; references must differ by at least 0.01. Changing the channel
   requires new calibration.
3. Set the start and stop thresholds (defaults 30% and 50%). These are relative
   calibrated values, not a measurement of volumetric water content.
4. Set the median-filter window (default 3 samples), measurement interval
   (10 seconds), portion (5 seconds) and soak period (300 seconds).
5. Choose a daily time budget, then explicitly enable automation and save.

At or below the lower threshold, the controller starts a series of small
portions. Between portions it waits for absorption and collects a **new complete
filter window**. The series continues until reaching the upper threshold.
Missing/non-finite readings and ADC saturation block automatic starts. An invalid
selected sensor reading during an automatic cycle stops that cycle. Manual
sessions take precedence while active.

The daily budget uses UTC calendar days and survives restarts. Before each cycle,
the database reserves its **full requested time limit**, including manual,
failed and cancelled cycles. Automation cannot reserve beyond the budget. This
conservative accounting avoids exceeding the automatic allowance after a crash;
it is not the elapsed pump-time metric. Explicit manual commands can exceed this
automatic budget. History separately stores actual session duration.

**Stop all disables automation persistently**, cancels the current session and
attempts to switch off both outputs independently. Normal process shutdown keeps
the saved automation preference. On restart it waits out the soak period and
collects fresh readings. Unfinished recorded sessions become `interrupted`, keep
their budget reservations and never resume mid-cycle.

## Flow meter and volume control

The exact meter model is not assumed. Set its free BCM GPIO with `FLOW_PIN`.
`FLOW_PULL_UP=1` counts activations on falling edges; `0` uses a pull-down and
counts rising edges. There is no software debounce to discard legitimate Hall
pulses. Select electrical interfacing and signal levels for the actual device;
do not connect an unverified 5 V signal directly to GPIO.

Calibration options in the panel:

- Enter the verified **pulses per liter** coefficient; or
- Run a short timed cycle, collect the output in a measuring container, then
  select the completed history run ID and enter the measured milliliters.
  The coefficient is `recorded pulses × 1000 / measured ml`.

Before calibration, timed cycles still count pulses, but their volume is unknown
(`null`, not zero). Volume-controlled cycles require both configured GPIO and a
calibration coefficient. Set the desired milliliters **and** a maximum duration.
The pump stops when pulse count reaches the target; timeout before the target is
an error. Volume resolution is one pulse; the 50 ms monitoring interval and
physical shutdown latency can cause overshoot. Calibrate under real operating
conditions and choose a meter suited to the actual low flow rate.

When a flow input is configured, all pump modes monitor pulses. No pulse for the
configured interval (default 5 seconds) stops the pump and valve with an error.
A timed cycle ending without any pulse also fails, even if shorter than that
interval. A valve-only manual session does not require flow. Flow/control faults
block new starts until the cause is resolved and the process restarted.

Settings and calibration are stored separately for `real` and `simulation` modes.
No physical pulses or moisture samples are generated by simulation itself.

## Manual operation

Only **zone 0** is supported. A cycle lasts 1–600 seconds. HTTP start returns
**202 Accepted**, not a completion confirmation; inspect `/api/status`.
Conflicting commands return 409. Open the valve before manually starting the
pump. Stopping the pump also closes the valve. Manual output control expires after
`MANUAL_TIMEOUT_SECONDS` (default 60), counted from opening the valve; repeated ON
commands do not extend the deadline.

Safety cleanup cannot handle SIGKILL, power loss, a hung process or a physical
relay failure. GPIO/ADC diagnostics verify software access, not actual water flow.

## History and database

`DATABASE_PATH` selects the SQLite file. Migrations run transactionally at startup
and `init-db` is now **non-destructive**:

```bash
uv run --no-sync flask --app backend/run.py init-db
```

The previous `moisture_readings` and `water_events` tables are kept intact and
imported once into the new history tables. Old cycles are marked `legacy` because
their actual outcome/volume was not recorded. New history includes raw and
calibrated moisture, invalid samples, cycle source/status, requested timeout,
elapsed session time, pulse count, delivered volume, and error events.

The panel shows a moisture chart with gaps for missing/invalid measurements,
cycles and errors. The chart shows at most the **latest 300 samples** in the chosen
24-hour/7-day/30-day range. Older run/event pages are available with buttons; the
API also paginates older readings. Displayed dates use the browser's timezone;
storage and daily budgets use UTC. The history view separates simulation and real
records. Records are not automatically deleted; plan storage/backup for long runs.

Database errors prevent a new cycle from starting without its history/budget
reservation. A write failure during a cycle causes a stop when detected. If its
final result cannot be saved, startup recovery marks it interrupted.

## Configuration

| Environment variable     | Default                | Purpose                                                           |
| ------------------------ | ---------------------- | ----------------------------------------------------------------- |
| `HARDWARE_MODE`          | `real`                 | `real` or `simulation`                                            |
| `PUMP_PIN`               | `17`                   | Pump BCM pin                                                      |
| `VALVE_PIN`              | `27`                   | Valve BCM pin                                                     |
| `MOISTURE_CHANNELS`      | `0,1,2`                | Unique MCP3008 channels 0–7; use `0` for one sensor               |
| `MANUAL_TIMEOUT_SECONDS` | `60`                   | Manual session timeout, 1–600 seconds                             |
| `FLOW_PIN`               | unset                  | Optional pulse-input BCM pin                                      |
| `FLOW_PULL_UP`           | `1`                    | `1`: pull-up/falling activation, `0`: pull-down/rising activation |
| `DATABASE_PATH`          | `instance/watering.db` | SQLite path (relative paths use Flask's instance directory)       |

Pins must be unique, in 0–27, and avoid SPI pins 7–11 when ADC channels are enabled.
Pump/valve outputs currently use `active_high=True`; configurable relay polarity
is a separate planned improvement. Automation settings, thresholds, time limits
and calibration are saved through the panel/API in SQLite, not environment vars.

## API

| Method    | Endpoint                | Purpose / body                                              |
| --------- | ----------------------- | ----------------------------------------------------------- |
| GET       | `/api/health`           | Process liveness                                            |
| GET       | `/api/status`           | Hardware, active cycle/volume, automation reason and budget |
| GET       | `/api/moisture`         | Raw readings, last filtered samples and timestamp           |
| GET       | `/api/hardware/probe`   | Inspect existing GPIO/ADC objects                           |
| POST      | `/api/water`            | `{"seconds":5,"zone":0}` or `{"seconds":30,"volume_ml":50}` |
| POST      | `/api/pump`             | `{"on":true}` or `{"on":false}`                             |
| POST      | `/api/valve`            | `{"open":true}` or `{"open":false}`                         |
| POST      | `/api/stop`             | Disable automation and stop both outputs                    |
| GET / PUT | `/api/settings`         | Read settings / update selected fields                      |
| POST      | `/api/flow/calibrate`   | `{"run_id":12,"measured_ml":100}`                           |
| GET       | `/api/history/readings` | Raw/filtered samples and errors                             |
| GET       | `/api/history/runs`     | Cycle history                                               |
| GET       | `/api/history/events`   | Error/recovery events                                       |

History query parameters: `limit` (1–1000, default 100), `before` (exclusive ID
cursor), `hours` (1–8760, default 24), `channel` (0–7, readings only). Responses
contain `items` and `next_before`. JSON types are strict; non-finite numbers,
fractional timeouts, unknown settings and invalid calibration are rejected.

`/api/health` checks process liveness only. The API currently has no authentication.
Swagger is not initialized; `/apidocs/` and `/apispec_1.json` remain unavailable.

## Docker

```bash
docker build -t watering .
docker run --rm -p 8080:5000 -e HARDWARE_MODE=simulation -v watering-data:/data watering
```

Or `HARDWARE_MODE=simulation docker compose up --build` (in PowerShell set
`$env:HARDWARE_MODE = "simulation"` before `docker compose up --build`).
Open **http://localhost:8080/**. Compose stores the database under
`backend/instance/`; stop with `docker compose down`.

The supplied profile does not grant GPIO/SPI access. Real Raspberry Pi hardware
requires a suitable driver and device permissions. The current host has a broken
`docker0` bridge: tests built with `--network=host` and used isolated containers
with `--network=none`. Fixing the host bridge is outside the application changes.

## Tests

```bash
uv pip install -r backend/requirements.txt -r backend/requirements-dev.txt
uv run --no-sync pytest
node frontend/tests/app.test.cjs
node frontend/tests/features.test.cjs
```

Python tests use simulation/mock pins. Frontend tests need Node.js, but the app
does not. Tests cover conflicts, faults, cancellation, calibration, pulse edges,
volume/no-flow stops, filtering/hysteresis, daily budgets, background sampling,
persistent settings, migrations, recovery and history pagination.

Hardware checks are opt-in and require the application to be stopped:

```bash
HARDWARE_MODE=real RUN_HARDWARE_TESTS=1 uv run --no-sync pytest backend/tests/test_hardware_connection.py -s
```

These initialize GPIO/ADC; they are not a physical flow test. Run them only when
the connected equipment is ready for such checks.
