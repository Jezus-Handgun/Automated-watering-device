from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest
from gpiozero import Device
from gpiozero.pins.mock import MockFactory

from app.controller import ControlConflict, WateringController
from app.hardware import gpio_controller as gpio


@pytest.fixture()
def hardware(monkeypatch):
    monkeypatch.setattr(Device, "pin_factory", MockFactory())
    hw = gpio.WateringHardware(gpio.HardwareConfig(moisture_channels=[]))
    assert hw.ready
    yield hw
    hw.close()


@pytest.fixture()
def controller(hardware):
    control = WateringController(hardware, manual_timeout=1)
    yield control
    control.close()


def wait_idle(controller):
    deadline = time.monotonic() + 3
    while controller.status()["operation"]["active"] and time.monotonic() < deadline:
        time.sleep(0.01)
    assert controller.status()["operation"]["active"] is False


def fail(*args, **kwargs):
    raise RuntimeError("injected GPIO failure")


def test_start_failure_closes_valve(controller, hardware, monkeypatch):
    monkeypatch.setattr(hardware.pump, "on", fail)
    with pytest.raises(gpio.HardwareError):
        controller.start(5)
    state = controller.status()
    assert state["hardware"]["valve_open"] is False
    assert state["hardware"]["pump_on"] is False
    assert state["operation"]["last_result"] == "failed"
    with pytest.raises(gpio.HardwareError):
        controller.start(5)


def test_stop_failure_still_closes_valve(controller, hardware, monkeypatch):
    controller.start(5)
    monkeypatch.setattr(hardware.pump, "off", fail)
    with pytest.raises(gpio.HardwareError):
        controller.stop()
    state = controller.status()
    assert state["hardware"]["valve_open"] is False
    assert state["hardware"]["ready"] is False
    assert state["operation"]["last_result"] == "failed"


def test_valve_failure_still_stops_pump(controller, hardware, monkeypatch):
    controller.start(5)
    monkeypatch.setattr(hardware.valve, "off", fail)
    with pytest.raises(gpio.HardwareError):
        controller.stop()
    assert hardware.status()["pump_on"] is False


def test_timed_completion(controller):
    controller.start(1)
    wait_idle(controller)
    state = controller.status()
    assert state["operation"]["last_result"] == "completed"
    assert state["hardware"]["pump_on"] is False
    assert state["hardware"]["valve_open"] is False


def test_manual_timeout_does_not_extend_on_repeated_commands(controller):
    controller.set_manual("valve", True)
    deadline = controller._session["deadline"]
    controller.set_manual("pump", True)
    controller.set_manual("pump", True)
    controller.set_manual("valve", True)
    assert controller._session["deadline"] == deadline
    wait_idle(controller)
    state = controller.status()
    assert state["operation"]["last_result"] == "timeout"
    assert state["hardware"]["pump_on"] is False
    assert state["hardware"]["valve_open"] is False


def test_concurrent_starts_only_one_succeeds(controller):
    barrier = threading.Barrier(2)

    def start():
        barrier.wait(timeout=2)
        try:
            controller.start(30)
            return "accepted"
        except ControlConflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: start(), range(2)))
    assert sorted(results) == ["accepted", "conflict"]
    assert controller.status()["hardware"]["pump_on"] is True


def test_old_cancelled_worker_cannot_stop_new_session(controller):
    controller.start(30)
    old_session = controller._session
    controller.stop()
    controller.start(30)
    # Deterministically execute the old worker after the new cycle starts.
    controller._wait_for_end(old_session)
    state = controller.status()
    assert state["operation"]["active"] is True
    assert state["hardware"]["pump_on"] is True


def test_probe_does_not_allocate_or_switch_active_outputs(controller, monkeypatch):
    controller.start(30)
    monkeypatch.setattr(gpio, "OutputDevice", fail)
    report = controller.probe()
    assert report["overall_status"] == "ok"
    assert report["physical_operation_verified"] is False
    assert controller.status()["hardware"]["pump_on"] is True
    assert controller.status()["hardware"]["valve_open"] is True


def test_close_cancels_and_releases_pins(controller, hardware):
    controller.start(30)
    controller.close()
    controller.close()
    assert hardware.closed
    assert not controller.status()["operation"]["active"]
    with pytest.raises(gpio.HardwareError):
        controller.start(1)
    replacement = gpio.WateringHardware(hardware.config)
    try:
        assert replacement.ready
        assert replacement.status()["pump_on"] is False
    finally:
        replacement.close()


def test_partial_initialization_releases_already_allocated_pin(monkeypatch):
    monkeypatch.setattr(Device, "pin_factory", MockFactory())
    original = gpio.OutputDevice
    created = []

    def output(pin, **kwargs):
        if created:
            raise RuntimeError("Valve initialization failed")
        device = original(pin, **kwargs)
        created.append(device)
        return device
    monkeypatch.setattr(gpio, "OutputDevice", output)
    hw = gpio.WateringHardware(gpio.HardwareConfig(moisture_channels=[]))
    assert not hw.ready
    assert created[0].closed
    with original(17, initial_value=False) as replacement:
        assert not replacement.value
    hw.close()


def test_sensor_initialization_failure_closes_previous_devices(monkeypatch):
    monkeypatch.setattr(Device, "pin_factory", MockFactory())

    class Sensor:
        closed = False

        def close(self):
            self.closed = True
    sensor = Sensor()

    def make_sensor(channel):
        if channel == 1:
            raise RuntimeError("SPI failure")
        return sensor
    monkeypatch.setattr(gpio, "MCP3008", make_sensor)
    hw = gpio.WateringHardware(gpio.HardwareConfig(moisture_channels=[0, 1]))
    assert not hw.ready
    assert sensor.closed
    assert hw.pump is None
    hw.close()


@pytest.mark.parametrize("config", [
    {"HARDWARE_MODE": "auto"}, {"PUMP_PIN": "wrong"},
    {"PUMP_PIN": True}, {"VALVE_PIN": 17}, {"VALVE_PIN": 28},
    {"MOISTURE_CHANNELS": "0,8"}, {"MOISTURE_CHANNELS": "0,0"},
    {"MOISTURE_CHANNELS": "0,no"}, {"MOISTURE_CHANNELS": "0,"},
    {"MOISTURE_CHANNELS": [True]}, {"PUMP_PIN": 10},
])
def test_invalid_config_is_rejected(config):
    with pytest.raises(ValueError):
        gpio.build_hardware_config(config)


def test_simulation_never_allocates_hardware(monkeypatch):
    monkeypatch.setattr(gpio, "OutputDevice", fail)
    hw = gpio.WateringHardware(gpio.HardwareConfig(mode="simulation"))
    assert hw.ready
    assert not hw.available
    hw.close()


def test_worker_start_failure_switches_off_both_outputs(controller, monkeypatch):
    monkeypatch.setattr(threading.Thread, "start", fail)
    with pytest.raises(gpio.HardwareError):
        controller.start(5)
    state = controller.status()
    assert state["hardware"]["pump_on"] is False
    assert state["hardware"]["valve_open"] is False
    assert state["operation"]["active"] is False


def test_active_hardware_fault_stops_session(controller, hardware):
    controller.start(30)
    hardware.error = "GPIO status read failed"
    state = controller.status()
    assert state["hardware"]["pump_on"] is False
    assert state["hardware"]["valve_open"] is False
    assert state["operation"]["last_result"] == "failed"


def test_shutdown_attempts_all_devices_even_when_one_close_fails(hardware, monkeypatch):
    valve = hardware.valve
    monkeypatch.setattr(hardware.pump, "close", fail)
    hardware.close()
    assert valve.closed
    assert hardware.closed
    assert "Nie udało się zwolnić urządzenia GPIO" in hardware.error
