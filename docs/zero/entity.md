# EntityOS binding (MEASURED / UNKNOWN)

## State authority

`src/zero/entity.rs` is the only module that derives EntityOS identity and
root state. The authority is the bundled `plugins/frankenstein3` plugin:

- `zero-manifest.json` — primary identity authority (`entity_name`, `name`,
  `version`, `entity_id`) and root state (`root_state` | `root` | `state` |
  `entity`, otherwise the whole manifest object).
- `plugin.json` — fallback evidence source only (name/version/id).
- plugin data directory — owner of `unified.db`.

Missing or malformed evidence is an error / `UNKNOWN`; no identity, root state
or health value is ever invented.

## Path resolution (f3_pfade precedence)

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

## One database for retina and entity

`entity::unified_db_path()` is the canonical resolver. The retina side uses
`zero::retina_db::unified_db_path()`, which delegates to it, so both organs
address the same file. Test: `zero::entity::tests::db_path_matches_retina`.

## Health

`entity_health_at(paths, now)` performs the measurement:

- `MEASURED(ok)` only when manifest + plugin metadata were read and parsed.
- `UNKNOWN` with a cause otherwise.
- `db_present` reports whether the database file was observed on disk.

Status line: `GRID ok | Retina ok | EntityOS ok | Omnipool ok`; stale or
unmeasured components render as `UNKNOWN`.

## Claim classes

- MEASURED: identity/root values, health class, db path, db presence.
- HYPOTHESIS: that the bundled plugin layout stays stable across machines.
- UNKNOWN: anything not observed in this run (missing files, parse errors).
