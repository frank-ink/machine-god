# unified.db Schema Reference

Regenerated from `zero/unifieddb/schema.sql`. This document is the authoritative reference; any divergence between this file and the SQL source fails the CI gate (see CI Gate: Schema Divergence).

## Delta Table (docs/zero/schema.md vs zero/unifieddb/schema.sql)

| Date | Agent | Source | Delta | Status |
|------|-------|--------|-------|--------|
| 2026-11-24 | r006-t5 | zero/unifieddb/schema.sql | Marked hand-maintained; removed non-SQLite implication check predicate; removed unenforceable cross-table manifest_hash invariant; Healthy-receipt rule expressed against proposed `target_state` column (PLANNED); `failure_count` semantics aligned to `health.ts` (consecutive failed checks including invocation and manifest failures, reset to 0 on Healthy); `manifest_status.plugin_id UNIQUE` added as required delta | PLANNED |
| 2026-11-24 | r007-t2 | zero/unifieddb/schema.sql | Restored truncated `gates` row and all subsequent columns; reinstated CHECK constraints (`status IN`, `approved_by`, `approved_at`, `revoked_at`); added Cross-Table Invariants, CHECK Constraints Summary, HealthStatus compound type; removed stray leading fence; CI divergence gate added | PLANNED |

## Conventions

- **R_t** = realised/persisted state read or owned by a component.
- **E_t** = evidence (measurements, receipts, verified outcomes — never model self-praise).
- **F** = pure transition `R_{t+1} = F(R_t, E_t)`.
- **M** = explicit admissibility space (gates, flags, limits as one structure).
- **L** = `c * h` ethically/causally weighted loss.
- Epistemic classes: `UNKNOWN != ZERO != ERROR != MEASURED`. Unknown stays unknown; it is never coerced to `0`, `0.5`, or `''`.
- **Epistemic Status Column**: Every column documents its epistemic classification: `MEASURED` (directly observed/verified), `HYPOTHESIS` (derived/estimated/uncalibrated), `UNKNOWN` (not yet measured), `COMPUTED` (deterministically derived from other columns).

## Tables

### schema_migrations

Tracks applied schema migrations.

| Column | Type | Constraints | Epistemic Status | Description |
|--------|------|-------------|------------------|-------------|
| version | TEXT | PK, NOT NULL | MEASURED | Migration version identifier |
| applied_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | MEASURED | Timestamp when migration was applied |

Invariant: migrations are append-only; `version` is unique by virtue of PK.

### identity

Root identity / key material for the Zero entity.

| Column | Type | Constraints | Epistemic Status | Description |
|--------|------|-------------|------------------|-------------|
| root_id | UUID | PK, NOT NULL | MEASURED | Canonical root identifier |
| public_key_pem | TEXT | NOT NULL | MEASURED | PEM-encoded public key |
| fingerprint_sha256 | TEXT | NOT NULL, UNIQUE | MEASURED | SHA-256 fingerprint of the public key |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | MEASURED | Creation timestamp |
| rotated_at | TIMESTAMPTZ | | MEASURED | Last key rotation timestamp |
| revoked | BOOLEAN | NOT NULL, DEFAULT FALSE | MEASURED | Revocation flag |

Invariant: `fingerprint_sha256` is UNIQUE; a revoked identity must not be used for new state authority.

### plugins

Bundled plugin registry (e.g. FranKenstein 3.0 organs).

| Column | Type | Constraints | Epistemic Status | Description |
|--------|------|-------------|------------------|-------------|
| id | UUID | PK, NOT NULL | MEASURED | Plugin instance identifier |
| name | TEXT | NOT NULL | MEASURED | Human-readable plugin name |
| manifest_path | TEXT | NOT NULL | MEASURED | Relative path to plugin manifest (no hard-coded /home paths) |
| version | TEXT | NOT NULL | MEASURED | Plugin semantic version |
| status | TEXT | NOT NULL, DEFAULT 'unknown', CHECK (status IN ('healthy','degraded','unhealthy','unknown')) | MEASURED | Lifecycle status aligned with TS HealthStatus.status |
| failure_count | INTEGER | NOT NULL, DEFAULT 0, CHECK (failure_count >= 0) | MEASURED | Consecutive failed health checks including invocation and manifest failures; resets to 0 on Healthy transition |
| health_score | REAL | CHECK (health_score IS NULL OR (health_score >= 0.0 AND health_score <= 1.0)) | MEASURED | Last measured health score (0.0–1.0) |
| last_check_at | TIMESTAMPTZ | | MEASURED | Timestamp of last health check |
| manifest_hash | TEXT | NOT NULL | MEASURED | Hash of the manifest file at load time |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | MEASURED | Last row update timestamp |

Invariant: `health_score`, when present, must be in [0.0, 1.0].
Invariant: `status` vocabulary matches TS `HealthStatus.status` union (`healthy | degraded | unhealthy | unknown`); `failed` removed — use `unhealthy` with `failure_count > 0`.
Invariant: `failure_count` increments on each failed check (invocation or manifest) and resets to 0 on `healthy` transition.

### manifest_status

Manifest-level health and validation tracking (separate from plugin runtime health).

| Column | Type | Constraints | Epistemic Status | Description |
|--------|------|-------------|------------------|-------------|
| id | UUID | PK, NOT NULL | MEASURED | Manifest status record identifier |
| plugin_id | UUID | NOT NULL, FK -> plugins(id), UNIQUE | MEASURED | Owning plugin |
| manifest_path | TEXT | NOT NULL | MEASURED | Path to manifest file |
| manifest_hash | TEXT | NOT NULL | MEASURED | Current hash of manifest file |
| validation_status | TEXT | NOT NULL, DEFAULT 'unknown', CHECK (validation_status IN ('valid','invalid','unknown','stale')) | MEASURED | Manifest schema validation result |
| validation_error | TEXT | | MEASURED | Error message if validation_status = 'invalid' |
| capability_count | INTEGER | NOT NULL, DEFAULT 0, CHECK (capability_count >= 0) | MEASURED | Number of declared capabilities |
| required_capability_count | INTEGER | NOT NULL, DEFAULT 0, CHECK (required_capability_count >= 0) | MEASURED | Number of required capabilities |
| last_validated_at | TIMESTAMPTZ | | MEASURED | Timestamp of last validation |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | MEASURED | Record creation timestamp |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | MEASURED | Last update timestamp |

Invariant: `validation_status = 'valid'` implies all required capabilities are satisfied.
Invariant: `stale` means manifest file mtime > `last_validated_at`.
Required delta: `manifest_status.plugin_id UNIQUE` (1:1 enforcement with `plugins`).

### organs

Organ instances belonging to a plugin.

| Column | Type | Constraints | Epistemic Status | Description |
|--------|------|-------------|------------------|-------------|
| id | UUID | PK, NOT NULL | MEASURED | Organ instance identifier |
| plugin_id | UUID | NOT NULL, FK -> plugins(id) | MEASURED | Owning plugin |
| name | TEXT | NOT NULL | MEASURED | Organ name |
| organ_type | TEXT | NOT NULL | MEASURED | Organ class (hook, grid, stern, star, etc.) |
| status | TEXT | NOT NULL, DEFAULT 'idle', CHECK (status IN ('idle','running','degraded','unhealthy','stopped')) | MEASURED | Lifecycle status |
| health_score | REAL | CHECK (health_score IS NULL OR (health_score >= 0.0 AND health_score <= 1.0)) | MEASURED | Last measured health score (0.0–1.0) |
| capacity_max | INTEGER | NOT NULL, DEFAULT 1, CHECK (capacity_max = 1) | MEASURED | Hard capacity limit (CLAYCODE MAX_CAPACITY = 1) |
| load_current | INTEGER | NOT NULL, DEFAULT 0, CHECK (load_current >= 0 AND load_current <= capacity_max) | MEASURED | Current load; must not exceed capacity_max |
| failure_count | INTEGER | NOT NULL, DEFAULT 0, CHECK (failure_count >= 0) | MEASURED | Consecutive organ health check failures |
| last_check_at | TIMESTAMPTZ | | MEASURED | Timestamp of last health check |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | MEASURED | Creation timestamp |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | MEASURED | Last update timestamp |

Invariant: `load_current <= capacity_max` (ON_VIOLATION -> TriggerEmergencyDeescalation); `capacity_max` is semantically fixed at 1.
Invariant: `failure_count` increments on each failed organ health check; resets to 0 on healthy transition.

### ziele

Measured goals table. Column epistemic tags and query examples live in `docs/zero/ziele.md`.

| Column | Type | Constraints | Epistemic Status | Description |
|--------|------|-------------|------------------|-------------|
| id | UUID | PK, NOT NULL | MEASURED | Goal identifier |
| name | TEXT | NOT NULL | MEASURED | Goal name |
| description | TEXT | | MEASURED | Free-text description |
| domain | TEXT | NOT NULL | MEASURED | Goal domain |
| target_value | REAL | NOT NULL | HYPOTHESIS | Target value (set at goal creation, not measured) |
| measured_value | REAL | | MEASURED | Last measured value (NULL = not yet measured) |
| unit | TEXT | NOT NULL | MEASURED | Unit of measurement |
| epistemic_status | TEXT | NOT NULL, CHECK (epistemic_status IN ('MEASURED','HYPOTHESIS','UNKNOWN')) | MEASURED | Epistemic classification of measured_value |
| confidence | REAL | CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)) | HYPOTHESIS | Uncalibrated confidence (HYPOTHESIS, != truth) |
| baseline_value | REAL | | MEASURED | Reference value before intervention |
| delta | REAL | | COMPUTED | Derived: measured_value - baseline_value |
| gate_passed | BOOLEAN | NOT NULL, DEFAULT FALSE | MEASURED | Gate result |
| verified_by | TEXT | | MEASURED | Principal who performed verification |
| verified_at | TIMESTAMPTZ | | MEASURED | Verification timestamp |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | MEASURED | Creation timestamp |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | MEASURED | Last update timestamp |
| decay_factor | REAL | NOT NULL, DEFAULT 0.0, CHECK (decay_factor >= 0.0 AND decay_factor <= 1.0) | HYPOTHESIS | Recency decay alpha (HYPOTHESIS) |
| score_effective | REAL | | COMPUTED | Derived effective score: measured_value * (1 - decay_factor * recency) |
| gate_name | TEXT | | MEASURED | Name of the verification gate |
| gate_status | TEXT | CHECK (gate_status IN ('passed','failed','pending')) | MEASURED | Gate evaluation status |
| measured_at | TIMESTAMPTZ | | MEASURED | Timestamp when gate was measured (functional tick time) |
| evidence_ref | TEXT | | MEASURED | External receipt or hash for gate evidence |

Invariant: `epistemic_status` is one of the three tags; `delta` and `score_effective` are derived fields, never directly written.
Invariant: `gate_status` vocabulary aligns with gate evaluation protocol; `measured_at` records functional tick time, not wall-clock.
Invariant: `target_value` is HYPOTHESIS (intent), `measured_value` is MEASURED (evidence).

### measurements

Raw evidence records (E_t).

| Column | Type | Constraints | Epistemic Status | Description |
|--------|------|-------------|------------------|-------------|
| id | UUID | PK, NOT NULL | MEASURED | Measurement identifier |
| source_table | TEXT | NOT NULL | MEASURED | Table the measurement refers to |
| source_column | TEXT | NOT NULL | MEASURED | Column the measurement refers to |
| source_row_id | UUID | NOT NULL | MEASURED | Row identifier in source table |
| value | REAL | NOT NULL | MEASURED | Measured value |
| method | TEXT | NOT NULL | MEASURED | Measurement method name |
| ts | TIMESTAMPTZ | NOT NULL, DEFAULT now() | MEASURED | Measurement timestamp |
| evidence_ref | TEXT | | MEASURED | External receipt or hash |
| uncertainty | REAL | CHECK (uncertainty IS NULL OR uncertainty >= 0.0) | HYPOTHESIS | Estimated uncertainty (HYPOTHESIS unless calibrated) |

Invariant: every measurement must have a `method`; `method` is not a truth claim.
Invariant: `uncertainty` is HYPOTHESIS unless separately calibrated and admitted.

### state_transitions

Journal of R_t -> R_{t+1} transitions (F).

| Column | Type | Constraints | Epistemic Status | Description |
|--------|------|-------------|------------------|-------------|
| id | UUID | PK, NOT NULL | MEASURED | Transition identifier |
| tick | BIGINT | NOT NULL, UNIQUE | MEASURED | Functional tick order (precedence, not wall-clock) |
| r_t_hash | TEXT | NOT NULL | MEASURED | Hash of realised state before transition |
| e_t_hash | TEXT | NOT NULL | MEASURED | Hash of evidence consumed |
| r_t1_hash | TEXT | NOT NULL | MEASURED | Hash of realised state after transition |
| transition_fn | TEXT | NOT NULL | MEASURED | Name of the pure function F applied |
| duration_ms | INTEGER | NOT NULL, CHECK (duration_ms >= 0) | MEASURED | Transition duration |
| journal_ref | TEXT | | MEASURED | Append-only journal reference |
| health_check_receipt_ref | TEXT | | MEASURED | Reference to health check receipt (required for healthy transitions) |
| target_state | TEXT | | PLANNED | Proposed target state of the transition (e.g. 'healthy'); not present in zero/unifieddb/schema.sql this round |

Invariant: `tick` is strictly monotonic; transitions are journaled before being applied (write-ahead).
Invariant: PLANNED `target_state`: when `target_state = 'healthy'`, `health_check_receipt_ref` must not be NULL. Expressed as a documentation rule; not enforced by SQLite until the column is added to zero/unifieddb/schema.sql.

### cvir_packets

Causal verification packets (CVIR).

| Column | Type | Constraints | Epistemic Status | Description |
|--------|------|-------------|------------------|-------------|
| id | UUID | PK, NOT NULL | MEASURED | Packet identifier |
| hypothesis_id | UUID | NOT NULL, FK -> ziele(id) | MEASURED | Related goal/hypothesis |
| evidence_ref | TEXT | NOT NULL | MEASURED | Reference to supporting evidence |
| promotion_level | TEXT | NOT NULL, CHECK (promotion_level IN ('MEASURE','FALSIFY','MATCHED_ABLATION','VERIFIED_OUTCOME','CAUSAL_CREDIT','BOUNDED_ADMISSION','REENTRY_TEST','CONTROL_INFLUENCE')) | MEASURED | Current rung |
| status | TEXT | NOT NULL, DEFAULT 'open', CHECK (status IN ('open','verified','rejected','archived')) | MEASURED | Packet status |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | MEASURED | Creation timestamp |
| verified_at | TIMESTAMPTZ | | MEASURED | Verification timestamp |

Invariant: `promotion_level` advances only one rung at a time; CVIR_PACKET != RUNTIME_CAUSAL_PROOF.

### gates (austritt)

Exit gates for secrets and sensitive paths.

| Column | Type | Constraints | Epistemic Status | Description |
|--------|------|-------------|------------------|-------------|
| id | UUID | PK, NOT NULL | MEASURED | Gate identifier |
| secret_type | TEXT | NOT NULL | MEASURED | Type of secret or path |
| path_pattern | TEXT | NOT NULL | MEASURED | Glob/regex pattern for guarded paths |
| status | TEXT | NOT NULL, CHECK (status IN ('open','closed','armed','bypassed')) | MEASURED | Gate state |
| approved_by | TEXT | | MEASURED | Principal who approved the gate opening |
| approved_at | TIMESTAMPTZ | | MEASURED | Timestamp when the gate was approved |
| revoked_at | TIMESTAMPTZ | | MEASURED | Timestamp when the gate was revoked |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | MEASURED | Creation timestamp |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | MEASURED | Last update timestamp |

Invariant: `status` vocabulary is closed; `approved_at` is NULL unless the gate has been approved; `revoked_at` implies `status = 'closed'`.

## Cross-Table Invariants

- **UNKNOWN never defaulted**: no column of epistemic class `UNKNOWN` may carry `DEFAULT 0`, `DEFAULT 0.5`, or `DEFAULT ''`; unknown stays `NULL` or an explicit `UNKNOWN` marker and is never coerced.
- **capacity_max = 1**: `organs.capacity_max` is semantically fixed at 1 (CLAYCODE `MAX_CAPACITY = 1`); `organs.load_current <= organs.capacity_max` (ON_VIOLATION -> TriggerEmergencyDeescalation).
- **tick-order precedence**: `state_transitions.tick` is strictly monotonic and encodes functional precedence, not wall-clock time; transitions are journaled before being applied (write-ahead).
- **write-ahead**: every `state_transitions` row is inserted into the journal before the corresponding state mutation becomes visible; no transition exists without a journal row.
- **healthy-receipt**: when `state_transitions.target_state = 'healthy'`, `state_transitions.health_check_receipt_ref` must not be NULL.

## CHECK Constraints Summary

| Table | Column | Constraint | Epistemic Status |
|-------|--------|------------|------------------|
| plugins | status | CHECK (status IN ('healthy','degraded','unhealthy','unknown')) | MEASURED |
| plugins | failure_count | CHECK (failure_count >= 0) | MEASURED |
| plugins | health_score | CHECK (health_score IS NULL OR (health_score >= 0.0 AND health_score <= 1.0)) | MEASURED |
| manifest_status | validation_status | CHECK (validation_status IN ('valid','invalid','unknown','stale')) | MEASURED |
| manifest_status | capability_count | CHECK (capability_count >= 0) | MEASURED |
| manifest_status | required_capability_count | CHECK (required_capability_count >= 0) | MEASURED |
| organs | status | CHECK (status IN ('idle','running','degraded','unhealthy','stopped')) | MEASURED |
| organs | health_score | CHECK (health_score IS NULL OR (health_score >= 0.0 AND health_score <= 1.0)) | MEASURED |
| organs | capacity_max | CHECK (capacity_max = 1) | MEASURED |
| organs | load_current | CHECK (load_current >= 0 AND load_current <= capacity_max) | MEASURED |
| organs | failure_count | CHECK (failure_count >= 0) | MEASURED |
| ziele | epistemic_status | CHECK (epistemic_status IN ('MEASURED','HYPOTHESIS','UNKNOWN')) | MEASURED |
| ziele | confidence | CHECK (confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)) | HYPOTHESIS |
| ziele | decay_factor | CHECK (decay_factor >= 0.0 AND decay_factor <= 1.0) | HYPOTHESIS |
| ziele | gate_status | CHECK (gate_status IN ('passed','failed','pending')) | MEASURED |
| measurements | uncertainty | CHECK (uncertainty IS NULL OR uncertainty >= 0.0) | HYPOTHESIS |
| state_transitions | duration_ms | CHECK (duration_ms >= 0) | MEASURED |
| cvir_packets | promotion_level | CHECK (promotion_level IN ('MEASURE','FALSIFY','MATCHED_ABLATION','VERIFIED_OUTCOME','CAUSAL_CREDIT','BOUNDED_ADMISSION','REENTRY_TEST','CONTROL_INFLUENCE')) | MEASURED |
| cvir_packets | status | CHECK (status IN ('open','verified','rejected','archived')) | MEASURED |
| gates | status | CHECK (status IN ('open','closed','armed','bypassed')) | MEASURED |

## HealthStatus Compound Type

```claycode
module zero.schema.health

compound HealthStatus {
  status:       enum { healthy, degraded, unhealthy, unknown }
  score:        option<f64>          // [0.0, 1.0], MEASURED; None == UNKNOWN
  failure_count: u32                 // >= 0, MEASURED
  last_check:   option<datetime>     // MEASURED
  reason:       option<string>       // MEASURED
  source:       string               // plugin | organ | grid | retina | omnipool
}

invariant HealthStatus.score_range:
  score.is_some() ==> (0.0 <= score.unwrap() && score.unwrap() <= 1.0)
  ON_VIOLATION -> TriggerEmergencyDeescalation

invariant HealthStatus.unknown_not_zero:
  status == unknown ==> score == None
  ON_VIOLATION -> TriggerEmergencyDeescalation

invariant HealthStatus.failure_zero_on_healthy:
  status == healthy ==> failure_count == 0
  ON_VIOLATION -> TriggerEmergencyDeescalation

fn from_row(row) -> HealthStatus { ... }
```

## CI Gate: Schema Divergence

`docs/zero/schema.md` is regenerated from `zero/unifieddb/schema.sql`. Any divergence between this document and the SQL source fails the CI gate. The reference is produced by a script that parses `zero/unifieddb/schema.sql` and compares column names, types, constraints, and epistemic labels row-by-row. Zero drift is required.
