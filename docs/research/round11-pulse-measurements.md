# Round 11: what actually exists of the pulse, the four endings and the inner wiki

Measured 2026-11-25, read-only. Nothing was built, no timer was installed, no pulse was started.
Scope: the author's local unified.db copy and the docs of the omega build. Host and user names are omitted.

## Measurements

| Question | Result | How measured |
|---|---|---|
| Is the Database Pulse specified? | Yes. Pulse 2.0 doc: ~1 Hz canonical tick (59.7/min measured), inner time as the pair (epoch, tick), gap classes `none`/`short`/`long`/`offline`, fast/medium/slow tick levels | doc `DB-PULSE-2026-09-30.md` and `PULSE-2-REPORT.md` of the omega build |
| Is a pulse running? | **No.** `pulse_epoch`, `pulse_beat`, `pulse_beat_hour`, `pulse_link`, `pulse_event`, `titan_mx_pulse`: 0 rows each | `select count(*)` per table |
| What are the `dbpulse_status.json` files? | Static test snapshots (tick 4096 / 8192, `prev_end: unclean`, written 2026-10-07 and 2026-10-14), not a live pulse | file mtime and content |
| Are the four packet endings defined? | **No.** 0 hits for telomere / docking / endings / DNA in the pulse docs and the research archives. D1-D4 from the ChatGPT round stay a hypothesis | grep over three archives plus FTS over `mem_fts` |
| Is the inner wiki populated? | **No.** `wiki_state.mode = active` (set 2026-10-03 by an owner directive), but `wiki_source`, `wiki_entity`, `wiki_claim`, `wiki_abstract`, `wiki_episode`, `wiki_feedback`, `wiki_gate_log` all have 0 rows: a switched-on empty shell | `select count(*)` |
| Where did the pulse break (2026-10-08 00:10)? | **Unexplained.** The only `00:10` found is a bucket of today (`f3_endo_puls_log`, 2026-11-25), not the break | `f3_endo_puls_log` range |
| Pulse write budget | Pre-registered 25 MB/day: measured 140.6 MB/day = FAIL; after group commit the documented worst-case bound is ~23 MB/day | doc `PULSE-2-REPORT.md` |

## A caution about summaries

A free-model summary of the pulse doc invented link-end fields (`source_pulse_id`, `beat_id`, ...).
The real `pulse_beat` columns are `id, epoch, tick, wall_ns, scale, digest, novelty, surprise, n_links, cpu_us, note`.
Rule used here: a summarised schema is only trusted after a grep against the real source.

## Consequence

The pulse, the four endings, the inner wiki and the regeneration loop are design intent plus empty tables in this
snapshot, not working code. Any build has to start from the empty tables, define the four endings explicitly as a
hypothesis (D1-D4) and test docking with a measurable criterion in a throwaway database. A continuous pulse or a
systemd timer needs the owner's decision.
See [core-idea-pulse-wiki.md](core-idea-pulse-wiki.md) for the idea itself.
