import pytest

from app import create_app
from app import routes


class DummyHardware:
    def __init__(self):
        self.available = False
        self._pump_on = False
        self._valve_open = False
        self.last_water = None

    def status(self):
        return {
            "available": self.available,
            "pump_on": self._pump_on,
            "valve_open": self._valve_open,
            "moisture_channels": [0, 1, 2],
        }

    def read_moisture(self):
        return [0.42, 0.58, 0.73]

    def set_pump(self, on: bool):
        self._pump_on = bool(on)

    def set_valve(self, open_value: bool):
        self._valve_open = bool(open_value)

    def water_for(self, seconds: int, zone: int = 0):
        self.last_water = {"seconds": seconds, "zone": zone}


@pytest.fixture()
def client():
    app = create_app()
    app.testing = True
    app.extensions["hardware"] = DummyHardware()
    return app.test_client()


def test_health_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_status_ok(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["hardware"]["available"] is False


def test_pump_validation(client):
    response = client.post("/api/pump", json={})
    assert response.status_code == 400

    response = client.post("/api/pump", json={"on": "maybe"})
    assert response.status_code == 400

    response = client.post("/api/pump", json={"on": True})
    assert response.status_code == 200


def test_valve_validation(client):
    response = client.post("/api/valve", json={})
    assert response.status_code == 400

    response = client.post("/api/valve", json={"open": "maybe"})
    assert response.status_code == 400

    response = client.post("/api/valve", json={"open": True})
    assert response.status_code == 200


def test_water_validation(client):
    response = client.post("/api/water", json={})
    assert response.status_code == 400

    response = client.post("/api/water", json={"seconds": 0})
    assert response.status_code == 400

    response = client.post("/api/water", json={"seconds": 10, "zone": 1})
    assert response.status_code == 200


def test_hardware_probe_endpoint(client, monkeypatch):
    report = {
        "overall_status": "ok",
        "components": [
            {"name": "Pump", "type": "gpio_output", "status": "ok"},
            {"name": "Valve", "type": "gpio_output", "status": "ok"},
        ],
    }
    monkeypatch.setattr(routes, "probe_hardware", lambda config: report)

    response = client.get("/api/hardware/probe")
    assert response.status_code == 200
    assert response.get_json() == report
