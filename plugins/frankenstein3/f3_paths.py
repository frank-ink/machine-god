"""Path resolution for Frankenstein 3 - portable across all languages.

All paths are derived exclusively from environment variables and the filesystem.
There are no hardcoded user directories and no machine names; the resolution
remains copyable to another machine.

This top-level file is the authoritative resolver. The read-only script
scripts/star/f3_paths.py is no longer cited as the source of precedence;
contract_env.json references this file.

Environment variables (resolution, no hardcoding):
  - FRANK3_DATA        : explicit Data-Root override (highest priority)
  - FRANKENSTEIN3_ROOT : Data-Root / Plugin-Root override
  - CLAUDE_PLUGIN_DATA : alternative Data-Root
  - XDG_DATA_HOME      : XDG Base Directory
  - HOME / USERPROFILE : home directory fallbacks
  - F3_DB_PATH         : direct path to unified.db (file or directory)
  - F3_DRY_RUN         : dry-run, then only F3_DB_PATH authoritative

Precedence (Data-Root, without unified.db):
  1. FRANK3_DATA
  2. FRANKENSTEIN3_ROOT
  3. Derivation from F3_DB_PATH (Data-Root: parent directory for file,
     directory itself for directory)
  4. CLAUDE_PLUGIN_DATA
  5. XDG_DATA_HOME/frankenstein3
  6. ~/.local/share/frankenstein3              (HOME)
  7. %USERPROFILE%/AppData/Local/frankenstein3

Precedence (DB path):
  1. FRANK3_DATA/unified.db
  2. FRANKENSTEIN3_ROOT/unified.db
  3. F3_DB_PATH (file or directory, see _infer_kind)
  4. CLAUDE_PLUGIN_DATA/unified.db
  5. XDG_DATA_HOME/frankenstein3/unified.db
  6. ~/.local/share/frankenstein3/unified.db
  7. %USERPROFILE%/AppData/Local/frankenstein3/unified.db

Dry-Run (F3_DRY_RUN truthy: 1|true|yes|on, case-insensitive):
  - F3_DB_PATH is required (no fallback).
  - All other path variables are ignored.
  - The DB path resolver returns F3_DB_PATH (tilde-expanded) directly.
  - The Data-Root resolver returns the parent directory if
    F3_DB_PATH is a file, and the directory itself if F3_DB_PATH
    is a directory.
  - No write accesses: ensure_db() creates nothing in dry-run (no mkdir,
    no DB initialization, no fixture creation, no self-check,
    no registration).
  - Invalid F3_DRY_RUN values raise PathsError (fail-closed).
  - Whitespace-only input is rejected (fail-closed), not mapped to '0'.

Bundle layout (relative, host-independent):
  - resolve_plugin_root() returns the directory of this file.
  - resolve_bundle_path(...) joins relative bundle components.
  - resolve_manifest_paths() returns env-derived manifest paths; the
    'resolver' entry points to this top-level file.

Paths are tilde-expanded (HOME, otherwise USERPROFILE), but not resolved
(no symlink resolution): configuration and result remain identical and
predictable.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
from enum import Enum
from pathlib import Path, PureWindowsPath
from typing import Iterator, Mapping, Optional


class PathsError(RuntimeError):
    """Error in path resolution (fail-closed, no silent fallback)."""


class PathKind(str, Enum):
    """Tagged union: is the path a file or a directory?"""

    FILE = "file"
    DIRECTORY = "directory"


_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off"})
DB_FILE_SUFFIXES = (".db", ".sqlite", ".sqlite3", ".db3")
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _normalize_dry_run(raw: Optional[str]) -> str:
    """Normalizes F3_DRY_RUN to '1' (active) or '0' (inactive).

    Contract rule (contract_env.json -> dry_run):
      - unset/empty          -> '0' (inactive)
      - truthy (1|true|yes|on, case-insensitive) -> '1' (active)
      - falsy (0|false|no|off, case-insensitive) -> '0' (inactive)
      - whitespace-only      -> PathsError (fail-closed: no default)
      - any other value      -> PathsError (fail-closed: no default, no silent fallback)
    """
    if raw is None or raw == "":
        return "0"
    stripped = raw.strip()
    if stripped == "":
        raise PathsError(
            "Invalid F3_DRY_RUN value: whitespace-only. Allowed: truthy=%s, falsy=%s"
            % (sorted(_TRUTHY), sorted(_FALSY))
        )
    lower = stripped.lower()
    if lower in _TRUTHY:
        return "1"
    if lower in _FALSY:
        return "0"
    raise PathsError(
        "Invalid F3_DRY_RUN value: '%s'. Allowed: truthy=%s, falsy=%s"
        % (raw, sorted(_TRUTHY), sorted(_FALSY))
    )


def _looks_windows(raw: str) -> bool:
    """Heuristic: does the path look like a Windows path?

    Allows portable handling of %USERPROFILE% styles on POSIX and
    vice versa, without hardcoding machine-specific paths.
    """
    if not raw:
        return False
    if _WINDOWS_DRIVE_RE.match(raw):
        return True
    return "\\" in raw


def _home() -> Optional[str]:
    """HOME first, then USERPROFILE.

Deliberately no pwd/os.path.expanduser lookup: this keeps resolution
deterministic and machine-independent.
"""
    for name in ("HOME", "USERPROFILE"):
        value = os.environ.get(name)
        if value:
            return value
    return None


def _expand(raw: str, home: Optional[str]) -> str:
    """Expands '~' and '~/...' against the given home directory."""
    if raw == "~":
        if not home:
            raise PathsError("HOME not set, cannot expand '~'")
        return home
    if raw.startswith("~/") or raw.startswith("~\\"):
        if not home:
            raise PathsError("HOME not set, cannot expand '~/' path: %s" % raw)
        if _looks_windows(home):
            rest = raw[2:].replace("/", "\\")
            return str(PureWindowsPath(home).joinpath(rest))
        return home + raw[1:]
    return raw


def _expand_env(raw: str) -> str:
    """Tilde expansion with current HOME/USERPROFILE."""
    return _expand(raw, _home())


def _join(base: str, *parts: str) -> Path:
    """Connects components portably (Windows-style remains Windows-style)."""
    if _looks_windows(base):
        return Path(str(PureWindowsPath(base).joinpath(*parts)))
    return Path(base).joinpath(*parts)


def resolve_plugin_root() -> Path:
    """Bundle layout: plugin root = directory of this file.

    Relative to bundle, never to a fixed user path.
    """
    return Path(__file__).resolve().parent


def resolve_bundle_path(*parts: str) -> Path:
    """Relative bundle path (script, contract, schema) below the plugin root."""
    return resolve_plugin_root().joinpath(*parts)


def _exists(path: Path) -> bool:
    """Existence check that doesn't hard-fail on exotic paths."""
    try:
        return path.exists()
    except (OSError, ValueError):
        return False


def _is_dry_run() -> bool:
    """Checks if dry-run mode is active (normalized value '1').

    Raises:
        PathsError: If F3_DRY_RUN has an invalid value (fail-closed).
    """
    return _normalize_dry_run(os.environ.get("F3_DRY_RUN")) == "1"


def _infer_kind(path: Path) -> PathKind:
    """Infers file vs. directory (sole source for this decision).

    Evidence order:
      1. Filesystem (exists + is_file/is_dir)
      2. Suffix: DB_FILE_SUFFIXES -> FILE, else DIRECTORY
    """
    if _exists(path):
        try:
            if path.is_file():
                return PathKind.FILE
        except (OSError, ValueError):
            pass
        return PathKind.DIRECTORY
    if path.suffix.lower() in DB_FILE_SUFFIXES:
        return PathKind.FILE
    return PathKind.DIRECTORY


def _data_root(path: Path) -> Path:
    """Data-root for a path: parent directory if file, directory itself if dir."""
    if _infer_kind(path) is PathKind.FILE:
        return path.parent
    return path


def _dry_run_db_path() -> Path:
    """F3_DB_PATH in dry-run (mandatory, tilde-expanded, otherwise unchanged)."""
    raw = os.environ.get("F3_DB_PATH")
    if not raw or not raw.strip():
        raise PathsError(
            "F3_DRY_RUN=1 requires F3_DB_PATH (no fallback to other path variables)"
        )
    return Path(_expand_env(raw))


def _dry_run_data_dir() -> Path:
    """Data root in dry-run: parent directory (file) or directory itself (dir)."""
    return _data_root(_dry_run_db_path())


def _resolve_data_dir() -> Path:
    """
    Resolves the data directory (without unified.db).

    Precedence:
    1. FRANK3_DATA (highest priority, explicit user override)
    2. FRANKENSTEIN3_ROOT (Plugin-/Data-Root override)
    3. Derivation from F3_DB_PATH (same source as DB path)
    4. CLAUDE_PLUGIN_DATA
    5. XDG_DATA_HOME/frankenstein3
    6. ~/.local/share/frankenstein3 (HOME)
    7. %USERPROFILE%/AppData/Local/frankenstein3
    """
    if _is_dry_run():
        return _dry_run_data_dir()

    # 1. FRANK3_DATA (highest priority, explicit user override)
    frank3_data = os.environ.get("FRANK3_DATA")
    if frank3_data:
        return Path(_expand_env(frank3_data))

    # 2. FRANKENSTEIN3_ROOT (Plugin-/Data-Root-Override)
    frank3_root = os.environ.get("FRANKENSTEIN3_ROOT")
    if frank3_root:
        return Path(_expand_env(frank3_root))

    # 3. Derivation from F3_DB_PATH (same source as the DB path)
    f3_db_path = os.environ.get("F3_DB_PATH")
    if f3_db_path:
        return _data_root(Path(_expand_env(f3_db_path)))

    # 4. CLAUDE_PLUGIN_DATA
    claude_plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if claude_plugin_data:
        return Path(_expand_env(claude_plugin_data))

    # 5. XDG_DATA_HOME
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return _join(_expand_env(xdg_data_home), "frankenstein3")

    # 6. HOME fallback (XDG-Default)
    home = os.environ.get("HOME")
    if home:
        return _join(_expand_env(home), ".local", "share", "frankenstein3")

    # 7. Windows USERPROFILE fallback
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        return _join(_expand_env(userprofile), "AppData", "Local", "frankenstein3")

    raise PathsError(
        "Cannot resolve data dir: no FRANK3_DATA, FRANKENSTEIN3_ROOT, F3_DB_PATH, "
        "CLAUDE_PLUGIN_DATA, XDG_DATA_HOME, HOME, or USERPROFILE set"
    )


def resolve_db_path() -> Path:
    """Resolves the full path to unified.db."""
    if _is_dry_run():
        return _dry_run_db_path()

    # 1. FRANK3_DATA (highest priority, explicit user override)
    frank3_data = os.environ.get("FRANK3_DATA")
    if frank3_data:
        return _join(_expand_env(frank3_data), "unified.db")

    # 2. FRANKENSTEIN3_ROOT (Plugin-/Data-Root-Override)
    frank3_root = os.environ.get("FRANKENSTEIN3_ROOT")
    if frank3_root:
        return _join(_expand_env(frank3_root), "unified.db")

    # 3. F3_DB_PATH (file or directory, same inference as for data root)
    f3_db_path = os.environ.get("F3_DB_PATH")
    if f3_db_path:
        p = Path(_expand_env(f3_db_path))
        if _infer_kind(p) is PathKind.FILE:
            return p
        return _join(str(p), "unified.db")

    # 4. CLAUDE_PLUGIN_DATA
    claude_plugin_data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if claude_plugin_data:
        return _join(_expand_env(claude_plugin_data), "unified.db")

    # 5. XDG_DATA_HOME
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return _join(_expand_env(xdg_data_home), "frankenstein3", "unified.db")

    # 6. HOME fallback (XDG-Default)
    home = os.environ.get("HOME")
    if home:
        return _join(
            _expand_env(home), ".local", "share", "frankenstein3", "unified.db"
        )

    # 7. Windows USERPROFILE fallback
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        return _join(
            _expand_env(userprofile),
            "AppData",
            "Local",
            "frankenstein3",
            "unified.db",
        )

    raise PathsError(
        "Cannot resolve db path: no FRANK3_DATA, FRANKENSTEIN3_ROOT, F3_DB_PATH, "
        "CLAUDE_PLUGIN_DATA, XDG_DATA_HOME, HOME, or USERPROFILE set"
    )


def resolve_data_dir() -> Path:
    """Public access to the data root (without unified.db)."""
    return _resolve_data_dir()


def resolve_manifest_paths() -> dict[str, str]:
    """Env-derived manifest paths (no hard-wired paths).

    Keys correspond to the path block in zero-manifest.json:
      plugin_root, data_dir, db_path, resolver, contract

    'resolver' points to the authoritative top-level file (f3_paths.py);
    scripts/star/f3_paths.py is read-only and not a source of precedence.
    """
    return {
        "plugin_root": str(resolve_plugin_root()),
        "data_dir": str(resolve_data_dir()),
        "db_path": str(resolve_db_path()),
        "resolver": str(resolve_bundle_path("f3_paths.py")),
        "contract": str(resolve_bundle_path("docs", "zero", "contract_env.json")),
    }


# Compatibility aliases: identical function object (no wrapper, no second path).
get_db_path = resolve_db_path
get_data_root = resolve_data_dir


def ensure_db() -> Path:
    """Creates the parent directory of the DB path and returns the DB path.

    In dry-run, nothing is written (dry-run = no side effects):
    no mkdir, no DB initialization, no fixture creation, no
    self-check, no registration. The SQLite file itself is not
    created here; the schema is handled by the DB layer.
    """
    db_path = resolve_db_path()
    if _is_dry_run():
        return db_path
    parent = db_path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PathsError(
            "Cannot create parent directory for DB path %s: %s" % (parent, exc)
        ) from exc
    return db_path


# --- Test helper functions: explicit environment, replayable ---


@contextlib.contextmanager
def _env_scope(env: Mapping[str, Optional[str]]) -> Iterator[None]:
    """Sets os.environ exclusively to `env` and restores the state afterwards."""
    old_env = dict(os.environ)
    try:
        os.environ.clear()
        for key, value in env.items():
            if value is None:
                continue
            os.environ[str(key)] = str(value)
        yield
    finally:
        os.environ.clear()
        os.environ.update(old_env)


def resolve_db_path_with_env(env: dict[str, str]) -> Path:
    """Test helper: resolves the DB path with a given environment."""
    with _env_scope(env):
        return resolve_db_path()


def resolve_data_dir_with_env(env: dict[str, str]) -> Path:
    """Test helper: resolves the data root with a given environment."""
    with _env_scope(env):
        return resolve_data_dir()


def ensure_db_with_env(env: Optional[dict[str, str]] = None) -> Path:
    """Test/contract helper function: ensure_db with explicit environment.

    env None  -> the current os.environ is used unchanged.
    env set -> the environment is set exclusively for resolution
    (replayable) and fully restored afterwards.

    Dry-Run (F3_DRY_RUN truthy: 1|true|yes|on):
      - F3_DB_PATH is required; without F3_DB_PATH -> PathsError (no fallback).
      - All other path variables are ignored.
      - Return value is F3_DB_PATH (tilde-expanded) as Path.
      - Zero filesystem write accesses: no mkdir, no DB init, no
        fixture creation, no self-check, no registration.
    """
    if env is None:
        return ensure_db()
    with _env_scope(env):
        return ensure_db()


def main() -> int:
    """CLI: outputs the resolved paths as JSON (read-only)."""
    try:
        paths = resolve_manifest_paths()
    except PathsError as exc:
        print("f3_paths: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps(paths, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ClayCode block for GRF/Omega integration
"""
module f3_paths {
  architecture PathResolver {
    stateAuthority: resolve_db_path, resolve_data_dir, ensure_db
    path env -> _normalize_dry_run -> _is_dry_run -> resolve_db_path
    path env -> _normalize_dry_run -> _is_dry_run -> resolve_data_dir
    invariant dry_run_fail_closed: F3_DRY_RUN in _TRUTHY union _FALSY union {unset, empty} else PathsError
    invariant dry_run_requires_f3_db_path: _is_dry_run() -> F3_DB_PATH != empty else PathsError
    invariant dry_run_isolated: _is_dry_run() -> ignores(FRANK3_DATA, FRANKENSTEIN3_ROOT, CLAUDE_PLUGIN_DATA, XDG_DATA_HOME, HOME, USERPROFILE)
    invariant ensure_db_no_write_in_dry_run: _is_dry_run() -> ensure_db() performs zero fs writes
    invariant whitespace_rejected: raw.strip() == "" -> PathsError (never maps to '0')
  }
  invariant dry_run_normalization: _normalize_dry_run(raw) in {"1", "0"} else PathsError
  fn _normalize_dry_run(raw: Optional[str]) -> str { ... }
  fn _is_dry_run() -> bool { ... }
  hypothesis H_DRY_RUN_MATRIX: 9 cases (unset, "", "1", "true", "0", "false", "maybe", "999", "  ") map to expected normalized values or PathsError
  promotion MEASURE -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME -> CAUSAL_CREDIT -> BOUNDED_ADMISSION -> REENTRY_TEST -> CONTROL_INFLUENCE
}
"""
