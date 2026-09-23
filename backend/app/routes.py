from flask import Blueprint, current_app, request
import sqlite3

from .controller import ControlConflict, WateringController
from .hardware.gpio_controller import HardwareError, WateringHardware
from .storage import BudgetExceeded

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _get_controller():
    # Flask serves concurrent requests; initialize the GPIO owner only once.
    with current_app.extensions["controller_lock"]:
        if current_app.extensions.get("controller_closed"):
            raise HardwareError("Aplikacja jest zamykana.")
        if "controller" not in current_app.extensions:
            hardware = WateringHardware(
                current_app.extensions["hardware_config"])
            try:
                current_app.extensions["controller"] = WateringController(
                    hardware, manual_timeout=current_app.config["MANUAL_TIMEOUT_SECONDS"],
                    store=current_app.extensions["store"])
            except Exception:
                hardware.close()
                raise
        return current_app.extensions["controller"]


@api_bp.errorhandler(HardwareError)
def hardware_error(error):
    return {"error": str(error)}, 503


@api_bp.errorhandler(ControlConflict)
def control_conflict(error):
    return {"error": str(error)}, 409


@api_bp.errorhandler(ValueError)
def invalid_value(error):
    return {"error": str(error)}, 400


@api_bp.errorhandler(sqlite3.Error)
def storage_error(error):
    return {"error": "Zapis historii jest niedostępny."}, 503


@api_bp.errorhandler(BudgetExceeded)
def budget_exceeded(error):
    return {"error": str(error)}, 409


@api_bp.after_request
def prevent_cached_status(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@api_bp.get("/health")
def health():
    # Process liveness, deliberately separate from hardware readiness.
    return {"status": "ok"}


@api_bp.get("/status")
def status():
    return _get_controller().status()


@api_bp.get("/moisture")
def moisture():
    return _get_controller().moisture()


@api_bp.get("/hardware/probe")
def hardware_probe():
    return _get_controller().probe()


def _manual_command(device, field):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Niepoprawna treść żądania JSON."}, 400
    if type(data.get(field)) is not bool:
        return {"error": f"Pole '{field}' musi mieć wartość logiczną true albo false."}, 400
    controller = _get_controller()
    controller.set_manual(device, data[field])
    return {"status": "ok", field: data[field], **controller.status()}


@api_bp.post("/pump")
def pump():
    return _manual_command("pump", "on")


@api_bp.post("/valve")
def valve():
    return _manual_command("valve", "open")


@api_bp.post("/water")
def water():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Niepoprawna treść żądania JSON."}, 400
    seconds = data.get("seconds")
    if type(seconds) is not int or not 1 <= seconds <= 600:
        return {"error": "Czas podlewania musi być liczbą całkowitą od 1 do 600 sekund."}, 400
    zone = data.get("zone", 0)
    if type(zone) is not int or zone != 0:
        return {"error": "Obsługiwana jest tylko strefa 0. Numer strefy musi być liczbą całkowitą 0."}, 400
    if "volume_ml" in data and data["volume_ml"] is None:
        return {"error": "Objętość musi być skończoną liczbą od 1 do 5000 ml."}, 400
    operation = _get_controller().start(
        seconds, zone, target_ml=data.get("volume_ml"))
    return {"status": "accepted", "seconds": seconds, "zone": zone, "operation": operation}, 202


@api_bp.post("/stop")
def stop():
    operation = _get_controller().stop()
    return {"status": "ok", "operation": operation}


@api_bp.get("/settings")
def settings():
    controller = _get_controller()
    with controller._lock:
        return controller.settings.json()


@api_bp.put("/settings")
def update_settings():
    return _get_controller().update_settings(request.get_json(silent=True))


@api_bp.post("/flow/calibrate")
def calibrate_flow():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {"error": "Podaj numer cyklu i zmierzoną objętość w obiekcie JSON."}, 400
    return _get_controller().calibrate_flow(data.get("run_id"), data.get("measured_ml"))


@api_bp.get("/history/<kind>")
def history(kind):
    if kind not in ("readings", "runs", "events"):
        return {"error": "Nieznany rodzaj historii."}, 404

    def parameter(name, default, low, high):
        raw = request.args.get(name)
        if raw is None:
            return default
        if not raw.isascii() or not raw.isdecimal() or not low <= int(raw) <= high:
            raise ValueError(
                f"Parametr {name} musi być liczbą całkowitą od {low} do {high}.")
        return int(raw)
    result = current_app.extensions["store"].history(
        kind, current_app.extensions["hardware_config"].mode == "simulation",
        limit=parameter("limit", 100, 1, 1000),
        before=parameter("before", None, 1, 2**63 - 1),
        hours=parameter("hours", 24, 1, 8760),
        channel=parameter("channel", None, 0, 7))
    return result
