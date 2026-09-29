"""Greenhouse v0.3: temporary databases and mocked GPIO only."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import threading
import time

import pytest
from gpiozero import Device
from gpiozero.pins.mock import MockFactory

from app import create_app, close_app
from app.controller import WateringController, ControlConflict, LowWater
from app.hardware.gpio_controller import HardwareConfig, WateringHardware, build_hardware_config
from app.storage import Store, BudgetExceeded


def wait_for(predicate, timeout=1):
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        time.sleep(0.005)
    assert predicate()


@pytest.fixture
def control(tmp_path, monkeypatch):
    monkeypatch.setattr(Device, 'pin_factory', MockFactory())
    hw = WateringHardware(HardwareConfig(moisture_channels=[], valve_enabled=False, water_level_pin=24))
    assert hw.ready
    hw.water_level_input.pin.drive_low()
    controller = WateringController(hw, store=Store(str(tmp_path / 'greenhouse.db')))
    yield controller
    controller.close()


@pytest.mark.parametrize('active_high', [False, True])
def test_pump_only_never_allocates_or_switches_valve(monkeypatch, active_high):
    factory = MockFactory()
    monkeypatch.setattr(Device, 'pin_factory', factory)
    hw = WateringHardware(HardwareConfig(moisture_channels=[], valve_enabled=False,
                                        valve_pin=17, pump_active_high=active_high))
    controller = WateringController(hw)
    try:
        assert hw.ready and hw.valve is None
        assert len(hw.probe()['components']) == 1
        assert hw.pump.pin.state == (not active_high)
        controller.set_manual('pump', True)
        assert hw.pump.pin.state == active_high
        assert hw.status()['valve_open'] is None
        with pytest.raises(ControlConflict):
            controller.set_manual('valve', False)
        assert hw.status()['pump_on']
        controller.set_manual('pump', False)
        assert hw.pump.pin.state == (not active_high)
        controller.start(1)
        assert hw.status()['pump_on']
        controller.stop()
        assert hw.pump.pin.state == (not active_high)
    finally:
        controller.close()


@pytest.mark.parametrize('patch', [
    {'WATER_LEVEL_PIN': '17'}, {'WATER_LEVEL_PIN': '27'},
    {'WATER_LEVEL_PIN': '8'}, {'WATER_LEVEL_PIN': '28'},
    {'WATER_LEVEL_PIN': True}, {'WATER_LEVEL_PIN': '22', 'FLOW_PIN': '22'},
    {'VALVE_ENABLED': 0}, {'VALVE_ENABLED': 'false'},
])
def test_invalid_new_configuration(patch):
    with pytest.raises(ValueError):
        build_hardware_config(patch)


def test_disabled_valve_does_not_reserve_its_pin():
    config = build_hardware_config({'VALVE_ENABLED': '0', 'WATER_LEVEL_PIN': '27'})
    assert config.water_level_pin == config.valve_pin


@pytest.mark.parametrize('manual', [False, True])
@pytest.mark.parametrize('unknown', [False, True])
def test_missing_or_unknown_water_blocks_start(control, manual, unknown):
    sensor = control.hardware.water_level_input
    if unknown:
        sensor.close()
    else:
        sensor.pin.drive_high()  # open contact or broken wire
    with pytest.raises(LowWater):
        control.set_manual('pump', True) if manual else control.start(1)
    assert not control.hardware.status()['pump_on']
    assert control.store.daily_used(False) == 0
    assert control.store.history('events', False)['items'][0]['kind'] == 'low_water'
    assert control._error is None


def test_simulation_does_not_invent_water():
    hw = WateringHardware(HardwareConfig(mode='simulation', valve_enabled=False, water_level_pin=24))
    controller = WateringController(hw)
    try:
        assert hw.water_level() == {'configured': True, 'water_present': None, 'state': 'unknown'}
        with pytest.raises(LowWater):
            controller.start(1)
        assert hw.water_level_input is None
    finally:
        controller.close()


@pytest.mark.parametrize('manual', [False, True])
def test_water_loss_stops_run_and_can_recover(control, manual):
    if manual:
        control.set_manual('pump', True)
    else:
        control.start(30)
    run_id = control._session['run_id']
    control.hardware.water_level_input.pin.drive_high()
    wait_for(lambda: not control.hardware.status()['pump_on'])
    with control._lock:
        pass
    wait_for(lambda: control._session is None)
    with control._lock:
        assert control.store.run(run_id)['status'] == 'low_water'
    assert any(e['kind'] == 'low_water' for e in control.store.history('events', False)['items'])
    assert control._error is None
    control.hardware.water_level_input.pin.drive_low()
    control.start(1)
    assert control.hardware.status()['pump_on']


def test_water_is_rechecked_after_database_reservation(control, monkeypatch):
    original = control.store.begin_run
    def reserve(*args):
        run_id = original(*args)
        control.hardware.water_level_input.pin.drive_high()
        return run_id
    monkeypatch.setattr(control.store, 'begin_run', reserve)
    with pytest.raises(LowWater):
        control.start(5)
    assert not control.hardware.status()['pump_on']
    run = control.store.history('runs', False)['items'][0]
    assert run['status'] == 'low_water' and run['pump_seconds'] == 0
    assert control.store.daily_used(False) == 5


def test_low_water_and_frozen_metrics_during_sqlite_lock(control, monkeypatch):
    control.hardware.config.flow_pin = 22  # explicit test injection of pulses
    control.update_settings({'flow_pulses_per_liter': 1000})
    control.update_settings({'pump_ml_per_second': 2}, pump_calibration=True)
    control.start(30)
    session = control._session
    control.hardware._record_pulse()
    entered = threading.Event()
    original = control.store.samples
    def blocked(readings, simulated, created_at):
        entered.set()
        # No ADC is allocated by this fixture; inject one explicit test sample
        # so SQLite actually attempts a write rather than an empty executemany.
        return original([{"channel": 0, "raw_value": None, "moisture_percent": None,
                          "error": "test"}], simulated, created_at)
    monkeypatch.setattr(control.store, 'samples', blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with control.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            sampling = pool.submit(control.sample_once)
            assert entered.wait(1)
            control.hardware.water_level_input.pin.drive_high()
            wait_for(lambda: not control.hardware.status()['pump_on'], timeout=0.6)
            assert not sampling.done()
            first = control._operation_status()
            assert first['pulses'] == 1 and first['delivered_ml'] == 1
            assert first['estimated_ml'] == round(first['pump_seconds'] * 2, 3)
            for _ in range(5):
                control.hardware._record_pulse()
            time.sleep(0.08)
            after = control._operation_status()
            for key in ('pump_seconds', 'estimated_ml', 'pulses', 'delivered_ml'):
                assert first[key] == after[key]
        sampling.result(timeout=3)
    wait_for(lambda: control._session is None)
    with control._lock:
        row = control.store.run(session['run_id'])
    assert row['status'] == 'low_water'
    for key in ('pump_seconds', 'estimated_ml', 'pulses', 'delivered_ml'):
        assert row[key] == first[key]
    assert row['pump_ml_per_second'] == 2


@pytest.mark.parametrize('action', ['timed', 'manual', 'automatic'])
def test_budget_denial_is_not_a_hardware_fault(control, action):
    control.update_settings({'daily_limit_seconds': 2})
    control.start(2)
    control.stop()
    with pytest.raises(BudgetExceeded):
        if action == 'manual':
            control.set_manual('pump', True)
        else:
            control.start(1, source='automatic' if action == 'automatic' else 'manual')
    assert control._error is None
    assert control.hardware.ready
    assert not control.hardware.status()['pump_on']
    assert control.store.daily_used(False) == 2
    assert len(control.store.history('runs', False)['items']) == 1


def test_manual_reservation_once_and_survives_restart(control):
    control.set_manual('pump', True)
    control.set_manual('pump', True)
    assert control.store.daily_used(False) == 60
    control.stop()
    config = control.hardware.config
    control.close()
    replacement_hw = WateringHardware(config)
    replacement_hw.water_level_input.pin.drive_low()
    replacement = WateringController(replacement_hw, store=control.store)
    try:
        assert replacement.store.daily_used(False) == 60
        assert replacement.status()['operation']['active'] is False
    finally:
        replacement.close()


def completed_run(control):
    run_id = control.start(1)['run_id']
    wait_for(lambda: control._session is None, timeout=2)
    with control._lock:
        return control.store.run(run_id)


def test_pump_calibration_and_estimate_only_for_future_runs(control):
    before = completed_run(control)
    assert before['estimated_ml'] is None and before['delivered_ml'] is None
    assert control.settings.pump_ml_per_second is None
    result = control.calibrate_pump(before['id'], 5)
    assert result['pump_ml_per_second'] == pytest.approx(5 / before['pump_seconds'])
    assert control.store.run(before['id']) == before  # no invented historical values
    control.start(1)
    time.sleep(0.03)
    control.stop()
    run = control.store.history('runs', False)['items'][0]
    assert run['estimated_ml'] == round(run['pump_seconds'] * result['pump_ml_per_second'], 3)
    assert run['delivered_ml'] is None
    assert run['pump_seconds'] <= run['elapsed_seconds']
    assert control.store.settings('real')['pump_ml_per_second'] == result['pump_ml_per_second']
    assert control.store.settings('simulation') == {}
    with pytest.raises(ControlConflict):
        control.start(1, target_ml=5)


@pytest.mark.parametrize('patch', [
    {'status': 'cancelled'}, {'status': 'failed'}, {'status': 'running'},
    {'status': 'interrupted'}, {'status': 'low_water'}, {'mode': 'manual'},
    {'mode': 'volume'}, {'target_ml': 5}, {'simulated': 1}, {'pump_seconds': None},
    {'pump_seconds': 0}, {'pump_seconds': -1}, {'error': 'GPIO failure'},
])
def test_invalid_calibration_run_rejected(control, patch):
    # Prepare persisted inputs directly; no fake hardware measurements are used by production.
    run_id = control.store.begin_run('manual', 'watering', 2, None, False)
    control.store.finish_run(run_id, 'completed', None, 2, None, None, pump_seconds=2)
    with control.store.connection() as db:
        for key, value in patch.items():
            db.execute(f'UPDATE watering_runs SET {key}=? WHERE id=?', (value, run_id))
    with pytest.raises(ValueError):
        control.calibrate_pump(run_id, 5)
    assert control.settings.pump_ml_per_second is None


@pytest.mark.parametrize('run_id,ml', [(True, 5), (1.5, 5), (0, 5), (999, 5),
                                      (1, True), (1, 0), (1, '5'), (1, float('inf')), (1, float('nan'))])
def test_pump_calibration_input_validation(control, run_id, ml):
    with pytest.raises(ValueError):
        control.calibrate_pump(run_id, ml)


def test_pump_calibration_cannot_change_during_run(control):
    run_id = control.start(1)['run_id']
    with pytest.raises(ControlConflict):
        control.calibrate_pump(run_id, 5)
    with pytest.raises(ValueError):
        control.update_settings({'pump_ml_per_second': 5})


def test_manual_valve_time_is_not_pump_time(tmp_path, monkeypatch):
    hw = WateringHardware(HardwareConfig(mode='simulation'))
    controller = WateringController(hw, store=Store(str(tmp_path / 'manual.db')))
    try:
        controller.set_manual('valve', True)
        session = controller._session
        time.sleep(0.05)
        assert controller._operation_status()['pump_seconds'] == 0
        controller.set_manual('pump', True)
        controller.stop()
        row = controller.store.run(session['run_id'])
        assert row['elapsed_seconds'] - row['pump_seconds'] >= 0.05
    finally:
        controller.close()


def test_v1_migration_keeps_all_history_without_estimates(tmp_path):
    path = str(tmp_path / 'v1.db')
    schema = Path(__file__).parents[1] / 'app/schema.sql'
    with sqlite3.connect(path) as db:
        db.executescript(schema.read_text())  # version 1 base schema
        db.execute("INSERT INTO watering_runs(source,mode,seconds,status,created_at,elapsed_seconds) VALUES('manual','watering',2,'completed','2026-09-28T10:00:00Z',2)")
        db.execute("INSERT INTO system_events(kind,message,created_at) VALUES('test','keep','2026-09-28T10:00:00Z')")
        db.execute("INSERT INTO settings(scope,value) VALUES('real','{}')")
        db.execute('PRAGMA user_version=1')
    store = Store(path)
    Store(path)
    row = store.run(1)
    assert row['elapsed_seconds'] == 2 and row['status'] == 'completed'
    assert row['pump_seconds'] is row['estimated_ml'] is row['pump_ml_per_second'] is None
    with store.connection() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert db.execute('SELECT message FROM system_events').fetchone()[0] == 'keep'
        assert db.execute('SELECT value FROM settings').fetchone()[0] == '{}'
        assert db.execute('SELECT count(*) FROM watering_runs').fetchone()[0] == 1


def test_new_api_contract(tmp_path):
    app = create_app({'TESTING': True, 'HARDWARE_MODE': 'simulation', 'VALVE_ENABLED': '0',
                      'DATABASE_PATH': str(tmp_path / 'api.db')})
    try:
        client = app.test_client()
        assert client.post('/api/valve', json={'open': True}).status_code == 409
        assert client.post('/api/pump/calibrate', json=[]).status_code == 400
        assert client.post('/api/pump/calibrate', json={'run_id': 1, 'measured_ml': 5}).status_code == 400
        assert client.put('/api/settings', json={'pump_ml_per_second': 5}).status_code == 400
        start = client.post('/api/water', json={'seconds': 1})
        assert start.status_code == 202
        wait_for(lambda: not app.extensions['controller']._session, timeout=2)
        response = client.post('/api/pump/calibrate', json={'run_id': start.json['operation']['run_id'], 'measured_ml': 5})
        assert response.status_code == 200 and response.json['pump_ml_per_second'] > 0
        assert client.post('/api/water', json={'seconds': 1, 'volume_ml': 5}).status_code == 409
        assert client.put('/api/settings', json={'daily_limit_seconds': 1}).status_code == 200
        assert client.post('/api/pump', json={'on': True}).status_code == 409
        assert client.get('/api/status').json['hardware']['ready']
    finally:
        close_app(app)
