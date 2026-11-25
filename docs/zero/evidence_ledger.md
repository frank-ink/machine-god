# Evidence Ledger — Items 6-9

Records the epistemic status of Track 2 / Track 3 capabilities.
Labels: `MEASURED` (gate receipt hash recorded in ledger), `HYPOTHESIS` (intended, design referenced, no passing gate receipt), `UNKNOWN` (no verifying measurement available). `UNKNOWN` is never defaulted to 0 or 0.5.

CVIR promotion ladder (no rung may be skipped):
`MEASURE → FALSIFY → MATCHED_ABLATION → VERIFIED_OUTCOME → CAUSAL_CREDIT → BOUNDED_ADMISSION → REENTRY_TEST → CONTROL_INFLUENCE`

## Item 6: Omega ground mode (`src/zero/omega.rs`)
- Classification: HYPOTHESIS
- CVIR promotion stage: MEASURE
- Gate: `cargo test -p machine_god zero::omega_test::test_build_chat_request -- --nocapture 2>&1 | tee /tmp/omega_gate.log && sha256sum /tmp/omega_gate.log | cut -d' ' -f1`
- Falsification condition: Test fails if (a) chat request builder produces invalid JSON for OpenAI-compatible endpoint, (b) language detection returns wrong locale for DE/EN fixtures, (c) fallback sentence is not emitted when server unreachable, (d) loopback enforcement allows non-127.0.0.1 address.
- Gate receipt hash: `UNMEASURED`
- Evidence: design anchor `docs/zero/architecture.md#omega-ground-mode`

## Item 7: Freewiki provider tips (`src/zero/freewiki.rs`)
- Classification: HYPOTHESIS
- CVIR promotion stage: MEASURE
- Gate: `cargo test -p machine_god zero::freewiki_test::test_pick_tip -- --nocapture 2>&1 | tee /tmp/freewiki_gate.log && sha256sum /tmp/freewiki_gate.log | cut -d' ' -f1`
- Falsification condition: Test fails if (a) tip picked for provider with `configured=true`, (b) more than one tip returned per session, (c) tip contains provider not present in `providers.json`, (d) output lacks fenced code box with URL, (e) new providers not prioritized over older ones.
- Gate receipt hash: `UNMEASURED`
- Evidence: design anchor `docs/zero/architecture.md#freewiki-provider-tips`

## Item 8: Retina own eye (`src/zero/retina.rs`)
- Classification: HYPOTHESIS
- CVIR promotion stage: MEASURE
- Gate: `cargo test -p machine_god zero::retina_test::test_read_retina_question -- --nocapture 2>&1 | tee /tmp/retina_gate.log && sha256sum /tmp/retina_gate.log | cut -d' ' -f1`
- Falsification condition: Test fails if (a) subprocess calls non-loopback address, (b) GRID push target is not 127.0.0.1:8490 (or `MACHINE_GOD_GRID_PORT`), (c) unified.db write uses kind != 'retina', (d) missing Retina returns invented content instead of "Retina not available", (e) `--line` output not parsed into one-line state.
- Gate receipt hash: `UNMEASURED`
- Evidence: design anchor `docs/zero/architecture.md#retina-own-eye`

## Item 9: Grid + EntityOS status line (`src/zero/grid.rs`, `src/zero/entity.rs`)
- Classification: HYPOTHESIS
- CVIR promotion stage: MEASURE
- Gate: `cargo test -p machine_god zero::grid_test::test_health_check -- --nocapture 2>&1 | tee /tmp/grid_gate.log && sha256sum /tmp/grid_gate.log | cut -d' ' -f1`
- Falsification condition: Test fails if (a) health check reports "ok" for unreachable GRID/EntityOS, (b) status line omits any of the four components (GRID, Retina, EntityOS, Omnipool), (c) UNKNOWN not shown for unmeasured components, (d) loopback enforcement violated for GRID push.
- Gate receipt hash: `UNMEASURED`
- Evidence: design anchor `docs/zero/architecture.md#grid-entityos-wiring`

## Notes

- `HYPOTHESIS` rows carry `gate_receipt_hash = UNMEASURED` and `promotion_stage = MEASURE` (the rung currently under test); no stage is claimed without a passing receipt hash.
- When a gate receipt hash is recorded (replacing `UNMEASURED`), the row may be promoted to `MEASURED` with the highest passed CVIR stage recorded.
- Promotion follows the 8-rung ladder strictly: a row at stage N may only advance to N+1 after its gate for N+1 passes and receipt is recorded.
- Dead schema references (`evidence_ref='-'`, `promotion_stage='-'`, `CVIR promotion path` full ladder per row) removed.
