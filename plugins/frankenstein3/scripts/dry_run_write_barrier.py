#!/usr/bin/env python3
"""Dry-run write-barrier hook.

Read-only probe hook. Performs zero writes to unified.db regardless of
environment. Invoked by test_dry_run_write_barrier.py with F3_DRY_RUN=1.
"""
import os
import sqlite3
import sys
from pathlib import Path


def main() -> int:
    plugin_root = Path(
        os.environ.get("CLAUDE_PLUGIN_ROOT", Path(__file__).resolve().parents[1])
    )
    db_path = plugin_root / "unified.db"

    # Read-only inspection only. No INSERT / UPDATE / DELETE / DDL.
    if db_path.exists():
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()
        finally:
            conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
