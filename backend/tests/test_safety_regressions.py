"""Safety regressions: GPIO mocks and a real, temporary SQLite database."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest
from gpiozero import Device
from gpiozero.pins.mock import MockFactory

from app.controller import ControlConflict, WateringController
from app.hardware.gpio_controller import HardwareConfig, WateringHardware, build_hardware_config
from app.storage import Store


def wait_for(predicate, timeout=0.5):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.005)
    assert predicate()


@pytest.mark.parametrize('pump_high', [False, True])
@pytest.mark.parametrize('valve_high', [False, True])
def test_output_polarities_and_safe_off(monkeypatch, pump_high, valve_high):
    monkeypatch.setattr(Device, 'pin_factory', MockFactory())
    config = build_hardware_config({'MOISTURE_CHANNELS': '',
                                   'PUMP_ACTIVE_HIGH': str(int(pump_high)),
                                   'VALVE_ACTIVE_HIGH': str(int(valve_high))})
    hw = WateringHardware(config)
    try:
        for device, high in ((hw.pump, pump_high), (hw.valve, valve_high)):
            assert device.pin.state == (not high)
        hw.set_valve(True)
        hw.set_pump(True)
        assert hw.status()['pump_on'] is True
        assert hw.status()['valve_open'] is True
        assert hw.pump.pin.state == pump_high
        assert hw.valve.pin.state == valve_high
        assert hw.safe_off() == []
        assert hw.pump.pin.state == (not pump_high)
        assert hw.valve.pin.state == (not valve_high)
    finally:
        hw.close()


@pytest.mark.parametrize('key', ['PUMP_ACTIVE_HIGH', 'VALVE_ACTIVE_HIGH'])
@pytest.mark.parametrize('value', ['false', 'yes', '', 0, 1, None])
def test_invalid_polarity(key, value):
    with pytest.raises(ValueError):
        build_hardware_config({key: value})


@pytest.fixture()
def control(tmp_path):
    hw = WateringHardware(HardwareConfig(mode='simulation', moisture_channels=[0]))
    controller = WateringController(hw, manual_timeout=1, store=Store(str(tmp_path / 'test.db')))
    yield controller
    controller.close()


@pytest.mark.parametrize('mode', ['timed', 'manual', 'stop', 'close', 'flow'])
def test_database_write_lock_does_not_delay_outputs_off(control, monkeypatch, mode):
    if mode == 'flow':
        control.hardware.config.flow_pin = 22
        control.settings.no_flow_timeout_seconds = 0.2
    if mode == 'manual':
        control.set_manual('valve', True)
        control.set_manual('pump', True)
    else:
        control.start(1 if mode == 'timed' else 30)
    session = control._session
    entered = threading.Event()
    samples = control.store.samples

    def observed_samples(*args):
        entered.set()
        return samples(*args)

    monkeypatch.setattr(control.store, 'samples', observed_samples)
    with ThreadPoolExecutor(max_workers=2) as pool:
        with control.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            sampler = pool.submit(control.sample_once)
            assert entered.wait(1)
            stopping = None
            if mode in ('stop', 'close'):
                stopping = pool.submit(getattr(control, mode))
            # Inspect outputs directly: HTTP status may itself await SQLite.
            wait_for(lambda: not control.hardware.status()['pump_on'],
                     timeout=1.4 if mode in ('timed', 'manual') else 0.6)
            assert control.hardware.status()['valve_open'] is False
            assert not sampler.done(), 'Database must still be blocked at cutoff'
            stopped_at = session['stopped_at']
        sampler.result(timeout=3)
        if stopping:
            stopping.result(timeout=3)
    wait_for(lambda: control._session is None)
    with control._lock:
        run = control.store.run(session['run_id'])
    assert run['elapsed_seconds'] == pytest.approx(stopped_at - session['started'])
    assert control.store.daily_used(True) == session['seconds']


def test_stop_cancels_start_waiting_for_reservation(control, monkeypatch):
    entered = threading.Event()
    begin = control.store.begin_run
    switched_on = []
    original = control.hardware.set_pump

    def pump(on):
        if on:
            switched_on.append(True)
        original(on)

    def observed_begin(*args):
        entered.set()
        return begin(*args)

    monkeypatch.setattr(control.store, 'begin_run', observed_begin)
    monkeypatch.setattr(control.hardware, 'set_pump', pump)
    with ThreadPoolExecutor(max_workers=2) as pool:
        with control.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            starting = pool.submit(control.start, 30)
            assert entered.wait(1)
            stopping = pool.submit(control.stop)
            wait_for(lambda: control._pending_stops == 1)
            assert not control.hardware.status()['pump_on']
        with pytest.raises(ControlConflict):
            starting.result(timeout=3)
        stopping.result(timeout=3)
    assert switched_on == []
    assert control._session is None
    assert control.store.daily_used(True) == 30
    assert control.store.history('runs', True)['items'][0]['status'] == 'cancelled'
    control.start(1)
    assert control.hardware.status()['pump_on']
