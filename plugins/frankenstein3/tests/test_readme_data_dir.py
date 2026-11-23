"""Machine-checkable invariants for the documented data-directory resolution order.

Stdlib only. Run from the plugin directory:
    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import unittest
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
README = PLUGIN_DIR / "README.md"

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


class DataDirResolutionOrderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = README.read_text(encoding="utf-8")
        cls.lines = cls.text.splitlines()

    def test_readme_present(self) -> None:
        self.assertTrue(README.is_file(), README)

    def test_exactly_one_resolution_order(self) -> None:
        for marker in ORDER:
            self.assertEqual(
                1, self.text.count(marker), f"marker not unique: {marker}"
            )

    def test_resolution_order_sequence(self) -> None:
        positions = [self.text.index(marker) for marker in ORDER]
        self.assertEqual(
            sorted(positions), positions, "resolution order is not monotonic"
        )

    def test_no_conflicting_location_claim(self) -> None:
        lowered = self.text.lower()
        for phrase in FORBIDDEN_CLAIMS:
            self.assertNotIn(
                phrase.lower(), lowered, f"conflicting location claim present: {phrase}"
            )

    def test_plugin_root_honoured(self) -> None:
        self.assertIn("$PLUGIN_ROOT", self.text)
        self.assertIn("$PLUGIN_ROOT/.frankenstein3", self.text)
        self.assertGreaterEqual(self.text.count("$PLUGIN_ROOT"), 2)

    def test_installer_and_python_agreement_documented(self) -> None:
        both = [
            line
            for line in self.lines
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


if __name__ == "__main__":
    unittest.main()
