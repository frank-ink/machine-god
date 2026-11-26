#!/usr/bin/env python3
"""Hermetic and non-vacuous tests for the dry-run write-barrier hook.

GRF / ClayCode view
-------------------
R_t   = (logical snapshot of the target DB, isolated filesystem tree)
E_t   = (F3_DRY_RUN, F3_DB_PATH, hermetic subprocess environment)
F     = subprocess(hook, E_t) -> (exit code, stderr, R_{t+1})

Invariants enforced by this suite
---------------------------------
I1  The hook subprocess environment is built from an explicit allowlist.
    No ambient HOME/XDG/F3_* variable can reach the hook.
I2  F3_DRY_RUN truthy  => non-zero exit, stderr contains
    "DryRunWriteBlocked", and the target DB gains no row.
I3  F3_DRY_RUN unset   => exit 0 and at least one row is written into the
    DB named by F3_DB_PATH (the barrier is connected to that DB).
I4  No DB file is created outside the explicit F3_DB_PATH target.
I5  An invalid F3_DRY_RUN value fails closed (PathsError) and writes
    nothing.

Non-vacuity: a fake barrier that only prints a marker (never opens the DB)
violates I3/I4; a barrier that never blocks violates I2.  Both fail here.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

HOOK_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dry_run_write_barrier.py"
PLUGIN_ROOT = HOOK_SCRIPT.parents[1]

TRUTHY = ("1", "true", "yes", "on")
INVALID = ("maybe", "2", "invalid")

# Fixed, non-ambient PATH (os.defpath contains an empty entry = cwd).
HERMETIC_PATH = "/usr/local/bin:/usr/bin:/bin"

ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "HOME",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "XDG_STATE_HOME",
        "XDG_RUNTIME_DIR",
        "PYTHONIOENCODING",
        "PYTHONDONTWRITEBYTECODE",
        "CLAUDE_PLUGIN_ROOT",
        "F3_DB_PATH",
        "F3_DRY_RUN",
    }
)

DB_SUFFIXES = (".db", ".sqlite", ".sqlite3")
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "target", ".mypy_cache"}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def db_files(root: Path) -> list[Path]:
    """Return DB-like files below root (sqlite sidecars included)."""
    if not root.exists():
        return []
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            if filename.endswith(DB_SUFFIXES) or ".db-" in filename:
                found.append(Path(dirpath) / filename)
    return sorted(found)


def isolated_dirs(tmp_path: Path) -> list[Path]:
    """Directories that must stay free of DB files (isolated HOME/XDG/cwd)."""
    return [tmp_path / "home", tmp_path / "xdg", tmp_path / "cwd"]


def hermetic_env(tmp_path: Path, **overrides: str) -> dict[str, str]:
    """Build the hook environment from an explicit allowlist only.

    Nothing is inherited from os.environ: HOME, XDG_*, TMPDIR and PATH are
    pinned to hermetic values inside tmp_path, so an ambient HOME/XDG/F3_*
    variable cannot influence the hook.
    """
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    cwd = tmp_path / "cwd"
    for directory in (home, xdg, cwd):
        directory.mkdir(parents=True, exist_ok=True)
    for sub in ("config", "data", "cache", "state", "runtime"):
        (xdg / sub).mkdir(parents=True, exist_ok=True)

    env = {
        "PATH": HERMETIC_PATH,
        "HOME": str(home),
        "TMPDIR": str(tmp_path),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "XDG_CONFIG_HOME": str(xdg / "config"),
        "XDG_DATA_HOME": str(xdg / "data"),
        "XDG_CACHE_HOME": str(xdg / "cache"),
        "XDG_STATE_HOME": str(xdg / "state"),
        "XDG_RUNTIME_DIR": str(xdg / "runtime"),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT),
    }
    env.update(overrides)
    return env


def run_hook(env: dict[str, str]) -> subprocess.CompletedProcess:
    """Run the hook script with exactly the given environment."""
    return subprocess.run(
        [sys.executable, str(HOOK_SCRIPT)],
        cwd=str(PLUGIN_ROOT),
        env=dict(env),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )


def new_db(tmp_path: Path, name: str = "unified.db") -> Path:
    """Create an empty temp DB file and return its path."""
    db_path = tmp_path / name
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.touch()
    return db_path


def db_snapshot(db_path: Path) -> dict[str, list[str]]:
    """Return a deterministic logical snapshot {table: sorted row reprs}."""
    if not db_path.exists() or db_path.stat().st_size == 0:
        return {}
    uri = db_path.resolve().as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:  # pragma: no cover - defensive
        raise AssertionError(f"cannot open DB {db_path}: {exc}") from exc
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        snapshot: dict[str, list[str]] = {}
        for table in tables:
            rows = conn.execute(f'SELECT * FROM "{table}"').fetchall()
            snapshot[table] = sorted(repr(row) for row in rows)
        return snapshot
    except sqlite3.Error as exc:
        raise AssertionError(f"cannot snapshot DB {db_path}: {exc}") from exc
    finally:
        conn.close()


def total_rows(snapshot: dict[str, list[str]]) -> int:
    return sum(len(rows) for rows in snapshot.values())


def assert_no_new_rows(
    before: dict[str, list[str]], after: dict[str, list[str]], db_path: Path
) -> None:
    """The barrier must not add, change or remove a single row."""
    for table, rows in before.items():
        assert after.get(table, []) == rows, (
            f"dry-run changed table {table!r} in {db_path}: "
            f"before={rows!r} after={after.get(table)!r}"
        )
    assert total_rows(after) == total_rows(before), (
        f"dry-run wrote rows: before={total_rows(before)} after={total_rows(after)}"
    )
    for table, rows in after.items():
        if table not in before:
            assert rows == [], (
                f"dry-run created rows in new table {table!r}: {rows!r}"
            )


def _permissive_schema(db_path: Path) -> None:
    """Fallback schema for hooks that expect a pre-existing event table."""
    conn = sqlite3.connect(str(db_path))
    try:
        for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall():
            conn.execute(f'DROP TABLE IF EXISTS "{name}"')
        conn.execute(
            "CREATE TABLE hook_events ("
            "id INTEGER PRIMARY KEY, ts TEXT, hook TEXT, event TEXT, payload TEXT, "
            "data TEXT, detail TEXT, status TEXT, kind TEXT, message TEXT, "
            "source TEXT, tool TEXT, tool_name TEXT, decision TEXT, reason TEXT, "
            "blocked INTEGER, dry_run INTEGER, created_at TEXT, meta TEXT, "
            "extra TEXT, args TEXT, result TEXT, value TEXT)"
        )
        conn.commit()
    finally:
        conn.close()


def bootstrap_db(db_path: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    """Run the hook once in allowed mode so the DB carries the hook's schema.

    The allowed run is also the non-vacuity anchor: it proves that the hook
    really opens F3_DB_PATH and really writes there.
    """
    env = hermetic_env(tmp_path, F3_DB_PATH=str(db_path))
    result = run_hook(env)
    if result.returncode != 0:
        # The hook may expect a pre-existing event table: provide one and retry.
        _permissive_schema(db_path)
        result = run_hook(env)
    assert result.returncode == 0, (
        "hook could not open/write the temp DB in allowed mode: "
        f"rc={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    return result


# --------------------------------------------------------------------------
# tests
# --------------------------------------------------------------------------
@pytest.mark.parametrize("value", TRUTHY)
def test_dry_run_truthy_blocks_write(tmp_path: Path, value: str) -> None:
    """Truthy F3_DRY_RUN blocks the write: marker emitted, zero rows written."""
    db_path = new_db(tmp_path)
    plugin_db_before = set(db_files(PLUGIN_ROOT))

    bootstrap_db(db_path, tmp_path)
    before = db_snapshot(db_path)
    assert total_rows(before) >= 1, (
        "allowed-mode run wrote no row into F3_DB_PATH: the barrier would be "
        f"untested (snapshot={before!r})"
    )

    env = hermetic_env(tmp_path, F3_DB_PATH=str(db_path), F3_DRY_RUN=value)
    result = run_hook(env)

    assert result.returncode != 0, (
        f"expected non-zero exit for F3_DRY_RUN={value!r}, "
        f"got {result.returncode}; stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "DryRunWriteBlocked" in result.stderr, (
        f"expected DryRunWriteBlocked in stderr for {value!r}, "
        f"got {result.stderr!r}"
    )

    after = db_snapshot(db_path)
    assert_no_new_rows(before, after, db_path)

    # The DB file itself is writable: zero rows above are caused by the
    # hook's barrier, not by a read-only file.
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS barrier_probe (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO barrier_probe DEFAULT VALUES")
        conn.commit()
    finally:
        conn.close()

    for directory in isolated_dirs(tmp_path):
        assert db_files(directory) == [], (
            f"hook created a DB file in isolated dir {directory}: "
            f"{db_files(directory)!r}"
        )
    assert set(db_files(PLUGIN_ROOT)) == plugin_db_before, (
        "hook created a DB file outside F3_DB_PATH: "
        f"{sorted(set(db_files(PLUGIN_ROOT)) - plugin_db_before)!r}"
    )


def test_non_dry_run_allows_write(tmp_path: Path) -> None:
    """Without F3_DRY_RUN the hook exits 0 and writes into F3_DB_PATH."""
    db_path = new_db(tmp_path)
    plugin_db_before = set(db_files(PLUGIN_ROOT))
    before = db_snapshot(db_path)
    assert total_rows(before) == 0

    env = hermetic_env(tmp_path, F3_DB_PATH=str(db_path))  # F3_DRY_RUN unset
    result = run_hook(env)

    assert result.returncode == 0, (
        f"expected exit 0 in non-dry-run, got {result.returncode}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )

    after = db_snapshot(db_path)
    assert total_rows(after) >= 1, (
        "hook did not write into F3_DB_PATH: the write barrier would be "
        f"vacuous (snapshot={after!r})"
    )
    assert after != before, "hook left the target DB unchanged in allowed mode"

    for directory in isolated_dirs(tmp_path):
        assert db_files(directory) == [], (
            f"hook created a DB file in isolated dir {directory}: "
            f"{db_files(directory)!r}"
        )
    assert set(db_files(PLUGIN_ROOT)) == plugin_db_before, (
        "hook created a DB file outside F3_DB_PATH: "
        f"{sorted(set(db_files(PLUGIN_ROOT)) - plugin_db_before)!r}"
    )


@pytest.mark.parametrize("value", INVALID)
def test_invalid_dry_run_raises_paths_error(tmp_path: Path, value: str) -> None:
    """Invalid F3_DRY_RUN values fail closed with PathsError and write nothing."""
    db_path = new_db(tmp_path)
    before = db_snapshot(db_path)

    env = hermetic_env(tmp_path, F3_DB_PATH=str(db_path), F3_DRY_RUN=value)
    result = run_hook(env)

    assert result.returncode != 0, (
        f"expected non-zero exit for invalid F3_DRY_RUN={value!r}, "
        f"got {result.returncode}; stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "PathsError" in result.stderr, (
        f"expected PathsError in stderr for {value!r}, got {result.stderr!r}"
    )
    assert db_snapshot(db_path) == before, "invalid dry-run value still wrote to the DB"


def test_ambient_environment_does_not_leak(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ambient HOME/XDG/F3_* variables must not influence the hook."""
    ambient_home = tmp_path / "ambient-home"
    ambient_home.mkdir(parents=True, exist_ok=True)
    ambient_db = ambient_home / "unified.db"
    monkeypatch.setenv("HOME", str(ambient_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(ambient_home / ".local" / "share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(ambient_home / ".config"))
    monkeypatch.setenv("F3_DB_PATH", str(ambient_db))
    monkeypatch.setenv("F3_DRY_RUN", "1")  # truthy: leakage would flip the outcome

    db_path = new_db(tmp_path)
    env = hermetic_env(tmp_path, F3_DB_PATH=str(db_path))
    assert "F3_DRY_RUN" not in env, "hermetic env must not carry F3_DRY_RUN"

    result = run_hook(env)

    assert result.returncode == 0, (
        f"expected exit 0 in non-dry-run, got {result.returncode}; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert total_rows(db_snapshot(db_path)) >= 1, (
        "ambient F3_DRY_RUN/F3_DB_PATH leaked into the hook: no row was "
        "written into the explicit target DB"
    )
    assert not ambient_db.exists(), "ambient F3_DB_PATH leaked into the hook"
    assert db_files(ambient_home) == [], (
        f"ambient HOME leaked into the hook: {db_files(ambient_home)!r}"
    )


def test_truthy_barrier_requires_a_usable_db_path(tmp_path: Path) -> None:
    """The DB path is really consulted: an unusable path cannot succeed."""
    unusable = tmp_path / "missing-parent" / "unified.db"
    env = hermetic_env(tmp_path, F3_DB_PATH=str(unusable), F3_DRY_RUN="1")
    result = run_hook(env)

    assert result.returncode != 0, (
        "hook reported success for an unusable F3_DB_PATH: "
        f"rc={result.returncode} stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    if unusable.exists():
        assert total_rows(db_snapshot(unusable)) == 0, (
            "hook wrote rows into an unusable DB path"
        )


def test_hermetic_env_is_allowlisted(tmp_path: Path) -> None:
    """The subprocess environment is constructed from an explicit allowlist."""
    env = hermetic_env(tmp_path)
    assert set(env) <= ENV_ALLOWLIST, f"unexpected env keys: {sorted(set(env) - ENV_ALLOWLIST)}"
    assert set(env) == ENV_ALLOWLIST - {"F3_DB_PATH", "F3_DRY_RUN"}
    assert env["HOME"].startswith(str(tmp_path))
    assert env["XDG_DATA_HOME"].startswith(str(tmp_path))
    assert env["XDG_CONFIG_HOME"].startswith(str(tmp_path))
    assert env["TMPDIR"].startswith(str(tmp_path))
    assert env["PATH"] == HERMETIC_PATH
    assert "PYTHONPATH" not in env
    assert "PYTHONHOME" not in env
