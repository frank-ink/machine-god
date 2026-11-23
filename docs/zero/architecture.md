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
    path RustHost -> RustHost : SelfMeasurement { schema: UnifiedDBSchema, goals: ZieleTable }
    path TSBridge -> TSBridge : BridgeHealth { latency_p99: Duration, error_rate: Ratio }
    path PythonZero -> PythonZero : OrganRegistrySync { discovered: Vec<OrganId>, failed: Vec<OrganId> }
  }
  
  // Component specifications with epistemic tags
  component RustHost {
    language = "Rust";
    crate = "zero";
    responsibilities = [
      "Plugin manifest loading (bundled, no network)" [MEASURED],
      "UnifiedDB schema ownership (single writer)" [MEASURED],
      "Ziele table exposure (read-only view)" [MEASURED],
      "AustrittGate enforcement (secret exit)" [HYPOTHESIS],
      "Health aggregation across boundaries" [HYPOTHESIS]
    ];
    tests = ["src/zero/plugin_manifest_test.rs", "src/zero/unified_db_test.rs", "src/zero/ziele_test.rs", "src/zero/austritt_gate_test.rs"];
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
      "Star/Stern coordination" [HYPOTHESIS],
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
      "Star/Stern pattern execution" [UNKNOWN]
    ];
    tests = ["plugins/frankenstein3/test_organs.py", "plugins/frankenstein3/test_grid.py", "plugins/frankenstein3/test_gwt.py"];
  }
  
  // GRF Transition Function: R_{t+1} = F(R_t, E_t)
  fn F(R_t: SystemState, E_t: EvidenceBundle) -> SystemState {
    // R_t = { unified_db: UnifiedDBState, ziele: ZieleTable, plugin_health: HealthMap, bridge_health: BridgeHealth, organ_registry: OrganRegistry }
    // E_t = { manifest_checksum: Blake3, invocation_receipts: Vec<Receipt>, test_results: Vec<TestResult>, measurement_samples: Vec<Sample> }
    let R_next = SystemState {
      unified_db: R_t.unified_db.apply_migrations(E_t.manifest_checksum),
      ziele: R_t.ziele.update_progress(E_t.test_results),
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
    condition: manifest.parse_result.kind == ParseError => health.status == HealthStatus.Failed
    check: fn checkManifestParseHealth(parseResult: ParseResult, health: HealthReport) -> void {
      if (parseResult.kind === "ParseError" && health.status !== HealthStatus.Failed) {
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
    claim: "AustrittGate prevents secret leakage by intercepting all outbound network calls at the Rust host boundary"
    class: HYPOTHESIS
    falsification: "Network call observed bypassing AustrittGate in integration test"
    promotion: MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> CAUSAL_CREDIT -> BOUNDED_ADMISSION -> REENTRY_TEST -> CONTROL_INFLUENCE
  }
  
  hypothesis H_GRID_GWT_WORKSPACE {
    claim: "GRID/GWT workspace provides measurable coordination improvement over flat message passing for multi-organ tasks"
    class: HYPOTHESIS
    falsification: "No statistically significant difference in task completion rate (p > 0.05) between GRID/GWT and flat baseline"
    promotion: MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> CAUSAL_CREDIT -> BOUNDED_ADMISSION -> REENTRY_TEST -> CONTROL_INFLUENCE
  }
  
  hypothesis H_STAR_STERN_COORDINATION {
    claim: "Star/Stern pattern reduces organ invocation latency variance by >30% vs round-robin"
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
  
  hypothesis H_ZIELE_TABLE_HONEST_UNKNOWN {
    claim: "Ziele table reports UNKNOWN (not 0, not 0.5) for any goal where measurement infrastructure is absent"
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
| Ziele table exposes read-only view | MEASURED | `src/zero/ziele_test.rs::test_read_only_view` | 0 write attempts succeeded (n=100) | `cargo test -p zero ziele` |
| AustrittGate intercepts outbound network calls | HYPOTHESIS | `src/zero/austritt_gate_test.rs::test_network_intercept` | NOT YET MEASURED | PENDING |
| Health aggregation produces valid HealthReport | HYPOTHESIS | `src/zero/health_test.rs::test_aggregation` | NOT YET MEASURED | PENDING |

### 2.2 TS Bridge (`agent-sdk/src/zero/`)

| Claim | Epistemic Class | Test Path | Measured Value | CI Run |
|-------|-----------------|-----------|----------------|--------|
| Plugin discovery finds all organs in plugins/frankenstein3/ | MEASURED | `agent-sdk/src/zero/plugin_discovery.test.ts::discovers_all_organs` | 12/12 organs discovered | `npm test -- plugin_discovery` |
| Type-safe invocation wrappers serialize/deserialize correctly | MEASURED | `agent-sdk/src/zero/invocation.test.ts::roundtrip` | 100% roundtrip fidelity (n=1000) | `npm test -- invocation` |
| Evidence bundle serialization preserves receipts | MEASURED | `agent-sdk/src/zero/evidence.test.ts::receipt_preservation` | 0 receipts lost (n=500) | `npm test -- evidence` |
| Health check orchestration returns valid HealthStatus | HYPOTHESIS | `agent-sdk/src/zero/health.test.ts::orchestration` | NOT YET MEASURED | PENDING |

### 2.3 Python Zero (`zero/`)

| Claim | Epistemic Class | Test Path | Measured Value | CI Run |
|-------|-----------------|-----------|----------------|--------|
| Organ registry discovers organs dynamically | MEASURED | `zero/test_organ_registry.py::test_dynamic_discovery` | 12/12 organs registered | `python -m pytest zero/test_organ_registry.py` |
| Invocation routing delivers payload to correct organ | MEASURED | `zero/test_invocation_routing.py::test_route_delivery` | 100% correct routing (n=200) | `python -m pytest zero/test_invocation_routing.py` |
| GRID/GWT workspace manages cell state | HYPOTHESIS | `zero/test_grid_workspace.py::test_cell_state` | NOT YET MEASURED | PENDING |
| Star/Stern coordination executes pattern | UNKNOWN | `zero/test_star_stern.py::test_pattern_execution` | NO TEST YET | NOT IMPLEMENTED |

### 2.4 Frankenstein3 Organs (`plugins/frankenstein3/`)

| Claim | Epistemic Class | Test Path | Measured Value | CI Run |
|-------|-----------------|-----------|----------------|--------|
| Organ implementations load without hard-coded paths | MEASURED | `plugins/frankenstein3/test_organs.py::test_portable_load` | Loads on 3 different machines | `python -m pytest plugins/frankenstein3/test_organs.py` |
| GRID cell operations maintain consistency | HYPOTHESIS | `plugins/frankenstein3/test_grid.py::test_cell_consistency` | NOT YET MEASURED | PENDING |
| GWT broadcast/receive delivers to all subscribers | HYPOTHESIS | `plugins/frankenstein3/test_gwt.py::test_broadcast_delivery` | NOT YET MEASURED | PENDING |
| Star/Stern pattern executes without error | UNKNOWN | `plugins/frankenstein3/test_star_stern.py::test_execution` | NO TEST YET | NOT IMPLEMENTED |

## 3. Fusion Data Flow (GRF: T_Omega = ∫ R_t ⊗ E_t dt)

```
R_t (SystemState) = {
  unified_db: UnifiedDBState { schema_version: u32, writer_pid: Pid, last_migration: Timestamp },
  ziele: ZieleTable { goals: Vec<GoalRow>, last_measured: Timestamp },
  plugin_health: HealthMap { plugin_id -> HealthStatus },
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
  ziele: update_goal_progress(R_t.ziele, E_t.test_results),
  plugin_health: aggregate_health(R_t.plugin_health, E_t.invocation_receipts),
  bridge_health: update_latency(R_t.bridge_health, E_t.measurement_samples),
  organ_registry: sync_registry(R_t.organ_registry, E_t.invocation_receipts)
}
```

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
| Reliable Memory | UnifiedDB + Ziele table + OrganRegistry | `test_persistence_across_restarts` passes |
| Self-Measurement | HealthReport + BridgeHealth + OrganMetrics | All components emit `Sample { method != "self_report" }` |
| Self-Correction Under Gates | AustrittGate + MAX_CAPACITY_1 + single_writer | `test_gate_enforcement_under_load` passes |
| Transfer Without New Code | Portable plugin bundle + fs-based discovery | `test_clean_machine_copy` passes |

## 6. Health State Machine (ClayCode: SPEC, not yet implemented)

```claycode
module zero_health {
  architecture HealthStateMachine {
    stateAuthority = "TSBridge";
    
    // ManifestStatus: separate from HealthStatus (parse-time vs runtime)
    type ManifestStatus =
      | ManifestParsed { manifest: PluginManifest, checksum: Blake3, at: Tick }
      | ManifestParseError { kind: "schema" | "checksum" | "io", message: String, at: Tick };
    
    // HealthStatus: runtime health with failureCount for Degraded/Unhealthy
    // Aligned with schema.md vocabulary: healthy | degraded | unhealthy | failed
    type HealthStatus =
      | Healthy { since: Tick, evidence: EvidenceRef }
      | Degraded { since: Tick, reason: DegradationReason, failureCount: u32, evidence: EvidenceRef }
      | Unhealthy { since: Tick, reason: FailureReason, failureCount: u32, evidence: EvidenceRef }
      | Failed { since: Tick, error: ParseError | Timeout | IOError, evidence: EvidenceRef };
    
    // ParseResult with explicit Kind (no silent defaults)
    type ParseResult =
      | Parsed { manifest: PluginManifest, checksum: Blake3 }
      | ParseError { kind: "schema" | "checksum" | "io", message: String, at: Tick };
    
    // HealthEvent: all inputs to the state machine (Kind discriminator)
    type HealthEvent =
      | ManifestParsed { receipt: EvidenceRef }
      | ManifestParseError { error: ParseError, receipt: EvidenceRef }
      | InvocationSuccess { receipt: EvidenceRef }
      | InvocationFailure { receipt: EvidenceRef }
      | HealthCheckTimeout
      | IOError { error: IOError };
    
    // Single transition table keyed by (stateKind, eventKind) — NOT full payload
    // stateKind ∈ { Healthy, Degraded, Unhealthy, Failed }
    // eventKind ∈ { ManifestParsed, ManifestParseError, InvocationSuccess, InvocationFailure, HealthCheckTimeout, IOError }
    transitionTable: Map<(StateKind, EventKind), NextStateSpec> = {
      // From Healthy
      (Healthy, ManifestParsed)         -> Healthy { since: tick, evidence: event.receipt }
      (Healthy, ManifestParseError)     -> Failed { since: tick, error: event.error, evidence: event.receipt }
      (Healthy, InvocationSuccess)      -> Healthy { since: tick, evidence: event.receipt }
      (Healthy, InvocationFailure)      -> Degraded { since: tick, reason: "invocation_failure", failureCount: 1, evidence: event.receipt }
      (Healthy, HealthCheckTimeout)     -> Failed { since: tick, error: Timeout, evidence: missing }
      (Healthy, IOError)                -> Failed { since: tick, error: event.error, evidence: missing }
      
      // From Degraded
      (Degraded, ManifestParsed)         -> Healthy { since: tick, evidence: event.receipt }
      (Degraded, ManifestParseError)     -> Failed { since: tick, error: event.error, evidence: event.receipt }
      (Degraded, InvocationSuccess)      -> Healthy { since: tick, evidence: event.receipt }
      (Degraded, InvocationFailure)      -> Unhealthy { since: tick, reason: "repeated_failure", failureCount: state.failureCount + 1, evidence: event.receipt }
      (Degraded, HealthCheckTimeout)     -> Failed { since: tick, error: Timeout, evidence: missing }
      (Degraded, IOError)                -> Failed { since: tick, error: event.error, evidence: missing }
      
      // From Unhealthy
      (Unhealthy, ManifestParsed)         -> Healthy { since: tick, evidence: event.receipt }
      (Unhealthy, ManifestParseError)     -> Failed { since: tick, error: event.error, evidence: event.receipt }
      (Unhealthy, InvocationSuccess)      -> Degraded { since: tick, reason: "recovering", failureCount: state.failureCount, evidence: event.receipt }
      (Unhealthy, InvocationFailure)      -> Unhealthy { since: tick, reason: "persistent_failure", failureCount: state.failureCount + 1, evidence: event.receipt }
      (Unhealthy, HealthCheckTimeout)     -> Failed { since: tick, error: Timeout, evidence: missing }
      (Unhealthy, IOError)                -> Failed { since: tick, error: event.error, evidence: missing }
      
      // From Failed (terminal for this check cycle; requires re-check to exit)
      (Failed, ManifestParsed)         -> Healthy { since: tick, evidence: event.receipt }
      (Failed, ManifestParseError)     -> Failed { since: tick, error: event.error, evidence: event.receipt }
      (Failed, InvocationSuccess)      -> Failed { since: tick, error: IOError("unexpected"), evidence: event.receipt }
      (Failed, InvocationFailure)      -> Failed { since: tick, error: IOError("unexpected"), evidence: event.receipt }
      (Failed, HealthCheckTimeout)     -> Failed { since: tick, error: Timeout, evidence: missing }
      (Failed, IOError)                -> Failed { since: tick, error: event.error, evidence: missing }
    };
    
    // Design-by-Contract: transition function with pre/post conditions
    // tick parameter replaces now() — precedence is functional order, not wall-clock
    fn transition(current: HealthStatus, event: HealthEvent, tick: Tick): HealthStatus
      requires: transitionTable.containsKey((current.kind, event.kind))
      requires: current != null && event != null
      ensures: result != null
      ensures: transitionTable.get((current.kind, event.kind)).matches(result)
      ensures: // Failed only reachable via parse error, timeout, or IO error
        (result.kind == "Failed" ==> event.kind in ["ManifestParseError", "HealthCheckTimeout", "IOError"])
      ensures: // failureCount increments only on failure transitions from Degraded/Unhealthy
        (event.kind == "InvocationFailure" && current.kind in ["Degraded", "Unhealthy"] ==> 
         result.failureCount == current.failureCount + 1)
      ensures: // failureCount resets to 1 on first failure from Healthy
        (event.kind == "InvocationFailure" && current.kind == "Healthy" ==> result.failureCount == 1)
      ensures: // failureCount preserved on recovery transitions
        (event.kind == "InvocationSuccess" && current.kind in ["Degraded", "Unhealthy"] ==> 
         result.failureCount == current.failureCount)
    {
      let spec = transitionTable.get((current.kind, event.kind))!;
      return spec.instantiate(current, event, tick);
    }
    
    // Executable invariant check (SPEC: not yet implemented)
    // Throws InvariantViolationError if manifest parse error does not yield Failed status
    fn checkManifestParseHealthInvariant(parseResult: ParseResult, health: HealthStatus): void {
      if (parseResult.kind === "ParseError" && health.kind !== "Failed") {
        throw new InvariantViolationError(
          `Manifest parse error must produce HealthStatus.Failed, got ${health.kind}`
        );
      }
    }
    
    // ON_VIOLATION -> TriggerEmergencyDeescalation with queue/reject action
    // Restored per acceptance criteria
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
