# Retina-GRID (Stufe 1, Shadow)

Layering: the Retina (own machine, text only, no images) is the base layer of the GRID. LLMs sit above it as organs and are
called per task class (code / json / de / reason / long / tool) through the Omni-Brain router; the GRID decides *what* class is
needed, the router decides *which* model. No fixed model names in code.

## What exists
- `plugins/frankenstein3/scripts/star/modules/grid10/retina_grid.py` feeds the retina event stream (`f2_retina_geschehen`)
  into the same `GridV2Engine` as the text GRID, in fixed 5-minute windows. Every closed window is exactly one step,
  empty windows included (deterministic, replayable from the event log).
- Shadow only: own tables `f3_grid_v2r_state` / `f3_grid_v2r_log`; never writes `f3_grid_v2_state`, never publishes to the GWT.
- Switches: `star_konfig` key `frank3.grid_retina.mode` (`off` | `shadow`, default `shadow`); `frank3.kill=1` stops it.
- Cell mapping is uncalibrated starting values (monotone in the named feature only):
  G9 surprise = clamp(max bits in window / 4), G4 bond = 1 on person_kommt/person_geht, G6 tool pressure = 1 on fokus_app,
  G10 volume = clamp(events / 10).
- Test gate: `python3 -I test_retina_grid.py` (mapping, idempotence, isolation, gap cap, read-only real-data replay).

## Measured, not claimed
- The 0.8B per-frame readings carried too little signal as GRID input (98 % abstain, 3-7 distinct values per axis), so the
  event stream is used instead.
- Real-data replay on one machine: 5036 windows, 93.5 % abstain, wins G6 170 / G4 61 / G9 48 / G10 47. No predictive
  benefit is claimed; promotion into the main GRID lane needs a green gate plus a human decision.

## Next
Thalamus gating of the retina channels (original gain formula plus habituation recovery and burst only from real signals),
then the Omni-Brain class call, then promotion by a human. No merge without review.
