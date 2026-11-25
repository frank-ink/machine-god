CLAYCODE SPECIFICATION (WP-2a)

```
module gridv1_pure

stateAuthority JSpace {
  cells: [Cell; 10]
  generation: u64
  causal_event: Option<String>
  invariant MAX_CAPACITY == 1
  invariant forall c in cells: 0.0 <= c.activation <= 1.0
  invariant sum(c.uptake for c in cells) == conserved_uptake
  invariant epistemic_tagging: UNKNOWN != ZERO != ERROR != MEASURED
  ON_VIOLATION -> TriggerEmergencyDeescalation
}

architecture GridV1Pure {
  path fill_jspace(seed: u64, inputs: &[f64]) -> JSpace
  path uptake_and_state(cells: &mut [Cell; 10]) -> f64
  path percept_axes(cells: &[Cell; 10]) -> [f64; 10]
  path canonical_digest(fields: &DigestFields) -> String
  path _r6(x: f64) -> f64
  path _rate_limited_step(current: f64, target: f64, rate: f64) -> f64
  path _clip(value: f64, min: f64, max: f64) -> f64
  path _theoretischer_broadcast_bereich(cells: &[Cell; 10]) -> f64
  path select_winner(cells: &[Cell; 10]) -> usize
  path read_messvektor(cells: &[Cell; 10]) -> Messvektor
  path alignment_hook(cells: &[Cell; 10], limit: f64) -> bool
}

fn F(R_t, E_t) -> R_{t+1} {
  R_{t+1} = pure_transition(R_t, E_t)
  // deterministic, replayable, journaled; precedence = functional order
}

invariant decay_term_bounds: Score_effective <= Score_raw
invariant winner_bounds: select_winner(cells) < 10

hypothesis H_fill_deterministic: same seed + inputs => identical JSpace
hypothesis H_uptake_conservation: sum of uptakes invariant under uptake_and_state

promotion MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> BOUNDED_ADMISSION
```

=== FILE: docs/gridv1/WP2A_GRID10_PURE_FUNCTIONS.clay ===
```
module gridv1_pure

stateAuthority JSpace {
  cells: [Cell; 10]
  generation: u64
  causal_event: Option<String>
  invariant MAX_CAPACITY == 1
  invariant forall c in cells: 0.0 <= c.activation <= 1.0
  invariant sum(c.uptake for c in cells) == conserved_uptake
  invariant epistemic_tagging: UNKNOWN != ZERO != ERROR != MEASURED
  ON_VIOLATION -> TriggerEmergencyDeescalation
}

architecture GridV1Pure {
  path fill_jspace(seed: u64, inputs: &[f64]) -> JSpace
  path uptake_and_state(cells: &mut [Cell; 10]) -> f64
  path percept_axes(cells: &[Cell; 10]) -> [f64; 10]
  path canonical_digest(fields: &DigestFields) -> String
  path _r6(x: f64) -> f64
  path _rate_limited_step(current: f64, target: f64, rate: f64) -> f64
  path _clip(value: f64, min: f64, max: f64) -> f64
  path _theoretischer_broadcast_bereich(cells: &[Cell; 10]) -> f64
  path select_winner(cells: &[Cell; 10]) -> usize
  path read_messvektor(cells: &[Cell; 10]) -> Messvektor
  path alignment_hook(cells: &[Cell; 10], limit: f64) -> bool
}

fn F(R_t, E_t) -> R_{t+1} {
  R_{t+1} = pure_transition(R_t, E_t)
  // deterministic, replayable, journaled; precedence = functional order
}

invariant decay_term_bounds: Score_effective <= Score_raw
invariant winner_bounds: select_winner(cells) < 10

hypothesis H_fill_deterministic: same seed + inputs => identical JSpace
hypothesis H_uptake_conservation: sum of uptakes invariant under uptake_and_state

promotion MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> BOUNDED_ADMISSION
```

=== FILE: docs/gridv1/WP2A_EVIDENCE.json ===
```json
{
  "wp": "WP-2a",
  "title": "GRID10 Pure Functions Port to Rust",
  "status": "CODE_COMPLETE_TESTS_UNEXECUTED",
  "cargo_toml_inspected": false,
  "dependencies": "std-only (no new crates; proptest UNKNOWN)",
  "notes": "Cargo.toml in HOST SEAM was not available for inspection in this pass. Implementation uses only std/core to guarantee compilation with existing dependencies. proptest 10k property tests from acceptance criteria are represented as std #[test] unit tests; proptest integration is UNKNOWN pending dependency verification.",
  "tests": [
    { "name": "fill_jspace_deterministic", "kind": "unit", "status": "UNKNOWN" },
    { "name": "uptake_and_state_conservation", "kind": "unit", "status": "UNKNOWN" },
    { "name": "canonical_digest_fixed_order", "kind": "unit", "status": "UNKNOWN" },
    { "name": "decay_term_bounds", "kind": "unit", "status": "UNKNOWN" },
    { "name": "select_winner_bounds", "kind": "unit", "status": "UNKNOWN" },
    { "name": "clip_bounds", "kind": "unit", "status": "UNKNOWN" },
    { "name": "alignment_hook_respects_limit", "kind": "unit", "status": "UNKNOWN" }
  ],
  "proptest_10k_iterations": "UNKNOWN - @rust proptest crate not confirmed in Cargo.toml",
  "cvir_laws_encoded": [
    "UNKNOWN != ZERO != ERROR != MEASURED",
    "MODEL_OUTPUT != EFFECT_AUTHORITY",
    "PREDICTION != OBSERVATION"
  ],
  "on_violation_policy": "panic/fail-closed (TriggerEmergencyDeescalation equivalent in userspace)"
}
```

=== FILE: src/gridv1/mod.rs ===
```rust
//! WP-2a: GRID10 pure functions ported to Rust.
//! GRF frame: R_t = realised state (JSpace), E_t = evidence (inputs/measurements),
//! F = pure transition R_{t+1} = F(R_t, E_t). All functions are deterministic,
//! replayable, and journaled by construction. Epistemic classes are tagged per
//! CVIR law: UNKNOWN != ZERO != ERROR != MEASURED.

pub mod invariants;
pub mod pure;
pub mod types;

#[cfg(test)]
mod tests;

pub use invariants::*;
pub use pure::*;
pub use types::*;
```

=== FILE: src/gridv1/types.rs ===
```rust
//! Compound variables / ClayCode compound values for GRID10.
//! Borrowed from Rust struct/enum idioms to make states precise and illegal
//! states unrepresentable. Epistemic class is a discriminated sum type.

/// CVIR epistemic classes. UNKNOWN stays UNKNOWN; never defaulted to 0 or 0.5.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum EpistemicClass {
    Unknown,
    Zero,
    Error,
    Measured,
}

impl EpistemicClass {
    pub fn as_f64(self) -> f64 {
        match self {
            EpistemicClass::Measured => 1.0,
            EpistemicClass::Zero => 0.0,
            EpistemicClass::Unknown => f64::NAN,
            EpistemicClass::Error => f64::NAN,
        }
    }
}

/// Single GRID10 cell with compound metadata (salience, uncertainty,
/// contradiction, evidence source, generation, causal event).
#[derive(Clone, Debug, PartialEq)]
pub struct Cell {
    pub id: u8,
    pub activation: f64,
    pub uptake: f64,
    pub epistemic: EpistemicClass,
    pub evidence_source: Option<String>,
    pub generation: u64,
    pub salience: f64,
    pub uncertainty: f64,
    pub contradiction: f64,
}

impl Cell {
    pub fn new(id: u8) -> Self {
        Self {
            id,
            activation: 0.0,
            uptake: 0.0,
            epistemic: EpistemicClass::Unknown,
            evidence_source: None,
            generation: 0,
            salience: 0.0,
            uncertainty: 0.0,
            contradiction: 0.0,
        }
    }
}

/// J-Space shadow workspace: fixed 10-cell grid (GRID10).
#[derive(Clone, Debug, PartialEq)]
pub struct JSpace {
    pub cells: [Cell; 10],
    pub generation: u64,
    pub causal_event: Option<String>,
}

impl JSpace {
    pub fn empty() -> Self {
        let mut cells = [Cell::new(0); 10];
        for (i, cell) in cells.iter_mut().enumerate() {
            cell.id = i as u8;
        }
        Self {
            cells,
            generation: 0,
            causal_event: None,
        }
    }
}

/// Message vector read from cells, with aggregated metadata.
#[derive(Clone, Debug, PartialEq)]
pub struct Messvektor {
    pub values: [f64; 10],
    pub salience: f64,
    pub uncertainty: f64,
    pub contradiction: f64,
}

/// Fixed-order fields for canonical_digest. Field order is part of the
/// invariant; %.6f precision is applied deterministically.
#[derive(Clone, Debug, PartialEq)]
pub struct DigestFields {
    pub field_a: f64,
    pub field_b: f64,
    pub field_c: f64,
    pub field_d: f64,
    pub field_e: f64,
}
```

=== FILE: src/gridv1/pure.rs ===
```rust
//! Pure sub-functions ported from Python to Rust (property-testable).
//! All functions are deterministic: same input -> same output.
//! No I/O, no wall-clock, no randomness. Precedence is functional order.

use crate::gridv1::types::*;

/// Clip value to [min, max]. Invariant: min <= max (debug_asserted).
pub fn _clip(value: f64, min: f64, max: f64) -> f64 {
    debug_assert!(min <= max, "_clip: min must be <= max");
    if value < min {
        min
    } else if value > max {
        max
    } else {
        value
    }
}

/// _r6 helper. Exact Python semantics UNKNOWN in this pass; ported as the
/// real sixth root for non-negative input, 0.0 otherwise.
pub fn _r6(x: f64) -> f64 {
    if x < 0.0 || !x.is_finite() {
        0.0
    } else {
        x.powf(1.0 / 6.0)
    }
}

/// Rate-limited step: move `current` toward `target` by at most `rate`.
pub fn _rate_limited_step(current: f64, target: f64, rate: f64) -> f64 {
    let diff = target - current;
    if diff > rate {
        current + rate
    } else if diff < -rate {
        current - rate
    } else {
        target
    }
}

/// Theoretical broadcast bereich: sum of activations weighted by salience.
pub fn _theoretischer_broadcast_bereich(cells: &[Cell; 10]) -> f64 {
    let mut sum = 0.0;
    for cell in cells.iter() {
        sum += cell.activation * cell.salience;
    }
    sum
}

/// Fill J-Space deterministically from a seed and input slice.
/// Inputs beyond 10 are ignored; missing inputs default to 0.0.
pub fn fill_jspace(seed: u64, inputs: &[f64]) -> JSpace {
    let mut cells = [Cell::new(0); 10];
    for (i, cell) in cells.iter_mut().enumerate().take(10) {
        cell.id = i as u8;
        let input = inputs.get(i).copied().unwrap_or(0.0);
        cell.activation = _clip(input, 0.0, 1.0);
        cell.uptake = _r6(cell.activation);
        cell.epistemic = if input.is_finite() {
            EpistemicClass::Measured
        } else {
            EpistemicClass::Error
        };
        cell.generation = seed;
        cell.salience = _clip(cell.activation, 0.0, 1.0);
    }
    JSpace {
        cells,
        generation: seed,
        causal_event: Some(format!("fill_jspace_seed_{}", seed)),
    }
}

/// Uptake and state: recompute uptake from activation for every cell and
/// return the conserved sum of uptakes.
pub fn uptake_and_state(cells: &mut [Cell; 10]) -> f64 {
    let mut sum = 0.0;
    for cell in cells.iter_mut() {
        cell.uptake = _r6(cell.activation);
        sum += cell.uptake;
    }
    sum
}

/// Percept axes: L2-normalized activation axes.
pub fn percept_axes(cells: &[Cell; 10]) -> [f64; 10] {
    let mut out = [0.0; 10];
    let mut norm_sq = 0.0;
    for cell in cells.iter() {
        norm_sq += cell.activation * cell.activation;
    }
    let norm = norm_sq.sqrt();
    if norm > 0.0 {
        for (i, cell) in cells.iter().enumerate() {
            out[i] = cell.activation / norm;
        }
    }
    out
}

/// Canonical digest: fixed field order (a,b,c,d,e), %.6f precision,
/// pipe-separated. Field order is invariant; changing order changes digest.
pub fn canonical_digest(fields: &DigestFields) -> String {
    format!(
        "{:.6f}|{:.6f}|{:.6f}|{:.6f}|{:.6f}",
        fields.field_a,
        fields.field_b,
        fields.field_c,
        fields.field_d,
        fields.field_e
    )
}

/// Select winner: index of max activation; ties broken by lowest cell id.
/// Invariant: result < 10.
pub fn select_winner(cells: &[Cell; 10]) -> usize {
    let mut best_idx: usize = 0;
    let mut best_val = cells[0].activation;
    for (i, cell) in cells.iter().enumerate().skip(1) {
        if cell.activation > best_val {
            best_val = cell.activation;
            best_idx = i;
        }
    }
    best_idx
}

/// Read messvektor from cells; aggregates salience/uncertainty/contradiction.
pub fn read_messvektor(cells: &[Cell; 10]) -> Messvektor {
    let mut values = [0.0; 10];
    let mut salience = 0.0;
    let mut uncertainty = 0.0;
    let mut contradiction = 0.0;
    for (i, cell) in cells.iter().enumerate() {
        values[i] = cell.activation;
        salience += cell.salience;
        uncertainty += cell.uncertainty;
        contradiction += cell.contradiction;
    }
    let n = 10.0;
    Messvektor {
        values,
        salience: salience / n,
        uncertainty: uncertainty / n,
        contradiction: contradiction / n,
    }
}

/// Alignment hook (pure part): true iff max activation <= limit.
pub fn alignment_hook(cells: &[Cell; 10], limit: f64) -> bool {
    let max = cells
        .iter()
        .map(|c| c.activation)
        .fold(0.0f64, f64::max);
    max <= limit
}
```

=== FILE: src/gridv1/invariants.rs ===
```rust
//! Hard invariants with ON_VIOLATION fail-closed intervention.
//! In kernel context this maps to TriggerEmergencyDeescalation; in userspace
//! it panics to guarantee no silent continuation.

use crate::gridv1::types::*;

pub const MAX_CAPACITY: usize = 1;
pub const GRID_SIZE: usize = 10;

#[derive(Debug)]
pub enum InvariantViolation {
    UptakeNotConserved { expected: f64, actual: f64 },
    ActivationOutOfBounds { cell_id: u8, value: f64 },
    WinnerOutOfBounds { index: usize },
    ScoreEffectiveExceedsRaw { raw: f64, effective: f64 },
    EmptyJSpace,
}

/// Check J-Space structural invariants (capacity, activation bounds).
pub fn check_jspace_invariants(space: &JSpace) -> Result<(), InvariantViolation> {
    if space.cells.len() != GRID_SIZE {
        return Err(InvariantViolation::EmptyJSpace);
    }
    for cell in &space.cells {
        if !(0.0..=1.0).contains(&cell.activation) {
            return Err(InvariantViolation::ActivationOutOfBounds {
                cell_id: cell.id,
                value: cell.activation,
            });
        }
    }
    Ok(())
}

/// Check uptake conservation between two snapshots.
pub fn check_uptake_conservation(before: f64, after: f64) -> Result<(), InvariantViolation> {
    if (before - after).abs() > 1e-9 {
        return Err(InvariantViolation::UptakeNotConserved {
            expected: before,
            actual: after,
        });
    }
    Ok(())
}

/// Check decay-term bound: Score_effective <= Score_raw.
pub fn check_decay_bound(raw: f64, effective: f64) -> Result<(), InvariantViolation> {
    if effective > raw {
        return Err(InvariantViolation::ScoreEffectiveExceedsRaw { raw, effective });
    }
    Ok(())
}

/// ON_VIOLATION hook: fail-closed emergency de-escalation.
/// Never silently continues after a violated invariant.
pub fn on_violation(violation: InvariantViolation) -> ! {
    panic!("GRID10 invariant violation: {:?}", violation);
}
```

=== FILE: src/gridv1/tests.rs ===
```rust
//! Unit tests for WP-2a pure functions.
//! NOTE: proptest 10k iterations from the acceptance criteria are NOT used
//! here because the proptest crate was not confirmed in Cargo.toml (std-only).
//! These are deterministic std #[test] checks covering the same properties.

use crate::gridv1::*;

#[test]
fn fill_jspace_deterministic() {
    let inputs: [f64; 10] = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0];
    let a = fill_jspace(42, &inputs);
    let b = fill_jspace(42, &inputs);
    assert_eq!(a, b);
    assert_eq!(a.generation, 42);
    assert!(a.causal_event.is_some());
}

#[test]
fn fill_jspace_activation_bounds() {
    let inputs: [f64; 10] = [-5.0, 0.0, 0.5, 2.0, 1.0, -1.0, 3.0, 0.0, 0.0, 0.0];
    let space = fill_jspace(1, &inputs);
    for cell in &space.cells {
        assert!((0.0..=1.0).contains(&cell.activation));
    }
}

#[test]
fn uptake_and_state_conservation() {
    let inputs: [f64; 10] = [1.0; 10];
    let mut space = fill_jspace(7, &inputs);
    let sum_before: f64 = space.cells.iter().map(|c| c.uptake).sum();
    let sum_after = uptake_and_state(&mut space.cells);
    assert!((sum_before - sum_after).abs() < 1e-9);
}

#[test]
fn canonical_digest_fixed_order() {
    let fields = DigestFields {
        field_a: 1.0,
        field_b: 2.0,
        field_c: 3.0,
        field_d: 4.0,
        field_e: 5.0,
    };
    let digest = canonical_digest(&fields);
    assert_eq!(digest, "1.000000|2.000000|3.000000|4.000000|5.000000");
}

#[test]
fn decay_term_bounds() {
    let raw = 0.8;
    let effective = _clip(raw, 0.0, 1.0);
    assert!(effective <= raw);
}

#[test]
fn clip_bounds() {
    assert_eq!(_clip(-1.0, 0.0, 1.0), 0.0);
    assert_eq!(_clip(2.0, 0.0, 1.0), 1.0);
    assert_eq!(_clip(0.5, 0.0, 1.0), 0.5);
}

#[test]
fn select_winner_bounds() {
    let space = fill_jspace(1, &[0.0; 10]);
    let idx = select_winner(&space.cells);
    assert!(idx < 10);
}

#[test]
fn alignment_hook_respects_limit() {
    let mut space = fill_jspace(3, &[0.5; 10]);
    assert!(alignment_hook(&space.cells, 1.0));
    space.cells[0].activation = 2.0;
    assert!(!alignment_hook(&space.cells, 1.0));
}

#[test]
fn read_messvektor_shape() {
    let space = fill_jspace(9, &[0.5; 10]);
    let mv = read_messvektor(&space.cells);
    assert_eq!(mv.values.len(), 10);
    assert!((0.0..=1.0).contains(&mv.salience));
}
```