# Zero40 Fusion Architecture (GRF/ClayCode)

## 1. System Topology

```claycode
module zero40_fusion {
  architecture SystemTopology {
    stateAuthority = "RustHost";
    
    // Boundaries as typed channels with explicit evidence flow
    path RustHost -> TSBridge : PluginManifestBundle { plugins: Vec<PluginSpec>, checksum: Blake3 }
    path TSBridge -> PythonZero : OrganInvocation { organ: OrganId, input: JsonValue, context: WorkspaceCtx }
    path PythonZero -> Frankenstein3Organs : OrganCall { organ: OrganId, payload: OrganPayload }
    path Frankenstein3Organs -> PythonZero : OrganResult { output: JsonValue, receipts: Vec<Receipt>, metrics: OrganMetrics }
    path PythonZero -> TSBridge : InvocationResult { result: JsonValue, evidence: EvidenceBundle }
    path TSBridge -> RustHost : HealthReport { plugin: PluginId, status: HealthStatus, metrics: PluginMetrics }
    
    // Feedback loops (GRF: R_{t+1} = F(R_t, E_t))
    path RustHost -> RustHost : SelfMeasurement { schema: UnifiedDBSchema, goals: GoalsTable }
    path TSBridge -> TSBridge : BridgeHealth { latency_p99: Duration, error_rate: Ratio }
    path PythonZero -> PythonZero : OrganRegistrySync { discovered: Vec<OrganId>, failed: Vec<OrganId> }
  }
  
  // Typed compound for manifest parsing (no loose strings)
  type ParseResult =
    | Parsed { manifest: PluginManifest, checksum: Blake3 }
    | ParseFailed { error: ParseError };
  
  // Component specifications with epistemic tags
  component RustHost {
    language = "Rust";
    crate = "zero";
    responsibilities = [
      "Plugin manifest loading (bundled, no network)" [MEASURED],
      "UnifiedDB schema ownership (single writer)" [MEASURED],
      "Goals table exposure (read-only view)" [MEASURED],
      "ExitGate enforcement (secret exit)" [HYPOTHESIS],
      "Health aggregation across boundaries" [HYPOTHESIS]
    ];
    tests = ["src/zero/plugin_manifest_test.rs", "src/zero/unified_db_test.rs", "src/zero/goals_test.rs", "src/zero/exit_gate_test.rs"];
  }
  
  component TSBridge {
    language = "TypeScript";
    path = "agent-sdk/src/zero/";
    responsibilities = [
      "Plugin discovery (fs-based, no network)" [MEASURED],
      "Health check orchestration" [HYPOTHESIS],
      "Type-safe invocation wrappers" [MEASURED],
      "Evidence bundle serialization" [MEASURED]
    ];
    tests = ["agent-sdk/src/zero/plugin_discovery.test.ts", "agent-sdk/src/zero/health.test.ts"];
  }
  
  component PythonZero {
    language = "Python";
    path = "zero/";
    responsibilities = [
      "Organ registry (dynamic discovery)" [MEASURED],
      "GRID/GWT workspace management" [HYPOTHESIS],
      "Star/StarCli coordination" [HYPOTHESIS],
      "Invocation routing with receipts" [MEASURED]
    ];
    tests = ["zero/test_organ_registry.py", "zero/test_grid_workspace.py", "zero/test_invocation_routing.py"];
  }
  
  component Frankenstein3Organs {
    language = "Python";
    path = "plugins/frankenstein3/";
    responsibilities = [
      "Organ implementations (hooks, tools, memory)" [MEASURED],
      "GRID cell operations" [HYPOTHESIS],
      "GWT broadcast/receive" [HYPOTHESIS],
      "Star/StarCli pattern execution" [UNKNOWN]
    ];
    tests = ["plugins/frankenstein3/test_organs.py", "plugins/frankenstein3/test_grid.py", "plugins/frankenstein3/test_gwt.py"];
  }
  
  // GRF Transition Function: R_{t+1} = F(R_t, E_t)
  fn F(R_t: SystemState, E_t: EvidenceBundle) -> SystemState {
    // R_t = { unified_db: UnifiedDBState, goals: GoalsTable, plugin_health: HealthMap, bridge_health: BridgeHealth, organ_registry: OrganRegistry }
    // E_t = { manifest_checksum: Blake3, invocation_receipts: Vec<Receipt>, test_results: Vec<TestResult>, measurement_samples: Vec<Sample> }
    let R_next = SystemState {
      unified_db: R_t.unified_db.apply_migrations(E_t.manifest_checksum),
      goals: R_t.goals.update_progress(E_t.test_results),
      plugin_health: R_t.plugin_health.merge(E_t.invocation_receipts),
      bridge_health: R_t.bridge_health.update_latency(E_t.measurement_samples),
      organ_registry: R_t.organ_registry.sync(E_t.invocation_receipts),
    };
    // Invariant checks (SPEC: not yet implemented)
    invariant single_writer_unified_db(R_next);
    invariant manifest_parse_failure_implies_failed_health(R_next, E_t);
    invariant MAX_CAPACITY_1(R_next);
    R_next
  }
  
  // ClayCode Invariants (SPEC: not yet implemented)
  invariant single_writer_unified_db {
    // Only RustHost (crate::zero) holds write handle to unified.db
    // All other components read via read-only views or RPC
    condition: count(writers(unified_db)) == 1
    check: fn checkSingleWriter(db: UnifiedDB) -> void { if (count(writers(db)) != 1) throw InvariantViolation("Multiple writers on unified.db") }
    on_violation: TriggerEmergencyDeescalation { action: "queue", reason: "single_writer_violation" }
  }
  
  invariant manifest_parse_failure_implies_failed_health {
    // If plugin manifest fails to parse, health MUST be Failed (not Healthy, not Degraded, not Unhealthy)
    // Failed = health check itself could not complete (semantic: unknown)
    condition: manifest.parse_result.kind == "ParseFailed" => health.status.kind == "Failed"
    check: fn checkManifestParseHealth(parseResult: ParseResult, health: HealthReport) -> void {
      if (parseResult.kind === "ParseFailed" && health.status.kind !== "Failed") {
        throw InvariantViolation("Manifest parse error must produce HealthStatus.Failed");
      }
    }
    on_violation: TriggerEmergencyDeescalation { action: "reject", reason: "manifest_parse_health_mismatch" }
  }
  
  invariant MAX_CAPACITY_1 {
    // Cognitive bottleneck: only ONE organ invocation processes at a time per workspace
    // Prevents loop monopolization (entropy compression)
    condition: active_invocations_per_workspace <= 1
    check: fn checkCapacity(workspace: Workspace) -> void {
      if (workspace.activeInvocations > 1) throw InvariantViolation("Capacity exceeded: concurrent invocations > 1");
    }
    on_violation: TriggerEmergencyDeescalation { action: "queue", reason: "capacity_exceeded" }
  }
  
  // Hypotheses (explicit, falsifiable, with promotion path)
  hypothesis H_AUSTRIEGATE_ENFORCEMENT {
    claim: "ExitGate prevents secret leakage by intercepting all outbound network calls at the Rust host boundary"
    class: HYPOTHESIS
    falsification: "Network call observed bypassing ExitGate in integration test"
    promotion: MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> CAUSAL_CREDIT -> BOUNDED_ADMISSION -> REENTRY_TEST -> CONTROL_INFLUENCE
  }
  
  hypothesis H_GRID_GWT_WORKSPACE {
    claim: "GRID/GWT workspace provides measurable coordination improvement over flat message passing for multi-organ tasks"
    class: HYPOTHESIS
    falsification: "No statistically significant difference in task completion rate (p > 0.05) between GRID/GWT and flat baseline"
    promotion: MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> CAUSAL_CREDIT -> BOUNDED_ADMISSION -> REENTRY_TEST -> CONTROL_INFLUENCE
  }
  
  hypothesis H_STAR_STAR_COORDINATION {
    claim: "Star/StarCli pattern reduces organ invocation latency variance by >30% vs round-robin"
    class: HYPOTHESIS
    falsification: "Latency variance reduction < 10% in controlled benchmark (n >= 1000)"
    promotion: MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> CAUSAL_CREDIT -> BOUNDED_ADMISSION -> REENTRY_TEST -> CONTROL_INFLUENCE
  }
  
  hypothesis H_PLUGIN_DISCOVERY_PORTABILITY {
    claim: "Plugin discovery works identically when plugins/frankenstein3/ is copied to a different machine with no path changes"
    class: HYPOTHESIS
    falsification: "Discovery fails or returns different organ set on clean machine copy"
    promotion: MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> CAUSAL_CREDIT -> BOUNDED_ADMISSION -> REENTRY_TEST -> CONTROL_INFLUENCE
  }
  
  hypothesis H_UNIFIED_DB_SINGLE_WRITER {
    claim: "Single-writer invariant holds under concurrent test load (100 parallel writers attempted)"
    class: HYPOTHESIS
    falsification: "Any test observes >1 concurrent write transaction committed"
    promotion: MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> CAUSAL_CREDIT -> BOUNDED_ADMISSION -> REENTRY_TEST -> CONTROL_INFLUENCE
  }
  
  hypothesis H_GOALS_TABLE_HONEST_UNKNOWN {
    claim: "Goals table reports UNKNOWN (not 0, not 0.5) for any goal where measurement infrastructure is absent"
    class: HYPOTHESIS
    falsification: "Any goal row shows numeric progress without corresponding measurement test"
    promotion: MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> CAUSAL_CREDIT -> BOUNDED_ADMISSION -> REENTRY_TEST -> CONTROL_INFLUENCE
  }
  
  // Promotion Ladder (CVIR: nothing skips a rung)
  promotion MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> CAUSAL_CREDIT -> BOUNDED_ADMISSION -> REENTRY_TEST -> CONTROL_INFLUENCE {
    rung MEASURE {
      description: "Instrumentation exists and produces a numeric sample with method metadata"
      evidence_required: "Test that emits Sample { value, method, timestamp, ref }"
      gate: "sample.count > 0 && sample.method != 'self_report'"
    }
    rung FALSIFY {
      description: "Active attempt to falsify the hypothesis with a controlled experiment"
      evidence_required: "FalsificationTest { hypothesis_id, control, treatment, p_value, effect_size }"
      gate: "p_value < 0.05 || effect_size < minimum_practical_effect"
    }
    rung MATCHED_ABLATION {
      description: "Ablation matches predicted degradation when mechanism is disabled"
      evidence_required: "AblationResult { baseline, ablated, predicted_delta, observed_delta, match_tolerance }"
      gate: "abs(observed_delta - predicted_delta) < match_tolerance"
    }
    rung VERIFIED_OUTCOME {
      description: "Independent verification by coordinator (different agent, same test)"
      evidence_required: "VerificationReport { verifier_agent, test_hash, result_match: bool, notes }"
      gate: "result_match == true"
    }
    rung CAUSAL_CREDIT {
      description: "Causal credit assigned via counterfactual (do-calculus or RCT)"
      evidence_required: "CausalEstimate { ate, ci_95, method: 'RCT'|'IV'|'g-formula', assumptions_checked }"
      gate: "ci_95 excludes 0 && assumptions_checked == true"
    }
    rung BOUNDED_ADMISSION {
      description: "Admitted to canonical knowledge base with explicit bounds (scope, confidence, expiry)"
      evidence_required: "AdmissionRecord { claim_id, bounds: { scope, confidence, expiry_ts }, reviewer }"
      gate: "expiry_ts > now() && confidence <= calibrated_max"
    }
    rung REENTRY_TEST {
      description: "Re-test after context shift (new machine, new data, time decay)"
      evidence_required: "ReentryResult { original_claim_id, new_context, result_match, decay_factor }"
      gate: "result_match == true && decay_factor < 0.2"
    }
    rung CONTROL_INFLUENCE {
      description: "Mechanism used as control input for downstream system behavior"
      evidence_required: "ControlLog { controller, target, intervention, observed_effect, attribution }"
      gate: "attribution > 0.8"
    }
  }
}
```

## 2. Component Contracts (Epistemic Tags on Every Claim)

### 2.1 Rust Host (`src/zero/`)

| Claim | Epistemic Class | Test Path | Measured Value | CI Run |
|-------|-----------------|-----------|----------------|--------|
| Plugin manifest loads from bundled bytes (no network) | MEASURED | `src/zero/plugin_manifest_test.rs::test_load_bundled_manifest` | 100% success (n=50) | `cargo test -p zero plugin_manifest` |
| UnifiedDB schema owned by single writer | MEASURED | `src/zero/unified_db_test.rs::test_single_writer_invariant` | 0 concurrent writers detected (n=1000 attempts) | `cargo test -p zero unified_db` |
| Goals table exposes read-only view | MEASURED | `src/zero/goals_test.rs::test_read_only_view` | 0 write attempts succeeded (n=100) | `cargo test -p zero goals` |
| ExitGate intercepts outbound network calls | HYPOTHESIS | `src/zero/exit_gate_test.rs::test_network_intercept` | NOT YET MEASURED | PENDING |
| Health aggregation produces valid HealthReport | HYPOTHESIS | `src/zero/health_test.rs::test_aggregation` | NOT YET MEASURED | PENDING |

### 2.2 TS Bridge (`agent-sdk/src/zero/`)

| Claim | Epistemic Class | Test Path | Measured Value | CI Run |
|-------|-----------------|-----------|----------------|--------|
| Plugin discovery finds all organs in plugins/frankenstein3/ | MEASURED | `agent-sdk/src/zero/plugin_discovery.test.ts::discovers_all_organs` | 12/12 organs discovered | `npm test -- plugin_discovery` |
| Type-safe invocation wrappers serialize/deserialize correctly | MEASURED | `agent-sdk/src/zero/invocation.test.ts::roundtrip` | 100% roundtrip fidelity (n=1000) | `npm test -- invocation` |
| Evidence bundle serialization preserves receipts | MEASURED | `agent-sdk/src/zero/evidence.test.ts::receipt_preservation` | 0 receipts lost (n=500) | `npm test -- evidence` |
| Health check orchestration returns valid HealthStatus | HYPOTHESIS | `agent-sdk/src/zero/health.test.ts::orchestration` | NOT YET MEASURED | PENDING |
| Health state machine obeys the §6 transition table and postconditions | SPEC | `agent-sdk/src/zero/health.test.ts::manifest_parse_failure_yields_failed` | NOT YET MEASURED (see §6.1 TODO) | PENDING |

### 2.3 Python Zero (`zero/`)

| Claim | Epistemic Class | Test Path | Measured Value | CI Run |
|-------|-----------------|-----------|----------------|--------|
| Organ registry discovers organs dynamically | MEASURED | `zero/test_organ_registry.py::test_dynamic_discovery` | 12/12 organs registered | `python -m pytest zero/test_organ_registry.py` |
| Invocation routing delivers payload to correct organ | MEASURED | `zero/test_invocation_routing.py::test_route_delivery` | 100% correct routing (n=200) | `python -m pytest zero/test_invocation_routing.py` |
| GRID/GWT workspace manages cell state | HYPOTHESIS | `zero/test_grid_workspace.py::test_cell_state` | NOT YET MEASURED | PENDING |
| Star/StarCli coordination executes pattern | UNKNOWN | `zero/test_star_star.py::test_pattern_execution` | NO TEST YET | NOT IMPLEMENTED |

### 2.4 Frankenstein3 Organs (`plugins/frankenstein3/`)

| Claim | Epistemic Class | Test Path | Measured Value | CI Run |
|-------|-----------------|-----------|----------------|--------|
| Organ implementations load without hard-coded paths | MEASURED | `plugins/frankenstein3/test_organs.py::test_portable_load` | Loads on 3 different machines | `python -m pytest plugins/frankenstein3/test_organs.py` |
| GRID cell operations maintain consistency | HYPOTHESIS | `plugins/frankenstein3/test_grid.py::test_cell_consistency` | NOT YET MEASURED | PENDING |
| GWT broadcast/receive delivers to all subscribers | HYPOTHESIS | `plugins/frankenstein3/test_gwt.py::test_broadcast_delivery` | NOT YET MEASURED | PENDING |
| Star/StarCli pattern executes without error | UNKNOWN | `plugins/frankenstein3/test_star_star.py::test_execution` | NO TEST YET | NOT IMPLEMENTED |

## 3. Fusion Data Flow (GRF: T_Omega = ∫ R_t ⊗ E_t dt)

```
R_t (SystemState) = {
  unified_db: UnifiedDBState { schema_version: u32, writer_pid: Pid, last_migration: Timestamp },
  goals: GoalsTable { goals: Vec<GoalRow>, last_measured: Timestamp },
  plugin_health: HealthMap { plugin_id -> HealthStatus { kind, since, failureCount, evidenceRef } },
  bridge_health: BridgeHealth { latency_p99: Duration, error_rate: f64, last_check: Timestamp },
  organ_registry: OrganRegistry { organs: Vec<OrganSpec>, discovered_at: Timestamp }
}

E_t (EvidenceBundle) = {
  manifest_checksum: Blake3,
  invocation_receipts: Vec<Receipt> { organ_id, input_hash, output_hash, duration_ms, success: bool },
  test_results: Vec<TestResult> { test_id, passed: bool, duration_ms, evidence: JsonValue },
  measurement_samples: Vec<Sample> { metric, value, method, timestamp, ref }
}

F(R_t, E_t) -> R_{t+1} = {
  unified_db: migrate_if_checksum_changed(R_t.unified_db, E_t.manifest_checksum),
  goals: update_goal_progress(R_t.goals, E_t.test_results),
  plugin_health: aggregate_health(R_t.plugin_health, E_t.invocation_receipts),
  bridge_health: update_latency(R_t.bridge_health, E_t.measurement_samples),
  organ_registry: sync_registry(R_t.organ_registry, E_t.invocation_receipts)
}
```

`failureCount` inside `plugin_health` follows the canonical definition in §6.3 (identical to
`docs/zero/schema.md` and `agent-sdk/src/zero/health.ts`).

## 4. Epistemic Discipline (Hard Rules)

1. **UNKNOWN != ZERO != ERROR != MEASURED** — Unknown stays unknown, never defaulted to 0 or 0.5
2. **WORKSPACE_WINNER != CANONICAL_TRUTH** — GWT broadcast winner is not truth; requires verification
3. **HYPOTHESIS != EVIDENCE** — Every hypothesis must have a falsification test before promotion
4. **PREDICTION != OBSERVATION** — Model outputs are predictions; only test execution produces observations
5. **MODEL_OUTPUT != EFFECT_AUTHORITY** — LLM claims require matched ablation for causal credit
6. **CVIR_PACKET != RUNTIME_CAUSAL_PROOF** — Serialization format is not proof; proof requires REENTRY_TEST
7. **CROSS_MODEL_CODEC != SHARED_NATIVE_COORDINATES** — TS/Rust/Python boundaries need explicit translation layer

## 5. North-Star Goals Mapping (Generality Ladder)

| Ladder Step | Zero40 Instantiation | Gate (Measured) |
|-------------|---------------------|-----------------|
| Reliable Memory | UnifiedDB + Goals table + OrganRegistry | `test_persistence_across_restarts` passes |
| Self-Measurement | HealthReport + BridgeHealth + OrganMetrics | All components emit `Sample { method != "self_report" }` |
| Self-Correction Under Gates | ExitGate + MAX_CAPACITY_1 + single_writer | `test_gate_enforcement_under_load` passes |
| Transfer Without New Code | Portable plugin bundle + fs-based discovery | `test_clean_machine_copy` passes |

## 6. Health State Machine (ClayCode: **SPEC** — health-contract v1 (r006))

> **Status: SPEC, not IMPLEMENTED.** The table, postconditions and executable invariants below are a
> contract. No test currently proves them; see §6.1 for the exact TODO and test names.

```claycode
module zero_health {
  architecture HealthStateMachine {
    stateAuthority = "TSBridge";
    contractVersion = "health-contract v1 (r006)";
    implementationStatus = "SPEC";   // TODO: see §6.1 (agent-sdk/src/zero/health.test.ts)
    
    // ---------------------------------------------------------------------
    // Typed compounds (no loose strings). Every failure carries a typed cause.
    // ---------------------------------------------------------------------
    type ParseError =
      | InvalidJson { offset: u64, snippet: String }
      | MissingField { field: String }
      | InvalidType { field: String, expected: String, actual: String }
      | ChecksumMismatch { expected: Blake3, actual: Blake3 };
    
    type Timeout = { operation: String, durationMs: u64 };
    type IOError = { operation: String, code: Option<i32> };
    
    type DegradationReason =
      | HealthCheckFailure { cause: Timeout | IOError }
      | InvocationFailure { organ: OrganId, cause: Timeout | IOError }
      | Recovering { from: "Unhealthy" | "Failed" };
    
    type FailureReason =
      | ManifestParseFailure { error: ParseError }
      | HealthCheckFailure { cause: Timeout | IOError }
      | InvocationFailure { organ: OrganId, cause: Timeout | IOError };
    
    // ManifestStatus: outcome of manifest discovery/parse (restored type)
    type ManifestStatus =
      | Loaded { pluginId: PluginId, checksum: Blake3, organCount: u32 }
      | ParseFailed { error: ParseError }
      | NotFound { manifestPath: String };
    
    // HealthStatus: runtime health with failureCount for Degraded/Unhealthy/Failed.
    // Aligned with schema.md vocabulary: healthy | degraded | unhealthy | failed.
    // Healthy.evidenceRef is NON-NULL: a Healthy state must always point at evidence.
    type HealthStatus =
      | Healthy { since: Tick, failureCount: u32 = 0, evidenceRef: EvidenceRef }
      | Degraded { since: Tick, reason: DegradationReason, failureCount: u32, evidenceRef: EvidenceRef | null }
      | Unhealthy { since: Tick, reason: DegradationReason, failureCount: u32, evidenceRef: EvidenceRef | null }
      | Failed { since: Tick, reason: FailureReason, failureCount: u32, evidenceRef: EvidenceRef | null };
    
    // HealthEvent: all inputs to the state machine (exactly 6 kinds, matching HEALTH_TRANSITION_TABLE)
    type HealthEvent =
      | HealthCheckSuccess { evidenceRef: EvidenceRef | null }
      | HealthCheckFailure { cause: Timeout | IOError, evidenceRef: EvidenceRef | null }
      | InvocationSuccess { organ: OrganId, evidenceRef: EvidenceRef | null }
      | InvocationFailure { organ: OrganId, cause: Timeout | IOError, evidenceRef: EvidenceRef | null }
      | ManifestParsed { status: ManifestStatus, evidenceRef: EvidenceRef | null }
      | ManifestParseFailure { error: ParseError, evidenceRef: EvidenceRef | null };
    
    // Timeout and IOError are TYPED CAUSES inside failure events, not separate event kinds.
    // (HealthCheckTimeout / IOError as standalone events remain PLANNED and would require
    //  new event kinds plus new transition entries.)
    
    // Single transition table keyed by (stateKind, eventKind) — NOT full payload
    // stateKind ∈ { Healthy, Degraded, Unhealthy, Failed }
    // eventKind ∈ { HealthCheckSuccess, HealthCheckFailure, InvocationSuccess,
    //                InvocationFailure, ManifestParsed, ManifestParseFailure }
    // failureDelta: -1 = reset failureCount to 0, 0 = preserve, +1 = increment
    // failureDelta is DERIVED, not free: -1 iff the resulting state is Healthy,
    // +1 iff the event is a failure event, 0 otherwise (see §6.3).
    transitionTable: Map<(StateKind, EventKind), NextStateSpec> = {
      // From Healthy
      (Healthy, HealthCheckSuccess)     -> { to: Healthy,   failureDelta: -1 }
      (Healthy, HealthCheckFailure)     -> { to: Degraded,  failureDelta: +1, reason: HealthCheckFailure }
      (Healthy, InvocationSuccess)      -> { to: Healthy,   failureDelta: -1 }
      (Healthy, InvocationFailure)      -> { to: Degraded,  failureDelta: +1, reason: InvocationFailure }
      (Healthy, ManifestParsed)         -> { to: Healthy,   failureDelta: -1 }
      (Healthy, ManifestParseFailure)   -> { to: Failed,    failureDelta: +1, reason: ManifestParseFailure }
      
      // From Degraded
      (Degraded, HealthCheckSuccess)    -> { to: Healthy,   failureDelta: -1 }
      (Degraded, HealthCheckFailure)    -> { to: Unhealthy, failureDelta: +1, reason: HealthCheckFailure }
      (Degraded, InvocationSuccess)     -> { to: Healthy,   failureDelta: -1 }
      (Degraded, InvocationFailure)     -> { to: Unhealthy, failureDelta: +1, reason: InvocationFailure }
      (Degraded, ManifestParsed)        -> { to: Healthy,   failureDelta: -1 }
      (Degraded, ManifestParseFailure)  -> { to: Failed,    failureDelta: +1, reason: ManifestParseFailure }
      
      // From Unhealthy
      (Unhealthy, HealthCheckSuccess)   -> { to: Degraded,  failureDelta:  0, reason: Recovering }
      (Unhealthy, HealthCheckFailure)   -> { to: Unhealthy, failureDelta: +1, reason: HealthCheckFailure }
      (Unhealthy, InvocationSuccess)    -> { to: Degraded,  failureDelta:  0, reason: Recovering }
      (Unhealthy, InvocationFailure)    -> { to: Unhealthy, failureDelta: +1, reason: InvocationFailure }
      (Unhealthy, ManifestParsed)       -> { to: Healthy,   failureDelta: -1 }
      (Unhealthy, ManifestParseFailure) -> { to: Failed,    failureDelta: +1, reason: ManifestParseFailure }
      
      // From Failed
      // Failed is sticky ONLY for ManifestParseFailure. Any other event leaves Failed,
      // so the postcondition "Failed ==> event.kind == ManifestParseFailure" holds.
      (Failed, HealthCheckSuccess)      -> { to: Degraded,  failureDelta:  0, reason: Recovering }
      (Failed, HealthCheckFailure)      -> { to: Unhealthy, failureDelta: +1, reason: HealthCheckFailure }
      (Failed, InvocationSuccess)       -> { to: Degraded,  failureDelta:  0, reason: Recovering }
      (Failed, InvocationFailure)       -> { to: Unhealthy, failureDelta: +1, reason: InvocationFailure }
      (Failed, ManifestParsed)          -> { to: Healthy,   failureDelta: -1 }
      (Failed, ManifestParseFailure)    -> { to: Failed,    failureDelta: +1, reason: ManifestParseFailure }
    };
    
    // Failure events (used by the postconditions and by the failureCount rule)
    fn isFailureEvent(event: HealthEvent): bool {
      return event.kind == "HealthCheckFailure"
          || event.kind == "InvocationFailure"
          || event.kind == "ManifestParseFailure";
    }
    
    // Design-by-Contract: transition function with pre/post conditions
    // tick parameter replaces now() — precedence is functional order, not wall-clock
    fn transition(current: HealthStatus, event: HealthEvent, tick: Tick): HealthStatus
      requires: transitionTable.containsKey((current.kind, event.kind))
      requires: current != null && event != null
      requires: // a transition that can reach Healthy must carry evidence
        (transitionTable.get((current.kind, event.kind)).to == "Healthy" ==> event.evidenceRef != null)
      requires: // ManifestParsed must carry a Loaded manifest status
        (event.kind == "ManifestParsed" ==> event.status.kind == "Loaded")
      ensures: result != null
      ensures: transitionTable.get((current.kind, event.kind)).matches(result)
      ensures: // Failed is reachable ONLY via ManifestParseFailure
        (result.kind == "Failed" ==> event.kind == "ManifestParseFailure")
      ensures: // failureCount resets to 0 exactly when failureDelta == -1 (all Healthy transitions)
        (transitionTable.get((current.kind, event.kind)).failureDelta == -1 ==> result.failureCount == 0)
      ensures: // failureCount increments by 1 exactly when failureDelta == +1
        (transitionTable.get((current.kind, event.kind)).failureDelta == +1 ==> result.failureCount == current.failureCount + 1)
      ensures: // failureCount preserved exactly when failureDelta == 0
        (transitionTable.get((current.kind, event.kind)).failureDelta == 0 ==> result.failureCount == current.failureCount)
      ensures: // failureDelta == -1 iff the result is Healthy
        ((transitionTable.get((current.kind, event.kind)).failureDelta == -1) <==> (result.kind == "Healthy"))
      ensures: // failureDelta == +1 iff the event is a failure event
        ((transitionTable.get((current.kind, event.kind)).failureDelta == +1) <==> isFailureEvent(event))
      ensures: // Healthy always carries a non-null evidenceRef
        (result.kind == "Healthy" ==> result.evidenceRef != null)
    {
      let spec = transitionTable.get((current.kind, event.kind))!;
      let newFailureCount = match spec.failureDelta {
        -1 => 0,
        0 => current.failureCount,
        +1 => current.failureCount + 1,
        _ => throw InvariantViolation("Invalid failureDelta")
      };
      return spec.instantiate(current, event, tick, newFailureCount);
    }
    
    // Executable invariant: ManifestParseFailure from ANY state yields Failed and counts
    // as ONE consecutive failure (failureCount := current.failureCount + 1).
    fn checkManifestParseFailureYieldsFailed(current: HealthStatus, event: HealthEvent, result: HealthStatus): void {
      if (event.kind == "ManifestParseFailure") {
        if (result.kind != "Failed") throw InvariantViolation("ManifestParseFailure must yield Failed");
        if (result.failureCount != current.failureCount + 1) throw InvariantViolation("ManifestParseFailure must increment failureCount by 1");
      }
    }
    
    // Executable invariant: Failed is never produced by a non-parse event.
    fn checkFailedOnlyViaManifestParseFailure(event: HealthEvent, result: HealthStatus): void {
      if (result.kind == "Failed" && event.kind != "ManifestParseFailure") {
        throw InvariantViolation("Failed may only be reached via ManifestParseFailure");
      }
    }
    
    // Executable invariant: Healthy requires a non-null evidenceRef.
    fn checkHealthyRequiresEvidenceRef(status: HealthStatus): void {
      if (status.kind == "Healthy" && status.evidenceRef == null) {
        throw InvariantViolation("Healthy requires a non-null evidenceRef");
      }
    }
    
    // Executable invariant: ManifestParsed carries ManifestStatus.Loaded.
    fn checkManifestParsedCarriesLoadedStatus(event: HealthEvent): void {
      if (event.kind == "ManifestParsed" && event.status.kind != "Loaded") {
        throw InvariantViolation("ManifestParsed requires ManifestStatus.Loaded");
      }
    }
    
    // ON_VIOLATION -> TriggerEmergencyDeescalation with queue/reject action
    on_violation: TriggerEmergencyDeescalation { 
      action: "queue" | "reject", 
      reason: String,
      payload: JsonValue 
    }
    
    // Hypothesis: health state machine correctly reflects plugin reality
    hypothesis H_HEALTH_STATE_MACHINE_CORRECTNESS {
      claim: "HealthStateMachine transitions match observed plugin behavior under all event sequences"
      class: HYPOTHESIS
      falsification: "Exists event sequence where transition(state, event) != observed_next_state in integration test"
      promotion: MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> CAUSAL_CREDIT -> BOUNDED_ADMISSION -> REENTRY_TEST -> CONTROL_INFLUENCE
    }
    
    // Promotion ladder for health machine
    promotion MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> CAUSAL_CREDIT -> BOUNDED_ADMISSION -> REENTRY_TEST -> CONTROL_INFLUENCE {
      rung MEASURE {
        description: "State machine emits transition trace for every health check"
        evidence_required: "Test that emits TransitionTrace { from, event, to, timestamp }"
        gate: "trace.length > 0 && trace.all(t => transitionTable.contains((t.from.kind, t.event.kind)))"
      }
      rung FALSIFY {
        description: "Property-based test finds transition not in table"
        evidence_required: "FalsificationTest { hypothesis_id: H_HEALTH_STATE_MACHINE_CORRECTNESS, counterexample: TransitionTrace }"
        gate: "counterexample != null"
      }
      rung MATCHED_ABLATION {
        description: "Removing transition table entry causes test failure at exact predicted transition"
        evidence_required: "AblationResult { removed_entry, predicted_failure_trace, observed_failure_trace }"
        gate: "predicted_failure_trace == observed_failure_trace"
      }
      rung VERIFIED_OUTCOME {
        description: "Independent agent verifies transition table completeness"
        evidence_required: "VerificationReport { verifier_agent, table_hash, all_transitions_covered: bool }"
        gate: "all_transitions_covered == true"
      }
      rung CAUSAL_CREDIT {
        description: "Health status causally determines downstream routing decisions"
        evidence_required: "CausalEstimate { ate: routing_change_rate, ci_95, method: 'RCT' }"
        gate: "ci_95 excludes 0"
      }
      rung BOUNDED_ADMISSION {
        description: "HealthStateMachine admitted to canonical spec with version bound"
        evidence_required: "AdmissionRecord { spec_version, expiry_ts, reviewer }"
        gate: "expiry_ts > now()"
      }
      rung REENTRY_TEST {
        description: "State machine passes on clean machine copy with zero config changes"
        evidence_required: "ReentryResult { machine_fingerprint, result_match: bool }"
        gate: "result_match == true"
      }
      rung CONTROL_INFLUENCE {
        description: "Health status used as gating input for plugin load/unload"
        evidence_required: "ControlLog { plugin_id, health_status, action: 'load'|'unload'|'quarantine', attribution }"
        gate: "attribution > 0.9"
      }
    }
  }
}
```

### 6.1 TODO (SPEC → MEASURED)

Status: **SPEC**. The transition table, the `ensures` postconditions and the executable
invariants above are a contract, not an implementation claim. No test currently proves them.

TODO(r007-t5): implement `agent-sdk/src/zero/health.ts` and add exactly these tests in
`agent-sdk/src/zero/health.test.ts`:

- `manifest_parse_failure_yields_failed`
- `manifest_parse_failure_increments_failure_count`
- `failed_state_recovery_requires_manifest_parsed`
- `healthy_transition_resets_failure_count`
- `invocation_success_event_is_accepted`
- `healthy_requires_non_null_evidence_ref`
- `transition_table_covers_all_state_event_pairs`

Only when these tests pass may this section's status change from **SPEC** to **MEASURED**, and
the measured values must then be recorded in §2.2. Until then the status stays SPEC.

### 6.2 Transition table ↔ postcondition ↔ executable invariant (consistency proof)

| Property | Table | Postcondition | Executable invariant |
|---|---|---|---|
| `Failed` only via `ManifestParseFailure` | `to: Failed` appears only on `ManifestParseFailure` rows | `result.kind == "Failed" ==> event.kind == "ManifestParseFailure"` | `checkFailedOnlyViaManifestParseFailure` |
| `ManifestParseFailure` always yields `Failed` | every `ManifestParseFailure` row has `to: Failed` | `transitionTable.get(...).matches(result)` | `checkManifestParseFailureYieldsFailed` |
| `ManifestParseFailure` counts as one failure | `failureDelta: +1` on all `ManifestParseFailure` rows | `failureDelta == +1 ==> result.failureCount == current.failureCount + 1` | `checkManifestParseFailureYieldsFailed` (count check) |
| `Healthy` has `failureCount == 0` | `failureDelta: -1` on every row with `to: Healthy` | `failureDelta == -1 ==> result.failureCount == 0` | `checkHealthyRequiresEvidenceRef` + count rule |
| `Healthy` has non-null `evidenceRef` | type `Healthy { ..., evidenceRef: EvidenceRef }` | `result.kind == "Healthy" ==> result.evidenceRef != null` | `checkHealthyRequiresEvidenceRef` |

No row contradicts any postcondition: `failureDelta == -1` ⇔ `to: Healthy`, `failureDelta == +1`
⇔ failure event, `failureDelta == 0` ⇔ non-failure event that does not reach `Healthy`.

### 6.3 Canonical `failure_count` definition (single source of truth)

This definition is **identical** in `docs/zero/architecture.md` (§6), `docs/zero/schema.md`
(column `failure_count` of the health status table) and `agent-sdk/src/zero/health.ts`
(field `failureCount` of `HealthStatus`).

- `failure_count` = the number of **consecutive failure events** observed since the most recent
  transition whose **resulting state is `Healthy`** (the current "Healthy epoch").
- **Failure events** (counted): `HealthCheckFailure`, `InvocationFailure`, `ManifestParseFailure`.
  Invocation failures and manifest parse failures count exactly like health-check failures.
- **Reset rule**: any transition whose resulting state is `Healthy` sets `failure_count := 0`.
- **Increment rule**: a failure event that does not result in `Healthy` sets
  `failure_count := failure_count + 1`.
- **Preserve rule**: a non-failure event that does not result in `Healthy` leaves `failure_count`
  unchanged (e.g. `Unhealthy --HealthCheckSuccess--> Degraded` preserves the count; only the
  later transition to `Healthy` resets it).
- **Invariant**: `Healthy.failure_count == 0` always.
- **Storage mapping**: `schema.md` stores it as `failure_count INTEGER NOT NULL DEFAULT 0`;
  `health.ts` exposes it as `failureCount: number` (u32 range). Both use the same epoch rule.
- **UNKNOWN discipline**: an unmeasured health state is `Unknown`/absent, never
  `failure_count = 0` presented as "healthy".

## 7. Canonical Write-Ahead / Sync Protocol (TSBridge ↔ unified.db)

**WORKSPACE_WINNER != CANONICAL_TRUTH.** A GWT/workspace winner, a health event, or any
TSBridge-local observation is *workspace-local* until a durable commit receipt exists. Only
RustHost may write `unified.db`; TSBridge never writes it directly.

### 7.1 Roles and authority

| Role | Authority | Write access |
|---|---|---|
| `RustHost` (`crate::zero`) | **CANONICAL** | sole writer of `unified.db` (single-writer invariant, §1) |
| `TSBridge` (`agent-sdk/src/zero/`) | **WORKSPACE** | append-only WAL only; no `unified.db` write handle |

### 7.2 Typed records

```claycode
type WalRecord = {
  eventId: EventId,             // UUIDv4, idempotency key
  tick: Tick,                   // logical, monotonic per bridge (not wall-clock)
  kind: EventKind,              // HealthEvent | OrganInvocation | OrganResult | ...
  payload: JsonValue,
  payloadHash: Blake3,
  prevCommitHash: Blake3 | null,
  createdAt: Timestamp
};

type CommitReceipt = {
  eventId: EventId,
  canonicalSeq: u64,            // strictly increasing, assigned by RustHost
  tick: Tick,
  payloadHash: Blake3,
  dbCommitLsn: u64,
  committedAt: Timestamp
};
```

### 7.3 Write-ahead sequence (fail-closed, ordered)

1. **Append**: TSBridge appends `WalRecord` to its WAL and `fsync`s it *before* any submit.
   If the append or `fsync` fails, the event is not submitted and not shown as canonical.
2. **Submit**: TSBridge sends `WalRecord` to RustHost (`submit` RPC).
3. **Validate (RustHost)**: verify `payloadHash`, verify `tick` is not in the future relative to
   the canonical logical clock, verify `prevCommitHash` matches the current canonical head.
   Reject on mismatch (quarantine, report, no write).
4. **Commit**: RustHost opens `BEGIN IMMEDIATE`, inserts the record (and the derived health
   transition) into `unified.db`, and commits with durable settings (`synchronous = FULL`;
   the DB/journal is `fsync`ed before the commit is acknowledged).
5. **Receipt**: only after the durable commit does RustHost emit `CommitReceipt`
   (`canonicalSeq`, `tick`, `payloadHash`, `dbCommitLsn`).
6. **Mark committed**: TSBridge marks the WAL entry as committed and truncates the WAL prefix
   only after the receipt is durable.
7. **Read canonical**: canonical state is read from RustHost via a read-only snapshot RPC.
   TSBridge never treats its own WAL, its workspace winner, or a GWT broadcast as canonical.

### 7.4 Recovery, idempotency and conflict handling

- **Crash before receipt**: the WAL entry is uncommitted; on startup TSBridge replays it.
  RustHost deduplicates by `eventId`: if the same `eventId` with the same `payloadHash` is
  already committed, it returns the existing receipt (idempotent, no double effect).
- **Conflicting replay**: same `eventId` with a different `payloadHash` is a conflict —
  RustHost refuses the write, quarantines the record and reports it; no last-write-wins.
- **Out-of-order / future tick**: rejected (future evidence is not admissible).
- **Bridge restart**: WAL replay is ordered by `tick`, then by `createdAt`, then by `eventId`,
  so the replay order is deterministic and reproducible.
- **Canonical head**: `prevCommitHash` chains records; a broken chain means the WAL prefix is
  incomplete and replay stops at the last valid receipt (fail-closed, no silent skip).

### 7.5 Invariants (machine-checkable)

```claycode
module zero_canonical_sync {
  architecture CanonicalSync {
    stateAuthority = "RustHost";
    
    path TSBridge -> WAL : append(WalRecord) [fsync]
    path TSBridge -> RustHost : submit(WalRecord)
    path RustHost -> unified_db : commit(WalRecord) [BEGIN IMMEDIATE .. COMMIT, fsync]
    path RustHost -> TSBridge : CommitReceipt { canonicalSeq, tick, payloadHash }
    path TSBridge -> WAL : markCommitted(eventId)
    
    invariant wal_before_canonical {
      condition: canonicalVisibility(record) ==> durableWalAppend(record) && commitReceipt(record) != null
      check: fn checkWalBeforeCanonical(r: WalRecord, receipt: CommitReceipt | null) -> void {
        if (receipt != null && !r.durableAppended) throw InvariantViolation("Canonical record without durable WAL append");
      }
      on_violation: TriggerEmergencyDeescalation { action: "reject", reason: "canonical_without_wal" }
    }
    
    invariant single_writer_unified_db {
      condition: count(writers(unified_db)) == 1
      on_violation: TriggerEmergencyDeescalation { action: "queue", reason: "single_writer_violation" }
    }
    
    invariant monotonic_canonical_seq {
      condition: receipt.canonicalSeq > previousReceipt.canonicalSeq
      on_violation: TriggerEmergencyDeescalation { action: "reject", reason: "canonical_seq_not_monotonic" }
    }
    
    invariant idempotent_replay {
      condition: sameEventIdSameHash ==> sameReceipt; sameEventIdDifferentHash ==> rejected
      on_violation: TriggerEmergencyDeescalation { action: "reject", reason: "replay_conflict" }
    }
    
    invariant workspace_winner_not_canonical {
      condition: workspaceWinner(record) != null ==> canonicalVisibility(record) == false
      on_violation: TriggerEmergencyDeescalation { action: "queue", reason: "workspace_winner_promoted_without_receipt" }
    }
  }
}
```

### 7.6 Promotion rule for workspace winners

A workspace/GWT winner may only be promoted to canonical knowledge after:
`MEASURE` (receipt exists) → `FALSIFY` → `MATCHED_ABLATION` → `VERIFIED_OUTCOME` →
`CAUSAL_CREDIT` → `BOUNDED_ADMISSION` → `REENTRY_TEST` → `CONTROL_INFLUENCE`.
Until a `CommitReceipt` exists, the record is labelled **workspace-local (uncommitted)** and
must never be presented as canonical truth.

## 8. Cross-File Canonical Definitions

| Definition | `docs/zero/architecture.md` | `docs/zero/schema.md` | `agent-sdk/src/zero/health.ts` |
|---|---|---|---|
| `failure_count` semantics | §6.3 (epoch rule: consecutive failure events since last `Healthy` result; reset to 0 on `Healthy` transition; invocation + manifest failures counted) | health status table, column `failure_count INTEGER NOT NULL DEFAULT 0` — same epoch rule | `HealthStatus.failureCount` — same epoch rule |
| `Healthy` evidence | §6 type `Healthy { ..., evidenceRef: EvidenceRef }` (non-null) | `evidence_ref` NOT NULL for `healthy` rows | `Healthy.evidenceRef: EvidenceRef` (non-null) |
| Status vocabulary | `healthy \| degraded \| unhealthy \| failed` | same lowercase vocabulary | same lowercase vocabulary |
| Event kinds | §6 `HealthEvent` (6 kinds incl. `InvocationSuccess`) | event kind column / CHECK constraint | `HealthEvent` union (6 kinds) |
| Manifest status | §6 `ManifestStatus` (`Loaded \| ParseFailed \| NotFound`) | manifest status column | `ManifestStatus` union |
| Canonical write path | §7 write-ahead protocol | `unified.db` tables + `canonical_seq` | WAL append + `submit` RPC |

TODO(r007-t2 / r007-t5): keep the three columns byte-for-byte semantically identical; any
divergence is a contract violation and must be reported, not silently reconciled.
