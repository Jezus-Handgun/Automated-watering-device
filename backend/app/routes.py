from flask import Blueprint, current_app, request

from .hardware.gpio_controller import (
    build_hardware_config,
    probe_hardware,
    WateringHardware,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _parse_bool_strict(value):
    if isinstance(value, bool):
        return True, value
    if isinstance(value, (int, float)):
        return True, value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "1", "yes", "y", "on"):
            return True, True
        if text in ("false", "0", "no", "n", "off"):
            return True, False
    return False, None


def _parse_int_strict(value, min_value=None, max_value=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return False, None
    if min_value is not None and number < min_value:
        return False, None
    if max_value is not None and number > max_value:
        return False, None
    return True, number


def _get_hardware():
    if "hardware" not in current_app.extensions:
        current_app.extensions["hardware"] = WateringHardware(
            build_hardware_config(current_app.config))
    return current_app.extensions["hardware"]


@api_bp.get("/health")
def health():
    return {"status": "ok"}


@api_bp.get("/status")
def status():
    hw = _get_hardware()
    return {"hardware": hw.status()}


@api_bp.get("/moisture")
def moisture():
    hw = _get_hardware()
    return {"hardware_available": hw.available, "readings": hw.read_moisture()}


@api_bp.get("/hardware/probe")
def hardware_probe():
    config = build_hardware_config(current_app.config)
    return probe_hardware(config)


@api_bp.post("/pump")
def pump():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Invalid JSON body."}, 400
    if "on" not in data:
        return {"error": "Field 'on' is required."}, 400
    ok, on_value = _parse_bool_strict(data.get("on"))
    if not ok:
        return {"error": "Field 'on' must be boolean."}, 400
    hw = _get_hardware()
    hw.set_pump(on_value)
    return {"status": "ok", "on": on_value}


@api_bp.post("/valve")
def valve():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Invalid JSON body."}, 400
    if "open" not in data:
        return {"error": "Field 'open' is required."}, 400
    ok, open_value = _parse_bool_strict(data.get("open"))
    if not ok:
        return {"error": "Field 'open' must be boolean."}, 400
    hw = _get_hardware()
    hw.set_valve(open_value)
    return {"status": "ok", "open": open_value}


@api_bp.post("/water")
def water():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Invalid JSON body."}, 400
    if "seconds" not in data:
        return {"error": "Field 'seconds' is required."}, 400
    ok, seconds = _parse_int_strict(data.get("seconds"),
                                    min_value=1, max_value=600)
    if not ok:
        return {
            "error": "Field 'seconds' must be an integer between 1 and 600."
        }, 400
    zone = 0
    if "zone" in data:
        ok, zone = _parse_int_strict(data.get("zone"),
                                     min_value=0, max_value=16)
        if not ok:
            return {
                "error": "Field 'zone' must be an integer between 0 and 16."
            }, 400
    hw = _get_hardware()
    hw.water_for(seconds=seconds, zone=zone)
    return {"status": "ok", "seconds": seconds, "zone": zone}
