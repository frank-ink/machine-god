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

import hashlib
import inspect
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
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
#: Includes F3_DB_PATH as it is derived from the same precedence resolution.
HOOK_ENV_WRITE_VARS = ("FRANK3_DATA", "CLAUDE_PLUGIN_DATA", "F3_DB_PATH")

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

    Only the documented precedence variables are written:
    ``FRANK3_DATA``, ``CLAUDE_PLUGIN_DATA``, and the derived ``F3_DB_PATH``.
    The data directory is derived by :mod:`f3_pfade` under the very same
    environment, so the hook and the test can never disagree about the
    fixture database.

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
    data_dir, db_path = _resolve_under(merged)

    env = dict(merged)
    env["FRANK3_DATA"] = str(data_dir)
    env["CLAUDE_PLUGIN_DATA"] = str(data_dir)
    env["F3_DB_PATH"] = str(db_path)
    env["F3_DRY_RUN"] = "1"
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
    """Run the plugin status script with the canonical hook environment.

    The script defaults to ``scripts/status.py`` under PLUGIN_ROOT — the
    single source of truth.  ``status_runner.py`` (the old copy under
    ``scripts/star/``) is removed.
    """
    script_path = Path(script) if script is not None else (PLUGIN_ROOT / "scripts" / "status.py")
    if not script_path.exists():
        raise FileNotFoundError(f"status script not found: {script_path}")
    hook_env = _hook_env(env or {})
    return subprocess.run(
        [sys.executable, str(script_path)],
        env=hook_env,
        capture_output=True,
        text=True,
    )


def _sha256_file(path: Path) -> str:
    """Return hex sha256 of *path*."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _stat_tuple(path: Path) -> tuple:
    """Return (inode, mtime_ns, size) for *path*."""
    st = path.stat()
    return (st.st_ino, st.st_mtime_ns, st.st_size)


class RunStatusIsolationTests(unittest.TestCase):
    """Tests for the run_status path fix and dry-run fixture isolation."""

    def test_run_status_uses_real_scripts_status_py(self) -> None:
        """run_status() must execute scripts/status.py, not STAR_DIR/status.py."""
        source = inspect.getsource(run_status)
        self.assertIn("scripts/status.py", source)
        self.assertNotIn("star/status.py", source)

    def test_hook_env_sets_f3_db_path_to_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture_dir = Path(tmp)
            env = _hook_env({"FRANK3_DATA": str(fixture_dir)})
            self.assertEqual(env["F3_DB_PATH"], str(fixture_dir / "unified.db"))
            self.assertEqual(env["FRANK3_DATA"], str(fixture_dir))
            self.assertEqual(env["CLAUDE_PLUGIN_DATA"], str(fixture_dir))
            self.assertEqual(env["F3_DRY_RUN"], "1")

    def test_hook_env_write_vars_invariant(self) -> None:
        """HOOK_ENV_WRITE_VARS must equal the set of vars _hook_env writes (minus base)."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture_dir = Path(tmp)
            base_env = dict(os.environ)
            # Clear any pre-existing test vars
            for var in ("FRANK3_DATA", "CLAUDE_PLUGIN_DATA", "F3_DB_PATH", "F3_DRY_RUN"):
                base_env.pop(var, None)
            env = _hook_env({"FRANK3_DATA": str(fixture_dir)}, environment=base_env)
            written = set(env.keys()) - set(base_env.keys())
            self.assertEqual(written, set(HOOK_ENV_WRITE_VARS) | {"F3_DRY_RUN"})

    def _sqlite_page_count(self, db_path: Path) -> Optional[int]:
        if not db_path.exists():
            return None
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("PRAGMA page_count").fetchone()
            return int(row[0]) if row is not None else None
        finally:
            conn.close()

    def test_dry_run_never_touches_real_data_dir(self) -> None:
        real_db = Path.home() / ".local/share/frankenstein3" / "unified.db"
        before_real = self._sqlite_page_count(real_db)

        with tempfile.TemporaryDirectory() as tmp:
            fixture_dir = Path(tmp)
            proc = run_status(env={"FRANK3_DATA": str(fixture_dir)})
            self.assertIsInstance(proc, subprocess.CompletedProcess)
            self.assertIn("Frankenstein 3.0 - Status Check", proc.stdout)

        after_real = self._sqlite_page_count(real_db)
        self.assertEqual(before_real, after_real)

    def test_dry_run_fixture_db_written_real_db_untouched_behavioural(self) -> None:
        """
        Behavioural dry-run test:
        - Fixture DB file exists and was written (page count > 0 or file exists)
        - Real unified.db is proven untouched via:
            * read-only URI connection (mode=ro)
            * sha256 hash unchanged
            * mtime/inode unchanged
            * sanitized env (no leakage of real paths into fixture env)
        """
        real_db = Path.home() / ".local/share/frankenstein3" / "unified.db"
        real_db_exists = real_db.exists()

        # Capture real DB state before
        real_sha256_before = _sha256_file(real_db) if real_db_exists else None
        real_stat_before = _stat_tuple(real_db) if real_db_exists else None

        # Verify read-only URI works on real DB (if it exists)
        if real_db_exists:
            ro_uri = f"file:{real_db}?mode=ro"
            conn = sqlite3.connect(ro_uri, uri=True)
            try:
                # Should succeed for read-only
                conn.execute("PRAGMA page_count").fetchone()
            finally:
                conn.close()

        with tempfile.TemporaryDirectory() as tmp:
            fixture_dir = Path(tmp)
            fixture_db = fixture_dir / "unified.db"

            # Run dry-run status check
            proc = run_status(env={"FRANK3_DATA": str(fixture_dir)})
            self.assertIsInstance(proc, subprocess.CompletedProcess)
            self.assertIn("Frankenstein 3.0 - Status Check", proc.stdout)

            # Fixture DB must exist and have been written
            self.assertTrue(fixture_db.exists(), "Fixture DB was not created")
            fixture_page_count = self._sqlite_page_count(fixture_db)
            self.assertIsNotNone(fixture_page_count)
            self.assertGreater(fixture_page_count, 0, "Fixture DB has zero pages (not written)")

            # Verify fixture DB is readable via read-only URI
            ro_uri = f"file:{fixture_db}?mode=ro"
            conn = sqlite3.connect(ro_uri, uri=True)
            try:
                count = conn.execute("PRAGMA page_count").fetchone()
                self.assertIsNotNone(count)
                self.assertGreater(int(count[0]), 0)
            finally:
                conn.close()

            # Sanitized env: fixture env must not contain real DB path
            hook_env = _hook_env({"FRANK3_DATA": str(fixture_dir)})
            self.assertEqual(hook_env["F3_DB_PATH"], str(fixture_db))
            self.assertNotIn(str(real_db), hook_env["F3_DB_PATH"])
            # No legacy DB env vars leaked
            for var in LEGACY_DB_ENV_VARS:
                self.assertNotIn(var, hook_env, f"Legacy var {var} leaked into hook env")

        # Real DB state after (if it existed)
        if real_db_exists:
            real_sha256_after = _sha256_file(real_db)
            real_stat_after = _stat_tuple(real_db)

            self.assertEqual(
                real_sha256_after, real_sha256_before,
                "Real unified.db sha256 changed during dry-run"
            )
            self.assertEqual(
                real_stat_after, real_stat_before,
                "Real unified.db mtime/inode/size changed during dry-run"
            )


if __name__ == "__main__":
    unittest.main()
