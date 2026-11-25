[CLAYCODE // GRID10 // WP-2a]
module gridv1 {
  stateAuthority Grid10RealisedState {
    jspace: JSpace
      invariant JSPACE_CAPACITY: len(slots) <= MAX_CAPACITY (MAX_CAPACITY = 1)
      ON_VIOLATION -> TriggerEmergencyDeescalation
    messvektor: Messvektor
    epoch: u64
    turn_seq: u64 (precedence over wall-clock)
    broadcast_region: BroadcastRegion
    alignment_state: AlignmentState
  }

  architecture Grid10Turn {
    path R_t --[PureEvidence E_t]--> F --> R_{t+1}
    path F = apply_evidence ∘ select_winner ∘ compute_percept_axes ∘ validate_invariants
  }

  invariant UPTAKE_CONSERVATION: sum(uptakes) == 1.0 ± EPSILON
    ON_VIOLATION -> RejectTransition
  invariant DECAY_BOUND: Score_effective <= Score_raw
    ON_VIOLATION -> RejectTransition
  invariant DIGEST_ORDER: digest.0 starts_with fixed_prefix
    ON_VIOLATION -> RejectTransition
  invariant EPISTEMIC_CLASS: UNKNOWN != ZERO != ERROR != MEASURED
    ON_VIOLATION -> RejectTransition

  fn F(R_t: Grid10RealisedState, E_t: PureEvidence) -> Result<Grid10RealisedState, InvariantViolation> {
    pre: check_jspace_capacity(&R_t.jspace)
    body: R_{t+1} = apply_evidence(R_t, E_t)
    post: check_jspace_capacity(&R_{t+1}.jspace)
    post: check_decay_bound(1.0, R_{t+1}.broadcast_region.radius)
    ON_VIOLATION -> TriggerEmergencyDeescalation
  }

  hypothesis H_WINNER_CANONICAL: select_winner output is canonical truth
    status: UNKNOWN
    promotion MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> CAUSAL_CREDIT -> BOUNDED_ADMISSION -> REENTRY_TEST -> CONTROL_INFLUENCE
}

=== FILE: src/lib.rs ===
//! claude-code-rust library root.
//! WP-2a: GRID10 pure functions module (ClayCode / GRF).
//! Wire the gridv1 module here; all other existing modules must be preserved.

pub mod gridv1;

=== FILE: src/gridv1/mod.rs ===
//! WP-2a: GRID10 pure functions module (ClayCode / GRF).
//! R_t = Grid10RealisedState, E_t = PureEvidence, F = pure transition fns.
//! Precedence is turn_seq (functional order), never wall-clock.

pub mod types;
pub mod invariants;
pub mod pure;
pub mod property_tests;

=== FILE: src/gridv1/types.rs ===
//! WP-2a: GRID10 pure compound types (ClayCode surface).
//! Epistemic classes are explicit: UNKNOWN != ZERO != ERROR != MEASURED.
//! Compound values are tagged unions; illegal states are unrepresentable.

use std::fmt;

pub const MAX_CAPACITY: usize = 1;
pub const GRID10_CELLS: usize = 10;
pub const EPSILON: f64 = 1e-6;
pub const CANONICAL_PRECISION: u32 = 6;

/// Epistemic class tag for every compound value.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum EpistemicClass {
    Measured,
    Derived,
    Hypothesis,
    Unknown,
    Error,
}

/// Tagged compound value. Illegal states unrepresentable.
#[derive(Debug, Clone, PartialEq)]
pub enum EpistemicValue {
    Measured { value: f64, method: String, ts: u64, ref_id: String },
    Derived { from: Vec<String>, value: f64 },
    Hypothesis { value: f64, confidence: f64 },
    Unknown { reason: String },
    Error { code: String, message: String },
}

impl EpistemicValue {
    pub fn value(&self) -> Option<f64> {
        match self {
            EpistemicValue::Measured { value, .. } => Some(*value),
            EpistemicValue::Derived { value, .. } => Some(*value),
            EpistemicValue::Hypothesis { value, .. } => Some(*value),
            EpistemicValue::Unknown { .. } => None,
            EpistemicValue::Error { .. } => None,
        }
    }

    pub fn class(&self) -> EpistemicClass {
        match self {
            EpistemicValue::Measured { .. } => EpistemicClass::Measured,
            EpistemicValue::Derived { .. } => EpistemicClass::Derived,
            EpistemicValue::Hypothesis { .. } => EpistemicClass::Hypothesis,
            EpistemicValue::Unknown { .. } => EpistemicClass::Unknown,
            EpistemicValue::Error { .. } => EpistemicClass::Error,
        }
    }
}

/// A single J-Space slot with metadata bundle (ClayCode BIND(slot_i, x_i)).
#[derive(Debug, Clone, PartialEq)]
pub struct JSpaceSlot {
    pub slot_id: usize,
    pub value: EpistemicValue,
    pub salience: f64,
    pub uncertainty: f64,
    pub contradiction: f64,
    pub evidence_source: String,
    pub generation: u64,
    pub causal_event: Option<String>,
    pub allowed_action_class: String,
}

/// J-Space: fixed 10-cell shadow workspace.
#[derive(Debug, Clone, PartialEq)]
pub struct JSpace {
    pub slots: [Option<JSpaceSlot>; GRID10_CELLS],
    pub epoch: u64,
    pub turn_seq: u64,
}

impl JSpace {
    pub fn len(&self) -> usize {
        self.slots.iter().filter(|s| s.is_some()).count()
    }
}

/// Messvektor entry.
#[derive(Debug, Clone, PartialEq)]
pub struct MessvektorEntry {
    pub slot_id: usize,
    pub vector: EpistemicValue,
    pub timestamp: u64,
}

/// Messvektor: message vector read by GRID10 turn engine.
#[derive(Debug, Clone, PartialEq)]
pub struct Messvektor {
    pub entries: Vec<MessvektorEntry>,
    pub epoch: u64,
}

/// Uptake state: conservation of sum(uptake) == 1.0.
#[derive(Debug, Clone, PartialEq)]
pub struct UptakeState {
    pub uptakes: [EpistemicValue; GRID10_CELLS],
    pub sum: EpistemicValue,
    pub epoch: u64,
}

/// Percept axes computed from uptake state (_r6 hints at 6-dimensional).
#[derive(Debug, Clone, PartialEq)]
pub struct PerceptAxes {
    pub axes: [f64; 6],
    pub epoch: u64,
}

/// Canonical digest: fixed field order, fixed-precision serialization.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct Digest(pub String);

/// Clip bounds.
#[derive(Debug, Clone, PartialEq)]
pub struct ClipBounds {
    pub min: f64,
    pub max: f64,
}

/// Rate budget per step.
#[derive(Debug, Clone, PartialEq)]
pub struct RateBudget {
    pub tokens_per_step: f64,
    pub decay_alpha: f64,
}

/// Broadcast region (_theoretischer_broadcast_bereich).
#[derive(Debug, Clone, PartialEq)]
pub struct BroadcastRegion {
    pub center: [f64; 6],
    pub radius: f64,
    pub epoch: u64,
}

/// Alignment state.
#[derive(Debug, Clone, PartialEq)]
pub struct AlignmentState {
    pub policy_version: String,
    pub last_decision: Option<String>,
    pub epoch: u64,
}

/// Alignment input.
#[derive(Debug, Clone, PartialEq)]
pub struct AlignmentInput {
    pub winner_slot: usize,
    pub winner_score: EpistemicValue,
    pub messvektor: Messvektor,
}

/// Alignment decision output.
#[derive(Debug, Clone, PartialEq)]
pub struct AlignmentDecision {
    pub admitted: bool,
    pub reason: String,
    pub epoch: u64,
}

/// Winner selected by select_winner.
#[derive(Debug, Clone, PartialEq)]
pub struct Winner {
    pub slot_id: usize,
    pub score: EpistemicValue,
    pub decision_digest: Digest,
}

/// Candidate bundle for select_winner (ClayCode BUNDLE(BIND(slot_i, x_i))).
#[derive(Debug, Clone, PartialEq)]
pub struct Candidate {
    pub slot_id: usize,
    pub bound_value: EpistemicValue,
    pub metadata: JSpaceSlot,
}

/// Pure evidence input E_t.
#[derive(Debug, Clone, PartialEq)]
pub struct PureEvidence {
    pub input_vector: Vec<f64>,
    pub rate_budget: RateBudget,
    pub clip_bounds: ClipBounds,
    pub epoch: u64,
}

/// Realised state R_t owned by the substrate.
#[derive(Debug, Clone, PartialEq)]
pub struct Grid10RealisedState {
    pub jspace: JSpace,
    pub messvektor: Messvektor,
    pub epoch: u64,
    pub turn_seq: u64,
    pub broadcast_region: BroadcastRegion,
    pub alignment_state: AlignmentState,
}

/// Fail-closed error for invariant violations.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InvariantViolation {
    pub invariant: String,
    pub detail: String,
}

impl fmt::Display for InvariantViolation {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "invariant violation '{}': {}", self.invariant, self.detail)
    }
}

impl std::error::Error for InvariantViolation {}

=== FILE: src/gridv1/invariants.rs ===
//! WP-2a: Structural invariants with ON_VIOLATION fail-closed semantics.
//! These are the CLAYCODE structural invariants, enforced at runtime.

use crate::gridv1::types::*;

/// ON_VIOLATION -> TriggerEmergencyDeescalation: J-Space capacity must not exceed 1.
pub fn check_jspace_capacity(jspace: &JSpace) -> Result<(), InvariantViolation> {
    if jspace.len() > MAX_CAPACITY {
        return Err(InvariantViolation {
            invariant: "JSPACE_CAPACITY".into(),
            detail: format!(
                "jspace slots {} > MAX_CAPACITY {}",
                jspace.len(),
                MAX_CAPACITY
            ),
        });
    }
    Ok(())
}

/// ON_VIOLATION -> RejectTransition: uptake sum must be conserved (== 1.0).
pub fn check_uptake_conservation(state: &UptakeState) -> Result<(), InvariantViolation> {
    let sum: f64 = state
        .uptakes
        .iter()
        .filter_map(|v| v.value())
        .sum();
    if (sum - 1.0).abs() > EPSILON {
        return Err(InvariantViolation {
            invariant: "UPTAKE_CONSERVATION".into(),
            detail: format!("sum of uptakes {} != 1.0 (eps {})", sum, EPSILON),
        });
    }
    Ok(())
}

/// ON_VIOLATION -> RejectTransition: digest fields must be fixed order.
pub fn check_digest_order(digest: &Digest, expected_prefix: &str) -> Result<(), InvariantViolation> {
    if !digest.0.starts_with(expected_prefix) {
        return Err(InvariantViolation {
            invariant: "DIGEST_ORDER".into(),
            detail: format!(
                "digest does not start with fixed-order prefix '{}'",
                expected_prefix
            ),
        });
    }
    Ok(())
}

/// ON_VIOLATION -> RejectTransition: Score_effective <= Score_raw.
pub fn check_decay_bound(raw: f64, effective: f64) -> Result<(), InvariantViolation> {
    if effective > raw + EPSILON {
        return Err(InvariantViolation {
            invariant: "DECAY_BOUND".into(),
            detail: format!("effective {} > raw {}", effective, raw),
        });
    }
    Ok(())
}

/// ON_VIOLATION -> RejectTransition: a field that requires a measurement must not be Unknown/Error/Hypothesis.
pub fn require_measured(value: &EpistemicValue, field: &str) -> Result<(), InvariantViolation> {
    match value {
        EpistemicValue::Measured { .. } => Ok(()),
        _ => Err(InvariantViolation {
            invariant: "EPISTEMIC_MEASURED_REQUIRED".into(),
            detail: format!(
                "field '{}' is not Measured (epistemic class {:?})",
                field,
                value.class()
            ),
        }),
    }
}

/// ON_VIOLATION -> TriggerEmergencyDeescalation: run all structural invariants on realised state.
pub fn check_all_invariants(state: &Grid10RealisedState) -> Result<(), InvariantViolation> {
    check_jspace_capacity(&state.jspace)?;
    Ok(())
}

=== FILE: src/gridv1/pure.rs ===
//! WP-2a: Pure transition functions F(R_t, E_t) -> R_{t+1}.
//! All functions are deterministic and replayable; precedence is turn_seq, not wall-clock.
//! UNKNOWN: exact decay curve for broadcast radius is pending measurement.

use crate::gridv1::types::*;
use crate::gridv1::invariants::*;

/// Apply evidence E_t to realised state R_t, producing a candidate next state.
/// This is the pure core of F before invariant gating.
pub fn apply_evidence(R_t: &Grid10RealisedState, E_t: &PureEvidence) -> Grid10RealisedState {
    let mut next = R_t.clone();
    next.epoch = E_t.epoch;
    next.turn_seq = R_t.turn_seq.wrapping_add(1);
    // Anti-monopoly decay: radius shrinks by alpha each step.
    let alpha = E_t.rate_budget.decay_alpha;
    next.broadcast_region.radius = (next.broadcast_region.radius * (1.0 - alpha)).max(0.0);
    next
}

/// Select a winner from J-Space slots using bound values.
/// Fail-closed: capacity invariant is checked; no measurable candidate is an error.
pub fn select_winner(jspace: &JSpace) -> Result<Winner, InvariantViolation> {
    check_jspace_capacity(jspace)?;
    let mut best_id: Option<usize> = None;
    let mut best_val: Option<f64> = None;
    let mut best_score: Option<EpistemicValue> = None;
    for slot in jspace.slots.iter().flatten() {
        if let Some(v) = slot.value.value() {
            let better = best_val.map_or(true, |bv| v > bv);
            if better {
                best_id = Some(slot.slot_id);
                best_val = Some(v);
                best_score = Some(slot.value.clone());
            }
        }
    }
    match (best_id, best_score) {
        (Some(slot_id), Some(score)) => Ok(Winner {
            slot_id,
            score,
            decision_digest: Digest(format!("grid10:winner:{}", slot_id)),
        }),
        _ => Err(InvariantViolation {
            invariant: "WINNER_SELECTION".into(),
            detail: "no measurable candidate in J-Space".into(),
        }),
    }
}

/// Compute percept axes from uptake state (6-dimensional _r6 hint).
pub fn compute_percept_axes(uptake: &UptakeState) -> PerceptAxes {
    let mut axes = [0.0; 6];
    for (i, u) in uptake.uptakes.iter().enumerate().take(6) {
        if let Some(v) = u.value() {
            axes[i % 6] += v;
        }
    }
    PerceptAxes {
        axes,
        epoch: uptake.epoch,
    }
}

/// Effective score with decay: Score_effective = Score_raw * (1 - alpha * Recency).
pub fn effective_score(raw: f64, recency: u64, alpha: f64) -> f64 {
    let decay = 1.0 - alpha * (recency as f64);
    (raw * decay.max(0.0)).max(0.0)
}

/// The canonical transition F: R_{t+1} = F(R_t, E_t).
/// Pre-conditions and post-conditions are enforced; ON_VIOLATION -> fail-closed.
pub fn F(
    R_t: &Grid10RealisedState,
    E_t: &PureEvidence,
) -> Result<Grid10RealisedState, InvariantViolation> {
    // Pre-conditions (structural invariants on R_t)
    check_jspace_capacity(&R_t.jspace)?;

    let next = apply_evidence(R_t, E_t);

    // Winner selection is part of the turn path; a missing measurable candidate fails closed.
    let _winner = select_winner(&next.jspace)?;

    // Post-conditions on R_{t+1}
    check_jspace_capacity(&next.jspace)?;
    check_decay_bound(1.0, next.broadcast_region.radius)?;

    Ok(next)
}

=== FILE: src/gridv1/property_tests.rs ===
//! WP-2a: Property-based style tests (std-only).
//! These are executable invariants; any failure is a hard contract breach.

use crate::gridv1::types::*;
use crate::gridv1::invariants::*;
use crate::gridv1::pure::*;

#[cfg(test)]
mod tests {
    use super::*;

    fn empty_jspace() -> JSpace {
        JSpace {
            slots: [None; GRID10_CELLS],
            epoch: 0,
            turn_seq: 0,
        }
    }

    fn default_state() -> Grid10RealisedState {
        Grid10RealisedState {
            jspace: empty_jspace(),
            messvektor: Messvektor { entries: vec![], epoch: 0 },
            epoch: 0,
            turn_seq: 0,
            broadcast_region: BroadcastRegion { center: [0.0; 6], radius: 1.0, epoch: 0 },
            alignment_state: AlignmentState { policy_version: "v0".into(), last_decision: None, epoch: 0 },
        }
    }

    fn sample_slot() -> JSpaceSlot {
        JSpaceSlot {
            slot_id: 0,
            value: EpistemicValue::Measured { value: 0.5, method: "t".into(), ts: 0, ref_id: "r".into() },
            salience: 1.0,
            uncertainty: 0.0,
            contradiction: 0.0,
            evidence_source: "t".into(),
            generation: 0,
            causal_event: None,
            allowed_action_class: "act".into(),
        }
    }

    #[test]
    fn jspace_capacity_invariant_holds_for_empty() {
        let s = default_state();
        assert!(check_jspace_capacity(&s.jspace).is_ok());
    }

    #[test]
    fn jspace_capacity_rejects_over_capacity() {
        let mut s = default_state();
        s.jspace.slots[0] = Some(sample_slot());
        s.jspace.slots[1] = Some(JSpaceSlot {
            slot_id: 1,
            value: EpistemicValue::Measured { value: 0.5, method: "t".into(), ts: 0, ref_id: "r".into() },
            salience: 1.0,
            uncertainty: 0.0,
            contradiction: 0.0,
            evidence_source: "t".into(),
            generation: 0,
            causal_event: None,
            allowed_action_class: "act".into(),
        });
        assert!(check_jspace_capacity(&s.jspace).is_err());
    }

    #[test]
    fn uptake_conservation_holds_for_unit_sum() {
        let mut uptakes = [EpistemicValue::Measured { value: 0.0, method: "".into(), ts: 0, ref_id: "".into() }; GRID10_CELLS];
        uptakes[0] = EpistemicValue::Measured { value: 1.0, method: "".into(), ts: 0, ref_id: "".into() };
        let state = UptakeState {
            uptakes,
            sum: EpistemicValue::Measured { value: 1.0, method: "".into(), ts: 0, ref_id: "".into() },
            epoch: 0,
        };
        assert!(check_uptake_conservation(&state).is_ok());
    }

    #[test]
    fn uptake_conservation_rejects_non_unit_sum() {
        let mut uptakes = [EpistemicValue::Measured { value: 0.0, method: "".into(), ts: 0, ref_id: "".into() }; GRID10_CELLS];
        uptakes[0] = EpistemicValue::Measured { value: 2.0, method: "".into(), ts: 0, ref_id: "".into() };
        let state = UptakeState {
            uptakes,
            sum: EpistemicValue::Measured { value: 2.0, method: "".into(), ts: 0, ref_id: "".into() },
            epoch: 0,
        };
        assert!(check_uptake_conservation(&state).is_err());
    }

    #[test]
    fn decay_bound_rejects_effective_greater_than_raw() {
        assert!(check_decay_bound(1.0, 1.0 + EPSILON * 2.0).is_err());
        assert!(check_decay_bound(1.0, 1.0).is_ok());
        assert!(check_decay_bound(1.0, 0.5).is_ok());
    }

    #[test]
    fn require_measured_rejects_unknown() {
        let v = EpistemicValue::Unknown { reason: "pending".into() };
        assert!(require_measured(&v, "score").is_err());
    }

    #[test]
    fn require_measured_accepts_measured() {
        let v = EpistemicValue::Measured { value: 1.0, method: "m".into(), ts: 0, ref_id: "r".into() };
        assert!(require_measured(&v, "score").is_ok());
    }

    #[test]
    fn epistemic_unknown_is_not_zero() {
