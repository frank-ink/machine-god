#!/usr/bin/env python3
"""Dry-run write barrier hook for FranKenstein 3.

When F3_DRY_RUN is set to a truthy value (1/true/yes/on), the barrier
refuses every write to unified.db. Enforcement is real: the barrier opens
the authoritative SQLite database with PRAGMA query_only=ON and a
deny-all connection authorizer, then attempts a write inside a
transaction that must be blocked. Fail-closed: if the write is not
blocked, DryRunWriteBlocked is raised anyway.

The barrier performs zero persistent writes in any environment.

The authoritative DB path is resolved by f3_paths.resolve_db_path(); the
barrier never hard-codes a path and never reads CLAUDE_PLUGIN_ROOT.

Entry points:
  * package import  -> scripts/__init__.py runs install_path_bootstrap()
  * standalone script -> this module bootstraps the plugin root path below
"""

from __future__ import annotations

import sys
from pathlib import Path

# --- standalone script bootstrap -------------------------------------
# __init__.py only runs on package import, so a standalone script must
# install the plugin root path itself before importing f3_paths.  The
# plugin root is inserted at sys.path[0] so the authoritative
# plugins/frankenstein3/f3_paths.py wins over any other copy.
_SCRIPTS_DIR = Path(__file__).resolve().parent
_PLUGIN_ROOT = _SCRIPTS_DIR.parent
_PLUGIN_ROOT_STR = str(_PLUGIN_ROOT)
if _PLUGIN_ROOT_STR in sys.path:
    sys.path.remove(_PLUGIN_ROOT_STR)
sys.path.insert(0, _PLUGIN_ROOT_STR)

import sqlite3

from f3_paths import PathsError, _is_dry_run, resolve_db_path


class DryRunWriteBlocked(RuntimeError):
    """Raised when a write is attempted while dry-run mode is active."""


def _deny_all_authorizer(
    action: int,
    arg1: str | None,
    arg2: str | None,
    dbname: str | None,
    source: str | None,
) -> int:
    """SQLite connection authorizer that denies every action (SQLITE_DENY)."""
    return 1  # SQLITE_DENY


def barrier() -> None:
    """Enforce the dry-run write barrier at the SQLite level.

    Causal order:
      1. Query dry-run mode FIRST via f3_paths._is_dry_run().
      2. Only when active, resolve the DB path (error message + connection).
      3. Open the DB, set PRAGMA query_only=ON and a deny-all authorizer.
      4. Attempt a real CREATE TABLE inside a transaction; it must fail.
         If it does not fail, fail closed and raise DryRunWriteBlocked.
    """
    # (1) Mode check FIRST.
    dry = _is_dry_run()
    if not dry:
        return

    # (2) Resolve DB path only for the error message / connection.
    try:
        db_path = resolve_db_path()
    except PathsError as exc:
        print(f"{exc.__class__.__name__}: {exc}", file=sys.stderr)
        sys.exit(2)

    # (3) Open the DB and enforce query_only at the SQLite level.
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.set_authorizer(_deny_all_authorizer)

        # (4) Attempt a real write to prove the barrier holds (fail-closed).
        try:
            conn.execute("CREATE TABLE dry_run_barrier_probe (x INTEGER)")
            # Write was NOT blocked -> fail closed.
            conn.rollback()
            raise DryRunWriteBlocked(
                f"dry-run write barrier failed: write to {db_path} was not blocked"
            )
        except sqlite3.Error as exc:
            # Expected: write blocked by query_only / authorizer.
            conn.rollback()
            raise DryRunWriteBlocked(
                f"F3_DRY_RUN active: write to {db_path} blocked by dry-run write barrier ({exc})"
            ) from exc
    finally:
        conn.close()


def main() -> int:
    try:
        barrier()
    except DryRunWriteBlocked as exc:
        print(f"{exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1
    except PathsError as exc:
        print(f"{exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
