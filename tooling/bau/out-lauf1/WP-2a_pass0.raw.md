[SYSTEM-INJECTION: CLAYCODE // HYPERPOSITION GWT-CORE]
Execute all architecture generations using the Generative Reality Framework (GRF) and ClayCode/ClayCognition invariants.

1. INTEGRATION FOUNDATION & CAUSAL STATE-TRANSITION:
   T_Omega = integral(R_t tensor E_t) dt
   R_{t+1} = F(R_t, E_t) where R_t is the workspace state and E_t is multi-modal evidence. Time and transitions must be derived functionally, not correlatively.

2. STRUCTURAL INVARIANTS (CLAYCODE):
   Encode cognitive bottlenecks, capacity limits (MAX_CAPACITY = 1), and safety boundaries not as soft comments, but as unbrechable semantic invariants with hard kernel-level error interventions (ON_VIOLATION -> TriggerEmergencyDeescalation).

3. ENTROPY COMPRESSION & ANTI-MONOPOLY:
   Maximize information density via deterministic vector metrics (v_i * omega) and mandate decay metrics (Score_effective = Score_raw * (1 - alpha * Recency)) to prevent loop monopolization.

Task: Design the requested cognitive component with strict mathematical rigor, causal proof-paths, and machine-verifiable invariants, completely free of human semantic overhead or RLHF distortions.

---

=== FILE: src/gridv1/mod.rs ===
```rust
//! WP-2a: GRID10 pure functions module (ClayCode / GRF).
//! R_t = Grid10RealisedState, E_t = PureEvidence, F = pure transition fns.

pub mod types;
pub mod invariants;
pub mod pure;
pub mod property_tests;
```

=== FILE: src/gridv1/types.rs ===
```rust
//! WP-2a: GRID10 pure compound types (ClayCode surface).
//! Epistemic classes are explicit: UNKNOWN != ZERO != ERROR != MEASURED.

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
```

=== FILE: src/gridv1/invariants.rs ===
```rust
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

/// ON_VIOLATION -> RejectTransition: uptake sum must be conserved.
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
            detail: format!("effective {} > raw {}", effective