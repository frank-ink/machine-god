"""Compatibility shim: re-exports the authoritative f3_paths from the plugin root.

scripts/ is on sys.path for standalone script execution, so this module would
shadow plugins/frankenstein3/f3_paths.py.  Instead of duplicating path logic
here, the authoritative module is loaded by file path and its public names are
re-exported.  There is exactly one source of truth: the plugin-root module.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# scripts/f3_paths.py -> parent = scripts/ -> parent = plugins/frankenstein3
_AUTHORITATIVE = Path(__file__).resolve().parent.parent / "f3_paths.py"

_spec = importlib.util.spec_from_file_location("f3_paths.plugin_root", _AUTHORITATIVE)
if _spec is None or _spec.loader is None:  # pragma: no cover - defensive
    raise ImportError(f"cannot load authoritative f3_paths from {_AUTHORITATIVE}")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

resolve_db_path = _module.resolve_db_path
resolve_plugin_root = _module.resolve_plugin_root
PathsError = _module.PathsError
_is_dry_run = _module._is_dry_run

__all__ = ["resolve_db_path", "resolve_plugin_root", "PathsError", "_is_dry_run"]
