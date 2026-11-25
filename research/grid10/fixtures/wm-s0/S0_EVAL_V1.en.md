# S0_EVAL_V1: Prospective Evaluation of World Model WM1 (fixed 2026-11-25, draft ChatGPT Round 9)

Purpose: first prospective test stage. Not a final proof of learning. Parameters are proposed initial fixings, not empirically validated. After freezing (sha256 in S0_EVAL_V1.sha256) they are no longer changed; a change is newly fixed as S0_EVAL_V2.

1. Data basis: rows from f3_wm_pred with status='evaluated' and prospective=1. Forecast frozen before window start (frozen_hash), evaluated independently of the forecaster (Brier against raw events). Windows without sensor sample are UNKNOWN and never enter the evaluation, nothing is imputed. Historical windows (baseline) are not S0 data.
2. Version: each model version is evaluated separately (main evaluation: Version 0). Version boundaries are never shifted retroactively; a forecast counts under the version under which it was frozen.
3. References: frozen W0 reference (base rates, frozen before measurement start) and persistence (last evaluated window). Model, W0, and persistence have the same information state and horizon (mandatory fields in f3_wm_pred).
4. Minimum scope: 200 valid windows per version, otherwise result TOO_LITTLE_DATA.
5. Main metric: Brier Skill Score against W0: BSS = 1 - Sum(B_Model) / Sum(B_W0). Secondary: BSS against persistence (only windows with existing persistence forecast). Additionally per retina channel.
6. Uncertainty: paired block bootstrap, 95%-interval (percentiles 2.5 and 97.5), block length 12 windows (60 min), 10000 repetitions, fixed random seed 20261125. Blocks consist only of temporally immediately consecutive windows (bucket difference 1) and are never assembled across observation gaps; a shorter remainder block at the end of a contiguous section is retained. Sensitivity: block lengths 24 and 36, only reported.
7. Verdict: positive = lower bound of CI above 0; negative = upper bound below 0; otherwise inconclusive.
8. No ablation. All results reported with n, number of sections, number of blocks, and number of UNKNOWN windows.
