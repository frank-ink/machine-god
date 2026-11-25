"""Contract and dry-run tests for the authoritative top-level resolver.

Stdlib-only (unittest), no network access, no hardcoded host paths. The test runs isolated against temporary directories and patches os.environ for reproducible resolution.
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
RESOLVER = PLUGIN_ROOT / "f3_paths.py"
CONTRACT = PLUGIN_ROOT / "docs" / "zero" / "contract_env.json"


def _load_resolver() -> ModuleType:
    """Loads the top-level file directly from the path (no package import needed)."""
    spec = importlib.util.spec_from_file_location("f3_paths_top_level", RESOLVER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load resolver: %s" % RESOLVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


f3 = _load_resolver()


class DryRunContractTest(unittest.TestCase):
    def test_optional_import_present(self) -> None:
        source = RESOLVER.read_text(encoding="utf-8")
        self.assertIn("from typing import", source)
        self.assertIn("Optional", source)
        self.assertTrue(hasattr(f3, "Optional"))

    def test_dry_run_returns_db_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "nested" / "unified.db"
            resolved = f3.ensure_db_with_env(
                {"F3_DRY_RUN": "1", "F3_DB_PATH": str(db)}
            )
            self.assertIsInstance(resolved, Path)
            self.assertEqual(resolved, db)
            self.assertFalse(db.parent.exists(), "dry-run must not create directories")

    def test_dry_run_requires_db_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(f3.PathsError):
                f3.ensure_db_with_env(
                    {
                        "F3_DRY_RUN": "1",
                        "FRANK3_DATA": str(Path(tmp) / "ignored"),
                    }
                )

    def test_dry_run_ignores_other_path_variables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "explicit.db"
            resolved = f3.ensure_db_with_env(
                {
                    "F3_DRY_RUN": "true",
                    "F3_DB_PATH": str(db),
                    "FRANK3_DATA": str(Path(tmp) / "other"),
                    "FRANKENSTEIN3_ROOT": str(Path(tmp) / "other2"),
                    "CLAUDE_PLUGIN_DATA": str(Path(tmp) / "other3"),
                }
            )
            self.assertEqual(resolved, db)

    def test_truthy_values_activate_dry_run(self) -> None:
        for raw in ("1", "true", "TRUE", "yes", "on"):
            with tempfile.TemporaryDirectory() as tmp:
                db = Path(tmp) / "x.db"
                resolved = f3.ensure_db_with_env(
                    {"F3_DRY_RUN": raw, "F3_DB_PATH": str(db)}
                )
                self.assertEqual(resolved, db, "raw=%s" % raw)

    def test_dry_run_zero_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "sub" / "dir" / "unified.db"
            before = sorted(p.name for p in root.iterdir())
            f3.ensure_db_with_env({"F3_DRY_RUN": "1", "F3_DB_PATH": str(db)})
            after = sorted(p.name for p in root.iterdir())
            self.assertEqual(before, after)
            self.assertFalse(db.parent.exists())
            self.assertFalse(db.exists())

    def test_dry_run_data_dir_derivation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "unified.db"
            data_dir = f3.resolve_data_dir_with_env(
                {"F3_DRY_RUN": "1", "F3_DB_PATH": str(db)}
            )
            self.assertEqual(data_dir, Path(tmp))

    def test_contract_points_to_top_level_resolver(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        contract = json.loads(text)
        self.assertEqual(contract["sources"]["path_resolution"], "f3_paths.py")
        self.assertEqual(contract["resolver"], "f3_paths.py")
        self.assertEqual(contract["precedence_source"], "f3_paths.py")
        self.assertNotIn("scripts/star/f3_paths.py", text)

    def test_manifest_resolver_points_to_top_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "HOME": tmp,
                "F3_DRY_RUN": "1",
                "F3_DB_PATH": str(Path(tmp) / "unified.db"),
            }
            with mock.patch.dict(os.environ, env, clear=True):
                paths = f3.resolve_manifest_paths()
        self.assertEqual(Path(paths["resolver"]), RESOLVER)
        self.assertEqual(Path(paths["contract"]), CONTRACT)


if __name__ == "__main__":
    unittest.main()
