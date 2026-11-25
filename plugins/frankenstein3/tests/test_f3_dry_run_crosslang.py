#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-language test fixture for F3_DRY_RUN truthy semantics alignment.

Verifies that install.sh's _normalize_f3_dry_run() and f3_paths.is_dry_run()
agree on the unified truthy set: {'1','true','yes','on'} (case-insensitive).

Run: python3 -m pytest plugins/frankenstein3/tests/test_f3_dry_run_crosslang.py -v
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Ensure the plugin's scripts/star is importable
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
STAR_DIR = PLUGIN_ROOT / "scripts" / "star"
if str(STAR_DIR) not in sys.path:
    sys.path.insert(0, str(STAR_DIR))

from f3_paths import is_dry_run  # noqa: E402

INSTALL_SH = PLUGIN_ROOT / "install.sh"

# Marker used by install.sh for the dry-run temp directory name.
# The installer prints the *expanded* path, e.g.
#   DRY-RUN: data dir would be /custom/tmp/frankenstein3-dryrun-1234
_DRYRUN_MARKER = "frankenstein3-dryrun-"

# Unified truthy/falsy test matrix (raw_value, expected_normalized, expected_is_dry_run)
TEST_CASES = [
    # Truthy values (case variations)
    ("1", "1", True),
    ("true", "1", True),
    ("TRUE", "1", True),
    ("True", "1", True),
    ("yes", "1", True),
    ("YES", "1", True),
    ("on", "1", True),
    ("ON", "1", True),
    # Falsy values (case variations)
    ("0", "0", False),
    ("false", "0", False),
    ("FALSE", "0", False),
    ("no", "0", False),
    ("NO", "0", False),
    ("off", "0", False),
    ("OFF", "0", False),
    ("", "0", False),
    # Unknown values -> falsy (fail-closed)
    ("maybe", "0", False),
    ("2", "0", False),
    ("enabled", "0", False),
    ("disabled", "0", False),
]


def _candidate_dryrun_paths(stdout: str) -> list[Path]:
    """Return every absolute dry-run temp path that appears in installer output.

    The path is identified by the 'frankenstein3-dryrun-' marker inside a
    whitespace-delimited token. Unexpanded tokens (e.g. '$TMPDIR/...') are
    ignored: only absolute, already-expanded paths are candidates.
    """
    candidates: list[Path] = []
    for token in re.split(r"\s+", stdout):
        if _DRYRUN_MARKER not in token:
            continue
        raw = token.strip("\"'`,;:")
        if "=" in raw:
            raw = raw.rsplit("=", 1)[1]
        if not raw.startswith("/") and "/" in raw:
            raw = raw[raw.index("/"):]
        if raw.startswith("/"):
            candidates.append(Path(raw))
    return candidates


def _is_under(path: Path, base: Path) -> bool:
    """True iff `path` resolves inside `base` (prefix check on resolved paths)."""
    try:
        path.resolve().relative_to(base.resolve())
    except ValueError:
        return False
    return True


def _resolve_dryrun_temp_path(stdout: str, expected_base: Path) -> Path:
    """Pick the dry-run temp path printed by install.sh.

    If several candidates exist, the one under `expected_base` wins; otherwise
    the first absolute candidate is returned so the caller fails loudly.
    """
    candidates = _candidate_dryrun_paths(stdout)
    assert candidates, (
        "installer output contains no absolute dry-run temp path: " + stdout
    )
    for candidate in candidates:
        if _is_under(candidate, expected_base):
            return candidate
    return candidates[0]


def _run_install_sh_normalize(raw_value: str) -> str:
    """Run install.sh's _normalize_f3_dry_run function in a subprocess and return its output."""
    # We source install.sh and call the internal function directly
    script = f"""
source {INSTALL_SH} 2>/dev/null || true
_normalize_f3_dry_run "{raw_value}"
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ, "F3_DRY_RUN": raw_value},
    )
    if proc.returncode != 0:
        raise RuntimeError(f"install.sh normalize failed: {proc.stderr}")
    return proc.stdout.strip()


def test_crosslang_truthy_alignment():
    """install.sh normalize and f3_paths.is_dry_run must agree on every test case."""
    for raw, expected_norm, expected_dry in TEST_CASES:
        # Test install.sh normalization
        norm = _run_install_sh_normalize(raw)
        assert norm == expected_norm, (
            f"install.sh _normalize_f3_dry_run({raw!r}) = {norm!r}, expected {expected_norm!r}"
        )

        # Test f3_paths.is_dry_run
        old = os.environ.get("F3_DRY_RUN")
        try:
            if raw == "":
                os.environ.pop("F3_DRY_RUN", None)
            else:
                os.environ["F3_DRY_RUN"] = raw
            # Need to re-import to pick up new env (module uses os.environ.get at call time)
            from importlib import reload
            import f3_paths
            reload(f3_paths)
            from f3_paths import is_dry_run as is_dry_run_fresh
            result = is_dry_run_fresh()
        finally:
            if old is None:
                os.environ.pop("F3_DRY_RUN", None)
            else:
                os.environ["F3_DRY_RUN"] = old

        assert result == expected_dry, (
            f"f3_paths.is_dry_run() with F3_DRY_RUN={raw!r} = {result}, expected {expected_dry}"
        )

    print("All cross-language truthy alignment tests passed!")


def test_acceptance_criteria_shell():
    """Acceptance: F3_DRY_RUN=false ./install.sh --dry-run must NOT set DRY_RUN=true."""
    # This simulates: bash -c 'source install.sh; F3_DRY_RUN=false ./install.sh --dry-run 2>&1 | grep -q DRY_RUN=true'
    # The grep should FAIL (return non-zero) because 'false' is not truthy.
    script = f"""
source {INSTALL_SH} 2>/dev/null || true
F3_DRY_RUN=false {INSTALL_SH} --dry-run 2>&1
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
    )
    output = proc.stdout + proc.stderr
    # DRY-RUN message should NOT appear because 'false' is falsy
    assert "DRY-RUN:" not in output, (
        f"F3_DRY_RUN=false incorrectly triggered dry-run mode. Output: {output}"
    )
    print("Acceptance criteria (shell false): PASSED")


def test_acceptance_criteria_shell_true():
    """Acceptance: F3_DRY_RUN=1 ./install.sh --dry-run MUST set DRY_RUN=true."""
    script = f"""
source {INSTALL_SH} 2>/dev/null || true
F3_DRY_RUN=1 {INSTALL_SH} --dry-run 2>&1
"""
    proc = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
    )
    output = proc.stdout + proc.stderr
    assert "DRY-RUN:" in output, (
        f"F3_DRY_RUN=1 did not trigger dry-run mode. Output: {output}"
    )
    print("Acceptance criteria (shell 1): PASSED")


def test_acceptance_criteria_python():
    """Acceptance: Python test from task description must pass."""
    # os.environ['F3_DRY_RUN']='false'; assert _is_dry_run() == False
    # os.environ['F3_DRY_RUN']='1'; assert _is_dry_run() == True
    old = os.environ.get("F3_DRY_RUN")
    try:
        os.environ["F3_DRY_RUN"] = "false"
        from importlib import reload
        import f3_paths
        reload(f3_paths)
        from f3_paths import is_dry_run as is_dry_run_fresh
        assert is_dry_run_fresh() is False, "F3_DRY_RUN='false' should be False"

        os.environ["F3_DRY_RUN"] = "1"
        reload(f3_paths)
        from f3_paths import is_dry_run as is_dry_run_fresh2
        assert is_dry_run_fresh2() is True, "F3_DRY_RUN='1' should be True"
    finally:
        if old is None:
            os.environ.pop("F3_DRY_RUN", None)
        else:
            os.environ["F3_DRY_RUN"] = old
    print("Acceptance criteria (python): PASSED")


# --- NEW TEST: Dry-run isolation with FRANK3_DATA set ---
def test_dry_run_isolation_frank3_data_set():
    """ACCEPTANCE: FRANK3_DATA=real + F3_DB_PATH=fixture + F3_DRY_RUN=1 -> returns fixture path.

    This is the core acceptance test for the dry-run isolation guard.
    When F3_DRY_RUN=1, the resolver MUST return F3_DB_PATH target (or error if unset),
    ignoring FRANK3_DATA/CLAUDE_PLUGIN_DATA/XDG/HOME completely.
    """
    from importlib import reload
    import f3_paths
    reload(f3_paths)
    from f3_paths import _resolve_db_path, PathsError

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir(parents=True)

        # Real data directory (should be IGNORED in dry-run)
        real_data = root / "real_frank3_data"
        real_data.mkdir(parents=True)

        # Fixture database (should be RETURNED in dry-run)
        fixture_db = root / "fixture" / "unified.db"
        fixture_db.parent.mkdir(parents=True, exist_ok=True)

        # Set up environment: FRANK3_DATA points to real, F3_DB_PATH to fixture, dry-run enabled
        old_env = {}
        for key in ("HOME", "F3_DRY_RUN", "F3_DB_PATH", "FRANK3_DATA", "CLAUDE_PLUGIN_DATA", "XDG_DATA_HOME"):
            old_env[key] = os.environ.get(key)

        try:
            os.environ["HOME"] = str(home)
            os.environ["F3_DRY_RUN"] = "1"
            os.environ["F3_DB_PATH"] = str(fixture_db)
            os.environ["FRANK3_DATA"] = str(real_data)
            os.environ.pop("CLAUDE_PLUGIN_DATA", None)
            os.environ.pop("XDG_DATA_HOME", None)

            reload(f3_paths)
            from f3_paths import _resolve_db_path as resolve_fresh

            result = resolve_fresh()

            # MUST return the fixture path, NOT the real data path
            assert result == fixture_db.resolve(), (
                f"Dry-run isolation failed: expected {fixture_db.resolve()}, got {result}"
            )
            assert result != (real_data / "unified.db").resolve(), (
                f"Dry-run incorrectly fell back to FRANK3_DATA: {result}"
            )

            print("ACCEPTANCE PASSED: Dry-run with FRANK3_DATA set returns F3_DB_PATH fixture")

        finally:
            for key, val in old_env.items():
                if val is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = val


def test_dry_run_isolation_without_f3_db_path_raises():
    """ACCEPTANCE: F3_DRY_RUN=1 without F3_DB_PATH must raise PathsError (not fall back)."""
    from importlib import reload
    import f3_paths
    reload(f3_paths)
    from f3_paths import _resolve_db_path, PathsError

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir(parents=True)
        real_data = root / "real_frank3_data"
        real_data.mkdir(parents=True)

        old_env = {}
        for key in ("HOME", "F3_DRY_RUN", "F3_DB_PATH", "FRANK3_DATA", "CLAUDE_PLUGIN_DATA", "XDG_DATA_HOME"):
            old_env[key] = os.environ.get(key)

        try:
            os.environ["HOME"] = str(home)
            os.environ["F3_DRY_RUN"] = "1"
            os.environ["FRANK3_DATA"] = str(real_data)
            os.environ.pop("F3_DB_PATH", None)
            os.environ.pop("CLAUDE_PLUGIN_DATA", None)
            os.environ.pop("XDG_DATA_HOME", None)

            reload(f3_paths)
            from f3_paths import _resolve_db_path as resolve_fresh

            try:
                resolve_fresh()
                assert False, "Expected PathsError: dry-run requires F3_DB_PATH"
            except PathsError as e:
                assert "F3_DRY_RUN=1 requires F3_DB_PATH" in str(e)
                print("ACCEPTANCE PASSED: Dry-run without F3_DB_PATH raises PathsError")

        finally:
            for key, val in old_env.items():
                if val is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = val


# --- NEW TEST: Installer --dry-run creates no files in real data dir ---
def test_installer_dry_run_creates_no_files_in_real_data_dir():
    """ACCEPTANCE: ./install.sh --dry-run with FRANK3_DATA set creates no files in real data dir.

    This verifies the installer's --dry-run flag (not F3_DRY_RUN env var) properly
    isolates the real data directory by returning a temp path and exiting before any writes.
    The reported temp path must expand under $TMPDIR (resolved prefix), not a literal /tmp.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir(parents=True)
        real_data = root / "real_frank3_data"
        real_data.mkdir(parents=True)
        custom_tmp = root / "custom_tmp"
        custom_tmp.mkdir(parents=True)

        # Environment: FRANK3_DATA points to real data dir, no F3_DRY_RUN (so not fixture mode)
        env = {
            **os.environ,
            "HOME": str(home),
            "FRANK3_DATA": str(real_data),
            "F3_DRY_RUN": "0",  # Explicitly falsy to avoid fixture mode
            "TMPDIR": str(custom_tmp),
        }
        # Remove any vars that would affect resolution
        for key in ["F3_DB_PATH", "CLAUDE_PLUGIN_DATA", "XDG_DATA_HOME", "FRANKENSTEIN3_ROOT"]:
            env.pop(key, None)

        proc = subprocess.run(
            [str(INSTALL_SH), "--dry-run"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(PLUGIN_ROOT),
        )

        # Must exit successfully
        assert proc.returncode == 0, f"Installer failed with exit code {proc.returncode}: {proc.stderr}"

        # Must print DRY-RUN message
        assert "DRY-RUN:" in proc.stdout, f"Expected DRY-RUN output, got: {proc.stdout}"

        # Real data dir must remain completely empty (no unified.db, no subdirs)
        real_db = real_data / "unified.db"
        assert not real_db.exists(), f"Real DB created at {real_db} during dry-run"
        assert not any(real_data.iterdir()), f"Files created in real data dir during dry-run: {list(real_data.iterdir())}"

        # The reported data dir must be the expanded temp path under $TMPDIR.
        # Single check on the resolved path prefix - not a literal-string alternative.
        dryrun_path = _resolve_dryrun_temp_path(proc.stdout, custom_tmp)
        assert _is_under(dryrun_path, custom_tmp), (
            f"Dry-run temp path {dryrun_path} does not expand under TMPDIR={custom_tmp}; "
            f"installer output: {proc.stdout}"
        )
        assert not str(dryrun_path).startswith("/tmp/frankenstein3-dryrun-"), (
            f"Dry-run temp path must not be hard-coded under /tmp: {dryrun_path}"
        )
        assert str(real_data) not in proc.stdout, (
            f"Dry-run should not reference real data dir {real_data}, got: {proc.stdout}"
        )

        print("ACCEPTANCE PASSED: Installer --dry-run creates no files in real data dir")


# --- NEW TEST: Installer F3_DRY_RUN=1 creates no files in real data dir ---
def test_installer_f3_dry_run_creates_no_files_in_real_data_dir():
    """ACCEPTANCE: F3_DRY_RUN=1 with F3_DB_PATH=fixture creates no files in real data dir.

    This verifies the installer's F3_DRY_RUN=1 env var (fixture mode) properly
    isolates the real data directory by exiting before any writes.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir(parents=True)
        real_data = root / "real_frank3_data"
        real_data.mkdir(parents=True)
        fixture_db = root / "fixture" / "unified.db"
        fixture_db.parent.mkdir(parents=True, exist_ok=True)

        # Environment: FRANK3_DATA points to real data dir, F3_DRY_RUN=1 with fixture DB
        env = {
            **os.environ,
            "HOME": str(home),
            "FRANK3_DATA": str(real_data),
            "F3_DRY_RUN": "1",
            "F3_DB_PATH": str(fixture_db),
        }
        # Remove any vars that would affect resolution
        for key in ["CLAUDE_PLUGIN_DATA", "XDG_DATA_HOME", "FRANKENSTEIN3_ROOT"]:
            env.pop(key, None)

        proc = subprocess.run(
            [str(INSTALL_SH)],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(PLUGIN_ROOT),
        )

        # Must exit successfully
        assert proc.returncode == 0, f"Installer failed with exit code {proc.returncode}: {proc.stderr}"

        # Must print DRY-RUN message
        assert "DRY-RUN:" in proc.stdout, f"Expected DRY-RUN output, got: {proc.stdout}"

        # Real data dir must remain completely empty (no unified.db, no subdirs)
        real_db = real_data / "unified.db"
        assert not real_db.exists(), f"Real DB created at {real_db} during F3_DRY_RUN=1"
        assert not any(real_data.iterdir()), f"Files created in real data dir during F3_DRY_RUN=1: {list(real_data.iterdir())}"

        # Fixture DB must NOT be created either (dry-run doesn't init DB)
        assert not fixture_db.exists(), f"Fixture DB created at {fixture_db} during dry-run"

        # The reported data dir should be the fixture path
        assert str(fixture_db.parent) in proc.stdout, (
            f"Dry-run should report fixture data dir, got: {proc.stdout}"
        )
        assert str(real_data) not in proc.stdout, (
            f"Dry-run should not reference real data dir {real_data}, got: {proc.stdout}"
        )

        print("ACCEPTANCE PASSED: Installer F3_DRY_RUN=1 creates no files in real data dir")


# --- NEW TEST: Temp dir uses TMPDIR with fallback ---
def test_installer_uses_tmpdir_not_hardcoded_tmp():
    """ACCEPTANCE: Installer uses $TMPDIR (fallback /tmp) for dry-run temp path, not hard-coded /tmp.

    The check is on the *resolved* path prefix: the printed dry-run path must
    resolve inside the custom TMPDIR. If the installer hard-codes /tmp, the
    resolved path is /tmp/frankenstein3-dryrun-* and this test fails.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir(parents=True)
        real_data = root / "real_frank3_data"
        real_data.mkdir(parents=True)

        # Test with custom TMPDIR
        custom_tmp = root / "custom_tmp"
        custom_tmp.mkdir(parents=True)

        env = {
            **os.environ,
            "HOME": str(home),
            "FRANK3_DATA": str(real_data),
            "F3_DRY_RUN": "0",
            "TMPDIR": str(custom_tmp),
        }
        for key in ["F3_DB_PATH", "CLAUDE_PLUGIN_DATA", "XDG_DATA_HOME", "FRANKENSTEIN3_ROOT"]:
            env.pop(key, None)

        proc = subprocess.run(
            [str(INSTALL_SH), "--dry-run"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(PLUGIN_ROOT),
        )

        assert proc.returncode == 0, f"Installer failed: {proc.stderr}"
        assert "DRY-RUN:" in proc.stdout

        # The printed temp path must resolve under the custom TMPDIR (prefix check).
        dryrun_path = _resolve_dryrun_temp_path(proc.stdout, custom_tmp)
        resolved_path = dryrun_path.resolve()
        assert _is_under(resolved_path, custom_tmp), (
            f"Dry-run temp path {dryrun_path} (resolved: {resolved_path}) is not under "
            f"TMPDIR={custom_tmp}; installer output: {proc.stdout}"
        )
        # Must not be the hard-coded /tmp prefix.
        assert not str(dryrun_path).startswith("/tmp/frankenstein3-dryrun-"), (
            f"Dry-run temp path must not be hard-coded under /tmp: {dryrun_path}"
        )

        print("ACCEPTANCE PASSED: Installer uses TMPDIR for temp path")


# --- NEW TEST: Cleanup assertion - temp dir cleaned up on exit ---
def test_dry_run_temp_dir_cleanup():
    """ACCEPTANCE: Dry-run temp directory is cleaned up (no orphaned temp dirs left behind).

    The installer's --dry-run creates a temp path like $TMPDIR/frankenstein3-dryrun-$$
    but exits before creating it. This test verifies no temp dirs are left behind.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir(parents=True)
        real_data = root / "real_frank3_data"
        real_data.mkdir(parents=True)

        # Use a known TMPDIR to track what gets created
        test_tmpdir = root / "test_tmpdir"
        test_tmpdir.mkdir(parents=True)

        env = {
            **os.environ,
            "HOME": str(home),
            "FRANK3_DATA": str(real_data),
            "F3_DRY_RUN": "0",
            "TMPDIR": str(test_tmpdir),
        }
        for key in ["F3_DB_PATH", "CLAUDE_PLUGIN_DATA", "XDG_DATA_HOME", "FRANKENSTEIN3_ROOT"]:
            env.pop(key, None)

        # Run installer --dry-run multiple times
        for _ in range(3):
            proc = subprocess.run(
                [str(INSTALL_SH), "--dry-run"],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(PLUGIN_ROOT),
            )
            assert proc.returncode == 0

        # Check test_tmpdir: should only have the temp dirs from the dry-run runs
        # But since dry-run exits before mkdir, there should be ZERO frankenstein3-dryrun-* dirs
        dryrun_dirs = list(test_tmpdir.glob("frankenstein3-dryrun-*"))
        assert len(dryrun_dirs) == 0, (
            f"Orphaned dry-run temp dirs found in {test_tmpdir}: {dryrun_dirs}. "
            "Dry-run should not create any directories."
        )

        print("ACCEPTANCE PASSED: No orphaned temp dirs left after dry-run")


if __name__ == "__main__":
    test_crosslang_truthy_alignment()
    test_acceptance_criteria_shell()
    test_acceptance_criteria_shell_true()
    test_acceptance_criteria_python()
    test_dry_run_isolation_frank3_data_set()
    test_dry_run_isolation_without_f3_db_path_raises()
    test_installer_dry_run_creates_no_files_in_real_data_dir()
    test_installer_f3_dry_run_creates_no_files_in_real_data_dir()
    test_installer_uses_tmpdir_not_hardcoded_tmp()
    test_dry_run_temp_dir_cleanup()
    print("\n✓ All cross-language F3_DRY_RUN tests passed!")
