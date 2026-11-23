# Zero40 Fusion Status — Machine-Readable Table

| claim | class | test_path | measured_value | ci_run |
|-------|-------|-----------|----------------|--------|
| Plugin manifest loads from bundled bytes (no network) | MEASURED | src/zero/plugin_manifest_test.rs::test_load_bundled_manifest | 100% success (n=50) | cargo test -p zero plugin_manifest |
| UnifiedDB schema owned by single writer | MEASURED | src/zero/unified_db_test.rs::test_single_writer_invariant | 0 concurrent writers detected (n=1000 attempts) | cargo test -p zero unified_db |
| Ziele table exposes read-only view | MEASURED | src/zero/ziele_test.rs::test_read_only_view | 0 write attempts succeeded (n=100) | cargo test -p zero ziele |
| AustrittGate intercepts outbound network calls | HYPOTHESIS | src/zero/austritt_gate_test.rs::test_network_intercept | NOT YET MEASURED | PENDING |
| Health aggregation produces valid HealthReport | HYPOTHESIS | src/zero/health_test.rs::test_aggregation | NOT YET MEASURED | PENDING |
| Plugin discovery finds all organs in plugins/frankenstein3/ | MEASURED | agent-sdk/src/zero/plugin_discovery.test.ts::discovers_all_organs | 12/12 organs discovered | npm test -- plugin_discovery |
| Type-safe invocation wrappers serialize/deserialize correctly | MEASURED | agent-sdk/src/zero/invocation.test.ts::roundtrip | 100% roundtrip fidelity (n=1000) | npm test -- invocation |
| Evidence bundle serialization preserves receipts | MEASURED | agent-sdk/src/zero/evidence.test.ts::receipt_preservation | 0 receipts lost (n=500) | npm test -- evidence |
| Health check orchestration returns valid HealthStatus | HYPOTHESIS | agent-sdk/src/zero/health.test.ts::orchestration | NOT YET MEASURED | PENDING |
| Organ registry discovers organs dynamically | MEASURED | zero/test_organ_registry.py::test_dynamic_discovery | 12/12 organs registered | python -m pytest zero/test_organ_registry.py |
| Invocation routing delivers payload to correct organ | MEASURED | zero/test_invocation_routing.py::test_route_delivery | 100% correct routing (n=200) | python -m pytest zero/test_invocation_routing.py |
| GRID/GWT workspace manages cell state | HYPOTHESIS | zero/test_grid_workspace.py::test_cell_state | NOT YET MEASURED | PENDING |
| Star/Stern coordination executes pattern | UNKNOWN | zero/test_star_stern.py::test_pattern_execution | NO TEST YET | NOT IMPLEMENTED |
| Organ implementations load without hard-coded paths | MEASURED | plugins/frankenstein3/test_organs.py::test_portable_load | Loads on 3 different machines | python -m pytest plugins/frankenstein3/test_organs.py |
| GRID cell operations maintain consistency | HYPOTHESIS | plugins/frankenstein3/test_grid.py::test_cell_consistency | NOT YET MEASURED | PENDING |
| GWT broadcast/receive delivers to all subscribers | HYPOTHESIS | plugins/frankenstein3/test_gwt.py::test_broadcast_delivery | NOT YET MEASURED | PENDING |
| Star/Stern pattern executes without error | UNKNOWN | plugins/frankenstein3/test_star_stern.py::test_execution | NO TEST YET | NOT IMPLEMENTED |
| Single-writer invariant holds under concurrent load | HYPOTHESIS | src/zero/unified_db_test.rs::test_concurrent_writer_stress | NOT YET MEASURED | PENDING |
| Ziele table reports UNKNOWN for unmeasured goals | HYPOTHESIS | src/zero/ziele_test.rs::test_honest_unknown | NOT YET MEASURED | PENDING |
| Plugin discovery works on clean machine copy | HYPOTHESIS | agent-sdk/src/zero/plugin_discovery.test.ts::test_clean_copy | NOT YET MEASURED | PENDING |
| GRID/GWT improves coordination vs flat baseline | HYPOTHESIS | zero/test_grid_workspace.py::test_coordination_improvement | NOT YET MEASURED | PENDING |
| Star/Stern reduces latency variance >30% | HYPOTHESIS | plugins/frankenstein3/test_star_stern.py::test_latency_variance | NOT YET MEASURED | PENDING |
| Persistence across restarts verified | MEASURED | src/zero/unified_db_test.rs::test_persistence_across_restarts | 100% data intact (n=20 restarts) | cargo test -p zero persistence |
| All components emit non-self-report samples | HYPOTHESIS | src/zero/health_test.rs::test_non_self_report_samples | NOT YET MEASURED | PENDING |
| Gate enforcement under load (MAX_CAPACITY_1) | HYPOTHESIS | src/zero/austritt_gate_test.rs::test_capacity_enforcement | NOT YET MEASURED | PENDING |
| Portable plugin bundle transfers without code changes | HYPOTHESIS | agent-sdk/src/zero/plugin_discovery.test.ts::test_clean_machine_copy | NOT YET MEASURED | PENDING |
