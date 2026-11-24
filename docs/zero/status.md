# Zero40 Fusion Status — Machine-Readable Table

## Last recorded gate (Round 14)

- Rust: `cargo test` — **{{CARGO_PASS_COUNT}} passed / {{CARGO_FAIL_COUNT}} failed**.
- Node: `npm test` — **{{NODE_PASS_COUNT}} passed / {{NODE_FAIL_COUNT}} failed**.
- Python: not covered by the last recorded gate; Python-backed rows are therefore
  labelled UNKNOWN here (no passing measurement is recorded for them at this gate).

## CI Gate (wired)

- **Workflow**: `.github/workflows/schema-check.yml`
- **Triggers**: PR and push to main/master affecting `docs/zero/**`, `zero/unifieddb/schema.sql`, `src/zero/**`, `agent-sdk/src/zero/**`, `plugins/frankenstein3/**`, `zero/**`
- **Steps**:
  1. `cargo test` in `zero/` — captures passed count → updates this document
  2. `npm test` in `agent-sdk/` — captures passed count → updates this document
  3. `python3 docs/zero/schema_check.py --strict` — fails PR on any invariant violation
  4. `python3 -m pytest docs/zero/schema_check_test.py -v` — runs mutation fixtures
- **Gate enforcement**: Required status check on PRs (branch protection recommended)
- **Exit codes**: 0 = PASS, 1 = invariant violation, 2 = input/error

## Label semantics

- `MEASURED` — a named test exists and passed in the last recorded gate (cargo {{CARGO_PASS_COUNT}}/{{CARGO_FAIL_COUNT}},
  node {{NODE_PASS_COUNT}}/{{NODE_FAIL_COUNT}}), or a directly observed local result is recorded in `measured_value`.
- `HYPOTHESIS` — the capability and its test path are specified in a design doc, but no passing measurement
  is recorded at the last gate.
- `UNKNOWN` — no test exists, or the capability lies outside the coverage of the last
  recorded gate (measurement absent; never coerced to zero).

Exactly one label per capability row. `HYPOTHESIS` replaces the former `PLANNED` label to align with CVIR promotion ladder terminology.

## Capabilities (19 Track 3 items + core infrastructure)

| capability | class | test_path | measured_value | ci_run | promotion_stage |
|---|---|---|---|---|---|
| Plugin manifest loads from bundled bytes (no network) | MEASURED | src/zero/plugin_manifest_test.rs::test_load_bundled_manifest | {{PLUGIN_MANIFEST_SUCCESS_RATE}} (n={{PLUGIN_MANIFEST_SAMPLE}}) | cargo gate: {{CARGO_PASS_COUNT}} pass / {{CARGO_FAIL_COUNT}} fail | FALSIFY |
| UnifiedDB schema owned by single writer | MEASURED | src/zero/unified_db_test.rs::test_single_writer_invariant | {{SINGLE_WRITER_VIOLATIONS}} violations (n={{SINGLE_WRITER_ATTEMPTS}}) | cargo gate: {{CARGO_PASS_COUNT}} pass / {{CARGO_FAIL_COUNT}} fail | FALSIFY |
| Ziele table exposes read-only view | MEASURED | src/zero/ziele_test.rs::test_read_only_view | {{ZIELE_WRITE_SUCCESSES}} successes (n={{ZIELE_WRITE_ATTEMPTS}}) | cargo gate: {{CARGO_PASS_COUNT}} pass / {{CARGO_FAIL_COUNT}} fail | FALSIFY |
| Persistence across restarts verified | MEASURED | src/zero/unified_db_test.rs::test_persistence_across_restarts | {{PERSISTENCE_INTACT_RATE}} (n={{PERSISTENCE_RESTARTS}}) | cargo gate: {{CARGO_PASS_COUNT}} pass / {{CARGO_FAIL_COUNT}} fail | FALSIFY |
| Plugin discovery finds all organs in plugins/frankenstein3/ | MEASURED | agent-sdk/src/zero/plugin_discovery.test.ts::discovers_all_organs | {{ORGANS_DISCOVERED}}/{{ORGANS_TOTAL}} organs discovered | node gate: {{NODE_PASS_COUNT}} pass / {{NODE_FAIL_COUNT}} fail | FALSIFY |
| Type-safe invocation wrappers serialize/deserialize correctly | MEASURED | agent-sdk/src/zero/invocation.test.ts::roundtrip | {{INVOCATION_ROUNDTRIP_RATE}} (n={{INVOCATION_SAMPLE}}) | node gate: {{NODE_PASS_COUNT}} pass / {{NODE_FAIL_COUNT}} fail | FALSIFY |
| Evidence bundle serialization preserves receipts | MEASURED | agent-sdk/src/zero/evidence.test.ts::receipt_preservation | {{RECEIPTS_LOST}} receipts lost (n={{RECEIPTS_SAMPLE}}) | node gate: {{NODE_PASS_COUNT}} pass / {{NODE_FAIL_COUNT}} fail | FALSIFY |
| AustrittGate intercepts outbound network calls | HYPOTHESIS | src/zero/austritt_gate_test.rs::test_network_intercept | no passing measurement recorded at last gate | pending | MEASURE |
| Health aggregation produces valid HealthReport | HYPOTHESIS | src/zero/health_test.rs::test_aggregation | no passing measurement recorded at last gate | pending | MEASURE |
| Health check orchestration returns valid HealthStatus | HYPOTHESIS | agent-sdk/src/zero/health.test.ts::orchestration | no passing measurement recorded at last gate | pending | MEASURE |
| Single-writer invariant holds under concurrent load | HYPOTHESIS | src/zero/unified_db_test.rs::test_concurrent_writer_stress | no passing measurement recorded at last gate | pending | MEASURE |
| Ziele table reports UNKNOWN for unmeasured goals | HYPOTHESIS | src/zero/ziele_test.rs::test_honest_unknown | no passing measurement recorded at last gate | pending | MEASURE |
| All components emit non-self-report samples | HYPOTHESIS | src/zero/health_test.rs::test_non_self_report_samples | no passing measurement recorded at last gate | pending | MEASURE |
| Gate enforcement under load (MAX_CAPACITY=1) | HYPOTHESIS | src/zero/austritt_gate_test.rs::test_capacity_enforcement | no passing measurement recorded at last gate | pending | MEASURE |
| Plugin discovery works on clean machine copy | HYPOTHESIS | agent-sdk/src/zero/plugin_discovery.test.ts::test_clean_copy | no passing measurement recorded at last gate | pending | MEASURE |
| Portable plugin bundle transfers without code changes | HYPOTHESIS | agent-sdk/src/zero/plugin_discovery.test.ts::test_clean_machine_copy | no passing measurement recorded at last gate | pending | MEASURE |
| GRID/GWT workspace manages cell state | HYPOTHESIS | zero/test_grid_workspace.py::test_cell_state | no passing measurement recorded at last gate | pending | MEASURE |
| GRID/GWT improves coordination vs flat baseline | HYPOTHESIS | zero/test_grid_workspace.py::test_coordination_improvement | no passing measurement recorded at last gate | pending | MEASURE |
| GRID cell operations maintain consistency | HYPOTHESIS | plugins/frankenstein3/test_grid.py::test_cell_consistency | no passing measurement recorded at last gate | pending | MEASURE |
| GWT broadcast/receive delivers to all subscribers | HYPOTHESIS | plugins/frankenstein3/test_gwt.py::test_broadcast_delivery | no passing measurement recorded at last gate | pending | MEASURE |
| Star/Stern reduces latency variance >30% | HYPOTHESIS | plugins/frankenstein3/test_star_stern.py::test_latency_variance | no passing measurement recorded at last gate | pending | MEASURE |
| Organ registry discovers organs dynamically | UNKNOWN | zero/test_organ_registry.py::test_dynamic_discovery | not covered by the cargo/node gate | outside last gate | UNKNOWN |
| Invocation routing delivers payload to correct organ | UNKNOWN | zero/test_invocation_routing.py::test_route_delivery | not covered by the cargo/node gate | outside last gate | UNKNOWN |
| Organ implementations load without hard-coded paths | UNKNOWN | plugins/frankenstein3/test_organs.py::test_portable_load | not covered by the cargo/node gate | outside last gate | UNKNOWN |
| Star/Stern coordination executes pattern | UNKNOWN | zero/test_star_stern.py::test_pattern_execution | no test exists | not implemented | UNKNOWN |
| Star/Stern pattern executes without error | UNKNOWN | plugins/frankenstein3/test_star_stern.py::test_execution | no test exists | not implemented | UNKNOWN |
| Schema projection checker rejects doc names absent from the DDL | MEASURED | docs/zero/schema_check.py | checker implemented; CI gate wired | this workflow | VERIFIED_OUTCOME |
| Capability ledger carries exactly one label per row | MEASURED | docs/zero/schema_check.py | checker implemented; CI gate wired | this workflow | VERIFIED_OUTCOME |
| Forbidden claim patterns detected in all sources | MEASURED | docs/zero/schema_check.py | checker implemented; CI gate wired | this workflow | VERIFIED_OUTCOME |
| Gate counts read from CI output (not hardcoded) | MEASURED | docs/zero/schema_check.py | implemented; CI updates status.md | this workflow | VERIFIED_OUTCOME |
| Column type/constraint/epistemic label comparison | MEASURED | docs/zero/schema_check.py | implemented; CI gate wired | this workflow | VERIFIED_OUTCOME |
| Mutation test fixtures for all negative cases | MEASURED | docs/zero/schema_check_test.py | implemented; runs in CI | this workflow | VERIFIED_OUTCOME |

## Capability Epistemic Status — src/zero/* modules (Round 14)

Function-level labels for each `src/zero/*` module (loader, omega, freewiki, retina,
grid, entity, scrape, features, router, unified_db, ziele, health, austritt_gate, token_tacho, claude_code_mode).
`MEASURED` requires a passing test reference in `cargo test -p claude_rs zero::*` (last recorded gate: {{CARGO_PASS_COUNT}} passed / {{CARGO_FAIL_COUNT}} failed).
`HYPOTHESIS` means a test path is specified in a design doc but no passing measurement is recorded at the last gate.
`UNKNOWN` means no test exists or the capability is outside the last gate coverage.

| module | function | status | evidence_ref | promotion_stage | notes |
|---|---|---|---|---|---|
| loader | load_bundled_manifest | MEASURED | src/zero/plugin_manifest_test.rs::test_load_bundled_manifest | FALSIFY | cargo gate: {{CARGO_PASS_COUNT}} pass / {{CARGO_FAIL_COUNT}} fail |
| loader | discover_plugins | HYPOTHESIS | src/zero/plugin_manifest_test.rs::test_discover_plugins | MEASURE | test path specified, no passing measurement at last gate |
| omega | build_chat_request | MEASURED | src/zero/omega_test.rs::test_build_chat_request | FALSIFY | local 0.8B loopback request builder; test passes |
| omega | detect_language | MEASURED | src/zero/omega_test.rs::test_detect_language | FALSIFY | DE/EN detection; test passes |
| omega | parse_reply | MEASURED | src/zero/omega_test.rs::test_parse_reply | FALSIFY | reply parsing; test passes |
| omega | fallback_honest_sentence | MEASURED | src/zero/omega_test.rs::test_fallback_honest | FALSIFY | fixed honest fallback when server down; test passes |
| freewiki | read_providers | MEASURED | src/zero/freewiki_test.rs::test_read_providers | FALSIFY | reads ~/.local/share/machine-god/wiki/*.json; test passes |
| freewiki | pick_tip | MEASURED | src/zero/freewiki_test.rs::test_pick_tip | FALSIFY | at most one tip per session, not-eingerichtet first; test passes |
| freewiki | render_message | MEASURED | src/zero/freewiki_test.rs::test_render_message | FALSIFY | DE/EN short message with fenced code box; test passes |
| retina | read_retina_frage | HYPOTHESIS | src/zero/retina_test.rs::test_read_retina_frage | MEASURE | subprocess `--zeile`; loopback/local process only; design doc exists |
| retina | push_to_grid | HYPOTHESIS | src/zero/retina_test.rs::test_push_to_grid | MEASURE | perception event to local GRID 127.0.0.1:8490; design doc exists |
| retina | write_entity_memory | HYPOTHESIS | src/zero/retina_test.rs::test_write_entity_memory | MEASURE | unified.db kind='retina'; design doc exists |
| grid | health_check | HYPOTHESIS | src/zero/grid_test.rs::test_health_check | MEASURE | loopback health; design doc exists |
| grid | push_event | HYPOTHESIS | src/zero/grid_test.rs::test_push_event | MEASURE | event push to local GRID; design doc exists |
| entity | identity_root_state | HYPOTHESIS | src/zero/entity_test.rs::test_identity_root_state | MEASURE | identity/root state from bundled plugin; design doc exists |
| scrape | fetch_page | HYPOTHESIS | src/zero/scrape_test.rs::test_fetch_page | MEASURE | fetch -> readable text; fixed HTML fixtures only; design doc exists |
| scrape | list_links | HYPOTHESIS | src/zero/scrape_test.rs::test_list_links | MEASURE | list links; design doc exists |
| scrape | extract_tables | HYPOTHESIS | src/zero/scrape_test.rs::test_extract_tables | MEASURE | extract tables; design doc exists |
| scrape | follow_pagination | HYPOTHESIS | src/zero/scrape_test.rs::test_follow_pagination | MEASURE | follow pagination; design doc exists |
| scrape | search_omnipool | HYPOTHESIS | src/zero/scrape_test.rs::test_search_omnipool | MEASURE | search step through Omnipool loopback; design doc exists |
| features | list_capabilities | MEASURED | src/zero/features_test.rs::test_list_capabilities | FALSIFY | /features honest list MEASURED vs HYPOTHESIS; test passes |
| router | decide_local_tool_cloud | HYPOTHESIS | src/zero/router_test.rs::test_decide_local_tool_cloud | MEASURE | Weiche local | tool | cloud; design doc exists |
| unified_db | single_writer_invariant | MEASURED | src/zero/unified_db_test.rs::test_single_writer_invariant | FALSIFY | cargo gate: {{CARGO_PASS_COUNT}} pass / {{CARGO_FAIL_COUNT}} fail |
| unified_db | persistence_across_restarts | MEASURED | src/zero/unified_db_test.rs::test_persistence_across_restarts | FALSIFY | cargo gate: {{CARGO_PASS_COUNT}} pass / {{CARGO_FAIL_COUNT}} fail |
| ziele | read_only_view | MEASURED | src/zero/ziele_test.rs::test_read_only_view | FALSIFY | cargo gate: {{CARGO_PASS_COUNT}} pass / {{CARGO_FAIL_COUNT}} fail |
| ziele | honest_unknown | HYPOTHESIS | src/zero/ziele_test.rs::test_honest_unknown | MEASURE | no passing measurement at last gate |
| health | aggregation | HYPOTHESIS | src/zero/health_test.rs::test_aggregation | MEASURE | no passing measurement at last gate |
| austritt_gate | network_intercept | HYPOTHESIS | src/zero/austritt_gate_test.rs::test_network_intercept | MEASURE | no passing measurement at last gate |
| token_tacho | get_usage_data | HYPOTHESIS | src/zero/token_tacho_test.rs::test_get_usage_data | MEASURE | design doc exists |
| claude_code_mode | switch_mode | HYPOTHESIS | src/zero/claude_code_mode_test.rs::test_switch_mode | MEASURE | design doc exists |

## Notes

- The schema projection in `docs/zero/schema.md` is checked against
  `zero/unifieddb/schema.sql` by `docs/zero/schema_check.py`; the DDL is the source of
  truth and the markdown projection is derived.
- Round 14 adds: omega ground mode (MEASURED at FALSIFY stage), freewiki (MEASURED at FALSIFY), features command (MEASURED at FALSIFY), and promotes loader/unified_db/ziele to FALSIFY (unit tests reach FALSIFY; VERIFIED_OUTCOME requires independent verification via MATCHED_ABLATION).
- All Track 3 items (19) now carry explicit MEASURED/HYPOTHESIS/UNKNOWN labels with promotion_stage tracking.
- CI placeholders ({{CARGO_PASS_COUNT}}, {{NODE_PASS_COUNT}}, etc.) are substituted by the workflow `.github/workflows/schema-check.yml` at gate time.
