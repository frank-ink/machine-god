#!/usr/bin/env python3
"""Hermetic dry-run write-barrier test.

Invokes a dry-run hook with F3_DRY_RUN=1 and asserts zero writes to
unified.db by counting rows before and after.
"""
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dry_run_write_barrier.py"


def count_rows(db_path: Path) -> int:
    """Return total row count across all user tables in db_path."""
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        total = 0
        for (table,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ):
            try:
                total += conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            except sqlite3.Error:
                continue
        return total
    finally:
        conn.close()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="dry_run_barrier_") as tmp:
        plugin_root = Path(tmp)
        db_path = plugin_root / "unified.db"

        # Seed DB with a known row.
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("CREATE TABLE hook_events (id INTEGER PRIMARY KEY, ts TEXT)")
            conn.execute("INSERT INTO hook_events (ts) VALUES ('seed')")
            conn.commit()
        finally:
            conn.close()

        before = count_rows(db_path)
        assert before == 1, f"expected 1 seed row, got {before}"

        env = os.environ.copy()
        env["F3_DRY_RUN"] = "1"
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)

        result = subprocess.run(
            [sys.executable, str(HOOK_SCRIPT)],
            cwd=plugin_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"hook failed: {result.stderr}"

        after = count_rows(db_path)
        assert after == before, (
            f"dry-run hook wrote to DB: before={before}, after={after}"
        )

    print("dry-run write barrier: OK (zero writes under F3_DRY_RUN=1)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
