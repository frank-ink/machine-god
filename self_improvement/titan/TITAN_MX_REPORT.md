# TITAN_MX Architecture Report

## 1. Data Flow per User Turn

**Entry**: `hook.py:1` — `UserPromptSubmit` event triggers `main()` → loads `sources.json` → runs 4 sources in parallel (rl2, pc_inbox, pc_claims, stern) via `run_sources()` (`hook.py:180-210`).

**Block Splitting**: `adapter.py:180-250` `split_blocks()` classifies text into blocks with `kind` (rl2, pc_inbox, pc_claims, stern, system, task, file, tool_result, other), extracts `text`, `source`, `ts`, `tags`.

**Item Building**: `adapter.py:255-340` `build_items()` creates `ContextItem` (core.py:15-22) with `kind`, `text`, `relevance` (lexical overlap vs user prompt, `adapter.py:120-175`), `tokens`, `must_keep` flags.

**Profile Selection**: `adapter.py:345-400` `select_profile()` chooses **klein** (450 tok, max 6 items, min_rel 0.30), **mittel** (800/9/0.25), or **gross** (1400/12/0.20) via GRID signals G1-G10 + cues (build/free/see/measure/status) + architect mode (`adapter.py:370-395`).

**Organ Layer**: `organ_layer.py:40-95` `apply()` scales activation per organ kind (`KIND_ORGAN` map, `adapter.py:70-85`), applies emergent boost from f2_weg (`organ_layer.py:55-65`), compression (`organ_layer.py:65-75`), supersession (`organ_layer.py:75-85`), organ token caps (`organ_layer.py:85-90`), computes budget.

**Compiler**: `core.py:85-180` `compile_request()` — must-keep items first, then relevance floor (`min_relevance`), conflict groups (same `conflict_key`), budget enforcement. Returns `CompileResult` with `composed` text, `kept` items, `omitted` count.

**Output**: `hook.py:230-280` returns compiled context (mode=on) or passthrough (mode=off/shadow). Log shows `weggelassen=X/Y` = omitted/kept items (`hook.py:265`).

## 2. Storage Locations

**Reads**:
- `unified.db` (star_konfig, f2_grid_v2_log, entityos_arbeitspaket, f2_weg, f2_grid10_frame) via `store.py:50-90`
- `~/.claude/projects/*/*.jsonl` (replay prompts) via `replay_data.py:10-35`
- `replay/replay.jsonl` (593 prompts) via `replay.py:20-30`
- `replay/events.jsonl` via `replay_events.py:15-25`
- `sources.json` (source config) via `hook.py:100-130`
- State files: `state/carry.json`, `state/pretool.json`, `state/posttool.json` via `store.py:100-140`

**Writes**:
- `titan_claude.db` (tc_log, tc_freepool, titan_organ, titan_item, titan_activation, tc_outcome) via `ledger.py:25-80`, `store.py:150-200`
- State files above via `store.py:100-140`
- `kern.md` coverage report via `kern.py:90-130`

## 3. TITAN-MX vs titan_claude

**TITAN-MX** (`core.py:1-260`): Compiler core ported from Go (omegacv1-ship). Pure selection algorithm: ContextItem/Request/Result types, `compile_request()`, conflict groups, budget, relevance floor. No I/O, no organs, no hooks.

**titan_claude**: Hook wrapper (`hook.py`), organ layer (`organ_layer.py`), 11 native organ loaders (`native.py`), replay/lesion tooling, CLI (`tc.py`), adapter (`adapter.py`), modelcard (`modelcard.py`).

**titan_mx_pulse/transition/pattern/hyperblock**: Defined as DDL comments in `organs.py:120-135` but **no code writes them**. `ledger.py` DDL (`ledger.py:30-70`) creates only `tc_log`, `tc_freepool`, `titan_organ`, `titan_item`, `titan_activation`, `tc_outcome`. Zero rows because no INSERT statements target these tables anywhere in the codebase.

## 4. 18 titan_organ Slots

`organs.py:20-90` defines 19 slots (0-18):
- 0-17 from OMEGA: episodic, semantic, procedural, working, predictive, interoceptive, body, anomaly, engineering, planner, temporal, metacognition, normative, self_model, grid, repair_morphogenesis, grid10
- 18 = grid10 (added)
- **All authority = NONE** (`organs.py:45`)
- **17 wired** in `native.py:50-400` (11 loaders map to kinds via `KIND_ORGAN`)
- **repair_morphogenesis discarded** (no loader)
- `organ_layer.py` uses `KIND_ORGAN` map (`adapter.py:70-85`) to apply per-kind activation scaling, caps, emergent boost.

## 5. lesion.py & replay*.py Measurements

**lesion.py** (`lesion.py:15-80`): Per-organ ablation — forces one organ's activation=0 via `organ_layer.apply()` override, compares context hash vs control. Runs with `TC_NO_GRID=1` + frozen SNAPSHOT for determinism (`lesion.py:35-45`). Asserts context changes deterministically per organ.

**replay.py** (`replay.py:15-95`): Shadow compiles 593 real prompts from `replay/replay.jsonl`. Measures: token reduction vs passthrough, profile distribution (klein/mittel/gross), must-keep rate, omitted count, compile latency.

**replay_events.py** (`replay_events.py:20-120`): Replays SessionStart/PreToolUse/PostToolUse event sequences from `replay/events.jsonl`, verifies state dedupe (`events.py:150-200`).

**replay_data.py** (`replay_data.py:10-35`): Extracts prompts + injected context from `~/.claude/projects/*/*.jsonl` for replay corpus.

## 6. Tests & Assertions

**test_titan_claude.py**:
- `CoreTests` (12): `compile_request` budget, relevance floor, conflict groups, must-keep, empty input, profile caps
- `AdapterTests` (4): block classification, relevance scoring, profile selection, item building
- `HookTests`: mode switching (on/off/shadow), source execution, passthrough
- `InstallTests`: hook installation, sources.json generation
- All sandboxed: private `TC_STATE`, `TC_LOGDB` per test

**test_titan_organs.py**:
- `RegisterTests`: 18 slots, authority=NONE, grid10 at 18
- `ActivationTests`: organ_layer scaling, emergent, compression, supersession, caps
- `NativeTests`: 11 loaders return valid ContextItems
- `OrganLayerTests`: budget calculation, token caps per kind
- `EventsTests`: SessionStart/PreToolUse/PostToolUse handlers, dedupe
- `LedgerTests`: write path, schema, tc_outcome linkage
- `LesionTests`: ablation changes context hash deterministically
- `KernTests`: candidate generation, CLAUDE.compact.md coverage

## 7. 5 Weakest Points for Brain-Like Context Selection

1. **No outcome learning**: `tc_outcome` table exists (`ledger.py:65`) but no code reads it to adjust relevance/organ weights. `modelcard.py` computes correction rates (Wilson CI) but only **suggests** — no feedback loop (`modelcard.py:100-130`).

2. **No recurrence/memory across turns**: Each turn independent. `carry.json` (`store.py:110`) passes minimal state but no working memory of prior selections, errors, or corrections.

3. **No prediction error signal**: Compiler minimizes token budget, not surprise. No mechanism to detect "context was wrong" (missing facts, hallucination) and boost responsible organs.

4. **Static organ authority**: All 18 slots `authority=NONE` (`organs.py:45`). No organ can gate, veto, or request recompile. `organ_layer` only scales — no control flow.

5. **Profile selection is heuristic, not learned**: `select_profile()` (`adapter.py:345-400`) uses GRID signals + hardcoded cues. No bandit/RL to discover which profile works for which task type. `modelcard.py` has train/holdout split but no online update.