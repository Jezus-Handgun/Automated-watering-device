from flask import Blueprint, current_app, request

from .hardware.gpio_controller import HardwareConfig, WateringHardware

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _parse_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "1", "yes", "y", "on"):
            return True
        if text in ("false", "0", "no", "n", "off"):
            return False
    return default


def _parse_int(value, default, min_value=None, max_value=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if min_value is not None and number < min_value:
        return default
    if max_value is not None and number > max_value:
        return default
    return number


def _build_hardware_config():
    channels_raw = current_app.config.get("MOISTURE_CHANNELS", "0,1,2")
    channels = []
    for part in channels_raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            channels.append(int(part))
        except ValueError:
            continue
    return HardwareConfig(
        pump_pin=current_app.config.get("PUMP_PIN", 17),
        valve_pin=current_app.config.get("VALVE_PIN", 27),
        moisture_channels=channels,
    )


def _get_hardware():
    if "hardware" not in current_app.extensions:
        current_app.extensions["hardware"] = WateringHardware(_build_hardware_config())
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


@api_bp.post("/pump")
def pump():
    data = request.get_json(silent=True) or {}
    on_value = _parse_bool(data.get("on"), default=True)
    hw = _get_hardware()
    hw.set_pump(on_value)
    return {"status": "ok", "on": on_value}


@api_bp.post("/valve")
def valve():
    data = request.get_json(silent=True) or {}
    open_value = _parse_bool(data.get("open"), default=True)
    hw = _get_hardware()
    hw.set_valve(open_value)
    return {"status": "ok", "open": open_value}


@api_bp.post("/water")
def water():
    data = request.get_json(silent=True) or {}
    seconds = _parse_int(data.get("seconds"), default=5, min_value=1, max_value=600)
    zone = _parse_int(data.get("zone"), default=0, min_value=0, max_value=16)
    hw = _get_hardware()
    hw.water_for(seconds=seconds, zone=zone)
    return {"status": "ok", "seconds": seconds, "zone": zone}
