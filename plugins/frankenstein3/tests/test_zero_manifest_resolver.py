"""Honesty checks for the bundled FranKenstein 3.0 environment contract.

Two invariants are enforced here (fail closed: missing/unreadable files are
errors, never skips):

1. ``contract_env.json`` must not claim environment writes that no hook
   performs.  The contract may omit ``hook_env_writes`` entirely or list
   exactly the variables the hook configuration really writes.  Both
   directions are checked, so a future implementation must also declare
   itself and a future claim must be backed by code.
2. ``zero-manifest.json``'s static ``resolver`` must point at the
   authoritative resolver ``f3_pfade.py`` located directly in the plugin
   root (never at a stale copy below ``scripts/star``).

Stdlib only.  No network.  No host-specific paths.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterator, Set

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PLUGIN_ROOT / "zero-manifest.json"
CONTRACT_PATH = PLUGIN_ROOT / "docs" / "zero" / "contract_env.json"
HOOKS_PATH = PLUGIN_ROOT / "hooks" / "hooks.json"

RESOLVER_FILENAME = "f3_pfade.py"
STALE_RESOLVER_FRAGMENT = "scripts/star"

# Persistent environment writes performed by a hook command.
_WRITE_PATTERNS = (
    re.compile(r"\bexport\s+([A-Za-z_][A-Za-z0-9_]*)\s*="),
    re.compile(r"\bos\.environ\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\]\s*="),
    re.compile(r"\bsetenv\s+([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(r"\bputenv\s*\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)"),
)

_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _load_json(path: Path) -> Any:
    """Load a required JSON file; fail closed when it is missing/unreadable."""
    if not path.is_file():
        raise AssertionError("required file is missing: %s" % path)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _iter_dicts(node: Any) -> Iterator[Dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            for nested in _iter_dicts(value):
                yield nested
    elif isinstance(node, list):
        for value in node:
            for nested in _iter_dicts(value):
                yield nested


def scan_hook_env_writes(hooks: Any) -> Set[str]:
    """Return the environment variables the hook configuration really writes.

    Counted as writes: shell ``export NAME=``, ``os.environ["NAME"] =``,
    ``setenv NAME`` and ``putenv("NAME", ...)`` inside hook commands, plus
    hook-level ``env`` mappings.  A plain ``NAME=value command`` prefix is
    scoped to that child process only and is therefore not a persistent
    write.
    """
    written: Set[str] = set()
    for node in _iter_dicts(hooks):
        command = node.get("command")
        if isinstance(command, str):
            for pattern in _WRITE_PATTERNS:
                for name in pattern.findall(command):
                    if _ENV_NAME.fullmatch(name):
                        written.add(name)
        env_map = node.get("env")
        if isinstance(env_map, dict):
            for key in env_map:
                if isinstance(key, str) and _ENV_NAME.fullmatch(key):
                    written.add(key)
    return written


class ZeroManifestResolverTest(unittest.TestCase):
    """The static manifest resolver must be the plugin-root f3_pfade.py."""

    def setUp(self) -> None:
        self.manifest = _load_json(MANIFEST_PATH)

    def test_static_resolver_is_plugin_root_f3_pfade(self) -> None:
        resolver = self.manifest["paths"]["resolver"]
        self.assertIsInstance(resolver, str)
        self.assertTrue(
            resolver.endswith(RESOLVER_FILENAME),
            "resolver must end with %s, got %r" % (RESOLVER_FILENAME, resolver),
        )
        self.assertNotIn(
            STALE_RESOLVER_FRAGMENT,
            resolver,
            "resolver must not point at the stale copy %r" % STALE_RESOLVER_FRAGMENT,
        )
        rel = PurePosixPath(resolver)
        self.assertFalse(rel.is_absolute(), "resolver must be plugin-root relative: %r" % resolver)
        self.assertNotIn("..", rel.parts, "resolver must not escape the plugin root: %r" % resolver)
        self.assertEqual(
            rel.parent,
            PurePosixPath("."),
            "resolver must live directly in the plugin root: %r" % resolver,
        )
        self.assertTrue(
            (PLUGIN_ROOT / resolver).is_file(),
            "resolver file does not exist in plugin root: %r" % resolver,
        )

    def test_every_path_resolver_lives_in_plugin_root(self) -> None:
        paths = self.manifest["paths"]
        self.assertIsInstance(paths, dict)
        for key, spec in paths.items():
            if not isinstance(spec, dict):
                continue
            resolver = spec.get("resolver")
            if not isinstance(resolver, str):
                continue
            file_part = resolver.split("::", 1)[0]
            rel = PurePosixPath(file_part)
            self.assertFalse(rel.is_absolute(), "%s: resolver must be relative: %r" % (key, resolver))
            self.assertNotIn("..", rel.parts, "%s: resolver must not escape plugin root: %r" % (key, resolver))
            self.assertEqual(
                rel.parent,
                PurePosixPath("."),
                "%s: resolver must live directly in the plugin root: %r" % (key, resolver),
            )
            self.assertNotIn(
                STALE_RESOLVER_FRAGMENT,
                file_part,
                "%s: resolver must not point at the stale copy: %r" % (key, resolver),
            )
            self.assertTrue(
                (PLUGIN_ROOT / file_part).is_file(),
                "%s: resolver file does not exist in plugin root: %r" % (key, resolver),
            )

    def test_declared_contract_file_exists(self) -> None:
        contract_rel = self.manifest["paths"]["contract"]
        self.assertIsInstance(contract_rel, str)
        self.assertTrue(
            (PLUGIN_ROOT / contract_rel).is_file(),
            "declared contract file does not exist: %r" % contract_rel,
        )


class ContractEnvHonestyTest(unittest.TestCase):
    """The contract must not claim hook env writes that no hook performs."""

    def test_hook_env_writes_match_hook_implementation(self) -> None:
        contract = _load_json(CONTRACT_PATH)
        declared_raw = contract.get("hook_env_writes", [])
        self.assertIsInstance(
            declared_raw,
            list,
            "hook_env_writes must be a list when present, got %r" % type(declared_raw).__name__,
        )
        declared = {name for name in declared_raw if isinstance(name, str)}
        implemented = scan_hook_env_writes(_load_json(HOOKS_PATH))
        self.assertEqual(
            declared - implemented,
            set(),
            "contract claims hook env writes that no hook performs: %r" % sorted(declared - implemented),
        )
        self.assertEqual(
            implemented - declared,
            set(),
            "hooks write env vars that the contract does not declare: %r" % sorted(implemented - declared),
        )

    def test_contract_resolver_is_plugin_root_f3_pfade(self) -> None:
        contract = _load_json(CONTRACT_PATH)
        resolver = contract["resolver"]
        self.assertIsInstance(resolver, str)
        self.assertTrue(
            resolver.endswith(RESOLVER_FILENAME),
            "contract resolver must end with %s, got %r" % (RESOLVER_FILENAME, resolver),
        )
        rel = PurePosixPath(resolver)
        self.assertEqual(
            rel.parent,
            PurePosixPath("."),
            "contract resolver must live directly in the plugin root: %r" % resolver,
        )
        self.assertTrue(
            (PLUGIN_ROOT / resolver).is_file(),
            "contract resolver file does not exist in plugin root: %r" % resolver,
        )


if __name__ == "__main__":
    unittest.main()
