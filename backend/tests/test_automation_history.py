import sqlite3
import threading
import time

import pytest

from app import close_app, create_app, start_services
from app.automation import Settings, MoistureFilter
from app.controller import WateringController, ControlConflict
from app.hardware.gpio_controller import HardwareConfig, WateringHardware, HardwareError
from app.storage import Store, utc_now


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / "history.db"))


@pytest.fixture
def setup(store, monkeypatch):
    hw = WateringHardware(HardwareConfig(
        mode="simulation", moisture_channels=[0], flow_pin=22))
    controller = WateringController(hw, store=store)
    reading = [0.74]
    monkeypatch.setattr(hw, "read_moisture", lambda: list(reading))
    yield controller, store, reading
    controller.close()


def enable(controller, **patch):
    return controller.update_settings({"dry_raw": 0.9, "wet_raw": 0.1, "filter_samples": 1,
                                       "portion_seconds": 2, "soak_seconds": 2,
                                       "enabled": True, **patch})


def finish_and_expire_soak(controller):
    with controller._lock:
        controller._finish("completed")
        controller._soak_until = time.monotonic() - 1
    controller.sample_once()  # discard pre-soak filter window
    controller.sample_once()


def test_legacy_migration_preserves_data_and_is_idempotent(tmp_path):
    path = str(tmp_path / "legacy.db")
    with sqlite3.connect(path) as db:
        db.executescript("""CREATE TABLE moisture_readings(id INTEGER PRIMARY KEY, channel INTEGER, value REAL, created_at TEXT);
          INSERT INTO moisture_readings VALUES(4,2,0.42,'2026-09-22 10:00:00');
          CREATE TABLE water_events(id INTEGER PRIMARY KEY, seconds INTEGER, zone INTEGER, created_at TEXT);
          INSERT INTO water_events VALUES(7,15,0,'2026-09-22 10:01:00');""")
    store = Store(path)
    Store(path)
    with store.connection() as db:
        assert db.execute(
            "SELECT COUNT(*) FROM moisture_readings").fetchone()[0] == 1
        assert db.execute("SELECT value FROM moisture_readings WHERE id=4").fetchone()[
            0] == 0.42
        row = db.execute("SELECT * FROM sensor_samples").fetchone()
        assert row["raw_value"] == 0.42 and row["legacy_id"] == 4
        assert db.execute(
            "SELECT COUNT(*) FROM sensor_samples").fetchone()[0] == 1
        assert db.execute("SELECT status FROM watering_runs").fetchone()[
            0] == "legacy"
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1


def test_init_db_does_not_erase_recorded_history(tmp_path):
    app = create_app({"TESTING": True, "HARDWARE_MODE": "simulation",
                     "DATABASE_PATH": str(tmp_path / "db.sqlite")})
    store = app.extensions["store"]
    store.event("test", "preserve", True)
    try:
        assert app.test_cli_runner().invoke(args=["init-db"]).exit_code == 0
        assert app.test_cli_runner().invoke(args=["init-db"]).exit_code == 0
        assert len(store.history("events", True)["items"]) == 1
    finally:
        close_app(app)


def test_newer_schema_is_not_overwritten(tmp_path):
    path = str(tmp_path / "newer.db")
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=999")
    with pytest.raises(RuntimeError):
        Store(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 999


def test_filter_calibration_median_and_invalid_readings():
    settings = Settings(dry_raw=0.9, wet_raw=0.1, filter_samples=3)
    f = MoistureFilter()
    assert f.sample(0, 0.7, settings)["moisture_percent"] is None
    assert f.sample(0, 0.2, settings)["moisture_percent"] is None
    assert f.sample(0, 0.7, settings)["moisture_percent"] == 25
    assert f.sample(0, float("nan"), settings)["raw_value"] is None
    assert f.sample(0, 0.7, settings)["moisture_percent"] is None
    assert f.sample(0, 1, settings)["error"]
    settings = Settings(dry_raw=0.1, wet_raw=0.9, filter_samples=1)
    assert MoistureFilter().sample(0, 0.3, settings)["moisture_percent"] == 25


def test_automation_requires_calibration(setup):
    controller, _, _ = setup
    with pytest.raises(ValueError):
        controller.update_settings({"enabled": True})
    assert not controller.settings.enabled


def test_hysteresis_portions_soak_and_fresh_samples(setup):
    controller, store, reading = setup
    enable(controller, filter_samples=3)
    for _ in range(3):
        controller.sample_once()
    assert controller.status()["operation"]["source"] == "automatic"
    assert store.daily_used(True) == 2
    with controller._lock:
        controller._finish("completed")
    reading[0] = 0.58  # 40%, continue the existing demand until 50%
    for _ in range(3):
        controller.sample_once()
    assert not controller.status()["operation"]["active"]
    assert controller.status()["automation"]["reason"] == "soaking"
    controller._soak_until = time.monotonic() - 1
    controller.sample_once()
    for _ in range(2):
        controller.sample_once()
        assert not controller.status()["operation"]["active"]
    controller.sample_once()
    assert controller.status()["operation"]["active"]
    reading[0] = 0.46  # 55%, stop demanding water
    with controller._lock:
        controller._finish("completed")
        controller._soak_until = time.monotonic() - 1
    for _ in range(7):
        controller.sample_once()
    assert not controller.status()["operation"]["active"]
    assert controller.status()["automation"]["reason"] == "moisture_sufficient"


def test_sensor_failure_stops_automatic_cycle_and_logs_gap(setup):
    controller, store, reading = setup
    enable(controller)
    controller.sample_once()
    reading[0] = None
    controller.sample_once()
    state = controller.status()
    assert not state["operation"]["active"]
    assert not state["hardware"]["pump_on"]
    assert state["operation"]["last_result"] == "sensor_error"
    samples = store.history("readings", True)["items"]
    assert samples[0]["raw_value"] is None and samples[0]["error"]
    assert store.history("runs", True)[
        "items"][0]["error"] == "Pomiar wilgotności stał się niepoprawny."


def test_daily_limit_survives_restart_and_counts_manual_reservations(setup):
    controller, store, _ = setup
    controller.start(2)
    controller.stop()
    enable(controller, daily_limit_seconds=2)
    controller._soak_until = 0
    controller._soaking = False
    controller.sample_once()
    assert controller.status()["automation"]["reason"] == "daily_limit"
    controller.close()
    replacement = WateringController(WateringHardware(
        controller.hardware.config), store=store)
    try:
        assert replacement.settings.enabled
        assert replacement.status()["automation"]["daily_used_seconds"] == 2
        assert not replacement.status()["operation"]["active"]
    finally:
        replacement.close()


def test_restart_marks_interrupted_run_and_keeps_reservation(store):
    run_id = store.begin_run("automatic", "watering", 7, None, True)
    controller = WateringController(WateringHardware(
        HardwareConfig(mode="simulation")), store=store)
    try:
        assert store.run(run_id)["status"] == "interrupted"
        assert store.daily_used(True) == 7
        assert controller.status()["automation"]["soak_remaining_seconds"] > 0
    finally:
        controller.close()


def test_stop_disables_automation_persistently(setup):
    controller, store, _ = setup
    enable(controller)
    controller.sample_once()
    controller.stop()
    assert not store.settings("simulation")["enabled"]
    controller.sample_once()
    assert not controller.status()["operation"]["active"]


def test_store_failure_before_start_does_not_energize_outputs(setup, monkeypatch):
    controller, store, _ = setup

    def failure(*args, **kwargs):
        raise sqlite3.OperationalError("disk full")
    monkeypatch.setattr(store, "begin_run", failure)
    with pytest.raises(HardwareError):
        controller.start(2)
    state = controller.status()
    assert not state["hardware"]["pump_on"]
    assert not state["hardware"]["valve_open"]


def test_store_failure_on_finish_still_switches_off_outputs(setup, monkeypatch):
    controller, store, _ = setup
    controller.start(2)

    def failure(*args, **kwargs):
        raise sqlite3.OperationalError("disk full")
    monkeypatch.setattr(store, "finish_run", failure)
    with pytest.raises(HardwareError):
        controller.stop()
    assert not controller.hardware.status()["pump_on"]
    assert not controller.hardware.status()["valve_open"]


def test_background_samples_without_http_requests(tmp_path, monkeypatch):
    app = create_app({"TESTING": True, "HARDWARE_MODE": "simulation",
                     "DATABASE_PATH": str(tmp_path / "bg.db")})
    event = threading.Event()
    store = app.extensions["store"]
    original = store.samples

    def save(*args):
        original(*args)
        event.set()
    monkeypatch.setattr(store, "samples", save)
    try:
        start_services(app)
        assert event.wait(2)
        assert store.history("readings", True)["items"]
        worker = app.extensions["controller"]._service_thread
        close_app(app)
        assert not worker.is_alive()
    finally:
        close_app(app)


def test_settings_separate_simulated_and_real_modes(setup):
    controller, store, _ = setup
    enable(controller)
    assert store.settings("simulation")["enabled"]
    assert store.settings("real") == {}


def test_history_cursor_and_mode_isolation(store):
    for index in range(5):
        store.event("test", str(index), True)
    store.event("test", "real", False)
    first = store.history("events", True, limit=3)
    second = store.history("events", True, limit=3,
                           before=first["next_before"])
    assert len(first["items"]) == 3 and len(second["items"]) == 2
    assert not second["next_before"]
    assert len({row["id"] for row in first["items"] + second["items"]}) == 5


def test_midnight_reservation_is_counted(store, monkeypatch):
    monkeypatch.setattr("app.storage.utc_now",
                        lambda: "2026-09-22T00:00:00.123456Z")
    store.begin_run("automatic", "watering", 5, None, True, daily_limit=5)
    assert store.daily_used(True) == 5
