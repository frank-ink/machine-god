#!/usr/bin/env python3
"""Behavioural tests for f3_pfade.py path resolution (full env matrix).

GRF/ClayCode:
  R_t = (filesystem state under tmp_path, explicit env mapping)
  E_t = env mapping (F3_DRY_RUN / F3_DB_PATH / FRANK3_DATA / FRANKENSTEIN3_ROOT /
        CLAUDE_PLUGIN_DATA / XDG_DATA_HOME / HOME / USERPROFILE)
  F   = f3_pfade.resolve_*_with_env(env) -- pure, replayable
  M   = {dry_run, existing_file, existing_directory, missing_db_suffix,
        missing_other_suffix, home_unset, userprofile_fallback}
  L   = c * h -- c = branch identity, h = exact-path equality (no partial credit)

Every branch test uses a tmp_path fixture: the filesystem state is the
evidence, the env mapping is the input, the resolved path is the observation.
"""

import contextlib
import inspect
import os
import sys
import tempfile
from pathlib import Path, PureWindowsPath

FRANK3_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(FRANK3_ROOT))

import f3_pfade  # noqa: E402


# --- helpers ---------------------------------------------------------------


def _norm(path) -> str:
    """Normalisiert einen Pfad ohne Symlink-Auflösung (deterministisch)."""
    return os.path.normpath(str(path))


def _same(actual, expected) -> bool:
    return _norm(actual) == _norm(expected)


def _expect_error(fn, *args, **kwargs):
    """Fail-closed-Helper: erwartet PfadeError (kein pytest nötig)."""
    try:
        fn(*args, **kwargs)
    except f3_pfade.PfadeError:
        return
    raise AssertionError("expected PfadeError from %r" % (fn,))


@contextlib.contextmanager
def _env_scope(env):
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


# --- basic precedence ------------------------------------------------------


def test_frank3_data_only():
    env = {"FRANK3_DATA": "/custom/frank3/data"}
    path = f3_pfade.resolve_db_path_with_env(env)
    assert _same(path, Path("/custom/frank3/data/unified.db")), f"Got {path}"


def test_frank3_root_only():
    env = {"FRANKENSTEIN3_ROOT": "/root/env"}
    path = f3_pfade.resolve_db_path_with_env(env)
    assert _same(path, Path("/root/env/unified.db")), f"Got {path}"


def test_f3_db_path_as_directory():
    env = {"F3_DB_PATH": "/custom/f3/db/dir"}
    path = f3_pfade.resolve_db_path_with_env(env)
    assert _same(path, Path("/custom/f3/db/dir/unified.db")), f"Got {path}"


def test_f3_db_path_as_file():
    env = {"F3_DB_PATH": "/custom/f3/db.sqlite"}
    path = f3_pfade.resolve_db_path_with_env(env)
    assert _same(path, Path("/custom/f3/db.sqlite")), f"Got {path}"


def test_claude_plugin_data_only():
    env = {"CLAUDE_PLUGIN_DATA": "/plugin/data"}
    path = f3_pfade.resolve_db_path_with_env(env)
    assert _same(path, Path("/plugin/data/unified.db")), f"Got {path}"


def test_xdg_data_home_only():
    env = {"XDG_DATA_HOME": "/xdg/data"}
    path = f3_pfade.resolve_db_path_with_env(env)
    assert _same(path, Path("/xdg/data/frankenstein3/unified.db")), f"Got {path}"


def test_home_only(tmp_path):
    """HOME fallback resolves under a tmp_path-derived home, never a fixed one."""
    home = tmp_path / "home"
    env = {"HOME": str(home)}
    path = f3_pfade.resolve_db_path_with_env(env)
    expected = home / ".local" / "share" / "frankenstein3" / "unified.db"
    assert _same(path, expected), f"Got {path}"


def test_frank3_data_wins_over_frank3_root():
    env = {"FRANK3_DATA": "/frank3/wins", "FRANKENSTEIN3_ROOT": "/root/loses"}
    path = f3_pfade.resolve_db_path_with_env(env)
    assert _same(path, Path("/frank3/wins/unified.db")), f"Got {path}"


def test_frank3_root_wins_over_f3_db_path():
    env = {"FRANKENSTEIN3_ROOT": "/root/wins", "F3_DB_PATH": "/f3/loses"}
    path = f3_pfade.resolve_db_path_with_env(env)
    assert _same(path, Path("/root/wins/unified.db")), f"Got {path}"


def test_f3_db_path_wins_over_claude_plugin_data():
    env = {"F3_DB_PATH": "/f3/wins", "CLAUDE_PLUGIN_DATA": "/plugin/loses"}
    path = f3_pfade.resolve_db_path_with_env(env)
    assert _same(path, Path("/f3/wins/unified.db")), f"Got {path}"


def test_claude_plugin_data_wins_over_xdg():
    env = {"CLAUDE_PLUGIN_DATA": "/plugin/wins", "XDG_DATA_HOME": "/xdg/loses"}
    path = f3_pfade.resolve_db_path_with_env(env)
    assert _same(path, Path("/plugin/wins/unified.db")), f"Got {path}"


def test_f3_db_path_wins_over_xdg():
    env = {"F3_DB_PATH": "/f3/wins", "XDG_DATA_HOME": "/xdg/loses"}
    path = f3_pfade.resolve_db_path_with_env(env)
    assert _same(path, Path("/f3/wins/unified.db")), f"Got {path}"


def test_userprofile_fallback(tmp_path):
    """USERPROFILE fallback resolves under a tmp_path-derived Windows-style home."""
    win_home = PureWindowsPath("C:\\Users") / tmp_path.name
    env = {"USERPROFILE": str(win_home)}
    path = f3_pfade.resolve_db_path_with_env(env)
    expected = Path(str(win_home / "AppData" / "Local" / "frankenstein3" / "unified.db"))
    assert _same(path, expected), f"Got {path}"


def test_userprofile_fallback_posix_style(tmp_path):
    """USERPROFILE fallback also works for a POSIX-shaped profile directory."""
    win_home = tmp_path / "profile"
    env = {"USERPROFILE": str(win_home)}
    path = f3_pfade.resolve_db_path_with_env(env)
    expected = win_home / "AppData" / "Local" / "frankenstein3" / "unified.db"
    assert _same(path, expected), f"Got {path}"
    data_dir = f3_pfade.resolve_data_dir_with_env(env)
    assert _same(data_dir, win_home / "AppData" / "Local" / "frankenstein3")


def test_home_unset_uses_userprofile(tmp_path):
    """HOME unset -> USERPROFILE is the fallback (no silent default)."""
    profile = tmp_path / "profile"
    env = {"USERPROFILE": str(profile)}
    path = f3_pfade.resolve_db_path_with_env(env)
    expected = profile / "AppData" / "Local" / "frankenstein3" / "unified.db"
    assert _same(path, expected), f"Got {path}"


def test_no_home_no_userprofile_fails_closed():
    _expect_error(f3_pfade.resolve_db_path_with_env, {})
    _expect_error(f3_pfade.resolve_data_dir_with_env, {})


# --- tilde expansion -------------------------------------------------------


def test_tilde_expansion_frank3_data(tmp_path):
    home = tmp_path / "home"
    env = {"HOME": str(home), "FRANK3_DATA": "~/data"}
    path = f3_pfade.resolve_db_path_with_env(env)
    assert _same(path, home / "data" / "unified.db"), f"Got {path}"
    data_dir = f3_pfade.resolve_data_dir_with_env(env)
    assert _same(data_dir, home / "data"), f"Got {data_dir}"


def test_tilde_expansion_frank3_root(tmp_path):
    home = tmp_path / "home"
    env = {"HOME": str(home), "FRANKENSTEIN3_ROOT": "~/root"}
    path = f3_pfade.resolve_db_path_with_env(env)
    assert _same(path, home / "root" / "unified.db"), f"Got {path}"
    data_dir = f3_pfade.resolve_data_dir_with_env(env)
    assert _same(data_dir, home / "root"), f"Got {data_dir}"


def test_tilde_expansion_f3_db_path(tmp_path):
    home = tmp_path / "home"
    env = {"HOME": str(home), "F3_DB_PATH": "~/custom.db"}
    path = f3_pfade.resolve_db_path_with_env(env)
    assert _same(path, home / "custom.db"), f"Got {path}"


def test_tilde_expansion_claude_plugin_data(tmp_path):
    home = tmp_path / "home"
    env = {"HOME": str(home), "CLAUDE_PLUGIN_DATA": "~/plugin"}
    path = f3_pfade.resolve_db_path_with_env(env)
    assert _same(path, home / "plugin" / "unified.db"), f"Got {path}"


def test_tilde_expansion_xdg_data_home(tmp_path):
    home = tmp_path / "home"
    env = {"HOME": str(home), "XDG_DATA_HOME": "~/xdg"}
    path = f3_pfade.resolve_db_path_with_env(env)
    expected = home / "xdg" / "frankenstein3" / "unified.db"
    assert _same(path, expected), f"Got {path}"


def test_tilde_expansion_dry_run(tmp_path):
    home = tmp_path / "home"
    env = {"HOME": str(home), "F3_DRY_RUN": "1", "F3_DB_PATH": "~/dry.db"}
    path = f3_pfade.resolve_db_path_with_env(env)
    assert _same(path, home / "dry.db"), f"Got {path}"
    data_dir = f3_pfade.resolve_data_dir_with_env(env)
    assert _same(data_dir, home), f"Got {data_dir}"


def test_tilde_expansion_requires_home():
    """'~' without HOME and USERPROFILE fails closed."""
    _expect_error(f3_pfade.resolve_db_path_with_env, {"F3_DB_PATH": "~/custom.db"})


# --- dry-run matrix --------------------------------------------------------


def test_dry_run_requires_db_path():
    _expect_error(f3_pfade.resolve_db_path_with_env, {"F3_DRY_RUN": "1"})
    _expect_error(f3_pfade.resolve_data_dir_with_env, {"F3_DRY_RUN": "1"})


def test_dry_run_invalid_value_fails_closed():
    _expect_error(f3_pfade.resolve_db_path_with_env, {"F3_DRY_RUN": "maybe"})


def test_dry_run_file_returns_db_path_and_parent_root(tmp_path):
    db = tmp_path / "dry.db"
    db.write_text("fixture", encoding="utf-8")
    env = {"F3_DRY_RUN": "1", "F3_DB_PATH": str(db)}
    assert _same(f3_pfade.resolve_db_path_with_env(env), db)
    assert _same(f3_pfade.resolve_data_dir_with_env(env), tmp_path)


def test_dry_run_directory_returns_dir_root(tmp_path):
    directory = tmp_path / "drydir"
    directory.mkdir()
    env = {"F3_DRY_RUN": "1", "F3_DB_PATH": str(directory)}
    assert _same(f3_pfade.resolve_db_path_with_env(env), directory)
    assert _same(f3_pfade.resolve_data_dir_with_env(env), directory)


def test_dry_run_missing_db_suffix_infers_file(tmp_path):
    missing = tmp_path / "missing.db"
    assert not missing.exists()
    env = {"F3_DRY_RUN": "1", "F3_DB_PATH": str(missing)}
    assert _same(f3_pfade.resolve_db_path_with_env(env), missing)
    assert _same(f3_pfade.resolve_data_dir_with_env(env), tmp_path)


def test_dry_run_missing_without_db_suffix_infers_directory(tmp_path):
    missing = tmp_path / "missing_dir"
    assert not missing.exists()
    env = {"F3_DRY_RUN": "1", "F3_DB_PATH": str(missing)}
    assert _same(f3_pfade.resolve_db_path_with_env(env), missing / "unified.db")
    assert _same(f3_pfade.resolve_data_dir_with_env(env), missing)


def test_dry_run_ignores_other_path_vars(tmp_path):
    env = {
        "F3_DRY_RUN": "1",
        "F3_DB_PATH": str(tmp_path / "x.db"),
        "FRANK3_DATA": "/should/be/ignored",
        "FRANKENSTEIN3_ROOT": "/should/be/ignored",
        "CLAUDE_PLUGIN_DATA": "/should/be/ignored",
        "XDG_DATA_HOME": "/should/be/ignored",
        "HOME": "/should/be/ignored",
    }
    assert _same(f3_pfade.resolve_db_path_with_env(env), tmp_path / "x.db")
    assert _same(f3_pfade.resolve_data_dir_with_env(env), tmp_path)


def test_dry_run_ensure_db_has_no_side_effects(tmp_path):
    target = tmp_path / "dry" / "custom.db"
    env = {"F3_DRY_RUN": "1", "F3_DB_PATH": str(target)}
    path = f3_pfade.ensure_db_with_env(env)
    assert _same(path, target)
    assert not target.parent.exists(), "dry-run must not create directories"


# --- F3_DB_PATH branch matrix ---------------------------------------------


def test_resolve_db_path_existing_file_branch(tmp_path):
    """Branch 1: F3_DB_PATH points at an existing FILE -> that exact file."""
    db_file = tmp_path / "existing.db"
    db_file.write_text("sqlite fixture", encoding="utf-8")
    assert db_file.is_file()

    env = {"F3_DB_PATH": str(db_file), "HOME": str(tmp_path / "home")}
    path = f3_pfade.resolve_db_path_with_env(env)

    assert _same(path, db_file), f"expected {db_file}, got {path}"
    assert not _same(path, db_file.parent / "unified.db")


def test_resolve_db_path_existing_directory_branch(tmp_path):
    """Branch 2: F3_DB_PATH points at an existing DIRECTORY -> <dir>/unified.db."""
    db_dir = tmp_path / "existing_dir"
    db_dir.mkdir()
    assert db_dir.is_dir()

    env = {"F3_DB_PATH": str(db_dir), "HOME": str(tmp_path / "home")}
    path = f3_pfade.resolve_db_path_with_env(env)

    assert _same(path, db_dir / "unified.db"), f"got {path}"
    assert not _same(path, db_dir)


def test_resolve_db_path_missing_db_suffix_branch(tmp_path):
    """Branch 3: missing path with a DB suffix -> the path itself."""
    for suffix in (".db", ".sqlite", ".sqlite3", ".db3"):
        missing = tmp_path / ("missing_db" + suffix)
        assert not missing.exists(), f"fixture must be missing: {missing}"

        env = {"F3_DB_PATH": str(missing), "HOME": str(tmp_path / "home")}
        path = f3_pfade.resolve_db_path_with_env(env)

        assert _same(path, missing), f"expected {missing}, got {path}"
        assert not _same(path, missing / "unified.db")


def test_resolve_db_path_missing_other_suffix_branch(tmp_path):
    """Branch 4: missing path with any other suffix -> <path>/unified.db."""
    for name in ("missing_dir", "missing_file.txt"):
        missing = tmp_path / name
        assert not missing.exists(), f"fixture must be missing: {missing}"

        env = {"F3_DB_PATH": str(missing), "HOME": str(tmp_path / "home")}
        path = f3_pfade.resolve_db_path_with_env(env)

        assert _same(path, missing / "unified.db"), f"got {path}"
        assert not _same(path, missing)


def test_data_dir_derived_from_f3_db_path(tmp_path):
    """Non-dry-run: the data root follows the same file/dir inference."""
    db_file = tmp_path / "custom.db"
    env = {"F3_DB_PATH": str(db_file)}
    assert _same(f3_pfade.resolve_data_dir_with_env(env), tmp_path)

    db_dir = tmp_path / "custom_dir"
    env = {"F3_DB_PATH": str(db_dir)}
    assert _same(f3_pfade.resolve_data_dir_with_env(env), db_dir)


# --- ensure_db / aliases ---------------------------------------------------


def test_ensure_db_creates_parent_directory(tmp_path):
    target = tmp_path / "nested" / "deep" / "custom.db"
    env = {"F3_DB_PATH": str(target)}
    path = f3_pfade.ensure_db_with_env(env)
    assert _same(path, target)
    assert target.parent.is_dir(), "ensure_db must create the parent directory"
    assert not target.exists(), "ensure_db creates the parent, not the DB file"


def test_ensure_db_creates_parent_directory_for_frank3_data(tmp_path):
    data_dir = tmp_path / "frank3" / "data"
    env = {"FRANK3_DATA": str(data_dir)}
    path = f3_pfade.ensure_db_with_env(env)
    assert _same(path, data_dir / "unified.db")
    assert data_dir.is_dir()


def test_ensure_db_creates_parent_directory_for_frank3_root(tmp_path):
    data_dir = tmp_path / "frank3" / "root"
    env = {"FRANKENSTEIN3_ROOT": str(data_dir)}
    path = f3_pfade.ensure_db_with_env(env)
    assert _same(path, data_dir / "unified.db")
    assert data_dir.is_dir()


def test_get_db_path_is_alias_of_resolve_db_path():
    assert f3_pfade.get_db_path is f3_pfade.resolve_db_path


def test_get_db_path_alias_behaviour(tmp_path):
    env = {"F3_DB_PATH": str(tmp_path / "alias.db")}
    with _env_scope(env):
        assert _same(f3_pfade.get_db_path(), f3_pfade.resolve_db_path())


def test_private_wrappers_exist():
    assert callable(f3_pfade._resolve_db_path)
    assert callable(f3_pfade._get_data_root)
    assert callable(f3_pfade.ensure_db)
    assert callable(f3_pfade.resolve_data_dir)


# --- portability guards ----------------------------------------------------


def test_db_file_suffixes_constant():
    """DB_FILE_SUFFIXES marks explicit SQLite database files."""
    suffixes = f3_pfade.DB_FILE_SUFFIXES

    assert {".db", ".sqlite", ".sqlite3"} <= set(suffixes), f"Got {sorted(suffixes)}"
    assert ".txt" not in suffixes, f"Got {sorted(suffixes)}"
    assert len(set(suffixes)) == len(suffixes), "DB_FILE_SUFFIXES must not contain duplicates"
    for suffix in suffixes:
        assert isinstance(suffix, str), f"non-string member: {suffix!r}"
        assert suffix.startswith("."), f"member must be dot-prefixed: {suffix!r}"
        assert suffix == suffix.lower(), f"member must be lowercase: {suffix!r}"


def test_no_hardcoded_home_or_machine_names():
    """The resolver must not embed user directories or machine names."""
    source = (FRANK3_ROOT / "f3_pfade.py").read_text(encoding="utf-8")
    forbidden = [
        "/" + "home" + "/",
        "/Users" + "/",
        "ai" + "-core-node",
        "gabri" + "el",
    ]
    for needle in forbidden:
        assert needle not in source, f"hard-coded token in source: {needle!r}"


# --- runner ----------------------------------------------------------------


def _run_all():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        for name, fn in sorted(globals().items()):
            if not name.startswith("test_") or not callable(fn):
                continue
            params = inspect.signature(fn).parameters
            if "tmp_path" in params:
                fn(base)
            else:
                fn()
            print("ok", name)


if __name__ == "__main__":
    _run_all()
    print("All Python path tests passed!")
