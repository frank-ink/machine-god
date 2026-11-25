#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Guards for the shared ``sys.path`` bootstrap and the qualified status import.

The bootstrap must live in ``tests/__init__.py`` (not in ``conftest.py``),
because ``conftest.py`` is loaded by pytest only.  The test-support helper
``status.py`` must be imported qualified (``from tests import status``) so it
cannot collide with ``scripts/star/status.py``.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

import tests as tests_package  # noqa: E402
from tests import status  # noqa: E402


class TestBootstrapOwnership(unittest.TestCase):
    """The bootstrap is owned by the package, not by conftest.py."""

    def test_tests_package_is_this_directory(self):
        package_file = getattr(tests_package, "__file__", None)
        self.assertIsNotNone(package_file, "tests package has no __file__")
        self.assertEqual(
            Path(package_file).resolve().parent,
            Path(__file__).resolve().parent,
        )

    def test_star_dir_on_sys_path(self):
        star_dir = str((PLUGIN_ROOT / "scripts" / "star").resolve())
        self.assertIn(star_dir, sys.path)

    def test_tests_dir_on_sys_path(self):
        self.assertIn(str(Path(__file__).resolve().parent), sys.path)

    def test_conftest_has_no_bootstrap(self):
        conftest = Path(__file__).resolve().parent / "conftest.py"
        source = conftest.read_text(encoding="utf-8")
        self.assertNotIn("sys.path.insert", source)
        self.assertNotIn("import sys", source)


class TestStatusImportIsQualified(unittest.TestCase):
    """``from tests import status`` must not resolve to scripts/star/status.py."""

    def test_status_helper_lives_in_tests_package(self):
        status_file = getattr(status, "__file__", None)
        self.assertIsNotNone(status_file, "status helper has no __file__")
        self.assertEqual(
            Path(status_file).resolve().parent,
            Path(__file__).resolve().parent,
        )

    def test_status_helper_is_not_the_star_script(self):
        star_status = (PLUGIN_ROOT / "scripts" / "star" / "status.py").resolve()
        status_file = Path(status.__file__).resolve()
        self.assertNotEqual(status_file, star_status)


if __name__ == "__main__":
    unittest.main(verbosity=2)
