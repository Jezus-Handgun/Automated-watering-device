import os

import pytest

from app.hardware.gpio_controller import (
    build_hardware_config,
    probe_hardware,
    WateringHardware,
)


RUN_HARDWARE = os.environ.get("RUN_HARDWARE_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_HARDWARE,
    reason="Set RUN_HARDWARE_TESTS=1 to run hardware checks.",
)


def _load_config():
    return build_hardware_config(os.environ)


def test_hardware_probe_report():
    config = _load_config()
    report = probe_hardware(config)
    for component in report["components"]:
        name = component.get("name", "unknown")
        status = component.get("status", "unknown")
        location = component.get("location")
        details = " ".join(
            f"{key}={value}"
            for key, value in component.items()
            if key not in ("name", "status", "location")
        )
        location_text = f"location={location}" if location else ""
        line = " ".join(part for part in (location_text, details) if part)
        print(f"{name}: {status} {line}".strip())

    if report["overall_status"] != "ok":
        failed = [c for c in report["components"] if c.get("status") != "ok"]
        details = "; ".join(
            f"{c.get('name')} ({c.get('error', 'unknown error')})"
            for c in failed
        )
        raise AssertionError(f"FAIL: hardware probe failed. {details}")


def test_probe_component_count():
    config = _load_config()
    report = probe_hardware(config)
    expected = 2 + len(config.moisture_channels) + \
        (config.flow_pin is not None)
    assert len(report["components"]) == expected, (
        f"Expected {expected} components, got {len(report['components'])}."
    )


def test_moisture_readings_ok():
    config = _load_config()
    hw = WateringHardware(config)
    try:
        readings = hw.read_moisture()
        assert len(readings) == len(config.moisture_channels), (
            "FAIL: Moisture reading count does not match configured channels."
        )
        for channel, value in zip(config.moisture_channels, readings):
            assert value is not None, (
                f"FAIL: Moisture read failed on channel {channel}."
            )
            assert 0.0 <= value <= 1.0, (
                f"FAIL: Moisture value out of range on channel {channel}: {value}."
            )
    finally:
        hw.close()
