from concurrent.futures import ThreadPoolExecutor

import pytest

from app import close_app, create_app
from app.routes import _get_controller


@pytest.fixture()
def app(tmp_path):
    application = create_app({
        "TESTING": True, "HARDWARE_MODE": "simulation",
        "DATABASE_PATH": str(tmp_path / "watering.db"),
    })
    yield application
    close_app(application)


@pytest.fixture()
def client(app):
    return app.test_client()


def test_panel_and_api_share_origin(client):
    for path in ("/", "/app.js", "/styles.css", "/api/health"):
        assert client.get(path).status_code == 200
    assert b'src="app.js"' in client.get("/").data
    assert client.get("/api/health").get_json() == {"status": "ok"}


def test_explicit_simulation(client):
    payload = client.get("/api/status").get_json()
    assert payload["hardware"]["available"] is False
    assert payload["hardware"]["simulated"] is True
    assert payload["hardware"]["ready"] is True
    assert payload["operation"]["active"] is False
    response = client.get("/api/moisture")
    assert response.get_json()["readings"] == [None, None, None]
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("value", [None, "true", "false", 0, 1, 1.5, [], {}])
@pytest.mark.parametrize("path,field", [("pump", "on"), ("valve", "open")])
def test_manual_validation(client, value, path, field):
    assert client.post(f"/api/{path}", json={field: value}).status_code == 400


@pytest.mark.parametrize("seconds", [None, 0, -1, 601, 1.9, 1.0, True, False, "5", [], {}])
def test_water_rejects_invalid_seconds(client, seconds):
    assert client.post(
        "/api/water", json={"seconds": seconds}).status_code == 400


@pytest.mark.parametrize("zone", [1, 16, -1, True, False, 0.0, "0", None])
def test_only_integer_zone_zero(client, zone):
    assert client.post(
        "/api/water", json={"seconds": 5, "zone": zone}).status_code == 400


@pytest.mark.parametrize("path", ["water", "pump", "valve"])
@pytest.mark.parametrize("body", ["null", "[]", "{", '"test"'])
def test_invalid_body(client, path, body):
    assert client.post(f"/api/{path}", data=body,
                       content_type="application/json").status_code == 400


def test_async_start_conflicts_and_stop(client):
    response = client.post("/api/water", json={"seconds": 600, "zone": 0})
    assert response.status_code == 202
    assert response.get_json()["operation"]["active"] is True
    assert client.post("/api/water", json={"seconds": 1}).status_code == 409
    assert client.post("/api/pump", json={"on": False}).status_code == 409
    assert client.post("/api/valve", json={"open": False}).status_code == 409
    assert client.post("/api/stop").status_code == 200
    payload = client.get("/api/status").get_json()
    assert payload["operation"]["last_result"] == "cancelled"
    assert payload["hardware"]["pump_on"] is False
    assert payload["hardware"]["valve_open"] is False
    assert client.post("/api/stop").status_code == 200
    assert client.post("/api/water", json={"seconds": 5}).status_code == 202


def test_manual_interlocks(client):
    assert client.post("/api/pump", json={"on": True}).status_code == 409
    assert client.post("/api/valve", json={"open": True}).status_code == 200
    assert client.post("/api/pump", json={"on": True}).status_code == 200
    assert client.post("/api/valve", json={"open": False}).status_code == 409
    assert client.post("/api/water", json={"seconds": 5}).status_code == 409
    assert client.post("/api/pump", json={"on": False}).status_code == 200
    state = client.get("/api/status").get_json()
    assert state["hardware"]["valve_open"] is False
    assert state["operation"]["active"] is False


def test_probe_reports_simulation(client):
    report = client.get("/api/hardware/probe").get_json()
    assert report["overall_status"] == "simulated"
    assert report["physical_operation_verified"] is False
    assert len(report["components"]) == 5


def test_hardware_initialization_failure_is_not_simulation(tmp_path, monkeypatch):
    from app.hardware import gpio_controller

    def unavailable(*args, **kwargs):
        raise RuntimeError("No GPIO access")
    monkeypatch.setattr(gpio_controller, "OutputDevice", unavailable)
    app = create_app({"TESTING": True, "HARDWARE_MODE": "real",
                      "DATABASE_PATH": str(tmp_path / "test.db")})
    try:
        client = app.test_client()
        assert client.get("/api/health").status_code == 200
        state = client.get("/api/status").get_json()["hardware"]
        assert state["simulated"] is False
        assert state["ready"] is False
        assert state["pump_on"] is None
        assert "Nie udało się uruchomić sprzętu" in state["error"]
        response = client.post("/api/water", json={"seconds": 1})
        assert response.status_code == 503
        assert response.is_json
        assert client.get(
            "/api/hardware/probe").get_json()["overall_status"] == "fail"
    finally:
        close_app(app)


def test_concurrent_initialization_has_one_owner(app, monkeypatch):
    from app import routes
    original = routes.WateringHardware
    created = []

    def factory(config):
        hardware = original(config)
        created.append(hardware)
        return hardware
    monkeypatch.setattr(routes, "WateringHardware", factory)

    def get_owner(_):
        with app.app_context():
            return _get_controller()
    with ThreadPoolExecutor(max_workers=8) as pool:
        controllers = list(pool.map(get_owner, range(16)))
    assert len(created) == 1
    assert all(controller is controllers[0] for controller in controllers)


def test_hardware_failure_response_and_stop_remains_available(app, client, monkeypatch):
    with app.app_context():
        controller = _get_controller()

    def fail(on):
        if on:
            raise RuntimeError("Pump failed")
    monkeypatch.setattr(controller.hardware, "set_pump", fail)
    response = client.post("/api/water", json={"seconds": 5})
    assert response.status_code == 503
    assert "Błąd sterowania urządzeniem" in response.get_json()["error"]
    assert client.post("/api/stop").status_code == 200
    state = client.get("/api/status").get_json()
    assert state["hardware"]["valve_open"] is False
    assert state["hardware"]["ready"] is False


def test_shutdown_blocks_late_hardware_initialization(app, client):
    close_app(app)
    response = client.post("/api/water", json={"seconds": 5})
    assert response.status_code == 503
    assert "controller" not in app.extensions


@pytest.mark.parametrize("patch", [
    {"enabled": True}, {"enabled": "false"}, {"filter_samples": 2},
    {"channel": 7}, {"dry_raw": 0.5, "wet_raw": 0.5},
    {"start_percent": 60, "stop_percent": 40}, {"portion_seconds": True},
    {"portion_ml": float("nan")}, {"flow_pulses_per_liter": float("inf")},
    {"flow_pulses_per_liter": 10**400}, {"unknown": 1}, {}, None,
])
def test_settings_reject_invalid_changes(client, patch):
    before = client.get("/api/settings").get_json()
    response = client.put("/api/settings", json=patch)
    assert response.status_code == 400
    assert client.get("/api/settings").get_json() == before


def test_save_calibration_and_enable_automation(client):
    response = client.put(
        "/api/settings", json={"dry_raw": 0.9, "wet_raw": 0.1, "enabled": True})
    assert response.status_code == 200
    assert client.get("/api/settings").get_json()["enabled"]
    assert client.post("/api/stop").status_code == 200
    assert not client.get("/api/settings").get_json()["enabled"]


@pytest.mark.parametrize("suffix", ["?limit=0", "?limit=1001", "?before=-1", "?hours=0", "?hours=99999", "?channel=8", "?limit=1.5"])
def test_history_validation(client, suffix):
    assert client.get("/api/history/readings" + suffix).status_code == 400


def test_history_records_completed_commands(client):
    client.post("/api/water", json={"seconds": 5})
    client.post("/api/stop")
    run = client.get("/api/history/runs").get_json()["items"][0]
    assert run["status"] == "cancelled"
    assert run["simulated"] == 1
    assert run["delivered_ml"] is None
    assert run["finished_at"]
    assert client.get("/api/history/unknown").status_code == 404


@pytest.mark.parametrize("volume", [None, True, 0, -1, 5001, "50", float("nan"), 10**400])
def test_volume_validation(client, volume):
    assert client.post(
        "/api/water", json={"seconds": 5, "volume_ml": volume}).status_code == 400


def test_volume_requires_flow_configuration(client):
    assert client.post(
        "/api/water", json={"seconds": 5, "volume_ml": 50}).status_code == 409
    assert client.post("/api/flow/calibrate",
                       json={"run_id": 1, "measured_ml": 50}).status_code == 400


def test_changing_channel_requires_new_calibration(client):
    client.put("/api/settings", json={"dry_raw": 0.9, "wet_raw": 0.1})
    response = client.put("/api/settings", json={"channel": 1})
    assert response.status_code == 200
    assert response.get_json()["dry_raw"] is None
    assert response.get_json()["wet_raw"] is None
    assert client.put(
        "/api/settings", json={"enabled": True}).status_code == 400
