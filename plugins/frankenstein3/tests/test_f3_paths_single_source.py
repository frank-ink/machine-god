"""Fail-closed invariant tests for the FranKenstein 3 path resolver.

MEASURED here (filesystem + import machinery only):
  * the WHOLE plugin tree is scanned for files named ``f3_paths.py`` --
    no subtree is excluded any more (``scripts/``, ``star/`` and every
    other directory are included);
  * exactly one copy exists and it is the authoritative file at the
    plugin root ``plugins/frankenstein3/f3_paths.py``;
  * every other copy (inside the plugin tree or at the repository root)
    is reported as a violation;
  * with the scripts directory first on ``sys.path``, ``f3_paths`` still
    resolves to the authoritative file (no shadowing);
  * the resolver (at the plugin root) targets the plugin root;
  * every script under ``plugins/frankenstein3/scripts/`` is syntactically
    valid.

UNKNOWN (deliberately not asserted here): runtime behaviour of the
individual scripts.

Known limit: symlinked directories are not traversed (``followlinks=False``),
so a copy hidden behind a symlinked directory is UNKNOWN, not MEASURED.
"""

from __future__ import annotations

import ast
import importlib.machinery
import importlib.util
import os
from pathlib import Path
from typing import NamedTuple

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
STAR_DIR = PLUGIN_ROOT / "star"
REPO_ROOT = PLUGIN_ROOT.parents[1]

COPY_NAME = "f3_paths.py"
AUTHORITATIVE = PLUGIN_ROOT / COPY_NAME


class ResolverCopy(NamedTuple):
    """Compound record for one on-disk occurrence of ``f3_paths.py``."""

    declared: Path
    resolved: Path
    location: str


def _resolved(path: Path) -> Path:
    return path.resolve()


def _is_copy(path: Path) -> bool:
    """True for regular files and for (possibly broken) symlinks."""
    return path.is_file() or path.is_symlink()


def _raise_walk_error(error: OSError) -> None:
    """Fail closed: an unreadable subtree must not silently look empty."""
    raise error


def _location(declared: Path) -> str:
    if declared.parent == PLUGIN_ROOT:
        return "plugin_root"
    if declared == REPO_ROOT / COPY_NAME:
        return "repo_root"
    return "plugin_tree"


def _plugin_tree_copies() -> list[ResolverCopy]:
    """Every ``f3_paths.py`` inside the plugin tree -- NO subtree excluded."""
    if not PLUGIN_ROOT.is_dir():
        return []
    copies: list[ResolverCopy] = []
    for dirpath, dirnames, filenames in os.walk(
        PLUGIN_ROOT, followlinks=False, onerror=_raise_walk_error
    ):
        dirnames.sort()
        for name in sorted(filenames):
            if name != COPY_NAME:
                continue
            declared = Path(dirpath) / name
            if not _is_copy(declared):
                continue
            copies.append(
                ResolverCopy(
                    declared=declared,
                    resolved=_resolved(declared),
                    location=_location(declared),
                )
            )
    return sorted(copies, key=lambda copy: str(copy.declared))


def _repo_root_copies() -> list[ResolverCopy]:
    """A copy at the repository root is outside the plugin root -> violation."""
    candidate = REPO_ROOT / COPY_NAME
    if not _is_copy(candidate):
        return []
    return [
        ResolverCopy(
            declared=candidate,
            resolved=_resolved(candidate),
            location="repo_root",
        )
    ]


def _all_copies() -> list[ResolverCopy]:
    """All copies in the whole plugin tree plus the repository root."""
    return sorted(
        _plugin_tree_copies() + _repo_root_copies(),
        key=lambda copy: str(copy.declared),
    )


def _violations(copies: list[ResolverCopy]) -> list[ResolverCopy]:
    """Copies that are not the authoritative plugin-root file."""
    return [copy for copy in copies if copy.declared != AUTHORITATIVE]


def _load_from(spec) -> object:
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_authoritative_resolver_exists_at_plugin_root() -> None:
    assert AUTHORITATIVE.is_file(), (
        f"authoritative f3_paths.py missing at plugin root: {AUTHORITATIVE}"
    )
    assert not AUTHORITATIVE.is_symlink(), (
        "authoritative f3_paths.py must be a regular file, not a symlink: "
        f"{AUTHORITATIVE}"
    )


def test_no_duplicate_copies_anywhere() -> None:
    violations = _violations(_all_copies())
    assert not violations, (
        "duplicate f3_paths.py copies outside the plugin root: "
        + ", ".join(f"{copy.location}:{copy.declared}" for copy in violations)
    )


def test_exactly_one_authoritative_resolver() -> None:
    copies = _all_copies()
    assert len(copies) == 1, (
        "expected exactly one f3_paths.py in the plugin tree, found "
        f"{len(copies)}: {[str(copy.declared) for copy in copies]}"
    )
    assert copies[0].declared == AUTHORITATIVE, (
        "the single f3_paths.py must live at the plugin root, found: "
        f"{copies[0].declared}"
    )


def test_star_subtree_has_no_resolver_copy() -> None:
    if not STAR_DIR.is_dir():
        return
    copies = [
        copy
        for copy in _plugin_tree_copies()
        if copy.declared.parent == STAR_DIR or STAR_DIR in copy.declared.parents
    ]
    assert not copies, (
        "duplicate f3_paths.py copy in star/: "
        + ", ".join(str(copy.declared) for copy in copies)
    )


def test_duplicate_stub_is_absent() -> None:
    stub = SCRIPTS_DIR / COPY_NAME
    assert not _is_copy(stub), f"duplicate resolver stub still present: {stub}"


def test_scripts_dir_does_not_shadow_authoritative_resolver() -> None:
    assert AUTHORITATIVE.is_file(), (
        f"authoritative f3_paths.py missing at plugin root: {AUTHORITATIVE}"
    )
    search_path = [str(SCRIPTS_DIR), str(PLUGIN_ROOT), str(REPO_ROOT)]
    spec = importlib.machinery.PathFinder.find_spec("f3_paths", search_path)
    assert spec is not None, "f3_paths is not importable from the plugin tree"
    assert spec.origin is not None, "f3_paths has no file origin"
    origin = _resolved(Path(spec.origin))
    assert origin == _resolved(AUTHORITATIVE), (
        f"f3_paths resolves to unexpected file: {origin}"
    )


def test_resolver_targets_plugin_root() -> None:
    spec = importlib.machinery.PathFinder.find_spec("f3_paths", [str(PLUGIN_ROOT)])
    assert spec is not None and spec.origin is not None, (
        "f3_paths is not importable from the plugin root"
    )
    module = _load_from(spec)
    if hasattr(module, "resolve_plugin_root"):
        assert module.resolve_plugin_root() == PLUGIN_ROOT
    if hasattr(module, "resolve_db_path"):
        assert module.resolve_db_path() == PLUGIN_ROOT / "unified.db"


def test_all_scripts_are_syntactically_valid() -> None:
    if not SCRIPTS_DIR.is_dir():
        return
    for path in sorted(SCRIPTS_DIR.rglob("*.py")):
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        ast.parse(source, filename=str(path))
