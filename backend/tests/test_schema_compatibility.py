"""Compatibility with both historical v0.3 schemas marked user_version=2."""
from pathlib import Path
import sqlite3

import pytest

from app.controller import WateringController
from app.hardware.gpio_controller import HardwareConfig, WateringHardware
from app.storage import Store


def old_v2(path, *, canonical=False, both=False, factor=False):
    schema = Path(__file__).parents[1] / 'app/schema.sql'
    with sqlite3.connect(path) as db:
        db.executescript(schema.read_text())
        column = 'pump_seconds' if canonical else 'pump_elapsed_seconds'
        db.execute(f'ALTER TABLE watering_runs ADD COLUMN {column} REAL')
        db.execute('ALTER TABLE watering_runs ADD COLUMN estimated_ml REAL')
        if factor:
            db.execute('ALTER TABLE watering_runs ADD COLUMN pump_ml_per_second REAL')
        if both:
            db.execute('ALTER TABLE watering_runs ADD COLUMN pump_seconds REAL')
        db.execute(f"""INSERT INTO watering_runs
            (id,source,mode,seconds,status,simulated,created_at,elapsed_seconds,{column},estimated_ml)
            VALUES(1,'manual','watering',5,'completed',1,'2026-09-28T10:00:00Z',5,4,8)""")
        db.execute("""INSERT INTO watering_runs
            (id,source,mode,seconds,status,simulated,created_at)
            VALUES(2,'manual','watering',5,'interrupted',1,'2026-09-28T10:00:00Z')""")
        db.execute("INSERT INTO settings VALUES('simulation', '{\"pump_ml_per_second\":2}')")
        db.execute("INSERT INTO system_events(kind,message,created_at) VALUES('test','preserve','2026-09-28T10:00:00Z')")
        db.execute('PRAGMA user_version=2')


@pytest.mark.parametrize('canonical,factor', [(False, False), (False, True), (True, True)])
def test_both_v2_schemas_preserve_values_and_allow_new_cycles(tmp_path, canonical, factor):
    path = str(tmp_path / 'v2.db')
    old_v2(path, canonical=canonical, factor=factor)
    store = Store(path)
    row = store.run(1)
    assert row['pump_seconds'] == 4
    assert row['estimated_ml'] == 8
    assert row['delivered_ml'] is None and row['pump_ml_per_second'] is None
    unknown = store.run(2)
    assert unknown['pump_seconds'] is None and unknown['estimated_ml'] is None
    assert store.settings('simulation')['pump_ml_per_second'] == 2
    controller = WateringController(WateringHardware(HardwareConfig(mode='simulation', valve_enabled=False)), store=store)
    try:
        # Known legacy pump duration is usable; calibration never rewrites estimates.
        assert controller.calibrate_pump(1, 12)['pump_ml_per_second'] == 3
        run_id = controller.start(1)['run_id']
        controller.stop()
        assert store.run(run_id)['pump_seconds'] is not None
    finally:
        controller.close()
    Store(path)  # idempotent, including imported duration and existing estimate
    assert store.run(1) == row
    with store.connection() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 3
        assert db.execute('SELECT message FROM system_events WHERE id=1').fetchone()[0] == 'preserve'
        if not canonical:
            assert db.execute('SELECT pump_elapsed_seconds FROM watering_runs WHERE id=1').fetchone()[0] == 4


def test_both_duration_columns_keep_canonical_and_fill_only_unknown(tmp_path):
    path = str(tmp_path / 'both.db')
    old_v2(path, both=True)
    with sqlite3.connect(path) as db:
        db.execute('UPDATE watering_runs SET pump_seconds=3 WHERE id=1')
        db.execute('UPDATE watering_runs SET pump_elapsed_seconds=2 WHERE id=2')
    store = Store(path)
    assert store.run(1)['pump_seconds'] == 3
    assert store.run(1)['pump_elapsed_seconds'] == 4
    assert store.run(2)['pump_seconds'] == 2
    assert store.run(2)['estimated_ml'] is None


def test_failed_migration_rolls_back_columns_data_and_version(tmp_path):
    path = str(tmp_path / 'rollback.db')
    old_v2(path)
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TRIGGER reject_duration BEFORE UPDATE ON watering_runs
            BEGIN SELECT RAISE(ABORT, 'injected migration failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match='injected migration failure'):
        Store(path)
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2
        assert 'pump_seconds' not in {row[1] for row in db.execute('PRAGMA table_info(watering_runs)')}
        assert db.execute('SELECT pump_elapsed_seconds,estimated_ml FROM watering_runs WHERE id=1').fetchone() == (4, 8)


def test_unrecognized_v2_is_not_silently_claimed_as_migrated(tmp_path):
    path = str(tmp_path / 'unknown.db')
    old_v2(path)
    with sqlite3.connect(path) as db:
        db.execute('ALTER TABLE watering_runs RENAME COLUMN pump_elapsed_seconds TO undocumented_duration')
    with pytest.raises(RuntimeError, match='czas.*pompy'):
        Store(path)
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 2
