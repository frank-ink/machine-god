#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for f3_pfade path resolution.

The environment contract (precedence of FRANK3_DATA / CLAUDE_PLUGIN_DATA /
F3_DB_PATH / F3_DRY_RUN / XDG_DATA_HOME / HOME) is declared in
``docs/zero/contract_env.json`` and is verified here against the actual
implementations:

  * install.sh          -- data-dir precedence (measured via --dry-run)
  * f3_pfade.py         -- data-dir precedence (measured in-process)
  * status.py           -- hook environment write set (measured)
  * src/zero/, agent-sdk/src/zero/ -- optional Rust/TS consumers; when those
    trees are absent the Rust/TS coverage is honestly UNKNOWN (no skip).

Nothing here asserts a constant against itself: every order is *measured*
from a source and then compared with the declared contract.  A missing or
unreadable contract file is a hard failure, never a skipped test.

Run: python3 -m pytest plugins/frankenstein3/tests/test_pfade.py -v
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# The plugin root must be importable so that the qualified helper import
# below resolves to *this* test package (``tests.status``) and never to a
# same-named module elsewhere on ``sys.path``.
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

# Add star to path
STAR_DIR = PLUGIN_ROOT / "scripts" / "star"
if str(STAR_DIR) not in sys.path:
    sys.path.insert(0, str(STAR_DIR))

# The test-support helper (status.py) lives next to this file.
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

# Importing the package runs the shared bootstrap (tests/__init__.py).
# The helper is imported qualified so it cannot collide with
# scripts/star/status.py.
from tests import status  # noqa: E402

from f3_pfade import (  # noqa: E402
    PfadeError,
    get_db_path,
    get_schema_path,
    resolve_data_dir,
    resolve_plugin_root,
)

#: Repository root (the checkout that contains ``plugins/`` and ``docs/``).
REPO_ROOT = PLUGIN_ROOT.parent.parent

#: Canonical, machine-readable environment contract.
CONTRACT_ENV_JSON = REPO_ROOT / "docs" / "zero" / "contract_env.json"

#: Optional Rust / TypeScript source trees that may consume the contract.
RUST_SOURCE_DIR = REPO_ROOT / "src" / "zero"
TS_SOURCE_DIR = REPO_ROOT / "agent-sdk" / "src" / "zero"

#: Documented precedence for data directory resolution, highest priority first.
#: install.sh must agree exactly on these four.
DATA_DIR_PRECEDENCE_VARS = ("FRANK3_DATA", "CLAUDE_PLUGIN_DATA", "XDG_DATA_HOME", "HOME")

#: Full contract environment variable precedence (includes hook-only vars).
#: Order: data dir vars first, then hook-derived vars, then ambient fallbacks.
CONTRACT_ENV_PRECEDENCE = (
    "FRANK3_DATA",
    "CLAUDE_PLUGIN_DATA",
    "F3_DB_PATH",
    "F3_DRY_RUN",
    "XDG_DATA_HOME",
    "HOME",
)

#: Accepted key names in contract_env.json (schema tolerant on purpose:
#: the *values* are checked against the sources, not against a literal).
FLAT_KEYS = ("precedence", "env_precedence", "contract_precedence", "precedence_order")
DATA_KEYS = ("data_dir_precedence", "data_precedence", "data_dir_vars", "precedence_data_dir")
HOOK_KEYS = ("hook_env_write_vars", "hook_env_vars", "hook_write_vars", "write_vars")
EXTRA_KEYS = ("additional_vars", "extra_vars")

#: Environment variables that belong to the contract family.  A Rust/TS
#: consumer may not use one of these without declaring it in the contract.
CONTRACT_FAMILY_RE = re.compile(
    r"\b(?:F3_[A-Z0-9_]+|FRANK3_[A-Z0-9_]+|CLAUDE_PLUGIN_DATA|XDG_DATA_HOME)\b"
)


def _load_contract() -> dict:
    """Load docs/zero/contract_env.json.  Fail closed (never skip)."""
    if not CONTRACT_ENV_JSON.is_file():
        raise AssertionError(
            f"environment contract missing: {CONTRACT_ENV_JSON} "
            "(the contract file must exist; tests never skip)"
        )
    try:
        raw = json.loads(CONTRACT_ENV_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AssertionError(f"environment contract unreadable: {exc}") from exc
    if not isinstance(raw, dict):
        raise AssertionError("environment contract must be a JSON object")
    return raw


def _declared_list(contract: dict, keys) -> list | None:
    """Return the first non-empty list-of-strings found under *keys*."""
    for key in keys:
        value = contract.get(key)
        if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
            return list(value)
    return None


class TestPfadePrecedence(unittest.TestCase):
    """Test data directory resolution precedence (matches install.sh and README)."""

    def setUp(self):
        # Save original env
        self.old_env = dict(os.environ)
        # Clear relevant vars
        for var in ["FRANK3_DATA", "CLAUDE_PLUGIN_DATA", "XDG_DATA_HOME", "PLUGIN_ROOT"]:
            os.environ.pop(var, None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)

    def test_1_frank3_data_highest_priority(self):
        """FRANK3_DATA wins over everything else."""
        with tempfile.TemporaryDirectory() as tmp:
            frank3 = Path(tmp) / "frank3_data"
            os.environ["FRANK3_DATA"] = str(frank3)
            os.environ["CLAUDE_PLUGIN_DATA"] = str(Path(tmp) / "claude_plugin_data")
            os.environ["XDG_DATA_HOME"] = str(Path(tmp) / "xdg")

            result = resolve_data_dir()
            self.assertEqual(result, frank3.resolve())

    def test_2_claude_plugin_data_second(self):
        """CLAUDE_PLUGIN_DATA wins when FRANK3_DATA not set."""
        with tempfile.TemporaryDirectory() as tmp:
            claude = Path(tmp) / "claude_plugin_data"
            os.environ["CLAUDE_PLUGIN_DATA"] = str(claude)
            os.environ["XDG_DATA_HOME"] = str(Path(tmp) / "xdg")

            result = resolve_data_dir()
            self.assertEqual(result, claude.resolve())

    def test_3_xdg_data_home_third(self):
        """XDG_DATA_HOME/frankenstein3 wins when first two not set."""
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            os.environ["XDG_DATA_HOME"] = str(xdg)

            result = resolve_data_dir()
            expected = (xdg / "frankenstein3").resolve()
            self.assertEqual(result, expected)

    def test_4_xdg_fallback_fourth(self):
        """~/.local/share/frankenstein3 when nothing else set."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            os.environ["HOME"] = str(home)

            result = resolve_data_dir()
            expected = (home / ".local" / "share" / "frankenstein3").resolve()
            self.assertEqual(result, expected)

    def test_tilde_expansion(self):
        """Leading ~ expands to $HOME."""
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            os.environ["HOME"] = str(home)
            os.environ["FRANK3_DATA"] = "~/my_frank3_data"

            result = resolve_data_dir()
            expected = (home / "my_frank3_data").resolve()
            self.assertEqual(result, expected)

    def test_relative_path_resolution(self):
        """Relative paths resolve to absolute."""
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["FRANK3_DATA"] = "relative/data"

            result = resolve_data_dir()
            self.assertTrue(result.is_absolute())
            self.assertEqual(result.name, "data")

    def test_parent_directory_created(self):
        """Parent directory is created if missing."""
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "new" / "nested" / "data"
            os.environ["FRANK3_DATA"] = str(data_dir)

            result = resolve_data_dir()
            self.assertTrue(result.parent.exists())
            self.assertEqual(result, data_dir.resolve())


class TestPluginRoot(unittest.TestCase):
    """Test plugin root resolution."""

    def setUp(self):
        self.old_env = dict(os.environ)
        os.environ.pop("PLUGIN_ROOT", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)

    def test_explicit_argument(self):
        """Explicit argument takes priority."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "explicit_root"
            root.mkdir()
            (root / ".claude-plugin" / "plugin.json").parent.mkdir(parents=True)
            (root / ".claude-plugin" / "plugin.json").write_text("{}")

            result = resolve_plugin_root(explicit=str(root))
            self.assertEqual(result, root.resolve())

    def test_env_var(self):
        """PLUGIN_ROOT env var used when no explicit arg."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "env_root"
            root.mkdir()
            (root / ".claude-plugin" / "plugin.json").parent.mkdir(parents=True)
            (root / ".claude-plugin" / "plugin.json").write_text("{}")
            os.environ["PLUGIN_ROOT"] = str(root)

            result = resolve_plugin_root()
            self.assertEqual(result, root.resolve())

    def test_auto_discovery(self):
        """Walks up from __file__ to find .claude-plugin/plugin.json."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "auto_root"
            scripts_star = root / "scripts" / "star"
            scripts_star.mkdir(parents=True)
            (root / ".claude-plugin" / "plugin.json").parent.mkdir(parents=True)
            (root / ".claude-plugin" / "plugin.json").write_text("{}")

            # Simulate being called from scripts/star/f3_pfade.py
            import f3_pfade
            original_file = f3_pfade.__file__
            try:
                f3_pfade.__file__ = str(scripts_star / "f3_pfade.py")
                result = resolve_plugin_root()
                self.assertEqual(result, root.resolve())
            finally:
                f3_pfade.__file__ = original_file


class TestDerivedPaths(unittest.TestCase):
    """Test derived path helpers."""

    def test_get_db_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            db_path = get_db_path(data_dir)
            self.assertEqual(db_path, data_dir / "unified.db")

    def test_get_schema_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin_root = Path(tmp) / "plugin"
            schema_path = get_schema_path(plugin_root)
            self.assertEqual(schema_path, plugin_root / "daten" / "schema_leer.sql")


class TestPrecedenceMatchesInstallSh(unittest.TestCase):
    """f3_pfade.resolve_data_dir() must return the same path as install.sh's
    resolve_data_dir under identical env, parametrized over *every* documented
    data-dir precedence variable:

        FRANK3_DATA -> CLAUDE_PLUGIN_DATA -> XDG_DATA_HOME -> HOME

    For each slot the variable is set while all lower-priority variables are
    present as decoys, so the comparison proves the *order*, not just the
    individual slots.  This makes the module docstring claim machine-checkable
    instead of an assertion of faith.
    """

    INSTALL_SH = Path(__file__).resolve().parent.parent / "install.sh"

    def setUp(self):
        self.old_env = dict(os.environ)
        self.old_cwd = Path.cwd()
        self.tmpdir = tempfile.TemporaryDirectory(prefix="f3pfade-install-sh-")
        self.tmp = Path(self.tmpdir.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.plugin_root = self.tmp / "plugin"
        self.plugin_root.mkdir()
        (self.plugin_root / ".claude-plugin").mkdir()
        (self.plugin_root / ".claude-plugin" / "plugin.json").write_text("{}")
        self.cwd = self.tmp / "cwd"
        self.cwd.mkdir()
        # install.sh cd's into dirname(raw); ensure parents exist so dry-run
        # resolves the same way f3_pfade does.
        (self.home / ".local" / "share").mkdir(parents=True)
        for var in ["FRANK3_DATA", "CLAUDE_PLUGIN_DATA", "XDG_DATA_HOME", "PLUGIN_ROOT", "HOME"]:
            os.environ.pop(var, None)
        os.environ["HOME"] = str(self.home)
        os.environ["PLUGIN_ROOT"] = str(self.plugin_root)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)
        os.chdir(self.old_cwd)
        self.tmpdir.cleanup()

    def _install_sh_expected(self, env_overrides):
        env = os.environ.copy()
        env.update(env_overrides)
        proc = subprocess.run(
            ["bash", str(self.INSTALL_SH), "--dry-run"],
            env=env,
            cwd=str(self.cwd),
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"install.sh --dry-run failed: {proc.stderr}",
        )
        prefix = "DRY-RUN: Data dir would be: "
        for line in proc.stdout.splitlines():
            if line.startswith(prefix):
                return Path(line[len(prefix):]).resolve()
        self.fail(
            f"install.sh dry-run did not print data dir. "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )

    def _f3_pfade_actual(self, env_overrides):
        env = os.environ.copy()
        env.update(env_overrides)
        code = (
            "import sys\n"
            "sys.path.insert(0, %r)\n"
            "from f3_pfade import resolve_data_dir\n"
            "print(resolve_data_dir())"
        ) % (str(STAR_DIR),)
        proc = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            cwd=str(self.cwd),
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"f3_pfade subprocess failed: {proc.stderr}",
        )
        return Path(proc.stdout.strip()).resolve()

    def _cases(self):
        """Return ``(name, env_overrides, documented_expected_path)`` triples.

        One case per documented data-dir precedence variable; every lower-priority
        variable is set as a decoy so that the winner is proven by order.
        """
        home = self.home
        values = {
            "FRANK3_DATA": self.tmp / "frank3_abs",
            "CLAUDE_PLUGIN_DATA": self.tmp / "claude_abs",
            "XDG_DATA_HOME": self.tmp / "xdg_abs",
            "HOME": home,
        }
        documented = {
            "FRANK3_DATA": values["FRANK3_DATA"].resolve(),
            "CLAUDE_PLUGIN_DATA": values["CLAUDE_PLUGIN_DATA"].resolve(),
            "XDG_DATA_HOME": (values["XDG_DATA_HOME"] / "frankenstein3").resolve(),
            "HOME": (home / ".local" / "share" / "frankenstein3").resolve(),
        }

        cases = []
        for index, var in enumerate(DATA_DIR_PRECEDENCE_VARS):
            # this variable plus every lower-priority variable as decoy
            overrides = {name: str(values[name]) for name in DATA_DIR_PRECEDENCE_VARS[index:]}
            cases.append((f"{var}_wins", overrides, documented[var]))

        # value shapes of the highest-priority variable
        decoys = {
            "CLAUDE_PLUGIN_DATA": str(values["CLAUDE_PLUGIN_DATA"]),
            "XDG_DATA_HOME": str(values["XDG_DATA_HOME"]),
            "HOME": str(home),
        }
        cases.append((
            "frank3_data_tilde",
            dict(decoys, FRANK3_DATA="~/frank3_tilde"),
            (home / "frank3_tilde").resolve(),
        ))
        cases.append((
            "frank3_data_relative",
            dict(decoys, FRANK3_DATA="frank3_rel"),
            (self.cwd / "frank3_rel").resolve(),
        ))
        return cases

    def test_precedence_matches_install_sh(self):
        for name, overrides, documented in self._cases():
            with self.subTest(case=name):
                expected = self._install_sh_expected(overrides)
                actual = self._f3_pfade_actual(overrides)
                self.assertEqual(
                    actual,
                    documented,
                    f"case {name}: f3_pfade={actual} != documented={documented}",
                )
                self.assertEqual(
                    actual,
                    expected,
                    f"case {name}: f3_pfade={actual} != install.sh={expected}",
                )

    def test_every_data_dir_precedence_variable_is_parametrized(self):
        """Guard: all four documented data-dir variables must be covered by cases."""
        covered = {name.split("_wins")[0] for name, _ov, _exp in self._cases()}
        for var in DATA_DIR_PRECEDENCE_VARS:
            self.assertIn(var, covered)


class TestContractEnvPrecedence(unittest.TestCase):
    """The declared environment contract (docs/zero/contract_env.json) must
    agree with the implementations.

    GRF:
      R_t = contract file + source texts
      E_t = process environment
      F   = pure comparison of the *declared* order against the *measured*
            order (install.sh --dry-run, f3_pfade.resolve_data_dir,
            status.HOOK_ENV_WRITE_VARS)

    The old test compared a literal with itself (tautology).  This class
    measures the order from the sources and compares it with the contract.
    """

    INSTALL_SH = PLUGIN_ROOT / "install.sh"

    def setUp(self):
        self.old_env = dict(os.environ)
        self.old_cwd = Path.cwd()
        self.tmpdir = tempfile.TemporaryDirectory(prefix="f3pfade-contract-")
        self.tmp = Path(self.tmpdir.name)
        self.home = self.tmp / "home"
        (self.home / ".local" / "share").mkdir(parents=True)
        self.plugin_root = self.tmp / "plugin"
        (self.plugin_root / ".claude-plugin").mkdir(parents=True)
        (self.plugin_root / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
        self.cwd = self.tmp / "cwd"
        self.cwd.mkdir()
        for var in (
            "FRANK3_DATA",
            "CLAUDE_PLUGIN_DATA",
            "XDG_DATA_HOME",
            "F3_DB_PATH",
            "F3_DRY_RUN",
            "PLUGIN_ROOT",
        ):
            os.environ.pop(var, None)
        os.environ["HOME"] = str(self.home)
        os.environ["PLUGIN_ROOT"] = str(self.plugin_root)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)
        os.chdir(self.old_cwd)
        self.tmpdir.cleanup()

    # ------------------------------------------------------------------
    # measurement helpers
    # ------------------------------------------------------------------
    def _candidate_values(self):
        values = {
            "FRANK3_DATA": self.tmp / "frank3_abs",
            "CLAUDE_PLUGIN_DATA": self.tmp / "claude_abs",
            "XDG_DATA_HOME": self.tmp / "xdg_abs",
            "HOME": self.home,
        }
        expected = {
            "FRANK3_DATA": values["FRANK3_DATA"].resolve(),
            "CLAUDE_PLUGIN_DATA": values["CLAUDE_PLUGIN_DATA"].resolve(),
            "XDG_DATA_HOME": (values["XDG_DATA_HOME"] / "frankenstein3").resolve(),
            "HOME": (self.home / ".local" / "share" / "frankenstein3").resolve(),
        }
        return values, expected

    def _install_sh_data_dir(self, overrides):
        env = os.environ.copy()
        env.update(overrides)
        proc = subprocess.run(
            ["bash", str(self.INSTALL_SH), "--dry-run"],
            env=env,
            cwd=str(self.cwd),
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"install.sh --dry-run failed: {proc.stderr}",
        )
        prefix = "DRY-RUN: Data dir would be: "
        for line in proc.stdout.splitlines():
            if line.startswith(prefix):
                return Path(line[len(prefix):]).resolve()
        self.fail(
            f"install.sh dry-run did not print the data dir. "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )

    def _install_sh_precedence(self):
        """Measure install.sh's data-dir precedence by elimination."""
        values, expected = self._candidate_values()
        remaining = list(DATA_DIR_PRECEDENCE_VARS)
        order = []
        while remaining:
            overrides = {name: str(values[name]) for name in remaining}
            resolved = self._install_sh_data_dir(overrides)
            winner = next((n for n in remaining if resolved == expected[n]), None)
            self.assertIsNotNone(
                winner,
                msg=(
                    f"install.sh resolved {resolved}, which matches none of the "
                    f"documented candidates {expected}"
                ),
            )
            order.append(winner)
            remaining.remove(winner)
        return order

    def _f3_pfade_precedence(self):
        """Measure f3_pfade.resolve_data_dir()'s precedence by elimination."""
        values, expected = self._candidate_values()
        remaining = list(DATA_DIR_PRECEDENCE_VARS)
        order = []
        while remaining:
            for name in remaining:
                os.environ[name] = str(values[name])
            resolved = resolve_data_dir()
            winner = next((n for n in remaining if resolved == expected[n]), None)
            self.assertIsNotNone(
                winner,
                msg=(
                    f"f3_pfade resolved {resolved}, which matches none of the "
                    f"documented candidates {expected}"
                ),
            )
            order.append(winner)
            remaining.remove(winner)
            os.environ.pop(winner, None)
        return order

    def _contract_lists(self, contract):
        flat = _declared_list(contract, FLAT_KEYS)
        data = _declared_list(contract, DATA_KEYS)
        hook = _declared_list(contract, HOOK_KEYS)
        extra = _declared_list(contract, EXTRA_KEYS) or []
        return flat, data, hook, extra

    # ------------------------------------------------------------------
    # tests
    # ------------------------------------------------------------------
    def test_contract_env_precedence_documented(self):
        """The contract file must declare the order the sources actually use."""
        contract = _load_contract()
        flat, data_declared, hook_declared, extra = self._contract_lists(contract)

        self.assertIsNotNone(
            flat,
            msg="contract_env.json must declare a 'precedence' list of variables",
        )
        self.assertEqual(
            len(flat),
            len(set(flat)),
            msg="contract precedence contains duplicate variables",
        )

        # (1) data-dir precedence: contract vs install.sh vs f3_pfade
        install_order = self._install_sh_precedence()
        f3_order = self._f3_pfade_precedence()
        self.assertEqual(
            f3_order,
            install_order,
            msg="f3_pfade and install.sh disagree on the data-dir precedence",
        )
        if data_declared is None:
            data_declared = [v for v in flat if v in DATA_DIR_PRECEDENCE_VARS]
        self.assertEqual(
            data_declared,
            install_order,
            msg=(
                "contract data_dir_precedence does not match the order measured "
                f"from install.sh (contract={data_declared}, install.sh={install_order})"
            ),
        )

        # (2) hook environment write set: contract vs status.py
        hook_source_set = set(status.HOOK_ENV_WRITE_VARS)
        if hook_declared is None:
            hook_declared = [v for v in flat if v in hook_source_set]
        self.assertEqual(
            set(hook_declared),
            hook_source_set,
            msg=(
                "contract hook_env_write_vars do not match status.HOOK_ENV_WRITE_VARS "
                f"(contract={sorted(set(hook_declared))}, status={sorted(hook_source_set)})"
            ),
        )
        self.assertIn(
            "F3_DRY_RUN",
            hook_source_set,
            msg="status._hook_env must write F3_DRY_RUN (dry-run is part of the contract)",
        )

        # (3) every documented contract variable must be declared
        for var in CONTRACT_ENV_PRECEDENCE:
            self.assertIn(
                var,
                flat,
                msg=f"contract precedence does not declare {var}",
            )

        # (4) the flat list must preserve both source-derived orders
        self.assertEqual(
            [v for v in flat if v in set(data_declared)],
            data_declared,
            msg="contract precedence does not preserve the measured data-dir order",
        )
        self.assertEqual(
            [v for v in flat if v in hook_source_set],
            hook_declared,
            msg="contract precedence does not preserve the measured hook-env order",
        )

        # (5) declared plugin sources must exist (a contract may not lie)
        sources = contract.get("sources")
        if isinstance(sources, dict):
            for key, value in sources.items():
                if not isinstance(value, str):
                    continue
                if value.startswith("plugins/frankenstein3/"):
                    self.assertTrue(
                        (REPO_ROOT / value).exists(),
                        msg=f"contract declares a missing plugin source: {value}",
                    )

    def test_contract_env_rust_ts_sources_consistent(self):
        """Rust/TS consumers may only use contract variables, in contract order.

        If ``src/zero/`` or ``agent-sdk/src/zero/`` are absent in this
        checkout, the Rust/TS coverage is honestly UNKNOWN (no skip, no
        fabricated evidence).
        """
        contract = _load_contract()
        flat, data_declared, hook_declared, extra = self._contract_lists(contract)
        declared = (
            set(flat or [])
            | set(data_declared or [])
            | set(hook_declared or [])
            | set(extra or [])
        )

        for directory, suffixes in (
            (RUST_SOURCE_DIR, {".rs"}),
            (TS_SOURCE_DIR, {".ts"}),
        ):
            if not directory.is_dir():
                continue
            for path in sorted(directory.rglob("*")):
                if not path.is_file() or path.suffix not in suffixes:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                found = set(CONTRACT_FAMILY_RE.findall(text))
                if not found:
                    continue
                for var in sorted(found):
                    self.assertIn(
                        var,
                        declared,
                        msg=(
                            f"{path} uses {var}, which is not declared in "
                            f"{CONTRACT_ENV_JSON}"
                        ),
                    )
                data_found = [v for v in (data_declared or []) if v in found]
                if len(data_found) >= 2:
                    positions = [text.find(v) for v in data_found]
                    self.assertEqual(
                        positions,
                        sorted(positions),
                        msg=(
                            f"{path} mentions the data-dir variables in a "
                            f"different order than the contract: {data_found}"
                        ),
                    )


class TestStatusHookEnv(unittest.TestCase):
    """status._hook_env must use only the documented precedence variables."""

    def setUp(self):
        self.old_env = dict(os.environ)
        for var in status.LEGACY_DB_ENV_VARS:
            os.environ.pop(var, None)
        self.tmpdir = tempfile.TemporaryDirectory(prefix="f3pfade-status-")
        self.tmp = Path(self.tmpdir.name)
        self.fixture_dir = self.tmp / "fixture"
        self.fixture_dir.mkdir()
        self.fixture_db = self.fixture_dir / "unified.db"

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)
        self.tmpdir.cleanup()

    def test_hook_env_sets_only_documented_precedence_vars(self):
        env = status._hook_env({"FRANK3_DATA": str(self.fixture_dir)})

        self.assertEqual(env["FRANK3_DATA"], str(self.fixture_dir.resolve()))
        self.assertEqual(env["CLAUDE_PLUGIN_DATA"], str(self.fixture_dir.resolve()))

        # ambient variables are never rewritten by the helper
        self.assertEqual(env.get("XDG_DATA_HOME"), os.environ.get("XDG_DATA_HOME"))
        self.assertEqual(env.get("HOME"), os.environ.get("HOME"))

        # no shotgun guesses for the database location
        for var in status.LEGACY_DB_ENV_VARS:
            self.assertNotIn(var, env)

    def test_hook_env_resolves_fixture_db(self):
        env = status._hook_env({"FRANK3_DATA": str(self.fixture_dir)})

        resolved = status.fixture_db_path(env)
        self.assertEqual(resolved, self.fixture_db.resolve())
        self.assertEqual(
            Path(env["FRANK3_DATA"]) / "unified.db",
            self.fixture_db.resolve(),
        )

    def test_hook_env_follows_documented_precedence(self):
        """CLAUDE_PLUGIN_DATA is used when FRANK3_DATA is absent."""
        claude_dir = self.tmp / "claude_data"
        env = status._hook_env({"CLAUDE_PLUGIN_DATA": str(claude_dir)})
        self.assertEqual(env["FRANK3_DATA"], str(claude_dir.resolve()))
        self.assertEqual(env["CLAUDE_PLUGIN_DATA"], str(claude_dir.resolve()))
        self.assertEqual(
            status.fixture_db_path(env),
            (claude_dir / "unified.db").resolve(),
        )

    def test_hook_env_write_vars_invariant(self):
        """HOOK_ENV_WRITE_VARS must match what _hook_env actually writes."""
        base_env = dict(os.environ)
        for var in ("FRANK3_DATA", "CLAUDE_PLUGIN_DATA", "F3_DB_PATH", "F3_DRY_RUN"):
            base_env.pop(var, None)
        env = status._hook_env({"FRANK3_DATA": str(self.fixture_dir)}, environment=base_env)
        written = set(env.keys()) - set(base_env.keys())
        self.assertEqual(written, set(status.HOOK_ENV_WRITE_VARS))

    def test_env_write_vars_includes_f3_dry_run(self):
        """F3_DRY_RUN must be written into the hook environment.

        The dry-run switch is part of the published contract: a hook that
        cannot see F3_DRY_RUN would write to the real database while the
        caller believes it is in dry-run mode.
        """
        base_env = dict(os.environ)
        for var in ("FRANK3_DATA", "CLAUDE_PLUGIN_DATA", "F3_DB_PATH", "F3_DRY_RUN"):
            base_env.pop(var, None)
        env = status._hook_env({"FRANK3_DATA": str(self.fixture_dir)}, environment=base_env)
        written = set(env.keys()) - set(base_env.keys())

        self.assertIn(
            "F3_DRY_RUN",
            written,
            msg=f"F3_DRY_RUN is not written into the hook env (written={sorted(written)})",
        )
        self.assertIn(
            "F3_DRY_RUN",
            set(status.HOOK_ENV_WRITE_VARS),
            msg="F3_DRY_RUN is missing from status.HOOK_ENV_WRITE_VARS",
        )


class TestF3DbPathContract(unittest.TestCase):
    """F3_DB_PATH is an absolute-path contract: relative values fail closed."""

    def setUp(self):
        self.old_env = dict(os.environ)
        os.environ.pop("F3_DB_PATH", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)

    def test_relative_f3_db_path_raises(self):
        """A relative F3_DB_PATH must raise PfadeError (ON_VIOLATION)."""
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            os.environ["F3_DB_PATH"] = "relative/unified.db"
            with self.assertRaises(PfadeError) as ctx:
                get_db_path(data_dir)
            self.assertIn("F3_DB_PATH", str(ctx.exception))

    def test_absolute_f3_db_path_wins(self):
        """An absolute F3_DB_PATH overrides the derived DATA/unified.db."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture_db = Path(tmp) / "fixture" / "unified.db"
            fixture_db.parent.mkdir(parents=True, exist_ok=True)
            os.environ["F3_DB_PATH"] = str(fixture_db)
            self.assertEqual(
                get_db_path(Path(tmp) / "data"),
                fixture_db.resolve(),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
