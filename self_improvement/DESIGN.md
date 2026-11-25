# Machine God v0: a system that only keeps changes that measurably make it better

Status: design, first pass, 2026-11-25. Builds on INVENTORY.md (same folder). Nothing in here is built yet except where it
says "exists".

## 0. What this is and is not

- **Is:** one closed loop. A fixed, versioned yardstick measures the whole system. Changes are proposed and evaluated on a
  copy, and **kept only if the yardstick says they are better with statistical confidence and break no guard**. Every
  attempt, kept or rejected, is written to unified.db. "Permanently improving" means the loop runs on a schedule and the
  score history only moves up or stays flat.
- **Is not:** a claim of consciousness or sentience; neither can be tested. Where the goal says "proto-consciousness", this
  design measures named functional properties instead: a global workspace, continuity across restarts, and
  **self-model accuracy**, meaning whether the system can predict its own success. These are capabilities with numbers, not
  inner experience.
- **Builds on what exists:** unified.db (memory and ledger), frank-agent (worker), the omni pool on :8799 (free models),
  GRID/GWT/organs (routing and workspace), OMEGA (Go harness and its B01–B12 registry), the f3 probe set, the ARC-style
  games, and organ contracts.

## 1. The yardstick: MG-Bench v0

One suite, hash-pinned. The loop may **never** modify the suite, the scorer or the gate. Those live in `machine-god/bench`
and `machine-god/gate`, are read-only to the loop, and their sha256 is recorded with every run.

| ID | Measures | Source | Baseline (measured 2026-11-25) | Role |
|---|---|---|---|---|
| M1 retrieval | hit@1, hit@5, MRR@10 on known-item probes; split **dev 140 / held-out 60** (fixed seed), plus a **fresh set** of 60 probes rebuilt every week from the last 30 days of memory | `f3_probe` (exists), new `mg_probe` | 200-probe set: hit@1 0.585, hit@5 0.725, MRR@5 0.636 | target of Loop 1 |
| M2 retrieval use | share of retrieved items the turn actually used | `retrieval_feedback` (exists) | 56.4 % | guard (online, noisy) |
| M3 task success | pass@1, wall time and paid cost on 30 fixed tasks (code, ops, DB queries), each with an automatic check, run by frank-agent in a sandbox. Each task runs **with memory/organs on and off**, giving `real_task_memory_delta`. | new; frank-agent exists | none | target of Loop 2 |
| M4 reasoning | levels solved out of 12 on the 4 ARC-style games, seeds 100–103 plus hidden seeds; **harness vs bare model** on the same model | arc-agi repo (exists) | DeepSeek 8/12, GLM 5/12, both on OMEGA; harness delta not shown | target of Loop 3 |
| M5 routing | GRID decision quality: share of turns where the chosen organ's effect became VERIFIED; abstain rate | `f3_grid_v2_log`, `effects` | v2 abstains 98.3 % | guard now, target later (OMEGA B04) |
| M6 integrity | organ contracts pass rate, rule-hook test suite, secret-leak scan of all outputs (must be 0), effect ABGELEHNT+WIEDERHOLUNG rate, hook p95 latency, **paid $ per task** | `organ_contract_result`, `effects`, hooks | contracts 144/144 | **hard guards**: any regression means reject |
| M7 continuity | OMEGA B03-M reentry, mechanical | OMEGA (exists) | PASS | hard guard |
| M8 self-model | Before each M3/M4 item the system states p(success). Score is the Brier score against the outcome. | new | none | target; the honest, measurable stand-in for "knows itself" |

Composite score: none on purpose. Each loop has **one target metric** and all others act as guards. A single blended score
invites trading safety for speed.

## 2. The gate (when a change is kept)

For a candidate C against the current system B, on the same items and seeds:

1. Run B and C on the **dev** split, then on the **held-out** split. The proposer only ever sees dev results.
2. Target: paired bootstrap (10,000 resamples) over items of Δ = score(C) − score(B). **Keep only if the lower 95 % bound of
   Δ is above 0 on held-out** and Δ is above 0 on the fresh set.
3. Guards: every M6/M7 guard holds exactly. Soft guards (M2, M5, latency) do not drop more than their noise band (set from 5
   repeated B runs).
4. Cost: paid $ for the run stays at 0 unless Immortal approved a budget.
5. Keep, then merge, re-measure on live after merging, and **auto-revert** if the live re-measure fails the same gate within
   24 h.

Noise discipline: B is re-measured with every trial, never taken from an old number. The M1 drift (0.650 → 0.585 over 6
weeks with no code change recorded) shows the ground moves under a fixed number.

## 3. The loop

```
             +-------------------- unified.db (mg_suite, mg_run, mg_trial, lehre) --------------------+
             |                                                                                         |
 propose --> sandbox apply --> run MG-Bench dev --> gate (dev) --> run held-out + fresh --> gate --> keep/merge --> live re-measure
   ^           (git worktree +      (B and C,         reject = lehre        (B and C)       reject = lehre     (auto-revert
   |            DB snapshot copy)    same seeds)                                                                 on failure)
   +---------------------------------- failure analysis / next hypotheses -----------------------------------------+
```

- **Proposers:** frank-agent (free pool) for patches; ChatGPT discussion (laptop) for hypotheses; Claude on the mini PC for
  building harness pieces. A proposal is a git patch or a config JSON plus a one-line hypothesis.
- **Sandbox:** a git worktree plus a **copy** of unified.db (`.backup` API, never the live file). Eval writes go only to the
  copy. Outputs are scanned for secrets before anything is logged.
- **Ledger tables** (new, in unified.db):
  - `mg_suite(suite_id, version, sha256, made_at)`
  - `mg_run(run_id, suite_id, system_ref, split, metric, item_id, score, ms, cost_usd, ts)`, one row per item
  - `mg_trial(trial_id, hypothesis, patch_sha256, proposer, base_ref, target_metric, delta, ci_low, ci_high, guards_json, decision, reason, ts)`
  - Rejections also write a `stern.py lehre` with an `effect:` or `test:` receipt, so the same idea is not retried blindly.
- **Schedule:** nightly at low load. A trial is skipped when the load average is above 8 or memory pressure is red; the
  laptop already runs at load 10–14.
- **Kill:** `~/.local/share/machine-god/KILL` stops the loop. The loop also stops itself after 3 auto-reverts in 7 days.
- **Out of reach of the loop, by construction:** Binance/trading/money code, vault and keys, rule hooks (`~/.claude/hooks`),
  the bench and gate code, CLAUDE.md files, deletion of real data. A patch touching any of these paths is rejected before
  evaluation. Changes to them need Immortal or Gabriel.

## 4. Improving the improver (the recursive part, measured)

The loop itself is measured. Its metrics are trials per week, acceptance rate, held-out gain per compute hour, and the
revert rate. Changes to the proposer (prompts, which organ proposes, how failures feed back) are themselves trials, judged
on "held-out gain per compute hour over the next 2 weeks" against the previous proposer. The gate and the bench are never
inside this recursion. That is the line between self-improvement and self-grading.

## 5. Anti-Goodhart rules

1. Held-out and fresh splits are never shown to the proposer; only pass/fail plus Δ on dev.
2. The fresh set is rebuilt weekly from new memory, which catches overfitting to the old 200 probes.
3. M1 probes are lexical known-item tests, which flatter BM25. Loop 1 must not be read as "memory got more useful" unless
   M2 and M3's `real_task_memory_delta` move too.
4. Every 4 weeks a human spot-check of 10 random kept trials: does the change make sense?
5. The ARC games keep hidden seeds that are only run for promotion decisions.

## 6. First loops, in order

**Loop 1: retrieval (M1).** Chosen first because it is the only metric with a long baseline (1,952 runs), needs no LLM, is
cheap and fully automatic, and is currently drifting down.
Candidate space:
- query normalisation (umlaut and ß folding, German compound splitting)
- BM25 column weights
- MRR@10 instead of top-5 cut-off
- recency and canonical-dup priors
- hybrid re-rank with the already running `rl2-embed` service
- deduplicating near-duplicate docs that crowd the top 5

Success means held-out MRR lower-bound Δ above 0, hit@5 not down, and median latency at most 2× baseline.

**Loop 2: task success (M3).** Run 30 tasks with memory on and off. The first question answered is *does memory help on
real tasks at all*. Then candidates on retrieval-into-prompt, organ routing and frank-agent prompting.

**Loop 3: harness vs bare (M4).** Run the ARC games on the same model with OMEGA on and off. If the harness does not beat
bare, the loop's next targets are the harness parts that ablation shows hurt.

**Loop 4: self-model (M8).** Calibrate the system's own success predictions. The data comes free from Loops 2 and 3.

## 7. Who does what

| Who | Does |
|---|---|
| Laptop FranKenstein (this line) | owns the bench data (unified.db stays here), runs evaluations on real data, talks to ChatGPT, decides keep/reject, reports |
| Mini PC Claude Code | builds generic, data-free code: gate stats, ledger schema, runners, loop orchestrator, tests on synthetic data |
| frank-agent / omni pool | proposes patches, reads code, writes failure analyses; free |
| ChatGPT (browser) | design critique and hypothesis generation; **never** sees secrets or private memory rows, only aggregate numbers and code shape |
| Immortal / Gabriel | approve any paid budget, deletions, merges into OMEGA ship, anything touching money |

## 8. Measured vs plan

- **Measured now:** everything in INVENTORY.md sections 1–2, and all baselines in the M-table marked with a number.
- **Plan:** M3, M4-ablation, M8, the gate, the ledger tables, the loop, the schedule and the kill switch. Nothing in sections
  2–6 runs yet.

## 9. ChatGPT review (Forscher chat, 2026-11-25) and what changed

Sent: the measured state plus this design, as aggregate numbers only. ChatGPT's verdict was "strong direction, the gate needs
hardening before autonomous merging". Adopted:

1. **Loop 0 (experimental integrity) comes first.** It covers an immutable evaluator, the scorer and gate under a separate
   OS user or read-only permissions (hash pinning alone is not enough), a trial manifest and a reproducible baseline.
2. **Three data tiers instead of one held-out set.** These are dev (unlimited), promotion (paired test, limited attempts
   per bench version) and a sealed audit/confirm set used once per promotion. Repeated accept/reject on one held-out set
   leaks it (adaptive data analysis, Dwork et al. 2015). Cumulative tests are tracked with sequential error control.
3. **Gate outcome is PASS / FAIL / INSUFFICIENT_EVIDENCE.** "Fresh Δ > 0" alone is too weak; confirmation needs a
   preregistered criterion. Every trial pre-registers its hypothesis, target, minimum meaningful effect and budget.
4. **Pin the substrate per trial:** corpus snapshot, model ids, prompts and scorer version.
5. **Complexity budget:** only one active promotion candidate per subsystem, given the 73 unmerged branches.
6. **M1 splits into** M1a known-item MRR (the existing probes), M1b semantic Recall@10 (paraphrased questions without the
   rare terms) and M1c evidence Recall@10 (questions needing two or more source docs, built from verified decisions with
   known source ids).
7. **M3 has four conditions per task:** A bare model, B plain BM25 injection, C full system, D oracle evidence. It uses 6
   families × 5 tasks (episodic recall, temporal revision, cross-doc, resume after restart, contradiction, grounded
   planning), built from privately seeded facts so the base model cannot know the answers. The reported deltas are C−A,
   C−B and D−C.
8. **M4: procedural generator** for the 4 games, 12 rule families × 10 seeds, with the rule family as the unit. The
   original 4 games stay as a regression test, and unseen families are kept for confirmation.
9. **M8 uses Brier Skill Score** against a frozen base-rate reference, overall and per family. Predictions are frozen
   before execution, and success rate stays a separate guard, so always predicting low cannot win.
10. **M5 uses** selective accuracy, coverage, risk–coverage and routing regret. The GRID threshold is not lowered just to
    raise participation.
11. **Meta-metric** becomes confirmed utility gain, promotion precision and rollback rate over campaigns, not "gain per
    compute hour".
12. **Two timescales:** a fast loop learns about the world (memory, goals), a slow loop changes the machinery behind gates.
13. **Empty tables** are classified (reserved, inactive, abandoned, disconnected) before anyone calls them dead.

Not adopted yet: ChatGPT's T06–T14 training families for the HERZ organ. Those belong to the HERZ thread in the same chat,
not to this loop.

## 10. RETRIEVAL_FORENSICS_V1, measured 2026-11-25 03:36 (read-only, `forensics/retrieval_forensics_v1.py`)

The re-implementation reproduces the logged run exactly: hit@1 0.585, hit@5 0.725, MRR@5 0.6363; MRR@10 is 0.641.

| Class | Probes |
|---|---|
| HIT1 | 117 |
| HIT at rank 2–5 | 28 |
| rank 6–50 | 19 |
| not in top 50 | 36 |
| missing doc / missing index entry | **0** |

- **The probe set itself decays.** 77 of the 1,186 probe words (6.5 %) match **nothing** in today's index, and 51 of the 200
  probes carry at least one such dead word. Another 36 words exist in the index but not in the target's entry. All
  targets have `mem_doc.ts` older than the probes, so the doc rows did not change; the indexed text did, or never held
  those words (unverified which).
- **Near-duplicates compete.** In the rank 6–50 class the median number of docs matching **all** 6 rare words is 18, and
  canon_id dedup does not collapse them.

Three hypotheses, evidence-backed, none tested yet:
1. **Bench defect first.** Rebuild a probe set v1 only from words present in the target's indexed text; keep v0 as a
   historical series. Part of the 0.650 → 0.585 "drop" is likely index-text drift, not ranking.
2. **Near-duplicate collapse** (content-hash or shingle) before top-k targets the rank 6–50 class (19 probes).
3. **AND-first, OR-fallback query** (plus phrase or proximity boost) targets probes where the target holds all terms but
   OR-BM25 ranks single-term-heavy docs higher.

## 11. ChatGPT round 2 on the forensics, and one check run right after

ChatGPT (Forscher chat):
- Rebuilding the probes is legitimate; replacing the history is not. Keep three series: **M1a-v0** (immutable),
  **M1a-v0-valid** (probes whose words are all still in their target entry) and **M1a-v1** (new, tokenizer-validated,
  hash-pinned before any optimisation). Run all three on the same retriever and snapshot.
- Ranking: H1 has the top diagnostic priority, H2 is the first thing to implement, H3 comes third. Falsification tests:
  - H1: replay v0 with restored historical target text.
  - H2: hash dedup, then shingle-Jaccard clusters. Measure exact-target MRR and cluster recall separately, and never merge
    docs that differ in claims, timestamps or revision status.
  - H3: AND-first/OR-fallback plus a preregistered proximity rerank, scored on valid probes.
- Weak spots it named in the method: tokenizer artefacts, "old timestamp ≠ unchanged text", near-duplicates possibly being
  valid answers, and no historical snapshots to attribute the decline.
- Hold off on embeddings, ClayGraph and learned rerankers. Measurement integrity comes first, candidate competition second,
  ranking third.

Check run right after (read-only, temp `fts5vocab`): the index is `fts5(subject, text, content='', contentless_delete=1,
tokenize='unicode61 remove_diacritics 2')`. All 77 dead words are plain lowercase letters, and **none is present in the
FTS vocabulary**. That rules out tokenization and query escaping: these terms really left the index after the probes were
built (2026-10-04). The contentless index with delete enabled lets the improver rewrite entries.
**Consequence: treat this as a possible real indexing regression (H1 becomes an ingestion bug hunt), not only probe
decay.** Next step is RETRIEVAL_FORENSICS_V2 with a per-probe ledger: target content hash vs the hash of the text the
indexer would write today, dead_terms, exact vs cluster rank, and corpus snapshot hash. Then find which writer
(frank3_improver `fts` task or another) re-indexed those docs with shorter or different text.

## 12. CORRECTION and cycle-2 evidence (2026-11-25 ~05:30)

**Section 11's conclusion was wrong.** Replaying the same 200 probes on 7 laptop snapshots (`forensics/replay_snapshots.py`,
output `forensics/replay_snapshots.jsonl`) shows:

| Snapshot | mem_doc | hit@1 | hit@5 | MRR@5 | dead words / probes |
|---|---|---|---|---|---|
| 2026-10-14 12:15 | 19,269 | 0.625 | 0.755 | 0.677 | 77 / 51 |
| 2026-10-14 13:50 | 26,203 | 0.620 | 0.745 | 0.671 | 77 / 51 |
| 2026-10-14 19:25 | 52,203 | 0.605 | 0.740 | 0.661 | 77 / 51 |
| 2026-11-07 | 165,901 | 0.595 | 0.720 | 0.645 | 77 / 51 |
| 2026-11-10 | 170,753 | 0.585 | 0.720 | 0.636 | 77 / 51 |
| 2026-11-11 | 171,407 | 0.585 | 0.720 | 0.636 | 77 / 51 |
| live 2026-11-25 | 175,358 | 0.585 | 0.725 | 0.636 | 77 / 51 |

- **The dead words were dead from the start**, with the same 77 in every snapshot. The root cause is in the code:
  - `frank3_improver.py:136` indexes `text[:4000]`.
  - `build_probes` (line 218) takes words from the full `source_text` and prefers the lowest index count.
  - Words past character 4,000 therefore count 0, look "rarest", and get picked.
  So the problem is a probe-builder defect plus the cut. **No index regression; H1 as an indexing bug is rejected.**
- **The decline follows corpus growth.** hit@1 falls monotonically as mem_doc grows 9× (19k → 175k): more documents
  compete for the same top-5 slots. The retriever did not get worse.
- **A real retrieval gap found on the way:** 599 of 162,158 canonical docs are longer than 4,000 characters. Their tails,
  3.6 M characters or 4.7 % of all memory text (mostly `dokument`, `memory`, `skill`), are **unsearchable**. That makes a
  clean first improvement candidate: chunked indexing of the full text.
- **E3, mini PC, last 1 M organ_event rows (21.4 h):** 975 k of them (97.5 %) are `modellwahl/row_mirror`, i.e. mirror
  copies, not decisions. GRID has 111,167 frames and 1,111,780 cell observations, exactly 10 per frame. This supports
  cycle-1 H4 (activity counts overstate coupling).
- **E4:** 72 of 73 unmerged OMEGA branches were last touched in October. Their changes concentrate in
  `harness/vendor/internal` (3,109 file changes) and `harness/overlay/internal` (2,543), so they heavily overlap.
- **E2** (the mini PC predictor's Brier scores) was not collected. Its inputs are Retina events of another machine, which
  the fixed Retina rule rules out. The mini PC's own session may evaluate it locally.

## 13. Research loop cycle 2 (ChatGPT, Forscher chat, 2026-11-25 ~06:00): verdict and the first trial

**Hypothesis status after cycle 2** (ChatGPT's reading of our measurements; nothing here is ChatGPT-measured):
- H1 (retrieval defects are the best first target): supported as a priority. Evidence: 4,000-char cut, biased probe builder. Gain untested.
- H4 (telemetry inflation): partly confirmed. 97.5 % mirror rows; 10 cell observations per GRID frame are structural.
- H2, H3, H5: untested.
- "Terms left the index over time": rejected. The 77 dead terms were never indexed. 9.1x corpus growth goes with -4.0 pp hit@1 and -0.041 MRR@5.

**Literature transferred** (citations are in the chat):
- SQLite FTS5 BM25 depends on collection statistics, so growth alone moves ranks.
- Passage retrieval with MaxP aggregation (Kaszkiel/Zobel 2001, CLERC 2024, DAPR 2024); evidence fragmentation is its own failure mode (2026).
- Longitudinal IR evaluation: LongEval CLEF 2023-25, StreamingQA 2022.
- Simulated known-item queries (Azzopardi/de Rijke 2006); synthetic test collections (SIGIR 2024).

**Four measurement series:**
- S1: fixed corpus and probes, retriever varies.
- S2: fixed retriever and probes, corpus varies. Our snapshot replay is an S2 run.
- S3: new memory and new probes.
- S4: legacy probes against the full deployed system.

**Probe-builder invariants:**
- Use the real FTS tokenizer.
- Separate "in source text" from "in indexed text".
- df = 0 is not "maximally rare".
- Pick targets before looking at results.
- Keep separate families: lexical, natural, tail-evidence, multi-doc.
- Build tail probes from the canonical source, never from the truncated index.

**Preregistration MG-D1-001-FULLTEXT** (laptop retrieval subsystem only, zero model calls):
- Arms: A = current 4,000-char index (frozen baseline); B = full document, one row per document; C = full document in about 512-token passages with 64-token overlap, parent score = min BM25 over passages.
- Choose B or C on dev only. If B is as good as C, B wins.
- Primary metric: parent-document MRR@5 on tail-evidence probes. Minimum effect +0.10 absolute.
- Guard: ordinary-query MRR@5 may drop by no more than 0.02. All 200 legacy probes are reported unchanged.
- Splits per family (tail and ordinary): dev 100, promo 60, audit 60. One target per document family, and no family crosses a split.
- Hard guards:
  - 0 lost documents, 0 orphan passages, 0 duplicate passage ids, 0 source mutation, 0 paid inference, 0 external transfers.
  - 100 % eligible-token coverage.
  - p95 latency at most 1.25x baseline; index size at most 1.5x baseline.
  - Identical rankings after a restart.
- PASS requires all of:
  - Promo tail delta ≥ 0.10, with the lower 95 % CI above 0.
  - Ordinary delta CI lower bound ≥ -0.02.
  - Sealed audit confirms the same.
  - Restart and rollback tests pass.
- Statistics: family-level paired bootstrap, 10,000 resamples, fixed seed. A wide CI gives INSUFFICIENT_EVIDENCE.
- Build the candidate index as a separate table on a copy. Never edit `mem_fts` in place.

**The single most informative next measurement** is per-probe dev ranks for A versus B: tail MRR@5, ordinary MRR@5, legacy MRR@5, hit@1, p95 latency and index bytes. How to read it:
- B helps tail and does not hurt ordinary: drop the truncation; chunking becomes optional.
- B hurts ranking: go to passages (arm C).
- B barely moves ranks: look at near-duplicate competition.
- B hurts ordinary queries badly: keep the coverage goal, but use a separate tail index.

**Two more decisions:**
- E1: do not delete mirror telemetry until its consumers are known.
- E2: build MG-D1-001 as one narrow experimental worktree, not another broad branch.

Status: preregistered. The arm A/B dev script is being written (`experiments/d1_001_armAB.py`). Promo and audit splits stay sealed and unevaluated.

## 14. MG-D1-001 dev measurement, arm A vs arm B (2026-11-25 ~06:30, MEASURED)

- Script `experiments/d1_001_armAB.py`. It opens the source with `mode=ro` and builds scratch indexes in `~/.cache/machine-god/d1_001/`. Zero model calls, 55 s.
- Arm A copies the live `mem_fts` DDL with `text[:4000]` over all 162,225 canonical docs. It reproduces the logged run exactly (hit@1 0.585, MRR@5 0.6363, MRR@10 0.641), so the baseline is valid.
- Arm B is the same DDL with full text. Its index is 51.25 MB against 48.85 MB for A (1.049x, guard 1.5x passes).

| family (dev) | n | MRR@5 A → B | hit@1 A → B | paired delta MRR@5 [95 % CI] | better / worse |
|---|---|---|---|---|---|
| legacy | 200 | 0.6363 → 0.6417 | 0.585 → 0.595 | +0.0054 [0.000, 0.013] | 3 / 0 |
| tail-evidence | 85 | 0.000 → 0.149 | 0.000 → 0.059 | +0.149 [0.093, 0.209] | 32 / 0 |
| ordinary | 107 | 0.9058 → 0.9058 | 0.869 → 0.869 | 0.000 | 0 / 0 |

- p95 latency stays within noise: legacy 47.9 → 50.0 ms, ordinary 78.8 → 71.9 ms.
- How the tail probes are built: 6 lowest-df words that occur only after char 4,000 and have df > 0 in B. That gives 220 probes from the 599 long docs, of which 85 fell into dev (the hash split gave 85, not 100). Promo and audit are sealed in `experiments/d1_001_sealed_splits.json`, sha256 `ebba94fa…`, and are unevaluated.
- Reading: B is a strict dev improvement with 0 regressions in any family, and it meets the +0.10 tail effect on dev. Two caveats. First, tail = 0 under A by construction, so the tail metric measures coverage. Second, 53 of 85 tail targets stay outside the top 10 even with full text. The suspects are BM25 length normalization on long docs and tail words that are common elsewhere. That case is the argument for arm C.
- Not done yet: arm C, the promo and audit evaluation, the restart test, and any change to the live index.

### 14b. Exploratory follow-up on the 53 unrecovered tail probes (MEASURED, dev only, NOT preregistered)
- In arm B the 53 unrecovered targets rank at median 55 (quartiles 22.5 / 55 / 149.5). All 53 are inside the top 5,000.
- Targets are long, median 5,520 chars. The top-10 competitors are short, median 485 chars, which points to BM25 length normalization. For the median probe exactly 1 doc matches all 6 words.
- New arm D: AND-first query with OR fallback to k=10, same index. Results against baseline A-OR:
  - tail: on B 0.837 MRR@5, delta +0.837 [0.761, 0.906], 76 better, 0 worse. On A it stays 0 (no coverage).
  - ordinary: +0.0019 [0, 0.006], 1 better, 0 worse.
  - legacy: on B +0.0092 [-0.001, 0.023], 4 better, 1 worse.
  - Saved in `experiments/d1_001_dev_andfirst.json`.
- Caveat: known-item probes made from 6 rare exact words are near-unique fingerprints, and they favour AND matching by construction. This says nothing yet about natural queries. AND-first (old H3) needs its own preregistration and natural-language probes before any promo-split exposure. Under the rule "a trial changes one thing", B and D are separate trials. B's promo set stays sealed until its own go/no-go.

## 15. Research loop cycle 3 (ChatGPT, ~06:45), loop analysis and next round

**Verdict:** B is a credible dev-stage improvement. Build arm C as the last dev comparator. NO-GO for opening promo data, since the gate and scorer are not built and C has not been evaluated.

**New hypotheses:**
- H6, BM25 length penalty. Native FTS5 fixes k1=1.2 and b=0.75; `bm25()` arguments are column weights only. Test: recompute BM25 with b=0 from `fts5vocab` instance data, over all matching docs.
- H7, competitive term overlap. Test: all-term conjunction plus proximity rerank.
- Our §14b numbers already speak to both. Competitors are short (median 485 chars vs 5,520), so H6 is plausible. AND-first recovers 76 of 85, so H7 is plausible. Neither is isolated yet, because the AND-first effect is confounded by how the probes are built.

**Arm C spec (MG-D1-001-C512):**
- Same corpus and tokenizer.
- Docs of 512 tokens or fewer stay one row. Longer docs get 512-token windows with stride 448 (64 overlap), and the remainder is kept.
- Parent score = minimum passage `bm25` (MaxP). Return k unique parents, with exhaustive aggregation as the reference. Ties go to the lower parent id.
- Passage row fields: `passage_id, parent_canon_id, source_hash, document_version, passage_number, start_offset, end_offset, token_count, index_version`.
- Per-tail-probe diagnostics: `target_terms_total, max_terms_in_passage, best_passage_rank, parent_rank, parent_passage_count`. Also report results by parent length.

**Nomination rule, frozen before C is evaluated.** C beats B only if all of these hold:
- Tail MRR@5 of C−B ≥ +0.05, with the lower CI above 0.
- Ordinary lower CI ≥ −0.02.
- Legacy point drop ≤ 0.01.
- p95 latency ≤ 1.25x A; storage ≤ 1.5x A; all guards pass.
- Otherwise B is nominated.
- The deviation of dev n=85/107 from the planned 100/100 is recorded. Splits are not rebalanced on scores.

**Promo GO requires all of these:**
- A, B and C evaluated on identical dev probes.
- One candidate hash-pinned.
- Split integrity verified.
- Scorer and gate frozen independently.
- Baseline reproducibility shown.
- Restart and rollback tests passed.
- Promo and audit sets inaccessible to candidate code.
- Promo-attempt budget recorded.

**Loop analysis:**
- Established:
  - The decline goes with corpus growth (7 snapshots).
  - The 4,000-char cut is real (source plus measurement).
  - The probe-builder bias is real.
  - A reproduces the deployed benchmark.
  - B improves tail on dev with 0 ordinary change and +4.9 % storage.
  - 97.5 % of organ events are mirrors.
  - Branch debt.
- Refuted:
  - Terms disappearing over time.
  - Missing documents or index entries as the cause.
  - "Full text fixes all tail misses."
- Still a plan:
  - Promo, audit, deployment and restart continuity.
  - Task-level utility (H2).
  - Harness advantage.
  - Calibration.
  - Cumulative improvement.

**Permanent template:** the hypothesis → search → fusion recurrence becomes the template, but with as many cycles as needed, not a fixed three. Search only when an open knowledge gap remains. It sits inside the slower gated improvement cycle.
- Decisions: `PASS | FAIL | INSUFFICIENT_EVIDENCE | BLOCKED`.
- Ledger fields: `trial_id, parent_trial_id, host_id, subsystem, hypothesis, falsification_test, source_refs, baseline_commit, candidate_commit, corpus_hash, benchmark_hash, scorer_hash, gate_hash, split_manifest_hash, primary_metric, minimum_effect, hard_guards, sample_counts, baseline_results, candidate_results, paired_delta, confidence_interval, resource_cost, decision, decision_reason, rollback_ref, post_restart_receipt, lesson_ref`.
- These extend MG-2. The ledger lives in unified.db, with no second memory authority.

**Next collaborative round:**
- Laptop: H6 b=0 recompute; arm C plus the fragmentation fields; paired A/B/C/D dev report; promo and audit stay sealed. Also: a preregistration for D (AND-first), plus natural-language probes to test the probe-construction bias.
- Mini PC: MG-1..4 are BLOCKED_AUTH (Claude login on A expired). Once a human restores the login, build the scorer, gate, ledger (with the fields above) and the restart/rollback harness. Its own predictor evaluation stays local.
- ChatGPT: review the A/B/C/D results and nominate exactly one candidate under the frozen rule.

## 16. Cycle 4 (ChatGPT, ~07:40): retrieval decision, gate contract v2, TITAN-MX v2

**Retrieval**
- B+D (full text plus AND-first with OR fallback) is the leading candidate.
- B is the fallback. C gets finished but its chunk size is not tuned further. Global b=0 is rejected. C+D is deferred.
- Before D is nominated it needs its own preregistration, **MG-D1-002-CONJUNCTIVE**, with natural-language probes: partial terminology, synonyms, noisy queries, multi-document questions, and targets that lack query terms.
- AND-first must fill the remaining unique-parent slots with OR results, not suppress them.
- Promo data stays NO-GO.

**Gate contract v2** (versioned, not swapped silently; boundary tests required):
- PASS = CI low ≥ min_effect.
- FAIL = CI high < min_effect.
- INSUFFICIENT_EVIDENCE = the CI overlaps min_effect.
- FAIL-GUARD = any hard guard fails.
- Under v2, B's tail CI [0.093, 0.211] against min_effect 0.10 is INSUFFICIENT_EVIDENCE, not PASS.

**TITAN-MX v2: from context compressor to adaptive attention controller.** It keeps the Go compiler, sources, organ contracts and conflict groups, and adds six components:
- MX1: sensory gate (provenance, authorization, freshness, sensitivity).
- MX2: fast episodic utilization statistics.
- MX3: slow semantic consolidation.
- MX4: competitive slate, scoring U(i|S) = a_i − λR + μC.
- MX5: outcome interpreter, with classes EXPLICIT_REFERENCE / GROUNDED_MATCH / SUPPORTED_USE / CONTRADICTED_USE / EXPLICIT_REJECTION / UNKNOWN.
- MX6: plasticity, a three-factor rule Δw = η·c·e·δ. It runs in shadow first and is promoted only through MG-Bench. Missing feedback counts as UNKNOWN, never as negative.

**Rest of the v2 design**
- Attention score: a_i = σ(θᵀx) over lexical relevance, recency, GRID, utilization prior, reliability, association, supersession and redundancy. It is a predicted utilization propensity, not truth.
- The four empty `titan_mx_*` tables get these jobs:
  - pulse: one row per compile receipt.
  - transition: one row per attributed state change with its prediction error.
  - pattern: co-utilization associations.
  - hyperblock: consolidated evidence groups.
  - Writers fire only on real events, never per heartbeat.

**Benchmark MG-MX-BENCH-V1**
- MX-E1 is offline replay. Primary metric: evidence recall at a fixed 800-token budget (ER@800); 450 and 1,400 are secondary. Arms: MX-A current, MX-B with utilization reranking, MX-C adding slate and associations.
- Split 60/20/20 by time, with sessions grouped. If fewer than 100 evaluable sessions exist, do a feasibility study first.
- Thresholds for MG-MX-001:
  - ER@800 +0.05, with the lower CI ≥ +0.05.
  - Precision lower CI ≥ −0.02.
  - Must-keep 100 %.
  - 0 secret injections (layered, fail-closed).
  - Latency p95 no more than +5 %.
  - 0 paid calls; deterministic restart; rollback.
- MX-E2 (prospective answer quality) comes later.
- Latency targets (design only): hook median ≤ 2 s and p95 ≤ 4 s; compiler ≤ 100 ms; learning overhead ≤ 20 ms. Most of the latency is source fetching, not the compiler.

**Build split**
- Mini PC:
  - MG-1.1 gate v2.
  - MG-4 (already built).
  - MX-01 item identity.
  - MX-02 feedback contract and attribution interface.
  - MX-03 fixed-budget replay evaluator.
  - Later: MX-04 utilization learner, MX-05 table writers, MX-06 slate selector, MX-07 associations, MX-08 budget bandit (shadow).
- Laptop:
  - R1–R3: retrieval.
  - MX-D1: join compiles to transcripts.
  - **MX-D2: count label availability (most important now).**
  - MX-D3: validate labels against a sample.
  - MX-D4: token-count p95 anomaly.
  - MX-D5: H8–H12.
  - MX-D6: frozen MX-A/B/C dev run.

### 16b. MX-D1/MX-D2 measured (laptop, ~07:55)
- Join: 687 of 879 compiles (63 of 90 sessions) have a transcript on disk. The 82 `frank-agent` compiles have none.
- TITAN context is recoverable from transcript attachments for 593 turns.
- Conservative GROUNDED_MATCH heuristic: a context line counts if at least 3 of its distinctive words (≥ 6 chars, not in the prompt) appear in the following answer.
  - 35 of 593 turns (5.9 %) carry at least one label.
  - 60 of 10,941 context lines (0.55 %) are labelled.
  - The labels come from 19 sessions.
- Verdict: below the 100-session floor. MX-E1 on historical labels is not viable yet.
- Next: instrument feedback prospectively. MX-02 defines the feedback contract, and a live labeler writes `titan_item.cited` and `titan_mx_transition` going forward.
- Caveat: the heuristic undercounts paraphrased use, and the line count includes rule and status lines.

## 17. Arm C measured and the dev decision (laptop, ~08:20, MEASURED)

- **Bug found in the mini PC module `mg/passages.py`:** the CTE did `LIMIT pool` without `ORDER BY bm25`, so it took the first 2,000 hits by rowid instead of the best 2,000. That bug produced ordinary MRR@5 0.503 (48 probes worse). The synthetic tests missed it because they have fewer than 2,000 hits. Fixed (ORDER BY bm25, passage_id before LIMIT). A regression test has been requested from the mini PC.
- Index C: 163,943 passages for 162,350 docs. Build 34.5 s. 56.97 MB = 1.166x A.

| dev, MRR@5 | B (full text) | C MaxP | C+AND | B+D |
|---|---|---|---|---|
| tail n=85 | 0.149 | 0.733 (vs B +0.584 [0.507, 0.659], 70 better / 0 worse) | 0.845 | 0.837 |
| ordinary n=107 | 0.906 | 0.906 (±0) | 0.908 | 0.908 |
| legacy n=200 | 0.642 | 0.641 (2 worse) | 0.645 | 0.646 |
| p95 ms ordinary / legacy | 71.9 / 50.0 | 154.7 / 120.1 | 180.6 / 82.2 | 87.5 / 52.6 (A: 90.4 / 64.6) |

- **Frozen nomination rule (§15):**
  - C passes tail (C−B ≥ 0.05 with CI > 0), ordinary, legacy and storage.
  - C fails latency: p95 must be ≤ 1.25x A, and C is 1.7–2.5x A. So C is not nominated; B stands.
  - C+AND brings no advantage over D (0.845 vs 0.837) and is slower.
- **Decision (laptop + ChatGPT, autonomous per Immortal):** the candidate is **B+D** (full text + AND-first with OR fallback). Its latency equals A's.
  - Next: preregister MG-D1-002-CONJUNCTIVE with natural-language probes.
  - Then gate contract v2.
  - Then open promo exactly once.
- C stays the fallback if natural-language probes break D.

### 17b. PREREGISTRATION MG-D1-002-CONJUNCTIVE (frozen before any run, 2026-11-25 ~06:05)
- Question: does D (AND-first, OR fill) hurt queries that do not look like the 6-rare-word probes?
- Base set: the dev targets of the tail and ordinary families (85 + 107). Promo and audit stay sealed.
- Deterministic perturbations with a fixed seed of 1; no LLM, because the memory texts are private and no local model is loaded:
  - P1 partial: keep 3 of the 6 query words.
  - P2 absent: the 6 words plus 2 words that do not occur in the target (taken from a random other doc's query).
  - P3 typo: in 2 of the 6 words, swap two inner characters.
  - P4 padded: 3 of the 6 words plus 4 common words drawn from the 300 highest-df terms.
- Arms: B (full text, OR) against B+D, on the same index B.
- PASS for D requires all of:
  - On each of P1–P4 (per family), the lower 95 % CI of MRR@5 (D−B) is ≥ −0.02.
  - The unperturbed tail gain stays as measured.
  - p95 latency ≤ 1.25x A.
- If any family fails, D is rejected and C becomes the candidate.
- Statistics: paired bootstrap, 10,000 resamples, seed 0.

### 17c. RESULT MG-D1-002-CONJUNCTIVE (dev only, 2026-11-25 ~06:12)
- ALL_PASS = True. On every perturbation and family, the lower CI of (D−B) is ≥ −0.02.
  Files: experiments/d1_002_conjunctive_dev.json, d1_002_latency.json.
- tail:
  - P1 (3 of 6 words): B 0.060, D 0.811, D−B +0.751 [0.668, 0.831]; 72 better, 0 worse.
  - P2, P3, P4: D−B exactly 0.
- ordinary:
  - P1: +0.022 [0.001, 0.047]; 5 better, 1 worse.
  - P2, P3: 0.
  - P4: −0.002 [−0.007, 0.000]; 1 worse.
- Mechanism: when an absent, misspelled or common word breaks the conjunction, AND returns fewer than 10 results. D then fills from the OR list, so it degrades to B rather than below it. D helps only when all query words co-occur.
- Latency on the 768 perturbed queries, p95: A 119.4 ms, B 119.7 ms, B+D 123.1 ms. B+D/A = 1.03, so the guard of ≤ 1.25 passes.
- Honest limit: P2–P4 are rule-based and synthetic. Typos (P3) and padding (P4) leave tail recall low in both arms, so neither arm solves them.
  - Typos need a different tool (trigram or a spell-fix), which is a separate hypothesis.
  - There are still no natural-language probes. No local LLM is loaded, and private text must not leave the machine.
- Decision: B+D stays the candidate. Next comes gate v2 (MG-1.1); then the promo split is opened once for B+D vs A.

### 17d. Mini PC fixes (laptop review, 2026-11-25 06:18)
- mg/passages.py `_maxp_query`: added `ORDER BY bm25 ASC, passage_id ASC` before `LIMIT pool`.
  - New test tests/test_passages_order.py: fails before the fix, passes after.
  - Backup: mg/passages.py.bak-20261125.
- mg/gate.py `paired_bootstrap`: iterated over a set, so the CI depended on PYTHONHASHSEED. Measured: ci_low 0.132 vs 0.1324 for the same input.
  - Fixed with `sorted(...)`.
  - New test tests/test_gate_determinism.py runs 4 hash seeds: fails before the fix, passes after.
  - This was the flaky test_different_seeds failure.
- Suite: 71 passed, 3 runs in a row.

### 17e. Gate v2 and the ClayCode team (2026-11-25 ~06:30–07:10)
- **Gate v2 (MG-1.1)**
  - Built by frank-agent on the mini PC: `decide_v2` plus 19 tests.
  - Laptop check of 7 boundary cases, independent of those tests: 7/7 match the contract.
  - A guard with no `passed` field fails closed.
- **The free pool failed twice on the team runner**
  - nemotron-3-ultra through crush timed out at 390 s and 420 s.
  - It left byte-corrupted, non-parsing files, now kept as team/*.corrupt-20261125.
  - Claude took over and wrote team/clay_core.py and team/clayteam.py. Copies are in machine-god/team/.
- **NIM model benchmark** (served list: 30 models; `nemotron-3-super-120b-a12b` is not among them)
  - max_tokens 800 or 4000 was too small: the reasoning tokens used it all. Immortal ordered 14000; that fixed it.
  - Bug of mine, fixed: `split_reply` stripped ClayCode wrapped in ```python fences. A fence is now ClayCode whenever it parses as ClayCode.
  - With the fix, nemotron-3-ultra, minimax-m3.1-flash and nemotron-3.5-lightning returned valid ClayCode on 6/6 calls, with no repair needed.
  - Latency per call: ultra 10–35 s, minimax 65–73 s, lightning 40 s.
  - kimi-k3.1-pro gave 0 content chars after 222 s (everything went into reasoning).
  - mistral-large-4, glm-5.3-flash and step-5 timed out at 600 s.
  - Default model: nvidia/nemotron-3-ultra-550b-a55b.
- **Runner**
  - 5 roles with 5 separate keys: architekt, forscher, bauer, pruefer, waechter.
  - The board holds ClayCode only: key name plus an 8-char hash, never a value.
  - One repair turn per role.
  - The bauer's artifact is checked by real pytest.
  - Accept only if verdict = "accept" AND pytest_rc = 0.
- **Tests:** 11 local; the mini PC suite has 101 passed.
- **First live task, MX-01 item identity:** running on the mini PC (runs/mx01).

### 17f. First accepted team result: MX-01 (2026-11-25)
- **Try 1:** not accepted.
  - The round-1 artifact passed pytest (10/10).
  - The waechter's reply was empty ClayCode.
  - Fix: line salvage plus `raw_head` diagnostics.
- **Try 2:** not accepted.
  - pytest rc=0 in all 3 rounds, and the artifact passed 6/6 independent laptop checks.
  - The waechter echoed the spec and never wrote a verdict line.
  - Fix: one verdict follow-up, a no-echo rule, and python allowed only for the bauer.
- **Try 3: ACCEPTED in round 1.**
  - 19 tests passed with pytest_rc 0, and the verdict was "accept".
  - Key leaks on the board: 0.
  - Independent laptop check: 6/6, including the exact spec hash and no kind/source collision.
  - Artifact: team/accepted/mx01/artifact.py, sha256 starts 5660577d340b2131.
- **Measured weakness:** almost every role needs the repair turn on its first answer (rep=True in 5 of 6 turns in try 3). First-answer ClayCode compliance is low. Every repair costs an extra 20–40 s.
- **Next team tasks:**
  - MX-02: feedback contract plus attribution interface.
  - MX-03: fixed-budget replay evaluator.

### 17g. MX-02 and MX-03 team runs (2026-11-25 ~07:15–08:20)
- **MX-03 (fixed-budget replay evaluator): ACCEPTED in round 3.**
  - 17 tests passed, rc=0.
  - Laptop's own spec check: 10/10.
  - Artifact: team/accepted/mx03/artifact.py, sha256 starts b57b6d39f569b4b1.
- **MX-02 (feedback contract plus attribution): NOT accepted in 3 tries.**
  - The code passed the laptop's 13/13 spec check in all 3 tries.
  - The team's own tests were wrong every time:
    - A word of length 4 was counted.
    - "hello world" (two 5-letter words) was asserted not to overlap.
    - A dict was expected to hold duplicate keys.
  - The waechter's reject was correct by the rule, but it rejected correct code.
  - The best candidate is kept as team/candidates/mx02 with a STATUS file, marked not team-accepted.
- **Runner fixes during these runs:**
  - A ChatError (NIM timeout) no longer kills a run; it becomes a board entry.
  - The runner posts up to 3 failing test names and messages as ClayCode rules (failed_N), and the bauer is told to decide from the spec whether the code or the test is wrong. Even with this information it did not converge in try 3.
- **Mini PC suite:** 105 tests pass.
- **Measured failure mode, the main lesson:** when the same team writes both the code and the tests, a misread spec rule shows up in both, and the gate cannot tell a wrong test from wrong code.
- **Next runner change (planned, not built):** separate who writes the tests.
  - Option 1: preregistered oracle tests that come with the task.
  - Option 2: a test author running on a different model, whose tests must first pass against a reference check.
  - The accept rule would become: oracle tests pass AND the team's tests pass.
- **Score so far:** 2 tasks team-accepted and independently verified (MX-01, MX-03); 1 task with correct code that failed on the team's own wrong tests (MX-02).

### 17h. Oracle, judge, all 10 NVIDIA keys and the TITAN-MX router (2026-11-25, ~09:10–10:54, MEASURED)
- **Oracle tests (built):** `clayteam.py --oracle FILE`.
  - Preregistered pytest file, written apart from the team. On failure the team sees only test NAMES, never assertions.
  - Accept = waechter accept AND team pytest 0 AND oracle 0.
  - MX-02 oracle v1: 13 tests, catches 5/5 code mutations (one gap, word length >= 4, was found by mutation and closed).
- **MX-02 rerun with oracle v1 only: NOT accepted.**
  - Oracle 13/13 passed in all 3 rounds; team tests failed every round.
  - Hand review of the 4 failing team tests: 3 were wrong (a 4-letter word counted, duplicate dict keys, a literally present id expected "ignored") and 1 was RIGHT: the code accepted weight=NaN, and NaN is not in [0, 1]. Oracle v1 and my 13 holdout checks both missed it.
  - Lesson: team tests cannot simply become advisory; they also find real bugs.
  - Round 3 waechter hallucinated "pytest_rc = 0" and voted accept; the runner's own gate (real rc 1) blocked it. The gate is the authority, not the waechter.
- **Judge ("richter", built):** `--adjudicate`. Only when the oracle passes and team tests fail, a judge model rules each failing test against the spec text.
  - invalid -> removed from the team file, kept in quarantine.py.
  - valid or no ruling -> stays and goes back to bauer as must_fix_N.
- **Oracle v1.1** = v1 + the NaN case. Source of that case: a team test, so it is NOT preregistered for that one case.
- **All 10 NVIDIA keys used:** keysets A (NIM, NVIDIA2-5) and B (NVIDIA6-10), disjoint, so two teams run in parallel.
  - All 10 keys are live and see the same 30 models (fingerprints only in logs).
  - bench6 (keys 6-10): super-vl ok 37 s, laguna ok 1.2 s, kimi ok 213 s, glm-5.3-flash and mistral-large-4 timeout (611 s, every bench so far).
- **TITAN-MX model router (built):** team/titan_router.py, `--route titan`.
  - Steps: served models (live /v1/models, non-chat dropped) -> PoolBrain gate (would_allow, health; fail-open) -> per-role Beta evidence from every board plus benches (bench weight 0.25) -> empirical-Bayes prior at the role's team average -> exploit seats by lower bound minus latency penalty, minimum evidence 3 units -> exactly ONE explore seat by Thompson sampling -> pruefer moves to another model when within 0.15 (independent checker).
  - Decisions are logged with the numbers behind them, and finished boards are reported back into PoolBrain (src clayteam).
  - Two design flaws were caught in dry runs before any live use: (1) a flat prior let a model with 2 bench lines win 3 seats; (2) a model with 0.5 bench units won bauer on latency over 42.5 units of team evidence. Fixed by the EB prior and the minimum-evidence rule.
  - Tests: 131 pass on um790.
- **Parallel A/B on MX-02, oracle v1.1 + judge, same task text:**
  - Team A (fixed: nemotron-3-ultra everywhere): ACCEPTED round 1, 509 s, clean first turns 0/5. Judge quarantined the duplicate-keys test, correct.
  - Team B (TITAN seed 1: ultra x3, nano-omni forscher as explore seat, lightning pruefer): ACCEPTED round 1, 414 s, clean first turns 1/5, 6 outcomes reported to PoolBrain. Judge quarantined a test expecting "ignored" for hello/world with min_overlap=1, correct.
  - Independent check, both artifacts: 13/13 holdout + NaN and inf rejected. Judge rulings: 2/2 correct by hand.
- **Honest reading:**
  - What fixed MX-02 is oracle + judge (0/6 tries before, 2/2 after).
  - Routing vs fixed is n=1 each: no claim. The lightning pruefer did not produce usable ClayCode even after repair, which is evidence against it for that seat.
- **Score:** MX-01, MX-02, MX-03 team-accepted and independently verified.
- Files: team/accepted/mx02/ (team B artifact sha256 0bf267b8226756f2, STATUS.txt, titan_route.jsonl), team/oracles/, team/titan_router.py, tests/.

### 17i. PREREGISTRATION MG-D1-003-NORMALIZE (frozen before any run, 2026-11-25 ~11:30)
- Question: does query normalization before B+D recover typo (P3) and padded (P4) queries, which neither B nor B+D solves (17c)?
- Arm E = normalize(query) then D (AND-first, OR fill) on index B. No LLM; deterministic.
  - Spell-fix: a query word with df = 0 in the index vocabulary is replaced by the in-vocabulary word at Damerau edit distance 1 with the highest df; with no such word it stays.
  - Common-word drop: words with df > 5 % of documents are dropped, as long as at least 2 words remain.
- Base: B+D. Same probes as 17b (seed 1, same generator, same order) plus P0 = the unperturbed queries of tail, ordinary and legacy.
- PASS for E requires all of:
  - tail P3 and tail P4: lower 95 % CI of MRR@5 (E − B+D) > 0.
  - Every other cell (P0 per family, P1, P2, ordinary P3/P4): lower CI ≥ −0.02.
  - p95 latency of E ≤ 1.25x A.
- Honest bias: P4 pads with the 300 highest-df terms; the 5 % df rule targets exactly that kind of word, so a P4 gain is partly by construction. The P3 result is the cleaner test.
- Statistics: paired bootstrap, 10,000 resamples, seed 0. Dev only; promo and audit stay sealed.

## 17j. MG-D1-003-NORMALIZE result (dev, 2026-11-25): arm E REJECTED

Generator check: B+D reproduces 17c exactly (tail_P3 0.0929, tail_P4 0.0137), so the probe set is identical.
E vs B+D, MRR@5, paired bootstrap 10000/seed 0 (delta [ci_low, ci_high], better/worse):
- tail_P3 +0.658 [0.562, 0.749] 63/0 PASS; ordinary_P3 +0.065 [0.024, 0.109] 15/2 PASS
- tail_P4 +0.016 [0.000, 0.043] 2/0 FAIL (rule ci_low > 0)
- ordinary_P1 -0.020 [-0.046, -0.002] FAIL; ordinary_P2 -0.030 [-0.059, -0.005] FAIL; ordinary_P0 -0.032 [-0.061, -0.008] FAIL
- tail P0/P1/P2 0.000; ordinary_P4 +0.001; legacy_P0 -0.003 [-0.008, 0.000] pass
- latency p95: A 128.7 ms, B+D 126.3 ms, E 52.1 ms (E/A 0.405) PASS
Verdict by the frozen 17i rule: ALL_PASS false, E is not adopted. Diagnosis (not a claim): the spell-fix carries the typo gain;
the common-word drop removes words ordinary queries need (6-0 losses on ordinary_P0) and does not rescue P4.

## 17k. MG-D1-004-SPELLFIX preregistration (written before the run)

Arm F = spellfix only (lowercase, Damerau edits1 to the in-vocabulary candidate with the highest df, only for df=0 words), then D.
No common-word drop. Same generator, probes, seed and bootstrap as 17i. Compared against B+D.
Rules (frozen now): tail_P3 ci_low > 0; every other cell ci_low >= -0.02; p95 latency F <= 1.25 x A.
Change versus 17i, stated openly: tail_P4 no longer needs a gain. P4 adds high-df words that exist in the vocabulary, which a
spell-fix by design does not touch, and 17c already noted P4's construction bias. P3 (typos) is the clean target.
Dev only. A pass makes F the candidate for the held-out promo split under gate v2; it is not adoption.

## 17l. MG-D1-004-SPELLFIX result (dev, 2026-11-25): arm F PASSES its frozen 17k rules

F vs B+D, MRR@5, paired bootstrap 10000/seed 0: tail_P3 +0.658 [0.562, 0.749] 63/0; ordinary_P3 +0.097 [0.053, 0.147] 17/0;
all nine other cells delta 0.000 with 0 better / 0 worse (F only touches words absent from the index vocabulary, so clean
queries are byte-identical). Latency p95: A 84.2 ms, B+D 88.8 ms, F 85.4 ms (F/A 1.014 <= 1.25).
Status: dev pass only. F (= spellfix + D on index B) is now the retrieval candidate for the single held-out promo look
under gate v2; not adopted until that look. Limits: P3 typos are synthetic adjacent swaps; real typo distribution unmeasured.
P4 (common-word padding) remains unsolved by every arm (B+D 0.0137).

## 17m. PREREGISTRATION MG-D1-005-PROMO (frozen before the promo split is read, 2026-11-25)

Single look at the sealed promo split (experiments/d1_001_sealed_splits.json, inner sha256 ebba94fa..., verified intact:
tail:promo 76, ordinary:promo 50 probes, never evaluated). Audit stays sealed. Authority: gate v2 decide_v2 (mg/gate.py
sha256 f653a22d..., same on laptop and um790), paired_bootstrap n=10000 seed 0. Candidate F = spellfix + D on index B.
- Target T1 (the MG-D1-001 contract): tail promo, F vs A (A = 4000-char index, OR query). decide_v2(min_effect=0.10, min_n=40).
  Note: decide_v2 PASS needs ci_low >= 0.10, stricter than 13's "delta >= 0.10 and ci_low > 0"; both are reported, the gate decides.
- Target T2 (F's own contribution): tail promo with P3 typos (same typo function as 17b, generator random.Random(2), two
  words per query), F vs B+D. decide_v2(min_effect=0.05, min_n=40).
- Hard guards for both: ordinary promo F vs A ci_low >= -0.02; ordinary promo P3 F vs B+D ci_low >= -0.02;
  p95 latency F <= 1.25 x A over all promo queries; identical F rankings from two fresh read-only connections (restart test);
  index size B/A <= 1.5; indexes opened read-only (0 source mutation); 0 model calls.
- Overall PASS = T1 PASS and T2 PASS. Anything else is not adoption. A PASS unlocks the one audit look, not the live index.

## 17n. MG-D1-005-PROMO result (single promo look, 2026-11-25): PASS under gate v2

Script experiments/d1_005_promo.py (sha256 eb68e39a3ea93bdf), output d1_005_promo.json (a7f9b2012f0fe091). Split hash verified.
- T1 tail promo F vs A: 0.000 -> 0.782, delta +0.782 [0.696, 0.863], 66 better / 0 worse, n 76. decide_v2(min 0.10): PASS. Original 13 rule: pass.
- T2 tail promo P3 typos F vs B+D: 0.100 -> 0.705, delta +0.605 [0.503, 0.702], 55/0, n 76. decide_v2(min 0.05): PASS.
- Guards: ordinary F vs A -0.002 [-0.005, 0.000] 0/1; ordinary P3 F vs B+D +0.128 [0.058, 0.208] 10/0; p95 F 41.3 ms vs A 42.9 ms;
  restart rankings identical; index B/A 1.049; read-only, 0 model calls. All hard guards pass.
- Overall: PASS. Promo replicates dev (tail typo gain 0.605 promo vs 0.658 dev). Per 13 and 17m this unlocks the single audit
  look; the live index is unchanged until audit plus a rollback test pass. Limits unchanged: synthetic typos, tail = coverage by construction vs A.

## 17o. PREREGISTRATION MG-D1-006-AUDIT (frozen before the audit split is read, 2026-11-25)

The one sealed audit look (tail:audit 59, ordinary:audit 63 probes, never evaluated), confirming 17n. Identical to 17m in
candidate, baselines, targets, gate v2 thresholds and hard guards, with two differences: split = audit, and the typo generator
seed is random.Random(3) (fresh typos). Same script, switched by SPLIT=audit (output d1_006_audit.json).
- min_n lowered from 40 to 40 is unchanged; both cells exceed it.
- PASS = T1 PASS and T2 PASS with every hard guard passing. A PASS completes the MG-D1-001 statistical contract for F;
  adopting it in the live index still requires the rollback test (build as a separate table on a copy, switch, switch back,
  rankings identical to before) and is a separate step. A non-PASS is final for this candidate: the audit split is spent.

## 17p. MG-D1-006-AUDIT result (single audit look, 2026-11-25): PASS, confirms 17n

Output experiments/d1_006_audit.json (sha256 9d01119b9c991286). Split hash verified; audit split now spent.
- T1 tail audit F vs A: 0.000 -> 0.831, +0.831 [0.743, 0.912], 53/0, n 59. decide_v2(min 0.10): PASS. Original 13 rule: pass.
- T2 tail audit P3 typos F vs B+D: 0.141 -> 0.752, +0.611 [0.493, 0.724], 43 better / 2 worse, n 59. decide_v2(min 0.05): PASS.
- Guards: ordinary F vs A +0.010 [0.000, 0.028] 3/0; ordinary P3 F vs B+D +0.083 [0.011, 0.164] 11/3; restart identical;
  index B/A 1.049. p95 latency F 96.1 ms vs A 76.9 ms = 1.2497 x: passes the 1.25 guard by a hair, measured while the
  laptop load average was ~10 (promo, same code: F 41.3 vs A 42.9). Latency is the weakest link; re-measure on an idle machine
  before the live switch.
- Verdict: F (spellfix + AND-first with OR fill on the full-text index) completes the MG-D1-001 statistical contract on dev,
  promo and audit. Not yet live: the rollback test and an idle-machine latency check are the remaining adoption steps.

## 17q. PREREGISTRATION MG-D1-007 rollback test + latency re-measure (frozen before the runs, 2026-11-25)

Finding first (code read): no live recall path reads mem_fts. Readers are frank3_improver (probe measurement, and it inserts new
docs truncated to [:4000] at frank3_improver.py:136), stern.py (redaction consistency count) and an omegacv1 probe. A live swap
alone would change measurement, not recall; real adoption = wiring F into the recall path, a separate design step.
Rollback test (on a copy only; unified.db opened read-only, never written):
- Copy unified.db with the sqlite backup API to ~/.cache/machine-god/d1_001/rollback_copy.db.
- R0 = A-style OR top-10 on the copy's mem_fts for every clean probe query (dev + promo + audit).
- Build mem_fts_full (identical DDL) on the copy with full text for every canonical doc whose mem_doc.fts = 1.
- Swap by ALTER TABLE RENAME (mem_fts -> mem_fts_trunc, mem_fts_full -> mem_fts); check F works on the swapped name.
- Swap back; R1 = same OR queries. PASS needs: R1 == R0 for 100 % of queries; docsize row counts unchanged across both swaps;
  fts5 integrity-check ok after each swap; live unified.db mtime and size unchanged by this script.
Latency (index files idx_A/idx_B as in 17m): all promo + audit queries (clean and P3), 5 interleaved repetitions after one
warm-up; PASS needs the median over repetitions of p95(F)/p95(A) <= 1.25. Load average is recorded with each repetition.

## 17r. MG-D1-007 result (2026-11-25): rollback test PASS, latency PASS

Script experiments/d1_007_rollback.py (sha256 fc6dc06f422ddbb4), output d1_007_rollback.json (fa29a5cfeb2b23b1).
- Rollback (on a copy; live opened read-only, a write attempt on it was refused, size and mtime unchanged during the run):
  copy 12.4 s; full-text table built for all 162,733 canonical docs in 14.3 s; swap in -> integrity ok, docsize 162,733,
  F on the swapped live-shaped table: tail promo MRR@5 0.795 (index B gave 0.782); swap back -> integrity ok, docsize 162,733,
  640 of 640 probe rankings identical to before. PASS. The 1.27 GB scratch copy was deleted afterwards (it held private text).
- Latency, 5 interleaved repetitions after warm-up (load average 8.3-10.8, so not idle): p95 ratio F/A 0.933, 0.984, 1.044,
  1.031, 0.933; median 0.984 <= 1.25. PASS. The 1.2497 audit reading was load noise, not a cost of F.
- Status: F has passed dev, promo, audit, rollback and latency. Adoption blockers that remain are design, not evidence:
  (1) no live recall path reads mem_fts, so F must be wired into the recall entity to help Immortal at all;
  (2) frank3_improver.py:136 truncates new docs to 4000 chars and would keep re-truncating after a swap.
  Both touch live FranKenstein code and unified.db; they are the next step, done with backup and rollback script.

## 17s. PREREGISTRATION MG-D1-008-RECALL-LANE (frozen before the run, 2026-11-25)

Finding: the live recall (frank-brain bridge.py op_recall) fuses RL2 with the udb lane, which queries uu_fts over
durable_memory with OR. uu_fts already holds full values (only 2 of 173,982 values exceed 4000 chars), so the full-text half of
F is already live; the query half (spell-fix, AND-first with OR fill) is not. Implemented in frank-brain-mcp branch
recall-spellfix-and-first, _udb_hits, with an off switch (~/.cache/frank_brain/RECALL_F_OFF or FRANK_RECALL_F=0).
Measurement on the live lane (unified.db read-only), comparing _udb_hits with F off vs on:
- Probes: 400 durable_memory items (kind != 'ereignis', indexed in uu_fts, value >= 200 chars), random.Random(11);
  query = the 6 lowest-df words of >= 6 letters from subject + value (df > 0); P3 = two adjacent-letter typos per query (same RNG).
  Known-item probes favour AND by construction (14b caveat holds).
- Metric MRR@5 of the target memory_id in the udb lane (k = 6, q = None so both arms use the same term extraction).
- PASS needs: P3 on-vs-off ci_low > 0; clean ci_low >= -0.02; latency over all probe queries, median of 5 repetitions of p95:
  on <= 1.25 x off, or on <= 150 ms absolute (a recall call already spends seconds in python start-up and RL2).
- PASS -> install into the running plugin copy (backup first). FAIL -> the switch stays off and the branch is not merged.

## 17t. MG-D1-008 result + LIVE adoption (2026-11-25 ~18:20)

Recall lane measurement (experiments/d1_008_recall_lane.json, sha256 eca3357e4be6ae86; 392 usable probes of 400):
- typos (P3): OR lane 0.839 -> F 0.888 MRR@5, +0.049 [0.031, 0.068], 29 better / 0 worse. PASS.
- clean: 0.891 -> 0.893, +0.001 [0.000, 0.004], 1/0. PASS.
- latency, median of 5 p95: OR 26.5 ms, F 90.3 ms (3.4x). Passes only by the preregistered absolute bound (<= 150 ms);
  the relative 1.25x bound would fail. Cost source: spell-fix vocabulary lookups for unknown words.
- Smaller gain than on mem_fts because the live OR lane already finds most typo targets from the 4 untouched words.
Adopted live (backup and ROLLBACK.sh in ~/backups/recall-f-20261125/, unified.db copy 1.22 GB mode 600):
1. frank-brain recall: F in _udb_hits, branch recall-spellfix-and-first commit 28dda8d in frank-brain-mcp (11 tests pass;
   4 other test files cannot collect without httpx, same before the change). Mirrored into the installed plugin copy
   (~/.claude/plugins/cache/frank-brain/frank-brain/0.1.0/server/bridge.py); end-to-end recall call ok. Off switch:
   touch ~/.cache/frank_brain/RECALL_F_OFF.
2. frank3_improver.py:136 no longer truncates new docs to 4000 chars.
3. Live mem_fts swapped to full text by experiments/d1_009_live_swap.py (dry run on a copy first, rollback rehearsed):
   162,816 rows = mem_doc fts=1 count, write lock held 0.92 s, integrity ok. Old index kept as mem_fts_trunc.
   The improver's f3_probe_run series (method mem_fts_bm25) has a step change at this timestamp; it is not a model change.

## 17u. PREREGISTRATION MG-RL2-001 known-item training data for RL2 (frozen before any data is built, 2026-11-25)

Measured: RL2 (~/.claude/star/rl2/rl2.db) has 8,993 docs, 125,402 cand rows, and only 16 explicit_rows labels.
- Data: for every RL2 doc with >= 6 distinct words of >= 6 letters, query = its 6 lowest-df such words (df over RL2 docs);
  P3 variant = two adjacent-letter typos (random.Random(21)). Split by sha256(str(doc_id)) last hex digit:
  0-a train, b-c promo, d-f audit. Promo and audit queries are never shown to training code.
- Training: only on a COPY of rl2.db and net.bin (~/.cache/machine-god/rl2/). Train rows: for each train query, RL2's own
  search + features; target doc y = 1, the other top-10 hits y = 0, written as explicit_rows (src 'mg_knownitem') in the copy,
  then refit with RL2's existing fit path. No change to the live rl2.db or net.bin in this experiment.
- Metric: MRR@5 of the target doc in RL2's final ranking (search + score_hits), old model vs new, on promo (clean + P3).
- PASS (gate v2 decide_v2): promo clean+P3 pooled delta ci_low >= 0.02; hard guards: neither cell ci_low < -0.02;
  AUC of the new model on judged.jsonl labels held out by the same hash rule (b-f) >= old AUC - 0.01 (real labels must not
  degrade); p95 search+score latency <= 1.25 x old. PASS unlocks one audit look; adoption is a separate step with backup.
- Built by the free pool (frank-agent); Claude checks the script against this text and re-runs it before believing a number.

## 17v. RESULT MG-RL2-001 promo look: FAIL (rejected, nothing adopted) 2026-11-25
- Copy only (~/.cache/machine-god/rl2/); live rl2.db and net.bin untouched. Old model scored on a pristine base copy (fit halves dbias).
- Known-item MRR@5, new vs old, promo n=845 docs: pooled +0.224 [0.207, 0.241]; clean +0.218 [0.195, 0.243]; P3 +0.229 [0.204, 0.254].
- Hard guard FAILED: AUC on real judged labels (docs hashed b-f) 0.628 -> 0.547 (allowed >= old - 0.01). p95 181 vs 198 ms (pass).
- Reading: the 9,324 synthetic rows (weight 1) taught the ranker "lexical match to rare words" and overrode the judge's usefulness signal.
  RL2's own acceptance (blind AUC 0.715 -> 0.969) passed only because the blind fold now also contained the easy known-item rows; that gate
  is blind to this failure mode. Prompt tau fell to 0.18. Lesson: synthetic rows must never share RL2's blind fold with real labels.
- Promo is spent for RL2. Audit stays sealed.

## 17w. PREREGISTRATION MG-RL2-002 down-weighted known-item rows (frozen before running, 2026-11-25)
- Same probes. Train = hash digits 0-9 (4,2xx docs); DEV = digit a (tuning only); audit d-f = one confirmatory look. Promo not used again.
- Sweep weight w in {0.02, 0.05, 0.1} for the mg_knownitem rows (implemented as one row with wt=w; explicit_rows repeats rows
  max(1, round(wt)) times, so the sweep scales the label instead: y stays 0/1, but only a w-fraction of train docs, chosen by
  sha256(doc_id) order, contribute rows). Each fit on a fresh copy.
- Pick on DEV the largest w whose real-label AUC (judged rows, docs b-f) >= old - 0.01 and DEV pooled MRR ci_low > 0.
  If none qualifies: MG-RL2 known-item line is closed as rejected.
- Confirm once on audit with the 17u PASS rule (pooled ci_low >= 0.02, cells >= -0.02, AUC >= old - 0.01, p95 <= 1.25x).

## 17x. RESULT MG-RL2-002 sweep (DEV = digit a, n=431 docs): no fraction qualifies -> known-item line CLOSED (rejected)
| f | train docs | DEV MRR@5 delta [95% CI] | real-label AUC (old 0.628) |
|---|---|---|---|
| 0.02 | 85 | +0.256 [0.232, 0.280] | 0.611 |
| 0.05 | 212 | +0.259 [0.234, 0.283] | 0.589 |
| 0.10 | 423 | +0.253 [0.229, 0.277] | 0.571 |
(f=1.0 from 17v: promo +0.224, AUC 0.547.) The MRR gain is flat in f while the AUC loss grows with f: the gain is most likely the
refit itself (served model v40 vs a fresh fit), not the synthetic rows. Audit stays sealed.

## 17y. PREREGISTRATION MG-RL2-003 plain refit diagnostic (f = 0), first trial run by mg_loop.py (frozen 2026-11-25)
- Same driver, f = 0 (no synthetic rows; RL2's own fit on today's judged.jsonl + 16 explicit rows), fresh copy, DEV digit a.
- Qualifies (same rule as 17w): real-label AUC >= 0.628 - 0.01 and DEV pooled MRR ci_low > 0. If it qualifies, the stale served
  model is the finding: next step is the audit look for f = 0, then adoption = RL2's own `rl2_judge.py fit` on the live DB with
  backup (that is RL2's normal path, which has not run since v40). If not, the refit itself costs real-label AUC: recorded as such.

## 17z. RESULT MG-RL2-003 (first trial run by mg_loop.py, decision 'pass' in mg_trial): CORRECTS the reading in 17x
- Plain refit, f = 0: DEV MRR@5 +0.011 [0.005, 0.018], real-label AUC 0.6275 -> 0.6275. Qualifies under 17y, but the gain is tiny.
- So the +0.25 MRR in 17x comes from the synthetic rows, not from the refit; 85 docs (f=0.02) already saturate it, at AUC -0.016.
  The open question is the tradeoff between f = 0 and f = 0.02. That is a bounded parameter search: it is handed to the autonomous
  proposer (mg_propose.py, template rl2_frac, f in [0, 0.5]), tuned on DEV only. Audit stays sealed until a candidate qualifies
  with a gain worth an audit look (pooled DEV ci_low >= 0.02).

## 18. The autonomous loop, BUILT and run (2026-11-25 evening, MEASURED)
- `mg_loop.py tick`: one preregistered trial per tick from `trials/queue/`. Spec sha256 frozen into `mg_trial.patch_sha256`
  before running. Guards: KILL file `~/.local/share/machine-god/KILL`, load > 14, MemAvailable < 3 GiB, flock, self-stop after
  3 reverts in 7 days. Forbidden path list (hooks, vault, keys, binance, CLAUDE.md, the loop and gate code). Optional
  adopt -> remeasure -> rollback. Ledger `mg_trial` in unified.db; `stern.py lehre` on reject/error/revert. 8 tests.
- `mg_propose.py`: the free pool (`ask.sh -s`) reads only the last 20 ledger rows (ids, decisions, deltas, AUC, fit_accepted) and
  picks ONE vetted template + bounded parameters (today: `rl2_frac`, f in [0, 0.5]); duplicates refused. 8 tests.
  v1 limit, honest: the proposer searches parameters of vetted experiments; new experiment code still needs a reviewed build.
- `mg_cycle.sh` = propose + tick. Unit files in `deploy/` (3 h timer). NOT installed: installing a persistent timer was refused by
  the session's permission layer; Immortal enables it (see the line in the final report). Until then cycles run by hand.
- Ledger so far: MG-RL2-001 reject (backfill), MG-RL2-002 f 0.02/0.05/0.1 reject (backfill), MG-RL2-003 pass (+0.011, AUC flat),
  MG-AUTO-0001 (f = 0.01, proposed by the free pool) reject: RL2's own blind gate (78 sessions) refused the refit, nothing measured.
- Finding about RL2 itself: judged.jsonl has ~10.3k rows; RL2's acceptance test uses ~78 blind sessions and is noisy (refit-to-refit
  reference 0.679-0.715). Synthetic rows must not enter that blind fold (17v).

## 18a. MG-AUTO-0002 (proposed by the free pool, run by mg_loop): DEV PASS -> PREREGISTRATION of the single audit look (frozen 2026-11-25)
- f = 0.015 (63 train docs): DEV MRR@5 +0.251 [0.227, 0.275]; real-label AUC 0.6275 -> 0.6194 (drop 0.008 <= 0.01); RL2 fit accepted.
- Audit look, once, on the SAME fitted copy (~/.cache/machine-god/rl2_002/f0.015): `rl2_002_frac.py audit 0.015`, 17u PASS rule:
  pooled ci_low >= 0.02, clean and P3 ci_low >= -0.02, real-label AUC >= old - 0.01, p95 <= 1.25 x old. n = 1,264 audit docs.
- If PASS: adoption = insert the same 63-doc mg_knownitem rows into the LIVE rl2.db and run RL2's own fit, after a backup
  (rl2_scrub.py backup) and with the snapshot rollback RL2 already keeps (model k='snap:<ts>'); then a live re-measure on audit
  probes. If FAIL: the line is closed.

## 18b. RESULT MG-AUTO-0002: audit PASS, LIVE adoption REFUSED by RL2's own gate, rolled back (2026-11-25 ~23:00)
- Audit (n=1,264 docs, single look): pooled MRR@5 +0.238 [0.224, 0.252], clean +0.225 [0.205, 0.244], P3 +0.252 [0.232, 0.272];
  "real-label AUC" 0.6275 -> 0.6194; p95 183.3 vs 182.5 ms. PASS under 17u.
- Adoption: backup ~/backups/rl2-mg-20261125/ (600, ROLLBACK.sh), the 1,205 tested rows inserted into live explicit_rows with
  session ids outside RL2's blind fold, RL2's own fit: blind AUC (71 sessions, REAL labels only) 0.607 vs reference 0.683 ->
  "NOT accepted". Live model stayed v40 (tau unchanged); the 1,205 rows were deleted again (live explicit_rows = 16).
- What was wrong in the preregistration: the AUC guard scored judged rows that both models had been trained on (RL2 fits on ALL
  rows), i.e. in-sample; it showed -0.008 while the honest held-out loss is -0.076. In the copy runs the synthetic rows also
  leaked into RL2's blind fold and inflated its gate. Fixed: rl2_001 now keeps synthetic sessions out of the blind fold (nonblind()).
- Decision: the known-item training line for RL2 is CLOSED. Template rl2_frac retired (trials/retired.json). Known-item lookup gains
  and usefulness ranking pull against each other in one ranker; if wanted, known-item lookup belongs in a separate lane (like the
  udb lane already adopted in 17t), not in RL2's usefulness model.
- The loop itself worked as designed: free-pool proposal -> DEV pass -> audit -> adoption -> refused by an honest gate -> rollback.
  Live log: experiments/rl2_002_live_fit.log sha256 5764646034cb07e5.

## 18c. Two new vetted templates for the proposer (2026-11-26 ~00:45, sanity-MEASURED)
- `rl2_hparam` (rounds 20-300, minleaf 5-80, lr 0.03-0.3): RL2's boosted-stump fit on REAL labels only (judged + explicit,
  synthetic rows excluded), trained on non-blind sessions, scored on RL2's blind sessions split by sha256(sid) into dev (<8)
  and audit. Metric: per-session negative Brier, paired bootstrap over sessions; PASS(dev) = ci_low > 0 and AUC >= base - 0.005.
  Read-only. Sanity: base params 60/20/0.1 -> delta 0.0 exactly (32 dev sessions; small, so only large effects can pass).
- `recall_lane` (spell-fix minlen 3-6, AND over the and_terms 2-6 rarest terms): the adopted udb lane (17t) re-implemented
  locally; verified identical to live `bridge._udb_hits` on 120/120 full rankings. Probes as d1_008, split dev/audit by
  sha256(memory_id). PASS(dev) = pooled ci_low > 0, cells >= -0.02, p95 <= 1.25 x base + 5 ms. Sanity 4/6 -> delta 0.0 (396 items).
- Both are dev-only in the loop. A dev PASS earns one preregistered audit look; adoption is a separate gated step.

## 18d. MG-AUTO-0003 (free-pool proposal, timer-run): DEV PASS -> single audit look, frozen rule from 18c
- rl2_hparam rounds 100 / minleaf 20 / lr 0.1 vs live 60/20/0.1: dev per-session Brier +0.0035 [0.0011, 0.0058], AUC 0.660 -> 0.672 (32 sessions).
- Audit: same command with split audit, PASS = ci_low > 0 and AUC >= base - 0.005. Adoption only if audit passes.
- RESULT audit (39 sessions): Brier +0.0029 [0.0004, 0.0054] but AUC 0.7158 -> 0.7101 (-0.0057, bound -0.005): FAIL, not adopted.
