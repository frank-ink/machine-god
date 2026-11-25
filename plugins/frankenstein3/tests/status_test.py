#!/usr/bin/env python3
"""Tests for scripts/status.py — fresh-machine and data-dir behavior.

Environment contract (setUp/tearDown symmetry)
-----------------------------------------------
The tests below deliberately remove ``HOME`` and the data-dir steering
variables to exercise the fresh-machine path.  Removing ``HOME`` from
``os.environ`` also destroys ``pathlib.Path.home()`` for every later test in
the same interpreter, so the process environment is snapshotted in ``setUp``
and restored byte-for-byte in ``tearDown`` — including the distinction
between "variable absent" and "variable present with a value".
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from status import check_data_dir, check_database, resolve_data_dir  # noqa: E402

#: Variables that steer data-dir resolution; they must never leak out of a
#: test into the rest of the process.
ENV_KEYS = ("HOME", "FRANK3_DATA", "CLAUDE_PLUGIN_DATA", "XDG_DATA_HOME")

#: Process state captured at import time, before any test mutates the
#: environment.  ``None`` means "the variable was not set".
ORIGINAL_ENV = {key: os.environ.get(key) for key in ENV_KEYS}


class EnvIsolationMixin:
    """Snapshot/restore the process environment around every test."""

    def setUp(self) -> None:
        super().setUp()
        self._saved_env = {key: os.environ.get(key) for key in ENV_KEYS}

    def tearDown(self) -> None:
        try:
            self._restore_env()
        finally:
            super().tearDown()

    def _restore_env(self) -> None:
        """Restore the snapshot taken in ``setUp`` (unset stays unset)."""
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _clear_env(self) -> None:
        """Remove every data-dir steering variable (test-local state only)."""
        for key in ENV_KEYS:
            os.environ.pop(key, None)


class TestFreshMachine(EnvIsolationMixin, unittest.TestCase):
    """A machine without Frankenstein3 data dir must report UNKNOWN/FAIL."""

    def test_non_existent_data_dir_reports_fail_with_clear_message(self):
        self._clear_env()
        os.environ["HOME"] = "/nonexistent/home/dir"
        try:
            data_dir = resolve_data_dir()
            self.assertIsNotNone(data_dir)
            status, message = check_data_dir(data_dir)
            self.assertIn(status, ("UNKNOWN", "FAIL"))
            self.assertIn("data dir", message.lower())
            self.assertNotEqual(message, "")
        finally:
            self._restore_env()

    def test_database_check_on_missing_data_dir_is_fail_or_unknown(self):
        self._clear_env()
        os.environ["HOME"] = "/nonexistent/home/dir"
        try:
            data_dir = resolve_data_dir()
            status, message = check_database(data_dir, None)
            self.assertIn(status, ("UNKNOWN", "FAIL"))
            self.assertIn("database", message.lower())
            self.assertNotEqual(message, "")
        finally:
            self._restore_env()

    def test_home_restored_after_each_test(self):
        """The previous test's tearDown must have put HOME back."""
        self.assertEqual(os.environ.get("HOME"), ORIGINAL_ENV["HOME"])


class TestHomeRestoration(unittest.TestCase):
    """After the destructive class ran, the process environment is unchanged.

    This class is defined after ``TestFreshMachine`` and also sorts after it
    (``unittest`` loads module members alphabetically, pytest keeps file
    order), so it observes the state left behind by that class.
    """

    def tearDown(self) -> None:
        # Fail-safe: repair the environment even if the assertion below
        # failed, so later tests in the same process are not poisoned.
        for key, value in ORIGINAL_ENV.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_home_restored(self):
        """HOME must equal its pre-module value after the test class ran."""
        self.assertEqual(
            os.environ.get("HOME"),
            ORIGINAL_ENV["HOME"],
            "HOME was not restored by tearDown",
        )

    def test_data_env_restored(self):
        """The remaining data-dir variables must be restored as well."""
        for key in ("FRANK3_DATA", "CLAUDE_PLUGIN_DATA", "XDG_DATA_HOME"):
            with self.subTest(key=key):
                self.assertEqual(os.environ.get(key), ORIGINAL_ENV[key])


if __name__ == "__main__":
    unittest.main()
