# Machine God: self-improvement loop

A measured, autonomous improvement loop for the FranKenstein memory and retrieval stack. Nothing here claims consciousness;
"improvement" means a preregistered benchmark moved past a frozen gate on held-out data.

## How it runs
- `mg_cycle.sh` (systemd user timer, 15 min after the previous cycle ends) = `mg_propose.py` then `mg_loop.py tick`.
- `mg_propose.py`: the free LLM pool reads the last 20 ledger rows and picks ONE vetted template with bounded parameters
  (`rl2_hparam`, `recall_lane`; retired lines in `trials/retired.json`). Duplicates are refused.
- `mg_loop.py tick`: runs one queued trial on copies or read-only data, freezes the spec hash, applies the gate, writes the
  ledger (`mg_trial` in unified.db) and a lesson on rejection. A dev pass queues exactly one audit look. Guards: KILL file
  `~/.local/share/machine-god/KILL`, load, memory, lock, forbidden paths (hooks, vault, keys, trading code, gate code),
  self-stop after 3 reverts in 7 days.
- `experiments/mgfixed/mg/gate.py`: paired bootstrap and gate v2 (PASS needs the CI lower bound above the minimum effect).
- Unit files: `deploy/`. Tests: `tests/` (`python3 -m pytest -q tests/`).

## What it has measured (details and every number in DESIGN.md, sections 14-18d)
- Adopted live: full-text memory index + spell-fix/AND-first recall lane (sealed audit PASS, rollback tested).
- Adopted live: RL2 ranker 300 rounds / minleaf 55 / lr 0.3 (found by the loop, confirmed by one-look 5-fold CV on unused sessions; DESIGN 18e).
- Rejected, with reasons: normalisation arm E; synthetic known-item rows for the RL2 ranker (gains lookup, loses held-out
  usefulness AUC 0.683 -> 0.607); RL2 rounds=100 (dev pass, audit AUC guard missed by 0.0007).

## Layout
`DESIGN.md` plan, preregistrations and results · `INVENTORY.md` system inventory · `experiments/` trial scripts and result
JSON · `team/` ClayCode 5-role team runner + TITAN router · `titan/` TITAN-MX reports · `forensics/` retrieval forensics ·
`trials/` queue/done/retired. Private data (probe queries, memory text, logs) is not included.
