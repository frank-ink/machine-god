"""Machine-checkable invariants for the documented data-directory resolution order.

Stdlib only. Run from the plugin directory:
    python3 -m unittest discover -s tests
    python3 -m pytest tests

Isolation contract (machine-checkable):
  * every environment change is applied to ``os.environ`` (and restored afterwards),
  * every resolved data directory is asserted to live inside a temporary tree,
  * no test reads or writes the real ``$HOME``,
  * the documented precedence is verified behaviourally (measured): install.sh and
    f3_pfade.py are both executed under controlled environments and must resolve
    to the same path,
  * README markers are parsed at test time (not hard-coded) and compared to the
    measured behaviour,
  * README / plugin.json / marketplace.json metadata are compared field by field.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]
README = PLUGIN_DIR / "README.md"
INSTALL_SH = PLUGIN_DIR / "install.sh"
PLUGIN_JSON = PLUGIN_DIR / ".claude-plugin" / "plugin.json"
F3_PFADE_PY = PLUGIN_DIR / "scripts" / "star" / "f3_pfade.py"
THIS_TEST_FILE = Path(__file__).resolve()

#: Real HOME is captured once, only to PROVE that no test touches it.
REAL_HOME = Path(os.path.expanduser("~")).resolve()

#: Slot names used by the resolution logic.
SLOT_FRANK3_DATA = "FRANK3_DATA"
SLOT_CLAUDE_PLUGIN_DATA = "CLAUDE_PLUGIN_DATA"
SLOT_XDG_DATA_HOME = "XDG_DATA_HOME"
SLOT_HOME_DEFAULT = "HOME_DEFAULT"

#: Regexes parsed from README.md at test time to recover the documented order.
README_MARKER_RE = re.compile(r"^\s*\d+\.\s*`\$([A-Z_]+)`")
README_HOME_DEFAULT_RE = re.compile(r"^\s*\d+\.\s*`~/\.local/share/frankenstein3`")

# Portability leak pattern: only real host/path leaks.
HOME_PATH_PATTERN = re.compile(
    r'(?:'
    r'/home/[A-Za-z0-9_.-]+'
    r'|/Users/[A-Za-z0-9_.-]+'
    r'|/root/'
    r'|/opt/[A-Za-z0-9_.-]+'
    r'|[A-Za-z]:\\Users\\[A-Za-z0-9_.-]+'
    r'|(?!localhost\b)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.(?:local|lan|home\.arpa|internal|test|example|invalid)'
    r')',
    re.IGNORECASE
)


def parse_readme_documented_order(text: str) -> list[str]:
    """Parse the documented precedence order from README.md at test time.

    Returns slot names in documented order, e.g.
    ["FRANK3_DATA", "CLAUDE_PLUGIN_DATA", "XDG_DATA_HOME", "HOME_DEFAULT"].
    """
    order: list[str] = []
    seen_home_default = False
    for line in text.splitlines():
        m = README_MARKER_RE.match(line)
        if m:
            order.append(m.group(1))
            continue
        if (not seen_home_default) and README_HOME_DEFAULT_RE.match(line):
            order.append(SLOT_HOME_DEFAULT)
            seen_home_default = True
    return order


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def patched_env(**values):
    """Apply environment values to ``os.environ`` and restore them afterwards.

    ``None`` removes the variable. This is the ONLY sanctioned way to change
    the environment in this suite, so every change is applied to the real
    process environment (and therefore visible to the code under test).
    """
    missing = object()
    previous = {key: os.environ.get(key, missing) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)
        yield os.environ
    finally:
        for key, value in previous.items():
            if value is missing:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextlib.contextmanager
def isolated_env(root):
    """Point HOME (and the Windows equivalent) at a temporary tree.

    The real ``$HOME`` is never read or written by any test using this helper.
    """
    root = Path(root).resolve()
    home = root / "home"
    home.mkdir(parents=True, exist_ok=True)
    with patched_env(
        HOME=str(home),
        USERPROFILE=str(home),
        FRANK3_DATA=None,
        CLAUDE_PLUGIN_DATA=None,
        XDG_DATA_HOME=None,
        PLUGIN_ROOT=None,
    ):
        yield home


def load_module(path: Path, name: str):
    """Import a python file by path (stdlib only, no sys.path pollution)."""
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def is_inside(child: Path, parent: Path) -> bool:
    """True iff ``child`` resolves inside ``parent``."""
    try:
        Path(child).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def extract_install_data_dir(output: str) -> Path | None:
    """Extract the resolved data dir from install.sh output.

    Prefers a ``DATA_DIR=<path>`` line; falls back to the last absolute path.
    """
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("DATA_DIR="):
            p = Path(line[len("DATA_DIR="):].strip())
            if p.is_absolute():
                return p
    found: Path | None = None
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("/") or re.match(r"^[A-Za-z]:\\", line):
            p = Path(line)
            if p.is_absolute():
                found = p
    return found


def readme_metadata(text: str) -> dict:
    """Parse the structured metadata block of README.md."""
    fields = {}
    for key in ("Name", "Version", "Author", "Marketplace"):
        match = re.search(r"^\*\*" + key + r"\*\*:\s*(.+?)\s*$", text, re.MULTILINE)
        if match is None:
            raise AssertionError(f"README missing metadata field: {key}")
        fields[key.lower()] = match.group(1).strip()
    return fields


def author_names(obj) -> set:
    """Collect author-ish names from a JSON object (string/dict/list shapes)."""
    names = set()
    if not isinstance(obj, dict):
        return names
    for key in ("author", "author_name", "authors", "maintainer", "maintainers", "owner"):
        value = obj.get(key)
        if isinstance(value, str):
            if value.strip():
                names.add(value.strip())
        elif isinstance(value, dict):
            for sub in ("name", "author"):
                sub_value = value.get(sub)
                if isinstance(sub_value, str) and sub_value.strip():
                    names.add(sub_value.strip())
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    names.add(item.strip())
                elif isinstance(item, dict):
                    for sub in ("name", "author"):
                        sub_value = item.get(sub)
                        if isinstance(sub_value, str) and sub_value.strip():
                            names.add(sub_value.strip())
    return names


def marketplace_entries(data) -> list:
    """Plugin entries declared by a marketplace.json document."""
    entries = []
    if isinstance(data, dict):
        plugins = data.get("plugins")
        if isinstance(plugins, list):
            for item in plugins:
                if isinstance(item, dict):
                    entries.append(item)
        if isinstance(data.get("plugin"), dict):
            entries.append(data["plugin"])
    return entries


# ---------------------------------------------------------------------------
# README documentation invariants
# ---------------------------------------------------------------------------

class ReadmeDocumentationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readme_text = README.read_text(encoding="utf-8")
        cls.documented_order = parse_readme_documented_order(cls.readme_text)

    def test_readme_present(self) -> None:
        self.assertTrue(README.is_file(), README)

    def test_readme_documents_precedence_order(self) -> None:
        """README must document a non-empty precedence order with known slots."""
        self.assertGreater(
            len(self.documented_order), 0, "README documents no precedence markers"
        )
        self.assertIn(SLOT_FRANK3_DATA, self.documented_order)
        self.assertIn(SLOT_HOME_DEFAULT, self.documented_order)

    def test_readme_markers_are_unique(self) -> None:
        """Each documented marker must appear exactly once in the README."""
        marker_count = 0
        for line in self.readme_text.splitlines():
            if README_MARKER_RE.match(line) or README_HOME_DEFAULT_RE.match(line):
                marker_count += 1
        self.assertEqual(
            marker_count,
            len(self.documented_order),
            "README markers are not unique or are duplicated",
        )

    def test_no_conflicting_location_claim(self) -> None:
        lowered = self.readme_text.lower()
        for phrase in (
            "neben",
            "ausserhalb",
            "outside",
            "sibling",
            "elternordner",
            "parent directory",
        ):
            self.assertNotIn(
                phrase, lowered, f"conflicting location claim present: {phrase}"
            )

    def test_plugin_root_honoured(self) -> None:
        self.assertIn("$PLUGIN_ROOT", self.readme_text)

    def test_installer_and_python_agreement_documented(self) -> None:
        both = [
            line
            for line in self.readme_text.splitlines()
            if "install.sh" in line and "f3_pfade.py" in line
        ]
        self.assertTrue(
            both, "README does not state that installer and Python agree"
        )

    def test_referenced_implementations_exist(self) -> None:
        self.assertTrue(INSTALL_SH.is_file())
        matches = sorted(PLUGIN_DIR.glob("**/f3_pfade.py"))
        self.assertEqual(
            1, len(matches), f"expected exactly one f3_pfade.py, got {matches}"
        )


# ---------------------------------------------------------------------------
# metadata: README <-> plugin.json <-> marketplace.json
# ---------------------------------------------------------------------------

class MetadataAgreementTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.readme_text = README.read_text(encoding="utf-8")
        cls.meta = readme_metadata(cls.readme_text)

    def marketplace_path(self) -> Path:
        """Locate and open marketplace.json (never guessed from a substring)."""
        candidates = [
            PLUGIN_DIR / ".claude-plugin" / "marketplace.json",
            PLUGIN_DIR / "marketplace.json",
            PLUGIN_DIR.parent / "marketplace.json",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        matches = sorted(PLUGIN_DIR.glob("**/marketplace.json"))
        self.assertTrue(matches, "marketplace.json not found in plugin tree")
        return matches[0]

    def test_readme_metadata_fields_present(self) -> None:
        self.assertEqual("frankenstein3", self.meta["name"])
        self.assertEqual("3.0.0", self.meta["version"])
        self.assertTrue(self.meta["author"])
        self.assertIn("@", self.meta["marketplace"])

    def test_plugin_json_matches_readme(self) -> None:
        self.assertTrue(PLUGIN_JSON.is_file(), PLUGIN_JSON)
        data = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
        self.assertEqual(self.meta["name"], data.get("name"))
        self.assertEqual(self.meta["version"], data.get("version"))
        authors = author_names(data)
        self.assertTrue(authors, "plugin.json declares no author field")
        self.assertIn(
            self.meta["author"],
            authors,
            f"README author {self.meta['author']!r} not in plugin.json authors {authors}",
        )

    def test_marketplace_json_is_opened_and_parsed(self) -> None:
        path = self.marketplace_path()
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict, f"marketplace.json must contain an object: {path}")

    def test_marketplace_json_matches_readme(self) -> None:
        path = self.marketplace_path()
        data = json.loads(path.read_text(encoding="utf-8"))
        marketplace_name, _, plugin_name = self.meta["marketplace"].partition("@")
        self.assertTrue(marketplace_name)
        self.assertTrue(plugin_name)

        if isinstance(data.get("name"), str):
            self.assertEqual(
                marketplace_name,
                data["name"],
                f"marketplace name mismatch in {path}",
            )

        entries = marketplace_entries(data)
        if entries:
            names = [e.get("name") for e in entries if isinstance(e.get("name"), str)]
            self.assertIn(
                plugin_name,
                names,
                f"marketplace.json does not declare plugin {plugin_name!r}: {names}",
            )
            for entry in entries:
                if entry.get("name") == plugin_name and isinstance(entry.get("version"), str):
                    self.assertEqual(self.meta["version"], entry["version"])
        else:
            self.assertEqual(marketplace_name, data.get("name"))

    def test_author_agreement_across_manifests(self) -> None:
        plugin_data = json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))
        market_data = json.loads(self.marketplace_path().read_text(encoding="utf-8"))
        plugin_authors = author_names(plugin_data)
        market_authors = author_names(market_data)
        self.assertTrue(plugin_authors, "plugin.json declares no author")
        declared = plugin_authors | market_authors
        self.assertIn(
            self.meta["author"],
            declared,
            f"README author {self.meta['author']!r} matches no manifest author {declared}",
        )
        if market_authors:
            self.assertTrue(
                market_authors & plugin_authors,
                f"marketplace author {market_authors} disagrees with plugin.json author {plugin_authors}",
            )


# ---------------------------------------------------------------------------
# behavioural data-directory resolution (measured, isolated)
# ---------------------------------------------------------------------------

class DataDirResolutionBehaviourTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module(F3_PFADE_PY, "f3_pfade_under_test")
        cls.readme_text = README.read_text(encoding="utf-8")
        cls.documented_order = parse_readme_documented_order(cls.readme_text)

    def test_isolation_helper_replaces_home(self) -> None:
        """The isolation helper must really replace HOME in os.environ."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with isolated_env(root) as home:
                self.assertNotEqual(home.resolve(), REAL_HOME)
                self.assertEqual(Path(os.environ["HOME"]).resolve(), home.resolve())
                self.assertNotEqual(Path.home().resolve(), REAL_HOME)

    def _run_install_sh_resolve(self, env_overrides: dict, home: Path | None = None) -> Path:
        """Copy plugin to temp tree, run install.sh with env, return resolved data dir.

        The resolved path is extracted from install.sh stdout (DATA_DIR= line or
        last absolute path). The installer output is scanned for portability leaks.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            test_plugin = root / "frankenstein3"
            shutil.copytree(PLUGIN_DIR, test_plugin)
            install_sh = test_plugin / "install.sh"
            install_sh.chmod(0o755)

            if home is None:
                home = root / "home"
            home.mkdir(parents=True, exist_ok=True)

            env = os.environ.copy()
            env.update(env_overrides)
            env["HOME"] = str(home)
            env["USERPROFILE"] = str(home)
            env["PLUGIN_ROOT"] = str(test_plugin)
            for key in (
                SLOT_FRANK3_DATA,
                SLOT_CLAUDE_PLUGIN_DATA,
                SLOT_XDG_DATA_HOME,
            ):
                if key not in env_overrides:
                    env.pop(key, None)

            result = subprocess.run(
                ["bash", str(install_sh)],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(test_plugin),
                timeout=30,
            )
            self.assertEqual(
                0,
                result.returncode,
                f"install.sh failed in temp copy: stdout={result.stdout} stderr={result.stderr}",
            )

            output = result.stdout + result.stderr
            home_matches = HOME_PATH_PATTERN.findall(output)
            self.assertEqual(
                0,
                len(home_matches),
                f"install.sh output contains hard-coded paths/hostnames: {home_matches}",
            )
            self.assertNotIn(
                str(REAL_HOME), output, "install.sh output references the real HOME"
            )
            self.assertIn("frankenstein3", output.lower())

            resolved = extract_install_data_dir(result.stdout)
            self.assertIsNotNone(
                resolved, f"install.sh printed no absolute data-dir path: {result.stdout!r}"
            )
            resolved = resolved.resolve()
            self.assertTrue(
                is_inside(resolved, root),
                f"installer resolved outside the temp tree: {resolved}",
            )
            return resolved

    def test_frank3_data_level_installer_and_python_agree(self) -> None:
        """FRANK3_DATA: set only that env var, run install.sh and f3_pfade.py, assert same path."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            frank = root / "frank"
            frank.mkdir()
            expected = frank.resolve()

            install_path = self._run_install_sh_resolve({SLOT_FRANK3_DATA: str(frank)})
            self.assertEqual(install_path, expected)
            self.assertTrue(is_inside(install_path, root))

            with isolated_env(root):
                with patched_env(
                    **{
                        SLOT_FRANK3_DATA: str(frank),
                        "PLUGIN_ROOT": str(PLUGIN_DIR),
                    }
                ):
                    python_path = self.module.data_dir()
            self.assertEqual(python_path, expected)
            self.assertEqual(install_path, python_path)

    def test_claude_plugin_data_level_installer_and_python_agree(self) -> None:
        """CLAUDE_PLUGIN_DATA: set only that env var, run install.sh and f3_pfade.py, assert same path."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            claude = root / "claude"
            claude.mkdir()
            expected = claude.resolve()

            install_path = self._run_install_sh_resolve(
                {SLOT_CLAUDE_PLUGIN_DATA: str(claude)}
            )
            self.assertEqual(install_path, expected)
            self.assertTrue(is_inside(install_path, root))

            with isolated_env(root):
                with patched_env(
                    **{
                        SLOT_CLAUDE_PLUGIN_DATA: str(claude),
                        "PLUGIN_ROOT": str(PLUGIN_DIR),
                    }
                ):
                    python_path = self.module.data_dir()
            self.assertEqual(python_path, expected)
            self.assertEqual(install_path, python_path)

    def test_xdg_data_home_level_installer_and_python_agree(self) -> None:
        """XDG_DATA_HOME: set only that env var, run install.sh and f3_pfade.py, assert same path."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            xdg = root / "xdg"
            xdg.mkdir()
            expected = (xdg / "frankenstein3").resolve()

            install_path = self._run_install_sh_resolve(
                {SLOT_XDG_DATA_HOME: str(xdg)}
            )
            self.assertEqual(install_path, expected)
            self.assertTrue(is_inside(install_path, root))

            with isolated_env(root):
                with patched_env(
                    **{
                        SLOT_XDG_DATA_HOME: str(xdg),
                        "PLUGIN_ROOT": str(PLUGIN_DIR),
                    }
                ):
                    python_path = self.module.data_dir()
            self.assertEqual(python_path, expected)
            self.assertEqual(install_path, python_path)

    def test_home_default_level_installer_and_python_agree(self) -> None:
        """HOME fallback: no env vars, both resolve to $HOME/.local/share/frankenstein3."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            home = root / "home"
            home.mkdir()
            expected = (home / ".local" / "share" / "frankenstein3").resolve()

            install_path = self._run_install_sh_resolve({}, home=home)
            self.assertEqual(install_path, expected)
            self.assertTrue(is_inside(install_path, root))

            with isolated_env(root):
                python_path = self.module.data_dir()
            self.assertEqual(python_path, expected)
            self.assertEqual(install_path, python_path)

    def test_readme_documented_order_matches_measured_first_winner(self) -> None:
        """When all env vars are set, the first README marker must match the measured winner."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            frank = root / "frank"
            frank.mkdir()
            claude = root / "claude"
            claude.mkdir()
            xdg = root / "xdg"
            xdg.mkdir()

            with isolated_env(root):
                with patched_env(
                    **{
                        SLOT_FRANK3_DATA: str(frank),
                        SLOT_CLAUDE_PLUGIN_DATA: str(claude),
                        SLOT_XDG_DATA_HOME: str(xdg),
                        "PLUGIN_ROOT": str(PLUGIN_DIR),
                    }
                ):
                    measured = self.module.data_dir()

        self.assertEqual(measured, frank.resolve())
        self.assertGreater(len(self.documented_order), 0)
        self.assertEqual(
            self.documented_order[0],
            SLOT_FRANK3_DATA,
            f"README first marker {self.documented_order[0]!r} != measured first winner {SLOT_FRANK3_DATA!r}",
        )

    def test_relative_xdg_data_home_raises_pfade_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with isolated_env(root):
                with patched_env(XDG_DATA_HOME="relative/xdg"):
                    with self.assertRaises(self.module.PfadeError) as ctx:
                        self.module.data_dir()
            self.assertIn("relativer Pfad nicht erlaubt", str(ctx.exception))

    def test_relative_frank3_data_raises_pfade_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with isolated_env(root):
                with patched_env(FRANK3_DATA="relative/data"):
                    with self.assertRaises(self.module.PfadeError) as ctx:
                        self.module.data_dir()
            self.assertIn("relativer Pfad nicht erlaubt", str(ctx.exception))

    def test_relative_claude_plugin_data_raises_pfade_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with isolated_env(root):
                with patched_env(CLAUDE_PLUGIN_DATA="relative/data"):
                    with self.assertRaises(self.module.PfadeError) as ctx:
                        self.module.data_dir()
            self.assertIn("relativer Pfad nicht erlaubt", str(ctx.exception))

    def test_ensure_db_target_inside_tmp(self) -> None:
        """ensure_db() must only ever target a path inside the temp tree."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            data = root / "data"
            with isolated_env(root):
                with patched_env(FRANK3_DATA=str(data)):
                    db_path = self.module.ensure_db()
            self.assertTrue(is_inside(db_path, root), f"{db_path} outside {root}")
            self.assertFalse(is_inside(db_path, REAL_HOME), "ensure_db targets real HOME")

    def test_resolved_data_dir_never_under_real_home(self) -> None:
        """Guard: no resolution branch may point into the real $HOME."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with isolated_env(root):
                for env in (
                    {SLOT_FRANK3_DATA: str(root / "a")},
                    {SLOT_CLAUDE_PLUGIN_DATA: str(root / "b")},
                    {SLOT_XDG_DATA_HOME: str(root / "c")},
                    {},
                ):
                    with self.subTest(env=sorted(env)):
                        with patched_env(**env):
                            resolved = self.module.data_dir()
                        self.assertFalse(
                            is_inside(resolved, REAL_HOME),
                            f"{resolved} is inside the real HOME",
                        )


# ---------------------------------------------------------------------------
# plugin root must be name independent (copy-to-any-name workflow)
# ---------------------------------------------------------------------------

class PluginRootNameIndependenceTest(unittest.TestCase):
    def test_plugin_root_is_name_independent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            copy_name = "zzz-copied-plugin-any-name"
            target = root / copy_name
            shutil.copytree(PLUGIN_DIR, target)
            module = load_module(target / "scripts" / "star" / "f3_pfade.py", "f3_pfade_copied")

            with patched_env(PLUGIN_ROOT=str(target)):
                resolved = module.plugin_root()
            self.assertEqual(target.resolve(), resolved)
            self.assertEqual(copy_name, resolved.name)

            with patched_env(PLUGIN_ROOT=None):
                found = module._find_plugin_root(module.CODE)
            self.assertEqual(target.resolve(), found)
            self.assertEqual(copy_name, found.name)

    def test_plugin_root_env_absolute_is_honoured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            target = root / "another-name"
            target.mkdir()
            module = load_module(F3_PFADE_PY, "f3_pfade_env_root")
            with patched_env(PLUGIN_ROOT=str(target)):
                self.assertEqual(target.resolve(), module.plugin_root())

    def test_plugin_root_relative_env_raises_pfade_error(self) -> None:
        module = load_module(F3_PFADE_PY, "f3_pfade_rel_root")
        with patched_env(PLUGIN_ROOT="relative/path"):
            with self.assertRaises(module.PfadeError):
                module.plugin_root()


# ---------------------------------------------------------------------------
# installer isolation
# ---------------------------------------------------------------------------

class InstallerIsolationTest(unittest.TestCase):
    def test_install_sh_runs_in_temp_copy(self) -> None:
        """Copy plugin to temp dir, run install.sh with an isolated HOME/XDG."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            test_plugin = root / "frankenstein3"
            shutil.copytree(PLUGIN_DIR, test_plugin)

            install_sh = test_plugin / "install.sh"
            install_sh.chmod(0o755)

            home = root / "home"
            home.mkdir()
            xdg = root / "xdg"
            xdg.mkdir()

            env = os.environ.copy()
            env["PLUGIN_ROOT"] = str(test_plugin)
            env["HOME"] = str(home)
            env["USERPROFILE"] = str(home)
            env["XDG_DATA_HOME"] = str(xdg)
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

            output = result.stdout + result.stderr
            home_matches = HOME_PATH_PATTERN.findall(output)
            self.assertEqual(
                0, len(home_matches),
                f"install.sh output contains hard-coded paths/hostnames: {home_matches}"
            )
            self.assertNotIn(
                str(REAL_HOME), output,
                "install.sh output references the real HOME",
            )
            self.assertIn("frankenstein3", output.lower())

            for candidate in (
                xdg / "frankenstein3",
                home / ".local" / "share" / "frankenstein3",
            ):
                if candidate.exists():
                    self.assertTrue(
                        is_inside(candidate, root),
                        f"installer wrote outside the temp tree: {candidate}",
                    )

    def test_f3_pfade_works_in_isolated_tmpdir(self) -> None:
        """Copy plugin to temp dir, import f3_pfade.py, verify data_dir() stays in tmp."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            test_plugin = root / "frankenstein3"
            shutil.copytree(PLUGIN_DIR, test_plugin)

            f3_pfade_path = test_plugin / "scripts" / "star" / "f3_pfade.py"
            module = load_module(f3_pfade_path, "f3_pfade_test")

            with isolated_env(root) as home:
                with patched_env(PLUGIN_ROOT=str(test_plugin)):
                    data_dir = module.data_dir()
                    plugin_root = module.plugin_root()

            self.assertIsInstance(data_dir, Path)
            self.assertIn("frankenstein3", str(data_dir))
            self.assertTrue(is_inside(data_dir, root), f"{data_dir} outside {root}")
            self.assertFalse(is_inside(data_dir, REAL_HOME), "data_dir touches real HOME")
            self.assertEqual(test_plugin.resolve(), plugin_root)
            self.assertEqual(
                (home / ".local" / "share" / "frankenstein3").resolve(),
                data_dir,
            )


# ---------------------------------------------------------------------------
# portability leak detection
# ---------------------------------------------------------------------------

class PortabilityLeakScannerTest(unittest.TestCase):
    def _scan_files(self, pattern: str, extensions: tuple) -> list:
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

    # --- Fixture-based portability leak detection tests ---

    def _create_fixture_and_scan(self, content: str, suffix: str = ".txt") -> list:
        """Create a temporary fixture file (outside the repo) and scan it."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture_path = Path(tmp) / ("fixture" + suffix)
            fixture_path.write_text(content, encoding="utf-8")
            text = fixture_path.read_text(encoding="utf-8", errors="ignore")
            return HOME_PATH_PATTERN.findall(text)

    def test_scanner_flags_home_user_path(self) -> None:
        """Fixture containing /home/<user> MUST be flagged."""
        content = "/home/alice/project/unified.db"
        matches = self._create_fixture_and_scan(content)
        self.assertTrue(
            any("/home/alice" in m for m in matches),
            f"expected /home/<user> leak to be flagged, got: {matches}"
        )

    def test_scanner_flags_windows_user_path(self) -> None:
        """Fixture containing C:\\Users\\<user> MUST be flagged."""
        content = r"C:\Users\Bob\App\Local\unified.db"
        matches = self._create_fixture_and_scan(content)
        self.assertTrue(
            any(r"C:\Users\Bob" in m for m in matches),
            f"expected Windows user path leak to be flagged, got: {matches}"
        )

    def test_scanner_flags_machine_name_with_local_tld(self) -> None:
        """Fixture containing machine-name.local MUST be flagged."""
        content = "machine-a.local"
        matches = self._create_fixture_and_scan(content)
        self.assertTrue(
            any("machine-a.local" in m for m in matches),
            f"expected machine-name.local leak to be flagged, got: {matches}"
        )

    def test_scanner_allows_bare_hostname(self) -> None:
        """Fixture containing bare hostname (machine-a) MUST NOT be flagged."""
        content = "machine-a"
        matches = self._create_fixture_and_scan(content)
        self.assertEqual(
            0, len(matches),
            f"bare hostname must not be flagged, got: {matches}"
        )

    def test_scanner_allows_localhost(self) -> None:
        """Fixture containing localhost MUST NOT be flagged (loopback permitted)."""
        content = "localhost"
        matches = self._create_fixture_and_scan(content)
        self.assertEqual(
            0, len(matches),
            f"localhost must not be flagged, got: {matches}"
        )

    def test_scanner_allows_localhost_with_tld(self) -> None:
        """Fixture containing localhost.local MUST NOT be flagged (loopback permitted)."""
        content = "localhost.local"
        matches = self._create_fixture_and_scan(content)
        self.assertEqual(
            0, len(matches),
            f"localhost.local must not be flagged, got: {matches}"
        )

    def test_scanner_allows_dotted_identifiers(self) -> None:
        """Ordinary dotted identifiers MUST NOT be flagged."""
        for token in ("os.path", "json.dumps", "unified.db", "README.md", "frankenstein-3.0"):
            with self.subTest(token=token):
                matches = self._create_fixture_and_scan(token)
                self.assertEqual(
                    0, len(matches),
                    f"pattern falsely flagged dotted identifier: {token}, got: {matches}"
                )

    def test_scanner_allows_relative_plugin_paths(self) -> None:
        """Relative plugin paths and version strings MUST NOT be flagged."""
        for token in (
            "./frankenstein3/.frankenstein3",
            "$PLUGIN_ROOT/.frankenstein3",
            "scripts/star/f3_pfade.py",
            "daten/schema_leer.sql",
            "Frankenstein 3.0",
        ):
            with self.subTest(token=token):
                matches = self._create_fixture_and_scan(token)
                self.assertEqual(
                    0, len(matches),
                    f"pattern falsely flagged relative/plugin token: {token}, got: {matches}"
                )

    def test_scanner_flags_opt_path(self) -> None:
        """Fixture containing /opt/... MUST be flagged."""
        content = "/opt/frankenstein/data/unified.db"
        matches = self._create_fixture_and_scan(content)
        self.assertTrue(
            any("/opt/frankenstein" in m for m in matches),
            f"expected /opt/ leak to be flagged, got: {matches}"
        )

    def test_scanner_flags_root_path(self) -> None:
        """Fixture containing /root/ MUST be flagged."""
        content = "/root/.config/frankenstein3/unified.db"
        matches = self._create_fixture_and_scan(content)
        self.assertTrue(
            any("/root/" in m for m in matches),
            f"expected /root/ leak to be flagged, got: {matches}"
        )

    def test_scanner_flags_multiple_leaks_in_one_file(self) -> None:
        """Scanner must find all leaks in a file with multiple violations."""
        content = """
/home/alice/project/unified.db
machine-a.local
C:\\Users\\Bob\\App\\Local\\data.db
"""
        matches = self._create_fixture_and_scan(content)
        self.assertGreaterEqual(len(matches), 3, f"expected at least 3 leaks, got: {matches}")


if __name__ == "__main__":
    unittest.main()
