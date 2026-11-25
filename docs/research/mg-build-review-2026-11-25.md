# mg-build: team review, fixes and re-review (2026-11-25)

`research/mg-build` is the measurement tool: paired bootstrap gate, SQLite ledger, retrieval benchmark, dev -> promo -> audit loop.
The first batch (batch1) was reviewed by a team (guardian, checker, architect). Batch2 replaces it.

## What the review found in batch1

- The live-database guard could be bypassed (`file:` URIs, percent-encoding, hardlinks, symlinks, case, `-wal` sidecars).
- The kill file was checked only at start, not before each stage.
- Gate statistics: items were taken from the candidate instead of the baseline, missing items were dropped, NaN/inf were accepted.
- The promo budget could be reset by changing a label; crashes left no ledger row.
- 8 of 46 mutations of the checker survived (tests did not notice the change).

## What batch2 changed (84 tests)

- Baseline defines the item set; missing candidate items count 0.0; overlap below 0.8 is refused; NaN/inf and duplicates are refused.
- `bench_version` is derived from the item ids; the caller label only goes into the detail.
- `claim_promo` is atomic and strict; promo budget refusal and crashes leave ledger rows (`REFUSED_PROMO_BUDGET`, `ABORTED`).
- The kill file is checked before every stage; dev, promo and audit splits must be disjoint.
- Guards are wired in: hit@5 hard, latency soft (tolerance 25 % of base + 1 ms); `budget_s` is a wall-clock check between stages.
- Guard cases measured as blocked: direct path, `file:` URI, `?mode=` URI, `%61` URI, hardlink, symlink, upper case, `-wal`.
- Mutation checks: gate 8/8 killed, loop 10/10 killed; remaining survivors in ledger/bench are equivalent or defense-in-depth.

## Re-review (free pool, 2026-11-25)

A second review by a large free model (nemotron-3-ultra-550b) returned 8 claims. Each was checked against the real code:

| Claim | Check |
|---|---|
| Symlink/hardlink bypass of the guard | false: both blocked (measured with the default live path and with `MG_PROTECTED_DB`) |
| SQL injection via `metric` | false: parameter binding; a hostile `metric` raises `ValueError`, `mg_run` stays intact |
| Five functions named in the findings (`is_protected_db`, `paired_bootstrap_pvalue`, `promotion_loop`, `record_run`, `promote_if_significant`) | do not exist; the gate uses only the standard library (no numpy) |
| Unprotected default paths | **true, documented:** without `MG_PROTECTED_DB` / `MG_LIVE_SUFFIX` the public copy protects only `live/unified.db` and `~/.local/share/machine-god/unified.db` (measured: `/var/lib/machine-god/unified.db` is not protected) |

Result: 0 new defects, 1 confirmed configuration risk. Set `MG_PROTECTED_DB` and `MG_LIVE_SUFFIX` before pointing the tool at a real database.

## Known limits

- Candidate retriever code runs in-process, without a sandbox.
- A free-model review is a reading aid, not proof; only the measured rows above count.
