#!/usr/bin/env python3
"""Misst den Plugin-Zustand (selbstenthalten): Daten-DB, Tabellen, Hooks im Trockenlauf. PASS/FAIL-Tabelle."""
import os
import sys
import json
import sqlite3
import subprocess
import time
from pathlib import Path


def resolve_data_dir() -> Path:
    """Resolve data directory via env vars -> XDG -> fallback. No hardcoded paths."""
    # 1. Explicit env vars
    for var in ("FRANK3_DATA", "CLAUDE_PLUGIN_DATA"):
        val = os.environ.get(var)
        if val:
            return Path(val).expanduser().resolve()

    # 2. XDG Base Directory
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        return Path(xdg_data).expanduser().resolve() / "frankenstein3"

    # 3. Fallback: ~/.local/share/frankenstein3
    home = Path.home()
    return home / ".local" / "share" / "frankenstein3"


def resolve_schema(script_dir: Path) -> Path:
    """Locate schema_leer.sql beside the script or one level up (plugin root)."""
    candidates = [
        script_dir / "schema_leer.sql",
        script_dir.parent / "schema_leer.sql",
        script_dir.parent / "sql" / "schema_leer.sql",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    # Fallback: expected location; caller surfaces a clear error if absent.
    return (script_dir / "schema_leer.sql").resolve()


def ensure_db(data_dir: Path) -> Path:
    """Ensure unified.db exists and is initialized from schema_leer.sql.

    Creates the data directory and the SQLite database file if missing,
    then executes the schema from schema_leer.sql so that the subsequent
    read-only connection finds the expected tables. Returns the db path.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "unified.db"

    schema_path = resolve_schema(Path(__file__).resolve().parent)

    if not db_path.exists():
        if not schema_path.is_file():
            raise FileNotFoundError(f"schema_leer.sql not found: {schema_path}")
        schema_sql = schema_path.read_text(encoding="utf-8")
        conn = sqlite3.connect(db_path, timeout=1)
        try:
            conn.executescript(schema_sql)
            conn.commit()
        finally:
            conn.close()

    return db_path


def main() -> int:
    data_dir = resolve_data_dir()
    db_path = ensure_db(data_dir)

    rows = []

    def add(name: str, status: str, detail: str = "") -> None:
        rows.append((name, status, str(detail)[:90]))

    add("data dir", "PASS" if data_dir.is_dir() else "FAIL", data_dir)

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1)
        tabs = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
        conn.close()
        add("unified.db tables", "PASS" if len(tabs) > 50 else "FAIL", f"{len(tabs)} tables")
        for t in ("zero_raum", "star_konfig", "entityos_arbeitspaket"):
            add(f"table {t}", "PASS" if t in tabs else "FAIL")
    except Exception as e:
        add("unified.db", "FAIL", e)

    script_dir = Path(__file__).parent
    for name in ("digest.py", "reentry.py"):
        t0 = time.time()
        try:
            r = subprocess.run(
                [sys.executable, script_dir / name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            json.loads(r.stdout)
            add(
                f"hook {name}",
                "PASS" if r.returncode == 0 else "FAIL",
                f"{(time.time() - t0) * 1000:.0f} ms",
            )
        except Exception as e:
            add(f"hook {name}", "FAIL", e)

    w = max(len(r[0]) for r in rows) if rows else 0
    for n, s, d in rows:
        print(f"{n:<{w}}  {s:<6} {d}")

    fails = sum(1 for r in rows if r[1] == "FAIL")
    print(f"VERDICT: {len(rows) - fails} PASS, {fails} FAIL. {'Core measured OK.' if not fails else 'FAILs present - do not claim healthy.'}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
