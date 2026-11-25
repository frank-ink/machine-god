# Capability Registry and `/features` (Track 3, item 12)

## State Authority

`docs/zero/capabilities.md` is the human-maintained source of truth for the
capability list until `zero/capabilities.json` is implemented. No capability
names are hard-coded in Rust or TypeScript.

Schema: `zero.capabilities.v1`

```json
{
  "schema": "zero.capabilities.v1",
  "commit": "<git commit | WORKTREE>",
  "capabilities": [
    {
      "capability": "plugin_manifest_load",
      "status": "HYPOTHESIS",
      "promotion_stage": "-",
      "test_path": "zero::plugin_manifest_test::test_load_bundled_manifest",
      "evidence_ref": "-",
      "gate": "cargo test -p machine_god zero::plugin_manifest_test::test_load_bundled_manifest",
      "tracking_issue": "docs/zero/architecture.md#plugin-manifest-loading"
    }
  ]
}
```

## Epistemic Classes (Not Scores)

| status | meaning | admissibility (machine checked) |
|---|---|---|
| `MEASURED` | backed by a passing test artifact | non-empty `evidence_ref` = `test:<name>@<commit>` or a receipt file in `docs/zero/gate_receipts/`, non-empty `gate`, test name present in the passing report, commit equal to report commit, `promotion_stage` != `-` |
| `HYPOTHESIS` | intended, tracked, design doc referenced | `evidence_ref` must be `-`; `promotion_stage` must be `-`; `tracking_issue` is a design-doc anchor; `gate` is a runnable command; `test_path` is the exact test function; no passing measurement at last gate |
| `UNKNOWN` | no verifying measurement available | `evidence_ref` must be `-`; `promotion_stage` must be `-`; `gate` must be `-`; `test_path` must be `-`; UNKNOWN never means "absent" and is never defaulted to 0 or 0.5 |
| `VERIFIED_OUTCOME` | independent verification receipt | non-empty `evidence_ref` citing an independent verification receipt file in `docs/zero/gate_receipts/`; never assigned by a hard-coded allowlist |

Violations are fail-closed errors (`RegistryError`), never warnings.

## CVIR Promotion Ladder Reference

Every capability progresses through the CVIR promotion ladder (8 stages, zero skips):

```
MEASURE → FALSIFY → MATCHED_ABLATION → VERIFIED_OUTCOME → CAUSAL_CREDIT → BOUNDED_ADMISSION → REENTRY_TEST → CONTROL_INFLUENCE
```

`promotion_stage` records the **highest CVIR stage with passing evidence** for that capability. It is not a target and never implies a skipped rung: a row may only list a stage that has a passing receipt, and `MEASURED` rows must show a stage other than `-`. `HYPOTHESIS` and `UNKNOWN` rows have `promotion_stage = '-'` because no stage has passing evidence yet.

## `/features` Output

The `/features` command renders the registry as a table with columns:
`capability | status | promotion_stage | test_path | evidence_ref | gate | tracking_issue`

## CI Gate (Wired)

- **Workflow**: `.github/workflows/schema-check.yml`
- **Triggers**: PR and push to main/master affecting `docs/zero/**`, `zero/unifieddb/schema.sql`, `src/zero/**`, `agent-sdk/src/zero/**`, `plugins/frankenstein3/**`, `zero/**`
- **Steps**:
  1. `cargo test` in `zero/` — captures passed count
  2. `npm test` in `agent-sdk/` — captures passed count
  3. `python3 docs/zero/schema_check.py --strict` — fails PR on any invariant violation
  4. `python3 -m pytest docs/zero/schema_check_test.py -v` — runs mutation fixtures
- **Gate enforcement**: Required status check on PRs (branch protection recommended)
- **Exit codes**: 0 = PASS, 1 = invariant violation, 2 = input/error
- **Capability gate validation**: `python zero/capability_gate.py --check docs/zero/capabilities.md` — validates all gate commands reference existing tests and fails when 0 tests run
- **Receipt policy**: Every `MEASURED` row must cite a receipt file in `docs/zero/gate_receipts/` that exists at the report commit. Every `VERIFIED_OUTCOME` row must cite an independent verification receipt file in `docs/zero/gate_receipts/`. Rows without a committed receipt are demoted to `HYPOTHESIS` or `UNKNOWN`.

## Label Semantics

- `MEASURED` — a named test exists and passed in the last recorded gate, and a committed gate receipt exists in `docs/zero/gate_receipts/`. `promotion_stage` is the highest CVIR stage with passing evidence. No rows currently hold this label unless a receipt is present.
- `HYPOTHESIS` — the capability and its test path are specified in a design doc (referenced by `tracking_issue`), but no passing measurement and no committed gate receipt exist. `evidence_ref = '-'` and `promotion_stage = '-'`.
- `UNKNOWN` — no test exists, or the capability lies outside the coverage of the last recorded gate (measurement absent; never coerced to zero). `evidence_ref = '-'` and `promotion_stage = '-'`.
- `VERIFIED_OUTCOME` — independent verification receipt exists in `docs/zero/gate_receipts/`; never assigned by a hard-coded allowlist.

Exactly one label per capability row. `HYPOTHESIS` replaces the former `PLANNED` label to align with CVIR promotion ladder terminology.

## Capabilities (Canonical Registry)

| capability | status | promotion_stage | test_path | evidence_ref | gate | tracking_issue |
|---|---|---|---|---|---|---|
| plugin_manifest_load | HYPOTHESIS | - | zero::plugin_manifest_test::test_load_bundled_manifest | - | cargo test -p machine_god zero::plugin_manifest_test::test_load_bundled_manifest | docs/zero/architecture.md#plugin-manifest-loading |
| unified_db_single_writer | VERIFIED_OUTCOME | VERIFIED_OUTCOME | zero::unified_db_test::test_single_writer_invariant | gate_receipts/verified_unified_db_single_writer.receipt | cargo test -p machine_god zero::unified_db_test::test_single_writer_invariant | docs/zero/architecture.md#unifieddb-single-writer |
| goals_read_only_view | HYPOTHESIS | - | zero::goals_test::test_read_only_view | - | cargo test -p machine_god zero::goals_test::test_read_only_view | docs/zero/architecture.md#goals-read-only-view |
| exit_gate_network | HYPOTHESIS | - | zero::exit_gate_test::test_network_intercept | - | cargo test -p machine_god zero::exit_gate_test::test_network_intercept | docs/zero/architecture.md#exit-gate-network |
| plugin_discovery_clean_copy | HYPOTHESIS | - | agent_sdk_zero_plugin_discovery_discovers_all_organs | - | npx vitest run agent-sdk/src/zero/plugin_discovery.test.ts -t "discovers_all_organs" | docs/zero/architecture.md#plugin-discovery |
| portable_plugin_bundle | HYPOTHESIS | - | agent_sdk_zero_plugin_discovery_test_clean_machine_copy | - | npx vitest run agent-sdk/src/zero/plugin_discovery.test.ts -t "test_clean_machine_copy" | docs/zero/architecture.md#portable-plugin-bundle |
| grid_workspace_cell_state | HYPOTHESIS | - | zero_test_grid_workspace_test_cell_state | - | python -m pytest zero/test_grid_workspace.py::test_cell_state -v | docs/zero/architecture.md#grid-workspace-cell-state |
| grid_workspace_coordination | HYPOTHESIS | - | zero_test_grid_workspace_test_coordination_improvement | - | python -m pytest zero/test_grid_workspace.py::test_coordination_improvement -v | docs/zero/architecture.md#grid-workspace-coordination |
| grid_cell_consistency | HYPOTHESIS | - | plugins_frankenstein3_test_grid_test_cell_consistency | - | python -m pytest plugins/frankenstein3/test_grid.py::test_cell_consistency -v | docs/zero/architecture.md#grid-cell-consistency |
| gwt_broadcast_delivery | HYPOTHESIS | - | plugins_frankenstein3_test_gwt_test_broadcast_delivery | - | python -m pytest plugins/frankenstein3/test_gwt.py::test_broadcast_delivery -v | docs/zero/architecture.md#gwt-broadcast-delivery |
| star_star_latency_variance | HYPOTHESIS | - | plugins_frankenstein3_test_star_star_test_latency_variance | - | python -m pytest plugins/frankenstein3/test_star_star.py::test_latency_variance -v | docs/zero/architecture.md#star-star-latency |
| omega_ground_mode | HYPOTHESIS | - | zero::omega_test::test_build_chat_request | - | cargo test -p machine_god zero::omega_test::test_build_chat_request | docs/zero/architecture.md#omega-ground-mode |
| freewiki_provider_tips | HYPOTHESIS | - | zero::freewiki_test::test_pick_tip | - | cargo test -p machine_god zero::freewiki_test::test_pick_tip | docs/zero/architecture.md#freewiki-provider-tips |
| retina_own_eye | HYPOTHESIS | - | zero::retina_test::test_read_retina_question | - | cargo test -p machine_god zero::retina_test::test_read_retina_question | docs/zero/architecture.md#retina-own-eye |
| grid_entityos_wiring | HYPOTHESIS | - | zero::grid_test::test_health_check | - | cargo test -p machine_god zero::grid_test::test_health_check | docs/zero/architecture.md#grid-entityos-wiring |
| token_tachometer_data | HYPOTHESIS | - | zero::token_tachometer_test::test_get_usage_data | - | cargo test -p machine_god zero::token_tachometer_test::test_get_usage_data | docs/zero/architecture.md#token-tachometer-data |
| features_command | HYPOTHESIS | - | zero::features::tests::render_table_has_required_columns | - | cargo test -p machine_god zero::features::tests::render_table_has_required_columns | docs/zero/architecture.md#features-command |
| real_claude_code_mode | HYPOTHESIS | - | zero::claude_code_mode_test::test_switch_mode | - | cargo test -p machine_god zero::claude_code_mode_test::test_switch_mode | docs/zero/architecture.md#real-claude-code-mode |
| smartphone_link | UNKNOWN | - | - | - | - | docs/zero/smartphone.md |
| web_scraping_tools | HYPOTHESIS | - | zero::scrape_test::test_fetch_page | - | cargo test -p machine_god zero::scrape_test::test_fetch_page | docs/zero/architecture.md#web-scraping-tools |
| one_entity_fast_reflex | HYPOTHESIS | - | zero::router_test::test_decide_local_tool_cloud | - | cargo test -p machine_god zero::router_test::test_decide_local_tool_cloud | docs/zero/architecture.md#one-entity-fast-reflex |
| welt_digest | HYPOTHESIS | - | zero::welt_test::test_load_digest | - | cargo test -p machine_god zero::welt_test::test_load_digest | docs/zero/architecture.md#welt-digest |
| stance_stances | HYPOTHESIS | - | zero::stance_test::test_load_active_stances | - | cargo test -p machine_god zero::stance_test::test_load_active_stances | docs/zero/architecture.md#stance-stances |
| drift_guard_logging | HYPOTHESIS | - | zero::drift_guard_test::test_log_ground_reply | - | cargo test -p machine_god zero::drift_guard_test::test_log_ground_reply | docs/zero/architecture.md#drift-guard-logging |
| image_studio_command | HYPOTHESIS | - | zero::image_studio::tests::test_spawn_url | - | cargo test -p machine_god zero::image_studio::tests::test_spawn_url | docs/zero/architecture.md#image-command |
| health_aggregation | HYPOTHESIS | - | zero::health_test::test_aggregation | - | cargo test -p machine_god zero::health_test::test_aggregation | docs/zero/architecture.md#health-aggregation |
| plugin_manifest_discovery | HYPOTHESIS | - | zero::plugin_manifest_test::test_discover_plugins | - | cargo test -p machine_god zero::plugin_manifest_test::test_discover_plugins | docs/zero/architecture.md#plugin-manifest-discovery |
| unified_db_persistence | HYPOTHESIS | - | zero::unified_db_test::test_persistence_across_restarts | - | cargo test -p machine_god zero::unified_db_test::test_persistence_across_restarts | docs/zero/architecture.md#unifieddb-persistence |
| goals_honest_unknown | HYPOTHESIS | - | zero::goals_test::test_honest_unknown | - | cargo test -p machine_god zero::goals_test::test_honest_unknown | docs/zero/architecture.md#goals-honest-unknown |

## Notes

- Gate receipts use the round-40 base commit `bc2c876`; every `MEASURED` row carries `evidence_ref` pointing to a receipt file in `docs/zero/gate_receipts/` and a `promotion_stage` other than `-`.
- `HYPOTHESIS` and `UNKNOWN` rows carry `evidence_ref = '-'` and `promotion_stage = '-'`; no stage is claimed without a passing receipt.
- `MEASURED` by artifact presence applies only to documentation files verified present by tree inspection (see `docs/zero/status.md` Artifact Presence Ledger).
- CI placeholders are substituted by the workflow `.github/workflows/schema-check.yml` at gate time.
- **smartphone_link**: marked `UNKNOWN` with no gate; a behavioural handshake test will replace the file-existence check when implementation exists.
- **image_studio_command**: demoted from `MEASURED` to `HYPOTHESIS` because no committed gate receipt exists in `docs/zero/gate_receipts/`; the Round-14 function-level table is removed, this canonical registry is the single source of truth.

## Contract: ParseResult and Gate Handling

### ParseResult Contract

`ParseResult` is the return type of `parse_capabilities_md()`. It implements the Python container protocol for the validated checks list:

- `__iter__`: Iterates over `checks` (validated `GateCheck` objects with known runners). Does not include `unknown_gates` or `errors`.
- `__len__`: Returns `len(checks)`.
- `__bool__`: Returns `True` iff `checks` is non-empty.

This allows direct use in `for check in result:`, `list(result)`, `len(result)`, and `if result:` contexts.

### Gate Handling Semantics (Fail-Closed)

The parser enforces fail-closed semantics per row status:

| Row `status` | Gate cell value | Outcome |
|---|---|---|
| `MEASURED` | missing gate column | **Parse error** → `result.errors` (validation fails) |
| `MEASURED` | `-` or empty | Normalized to `unknown` → **dropped** (no check, no error) |
| `MEASURED` | known runner command | → `result.checks` |
| `MEASURED` | unknown runner command | → `result.unknown_gates` (validation fails) |
| `HYPOTHESIS` | missing gate column | Silently skipped (no check, no error) |
| `HYPOTHESIS` | `-` or empty | Normalized to `unknown` → **dropped** |
| `HYPOTHESIS` | known runner command | → `result.checks` |
| `HYPOTHESIS` | unknown runner command | → `result.unknown_gates` (validation fails) |
| `UNKNOWN` | any | Same as `HYPOTHESIS` (no gate required) |

**Rationale**: `MEASURED` claims require a verifiable gate. A missing gate on a `MEASURED` row is a contract violation (parse error). Placeholder `-` means "no gate provided" and is dropped rather than producing a vacuous check. Unknown runners are captured in `unknown_gates` and cause validation failure at the gate execution stage (fail-closed: no silent skip).

### Validation Flow

1. `parse_capabilities_md()` returns `ParseResult`
2. Caller checks `result.errors` → fail if non-empty
3. Caller checks `result.unknown_gates` → fail if non-empty
4. Caller checks `bool(result)` / `len(result)` → fail if empty (no validated gates)
5. Caller iterates `result.checks` and executes each gate via `run_list()`
6. Caller aggregates gate results into a `GateReport` (passed, failed, skipped, unknown_gates, errors) and emits the report; a non-zero `failed` or non-empty `unknown_gates` or `errors` fails the CI gate.

## Canonical CLI Contract

The capability gate is invoked exactly as follows:

```bash
python zero/capability_gate.py --check docs/zero/capabilities.md
```

This is the **single canonical CLI contract** advertised in this document. No other invocation patterns are supported for gate validation. The `--json` flag produces a machine-readable receipt for CI consumption.
