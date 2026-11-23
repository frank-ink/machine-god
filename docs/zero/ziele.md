# ZIELE — Measured Goals Table

Source: `zero/ZIELE.md` (measured goals definition) and `zero/unifieddb/schema.sql`.

## Purpose

`ziele` holds the measured goals of the Zero entity. Each row is a goal with a target value, a last measured value, and an explicit epistemic status. Progress is only what a gate MEASURED.

## Epistemic Tags

| Tag | Meaning |
|-----|---------|
| MEASURED | Value obtained by instrumented observation or gate result. |
| HYPOTHESIS | Uncalibrated estimate, model confidence, salience, or derived assumption. Not truth. |
| UNKNOWN | No measurement available. Stays UNKNOWN; never defaulted to `0`, `0.5`, or `''`. |

## Column Reference

| Column | Type | Constraints | Epistemic Tag | Description |
|--------|------|-------------|---------------|-------------|
| id | UUID | PK, NOT NULL | MEASURED | Generated goal identifier. |
| name | TEXT | NOT NULL | MEASURED | Human-readable goal name. |
| description | TEXT | | UNKNOWN | Free-text description; not machine-measured. |
| domain | TEXT | NOT NULL | MEASURED | Goal domain (identity, plugin, organ, measurement, gate, etc.). |
| target_value | REAL | NOT NULL | MEASURED | Target value to reach. |
| measured_value | REAL | | MEASURED | Last measured value. `NULL` means not yet measured (UNKNOWN measurement). |
| unit | TEXT | NOT NULL | MEASURED | Unit of measurement. |
| epistemic_status | TEXT | NOT NULL, CHECK (...) | MEASURED | Classification assigned by the promotion gate. |
| confidence | REAL | | HYPOTHESIS | Model or judge confidence. Confidence != truth. |
| baseline_value | REAL | | MEASURED | Reference value before intervention. |
| delta | REAL | | MEASURED | Derived: `measured_value - baseline_value`. |
| gate_passed | BOOLEAN | NOT NULL, DEFAULT FALSE | MEASURED | Gate result (pass/fail). |
| verified_by | TEXT | | UNKNOWN | Principal who performed verification. |
| verified_at | TIMESTAMPTZ | | MEASURED | Verification timestamp. |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | MEASURED | Creation timestamp. |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | MEASURED | Last update timestamp. |
| decay_factor | REAL | NOT NULL, DEFAULT 0.0 | HYPOTHESIS | Recency decay alpha (`Score_effective = Score_raw * (1 - alpha * Recency)`). |
| score_effective | REAL | | MEASURED | Derived effective score after decay. |

## Invariants

1. `epistemic_status` must be exactly one of `MEASURED`, `HYPOTHESIS`, `UNKNOWN`.
2. `measured_value IS NULL` does **not** mean `0`; it means the measurement has not been performed (UNKNOWN).
3. `confidence` is HYPOTHESIS; it is never interpreted as truth probability unless separately calibrated and admitted.
4. `delta` and `score_effective` are derived columns; they are computed, never directly written.
5. `gate_passed = TRUE` requires a corresponding `verified_at` and `verified_by` (or the row is rejected by the gate).
6. Promotion ladder: nothing skips a rung — `MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> CAUSAL_CREDIT -> BOUNDED_ADMISSION -> REENTRY_TEST -> CONTROL_INFLUENCE`.

## Query Examples

### 1. List goals whose measurement is still UNKNOWN

```sql
SELECT id, name, domain, measured_value, epistemic_status
FROM ziele
WHERE epistemic_status = 'UNKNOWN'
   OR measured_value IS NULL
ORDER BY created_at;
```

### 2. Goals that passed the gate, ordered by effective score

```sql
SELECT id, name, target_value, measured_value, score_effective, gate_passed
FROM ziele
WHERE gate_passed = TRUE
ORDER BY score_effective DESC NULLS LAST
LIMIT 20;
```

### 3. Compute delta for all measured goals

```sql
SELECT id, name, baseline_value, measured_value,
       (measured_value - baseline_value) AS delta
FROM ziele
WHERE measured_value IS NOT NULL
  AND baseline_value IS NOT NULL;
```

### 4. Hypotheses with high confidence (not truth)

```sql
SELECT id, name, confidence, epistemic_status
FROM ziele
WHERE epistemic_status = 'HYPOTHESIS'
  AND confidence > 0.5;
-- NOTE: confidence > 0.5 does not imply the goal is true.
```

### 5. Goals due for re-evaluation (decay-aware)

```sql
SELECT id, name, score_effective, decay_factor, updated_at
FROM ziele
WHERE decay_factor > 0
ORDER BY score_effective ASC
LIMIT 10;
```

### 6. Promotion ladder audit

```sql
SELECT id, name, epistemic_status, gate_passed, verified_at
FROM ziele
WHERE epistemic_status IN ('CAUSAL_CREDIT', 'BOUNDED_ADMISSION', 'CONTROL_INFLUENCE');
-- These statuses must have a complete CVIR packet chain; no rung may be skipped.
```

## Promotion Example

A goal starts at `epistemic_status = 'MEASURED'` after the first instrumented observation. To advance:

```sql
-- Pseudo-SQL; the actual transition is mediated by the gate service, not raw UPDATE
UPDATE ziele
SET epistemic_status = 'FALSIFY',
    updated_at = now()
WHERE id = '<goal-id>'
  AND epistemic_status = 'MEASURED'
  AND EXISTS (
    SELECT 1 FROM cvir_packets
    WHERE hypothesis_id = ziele.id
      AND promotion_level = 'MEASURE'
  );
```

No `UPDATE` may jump from `MEASURED` to `CONTROL_INFLUENCE` in a single step.
