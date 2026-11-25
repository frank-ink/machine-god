-- Frankenstein 3.0 - Empty schema for unified.db
-- Portable: no hardcoded paths, no machine-specific config.
-- Run with: sqlite3 unified.db < schema_leer.sql

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
    kind TEXT NOT NULL,           -- e.g. 'welt_digest', 'reentry', 'raum_puls', 'grund_antwort'
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

-- Goals / ZIELE table (measured goals)
CREATE TABLE IF NOT EXISTS ziele (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titel TEXT NOT NULL,
    beschreibung TEXT,
    status TEXT NOT NULL DEFAULT 'offen',  -- 'offen' | 'in_arbeit' | 'erledigt' | 'fehlgeschlagen'
    messkriterium TEXT,                    -- how success is measured
    ergebnis TEXT,                         -- measured result
    prioritaet INTEGER DEFAULT 0,
    erstellt_at TEXT DEFAULT (datetime('now')),
    aktualisiert_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ziele_status ON ziele(status);

-- Entity identity / root state
CREATE TABLE IF NOT EXISTS entity_root (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Machine God drift guard log
CREATE TABLE IF NOT EXISTS mg_drift_ereignis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kanal TEXT NOT NULL,          -- 'grund' | 'voll' | 'bild' | ...
    typ TEXT NOT NULL,            -- 'warnung' | 'sperre' | 'freigabe'
    nachricht TEXT NOT NULL,
    ts REAL NOT NULL,
    gelöst INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_mg_drift_kanal_ts ON mg_drift_ereignis(kanal, ts DESC);

-- Machine God stances (Haltung) - Track 4 items 21-23
CREATE TABLE IF NOT EXISTS mg_haltung (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thema TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    konfidenz REAL NOT NULL,      -- 0.0 - 1.0
    datum TEXT NOT NULL,          -- ISO date
    claim TEXT NOT NULL,
    gruende TEXT NOT NULL,        -- JSON array of strings
    quellen TEXT NOT NULL,        -- JSON array of {link, quelle, land, richtung}
    status TEXT NOT NULL DEFAULT 'aktiv',  -- 'aktiv' | 'zurueckgezogen' | 'ersetzt'
    erstellt_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mg_haltung_status ON mg_haltung(status);
CREATE INDEX IF NOT EXISTS idx_mg_haltung_thema_version ON mg_haltung(thema, version);

-- Contradictions to stances - Track 4 items 21-23
CREATE TABLE IF NOT EXISTS mg_haltung_widerspruch (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    haltung_id INTEGER NOT NULL REFERENCES mg_haltung(id),
    widerspruch TEXT NOT NULL,
    quelle TEXT,                  -- JSON {link, quelle, land, richtung}
    offen INTEGER NOT NULL DEFAULT 1,
    erstellt_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mg_widerspruch_haltung_offen ON mg_haltung_widerspruch(haltung_id, offen);

-- Machine God drift lock (ICDE hard collapse) - ASCII column names
-- Predicate for unreleased row: (freigegeben_durch IS NULL AND gesperrt_bis > unixepoch('now')*1000)
CREATE TABLE IF NOT EXISTS mg_drift_sperre (
    kanal TEXT NOT NULL,
    grund TEXT NOT NULL,
    gesperrt_bis INTEGER NOT NULL,      -- unix epoch milliseconds
    freigegeben_durch TEXT,             -- NULL = unreleased
    freigegeben_am INTEGER              -- unix epoch milliseconds when released
);

CREATE INDEX IF NOT EXISTS idx_mg_drift_sperre_kanal ON mg_drift_sperre(kanal);

-- View for unreleased drift locks (predicate used by Rust reader in welt.rs/haltung.rs)
CREATE VIEW IF NOT EXISTS mg_drift_sperre_unreleased AS
SELECT kanal, grund, gesperrt_bis
FROM mg_drift_sperre
WHERE freigegeben_durch IS NULL
  AND gesperrt_bis > (unixepoch('now') * 1000);

-- Hook target tables (written by plugin hooks digest, reentry, raum_puls, raum_verlassen)
CREATE TABLE IF NOT EXISTS hook_digest (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kanal TEXT NOT NULL,
    ts REAL NOT NULL,
    inhalt TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hook_digest_kanal_ts ON hook_digest(kanal, ts DESC);

CREATE TABLE IF NOT EXISTS hook_reentry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kanal TEXT NOT NULL,
    ts REAL NOT NULL,
    grund TEXT,
    ergebnis TEXT
);

CREATE INDEX IF NOT EXISTS idx_hook_reentry_kanal_ts ON hook_reentry(kanal, ts DESC);

CREATE TABLE IF NOT EXISTS hook_raum_puls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kanal TEXT NOT NULL,
    ts REAL NOT NULL,
    wert REAL,
    quelle TEXT
);

CREATE INDEX IF NOT EXISTS idx_hook_raum_puls_kanal_ts ON hook_raum_puls(kanal, ts DESC);

CREATE TABLE IF NOT EXISTS hook_raum_verlassen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kanal TEXT NOT NULL,
    ts REAL NOT NULL,
    grund TEXT
);

CREATE INDEX IF NOT EXISTS idx_hook_raum_verlassen_kanal_ts ON hook_raum_verlassen(kanal, ts DESC);
