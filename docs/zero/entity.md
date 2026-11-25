# EntityOS binding (evidence classes)

## State authority

`src/zero/entity.rs` is the module responsible for deriving EntityOS identity and root state from the bundled `plugins/frankenstein3` plugin evidence.

**Status: UNKNOWN.** `src/zero/entity.rs` is not implemented in this repository state; no `cargo test` has been executed against it. No identity, root state, or health value is ever invented. Missing or malformed evidence yields `UNKNOWN` / error.

Evidence precedence:
- `zero-manifest.json` — primary identity authority (`entity_name`, `name`, `version`, `entity_id`) and root state (`root_state` | `root` | `state` | `entity`, otherwise the whole manifest object).
- `plugin.json` — fallback evidence source only (name/version/id).
- plugin data directory — owner of `unified.db`.

## Path resolution (f3_paths precedence)

Plugin directory:

1. `MACHINE_GOD_PLUGIN_DIR`
2. `FRANKENSTEIN3_PLUGIN_DIR`
3. bundled `plugins/frankenstein3` (searched upwards from the crate root)

Plugin data directory:

1. `MACHINE_GOD_PLUGIN_DATA_DIR`
2. `FRANKENSTEIN3_DATA_DIR`
3. `FRANKENSTEIN3_PLUGIN_DATA_DIR`
4. `data_dir` declared in `zero-manifest.json` (relative → plugin directory)
5. `$XDG_DATA_HOME/frankenstein3`
6. `$HOME/.local/share/frankenstein3`
7. the plugin directory itself (portable fallback)

`unified.db` is always `<plugin data dir>/unified.db`.

## Storage contract — two schema files, explicit ownership

There is no single schema source of truth across the whole plugin bundle. Authority is split by file:

| Schema file | Owner | Scope |
|---|---|---|
| `zero/unifieddb/schema.sql` | `zero/` (this repo) | `unified.db` tables owned by Machine God / zero40, notably `durable_memory` rows with `kind=...` used by retina, welt_digest, reason_answer. |
| `plugins/frankenstein3/data/schema_empty.sql` | bundled plugin (`plugins/frankenstein3`) | Plugin-owned schema. `zero/` does not create, migrate, or claim authority over it. |

`entity::unified_db_path()` is the canonical resolver for the single `unified.db` file (`<plugin data dir>/unified.db`). Every Machine God organ reads and writes through it.

All Machine God kinds are `durable_memory` rows with `kind=...`, not standalone tables created by `zero/`:
- `kind='retina'` — perception events (Retina one-line state), north star item 9.
- `kind='welt_digest'` — today's digest, north star item 21.
- `kind='reason_answer'` — ground-mode answers, north star item 23.

Missing or malformed evidence for any kind yields `UNKNOWN`; no value is ever invented.

## Cross-repo contract (external)

The tables `mg_stance` and `mg_drift_event` live in the service side (`~/welt-organ`, built outside this repo). They are **external** to `zero/` and `plugins/frankenstein3`. The app reads them read-only; veto/rollback remain a CLI for Gabriel (`stance.py veto|rollback --wer gabriel`), never from the app. `zero/` does not own or migrate these tables.

## Health

`entity_health_at(paths, now)` performs the measurement:

- ok is reported only when manifest + plugin metadata were read and parsed.
- UNKNOWN with a cause otherwise.
- `db_present` reports whether the database file was observed on disk.

Status line: `GRID ok | Retina ok | EntityOS ok | Omnipool ok`; stale or unmeasured components render as `UNKNOWN`.

## Claim classes

- Identity/root values, health class, db path and db presence are reported only when actually observed in this run.
- HYPOTHESIS: that the bundled plugin layout stays stable across machines.
- UNKNOWN: anything not observed in this run (missing files, parse errors, unimplemented module).
