# How this was made: process archive (2026-11-24 / 2026-11-25)

Written in English at the owner's request. It records the process, not only the result. Every statement is tagged
**[measured]** (a command or test produced it), **[owner]** (stated by the owner in chat, not verifiable from this repo) or
**[open]** (not done or not shown).

## The setup, as the owner describes it [owner]

- Three FranKenstein instances work as one team: two based on Claude Code, one based on ChatGPT.
- All three build on about one year of research at the owner's institute for agentic research (iar.frank.ink).
- The team combines the data, tools and language models the owner fine-tuned (0.8B to 8B parameters).
- A new coding language based on emergence was invented along the way; parts of it can now be measured and controlled.

What this repo shows of that: the measurement side (`research/mg-build`, `research/grid10`), the team roles (`team/`) and the
decisions (`docs/research/`). **[open]** The coding language and the fine-tuned models are not in this repo, and no
control of any organ is demonstrated here: every organ in `research/grid10` is SHADOW (writes only its own ledger).

## Division of labour

| Who | Job | Evidence |
|---|---|---|
| ChatGPT-based instance + laptop instance | research, hypotheses, coordination (study, four-ending hypotheses D1-D4) | `docs/research/decisions-claude-chatgpt-2026-11-24.md` |
| Claude Code instance on the main machine (lead) | decides, measures, builds, says what is the case | tests, ledgers, commits below |
| Free-pool language models | generation, code drafts, first review (NVIDIA models first); never trusted without a test | `docs/research/mg-build-review-2026-11-25.md` |
| Review roles (architect, builder, checker, guardian) | independent review of diffs and claims | `team/agents/` |

Channel: a direct cable between the machines, used through a small team channel (`research/teamkanal`). The channel
had to be repaired first (a drop-in fix, reference scripts included).

## Timeline

1. **Spec.** The control-loop study (`control-loop-study-2026-11-24.pdf`) is chosen as the target architecture.
   Binding decisions are logged in the decisions file (SHADOW first, control only after evidence, merge only by a human).
2. **Team roles.** Five roles with a thinking frame (GRF) and measurable goals; the honest translation of the goal says no AGI
   indicator is shown as fulfilled.
3. **mg-build batch1** is built by the free pool, then reviewed by the team: the live-database guard was bypassable,
   the gate statistics took items from the candidate, dropped missing items and accepted NaN/inf, 8 of 46 mutations survived. **[measured]**
4. **mg-build batch2** fixes all of it: 84 tests, mutation checks gate 8/8 and loop 10/10 killed. **[measured]**
5. **Re-review** by a large free model (nemotron-3-ultra-550b): 8 claims, each checked against the code: 0 new defects, 1
   documented configuration risk. A model review is a reading aid, not proof.
6. **Round 11 (pulse, four endings, inner wiki).** Measured read-only: pulse tables 0 rows, wiki tables 0 rows, the four
   endings are defined in no source. Result: design intent plus empty tables, not working code (`round11-pulse-measurements.md`).
7. **Publication** to branch `fill/team-grid10-mg` only; main untouched.

## Incidents (kept visible on purpose)

- **Credential pasted in chat.** Treated as burned, never stored or repeated; rotation by the owner is **[open]**.
- **Wrong identity and build files pushed twice** (commits cbabd83 and dc89572): an auto-commit hook committed with the
  owner's real e-mail address and added `.pyc` files, the second time from a throwaway verification clone.
  Both times the branch was deleted and re-pushed clean; GitHub may still cache the old commits (only a support
  request removes them). Root cause fixed in the hook: build artefacts are never staged, repos under `/tmp` are never
  auto-pushed, the public repo is committed with a neutral identity; 19 hook tests incl. 3 regression tests. **[measured]**
- **Free-model summaries invented fields** (pulse link columns) and a model hung for ~28 minutes: every summary is now
  checked against the real source before it is used.

## Verification state at the end of this round **[measured]**

- Remote `fill/team-grid10-mg` = 9e5d3c7, `main` = eb72ae3 (unchanged), all new commits authored by "Machine God" (noreply).
- Fresh clone with bytecode disabled: 84 mg-build tests passed, grid10 15 test files green, 0 `.pyc` tracked, 0 e-mail hits.

## What is still open

Shadow experiment for the pulse (throwaway database, D1-D4 as stated hypotheses); S0 prospective collection (0 windows);
intent cortex below target (0.615 vs 0.80); WM1 advantage only retrospective; German identifiers still to be migrated.
