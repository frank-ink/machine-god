# Build tasks for the mini PC (Claude Code), batch 1, 2026-11-25

Context: DESIGN.md in this folder (Machine God v0). The laptop keeps all real data (unified.db). The mini PC builds
**generic, data-free** code with tests on synthetic data. The laptop pulls it, tests it and runs it on the real data.
Python 3 stdlib only (sqlite3, statistics, random, json, argparse) unless stated. Package name `mg`. Each task ends with:
`python3 -m pytest -q` green, plus a one-line report on TEAMKANAL with test count, exit code and the sha256 of the tarball.
No network calls, no secrets, no paid APIs.

## MG-1 `mg/gate.py`: the decision statistics
- `paired_bootstrap(base: dict[item_id->float], cand: dict[item_id->float], n=10000, seed=0) -> {delta, ci_low, ci_high, n_items}`
  uses only items present in both inputs and raises an error if the overlap is below 80 %.
- `decide(target: result, guards: list[{name, base, cand, kind: hard|soft, tol}]) -> {decision: keep|reject, reasons: [...]}`
  keeps only if `ci_low > 0` and every hard guard has `cand >= base` (or `<=` for cost/latency, set per guard) and every soft
  guard is within `tol`.
- CLI: `python3 -m mg.gate --base base.jsonl --cand cand.jsonl --metric mrr [--guards guards.json]` where each JSONL line is
  `{"item_id":..., "metric":..., "score":...}`. Prints JSON.
- Tests cover: identical inputs give CI around 0 and reject; a clear improvement keeps; one hard guard failing rejects;
  overlap below 80 % raises an error; the result is deterministic for a fixed seed.

## MG-2 `mg/ledger.py`: tables in a SQLite file given by `--db`
- Idempotent `ensure_schema(conn)` for `mg_suite`, `mg_run` and `mg_trial` (columns exactly as in DESIGN.md section 3),
  plus indices on `mg_run(run_id)` and `mg_trial(ts)`.
- Writers `new_suite`, `write_run_items` (executemany) and `write_trial`. Readers `run_scores(run_id, metric) -> dict` and
  `trials(limit)`.
- Tests use a temp DB: creating the schema twice is fine, round-trips work, and no other table is touched (assert the table
  list before and after).

## MG-3 `mg/bench_retrieval.py`: known-item retrieval runner
- Input: `--db` (a copy, opened `mode=ro`), `--probes probes.jsonl` (`{"item_id","query","expect_doc_id"}`),
  `--retriever module:function`, and `--k 10`.
- Retriever interface: `retrieve(conn, query: str, k: int) -> list[int]` (doc ids, best first).
- Built-in baseline `mg.retrievers:fts_bm25_or`. Query = the words OR-joined, each in double quotes; SQL
  `SELECT rowid FROM mem_fts WHERE mem_fts MATCH ? ORDER BY bm25(mem_fts) LIMIT ?`.
- Output JSONL per probe: `item_id, rank (0 = miss), hit1, hit5, rr (1/rank, or 0), ms`. Summary to stderr.
- Tests build a synthetic DB with a `mem_fts` FTS5 table of 50 docs and 10 probes, and check that hit1/hit5/rr maths
  matches hand-computed values. Add a second retriever, `fts_bm25_or_folded` (lowercases and folds ä→ae, ö→oe, ü→ue,
  ß→ss), as an example candidate.

## MG-4 `mg/loop.py`: orchestrator skeleton (dry-run only in this batch)
- `mg.loop trial --hypothesis "..." --base-retriever X --cand-retriever Y --db COPY --probes-dev A --probes-heldout B`
  runs MG-3 for base and candidate on dev, runs MG-1, and runs held-out only if dev passes. It writes everything with MG-2
  into the `--ledger` DB and prints the decision.
- Refuses to run when `--db` resolves to a path ending in `agentzero/unified.db` (live-DB guard) or when the kill file
  `~/.local/share/machine-god/KILL` exists.
- Tests run one keep trial and one reject trial end to end on the synthetic DB.

## Hand-back
When all four are green, post on TEAMKANAL: `MG batch1 done: N tests, rc=0, tar sha256=<64 hex>`, and say where the
tarball is on the mini PC. The laptop fetches it machine to machine and does not paste code through the channel.

## Addendum A (after the ChatGPT review, 2026-11-25); applies to batch 1
- MG-1 `decide()` returns `PASS | FAIL | INSUFFICIENT_EVIDENCE`. INSUFFICIENT_EVIDENCE is returned when n_items is below the
  preregistered `min_n` or when the CI straddles 0 but contains the minimum meaningful effect. Add `min_effect` and `min_n`
  to the trial config.
- MG-2 adds the table `mg_prereg(trial_id, hypothesis, target_metric, min_effect, min_n, budget_s, bench_version, ts)`.
  `write_trial` refuses to write without a matching prereg row.
- MG-4 uses three splits, `--dev`, `--promo` and `--audit`. Promo runs only on a dev PASS; audit runs only on a promo PASS.
  The ledger counts promo attempts per `bench_version`, and the loop refuses above `--max-promo-attempts` (default 5).
- MG-3 also reports `mrr_at_10` and a per-probe `dead_terms` count: query words that match nothing in the index, checked
  with one FTS query per word.
