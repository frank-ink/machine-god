-- grid10 local schema (additive, IF NOT EXISTS only). Written for this install
-- from the donor fixtures (f2wp1207_p10_p6d_fallback_test.py SCHEMA_SQL,
-- test_omega_grf_turn_forensics.py) + FK targets named in
-- f2wp1207_grid10_schema_reference.sql. The donor identity-layer DDL
-- (entity/installation/state_root/host_binding) is NOT in the donor repo:
-- the 4 identity tables below are a minimal local reconstruction. UNBELEGT
-- vs the original machine's identity layer.
CREATE TABLE IF NOT EXISTS f2_entity_identity (
    entity_id TEXT PRIMARY KEY, label TEXT NOT NULL, owner TEXT NOT NULL,
    created_at TEXT NOT NULL, schema TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS f2_installation_identity (
    installation_id TEXT PRIMARY KEY, entity_id TEXT NOT NULL REFERENCES f2_entity_identity(entity_id),
    install_ref TEXT NOT NULL, created_at TEXT NOT NULL, schema TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS f2_state_root_identity (
    state_root_id TEXT PRIMARY KEY, installation_id TEXT NOT NULL REFERENCES f2_installation_identity(installation_id),
    root_ref TEXT NOT NULL, created_at TEXT NOT NULL, schema TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS f2_host_binding (
    binding_id TEXT PRIMARY KEY, installation_id TEXT NOT NULL, host_ref TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL, schema TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS f2_runtime_epoch (
    runtime_epoch_id TEXT PRIMARY KEY, state_root_id TEXT NOT NULL, installation_id TEXT NOT NULL,
    host_binding_id TEXT NOT NULL, started_at TEXT NOT NULL, predecessor_epoch_id TEXT,
    termination_reason TEXT, schema TEXT NOT NULL, session_id TEXT, boot_id TEXT, ended_at TEXT,
    termination_evidence TEXT, successor_epoch_id TEXT, confidence REAL);
CREATE TABLE IF NOT EXISTS f2_reentry_record (
    reentry_id TEXT PRIMARY KEY, entity_id TEXT, installation_id TEXT NOT NULL, state_root_id TEXT NOT NULL,
    predecessor_epoch_id TEXT, successor_epoch_id TEXT NOT NULL, predecessor_termination_reason TEXT,
    predecessor_confidence REAL, predecessor_boot_id TEXT, successor_boot_id TEXT,
    last_grid10_frame_id TEXT, last_work_ref TEXT, created_at TEXT NOT NULL, schema TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS f2_grid10_frame (
    frame_id TEXT PRIMARY KEY, entity_id TEXT NOT NULL, installation_id TEXT NOT NULL,
    state_root_id TEXT NOT NULL, runtime_epoch_id TEXT NOT NULL, session_id TEXT NOT NULL,
    turn_event_id TEXT NOT NULL, opened_at TEXT NOT NULL, closed_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('OPEN','CLOSED','FAILED')), schema TEXT NOT NULL,
    cohort TEXT NOT NULL DEFAULT 'ORGANIC', broadcast_winner_cell TEXT, broadcast_value REAL,
    experiment_condition TEXT, state_weight REAL, UNIQUE (runtime_epoch_id, turn_event_id));
CREATE INDEX IF NOT EXISTS ix_f2_grid10_frame_epoch ON f2_grid10_frame (runtime_epoch_id);
CREATE INDEX IF NOT EXISTS ix_f2_grid10_frame_installation ON f2_grid10_frame (installation_id);
CREATE TABLE IF NOT EXISTS f2_grid10_cell_state (
    installation_id TEXT NOT NULL,
    logical_cell_id TEXT NOT NULL CHECK (logical_cell_id IN ('G1','G2','G3','G4','G5','G6','G7','G8','G9','G10')),
    state_value REAL NOT NULL DEFAULT 0.0, updated_at TEXT NOT NULL, updated_by_frame_id TEXT,
    won_broadcast_count INTEGER NOT NULL DEFAULT 0, schema TEXT NOT NULL,
    PRIMARY KEY (installation_id, logical_cell_id));
CREATE TABLE IF NOT EXISTS f2_grid10_p6d_state (
    condition_key TEXT NOT NULL,
    logical_cell_id TEXT NOT NULL CHECK (logical_cell_id IN ('G1','G2','G3','G4','G5','G6','G7','G8','G9','G10')),
    state_value REAL NOT NULL DEFAULT 0.0, updated_at TEXT NOT NULL, updated_by_frame_id TEXT,
    won_broadcast_count INTEGER NOT NULL DEFAULT 0, schema TEXT NOT NULL,
    PRIMARY KEY (condition_key, logical_cell_id));
CREATE TABLE IF NOT EXISTS f2_grid10_cell_observation (
    observation_id TEXT PRIMARY KEY, frame_id TEXT NOT NULL,
    logical_cell_id TEXT NOT NULL CHECK (logical_cell_id IN ('G1','G2','G3','G4','G5','G6','G7','G8','G9','G10')),
    input_digest_sha256 TEXT, output_digest_sha256 TEXT, uptake INTEGER NOT NULL DEFAULT 0,
    reentry_flag INTEGER NOT NULL DEFAULT 0, conflict_flag INTEGER NOT NULL DEFAULT 0,
    timing_ms REAL, cpu_ru_utime_delta_s REAL, rss_delta_kb INTEGER, predecessor_observation_id TEXT,
    schema TEXT NOT NULL, execution_position INTEGER, UNIQUE (frame_id, logical_cell_id));
CREATE INDEX IF NOT EXISTS ix_f2_grid10_cell_obs_frame ON f2_grid10_cell_observation (frame_id);
