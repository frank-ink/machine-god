# TITAN-MX: measured state (laptop, 2026-11-25 ~07:15, read-only)

Sources: `~/.claude/star/titan_claude/titan_claude.db` (the hook's own DB), unified.db on the laptop and the mini PC, and the code report in `TITAN_MX_REPORT.md` (written by the free pool; its slot and wired counts are corrected below).

- **Two registries.** In unified.db, `titan_organ` has 18 slots, all `authority=NONE`, `wired=0`, on both machines. That table is stale. The registry that matters is in titan_claude.db: 19 slots, 18 wired (15 `angepasst`, 3 `uebernommen`), 1 `verworfen`.
- **TITAN-MX learning tables** (`titan_mx_pulse/transition/pattern/hyperblock`): 0 rows on both machines, and no code writes them. They are a design that was never built.
- **Hook activity** (`tc_log`): 876 compiles from 2026-11-07 to today; 866 `on`, 10 `shadow`.
  - Profiles: klein 451, mittel 142, gross 277, none 6.
  - Fallbacks: 6 compile timeouts above 2.5 s.
- **Per compile** (median / p95): 14 / 21 items in, 6 / 15 selected. Raw 572 / 2,384 tokens, compiled 450 / 2,923 tokens. At the p95 the compiled context is larger than the raw input, because native organs add items.
- **Latency per prompt** (median / p95): compile 356 / 1,113 ms; total 4.0 / 8.1 s. The largest share is the `stern` source, about 3.4 s in the latest row.
- **Item decisions** (`tc_ledger`, 16,254 rows): selected 6,771, rejected 6,003, root 3,480.
  - Top organs: self 2,762, semantic 2,682, normative 2,610, grid10 1,966.
- **Item statistics** (`titan_item`, 2,353 items): seen 12,419, selected 6,803, **cited 0**. Nothing ever records whether a selected item was used in the answer.
- **Outcome signal** (`tc_outcome`): 11 user corrections in total. `modelcard.py` reads them for a report, but nothing feeds them back into selection.

## What is missing for a "more brain-like" selector
- An outcome loop: `cited` stays 0 and corrections are never fed back.
- Memory across turns: only `carry.json`.
- A prediction-error signal.
- Learned profile choice: profiles are picked by heuristics today.
- Hebbian or transition learning, which is what the empty `titan_mx_*` tables were meant to hold.
- A benchmark that measures context quality at all. Today there is only replay of token counts, profiles and latency.
