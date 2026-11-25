# Integration (do after the GRID worker finished; nothing here touches fusion/, interest/, mailbox/, firstrun/, public_overlay.py yet)

## 1. Archive files (repo path `reflect/`)
Runtime files only, same pattern as `interest/`:
```
reflect/core.ts  reflect/learn.ts  reflect/hook.ts  reflect/reflect.ts  reflect/proposals.ts  reflect/cli.ts  reflect/README.md
```
`reflect/reflect.test.ts` and this file stay in the repo. In `public_overlay.py`: add `reflect` to the list of overlay dirs that are copied (next to
"firstrun", "bridge", "interest", "mailbox", "fusion", "grid"), add the seven runtime files to the `files` list of the package/archive (same place as `interest/cli.ts ...`),
and the tests/INTEGRATION to the repo-only list (same place as `interest/interest.test.ts`).

## 2. Launcher subcommand `machine-god improve ...`
POSIX launcher (next to `interests)`):
```sh
improve) shift; exec "$MG_HOME/bin/machine-god-bridge-bun" "$MG_HOME/reflect/cli.ts" "$@" ;;
```
Windows launcher: `"%MG_HOME%\bin\machine-god-bridge-bun.exe" "%MG_HOME%\reflect\cli.ts" %*`.
The launcher must `export MG_HOME` (the install dir) so `improve apply` knows the allowed root and the hooks find the scripts.
Exit codes: 0 ok, 1 usage/not found, 2 backend failure, 3 refused (apply needs an interactive TTY).
Add `improve` to the launcher's help text.

## 3. Hook registration
Put this in a Machine God plugin so it merges with the user's Claude Code settings (same layout as `plugins/frankenstein3/hooks/hooks.json`; new plugin dir
e.g. `plugins/machine-god-reflect/` with `.claude-plugin/plugin.json` `{"name":"machine-god-reflect","version":"0.1.0"}` and `hooks/hooks.json`). Do NOT edit the frankenstein3 hooks.json.
```json
{ "hooks": {
  "PostToolUse":        [{ "matcher": "*", "hooks": [{ "type": "command", "command": "\"$MG_HOME/bin/machine-god-bridge-bun\" \"$MG_HOME/reflect/hook.ts\" post",   "timeout": 5 }] }],
  "PostToolUseFailure": [{ "matcher": "*", "hooks": [{ "type": "command", "command": "\"$MG_HOME/bin/machine-god-bridge-bun\" \"$MG_HOME/reflect/hook.ts\" post",   "timeout": 5 }] }],
  "Stop":               [{ "hooks": [{ "type": "command", "command": "\"$MG_HOME/bin/machine-god-bridge-bun\" \"$MG_HOME/reflect/hook.ts\" stop",   "timeout": 5 }] }],
  "UserPromptSubmit":   [{ "hooks": [{ "type": "command", "command": "\"$MG_HOME/bin/machine-god-bridge-bun\" \"$MG_HOME/reflect/hook.ts\" prompt", "timeout": 5 }] }]
} }
```
Windows: same with `%MG_HOME%` and the `.exe` path. Check that `$MG_HOME` is expanded in the hook environment (launcher exports it, the child inherits it);
otherwise write absolute paths at install time. The hooks exit 0 on every internal error and have a hard 2.5 s self-stop.
`claude -p` calls made by reflection set `MG_REFLECT_RUNNING=1`, which makes all four hooks no-ops (prevents recursion).

## 4. First-run companion
After the companion asked the user ("Machine God can reflect after each task and learn lessons; task summaries (redacted, capped) go to the AI you choose. Turn on?"),
on yes run `machine-god improve enable`, on no run `machine-god improve disable`. Until then the state is "unset": capture + injection only, no reflection, no network.
(This needs one added call in `firstrun/mg-firstrun.js`; not done here.)

## 5. Switch storage to the GRID unified.db later
All code talks to the `Db` interface in `core.ts` (`run/all/get/tx/close`) and all tables are prefixed `mgr_`, so they can live inside `unified.db` unchanged.
1. Once: `MG_REFLECT_DB=<data dir>/unified.db machine-god improve status` creates the tables there (`CREATE TABLE IF NOT EXISTS`, no existing table altered).
2. Migrate old rows (same column order, run once, then keep `reflect.db` as backup):
   ```sql
   ATTACH '<data dir>/reflect.db' AS old;
   INSERT OR IGNORE INTO mgr_events SELECT * FROM old.mgr_events;   -- same for mgr_tasks, mgr_lessons, mgr_lesson_versions, mgr_proposals, mgr_meta
   ```
3. Make it permanent: either export `MG_REFLECT_DB` in the launcher, or change the one-line default in `core.ts` `dbPath` to `grid/udb.js` `dbFile()`. Hooks, reflect and CLI all go through `dbPath`.
4. Optional: mirror lessons into `durable_memory` (kind `lesson`, subject = lesson id, value = text) so other connected AIs see them; add it as a hook in `learn.ts` `learn()` after the insert.
Check before switching: unified.db journal mode and busy handling under concurrent GRID writers (`core.ts` sets `busy_timeout=300`, WAL, and hooks swallow lock errors).

## 6. Checks after integrating
```sh
export MG_DATA_DIR=$(mktemp -d)
machine-god improve enable && machine-god improve run --backend dry && machine-god improve status
cd reflect && bun test
```
Rollback of the whole feature: remove the hooks plugin entry, the `improve)` launcher case and the seven files; user data is only `reflect.db`, `reflect.state`, `reflect.log`, `reflect-backups/`.
