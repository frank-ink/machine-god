# f3_paths — one resolver, one path

## State (R_t)

- Canonical resolver: `plugins/frankenstein3/f3_paths.py` (plugin root).
- Removed: `plugins/frankenstein3/scripts/f3_paths.py` (815-char duplicate stub).
  The stub's docstring claimed a single source of truth while creating a second
  one; whenever the `scripts/` directory preceded the plugin root on `sys.path`,
  the stub shadowed the authoritative module.

## Transition (F)

`F(R_t, E_t)`: delete the script-local copy; make the authoritative module
reachable by explicit path (or package import) only; enforce the invariant with
fail-closed tests. No new resolver semantics are introduced.

## Admissibility space (M)

- `scripts/f3_paths.py` MUST NOT exist (no second copy, no shim).
- Exactly one authoritative `f3_paths.py` may exist (plugin tree or repo root).
- `PathFinder.find_spec("f3_paths", [scripts_dir, plugin_root, repo_root])`
  MUST resolve outside `scripts/`.
- Scripts may import the resolver only via explicit path or package import.

## Import contract

```python
# explicit path (preferred)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # plugin root
from f3_paths import resolve_db_path, resolve_plugin_root

# package import (repository root on sys.path)
from plugins.frankenstein3.f3_paths import resolve_db_path
```

`plugins/frankenstein3/scripts/__init__.py` installs the authoritative resolver
directory at the front of `sys.path` when the scripts package is imported, so
`import scripts.<name>` can never bind a script-local `f3_paths`.

## Evidence (E_t)

| hypothesis | mechanism | metric | status |
|---|---|---|---|
| H_SINGLE_SOURCE | delete stub + explicit-path bootstrap + invariant tests | stub absent; exactly one resolver; no shadowing under `scripts/` first on `sys.path` | MEASURED by `plugins/frankenstein3/tests/test_f3_paths_single_source.py` |
| H_SINGLE_SOURCE | pytest suite of the plugin | `pytest plugins/frankenstein3/tests/` | UNKNOWN in the authoring environment (no shell); must be run by the coordinator |
| H_SINGLE_SOURCE | per-script import check | import each script under `plugins/frankenstein3/scripts/` | UNKNOWN in the authoring environment; coordinator must run it |

## Promotion path

MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> CAUSAL_CREDIT ->
BOUNDED_ADMISSION -> REENTRY_TEST -> CONTROL_INFLUENCE

No rung is skipped: the deletion is only VERIFIED_OUTCOME once the plugin test
suite and the per-script import check have actually been executed and recorded.
