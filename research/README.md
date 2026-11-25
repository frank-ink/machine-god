# Research (SHADOW material)

This directory is **research material**. It is not wired into the Rust app, the `machine-god` launcher or the release
archives, and it influences neither routing nor actions. Everything here runs locally and read-only, or against
throwaway databases created by the tests.

```
research/
  mg-build/    Measurement tool: gate (paired bootstrap), ledger, retrieval benchmark, loop (84 tests, mg-batch2 after team review)
  grid10/      Organs E1-E5, world model WM1/WM2, self model, intent cortex, class demand V1/V2/V2.1,
               retina thalamus, goal pursuit, freellm.py (15 test files, run_tests.py)
  teamkanal/   Reference scripts of the team-channel repair (cleaned, not runnable without a channel client)
team/          Dev team: roles, thinking frame, goal (see team/README.md)
docs/research/ Control-loop study (PDF + text), Claude + ChatGPT decisions, core idea pulse/wiki,
               round 11 measurements, mg-build review
```

## Honest status (2026-11-25)

| Part | Status | Evidence |
|---|---|---|
| All grid10 organs | SHADOW: write only to their own ledger, control nothing | code, tests |
| S0 (prospective collection) | `ZU_WENIG_DATEN`: 0 windows, no sensor cycle runs without a continuous tick | `s0_eval.py`, protocol in `fixtures/wm-s0/` |
| Intent cortex V1 | **failed**: `INTENT_BENCH_V1` macro-F1 0.615 (target 0.80), all five thresholds missed; the model measured was a local 4B model, which does not work as an intent cortex; other models are not measured | `fixtures/intent-bench/lauf_voll.json` |
| Class demand V1 | 89 % ABSTAIN on 1614 messages, accepted only as a baseline | `docs/research/decisions-*.md` |
| Class demand V2 / V2.1 | V2 semantically insufficient (pilot 24/40 exact); V2.1 28/40, but the pilot is a development set, not independent evidence | same |
| WM1 (forecast) | Historical advantage (Brier 0.0861 vs 0.1192) is retrospective and in-sample, not independently verified; prospective learning benefit open | same |
| WM2 (hypotheses) | uncalibrated; weights are plausibility shares of an unvalidated rule, not probabilities | `weltmodell2.py` |
| E3/E4 (goal genesis, competition) | goal sentences are template + finding (`rule_template`), not emergent; the competition executes nothing | same |
| Self model | capability probes; `intent_semantik` is FAILED | `selbstmodell.py` |
| Database pulse / four endings / inner wiki | **not running in the measured snapshot**: pulse tables hold 0 rows, wiki tables hold 0 rows (state `active`, empty), the four endings are not defined in any source found | `docs/research/round11-pulse-measurements.md` |
| mg-build | batch2 after team review; free-pool re-review reproduced 0 new defects; one documented configuration risk (see below) | `docs/research/mg-build-review-2026-11-25.md` |

No AGI, consciousness or emergence claim is made. No AGI indicator is shown as fulfilled (`team/ZIEL.md`).

## Tests (measured 2026-11-25 on a clean export, empty HOME)

```bash
python3 research/grid10/run_tests.py          # 15 test files, run as scripts: all green
cd research/mg-build && python3 -m pytest -q  # 84 passed
```

Not included, because they need private records or the live database: `test_grid_v2_parity.py` (was already red before
inclusion) and `test_v2_signals_extended.py` (measurement script against the live database).

## Free-pool models

Everything that needs a language model (intent cortex, team-channel check-in, roles under `team/`) calls any
OpenAI-compatible endpoint through `grid10/freellm.py`. No provider, key or model name is hard-wired:

```bash
export MG_LLM_URL="https://<provider>/v1/chat/completions"
export MG_LLM_MODEL="<model-id>"
export MG_LLM_KEY="<key>"        # optional, read from the environment only
```

Without these variables a model call fails loudly (the intent cortex then abstains); the tests need no network and no model.
Optional: `MG_LLM_HEALTH_URL` (health URL for the self-model probe `lokales_llm`), `MG_REAL_DB` and `MG_THALAMUS_VENDOR`
(only for two optional real-data replays), `MG_TRANSCRIPT_DIR` (only for the blind rating of the calibration).

**Live-database guard (mg-build, `mg/ledger.py`):** hardened against path-component tricks, `file:` URIs, percent
encoding, sidecars, hardlinks/symlinks and case. By default it protects only `live/unified.db` and
`~/.local/share/machine-god/unified.db`. **Register your own live database** with `MG_LIVE_SUFFIX` (trailing
`folder/name`) and `MG_PROTECTED_DB` (real files, separated by `os.pathsep`); otherwise it is not protected.
The measured numbers above hold for the local 4B model used at the time; there is no measurement for other models.

## Differences from the originals

- Data paths point to `research/grid10/fixtures/` (benchmark, S0 protocol, pilot tasks); the fixtures are byte-identical
  and their sha256 is checked by the tests. There are no fixed paths into a home directory.
- Model calls go through `grid10/freellm.py` to a freely chosen OpenAI-compatible endpoint instead of a fixed local model.
- Names of people, machines and hosts are neutralised; the live wiring (`register.py`) is missing.
- Not included: live-database content, private chat logs, gstack (a separate project with its own license).
- Language: new documents and file names are English. Older code comments, identifiers and some test names are still
  German and will be migrated in a separate, tested pass.
