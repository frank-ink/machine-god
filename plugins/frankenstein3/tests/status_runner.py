#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test-support helpers for FranKenstein 3 status/hook tests.

Canonical data-directory precedence (documented, and enforced by install.sh):

    FRANK3_DATA -> CLAUDE_PLUGIN_DATA -> XDG_DATA_HOME -> HOME

The fixture database is never guessed.  It is always derived from the *same*
environment through::

    f3_pfade.get_db_path(f3_pfade.resolve_data_dir())

so that the hook subprocess and the test observe one and the same file.
Only the two documented precedence variables are written into the hook
environment; the old "shotgun guess" list of database variables is gone.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from collections.abc import Mapping as _MappingABC
from pathlib import Path
from typing import Dict, Mapping, Optional, Union

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
STAR_DIR = PLUGIN_ROOT / "scripts" / "star"
if str(STAR_DIR) not in sys.path:
    sys.path.insert(0, str(STAR_DIR))

import f3_pfade  # noqa: E402  (sys.path bootstrap above)

#: Documented precedence variables, highest priority first.
PRECEDENCE_VARS = ("FRANK3_DATA", "CLAUDE_PLUGIN_DATA", "XDG_DATA_HOME", "HOME")

#: Variables that are *not* part of the documented contract.  Older code set
#: them as a "shotgun guess"; they are never written any more.
LEGACY_DB_ENV_VARS = (
    "FRANK3_DB",
    "FRANK3_DB_PATH",
    "FRANK3_DB_FILE",
    "FRANK3_UNIFIED_DB",
    "UNIFIED_DB",
    "UNIFIED_DB_PATH",
    "DB_PATH",
    "DATABASE_PATH",
)

#: The only variables :func:`_hook_env` is allowed to write.
HOOK_ENV_WRITE_VARS = ("FRANK3_DATA", "CLAUDE_PLUGIN_DATA")

PathLike = Union[str, "os.PathLike[str]"]


def _as_env(mapping: Mapping[str, object]) -> Dict[str, str]:
    """Normalise a mapping to ``str -> str``."""
    return {str(key): str(value) for key, value in mapping.items()}


def _merge(base: Mapping[str, str], overrides: Mapping[str, object]) -> Dict[str, str]:
    """Return *base* with *overrides* applied on top."""
    env = dict(base)
    env.update(_as_env(overrides))
    return env


def _resolve_under(env: Mapping[str, str]):
    """Resolve ``(data_dir, db_path)`` with *env* as the process environment.

    The resolution is delegated to :mod:`f3_pfade` so that Python and
    ``install.sh`` cannot drift apart.  The ambient environment is restored
    afterwards, even when the resolution raises.
    """
    saved = dict(os.environ)
    try:
        os.environ.update(_as_env(env))
        data_dir = Path(f3_pfade.resolve_data_dir())
        db_path = Path(f3_pfade.get_db_path(data_dir))
    finally:
        os.environ.clear()
        os.environ.update(saved)
    return data_dir, db_path


def fixture_db_path(env: Optional[Mapping[str, object]] = None) -> Path:
    """Return the fixture database path for *env* (default: ambient env).

    The path is derived from the documented precedence, never guessed::

        f3_pfade.get_db_path(f3_pfade.resolve_data_dir())
    """
    merged = _merge(os.environ, env or {})
    _data_dir, db_path = _resolve_under(merged)
    return db_path


# Aliases for callers that use the private / explicit spellings.
_fixture_db_path = fixture_db_path
resolve_fixture_db_path = fixture_db_path


def _hook_env(*args, **kwargs) -> Dict[str, str]:
    """Build the environment for a hook subprocess.

    Only the two documented precedence variables are written:
    ``FRANK3_DATA`` and ``CLAUDE_PLUGIN_DATA``.  The data directory is
    derived by :mod:`f3_pfade` under the very same environment, so the hook
    and the test can never disagree about the fixture database.

    Accepted call styles (all equivalent):

    * ``_hook_env()`` -- use the ambient environment.
    * ``_hook_env({"FRANK3_DATA": path})`` -- overrides on top of ambient.
    * ``_hook_env(path)`` -- shorthand for ``{"FRANK3_DATA": path}``.
    * ``_hook_env(data_dir=path)`` -- same as above.
    * ``_hook_env(env_overrides={...})`` -- explicit override mapping.
    """
    base = dict(os.environ)
    overrides: Dict[str, object] = {}

    for arg in args:
        if arg is None:
            continue
        if isinstance(arg, _MappingABC):
            overrides.update(arg)
        else:
            # A bare path is interpreted as the data directory.
            overrides["FRANK3_DATA"] = arg

    for key, value in kwargs.items():
        if key in ("data_dir", "data", "fixture_dir"):
            overrides["FRANK3_DATA"] = value
        elif key in ("env", "base_env", "environment"):
            base = _merge(base, value)
        elif key in ("env_overrides", "overrides"):
            overrides.update(value)
        else:
            overrides[key] = value

    merged = _merge(base, overrides)
    data_dir, _db_path = _resolve_under(merged)

    env = dict(merged)
    env["FRANK3_DATA"] = str(data_dir)
    env["CLAUDE_PLUGIN_DATA"] = str(data_dir)
    return env


def make_fixture_db(data_dir: PathLike) -> Path:
    """Create a minimal fixture database inside *data_dir*; return its path."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "unified.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS durable_memory ("
            "id INTEGER PRIMARY KEY, kind TEXT, value TEXT, ts TEXT)"
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def run_status(
    env: Optional[Mapping[str, object]] = None,
    script: Optional[PathLike] = None,
) -> subprocess.CompletedProcess:
    """Run the plugin status script with the canonical hook environment."""
    script_path = Path(script) if script is not None else (STAR_DIR / "status.py")
    if not script_path.exists():
        raise FileNotFoundError(f"status script not found: {script_path}")
    hook_env = _hook_env(env or {})
    return subprocess.run(
        [sys.executable, str(script_path)],
        env=hook_env,
        capture_output=True,
        text=True,
    )
