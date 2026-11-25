# Inventory: one year of FranKenstein / OMEGA / research work

> **Correction, 2026-11-25 05:05.** The **main unified.db is on the Minisforum mini PC**, not on the laptop. Facts, measured
> read-only over `ssh um790`:
> - Path `~/.local/share/agentzero/unified.db`, **19.77 GB**, last written 05:04. The host is `ai-core-node-projekt-frankenstein`.
> - 397 tables were counted, 158 of them empty. 34 Retina/screen/camera tables were skipped on purpose (Retina rule).
> - Biggest tables: organ_event 16.4 M rows, f3_wm_cover and f3_wm_pred_probe_v0 about 6.0 M each, f2_grid10_cell_observation
>   1.1 M, f2_physik 579 k, gw_wettbewerb 544 k, immune_baseline 415 k, durable_memory 120 k, effects 90.7 k.
> - The **retrieval benchmark tables there are empty** (`f3_probe`, `f3_probe_run`, `mem_doc`), so M1 exists only on the
>   laptop copy (1.21 GB).
> - The mini PC has a prospective predictor table (`f3_wm_pred_probe_v0`, columns `brier`, `brier_ref`, `frozen_hash`,
>   `prospective`). That is a ready-made Brier-skill setup for M8, but its inputs are Retina events, so it was not analysed
>   from the laptop.
>
> Everything below about "unified.db" refers to the laptop copy unless it says otherwise.

Measured on the laptop (immortal369) on 2026-11-25 between 03:10 and 03:40. Every number below comes from a command run at that
time: git, `du`, `systemctl --user` or read-only SQLite on `~/.local/share/agentzero/unified.db`. Repo purpose lines come from
each README's opening lines. **Not measured:** whether each repo's tests pass today, which was out of scope for this pass.
"Live" means a running service or runtime uses the code. A GitHub checkout in `~/repos/github_all` is usually an older copy.

## 1. What runs today (live body)

| Part | Where it lives | Evidence it runs |
|---|---|---|
| FranKenstein runtime (hooks, GRID, GWT, organs) | `~/.frankenstein3/plugin`, `~/.claude/star`, `~/frankenstein-3.0` | `f3_grid_v2_log` last row a few minutes old; organs gwt, improver, kognition, mathlab, netaware, reflector, route and titan_claude active |
| unified.db (memory) | `~/.local/share/agentzero/unified.db`, 1.21 GB | 417 base tables, **152 of them empty** (max rowid 0) |
| Effect ledger | table `effects`, 137,737 rows | last 30 days: 12,782 VERIFIED, 2,956 ZUGELASSEN (admitted, not marked verified), 28 ABGELEHNT, 11 WIEDERHOLUNG |
| Organ contracts | `organ_contract_result` | 144/144 OK on 2026-11-15 and 2026-11-22 |
| Organ health (latest per organ) | `organ_health` | 10 Healthy, 1 Degraded, 3 Missing |
| OMEGA (Go harness) | `~/omegacv1-ship`, branch `omega-B-ship` | last commit 2026-11-11; omega-immune, omega-voice, omega-retina*, omega-mail-*, omega-prognose-* services running |
| API-OMNI-BRAIN (free model router) | `~/.local/share/omni-brain`, 127.0.0.1:8799 | listening (python3) |
| Retina / vision | retina-cortex, retina-feed, retina-reader, sichtd services | running |
| Buero / TEAMKANAL / mund | `~/powercontext-pilot` | teamkanal-popup, teamkanal-sync and teamkanal-deploy running; laptop side posts OK, no mini-PC reply yet |
| frank-agent, frank-tz, frank-codex, frank-poolhealth | `~/.local/bin` | present (frank-tz digest answered in this pass) |
| frank-brain MCP | `~/repos/github_all/frank-brain-mcp` | connected in this session; **the repo has no git remote, so there is no off-machine backup** |

Failed user services right now: `omega-prognose-opus`, `vps-backup-large`, `vps-backup-small`.

## 2. Existing measurements (the base for the metric)

| Metric | Source | Value | Comment |
|---|---|---|---|
| Retrieval known-item probe | `f3_probe` (200 probes, all from `durable_memory`, made 2026-10-04) and `f3_probe_run` (1,952 runs, only method `mem_fts_bm25`) | latest **hit@1 0.585, hit@5 0.725, MRR@5 0.636**, median 10–75 ms | Weekly hit@1 fell 0.650 → 0.627 → 0.613 → 0.600 → 0.597 → 0.595 → 0.585 (weeks 39–45) and has stayed flat since. **No gate stopped the drop.** Each probe is 6 rare words taken from the target doc, which makes it a lexical "find this exact doc" test, not a usefulness test. |
| Retrieval use | `retrieval_feedback` | 4,480 items mentioned vs 3,457 unused (**56.4 % used**); 75 model relevance judgements, mean credit −0.83 | noisy online signal |
| GRID v2 routing | `f3_grid_v2_log`, 2,837 decisions since 2026-10-04 | **abstains 98.3 %** (max_score about 1.3–1.5 against threshold 4.0); v2 picked a winner 49 times | v2 is effectively off. The legacy winner is still used (G10 736, G3 476, G7 430 …). |
| Model eval | `model_eval` | 701 rows, 52 models, 28 tests | last run 2026-10-04, **7 weeks stale** |
| ARC-style reasoning games | `repos/github_all/fortlaufende-arc-agi-benchmark-forschung` (4 games with hidden rules, seeds 100–103, 12 levels) | OMEGA + DeepSeek V4.1 Flash 8/12 (66.7 %); OMEGA + GLM 5.3 Flash 5/12 (41.7 %) = FranKenstein 1.0 + bare GLM 5/12; OMEGA autonomous free-pool organ choice 0/12 | The repo's own finding: **the model moved the score; the harness around it did not**. n = 4 games, so small. |
| OMEGA benchmark registry | `~/omegacv1-ship/benchmarks/README.md` | B03-M (mechanical reentry) PASS; B04 GRID ablation integrity only; B01, B02 and B05–B12 planned or candidate | none of the causal benchmarks (does GRID, TITAN or the harness help?) has a result yet |
| Agentic Density Battery | `repos/github_all/agentic-density-battery` | 30-item architecture checklist plus probe set (paper by Gschaider & Unterweger 2026) | a structural checklist, not a performance score |

## 3. Repos in `~/repos/github_all` (38)

Format: last commit · commit count · size · tests (number of `test_*.py`, `*_test.go` and `*.test.*` files). Verdict is one of
**BASE** (build on it), **KEEP** (useful part), **ARCHIVE** (superseded, keep read-only) or **OFF-TOPIC** (not part of the entity).

### FranKenstein line (the entity itself)
| Repo | State | What it is | Verdict |
|---|---|---|---|
| Frankensteinv0.95 (Unsterblich92) | 2026-11-19 · 1 · 23 MB · t128 | Public, installable cut of private FranKenstein v5: hooks, GRID, GWT, organs, unified.db, learned retrieval, free-model mouth. Installs as a Claude Code plugin. | **BASE**: newest complete, documented form |
| frankenstein-v4 (Unsterblich92) | 2026-11-11 · 2 · 757 MB · t70 | Snapshot of the running laptop system on 2026-11-11 (code, config, redacted DB snapshots) | ARCHIVE (snapshot) |
| frankenstein-3.0 | 2026-10-05 · 42 · 8.5 MB · t6 | 3.0 runtime with MEASUREMENTS.md spec (hit@k, MRR, real_task_memory_delta …). The live copy is `~/frankenstein-3.0`; this checkout is older. | KEEP: the metric spec |
| frankenstein-2.0 | 2026-09-06 · 5,310 · 44 MB · t255 | 2.0 build with evidence home; GRID10. Its data is the `f2_*` tables in unified.db (90 tables, about 1.68 M rows). | ARCHIVE; the data stays |
| frankenstein (v0.7) | 2026-09-27 · 499 · 20 MB · t47 | "invisible agent harness with an active cognitive architecture" | ARCHIVE |
| Project-Frankenstein | 2026-09-13 · 575 · 458 MB · t19 | Pre-release on Qwen 3.5-4B; needs a LoRA that is not included | ARCHIVE |
| EntityOS | 2026-09-10 · 96 · 5.7 MB | Installable form of FranKenstein 2.0 | ARCHIVE (superseded by v0.95) |
| Dr.-Unterweger | 2026-09-02 · 2,149 · 29 MB · t32 | frankv0.1 `self.root` identity home and state contract | ARCHIVE |
| agentzero-2026-08-22-prototype | 2026-09-03 · 14 · 19 MB | Prototype whose README says its alignment could not be controlled, which led to GRID10 | ARCHIVE (negative result, worth keeping) |
| frankenstein-voice | 2026-09-12 · 1 · 2.6 MB | Voice module (ASR and playback) | ARCHIVE? `omega-voice.service` runs today; whether it replaces this was not checked |
| frank-brain-mcp | 2026-11-10 · 7 · 1.1 MB · t6 | MCP server exposing GRID, organs and recall to Claude chat | **KEEP, live**; needs a remote |
| Cognitive-devmachine (Unsterblich92) | 2026-11-10 · 11 · 1.6 MB · t5 | Research and engineering workspace for the ecosystem, including a GRID bridge | KEEP (workspace) |
| frankenstein-sync-test-1787702616 | 2026-08-26 · 2 · 51 MB | Sync test leftover holding a `.gpg` file and a `unified.db.snapshot` | **Check privacy**: whether the GitHub copy is public was not checked |

### Research entity and memory
| Repo | State | What it is | Verdict |
|---|---|---|---|
| clay-global-research-entity | 2026-10-30 · 22,915 · 283 MB · t667 | RAE-8.8, the project-wide research entity's external state backend. Has the largest test count of any repo here. | KEEP: research loop and its tests; no running service was found for it |
| clay-machine | 2026-08-16 · 286 · 4.1 MB · t32 | "P.K.R.", a persistent semantic computer (`udb`) | ARCHIVE |
| clay | 2026-08-22 · 103 · 2.5 MB · t3 | Companion window app (Ctrl+Alt+C) | ARCHIVE |
| microclay | 2026-08-14 · 3 | Minimal cybernetic micro-entity, DATABASE_PULSE contract | ARCHIVE |
| clay-unifieddb-backup, AndreasClaude | empty | no commits | dead |
| lcme | 2026-03-27 · 28 · 265 MB · t1 | Local Cognitive Memory Engine; OMEGA's B05 names it as the TITAN/LCME comparison | KEEP for B05 |
| self-integration | 2026-10-06 · 267 · 16 MB | Coordinator's reflection blog (FR 2.0 / WP1207) | ARCHIVE (narrative) |

### Benchmarks and instruments
| Repo | State | Verdict |
|---|---|---|
| fortlaufende-arc-agi-benchmark-forschung | 2026-09-25 · 23 · 4 rounds with logs | **BASE** for the reasoning metric (M4) |
| agentic-density-battery | 2026-05-30 · 5 | KEEP as a structural checklist |
| Identity-Collapse-Detection-Engine | 2025-12-29 · 4 | KEEP the idea (long-horizon identity drift) for a later guard metric |
| persona-engine-framework | 2026-01-01 · 76 | ARCHIVE |

### Vision, coordination and tools
| Repo | State | Verdict |
|---|---|---|
| digital-retina | 2026-09-06 · 36 · 129 MB · t3 | KEEP; retina services run (whether they use this code was not checked) |
| retina, qgolpu | single file / 2 commits | ARCHIVE (early retina experiments) |
| agentic-grid | 2026-05-01 · 4 | ARCHIVE; Raum, Buero and TEAMKANAL do this job now |
| agentforge | 2026-07-14 · 266 · 82 MB · t21 | Purpose not stated (no README; has api, engine and migrations directories). Unknown, needs a look. |
| andreas-claude, Andreas-Resercher, gabriel-claude | personal Claude configs and notes | KEEP private |

### Off-topic for the entity
krita (**7.3 GB**, Android Krita build fork), daemonweave (Next.js and Supabase site), frank-demo, roboart, video-launch-page.
These are 7.6 GB of the checkout. They could be moved off the laptop, which is 83–88 % full. Deleting anything needs Immortal or Gabriel.

## 4. OMEGA fragmentation (outside github_all)

- `~/omegacv1-ship` has **98 git worktrees**. **73 branches are not merged** into `omega-B-ship`. `git cherry` shows every one of
  the 73 still carries commits whose patches are not in ship, so none is safe to drop blindly. The biggest are omega-B-organs5
  (81), needle-chain-2026-10-11 (78), omega-B-organatlas-tf (72), omega-B-unifieddb (63), omega-B-rel (62) and
  omega-B-titan-prompt (60).
- About 30 further `~/omega-*` directories have no git (build copies, drafts, zips).
- Consequence for the design: OMEGA work happened as many parallel branches with no shared yardstick deciding what to merge.
  That is exactly the gap the improvement loop closes.

## 5. Dead or duplicated: summary

1. **Five generations of the same entity** (v0.7, 2.0, EntityOS, 3.0, v4, v0.95, Project-Frankenstein, Dr.-Unterweger).
   v0.95 plus the live `~/.frankenstein3` is the current one; the rest are history.
2. **152 empty tables** in unified.db (vp_* 10, omega_* 13, mem_* 7 …).
3. **GRID v2 never decides** (98.3 % abstain) while the legacy GRID still routes.
4. **Measurements exist but gate nothing.** The retrieval probe ran 1,952 times and drifted down about 10 % relative; model_eval
   stopped 7 weeks ago; OMEGA's causal benchmarks B01/B02/B05–B12 never ran.
5. **73 unmerged OMEGA branches**, 30 non-git OMEGA copies.
6. **No measured evidence yet that the harness beats the bare model** (ARC rounds 1–4). This is the most important open
   question for a "self-improving system". The design makes it the first thing the yardstick answers.
