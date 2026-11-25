# VOID

**A private, multi-team engineering workspace in which free-tier NVIDIA-hosted models design, review and prototype GRIDv1 - one substrate that fuses EntityOS and GRID10 inside `claude-rs`, our fork of [gschaidergabriel/machine-god](https://github.com/gschaidergabriel/machine-god) (Apache-2.0).**

**Inventor and builder: Gabriel.** He created the frameworks this repo runs on: GRF (Generative Reality Framework), EntityOS, GRID/GRID10, ClayCode and the FranKenstein system. The teams here are language models executing on his frameworks; every model output in this repo is model-generated, not a statement by him.

Teams think in **GRF** (Generative Reality Framework), speak **ClayCode** (typed contract notation) and label every claim `MEASURED`, `HYPOTHESIS` or `UNKNOWN`. This repo mirrors team output: read it as a lab notebook, not as a product.

> **Honest one-liner:** GRIDv1 exists today as a reviewed design document plus unverified prototype code on local branches. It is not a verified runtime.

---

## Status (2026-11-23)

Counts are files on disk at the time of writing; mirrors refresh every 15 minutes while teams run. "Done" means the pipeline produced its final file, not that the content is correct.

| Component | State | What exists | Evidence class |
|---|---|---|---|
| [Team 1 - GRID / kernel](teams/team1-grid/) (10 models, chief `nemotron-ultra`) | done | 10 chunk reports, 1 draft, 10 reviews, 1 final | final file reports 10/10 `APPROVE_WITH_CHANGES` (self-reported) |
| [Team 2 - research](teams/team2-forschung/) (10 models, chief `kimi`) | done, with substitution | 9 chunk reports on 5 research docs, 1 draft, 10 reviews, 1 final | `kimi` timed out on the final; `nemotron-ultra` generated it (recorded in the file header) |
| [Vereinigung](vereinigung/) (Team 1 + Team 2 = 20 voices) | done | 2 drafts, 20 reviews, [`GRIDv1.md`](vereinigung/final/GRIDv1.md) | 17x `APPROVE_WITH_CHANGES`, 3x `APPROVE` (as tabulated in the file) |
| Cosign of GRIDv1 | no unconditional cosign | 4 files, table below | mixed |
| [Team 3 - external](teams/team3-extern/) (persona leader + 5 coders) | stopped after round 6 | 6 rounds, 7 arXiv digests | `HYPOTHESIS` by policy |
| [Team 4 - build](build/) | reruns in progress | per-WP reports in `build/reports/` | compiler output of the builder's own loop |
| [Team 5 - swarm](swarm/) (50 agents) | running | 47 planned tasks, 3 cosigners, task outputs | see [`swarm/README.md`](swarm/README.md) |
| GRIDv1 runtime in the target repo | not shown | - | `UNKNOWN` |

### Cosign of GRIDv1

| Cosigner | Verdict | Notes |
|---|---|---|
| [`vereinigung/final/cosign_chef-kimi-k3.1-pro.md`](vereinigung/final/cosign_chef-kimi-k3.1-pro.md) | `YES_WITH_RESERVATIONS` | **Not independent.** Kimi timed out; `nemotron-ultra`, the author of GRIDv1, wrote this file as substitute. |
| [`swarm/cosign_nemotron-3.5-super-vl-120b-a12b.md`](swarm/cosign_nemotron-3.5-super-vl-120b-a12b.md) | `YES_WITH_RESERVATIONS` | Independent. Flags, among others, three different canonical DB paths. |
| [`swarm/cosign_minimax-m3.1-flash.md`](swarm/cosign_minimax-m3.1-flash.md) | `NO` | Independent. Backs the direction, rejects the artifact as written. |
| [`swarm/cosign_mistral-large-4-1t-a52b.md`](swarm/cosign_mistral-large-4-1t-a52b.md) | none | Timed out; the file holds no verdict. |

### Build state (Team 4)

Cargo error counts of work packages (WP) implemented on local branches `gridv1/<wp>` of the fork (not pushed to this repo). Source: the last logged check per WP.

| WP | Errors | Note |
|---|---|---|
| WP-TOPOLOGY | 0 | also clean in an independent `cargo check` |
| WP-2a | 0 | also clean in an independent `cargo check` |
| WP-2b | 16 | run 3, last pass |
| WP-1.5 | 1 | run 3, last pass |
| WP-0, WP-0.5, WP-1 | 0 | rerun 4, builder's own check; independent check pending |
| WP-2c | 14 | rerun 4, builder's own check |

Compiling is not correctness; see [`build/README.md`](build/README.md).

---

## Architecture

```
  SOURCES                            TEAMS (free NVIDIA-hosted models; GRF + ClayCode)
  -------                            --------------------------------------------------
  live GRID10 loop + modules ----->  TEAM 1  GRID / kernel design         (10 models)
  EntityOS repo + distillate ----->      zerlegen > entwurf > review > final
  claude-rs host seam                                   |
                                                        v
  5 research documents       ----->  TEAM 2  research core                (10 models)
                                         zerlegen > entwurf > review > final
                                                        |
                                                        v
                                     VEREINIGUNG  Team 1 + Team 2 = 20 voices
                                         v_entwurf > v_review > v_final
                                                        |
                                                        v
                                     +--------------------------------------+
                                     |  GRIDv1.md   (design contract)       |
                                     |  userspace substrate for claude-rs   |
                                     +--------------------------------------+
                                         |              |                |
                    +--------------------+              |                +--------------------+
                    v                                   v                                     v
          TEAM 4  build                       TEAM 5  swarm                         TEAM 3  external
          8 work packages -> code             planner -> 47 tasks                   persona leader + 5 coders
          cargo-check loop                    + 3 independent cosigners             arXiv digest, 6 rounds
                    |                                   |                                     |
                    v                                   v                                     |
          claude-rs branches                  claude-rs branches                  output = HYPOTHESIS,
          gridv1/<wp>                         gridv1/swarm-sNN                    read by the other teams,
          (local, not in this repo)           (local, not in this repo)           never counted as evidence
```

Not drawn: a free-model pool integration (`/api` command) sits on the fork branch `gridv1/omnipool`. It is outside this repo.

### What GRIDv1 is, and is not

GRIDv1 fuses the GRID10 turn engine and the EntityOS runtime into one substrate that every model request must pass: the fork's single per-turn seam (`buildQueryOptions()` in the Bun bridge) and one canonical state store (`unified.db`, one write door per table family). If the substrate is unavailable or an invariant fails, the host refuses instead of silently running without it.

**"Kernel level" means: no request bypasses the substrate.** `claude-rs` is a userspace process, so GRIDv1 is a userspace substrate. It is not an OS kernel module and gives no protection against a compromised host OS. OS mechanisms (cgroup v2, Landlock, seccomp) are proposed only as a hardening box around the process. The title of [`GRIDv1.md`](vereinigung/final/GRIDv1.md) says "USERSPACE SUBSTRATE" for this reason.

---

## Repo map

Every path below exists.

```
VOID/
|-- README.md                  this file (see "Reproduce" for where the canonical copy lives)
|-- teams/
|   |-- README.md              team index
|   |-- team1-grid/            Team 1: GRID / kernel design
|   |   |-- README.md
|   |   |-- ziel.md  team.json
|   |   `-- zerlegen/ entwurf/ review/ final/
|   |-- team2-forschung/       Team 2: research core
|   |   |-- README.md
|   |   |-- ziel.md  team.json  tasks.json
|   |   `-- zerlegen/ entwurf/ review/ final/
|   `-- team3-extern/          Team 3: external persona team
|       |-- README.md
|       |-- team.json  persona_kopf.md  gabriel_profil.md
|       |-- rounds/            r1..r6 impulse / coder / bundle files
|       `-- arxiv/             timestamped digests + latest.md
|-- vereinigung/               merge of Team 1 + Team 2
|   |-- README.md
|   |-- ziel.md
|   |-- entwurf/  review/      2 drafts, 20 reviews
|   `-- final/                 GRIDv1.md + cosign_chef-kimi-k3.1-pro.md
|-- build/                     Team 4
|   |-- README.md
|   `-- reports/               one report per work package
|-- swarm/                     Team 5
|   |-- README.md
|   |-- tasks.json             the 47 planned tasks
|   |-- cosign_*.md            3 independent cosign attempts
|   `-- sNN.md                 one output per task
|-- sources/
|   |-- README.md
|   |-- MANIFEST.md            source revisions
|   |-- entityos_destillat.md  distilled EntityOS description
|   `-- research-docs.sha256   hashes of the 5 research documents
`-- tools/
    |-- README.md
    `-- pipeline.sh  team.py  vereinigung.py  team3.py  arxiv_feed.py
        bau.py  schwarm.py  readme_team.py  void_sync.sh
```

Folder names `zerlegen` (decompose), `entwurf` (draft) and `ziel` (goal) are German. File contents are mostly English, with German in verbatim goal quotes and in Team 3's persona output.

---

## How the teams work

Each of Team 1 and Team 2 is a **chief plus nine voices**, each voice a different model served through NVIDIA's free hosted API.

1. **zerlegen** - source material is cut into chunks; one model per chunk writes a report.
2. **entwurf** - the chief merges the reports into one draft.
3. **review** - all ten models review the draft; objections, votes and resolutions go into a votes-and-dissent table.
4. **final** - the chief integrates the accepted amendments into one document.

**Vereinigung** repeats the pattern with 20 voices (`T1_*` from Team 1, `T2_*` from Team 2) over two competing drafts. The header of `GRIDv1.md` names `entwurf_chef-nemotron-ultra` as preferred base (15 of 20 votes).

**Team 3** differs on purpose. A leader persona modelled on the inventor, Gabriel (mathematician and techno-philosopher; follows arXiv, Perelman, Haramein) reads the other teams each round, issues an impulse and five coding tasks, and bundles the results.

**Team 4** turns Team 1's eight work packages into code (coder with up to three compile-fix loops, then tester). **Team 5** splits the remaining work into 47 atomic tasks, runs at most 12 agents in parallel, and adds three cosigners that did not write GRIDv1.

Models time out often. The runner then substitutes `nemotron-ultra` and writes the substitution into the file header. Not every model is an NVIDIA model (gemma, mistral, step, kimi, minimax, laguna and muse-glimmer also appear); all are called through NVIDIA's free hosted catalog.

**Measured bottleneck:** NVIDIA capacity and latency (timeouts, empty or length-truncated answers), not token budget.

---

## Evidence policy

| Class | Meaning |
|---|---|
| `MEASURED` | has a method and a reference (test output, compiler output, hash, line number) |
| `DERIVED` | follows from stated assumptions |
| `HYPOTHESIS` | plausible, untested; all persona output |
| `UNKNOWN` | stays unknown; never defaulted to 0 or 0.5 |

Rules the teams are held to:

- Consensus is not evidence: 20 votes of `APPROVE_WITH_CHANGES` are not a test.
- A prediction is not an observation; a vote winner is not truth; model confidence is not truth.
- "Finished" means verified by a test or measurement in the target repo, never by a model's claim.
- Nothing here claims consciousness or sentience; self-model indicators are functional measurements only.

---

## Reproduce

This repo alone does **not** reproduce the pipeline. The scripts in [`tools/`](tools/) need:

- local source copies: live GRID10 code, the EntityOS repo, the fork checkout, the five research documents (revisions in [`sources/MANIFEST.md`](sources/MANIFEST.md); documents identified by hash only);
- NVIDIA API keys from a local key store that is not in the repo;
- a local helper module and a prompt preamble outside the repo, plus absolute paths hard-coded to the original machine.

If you rebuild that environment, the order is:

```bash
bash tools/pipeline.sh              # Team 1 + Team 2, then Vereinigung -> GRIDv1
python3 tools/team3.py [ROUNDS]     # Team 3 rounds (uses tools/arxiv_feed.py)
python3 tools/bau.py [WP ...]       # Team 4 build
python3 tools/schwarm.py            # Team 5 swarm
bash tools/void_sync.sh             # mirror outputs into this repo
```

This `README.md` is copied in by `void_sync.sh` from a canonical file outside the repo (written by `tools/readme_team.py`). Edits made directly here are overwritten on the next sync.

---

## Limitations

- **No verified runtime.** No GRIDv1 test is shown to pass in the target repo. Implementation status is `UNKNOWN`.
- **Models mark their own homework.** The author of GRIDv1 wrote the non-independent cosign; vote tables are self-reported by the generating model.
- **Known contradictions in GRIDv1.** The independent cosigns cite three different canonical DB paths and undefined functions (for example `GRF_RAHMEN.render` and `TriggerEmergencyDeescalation`). Swarm tasks s01-s05 target these; no fix has been merged into `GRIDv1.md`.
- **Prototype code is unreviewed.** Team 3 round 6 found, for example, a runtime "no consciousness" scan that matches type names only, and a placeholder timestamp of 0.
- **Undelivered work.** Team 3's round-6 bundle lists two of five tasks (DB identity, door token) as not delivered.
- **Coverage gap.** Team 2 saw nine research-report bodies, not ten; the tenth is `UNKNOWN`.
- **Mirror artefacts.** The repo is rsynced: files can appear, change or vanish between syncs while teams run, and raw intermediate passes may hold unvalidated model output.
- **Language.** Model output mixes English and German.

---

## Ground rules

No secrets, keys or private host names in any file. No hype. No consciousness claims. Private repository.
