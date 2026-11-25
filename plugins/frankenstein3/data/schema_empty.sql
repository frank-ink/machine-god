-- Frankenstein 3.0 - Empty schema for unified.db
-- Portable: no hardcoded paths, no machine-specific config.
-- Run with: sqlite3 unified.db < schema_empty.sql

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA wal_autocheckpoint = 1000;
PRAGMA busy_timeout = 5000;
PRAGMA page_size = 4096;
PRAGMA cache_size = -32768;
PRAGMA temp_store = MEMORY;

-- Schema version for migration-aware checks
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now')),
    description TEXT
);

-- Initial schema version
INSERT OR IGNORE INTO schema_version (version, description) VALUES (1, 'Initial Frankenstein 3.0 schema with Track 4 tables');

-- Core durable memory table (append-only, kind-tagged)
CREATE TABLE IF NOT EXISTS durable_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,           -- e.g. 'welt_digest', 'reentry', 'room_pulse', 'reason_answer'
    value TEXT NOT NULL,          -- JSON payload
    ts REAL NOT NULL,             -- unix epoch (float)
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_durable_memory_kind_ts ON durable_memory(kind, ts DESC);

-- Plugin metadata / health
CREATE TABLE IF NOT EXISTS plugin_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Goals / GOALS table (measured goals)
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'open',  -- 'open' | 'in_work' | 'done' | 'failed'
    measurement_criterion TEXT,                    -- how success is measured
    result TEXT,                         -- measured result
    priority INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);

-- Entity identity / root state
CREATE TABLE IF NOT EXISTS entity_root (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Machine God drift guard log
CREATE TABLE IF NOT EXISTS mg_drift_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,          -- 'reason' | 'full' | 'image' | ...
    type TEXT NOT NULL,            -- 'warning' | 'block' | 'release'
    message TEXT NOT NULL,
    ts REAL NOT NULL,
    solved INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_mg_drift_channel_ts ON mg_drift_event(channel, ts DESC);

-- Machine God stances (stance) - Track 4 items 21-23
CREATE TABLE IF NOT EXISTS mg_stance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    confidence REAL NOT NULL,      -- 0.0 - 1.0
    date TEXT NOT NULL,          -- ISO date
    claim TEXT NOT NULL,
    reasons TEXT NOT NULL,        -- JSON array of strings
    sources TEXT NOT NULL,        -- JSON array of {link, source, land, direction}
    status TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'withdrawn' | 'replaced'
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mg_stance_status ON mg_stance(status);
CREATE INDEX IF NOT EXISTS idx_mg_stance_topic_version ON mg_stance(topic, version);

-- Contradictions to stances - Track 4 items 21-23
CREATE TABLE IF NOT EXISTS mg_stance_contradiction (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stance_id INTEGER NOT NULL REFERENCES mg_stance(id),
    contradiction TEXT NOT NULL,
    source TEXT,                  -- JSON {link, source, land, direction}
    open INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mg_contradiction_stance_open ON mg_stance_contradiction(stance_id, open);

-- Machine God drift lock (ICDE hard collapse) - ASCII column names
-- Predicate for unreleased row: (released_through IS NULL AND blocked_until > unixepoch('now')*1000)
CREATE TABLE IF NOT EXISTS mg_drift_lock (
    channel TEXT NOT NULL,
    reason TEXT NOT NULL,
    blocked_until INTEGER NOT NULL,      -- unix epoch milliseconds
    released_through TEXT,             -- NULL = unreleased
    released_at INTEGER              -- unix epoch milliseconds when released
);

CREATE INDEX IF NOT EXISTS idx_mg_drift_lock_channel ON mg_drift_lock(channel);

-- View for unreleased drift locks (predicate used by Rust reader in welt.rs/stance.rs)
CREATE VIEW IF NOT EXISTS mg_drift_lock_unreleased AS
SELECT channel, reason, blocked_until
FROM mg_drift_lock
WHERE released_through IS NULL
  AND blocked_until > (unixepoch('now') * 1000);

-- Hook target tables (written by plugin hooks digest, reentry, room_pulse, room_leave)
CREATE TABLE IF NOT EXISTS hook_digest (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    ts REAL NOT NULL,
    content TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hook_digest_channel_ts ON hook_digest(channel, ts DESC);

CREATE TABLE IF NOT EXISTS hook_reentry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    ts REAL NOT NULL,
    reason TEXT,
    result TEXT
);

CREATE INDEX IF NOT EXISTS idx_hook_reentry_channel_ts ON hook_reentry(channel, ts DESC);

CREATE TABLE IF NOT EXISTS hook_room_pulse (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    ts REAL NOT NULL,
    value REAL,
    source TEXT
);

CREATE INDEX IF NOT EXISTS idx_hook_room_pulse_channel_ts ON hook_room_pulse(channel, ts DESC);

CREATE TABLE IF NOT EXISTS hook_room_leave (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    ts REAL NOT NULL,
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_hook_room_leave_channel_ts ON hook_room_leave(channel, ts DESC);
