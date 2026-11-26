# Frankenstein 3.0 - Claude-Code-Plugin

A self-contained bundle. No network, no LLM calls, no secrets.

## Plugin Metadata
- **Name**: frankenstein3
- **Version**: 3.0.0
- **Author**: Frankenstein Team
- **Marketplace**: frankenstein3@frankenstein3

These fields correspond to `plugin.json` and `marketplace.json`.

## Portability
No hardcoded user paths and no machine names. All paths are
derived at runtime from environment variables (`$HOME`, `$USERPROFILE`, `$XDG_DATA_HOME`,
`$FRANK3_DATA`, ...) or from the relative bundle layout (directory of the
plugin file itself). The bundle can be copied to another machine
and used there without modifications.
### Path Resolution (f3_paths.py)
The canonical portability implementation lives in
`scripts/star/f3_paths.py` (and the bundle copy `f3_paths.py` in the plugin root;
both files are identical in content). All scripts must use this resolver;
there must be no second, custom path logic.

Environment variables (in this precedence order, first match wins):

Data Root (without unified.db):
1. `$FRANK3_DATA` - absolute path or `~`/`~/...`
2. `$FRANKENSTEIN3_ROOT` - Plugin/Data Root override
3. `$F3_DB_PATH` - Data Root derived from this (parent directory if file,
   directory itself if directory)
4. `$CLAUDE_PLUGIN_DATA` - absolute path or `~`/`~/...`
5. `$XDG_DATA_HOME/frankenstein3` - XDG Base Directory Specification
6. `$HOME/.local/share/frankenstein3` - XDG fallback via `$HOME`
7. `%USERPROFILE%\AppData\Local\frankenstein3` - Windows fallback via `$USERPROFILE`

DB Path (`unified.db`):
1. `$FRANK3_DATA/unified.db`
2. `$FRANKENSTEIN3_ROOT/unified.db`
3. `$F3_DB_PATH` (file or directory; if directory, `unified.db` is appended)
4. `$CLAUDE_PLUGIN_DATA/unified.db`
5. `$XDG_DATA_HOME/frankenstein3/unified.db`
6. `$HOME/.local/share/frankenstein3/unified.db`
7. `%USERPROFILE%\AppData\Local\frankenstein3/unified.db`

Paths are tilde-expanded (`$HOME`, otherwise `$USERPROFILE`), but not
resolved (no symlink resolution). Relative paths are made absolute against the
current working directory. Hardcoded user paths or machine names are never
written into the code.
### Bundle Layout (relative)
`resolve_plugin_root()` returns the directory of the calling file,
`resolve_bundle_path(...)` joins relative components (e.g., script,
contract, schema). The installer finds the plugin root via
`.claude-plugin/plugin.json` next to `install.sh` (or via `$PLUGIN_ROOT`,
only for reading plugin code). The `unified.db` is never written under
the plugin root.
### Hook Environment Variables (Contract, shared with Rust/TS)
Hooks receive a unified environment. The contract exists as a bundle copy
**in the plugin** under `docs/zero/contract_env.json` (path relative to plugin root).
In the repository, the same file additionally resides under `docs/zero/contract_env.json`
relative to the repository root; for standalone installation, only the plugin copy is relevant.

The contract defines six fields:

- `precedence` - resolution order of environment variables
- `data_dir_precedence` - resolution order of the data directory
- `hook_env_writes` - variables **written** by hooks
- `ambient_passthrough` - **passed-through** (ambient) variables
- `admissibility_space` - admissibility space with path variables and mode flags
- `sources` - provenance for each contract component

`hook_env_writes` and `ambient_passthrough` are disjoint. The following variables
are **written** (in this precedence order):

1. `FRANK3_DATA` - resolved data directory (highest priority)
2. `CLAUDE_PLUGIN_DATA` - identical to FRANK3_DATA
3. `F3_DB_PATH` - path to `unified.db` in the data directory

Passed through (ambient, never rewritten):

4. `F3_DRY_RUN` - `"1"` in dry-run mode, otherwise `"0"` (mode flag, never participates
   in path precedence)
5. `XDG_DATA_HOME` - is **not** rewritten (ambient)
6. `HOME` - is **not** rewritten (ambient)

Legacy variables (`FRANKENSTEIN_DB`, `FRANKENSTEIN3_DB`, `F3_DB`, `UNIFIED_DB`)
are **never** set.
### Manifest Paths (zero-manifest.json)
`zero-manifest.json` contains no fixed absolute paths. The `paths`
block refers exclusively to env-derived variables or relative
bundle paths:

| Key | Value | Meaning |
|---|---|---|
| `plugin_root` | `${PLUGIN_ROOT}` | Root of the installed bundle (resolved relative to the bundle file) |
| `data_dir` | `${FRANK3_DATA}` | User-specific data directory (fallback `$XDG_DATA_HOME/frankenstein3`, then `$HOME/.local/share/frankenstein3`) |
| `db_path` | `${F3_DB_PATH}` | Path to `unified.db` in the data directory |
| `resolver` | `scripts/star/f3_paths.py` | Relative bundle path of the canonical resolver |
| `contract` | `docs/zero/contract_env.json` | Relative bundle path of the hook contract |

The host replaces `${...}` at runtime; without the host the relative
bundle paths remain valid.

### Behavior of status.py
`python3 tests/status.py` (path relative to the plugin root, as defined in
the contract `docs/zero/contract_env.json`) checks the data directory and
the database and outputs a PASS/FAIL/UNKNOWN table.

The database `unified.db` is checked **read-only**: it is opened in
read-only mode (`mode=ro`, `PRAGMA query_only = ON`) and never modified.
No tables are created and no rows are written.

The data directory is probed for writability with a one-time temporary
file test (`NamedTemporaryFile`, `delete=True`); the test file is
deleted immediately and does not persist.

The dry-run of the hooks (`digest`, `reentry`, `room_pulse`) writes
exclusively to the fixture database passed via `F3_DB_PATH`, never to
the real data directory (`$HOME/.local/share/frankenstein3` or the actual
file resolved via `$FRANK3_DATA` / `$CLAUDE_PLUGIN_DATA`).
### Behavior on a Fresh Machine
On a machine without a Frankenstein3 data folder, `status.py` reports **UNKNOWN** for the data folder and database checks (or FAIL if the resolved path exists but is empty/unreadable). After the first `install.sh` (or manual `ensure_db()`), the status changes to PASS.

## Installation
```bash
# 1. Unpack bundle (arbitrary location, no user path in code)
unzip frankenstein3.zip
cd frankenstein3

# 2. Run installer (idempotent, non-interactive, no network)
./install.sh

# 3. Register in Claude Code (if claude CLI is in PATH)
#    The installer does this automatically (best effort). Otherwise in Claude Code:
#    /plugin marketplace add <PATH_TO_PLUGIN>
#    /plugin install frankenstein3@frankenstein3

# 4. Restart Claude Code or /plugin reload
```

The installer creates the data folder, initializes `unified.db` from `data/schema_empty.sql` (only if the schema is included), runs the status self-check, and registers the marketplace (if `claude` is in PATH). If `claude` is missing, the installer outputs the two manual commands and exits successfully.

### Dry Run -- Isolation Guaranteed
```bash
# Option 1: Flag on installer (installer writes nothing)
./install.sh --dry-run

# Option 2: Environment variable (uniform for installer AND Python)
F3_DRY_RUN=1 F3_DB_PATH="$PWD/fixture/unified.db" ./install.sh
# or
F3_DRY_RUN=true F3_DB_PATH="$PWD/fixture/unified.db" ./install.sh
# or
F3_DRY_RUN=yes F3_DB_PATH="$PWD/fixture/unified.db" ./install.sh
# or
F3_DRY_RUN=on F3_DB_PATH="$PWD/fixture/unified.db" ./install.sh
```

**IMPORTANT -- Dry-Run Isolation (Code Behavior, Not Prose):**
- When `F3_DRY_RUN` is set to a truthy value (`1`, `true`, `yes`, `on`,
   case-insensitive) **or** `--dry-run` is passed,
   the unified dry-run mode activates (`F3_DRY_RUN=1`).
- If additionally `F3_DB_PATH` is set, the resolver returns **exclusively**
   `F3_DB_PATH` (fixture mode).
   `FRANK3_DATA`, `FRANKENSTEIN3_ROOT`, `CLAUDE_PLUGIN_DATA`, `XDG_DATA_HOME`,
   `HOME` are ignored.
- If `F3_DB_PATH` is **not** set, the resolver uses a temporary
   directory under `$TMPDIR` (fallback chain: `$TEMP` -> `$TMP`).
   If all three are missing or none is an existing directory, the
   resolver aborts with an error (no fallback to `/tmp`).
- It never writes to the real data directory
   (`$HOME/.local/share/frankenstein3` or `$FRANK3_DATA`/`$CLAUDE_PLUGIN_DATA`).
- **No directories are created, no database initialized, no self-check
   executed, no registration performed** - the installer exits immediately
   after path resolution.
- The unified truthy set for `F3_DRY_RUN` is:
  `{'1', 'true', 'yes', 'on'}` (case-insensitive). Everything else (incl.
  `false`, `0`, `no`, `off`, `maybe`, empty) is falsy (fail-closed).
- Temporary paths use the fallback chain `$TMPDIR` -> `$TEMP` -> `$TMP`;
  if none is set or no existing directory, the installer aborts with an
  error (no hardcoded `/tmp`), preserving Windows/portability.

**Example (Fixture DB in Dry-Run):**
```bash
mkdir -p "$PWD/fixture"
F3_DB_PATH="$PWD/fixture/unified.db" \
F3_DRY_RUN=1 \
python3 -c "
import sys; sys.path.insert(0, 'scripts/star')
import f3_paths
print('DB path:', f3_paths.get_db_path())
# Returns the fixture path - NOT the real data folder
"
```

**Example (installer dry-run without fixture):**
```bash
# Requires TMPDIR, TEMP, or TMP in the environment (existing directory)
TMPDIR="$PWD/custom_tmp" ./install.sh --dry-run
# Temp path contains custom_tmp, no hardcoded /tmp
```

### Manual database initialization (without installer)
```bash
FRANK3_DATA="$HOME/.local/share/frankenstein3" python3 -c "
import sys; sys.path.insert(0, 'scripts/star')
import f3_paths; f3_paths.ensure_db()
print('DB:', f3_paths.get_db_path())
"
## Copying to another machine (portable copy/install)
The bundle contains no source-machine paths. The data directory is resolved anew on the target machine; no source-machine paths are copied along.

1. **Pack the bundle** (on the source machine, from the repository root):
   ```bash
   tar -czf frankenstein3.tar.gz -C plugins frankenstein3
   ```
2. **Copy to the target machine** (USB, `scp`, `rsync`, Git - any method):
   ```bash
   scp frankenstein3.tar.gz <targethost>:
   ```
3. **Unpack on the target machine** (target directory freely selectable):
   ```bash
   ssh <targethost> 'mkdir -p "$HOME/apps" && tar -xzf frankenstein3.tar.gz -C "$HOME/apps"'
   ```
4. **Dry run on the target machine** (proves: no hardcoded paths, no writes):
   ```bash
   ssh <targethost> 'cd "$HOME/apps/frankenstein3" && ./install.sh --dry-run'
   ```
5. **Installation on the target machine**:
   ```bash
   ssh <targethost> 'cd "$HOME/apps/frankenstein3" && ./install.sh'
   ```
   The installer resolves the data directory **on the target machine** using the same precedence (FRANK3_DATA -> FRANKENSTEIN3_ROOT -> F3_DB_PATH -> CLAUDE_PLUGIN_DATA -> `$XDG_DATA_HOME/frankenstein3` -> `$HOME/.local/share/frankenstein3`).
6. **Optional: custom data directory** (e.g., portable on a USB drive):
   ```bash
   FRANK3_DATA="$HOME/apps/f3-data" ./install.sh
   ```
7. **Registration** (see above). Done.
### Portability test without foreign machine (HOME override)
The following test simulates a foreign machine completely locally:
```bash
tmp="$(mktemp -d)"
cp -R plugins/frankenstein3 "$tmp/plugin"
mkdir -p "$tmp/home" "$tmp/xdg"
HOME="$tmp/home" XDG_DATA_HOME="$tmp/xdg" "$tmp/plugin/install.sh" --dry-run
HOME="$tmp/home" XDG_DATA_HOME="$tmp/xdg" "$tmp/plugin/install.sh"
```
Expectation: Exit code 0, data directory under `$tmp/xdg/frankenstein3` (or
`$tmp/home/.local/share/frankenstein3`), no attachments to foreign paths.

## Verify (Verification Checklist)

The following checklist is executable: each item can be verified with a command.
### 1. Dry-Run Isolation
| Step | Command | Expected Result |
|---|---|---|
| 1a | `./install.sh --dry-run` | Exit code 0, no file created, no repository required |
| 1b | `F3_DRY_RUN=1 F3_DB_PATH="$PWD/fixture/unified.db" python3 -c "import sys; sys.path.insert(0, 'scripts/star'); import f3_paths; print(f3_paths.get_db_path())"` | Returns the fixture path, not the real data directory |
| 1c | `F3_DRY_RUN=1 ./install.sh` (without `F3_DB_PATH`) | Uses temporary directory (requires TMPDIR/TEMP/TMP), exit code 0 |
| 1d | `F3_DRY_RUN=false ./install.sh --dry-run` | Falsy, but `--dry-run` flag sets `F3_DRY_RUN=true` -> dry run active |
| 1e | `F3_DRY_RUN=1 F3_DB_PATH="$PWD/fixture/unified.db" ./install.sh` | Exit code 0, DRY-RUN output, **no file in real data directory**, no DB init |
| 1f | `TMPDIR="$PWD/custom_tmp" ./install.sh --dry-run` | Temp path contains `custom_tmp`, not hardcoded `/tmp` |
| 1g | `unset TMPDIR TEMP TMP; ./install.sh --dry-run` | Aborts with error "No temporary directory found" |

Truthy values for `F3_DRY_RUN`: `{'1', 'true', 'yes', 'on'}` (case-insensitive). Everything else is falsy.

### 2. Database (status.py)
| Step | Command | Expected Result |
|---|---|---|
| 2a | `python3 tests/status.py` | PASS/FAIL/UNKNOWN table; on fresh machine data directory and database UNKNOWN |
| 2b | Read-only check | `unified.db` opened with `mode=ro` and `PRAGMA query_only = ON`; no tables created, no rows written |
| 2c | Writability | One-time `NamedTemporaryFile(delete=True)` test; test file deleted immediately |
### 3. Portability
| Step | Command | Expected Result |
|---|---|---|
| 3a | `tmp="$(mktemp -d)"; cp -R plugins/frankenstein3 "$tmp/plugin"; HOME="$tmp/home" XDG_DATA_HOME="$tmp/xdg" "$tmp/plugin/install.sh" --dry-run` | Exit code 0, no fixed path, no repository root required |
| 3b | `grep -rnE '/[Hh][Oo][Mm][Ee]/[^/]+' plugins/frankenstein3 --exclude-dir=.git` | No matches (no hardcoded user paths) |
| 3c | `python3 -m py_compile plugins/frankenstein3/f3_paths.py plugins/frankenstein3/scripts/star/f3_paths.py` | Exit code 0 (all bundled scripts compile) |
| 3d | `grep -rnEi 'ai[-_]core[-_]node|local[Hh]ost|127[.]0[.]0[.]1' plugins/frankenstein3` | No machine names or hardcoded host addresses in plugin code |
| 3e | `python3 -m pytest plugins/frankenstein3/tests/test_portable_paths.py` | All tests pass (optional, if pytest is available) |
## ./install.sh --dry-run and Resolver Behavior

The dry run documents the actual resolver behavior:

1. If `F3_DRY_RUN` is set to a truthy value (`1`, `true`, `yes`, `on`,
   case-insensitive) **or** `--dry-run` is passed,
   the unified dry-run mode activates (`F3_DRY_RUN=1`).
2. If additionally `F3_DB_PATH` is set, the resolver returns **exclusively**
   `F3_DB_PATH` (fixture mode).
   `FRANK3_DATA`, `FRANKENSTEIN3_ROOT`, `CLAUDE_PLUGIN_DATA`, `XDG_DATA_HOME`,
   `HOME` are ignored.
3. If `F3_DB_PATH` is **not** set, the resolver uses a temporary
   directory under `$TMPDIR` (fallback chain: `$TEMP` -> `$TMP`).
   If all three are missing or none is an existing directory, the
   resolver aborts with an error (no fallback to `/tmp`).
4. It never writes to the real data directory.
5. **The installer aborts IMMEDIATELY: no `mkdir`, no DB initialization,
   no self-check, no registration.**
6. Without dry-run mode, the normal resolution order applies:
   `FRANK3_DATA` -> `FRANKENSTEIN3_ROOT` -> `F3_DB_PATH` ->
   `CLAUDE_PLUGIN_DATA` -> `$XDG_DATA_HOME/frankenstein3` ->
   `$HOME/.local/share/frankenstein3`.

## Questions / Open Points (UNKNOWN)

- The exact content of `data/schema_empty.sql` is not documented in this
  bundle; `ensure_db()` is treated as external until the schema is
  delivered. Status: UNKNOWN.
- Whether the `claude` CLI is in PATH and registration works automatically
  depends on the target machine. Status: UNKNOWN.
- Whether `tests/status.py` or `scripts/status.py` exists in the bundle is
  not guaranteed; the installer then reports `UNKNOWN` instead of failing.
  Status: UNKNOWN.

## Included / Not Included (Bundle Contents)
### Included
| File / Folder | Function |
|---|---|
| `install.sh` | Idempotent installer, data folder resolution, DB initialization |
| `.claude-plugin/plugin.json` | Plugin metadata and root detection |
| `plugin.json` | Plugin metadata (Name, Version, Author, Marketplace) |
| `marketplace.json` | Marketplace entry `frankenstein3@frankenstein3` |
| `data/schema_empty.sql` | Empty schema for `unified.db` |
| `scripts/star/f3_paths.py` | Path resolver and `ensure_db()` (shared with Rust/TS) |
| `f3_paths.py` | Bundle copy of path resolver in plugin root |
| `tests/status.py` | PASS/FAIL/UNKNOWN check of data folder and database |
| `tests/test_portable_paths.py` | Portability tests (env-based resolution, no fixed user paths) |
| `tests/test_dry_run_fail_closed.py` | Fail-closed dry-run tests (README lines 1c/1g) |
| `docs/zero/contract_env.json` | Hook environment contract (bundle copy) |
| `zero-manifest.json` | Host manifest with env-derived or relative paths |
| `README.md` | This document (verification contract) |

### Not Included
| File / Folder | Reason |
|---|---|
| `unified.db` | Created fresh from `data/schema_empty.sql`, never shipped |
| `$HOME/.local/share/frankenstein3` | Created at runtime on target machine |
| `$HOME/.claude/star` | Never read or modified |
| Legacy variables (`FRANKENSTEIN_DB`, `FRANKENSTEIN3_DB`, `F3_DB`, `UNIFIED_DB`) | Never set |
| Hardcoded user paths or machine names | Violates portability, not in bundle |
| Network calls | Plugin operates without network |
