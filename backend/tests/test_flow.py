import time

import pytest
from gpiozero import Device
from gpiozero.pins.mock import MockFactory

from app.controller import WateringController, ControlConflict
from app.hardware.gpio_controller import HardwareConfig, WateringHardware, build_hardware_config
from app.storage import Store


@pytest.fixture
def controller(tmp_path):
    hw = WateringHardware(HardwareConfig(
        mode="simulation", moisture_channels=[0], flow_pin=22))
    control = WateringController(hw, store=Store(str(tmp_path / "flow.db")))
    control.update_settings({"flow_pulses_per_liter": 1000})
    yield control
    control.close()


def test_real_gpio_pulse_edges_are_counted(monkeypatch):
    factory = MockFactory()
    monkeypatch.setattr(Device, "pin_factory", factory)
    hw = WateringHardware(HardwareConfig(moisture_channels=[], flow_pin=22))
    try:
        pin = factory.pin(22)
        for _ in range(4):
            pin.drive_low()
            pin.drive_high()
        assert hw.flow()["pulses"] == 4
        assert hw.flow()["last_pulse"] is not None
        assert hw.probe()["components"][2]["name"] == "Flow meter"
    finally:
        hw.close()


def test_target_volume_completes_and_records_pulses(controller):
    controller.start(30, target_ml=10)
    with controller._lock:
        for _ in range(10):
            controller.hardware._record_pulse()
        controller._check_session(controller._session)
    state = controller.status()
    assert not state["operation"]["active"]
    assert not state["hardware"]["pump_on"]
    run = controller.store.history("runs", True)["items"][0]
    assert run["status"] == "completed"
    assert run["pulses"] == 10 and run["delivered_ml"] == 10


def test_no_flow_stops_both_outputs(controller):
    controller.start(30)
    with controller._lock:
        controller._session["pump_started"] = time.monotonic() - 6
        controller._check_session(controller._session)
    state = controller.status()
    assert "No flow" in state["operation"]["error"]
    assert not state["hardware"]["pump_on"]
    assert not state["hardware"]["valve_open"]


def test_missing_flow_calibration_rejects_volume_but_counts_time_run(controller):
    controller.update_settings({"flow_pulses_per_liter": None})
    with pytest.raises(ControlConflict):
        controller.start(5, target_ml=10)
    controller.start(5)
    controller.hardware._record_pulse()
    controller.stop()
    run = controller.store.history("runs", True)["items"][0]
    assert run["pulses"] == 1 and run["delivered_ml"] is None


def test_volume_timeout_is_failure(controller):
    controller.start(30, target_ml=10)
    with controller._lock:
        controller.hardware._record_pulse()
        controller._session["deadline"] = time.monotonic() - 1
        controller._check_session(controller._session)
    assert controller.status()["operation"]["last_result"] == "failed"
    assert "Target volume" in controller.status()["operation"]["error"]


def test_no_flow_applies_to_manual_pump(controller):
    controller.set_manual("valve", True)
    controller.set_manual("pump", True)
    with controller._lock:
        controller._session["pump_started"] = time.monotonic() - 6
        controller._check_session(controller._session)
    assert not controller.status()["hardware"]["pump_on"]
    assert controller.status()["operation"]["last_result"] == "failed"


def test_calibrate_using_measured_volume(controller):
    run_id = controller.start(30)["run_id"]
    for _ in range(20):
        controller.hardware._record_pulse()
    controller.stop()
    result = controller.calibrate_flow(run_id, 50)
    assert result["flow_pulses_per_liter"] == 400
    assert controller.store.settings(
        "simulation")["flow_pulses_per_liter"] == 400


def test_calibration_cannot_change_during_watering(controller):
    controller.start(30)
    with pytest.raises(ControlConflict):
        controller.update_settings({"flow_pulses_per_liter": 10})


@pytest.mark.parametrize("config", [{"FLOW_PIN": "17"}, {"FLOW_PIN": "8"}, {"FLOW_PIN": "28"},
                                    {"FLOW_PIN": True}, {"FLOW_PULL_UP": "yes"}])
def test_invalid_flow_configuration(config):
    with pytest.raises(ValueError):
        build_hardware_config(config)


def test_short_cycle_without_any_pulse_is_not_reported_successful(controller):
    controller.start(1)
    with controller._lock:
        controller._session["deadline"] = time.monotonic() - 0.1
        controller._check_session(controller._session)
    assert controller.status()["operation"]["last_result"] == "failed"
    assert "No flow" in controller.status()["operation"]["error"]
