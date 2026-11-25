#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the hardened status.py checks (stdlib only, no network)."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

STATUS_PATH = Path(__file__).with_name("status.py")


def _load_status():
    spec = importlib.util.spec_from_file_location("f3_status_under_test", STATUS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


status = _load_status()


def _make_plugin_root(root: Path) -> Path:
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / ".claude-plugin" / "hooks").mkdir(parents=True, exist_ok=True)
    return root


def _pass_hook_source(table: str) -> str:
    """A well-behaved dry-run hook: echoes the event and persists a row."""
    return (
        "#!/usr/bin/env python3\n"
        "import json, os, sqlite3, sys\n"
        "payload = sys.stdin.read()\n"
        "data = json.loads(payload) if payload.strip() else {}\n"
        "event = data.get('hook_event_name') or data.get('event') or 'StatusCheck'\n"
        "db = os.environ.get('F3_DB_PATH')\n"
        "conn = sqlite3.connect(db)\n"
        f"conn.execute('CREATE TABLE IF NOT EXISTS {table} (id INTEGER PRIMARY KEY, event TEXT)')\n"
        f"conn.execute('INSERT INTO {table} (event) VALUES (?)', (event,))\n"
        "conn.commit()\n"
        "conn.close()\n"
        "print(json.dumps({'ok': True, 'event': event, 'dry_run': True}))\n"
    )


def _fail_hook_source() -> str:
    """A vacuous hook: prints only {'ok': true} and persists nothing."""
    return "#!/usr/bin/env python3\nimport json\nprint(json.dumps({'ok': True}))\n"


class StatusCheckTests(unittest.TestCase):
    def test_syntax_error_is_reported_without_bytecode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "scripts"
            scripts.mkdir()
            broken = scripts / "broken_hook.py"
            broken.write_text("def broken(:\n    pass\n", encoding="utf-8")
            # The syntax error is real: a true compile must refuse it.
            with self.assertRaises(SyntaxError):
                compile(broken.read_text(encoding="utf-8"), str(broken), "exec")
            ok, msg = status.check_python_syntax(root)
            self.assertFalse(ok)
            self.assertIn("syntax errors", msg)
            self.assertIn("broken_hook.py", msg)
            # No bytecode cache may appear anywhere in the plugin tree.
            self.assertFalse(list(root.rglob("__pycache__")))
            self.assertFalse(list(root.rglob("*.pyc")))

    def test_valid_python_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "ok_hook.py").write_text("x = 1\n", encoding="utf-8")
            ok, msg = status.check_python_syntax(root)
            self.assertTrue(ok, msg)

    def test_missing_table_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schema = root / "schema.sql"
            schema.write_text(
                "CREATE TABLE goals (id INTEGER PRIMARY KEY, title TEXT);\n"
                "CREATE TABLE notes (id INTEGER PRIMARY KEY);\n",
                encoding="utf-8",
            )
            expected, err = status.read_expected_schema(schema)
            self.assertIsNone(err)
            assert expected is not None
            db = root / "unified.db"
            conn = sqlite3.connect(str(db))
            conn.execute("CREATE TABLE notes (id INTEGER PRIMARY KEY)")
            conn.commit()
            conn.close()
            ok, msg = status.check_database_schema(db, expected)
            self.assertFalse(ok)
            self.assertIn("missing tables: goals", msg)

    def test_matching_schema_passes_and_lists_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schema = root / "schema.sql"
            schema.write_text(
                "CREATE TABLE goals (id INTEGER PRIMARY KEY, title TEXT);\n"
                "CREATE TABLE notes (id INTEGER PRIMARY KEY);\n",
                encoding="utf-8",
            )
            expected, err = status.read_expected_schema(schema)
            self.assertIsNone(err)
            assert expected is not None
            db = root / "unified.db"
            conn = sqlite3.connect(str(db))
            conn.executescript(schema.read_text(encoding="utf-8"))
            conn.commit()
            conn.close()
            ok, msg = status.check_database_schema(db, expected)
            self.assertTrue(ok, msg)
            self.assertIn("PASS — tables:", msg)
            self.assertIn("goals", msg)

    def test_missing_column_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schema = root / "schema.sql"
            schema.write_text(
                "CREATE TABLE goals (id INTEGER PRIMARY KEY, title TEXT);\n",
                encoding="utf-8",
            )
            expected, err = status.read_expected_schema(schema)
            self.assertIsNone(err)
            assert expected is not None
            db = root / "unified.db"
            conn = sqlite3.connect(str(db))
            conn.execute("CREATE TABLE goals (id INTEGER PRIMARY KEY)")
            conn.commit()
            conn.close()
            ok, msg = status.check_database_schema(db, expected)
            self.assertFalse(ok)
            self.assertIn("missing columns: goals.title", msg)

    def test_writability_probe_leaves_no_residue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ok, msg = status.check_data_dir_writable(root)
            self.assertTrue(ok, msg)
            self.assertEqual(list(root.iterdir()), [])

    def test_extract_json_from_noisy_output(self) -> None:
        data = status.extract_json('log line\n{"ok": true, "digest": "x"}\n')
        self.assertIsInstance(data, dict)
        assert isinstance(data, dict)
        self.assertEqual(data.get("digest"), "x")

    def test_collect_keys_handles_nested_objects(self) -> None:
        keys = status.collect_keys({"a": {"b": [{"c": 1}]}})
        self.assertIn("a", keys)
        self.assertIn("b", keys)
        self.assertIn("c", keys)

    def test_resolve_paths_reports_failure_without_traceback(self) -> None:
        # Trigger the genuine resolution-failure branch: f3_paths cannot be
        # imported in this standalone harness. resolve_paths must report a FAIL
        # message and never leak a traceback.
        with patch.object(
            status,
            "_load_paths",
            return_value=(None, "ModuleNotFoundError: No module named 'f3_paths'"),
        ):
            paths, error = status.resolve_paths()
        self.assertIsNone(paths)
        self.assertIsInstance(error, str)
        self.assertTrue(error)
        self.assertNotIn("Traceback", error)
        self.assertNotIn("traceback", error.lower())

    # --- run_hook_dry_run ---

    def test_run_hook_dry_run_accepts_well_behaved_hook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_root = _make_plugin_root(root)
            hook = plugin_root / ".claude-plugin" / "hooks" / "digest.py"
            hook.write_text(_pass_hook_source("hook_digest"), encoding="utf-8")
            fixture_dir = root / "fixture"
            fixture_dir.mkdir()
            fixture_db = fixture_dir / "unified.db"
            schema = root / "schema.sql"
            schema.write_text("CREATE TABLE hook_digest (id INTEGER PRIMARY KEY, event TEXT);\n", encoding="utf-8")
            conn = sqlite3.connect(str(fixture_db))
            conn.executescript(schema.read_text(encoding="utf-8"))
            conn.commit()
            conn.close()
            ok, msg = status.run_hook_dry_run("digest", hook, plugin_root, fixture_dir, fixture_db)
            self.assertTrue(ok, msg)
            self.assertIn("hook_digest", msg)

    def test_run_hook_dry_run_rejects_ok_only_hook(self) -> None:
        # A hook printing only {'ok': true} must fail the non-vacuous gate.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_root = _make_plugin_root(root)
            hook = plugin_root / ".claude-plugin" / "hooks" / "digest.py"
            hook.write_text(_fail_hook_source(), encoding="utf-8")
            fixture_dir = root / "fixture"
            fixture_dir.mkdir()
            fixture_db = fixture_dir / "unified.db"
            conn = sqlite3.connect(str(fixture_db))
            conn.execute("CREATE TABLE hook_digest (id INTEGER PRIMARY KEY, event TEXT)")
            conn.commit()
            conn.close()
            ok, msg = status.run_hook_dry_run("digest", hook, plugin_root, fixture_dir, fixture_db)
            self.assertFalse(ok, msg)

    # --- check_hook_dry_runs ---

    def test_check_hook_dry_runs_all_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_root = _make_plugin_root(root)
            schema = root / "schema.sql"
            schema.write_text(
                "CREATE TABLE hook_digest (id INTEGER PRIMARY KEY, event TEXT);\n"
                "CREATE TABLE hook_reentry (id INTEGER PRIMARY KEY, event TEXT);\n"
                "CREATE TABLE hook_room_pulse (id INTEGER PRIMARY KEY, event TEXT);\n",
                encoding="utf-8",
            )
            for name in ("digest", "reentry", "room_pulse"):
                hook = plugin_root / ".claude-plugin" / "hooks" / f"{name}.py"
                hook.write_text(_pass_hook_source(f"hook_{name}"), encoding="utf-8")
            ok, msg = status.check_hook_dry_runs(plugin_root, schema)
            self.assertTrue(ok, msg)
            for name in ("digest", "reentry", "room_pulse"):
                self.assertIn(name, msg)

    def test_check_hook_dry_runs_fails_on_missing_hook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_root = _make_plugin_root(root)
            schema = root / "schema.sql"
            schema.write_text("CREATE TABLE hook_digest (id INTEGER PRIMARY KEY, event TEXT);\n", encoding="utf-8")
            ok, msg = status.check_hook_dry_runs(plugin_root, schema)
            self.assertFalse(ok, msg)
            self.assertIn("digest", msg)

    # --- find_hook ---

    def test_find_hook_prefers_canonical_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_root = _make_plugin_root(root)
            canonical = plugin_root / ".claude-plugin" / "hooks" / "digest.py"
            canonical.write_text("x = 1\n", encoding="utf-8")
            fallback = plugin_root / "scripts" / "digest.py"
            fallback.write_text("x = 2\n", encoding="utf-8")
            found = status.find_hook(plugin_root, "digest")
            self.assertIsNotNone(found)
            self.assertEqual(found, canonical)

    def test_find_hook_returns_none_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_root = _make_plugin_root(root)
            self.assertIsNone(status.find_hook(plugin_root, "does_not_exist"))

    # --- main() exit codes ---

    def _paths(self) -> status.Paths:
        return status.Paths(
            data_dir=Path("/tmp/x"),
            plugin_root=Path("/tmp/x"),
            db_path=Path("/tmp/x/unified.db"),
            schema_path=Path("/tmp/x/schema.sql"),
        )

    def test_main_exit_code_failure_when_paths_unresolved(self) -> None:
        with patch.object(status, "resolve_paths", return_value=(None, "cannot import f3_paths")):
            rc = status.main()
        self.assertEqual(rc, 1)

    def test_main_exit_code_success(self) -> None:
        with patch.object(status, "resolve_paths", return_value=(self._paths(), None)), \
             patch.object(status, "run_checks", return_value=[]):
            rc = status.main()
        self.assertEqual(rc, 0)

    def test_main_exit_code_failure_on_failed_check(self) -> None:
        with patch.object(status, "resolve_paths", return_value=(self._paths(), None)), \
             patch.object(
                 status,
                 "run_checks",
                 return_value=[("Hook dry-run", False, "FAIL: digest: no accepted row")],
             ):
            rc = status.main()
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
