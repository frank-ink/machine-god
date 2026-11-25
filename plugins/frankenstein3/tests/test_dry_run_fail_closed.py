"""Fail-closed dry-run behaviour for install.sh (README rows 1c and 1g).

Run:
    python3 -m unittest plugins/frankenstein3/tests/test_dry_run_fail_closed.py
    python3 plugins/frankenstein3/tests/test_dry_run_fail_closed.py
"""

import os
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALL_SH = os.path.join(ROOT, "install.sh")


def run_install(args=(), env_extra=None, env_remove=()):
    """Run install.sh via bash with a modified environment."""
    env = dict(os.environ)
    for key in env_remove:
        env.pop(key, None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["bash", INSTALL_SH, *args],
        env=env,
        capture_output=True,
        text=True,
    )


class DryRunFailClosedTests(unittest.TestCase):
    def test_row_1c_dry_run_without_f3_db_path_exits_zero(self):
        # F3_DRY_RUN=1 ./install.sh (without F3_DB_PATH) -> exit 0, temp dir used
        with tempfile.TemporaryDirectory() as tmp:
            result = run_install(
                env_extra={"TMPDIR": tmp, "F3_DRY_RUN": "1"},
                env_remove=("TEMP", "TMP"),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("DRY-RUN: Data dir would be:", result.stdout)
            self.assertIn(tmp, result.stdout)

    def test_row_1g_unset_temp_vars_aborts(self):
        # unset TMPDIR TEMP TMP; ./install.sh --dry-run -> non-zero, error text
        result = run_install(
            args=("--dry-run",),
            env_extra={"F3_DRY_RUN": "1"},
            env_remove=("TMPDIR", "TEMP", "TMP"),
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("No temporary directory found", result.stderr)


if __name__ == "__main__":
    unittest.main()
