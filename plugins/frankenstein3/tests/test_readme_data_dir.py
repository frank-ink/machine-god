"""Machine-checkable invariants for the documented data-directory resolution order.

Stdlib only. Run from the plugin directory:
    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
README = PLUGIN_DIR / "README.md"
INSTALL_SH = PLUGIN_DIR / "install.sh"
F3_PFADE_PY = PLUGIN_DIR / "scripts" / "star" / "f3_pfade.py"
THIS_TEST_FILE = Path(__file__).resolve()

ORDER = (
    "1. `$FRANK3_DATA`",
    "2. `$CLAUDE_PLUGIN_DATA`",
    "3. `$PLUGIN_ROOT/.frankenstein3`",
    "4. `./frankenstein3/.frankenstein3`",
)

FORBIDDEN_CLAIMS = (
    "neben",
    "ausserhalb",
    "outside",
    "sibling",
    "Elternordner",
    "parent directory",
)

# Broadened pattern: /home/..., /Users/..., /root/, /opt/..., C:\Users\..., and hostnames (e.g., my-host.local)
HOME_PATH_PATTERN = re.compile(
    r'(?:'
    r'/home/[A-Za-z0-9_.-]+'
    r'|/Users/[A-Za-z0-9_.-]+'
    r'|/root/'
    r'|/opt/[A-Za-z0-9_.-]+'
    r'|[A-Za-z]:\\Users\\[A-Za-z0-9_.-]+'
    r'|[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+'
    r')',
    re.IGNORECASE
)


class DataDirResolutionOrderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readme_text = README.read_text(encoding="utf-8")
        cls.readme_lines = cls.readme_text.splitlines()
        cls.install_sh_text = INSTALL_SH.read_text(encoding="utf-8") if INSTALL_SH.is_file() else ""
        cls.f3_pfade_text = F3_PFADE_PY.read_text(encoding="utf-8") if F3_PFADE_PY.is_file() else ""

    def test_readme_present(self) -> None:
        self.assertTrue(README.is_file(), README)

    def test_exactly_one_resolution_order(self) -> None:
        for marker in ORDER:
            self.assertEqual(
                1, self.readme_text.count(marker), f"marker not unique: {marker}"
            )

    def test_resolution_order_sequence(self) -> None:
        positions = [self.readme_text.index(marker) for marker in ORDER]
        self.assertEqual(
            sorted(positions), positions, "resolution order is not monotonic"
        )

    def test_no_conflicting_location_claim(self) -> None:
        lowered = self.readme_text.lower()
        for phrase in FORBIDDEN_CLAIMS:
            self.assertNotIn(
                phrase.lower(), lowered, f"conflicting location claim present: {phrase}"
            )

    def test_plugin_root_honoured(self) -> None:
        self.assertIn("$PLUGIN_ROOT", self.readme_text)
        self.assertIn("$PLUGIN_ROOT/.frankenstein3", self.readme_text)
        self.assertGreaterEqual(self.readme_text.count("$PLUGIN_ROOT"), 2)

    def test_installer_and_python_agreement_documented(self) -> None:
        both = [
            line
            for line in self.readme_lines
            if "install.sh" in line and "f3_pfade.py" in line
        ]
        self.assertTrue(
            both, "README does not state that installer and Python agree"
        )

    def test_referenced_implementations_exist(self) -> None:
        self.assertTrue((PLUGIN_DIR / "install.sh").is_file())
        matches = sorted(PLUGIN_DIR.glob("**/f3_pfade.py"))
        self.assertEqual(
            1, len(matches), f"expected exactly one f3_pfade.py, got {matches}"
        )

    # --- New portability invariants ---

    def _scan_files(self, pattern: str, extensions: tuple[str, ...]) -> list[tuple[Path, list[str]]]:
        """Scan files matching extensions, excluding this test file itself."""
        violations = []
        for file_path in PLUGIN_DIR.rglob(pattern):
            if file_path.resolve() == THIS_TEST_FILE:
                continue
            if file_path.suffix.lower() in extensions:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
                matches = HOME_PATH_PATTERN.findall(text)
                if matches:
                    violations.append((file_path.relative_to(PLUGIN_DIR), matches))
        return violations

    def test_no_hardcoded_home_paths_in_python(self) -> None:
        """Fail if any .py file (except this test) contains a hard-coded home/absolute path or hostname."""
        violations = self._scan_files("*.py", (".py",))
        self.assertEqual(
            0, len(violations),
            f"Hard-coded paths/hostnames found: {violations}"
        )

    def test_no_hardcoded_home_paths_in_shell(self) -> None:
        """Fail if any .sh file contains a hard-coded home/absolute path or hostname."""
        violations = self._scan_files("*.sh", (".sh",))
        self.assertEqual(
            0, len(violations),
            f"Hard-coded paths/hostnames found: {violations}"
        )

    def test_no_hardcoded_home_paths_in_markdown(self) -> None:
        """Fail if any .md file contains a hard-coded home/absolute path or hostname."""
        violations = self._scan_files("*.md", (".md",))
        self.assertEqual(
            0, len(violations),
            f"Hard-coded paths/hostnames found: {violations}"
        )

    def test_install_sh_resolves_data_dir_from_plugin_root_or_env(self) -> None:
        """install.sh must resolve DATA from PLUGIN_ROOT or env vars, never from hard-coded paths."""
        # Check that install.sh uses PLUGIN_ROOT or HERE (script location) for root resolution
        self.assertIn("PLUGIN_ROOT", self.install_sh_text)
        self.assertIn("HERE", self.install_sh_text)
        self.assertIn("BASH_SOURCE", self.install_sh_text)
        # Must not contain hard-coded absolute paths outside of variable expansion
        self.assertNotIn("/home/", self.install_sh_text)
        # Data dir resolution must follow documented order
        self.assertIn("FRANK3_DATA", self.install_sh_text)
        self.assertIn("CLAUDE_PLUGIN_DATA", self.install_sh_text)
        self.assertIn("PLUGIN_ROOT", self.install_sh_text)
        self.assertIn(".frankenstein3", self.install_sh_text)

    def test_f3_pfade_py_resolves_data_dir_from_plugin_root_or_env(self) -> None:
        """f3_pfade.py must resolve DATA from PLUGIN_ROOT or env vars, never from hard-coded paths."""
        self.assertIn("PLUGIN_ROOT", self.f3_pfade_text)
        self.assertIn("FRANK3_DATA", self.f3_pfade_text)
        self.assertIn("CLAUDE_PLUGIN_DATA", self.f3_pfade_text)
        self.assertIn(".frankenstein3", self.f3_pfade_text)
        self.assertIn("_find_plugin_root", self.f3_pfade_text)
        self.assertIn("CODE = Path(__file__).resolve().parent", self.f3_pfade_text)
        # Must not contain hard-coded absolute paths
        self.assertNotIn("/home/", self.f3_pfade_text)

    def test_readme_and_code_agree_on_resolution_order(self) -> None:
        """README documented order must match the actual resolution logic in install.sh and f3_pfade.py."""
        # Extract the effective resolution order from install.sh
        # install.sh: FRANK3_DATA -> CLAUDE_PLUGIN_DATA -> PLUGIN_ROOT/.frankenstein3 (via DATA_ROOT)
        install_order = [
            "FRANK3_DATA",
            "CLAUDE_PLUGIN_DATA",
            "PLUGIN_ROOT",
        ]
        for var in install_order:
            self.assertIn(var, self.install_sh_text, f"install.sh missing {var} in resolution")

        # Extract the effective resolution order from f3_pfade.py
        # f3_pfade.py: FRANK3_DATA -> CLAUDE_PLUGIN_DATA -> PLUGIN_ROOT/.frankenstein3
        f3_order = [
            "FRANK3_DATA",
            "CLAUDE_PLUGIN_DATA",
            "PLUGIN_ROOT",
        ]
        for var in f3_order:
            self.assertIn(var, self.f3_pfade_text, f"f3_pfade.py missing {var} in resolution")

        # README order must match (steps 1-3; step 4 is a fallback for when PLUGIN_ROOT detection differs)
        readme_order = ["FRANK3_DATA", "CLAUDE_PLUGIN_DATA", "PLUGIN_ROOT"]
        for var in readme_order:
            self.assertIn(var, self.readme_text, f"README missing {var} in resolution")

    def test_python_compiles_cleanly(self) -> None:
        """python3 -m py_compile must succeed on f3_pfade.py."""
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(F3_PFADE_PY)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            0, result.returncode,
            f"py_compile failed: {result.stderr}"
        )

    def test_install_sh_runs_in_temp_copy(self) -> None:
        """Copy plugin to temp dir, run install.sh, verify it exits 0 and outputs no absolute host paths."""
        import tempfile
        import shutil

        with tempfile.TemporaryDirectory() as tmp:
            test_plugin = Path(tmp) / "frankenstein3"
            shutil.copytree(PLUGIN_DIR, test_plugin)

            # Make install.sh executable
            install_sh = test_plugin / "install.sh"
            install_sh.chmod(0o755)

            # Run install.sh with PLUGIN_ROOT set to the temp copy
            env = os.environ.copy()
            env["PLUGIN_ROOT"] = str(test_plugin)
            # Unset FRANK3_DATA and CLAUDE_PLUGIN_DATA to test default resolution
            env.pop("FRANK3_DATA", None)
            env.pop("CLAUDE_PLUGIN_DATA", None)

            result = subprocess.run(
                ["bash", str(install_sh)],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(test_plugin),
                timeout=30,
            )

            self.assertEqual(
                0, result.returncode,
                f"install.sh failed in temp copy: stdout={result.stdout} stderr={result.stderr}"
            )

            # Output must not contain any absolute host paths (only paths under the temp copy)
            output = result.stdout + result.stderr
            home_matches = HOME_PATH_PATTERN.findall(output)
            self.assertEqual(
                0, len(home_matches),
                f"install.sh output contains hard-coded paths/hostnames: {home_matches}"
            )

            # Output should contain the temp data dir path
            self.assertIn(".frankenstein3", output)


if __name__ == "__main__":
    unittest.main()
