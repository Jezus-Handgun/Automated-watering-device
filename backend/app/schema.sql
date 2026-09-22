CREATE TABLE IF NOT EXISTS sensor_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel INTEGER NOT NULL,
    raw_value REAL,
    moisture_percent REAL,
    error TEXT,
    simulated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    legacy_id INTEGER UNIQUE
);
CREATE INDEX IF NOT EXISTS samples_time_channel ON sensor_samples(created_at, channel);
CREATE TABLE IF NOT EXISTS watering_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    mode TEXT NOT NULL,
    seconds INTEGER NOT NULL,
    target_ml REAL,
    delivered_ml REAL,
    pulses INTEGER,
    elapsed_seconds REAL,
    zone INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    error TEXT,
    simulated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    legacy_id INTEGER UNIQUE
);
CREATE INDEX IF NOT EXISTS runs_time ON watering_runs(created_at);
CREATE TABLE IF NOT EXISTS system_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    simulated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    scope TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
