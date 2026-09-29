"""Short-lived SQLite connections shared safely by HTTP and background workers."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sqlite3


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


class BudgetExceeded(RuntimeError):
    pass


class Store:
    def __init__(self, path):
        self.path = path
        self.migrate()

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=2)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def migrate(self):
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 3:
                raise RuntimeError(
                    "Schemat bazy danych jest nowszy niż ta wersja aplikacji.")
            if version == 3:
                return
            if version == 0:
                schema = Path(__file__).with_name("schema.sql").read_text()
                for statement in schema.split(";"):
                    if statement.strip():
                        db.execute(statement)
                tables = {row[0] for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                # Keep the original tables intact and import their records once.
                if "moisture_readings" in tables:
                    db.execute("""INSERT OR IGNORE INTO sensor_samples
                        (channel, raw_value, created_at, legacy_id)
                        SELECT channel, value, replace(created_at, ' ', 'T') || 'Z', id
                        FROM moisture_readings""")
                if "water_events" in tables:
                    db.execute("""INSERT OR IGNORE INTO watering_runs
                        (source, mode, seconds, zone, status, created_at, legacy_id)
                        SELECT 'legacy', 'time', seconds, zone, 'legacy',
                        replace(created_at, ' ', 'T') || 'Z', id FROM water_events""")
                db.execute("PRAGMA user_version=1")
            if version < 2:
                # No pump-time measurements existed in v1; leave them unknown.
                db.execute("ALTER TABLE watering_runs ADD COLUMN pump_seconds REAL")
                db.execute("ALTER TABLE watering_runs ADD COLUMN estimated_ml REAL")
                db.execute("ALTER TABLE watering_runs ADD COLUMN pump_ml_per_second REAL")
            # Two historical v0.3 variants used version 2 with different names.
            # Inspect the actual columns before claiming the canonical v3 schema.
            columns = {row["name"] for row in db.execute("PRAGMA table_info(watering_runs)")}
            if not {"pump_seconds", "pump_elapsed_seconds"} & columns:
                raise RuntimeError("Nieznany schemat czasu pracy pompy. Zachowano bazę bez zmian.")
            if "pump_seconds" not in columns:
                db.execute("ALTER TABLE watering_runs ADD COLUMN pump_seconds REAL")
            if "pump_elapsed_seconds" in columns:
                # Preserve the old column as evidence; existing canonical values win.
                db.execute("""UPDATE watering_runs SET pump_seconds=pump_elapsed_seconds
                    WHERE pump_seconds IS NULL AND pump_elapsed_seconds IS NOT NULL""")
            for name in ("estimated_ml", "pump_ml_per_second"):
                if name not in columns:
                    db.execute(f"ALTER TABLE watering_runs ADD COLUMN {name} REAL")
            db.execute("PRAGMA user_version=3")


    def settings(self, scope):
        with self.connection() as db:
            row = db.execute(
                "SELECT value FROM settings WHERE scope=?", (scope,)).fetchone()
            return json.loads(row[0]) if row else {}

    def save_settings(self, scope, value):
        with self.connection() as db:
            db.execute("INSERT INTO settings(scope, value) VALUES (?, ?) ON CONFLICT(scope) DO UPDATE SET value=excluded.value",
                       (scope, json.dumps(value, allow_nan=False)))

    def recover(self, simulated):
        now = utc_now()
        with self.connection() as db:
            changed = db.execute("""UPDATE watering_runs SET status='interrupted',
                finished_at=?, error='Aplikacja została zatrzymana przed zapisaniem wyniku. Objętość wody jest nieznana.'
                WHERE status='running' AND simulated=?""", (now, simulated)).rowcount
            if changed:
                db.execute("INSERT INTO system_events(kind,message,simulated,created_at) VALUES ('recovery',?,?,?)",
                           (f"Oznaczono niedokończone sesje jako przerwane: {changed}. Zachowano rezerwacje budżetu.", simulated, now))

    def samples(self, readings, simulated, created_at):
        with self.connection() as db:
            db.executemany("""INSERT INTO sensor_samples
                (channel,raw_value,moisture_percent,error,simulated,created_at) VALUES (?,?,?,?,?,?)""",
                           [(r["channel"], r["raw_value"], r["moisture_percent"], r["error"], simulated, created_at)
                            for r in readings])

    def event(self, kind, message, simulated):
        with self.connection() as db:
            db.execute("INSERT INTO system_events(kind,message,simulated,created_at) VALUES (?,?,?,?)",
                       (kind, message, simulated, utc_now()))

    def begin_run(self, source, mode, seconds, target_ml, simulated, daily_limit=None):
        now = utc_now()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            used = db.execute("""SELECT COALESCE(SUM(seconds),0) FROM watering_runs
                WHERE created_at>=? AND simulated=? AND source!='legacy'""",
                              (now[:10] + "T00:00:00", simulated)).fetchone()[0]
            if daily_limit is not None and used + seconds > daily_limit:
                raise BudgetExceeded("Wyczerpano dzienny budżet czasu podlewania.")
            cursor = db.execute("""INSERT INTO watering_runs
                (source,mode,seconds,target_ml,status,simulated,created_at)
                VALUES (?,?,?,?,'running',?,?)""", (source, mode, seconds, target_ml, simulated, now))
            return cursor.lastrowid

    def finish_run(self, run_id, status, error, elapsed, pulses, delivered_ml,
                   pump_seconds=None, estimated_ml=None, pump_ml_per_second=None):
        with self.connection() as db:
            db.execute("""UPDATE watering_runs SET status=?, error=?, elapsed_seconds=?,
                pulses=?, delivered_ml=?, pump_seconds=?, estimated_ml=?, pump_ml_per_second=?,
                finished_at=? WHERE id=? AND status='running'""",
                       (status, error, elapsed, pulses, delivered_ml, pump_seconds, estimated_ml,
                        pump_ml_per_second, utc_now(), run_id))

    def run(self, run_id):
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM watering_runs WHERE id=?", (run_id,)).fetchone()
            return dict(row) if row else None

    def daily_used(self, simulated):
        with self.connection() as db:
            return db.execute("""SELECT COALESCE(SUM(seconds),0) FROM watering_runs
                WHERE created_at>=? AND simulated=? AND source!='legacy'""",
                              (utc_now()[:10] + "T00:00:00", simulated)).fetchone()[0]

    def last_finished(self, simulated):
        with self.connection() as db:
            row = db.execute(
                "SELECT MAX(finished_at) FROM watering_runs WHERE simulated=?", (simulated,)).fetchone()
            return row[0]

    def history(self, kind, simulated, limit=100, before=None, hours=24, channel=None):
        table = {"readings": "sensor_samples",
                 "runs": "watering_runs", "events": "system_events"}[kind]
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)
                 ).isoformat().replace("+00:00", "Z")
        conditions, params = ["simulated=?",
                              "created_at>=?"], [simulated, since]
        if before is not None:
            conditions.append("id<?")
            params.append(before)
        if channel is not None and kind == "readings":
            conditions.append("channel=?")
            params.append(channel)
        with self.connection() as db:
            rows = db.execute(f"SELECT * FROM {table} WHERE {' AND '.join(conditions)} ORDER BY id DESC LIMIT ?",
                              (*params, limit + 1)).fetchall()
        items = [dict(row) for row in rows[:limit]]
        return {"items": items, "next_before": items[-1]["id"] if len(rows) > limit else None}
