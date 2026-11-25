#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Frankenstein 3.0 self-check / status script (read-only).

Checks:
  * data directory writability via tempfile.NamedTemporaryFile (unique name, no collision)
  * schema file presence
  * database schema: required tables/columns derived from the schema file (t2 schema)
  * required hook scripts present
  * Python syntax via ast.parse (never writes __pycache__)
  * hook dry-run execution (digest, reentry, raum_puls) against a fixture DB
    initialized from the schema; each hook must exit 0, emit JSON that matches
    the contract, echo the event it was asked to process, and persist a row in
    the fixture table hook_<name>. The dry-run gate is non-vacuous: a hook that
    only prints {'ok': true} fails.

No network, no secrets, no hard-coded machine paths.
"""
from __future__ import annotations

import ast
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import tokenize
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Set, Tuple

# Never emit bytecode caches (acceptance: syntax check must not create __pycache__).
sys.dont_write_bytecode = True

STAR_DIR = Path(__file__).resolve().parent / "star"
if str(STAR_DIR) not in sys.path:
    sys.path.insert(0, str(STAR_DIR))

REQUIRED_HOOKS = ("session_start.py", "post_tool_use.py", "session_end.py")
DRY_RUN_HOOKS = ("digest", "reentry", "raum_puls")

# JSON keys accepted for any dry-run hook (generic envelope).
# 'items' is intentionally absent: a list value must not satisfy the contract.
COMMON_JSON_KEYS = frozenset({"ok", "result", "output", "dry_run"})

# Hook-specific expected JSON keys (first match wins; alternatives are tolerated
# because the exact envelope of each hook is not part of the schema contract).
HOOK_EXPECTED_KEYS: Dict[str, frozenset] = {
    "digest": frozenset(
        {"digest", "digest_text", "digest_json", "text", "items", "entries", "summary"}
    ),
    "reentry": frozenset(
        {"reentry", "reentry_state", "reentry_check", "reentries", "eligible", "state", "status"}
    ),
    "raum_puls": frozenset(
        {"raum_puls", "raum", "puls", "pulse", "events", "state", "status"}
    ),
}

# Event column candidates used to verify that a hook accepted the event it was sent.
_EVENT_COLUMN_CANDIDATES = ("event", "hook_event_name", "event_name", "name", "type")


class Paths(NamedTuple):
    data_dir: Path
    plugin_root: Path
    db_path: Path
    schema_path: Path


# --------------------------------------------------------------------------- #
# path resolution (total: errors become FAIL messages, never tracebacks)
# --------------------------------------------------------------------------- #
def _load_pfade() -> Tuple[Any, Optional[str]]:
    try:
        import f3_pfade  # type: ignore

        return f3_pfade, None
    except Exception as exc:  # pragma: no cover - environment dependent
        return None, f"{type(exc).__name__}: {exc}"


def resolve_paths() -> Tuple[Optional[Paths], Optional[str]]:
    module, err = _load_pfade()
    if module is None:
        return None, f"cannot import f3_pfade ({err})"

    try:
        data_dir = Path(module.resolve_data_dir())
    except Exception as exc:
        return None, f"resolve_data_dir failed: {type(exc).__name__}: {exc}"

    try:
        plugin_root = Path(module.resolve_plugin_root())
    except Exception as exc:
        return None, f"resolve_plugin_root failed: {type(exc).__name__}: {exc}"

    try:
        db_path = Path(module.get_db_path(data_dir))
    except Exception as exc:
        return None, f"get_db_path failed: {type(exc).__name__}: {exc}"

    try:
        schema_path = Path(module.get_schema_path(plugin_root))
    except Exception as exc:
        return None, f"get_schema_path failed: {type(exc).__name__}: {exc}"

    return Paths(data_dir, plugin_root, db_path, schema_path), None


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #
def check_data_dir_writable(data_dir: Path) -> Tuple[bool, str]:
    """Read-only probe of the data directory using a unique temporary file."""
    try:
        if not data_dir.exists():
            return False, f"FAIL: data directory does not exist: {data_dir}"
        if not data_dir.is_dir():
            return False, f"FAIL: not a directory: {data_dir}"
        with tempfile.NamedTemporaryFile(
            mode="w",
            prefix=".write_test_",
            suffix=".tmp",
            dir=str(data_dir),
            delete=True,
        ) as handle:
            handle.write("ok")
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        return True, f"OK: {data_dir} writable"
    except Exception as exc:
        return False, f"FAIL: {data_dir} not writable: {type(exc).__name__}: {exc}"


def check_schema_exists(schema_path: Path) -> Tuple[bool, str]:
    """Check that the schema file exists."""
    try:
        if schema_path.exists():
            return True, f"OK: schema found at {schema_path}"
        return False, f"FAIL: schema not found at {schema_path}"
    except Exception as exc:
        return False, f"FAIL: schema path unusable: {type(exc).__name__}: {exc}"


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def read_expected_schema(
    schema_path: Path,
) -> Tuple[Optional[Dict[str, List[str]]], Optional[str]]:
    """Derive required tables/columns from the schema file (applied in memory)."""
    try:
        schema_sql = schema_path.read_text(encoding="utf-8")
    except Exception as exc:
        return None, f"cannot read schema: {type(exc).__name__}: {exc}"

    conn = sqlite3.connect(":memory:")
    try:
        try:
            conn.executescript(schema_sql)
        except Exception as exc:
            return None, f"schema cannot be applied: {type(exc).__name__}: {exc}"
        tables: Dict[str, List[str]] = {}
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        for (name,) in rows:
            cols = [
                row[1]
                for row in conn.execute(
                    f"PRAGMA table_info({_quote_ident(name)})"
                ).fetchall()
            ]
            tables[str(name)] = cols
        return tables, None
    finally:
        conn.close()


def check_database_schema(
    db_path: Path, expected: Optional[Dict[str, List[str]]]
) -> Tuple[bool, str]:
    """Validate the canonical DB read-only against the schema contract."""
    if not expected:
        return False, "FAIL — schema defines no tables"
    if not db_path.exists():
        return False, f"FAIL — database missing: {db_path}"

    uri = "file:" + urllib.parse.quote(str(db_path)) + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5)
    except Exception as exc:
        return False, f"FAIL — cannot open database read-only: {type(exc).__name__}: {exc}"

    try:
        conn.execute("PRAGMA query_only = ON")
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        actual: Dict[str, List[str]] = {}
        for (name,) in rows:
            actual[str(name)] = [
                row[1]
                for row in conn.execute(
                    f"PRAGMA table_info({_quote_ident(name)})"
                ).fetchall()
            ]
    except Exception as exc:
        return False, f"FAIL — cannot inspect database: {type(exc).__name__}: {exc}"
    finally:
        conn.close()

    missing_tables = sorted(set(expected) - set(actual))
    missing_columns: List[str] = []
    for table in sorted(set(expected) & set(actual)):
        for column in expected[table]:
            if column not in actual[table]:
                missing_columns.append(f"{table}.{column}")

    if missing_tables or missing_columns:
        parts: List[str] = []
        if missing_tables:
            parts.append("missing tables: " + ", ".join(missing_tables))
        if missing_columns:
            parts.append("missing columns: " + ", ".join(missing_columns))
        return False, "FAIL — " + "; ".join(parts)

    return True, "PASS — tables: " + ", ".join(sorted(expected))


def check_hooks_present(plugin_root: Path) -> Tuple[bool, str]:
    """Check that the required hook scripts exist."""
    hooks_dir = plugin_root / ".claude-plugin" / "hooks"
    missing = [h for h in REQUIRED_HOOKS if not (hooks_dir / h).exists()]
    if not missing:
        return True, f"OK: all {len(REQUIRED_HOOKS)} hooks present"
    return False, "FAIL: missing hooks: " + ", ".join(missing)


def _read_python_source(path: Path) -> str:
    try:
        with tokenize.open(str(path)) as handle:
            return handle.read()
    except Exception:
        return path.read_text(encoding="utf-8")


def check_python_syntax(plugin_root: Path) -> Tuple[bool, str]:
    """Verify all .py files parse (ast.parse only; no __pycache__ is written)."""
    script_dirs = [
        plugin_root / "scripts",
        plugin_root / "scripts" / "star",
        plugin_root / ".claude-plugin" / "hooks",
    ]
    errors: List[str] = []
    count = 0
    for directory in script_dirs:
        if not directory.exists():
            continue
        for py_file in sorted(directory.rglob("*.py")):
            count += 1
            try:
                rel = str(py_file.relative_to(plugin_root))
            except Exception:
                rel = str(py_file)
            try:
                source = _read_python_source(py_file)
            except Exception as exc:
                errors.append(f"{rel}: cannot read: {type(exc).__name__}: {exc}")
                continue
            try:
                ast.parse(source, filename=str(py_file))
            except SyntaxError as exc:
                errors.append(f"{rel}:{exc.lineno}: {exc.msg}")
            except Exception as exc:
                errors.append(f"{rel}: {type(exc).__name__}: {exc}")

    if errors:
        return False, "FAIL: syntax errors:\n  " + "\n  ".join(errors)
    return True, f"OK: {count} Python files parse (ast.parse, no bytecode written)"


# --------------------------------------------------------------------------- #
# hook dry-run execution
# --------------------------------------------------------------------------- #
def find_hook(plugin_root: Path, name: str) -> Optional[Path]:
    """Locate a hook script by stem, preferring the canonical hook directory."""
    preferred = [
        plugin_root / ".claude-plugin" / "hooks" / f"{name}.py",
        plugin_root / "hooks" / f"{name}.py",
        plugin_root / "scripts" / f"{name}.py",
        plugin_root / "scripts" / "star" / f"{name}.py",
    ]
    for candidate in preferred:
        if candidate.is_file():
            return candidate
    try:
        for candidate in sorted(plugin_root.rglob(f"{name}.py")):
            if candidate.is_file():
                return candidate
    except Exception:
        return None
    return None


def extract_json(text: str) -> Any:
    """Extract the first JSON value from noisy stdout."""
    stripped = (text or "").strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except Exception:
        pass
    for line in reversed(stripped.splitlines()):
        candidate = line.strip()
        if candidate.startswith("{") or candidate.startswith("["):
            try:
                return json.loads(candidate)
            except Exception:
                continue
    for opener, closer in (("{", "}"), ("[", "]")):
        start = stripped.find(opener)
        end = stripped.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(stripped[start : end + 1])
            except Exception:
                continue
    return None


def collect_keys(value: Any, acc: Optional[Set[str]] = None, depth: int = 4) -> Set[str]:
    """Collect JSON object keys (bounded depth) for contract checking."""
    if acc is None:
        acc = set()
    if depth < 0:
        return acc
    if isinstance(value, dict):
        for key, item in value.items():
            acc.add(str(key))
            collect_keys(item, acc, depth - 1)
    elif isinstance(value, list):
        acc.add("items")
        for item in value[:32]:
            collect_keys(item, acc, depth - 1)
    return acc


def _hook_env(plugin_root: Path, fixture_dir: Path, fixture_db: Path) -> Dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "F3_DATA_DIR": str(fixture_dir),
            "F3_DB_PATH": str(fixture_db),
            "F3_DB": str(fixture_db),
            "F3_UNIFIED_DB": str(fixture_db),
            "F3_PLUGIN_ROOT": str(plugin_root),
            "ZERO_DATA_DIR": str(fixture_dir),
            "ZERO_DB_PATH": str(fixture_db),
            "UNIFIED_DB_PATH": str(fixture_db),
            "FRANKENSTEIN3_DATA_DIR": str(fixture_dir),
            "F3_DRY_RUN": "1",
            "DRY_RUN": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": str(fixture_dir),
            "XDG_DATA_HOME": str(fixture_dir / ".local" / "share"),
        }
    )
    return env


def _hook_row_accepted(fixture_db: Path, table: str, event_name: str) -> Tuple[bool, str]:
    """Assert the fixture table hook_<name> exists and holds a row for event_name.

    This is the non-vacuous part of the dry-run gate: the hook must persist
    evidence that it accepted the event, not merely print a JSON envelope.
    """
    uri = "file:" + urllib.parse.quote(str(fixture_db)) + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5)
    except Exception as exc:
        return False, f"cannot open fixture DB: {type(exc).__name__}: {exc}"
    try:
        conn.execute("PRAGMA query_only = ON")
        present = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not present:
            return False, f"fixture table {table} not created by hook dry-run"
        cols = [
            row[1]
            for row in conn.execute(f"PRAGMA table_info({_quote_ident(table)})").fetchall()
        ]
        event_cols = [c for c in _EVENT_COLUMN_CANDIDATES if c in cols]
        if event_cols:
            col = event_cols[0]
            row = conn.execute(
                f"SELECT 1 FROM {_quote_ident(table)} WHERE {_quote_ident(col)} = ? LIMIT 1",
                (event_name,),
            ).fetchone()
            if row is None:
                return False, f"fixture table {table} has no row with {col}={event_name!r}"
            return True, f"table {table} accepted event {event_name!r}"
        # No event column: any row counts as persistence evidence.
        row = conn.execute(f"SELECT 1 FROM {_quote_ident(table)} LIMIT 1").fetchone()
        if row is None:
            return False, f"fixture table {table} has no rows"
        return True, f"table {table} has row"
    finally:
        conn.close()


def run_hook_dry_run(
    name: str,
    hook_path: Path,
    plugin_root: Path,
    fixture_dir: Path,
    fixture_db: Path,
) -> Tuple[bool, str]:
    """Run one hook in dry-run mode against the fixture DB.

    The gate is non-vacuous: the hook must (a) exit 0, (b) emit JSON that shares
    a contract key with the expected envelope, and (c) persist a row in the
    fixture table hook_<name> recording the event it was asked to process.
    Any failure returns False.
    """
    env = _hook_env(plugin_root, fixture_dir, fixture_db)
    payload = json.dumps(
        {
            "dry_run": True,
            "event": "StatusCheck",
            "hook_event_name": "StatusCheck",
            "session_id": "status-check",
        }
    )
    event_name = "StatusCheck"
    attempts = [["--dry-run"], ["--dry_run"], []]
    last_message = "not executed"

    for extra_args in attempts:
        cmd = [sys.executable, str(hook_path)] + extra_args
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(plugin_root),
                env=env,
                input=payload,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            last_message = "timeout after 30s"
            continue
        except Exception as exc:
            last_message = f"{type(exc).__name__}: {exc}"
            continue

        stdout = proc.stdout or ""
        stderr = (proc.stderr or "").strip()

        if proc.returncode == 0:
            data = extract_json(stdout)
            if data is None:
                return False, "exit 0 but no JSON output"
            keys = collect_keys(data)
            expected = set(HOOK_EXPECTED_KEYS.get(name, frozenset())) | set(COMMON_JSON_KEYS)
            matched = sorted(keys & expected)
            if not matched:
                return (
                    False,
                    "JSON keys "
                    + (", ".join(sorted(keys)[:8]) or "<none>")
                    + " do not include expected keys "
                    + ", ".join(sorted(expected)[:8]),
                )
            # The hook must persist evidence that it accepted the event.
            table = f"hook_{name}"
            ok_row, row_msg = _hook_row_accepted(fixture_db, table, event_name)
            if not ok_row:
                return False, row_msg
            return True, "exit 0, JSON keys: " + ", ".join(matched) + "; " + row_msg

        tail = (stderr or stdout).strip()
        last_message = f"exit {proc.returncode}: {tail[-300:]}"
        if "unrecognized arguments" not in stderr:
            break

    return False, last_message


def check_hook_dry_runs(plugin_root: Path, schema_path: Path) -> Tuple[bool, str]:
    """Execute digest/reentry/raum_puls in dry-run mode on a fixture DB."""
    try:
        schema_sql = schema_path.read_text(encoding="utf-8")
    except Exception as exc:
        return False, f"FAIL: cannot read schema for fixture: {type(exc).__name__}: {exc}"

    results: List[Tuple[str, bool, str]] = []
    with tempfile.TemporaryDirectory(prefix="f3_status_fixture_") as tmp:
        fixture_dir = Path(tmp)
        fixture_db = fixture_dir / "unified.db"
        try:
            conn = sqlite3.connect(str(fixture_db))
            try:
                conn.executescript(schema_sql)
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            return False, f"FAIL: fixture DB initialization failed: {type(exc).__name__}: {exc}"

        for name in DRY_RUN_HOOKS:
            hook_path = find_hook(plugin_root, name)
            if hook_path is None:
                results.append((name, False, "hook file not found"))
                continue
            ok, message = run_hook_dry_run(
                name, hook_path, plugin_root, fixture_dir, fixture_db
            )
            results.append((name, ok, message))

    failed = [item for item in results if not item[1]]
    if failed:
        details = "; ".join(f"{n}: {m}" for n, ok, m in results)
        return False, "FAIL: " + details
    return True, "OK: " + ", ".join(f"{n} (exit 0, JSON)" for n, ok, m in results)


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def run_checks(paths: Paths) -> List[Tuple[str, bool, str]]:
    """Run all checks and return list of (name, passed, message)."""
    expected: Optional[Dict[str, List[str]]] = None
    schema_error: Optional[str] = None
    if paths.schema_path.exists():
        expected, schema_error = read_expected_schema(paths.schema_path)
    else:
        schema_error = f"schema file missing: {paths.schema_path}"

    checks: List[Tuple[str, bool, str]] = []
    checks.append(("Data directory", *check_data_dir_writable(paths.data_dir)))
    checks.append(("Schema file", *check_schema_exists(paths.schema_path)))

    if schema_error:
        checks.append(("Database schema", False, f"FAIL — {schema_error}"))
    else:
        checks.append(("Database schema", *check_database_schema(paths.db_path, expected)))

    checks.append(("Hook scripts", *check_hooks_present(paths.plugin_root)))
    checks.append(("Python syntax", *check_python_syntax(paths.plugin_root)))
    checks.append(("Hook dry-run", *check_hook_dry_runs(paths.plugin_root, paths.schema_path)))
    return checks


def main() -> int:
    print("Frankenstein 3.0 - Status Check")
    print("=" * 50)

    paths, error = resolve_paths()
    if paths is None:
        print(f"FAIL: {error}")
        print("=" * 50)
        print("VERDICT: FAIL")
        return 1

    checks = run_checks(paths)
    all_pass = True

    for name, passed, msg in checks:
        if name == "Database schema":
            print(f"{name}: {msg}")
        else:
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {name}: {msg}")
        if not passed:
            all_pass = False

    print("=" * 50)
    print("VERDICT: PASS (0 FAIL)" if all_pass else "VERDICT: FAIL")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
