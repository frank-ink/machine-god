"""Script package bootstrap for FranKenstein 3.

Importing any module from this package makes the *authoritative* path
resolver importable under its canonical name ``f3_paths`` without ever
creating a second copy inside ``scripts/``.

The resolver is located by explicit path (never by shadowing import):
the plugin root is preferred, the repository root is the fallback.
If no authoritative resolver exists, nothing is injected and the state
stays UNKNOWN (no silent fallback module is created).
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPTS_DIR.parent
REPO_ROOT = PLUGIN_ROOT.parents[1]


def authoritative_resolver_path() -> Path | None:
    """Return the path of the single authoritative resolver, or None."""
    for candidate in (PLUGIN_ROOT / "f3_paths.py", REPO_ROOT / "f3_paths.py"):
        if candidate.is_file():
            return candidate.resolve()
    return None


def install_path_bootstrap() -> Path | None:
    """Make the authoritative resolver importable as ``f3_paths``.

    The resolver directory is prepended so that it wins over any other
    copy that might be reachable through ``sys.path`` (e.g. the scripts
    directory itself).  No module is created or shadowed here.
    """
    resolver = authoritative_resolver_path()
    if resolver is None:
        return None
    entry = str(resolver.parent)
    if entry in sys.path:
        sys.path.remove(entry)
    sys.path.insert(0, entry)
    return resolver


install_path_bootstrap()
