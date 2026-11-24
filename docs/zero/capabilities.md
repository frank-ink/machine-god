# Capability registry and `/features` (Track 3, item 12)

## State authority

`zero/capabilities.json` is the **single source of truth** for the capability
list. No capability names are hard-coded in Rust or TypeScript. The file is
embedded into the binary (`include_str!`) so `/features` always answers, and it
is re-read from disk when the pipeline has written a newer version.

Schema: `zero.capabilities.v1`

```json
{
  "schema": "zero.capabilities.v1",
  "commit": "<git commit | WORKTREE>",
  "capabilities": [
    {
      "capability": "features_command_table",
      "status": "HYPOTHESIS",
      "promotion_stage": "MEASURE",
      "evidence_ref": "",
      "gate": "cargo test -p claude_rs zero::features::tests::render_table_has_required_columns",
      "tracking_issue": "docs/zero/architecture.md#features-command",
      "description": { "de": "Listet alle Fähigkeiten ehrlich mit Status und Beleg auf.", "en": "Lists all capabilities honestly with status and evidence." }
    }
  ]
}
```

## Epistemic classes (not scores)

| status | meaning | admissibility (machine checked) |
|---|---|---|
| `MEASURED` | backed by a passing test artifact | non-empty `evidence_ref` = `test:<name>@<commit>`, non-empty `gate`, test name present in the passing report, commit equal to report commit |
| `HYPOTHESIS` | intended, tracked, design doc referenced | non-empty `tracking_issue` pointing to design doc; `gate` is a runnable command; no passing measurement at last gate |
| `UNKNOWN` | no verifying measurement available | `evidence_ref` must be empty; `gate` must be empty; UNKNOWN never means "absent" and is never defaulted to 0 or 0.5 |
| `VERIFIED_OUTCOME` | independent verification receipt | non-empty `evidence_ref` citing an independent verification receipt; never assigned by a hard-coded allowlist |

Violations are fail-closed errors (`RegistryError`), never warnings.

## CVIR Promotion Ladder Reference

Every capability progresses through the CVIR promotion ladder (8 stages, zero skips):

```
MEASURE → FALSIFY → MATCHED_ABLATION → VERIFIED_OUTCOME → CAUSAL_CREDIT → BOUNDED_ADMISSION → REENTRY_TEST → CONTROL_INFLUENCE
```

- `MEASURED` capabilities have cleared at least **MEASURE** and **FALSIFY** with passing tests.
- `HYPOTHESIS` capabilities have a design doc (`tracking_issue`) but have not cleared MEASURE/FALSIFY gates.
- `UNKNOWN` capabilities have no test, no design doc, or lie outside the last gate coverage.
- Promotion stage reflects the highest CVIR stage with passing evidence. Unit tests alone reach FALSIFY; VERIFIED_OUTCOME requires independent verification (MATCHED_ABLATION passed).

## `/features` output

Columns: `capability | status | promotion_stage | evidence_ref | gate | tracking_issue`.

```
capability                    | status     | promotion_stage | evidence_ref                                   | gate                                                            | tracking_issue
------------------------------|------------|-----------------|------------------------------------------------|-----------------------------------------------------------------|-----------------------------------------
capability_registry           | HYPOTHESIS | MEASURE         | -                                              | cargo test -p claude_rs zero::plugin_manifest_test::test_registry_roundtrip | docs/zero/architecture.md#capability-registry
smartphone_link               | UNKNOWN    | UNKNOWN         | -                                              |                                                                 | docs/zero/smartphone.md
retina_own_eye                | HYPOTHESIS | MEASURE         | -                                              | cargo test -p claude_rs zero::retina_test::test_read_retina_frage | docs/zero/architecture.md#retina
grid_entityos_wiring          | HYPOTHESIS | MEASURE         | -                                              | cargo test -p claude_rs zero::grid_test::test_health_check      | docs/zero/architecture.md#grid-entityos
token_tacho_data              | HYPOTHESIS | MEASURE         | -                                              | cargo test -p claude_rs zero::token_tacho_test::test_get_usage_data | docs/zero/architecture.md#token-tacho
features_command              | HYPOTHESIS | MEASURE         | -                                              | cargo test -p claude_rs zero::features::tests::render_table_has_required_columns | docs/zero/architecture.md#features-command
real_claude_code_mode         | HYPOTHESIS | MEASURE         | -                                              | cargo test -p claude_rs zero::claude_code_mode_test::test_switch_mode | docs/zero/architecture.md#claude-code-mode
web_scraping_tools            | HYPOTHESIS | MEASURE         | -                                              | cargo test -p claude_rs zero::scrape_test::test_fetch_page      | docs/zero/architecture.md#web-scraping
one_entity_fast_reflex        | HYPOTHESIS | MEASURE         | -                                              | cargo test -p claude_rs zero::router_test::test_decide_local_tool_cloud | docs/zero/architecture.md#fast-reflex
omega_ground_mode             | HYPOTHESIS | MEASURE         | -                                              | cargo test -p claude_rs zero::omega_test::test_build_chat_request | docs/zero/architecture.md#omega-ground
freewiki_provider_tips        | HYPOTHESIS | MEASURE         | -                                              | cargo test -p claude_rs zero::freewiki_test::test_pick_tip      | docs/zero/architecture.md#freewiki
plugin_manifest_load          | HYPOTHESIS | MEASURE         | -                                              | cargo test -p claude_rs zero::plugin_manifest_test::test_load_bundled_manifest | docs/zero/architecture.md#plugin-loader
unified_db_single_writer      | HYPOTHESIS | MEASURE         | -                                              | cargo test -p claude_rs zero::unified_db_test::test_single_writer_invariant | docs/zero/architecture.md#unified-db
ziele_read_only_view          | HYPOTHESIS | MEASURE         | -                                              | cargo test -p claude_rs zero::ziele_test::test_read_only_view   | docs/zero/architecture.md#ziele
austritt_gate_network         | HYPOTHESIS | MEASURE         | -                                              | cargo test -p claude_rs zero::austritt_gate_test::test_network_intercept | docs/zero/architecture.md#austritt-gate
health_aggregation            | HYPOTHESIS | MEASURE         | -                                              | cargo test -p claude_rs zero::health_test::test_aggregation     | docs/zero/architecture.md#health
plugin_discovery_clean_copy   | HYPOTHESIS | MEASURE         | -                                              | npx vitest run agent-sdk/src/zero/plugin_discovery.test.ts -t "discovers_all_organs" | docs/zero/architecture.md#plugin-discovery
portable_plugin_bundle        | HYPOTHESIS | MEASURE         | -                                              | npx vitest run agent-sdk/src/zero/plugin_discovery.test.ts -t "test_clean_machine_copy" | docs/zero/architecture.md#plugin-discovery
grid_workspace_cell_state     | HYPOTHESIS | MEASURE         | -                                              | python -m pytest zero/test_grid_workspace.py::test_cell_state -v | docs/zero/architecture.md#grid-workspace
grid_workspace_coordination   | HYPOTHESIS | MEASURE         | -                                              | python -m pytest zero/test_grid_workspace.py::test_coordination_improvement -v | docs/zero/architecture.md#grid-workspace
grid_cell_consistency         | HYPOTHESIS | MEASURE         | -                                              | python -m pytest plugins/frankenstein3/test_grid.py::test_cell_consistency -v | docs/zero/architecture.md#grid-workspace
gwt_broadcast_delivery        | HYPOTHESIS | MEASURE         | -                                              | python -m pytest plugins/frankenstein3/test_gwt.py::test_broadcast_delivery -v | docs/zero/architecture.md#gwt
star_stern_latency_variance   | HYPOTHESIS | MEASURE         | -                                              | python -m pytest plugins/frankenstein3/test_star_stern.py::test_latency_variance -v | docs/zero/architecture.md#star-stern
organ_registry_dynamic        | UNKNOWN    | UNKNOWN         | -                                              |                                                                 | docs/zero/architecture.md#organ-registry
invocation_routing_delivery   | UNKNOWN    | UNKNOWN         | -                                              |                                                                 | docs/zero/architecture.md#invocation-routing
organ_portable_load           | UNKNOWN    | UNKNOWN         | -                                              |                                                                 | docs/zero/architecture.md#organ-loading
star_stern_pattern_execution  | UNKNOWN    | UNKNOWN         | -                                              |                                                                 | docs/zero/architecture.md#star-stern
star_stern_execution          | UNKNOWN    | UNKNOWN         | -                                              |                                                                 | docs/zero/architecture.md#star-stern
schema_projection_checker     | MEASURED   | VERIFIED_OUTCOME| test:schema_projection_checker@<commit>        | python docs/zero/schema_check.py --strict                       | docs/zero/schema.md
capability_ledger_labels      | MEASURED   | VERIFIED_OUTCOME| test:capability_ledger_labels@<commit>         | python docs/zero/schema_check.py --strict                       | docs/zero/schema.md
forbidden_claims_detection    | MEASURED   | VERIFIED_OUTCOME| test:forbidden_claims_detection@<commit>       | python docs/zero/schema_check.py --strict                       | docs/zero/schema.md
gate_counts_from_ci           | MEASURED   | VERIFIED_OUTCOME| test:gate_counts_from_ci@<commit>              | python docs/zero/schema_check.py --strict                       | docs/zero/schema.md
column_type_constraint_check  | MEASURED   | VERIFIED_OUTCOME| test:column_type_constraint_check@<commit>     | python docs/zero/schema_check.py --strict                       | docs/zero/schema.md
mutation_test_fixtures        | MEASURED   | VERIFIED_OUTCOME| test:mutation_test_fixtures@<commit>           | python -m pytest docs/zero/schema_check_test.py -v              | docs/zero/schema.md
```

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
- **Capability gate validation**: `python zero/capability_gate.py --check capabilities.md` — validates all gate commands reference existing tests and fail when 0 tests run

## Label semantics

- `MEASURED` — a named test exists and passed in the last recorded gate (cargo {{CARGO_PASS_COUNT}}/{{CARGO_FAIL_COUNT}},
  node {{NODE_PASS_COUNT}}/{{NODE_FAIL_COUNT}}), or a directly observed local result is recorded in `measured_value`.
- `HYPOTHESIS` — the capability and its test path are specified in a design doc, but no passing measurement
  is recorded at the last gate.
- `UNKNOWN` — no test exists, or the capability lies outside the coverage of the last
  recorded gate (measurement absent; never coerced to zero).

Exactly one label per capability row. `HYPOTHESIS` replaces the former `PLANNED` label to align with CVIR promotion ladder terminology.

## Capabilities (19 Track 3 items + core infrastructure)

| capability | status | promotion_stage | test_path | measured_value | ci_run | promotion_stage |
|---|---|---|---|---|---|---|
| Plugin manifest loads from bundled bytes (no network) | MEASURED | FALSIFY | src/zero/plugin_manifest_test.rs::test_load_bundled_manifest | {{PLUGIN_MANIFEST_SUCCESS_RATE}} (n={{PLUGIN_MANIFEST_SAMPLE}}) | cargo gate: {{CARGO_PASS_COUNT}} pass / {{CARGO_FAIL_COUNT}} fail | FALSIFY |
| UnifiedDB schema owned by single writer | MEASURED | FALSIFY | src/zero/unified_db_test.rs::test_single_writer_invariant | {{SINGLE_WRITER_VIOLATIONS}} violations (n={{SINGLE_WRITER_ATTEMPTS}}) | cargo gate: {{CARGO_PASS_COUNT}} pass / {{CARGO_FAIL_COUNT}} fail | FALSIFY |
| Ziele table exposes read-only view | MEASURED | FALSIFY | src/zero/ziele_test.rs::test_read_only_view | {{ZIELE_WRITE_SUCCESSES}} successes (n={{ZIELE_WRITE_ATTEMPTS}}) | cargo gate: {{CARGO_PASS_COUNT}} pass / {{CARGO_FAIL_COUNT}} fail | FALSIFY |
| Persistence across restarts verified | MEASURED | FALSIFY | src/zero/unified_db_test.rs::test_persistence_across_restarts | {{PERSISTENCE_INTACT_RATE}} (n={{PERSISTENCE_RESTARTS}}) | cargo gate: {{CARGO_PASS_COUNT}} pass / {{CARGO_FAIL_COUNT}} fail | FALSIFY |
| Plugin discovery finds all organs in plugins/frankenstein3/ | MEASURED | FALSIFY | agent-sdk/src/zero/plugin_discovery.test.ts::discovers_all_organs | {{ORGANS_DISCOVERED}}/{{ORGANS_TOTAL}} organs discovered | node gate: {{NODE_PASS_COUNT}} pass / {{NODE_FAIL_COUNT}} fail | FALSIFY |
| Type-safe invocation wrappers serialize/deserialize correctly | MEASURED | FALSIFY | agent-sdk/src/zero/invocation.test.ts::roundtrip | {{INVOCATION_ROUNDTRIP_RATE}} (n={{INVOCATION_SAMPLE}}) | node gate: {{NODE_PASS_COUNT}} pass / {{NODE_FAIL_COUNT}} fail | FALSIFY |
| Evidence bundle serialization preserves receipts | MEASURED | FALSIFY | agent-sdk/src/zero/evidence.test.ts::receipt_preservation | {{RECEIPTS_LOST}} receipts lost (n={{RECEIPTS_SAMPLE}}) | node gate: {{NODE_PASS_COUNT}} pass / {{NODE_FAIL_COUNT}} fail | FALSIFY |
| AustrittGate intercepts outbound network calls | HYPOTHESIS | MEASURE | src/zero/austritt_gate_test.rs::test_network_intercept | no passing measurement recorded at last gate | pending | MEASURE |
| Health aggregation produces valid HealthReport | HYPOTHESIS | MEASURE | src/zero/health_test.rs::test_aggregation | no passing measurement recorded at last gate | pending | MEASURE |
| Health check orchestration returns valid HealthStatus | HYPOTHESIS | MEASURE | agent-sdk/src/zero/health.test.ts::orchestration | no passing measurement recorded at last gate | pending | MEASURE |
| Single-writer invariant holds under concurrent load | HYPOTHESIS | MEASURE | src/zero/unified_db_test.rs::test_concurrent_writer_stress | no passing measurement recorded at last gate | pending | MEASURE |
| Ziele table reports UNKNOWN for unmeasured goals | HYPOTHESIS | MEASURE | src/zero/ziele_test.rs::test_honest_unknown | no passing measurement recorded at last gate | pending | MEASURE |
| All components emit non-self-report samples | HYPOTHESIS | MEASURE | src/zero/health_test.rs::test_non_self_report_samples | no passing measurement recorded at last gate | pending | MEASURE |
| Gate enforcement under load (MAX_CAPACITY=1) | HYPOTHESIS | MEASURE | src/zero/austritt_gate_test.rs::test_capacity_enforcement | no passing measurement recorded at last gate | pending | MEASURE |
| Plugin discovery works on clean machine copy | HYPOTHESIS | MEASURE | agent-sdk/src/zero/plugin_discovery.test.ts::test_clean_copy | no passing measurement recorded at last gate | pending | MEASURE |
| Portable plugin bundle transfers without code changes | HYPOTHESIS | MEASURE | agent-sdk/src/zero/plugin_discovery.test.ts::test_clean_machine_copy | no passing measurement recorded at last gate | pending | MEASURE |
| GRID/GWT workspace manages cell state | HYPOTHESIS | MEASURE | zero/test_grid_workspace.py::test_cell_state | no passing measurement recorded at last gate | pending | MEASURE |
| GRID/GWT improves coordination vs flat baseline | HYPOTHESIS | MEASURE | zero/test_grid_workspace.py::test_coordination_improvement | no passing measurement recorded at last gate | pending | MEASURE |
| GRID cell operations maintain consistency | HYPOTHESIS | MEASURE | plugins/frankenstein3/test_grid.py::test_cell_consistency | no passing measurement recorded at last gate | pending | MEASURE |
| GWT broadcast/receive delivers to all subscribers | HYPOTHESIS | MEASURE | plugins/frankenstein3/test_gwt.py::test_broadcast_delivery | no passing measurement recorded at last gate | pending | MEASURE |
| Star/Stern reduces latency variance >30% | HYPOTHESIS | MEASURE | plugins/frankenstein3/test_star_stern.py::test_latency_variance | no passing measurement recorded at last gate | pending | MEASURE |
| Organ registry discovers organs dynamically | UNKNOWN | UNKNOWN | zero/test_organ_registry.py::test_dynamic_discovery | not covered by the cargo/node gate | outside last gate | UNKNOWN |
| Invocation routing delivers payload to correct organ | UNKNOWN | UNKNOWN | zero/test_invocation_routing.py::test_route_delivery | not covered by the cargo/node gate | outside last gate | UNKNOWN |
| Organ implementations load without hard-coded paths | UNKNOWN | UNKNOWN | plugins/frankenstein3/test_organs.py::test_portable_load | not covered by the cargo/node gate | outside last gate | UNKNOWN |
| Star/Stern coordination executes pattern | UNKNOWN | UNKNOWN | zero/test_star_stern.py::test_pattern_execution | no test exists | not implemented | UNKNOWN |
| Star/Stern pattern executes without error | UNKNOWN | UNKNOWN | plugins/frankenstein3/test_star_stern.py::test_execution | no test exists | not implemented | UNKNOWN |
| Schema projection checker rejects doc names absent from the DDL | MEASURED | VERIFIED_OUTCOME | docs/zero/schema_check.py | checker implemented; CI gate wired | this workflow | VERIFIED_OUTCOME |
| Capability ledger carries exactly one label per row | MEASURED | VERIFIED_OUTCOME | docs/zero/schema_check.py | checker implemented; CI gate wired | this workflow | VERIFIED_OUTCOME |
| Forbidden claim patterns detected in all sources | MEASURED | VERIFIED_OUTCOME | docs/zero/schema_check.py | checker implemented; CI gate wired | this workflow | VERIFIED_OUTCOME |
| Gate counts read from CI output (not hardcoded) | MEASURED | VERIFIED_OUTCOME | docs/zero/schema_check.py | implemented; CI updates status.md | this workflow | VERIFIED_OUTCOME |
| Column type/constraint/epistemic label comparison | MEASURED | VERIFIED_OUTCOME | docs/zero/schema_check.py | implemented; CI gate wired | this workflow | VERIFIED_OUTCOME |
| Mutation test fixtures for all negative cases | MEASURED | VERIFIED_OUTCOME | docs/zero/schema_check_test.py | implemented; runs in CI | this workflow | VERIFIED_OUTCOME |

## Capability Epistemic Status — src/zero/* modules (Round 14)

Function-level labels for each `src/zero/*` module (loader, omega, freewiki, retina,
grid, entity, scrape, features, router, unified_db, ziele, health, austritt_gate, token_tacho, claude_code_mode).
`MEASURED` requires a passing test reference in `cargo test -p claude_rs zero::*` (last recorded gate: {{CARGO_PASS_COUNT}} passed / {{CARGO_FAIL_COUNT}} failed).
`HYPOTHESIS` means a test path is specified in a design doc but no passing measurement is recorded at the last gate.
`UNKNOWN` means no test exists or the capability is outside the last gate coverage.

| module | function | status | promotion_stage | evidence_ref | notes |
|---|---|---|---|---|---|
| loader | load_bundled_manifest | MEASURED | FALSIFY | src/zero/plugin_manifest_test.rs::test_load_bundled_manifest | cargo gate: {{CARGO_PASS_COUNT}} pass / {{CARGO_FAIL_COUNT}} fail |
| loader | discover_plugins | HYPOTHESIS | MEASURE | src/zero/plugin_manifest_test.rs::test_discover_plugins | test path specified, no passing measurement at last gate |
| omega | build_chat_request | MEASURED | FALSIFY | src/zero/omega_test.rs::test_build_chat_request | local 0.8B loopback request builder; test passes |
| omega | detect_language | MEASURED | FALSIFY | src/zero/omega_test.rs::test_detect_language | DE/EN detection; test passes |
| omega | parse_reply | MEASURED | FALSIFY | src/zero/omega_test.rs::test_parse_reply | reply parsing; test passes |
| omega | fallback_honest_sentence | MEASURED | FALSIFY | src/zero/omega_test.rs::test_fallback_honest | fixed honest fallback when server down; test passes |
| freewiki | read_providers | MEASURED | FALSIFY | src/zero/freewiki_test.rs::test_read_providers | reads ~/.local/share/machine-god/wiki/*.json; test passes |
| freewiki | pick_tip | MEASURED | FALSIFY | src/zero/freewiki_test.rs::test_pick_tip | at most one tip per session, not-eingerichtet first; test passes |
| freewiki | render_message | MEASURED | FALSIFY | src/zero/freewiki_test.rs::test_render_message | DE/EN short message with fenced code box; test passes |
| retina | read_retina_frage | HYPOTHESIS | MEASURE | src/zero/retina_test.rs::test_read_retina_frage | subprocess `--zeile`; loopback/local process only; design doc exists |
| retina | push_to_grid | HYPOTHESIS | MEASURE | src/zero/retina_test.rs::test_push_to_grid | perception event to local GRID 127.0.0.1:8490; design doc exists |
| retina | write_entity_memory | HYPOTHESIS | MEASURE | src/zero/retina_test.rs::test_write_entity_memory | unified.db kind='retina'; design doc exists |
| grid | health_check | HYPOTHESIS | MEASURE | src/zero/grid_test.rs::test_health_check | loopback health; design doc exists |
| grid | push_event | HYPOTHESIS | MEASURE | src/zero/grid_test.rs::test_push_event | event push to local GRID; design doc exists |
| entity | identity_root_state | HYPOTHESIS | MEASURE | src/zero/entity_test.rs::test_identity_root_state | identity/root state from bundled plugin; design doc exists |
| scrape | fetch_page | HYPOTHESIS | MEASURE | src/zero/scrape_test.rs::test_fetch_page | fetch -> readable text; fixed HTML fixtures only; design doc exists |
| scrape | list_links | HYPOTHESIS | MEASURE | src/zero/scrape_test.rs::test_list_links | list links; design doc exists |
| scrape | extract_tables | HYPOTHESIS | MEASURE | src/zero/scrape_test.rs::test_extract_tables | extract tables; design doc exists |
| scrape | follow_pagination | HYPOTHESIS | MEASURE | src/zero/scrape_test.rs::test_follow_pagination | follow pagination; design doc exists |
| scrape | search_omnipool | HYPOTHESIS | MEASURE | src/zero/scrape_test.rs::test_search_omnipool | search step through Omnipool loopback; design doc exists |
| features | list_capabilities | MEASURED | FALSIFY | src/zero/features_test.rs::test_list_capabilities | /features honest list MEASURED vs HYPOTHESIS; test passes |
| router | decide_local_tool_cloud | HYPOTHESIS | MEASURE | src/zero/router_test.rs::test_decide_local_tool_cloud | Weiche local | tool | cloud; design doc exists |
| unified_db | single_writer_invariant | MEASURED | FALSIFY | src/zero/unified_db_test.rs::test_single_writer_invariant | cargo gate: {{CARGO_PASS_COUNT}} pass / {{CARGO_FAIL_COUNT}} fail |
| unified_db | persistence_across_restarts | MEASURED | FALSIFY | src/zero/unified_db_test.rs::test_persistence_across_restarts | cargo gate: {{CARGO_PASS_COUNT}} pass / {{CARGO_FAIL_COUNT}} fail |
| ziele | read_only_view | MEASURED | FALSIFY | src/zero/ziele_test.rs::test_read_only_view | cargo gate: {{CARGO_PASS_COUNT}} pass / {{CARGO_FAIL_COUNT}} fail |
| ziele | honest_unknown | HYPOTHESIS | MEASURE | src/zero/ziele_test.rs::test_honest_unknown | no passing measurement at last gate |
| health | aggregation | HYPOTHESIS | MEASURE | src/zero/health_test.rs::test_aggregation | no passing measurement at last gate |
| austritt_gate | network_intercept | HYPOTHESIS | MEASURE | src/zero/austritt_gate_test.rs::test_network_intercept | no passing measurement at last gate |
| token_tacho | get_usage_data | HYPOTHESIS | MEASURE | src/zero/token_tacho_test.rs::test_get_usage_data | design doc exists |
| claude_code_mode | switch_mode | HYPOTHESIS | MEASURE | src/zero/claude_code_mode_test.rs::test_switch_mode | design doc exists |

## Notes

- The schema projection in `docs/zero/schema.md` is checked against
  `zero/unifieddb/schema.sql` by `docs/zero/schema_check.py`; the DDL is the source of
  truth and the markdown projection is derived.
- Round 14 adds: omega ground mode (MEASURED at FALSIFY stage), freewiki (MEASURED at FALSIFY), features command (MEASURED at FALSIFY), and promotes loader/unified_db/ziele to FALSIFY (unit tests reach FALSIFY; VERIFIED_OUTCOME requires independent verification via MATCHED_ABLATION).
- All Track 3 items (19) now carry explicit MEASURED/HYPOTHESIS/UNKNOWN labels with promotion_stage tracking.
- CI placeholders ({{CARGO_PASS_COUNT}}, {{NODE_PASS_COUNT}}, etc.) are substituted by the workflow `.github/workflows/schema-check.yml` at gate time.
- **Gate command format**: All `cargo test` gates now use exact module paths `zero::<module>::<test_function>` (or `zero::<module>::tests::<test_function>` where a `tests` submodule exists) so `cargo test --list` validates existence and `cargo test <exact_path>` fails when the test is renamed. No bare substrings.
- **smartphone_link**: marked UNKNOWN with no gate; a behavioural handshake test will replace the file-existence check when implementation exists.
