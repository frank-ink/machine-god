#!/usr/bin/env python3
"""
Pytest-visible dry-run tests for f3_pfade.py resolver.

Tests verify:
- Dry-run requires F3_DB_PATH env var
- Dry-run ignores FRANK3_DATA, FRANKENSTEIN3_ROOT, CLAUDE_PLUGIN_DATA env vars
- Dry-run never writes to real data directory
- Fail-closed on typo values (maybe/false/0 treated as false)
- Dry-run ensure_db_with_env performs zero filesystem writes (no fixture DB created)
"""

import os
import tempfile
from pathlib import Path
import pytest

# Import the module under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from f3_pfade import (
    _resolve_db_path,
    _is_dry_run,
    _get_data_root,
    ensure_db_with_env,
    PfadeError,
)


class TestDryRunResolver:
    """Tests for dry-run behavior in f3_pfade resolver."""

    def setup_method(self):
        """Save original environment."""
        self.original_env = dict(os.environ)

    def teardown_method(self):
        """Restore original environment."""
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_dry_run_requires_F3_DB_PATH(self):
        """Dry-run mode requires F3_DB_PATH to be set explicitly."""
        os.environ['F3_DRY_RUN'] = 'true'
        os.environ.pop('F3_DB_PATH', None)
        os.environ.pop('FRANK3_DATA', None)
        os.environ.pop('FRANKENSTEIN3_ROOT', None)
        os.environ.pop('CLAUDE_PLUGIN_DATA', None)

        with pytest.raises(RuntimeError, match="F3_DB_PATH"):
            _resolve_db_path()

    def test_dry_run_ignores_FRANK3_DATA(self):
        """Dry-run mode ignores FRANK3_DATA even when set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_db = Path(tmpdir) / "fake.db"
            fake_db.write_text("fake")

            os.environ['F3_DRY_RUN'] = 'true'
            os.environ['F3_DB_PATH'] = str(fake_db)
            os.environ['FRANK3_DATA'] = "/this/should/be/ignored/real_data"

            result = _resolve_db_path()
            assert result == fake_db.resolve()
            assert "ignored" not in str(result)

    def test_dry_run_ignores_FRANKENSTEIN3_ROOT(self):
        """Dry-run mode ignores FRANKENSTEIN3_ROOT even when set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_db = Path(tmpdir) / "fake.db"
            fake_db.write_text("fake")

            os.environ['F3_DRY_RUN'] = 'true'
            os.environ['F3_DB_PATH'] = str(fake_db)
            os.environ['FRANKENSTEIN3_ROOT'] = "/this/should/be/ignored/root"

            result = _resolve_db_path()
            assert result == fake_db.resolve()
            assert "ignored" not in str(result)

    def test_dry_run_ignores_CLAUDE_PLUGIN_DATA(self):
        """Dry-run mode ignores CLAUDE_PLUGIN_DATA even when set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_db = Path(tmpdir) / "fake.db"
            fake_db.write_text("fake")

            os.environ['F3_DRY_RUN'] = 'true'
            os.environ['F3_DB_PATH'] = str(fake_db)
            os.environ['CLAUDE_PLUGIN_DATA'] = "/this/should/be/ignored/plugin"

            result = _resolve_db_path()
            assert result == fake_db.resolve()
            assert "ignored" not in str(result)

    def test_dry_run_never_writes_real_data_dir(self):
        """Dry-run never creates or writes to the real data directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dry_run_db = Path(tmpdir) / "dry_run.db"
            real_data_dir = Path(tmpdir) / "real_frank3_data"
            real_data_dir.mkdir()

            os.environ['F3_DRY_RUN'] = 'true'
            os.environ['F3_DB_PATH'] = str(dry_run_db)
            os.environ['FRANK3_DATA'] = str(real_data_dir)

            result = _resolve_db_path()

            assert result == dry_run_db.resolve()
            assert list(real_data_dir.iterdir()) == []

    def test_fail_closed_on_typo_maybe(self):
        """Typo value 'maybe' does NOT activate dry-run (fail-closed)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            real_db = Path(tmpdir) / "real.db"
            real_db.write_text("real")

            os.environ['F3_DRY_RUN'] = 'maybe'
            os.environ['F3_DB_PATH'] = str(real_db)
            os.environ.pop('FRANK3_DATA', None)

            assert _is_dry_run() is False

    def test_fail_closed_on_typo_false_string(self):
        """String 'false' does NOT activate dry-run (fail-closed)."""
        os.environ['F3_DRY_RUN'] = 'false'
        os.environ.pop('F3_DB_PATH', None)
        os.environ.pop('FRANK3_DATA', None)

        assert _is_dry_run() is False

    def test_fail_closed_on_typo_zero(self):
        """String '0' does NOT activate dry-run (fail-closed)."""
        os.environ['F3_DRY_RUN'] = '0'
        os.environ.pop('F3_DB_PATH', None)
        os.environ.pop('FRANK3_DATA', None)

        assert _is_dry_run() is False

    def test_fail_closed_on_empty_string(self):
        """Empty string does NOT activate dry-run (fail-closed)."""
        os.environ['F3_DRY_RUN'] = ''
        os.environ.pop('F3_DB_PATH', None)
        os.environ.pop('FRANK3_DATA', None)

        assert _is_dry_run() is False

    def test_fail_closed_on_random_string(self):
        """Random string does NOT activate dry-run (fail-closed)."""
        os.environ['F3_DRY_RUN'] = 'yes_please'
        os.environ.pop('F3_DB_PATH', None)
        os.environ.pop('FRANK3_DATA', None)

        assert _is_dry_run() is False

    def test_dry_run_true_activates(self):
        """Explicit 'true' activates dry-run."""
        os.environ['F3_DRY_RUN'] = 'true'
        os.environ.pop('F3_DB_PATH', None)
        os.environ.pop('FRANK3_DATA', None)

        assert _is_dry_run() is True

    def test_dry_run_1_activates(self):
        """Explicit '1' activates dry-run."""
        os.environ['F3_DRY_RUN'] = '1'
        os.environ.pop('F3_DB_PATH', None)
        os.environ.pop('FRANK3_DATA', None)

        assert _is_dry_run() is True

    def test_dry_run_case_insensitive(self):
        """Dry-run activation is case-insensitive for valid values."""
        for val in ['TRUE', 'True', '1', 'YES', 'yes']:
            os.environ['F3_DRY_RUN'] = val
            os.environ.pop('F3_DB_PATH', None)
            os.environ.pop('FRANK3_DATA', None)
            assert _is_dry_run() is True, f"Value '{val}' should activate dry-run"


class TestDataRootResolution:
    """Tests for _get_data_root behavior under dry-run."""

    def setup_method(self):
        self.original_env = dict(os.environ)

    def teardown_method(self):
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_data_root_uses_F3_DB_PATH_parent_in_dry_run(self):
        """In dry-run, data root is parent of F3_DB_PATH."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "subdir" / "test.db"
            db_path.parent.mkdir(parents=True)

            os.environ['F3_DRY_RUN'] = 'true'
            os.environ['F3_DB_PATH'] = str(db_path)
            os.environ['FRANK3_DATA'] = "/ignored"

            root = _get_data_root()
            assert root == db_path.parent.resolve()

    def test_data_root_falls_back_without_dry_run(self):
        """Without dry-run, uses FRANK3_DATA or default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            frank3_dir = Path(tmpdir) / "frank3_data"
            frank3_dir.mkdir()

            os.environ.pop('F3_DRY_RUN', None)
            os.environ['FRANK3_DATA'] = str(frank3_dir)

            root = _get_data_root()
            assert root == frank3_dir.resolve()


class TestIntegrationDryRun:
    """Integration-style tests for full resolution flow."""

    def setup_method(self):
        self.original_env = dict(os.environ)

    def teardown_method(self):
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_full_resolution_dry_run_isolated(self):
        """Full _resolve_db_path in dry-run is completely isolated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dry_db = Path(tmpdir) / "isolated.db"
            real_dir = Path(tmpdir) / "real_data"
            real_dir.mkdir()

            os.environ['F3_DRY_RUN'] = 'true'
            os.environ['F3_DB_PATH'] = str(dry_db)
            os.environ['FRANK3_DATA'] = str(real_dir)

            result = _resolve_db_path()

            assert result == dry_db.resolve()
            assert list(real_dir.iterdir()) == []

    def test_full_resolution_normal_uses_FRANK3_DATA(self):
        """Normal mode uses FRANK3_DATA when set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            frank3_dir = Path(tmpdir) / "frank3_data"
            frank3_dir.mkdir()
            expected_db = frank3_dir / "unified.db"

            os.environ.pop('F3_DRY_RUN', None)
            os.environ['FRANK3_DATA'] = str(frank3_dir)

            result = _resolve_db_path()
            assert result == expected_db.resolve()

    def test_missing_F3_DB_PATH_in_dry_run_raises_clear_error(self):
        """Missing F3_DB_PATH in dry-run raises actionable error."""
        os.environ['F3_DRY_RUN'] = 'true'
        os.environ.pop('F3_DB_PATH', None)
        os.environ.pop('FRANK3_DATA', None)

        with pytest.raises(RuntimeError) as exc_info:
            _resolve_db_path()

        error_msg = str(exc_info.value)
        assert "F3_DB_PATH" in error_msg
        assert "dry-run" in error_msg.lower() or "DRY_RUN" in error_msg


class TestEnsureDbWithEnvDryRun:
    """Tests that ensure_db_with_env performs zero filesystem writes in dry-run."""

    def setup_method(self):
        self.original_env = dict(os.environ)

    def teardown_method(self):
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_ensure_db_with_env_dry_run_creates_no_files(self):
        """Dry-run ensure_db_with_env must not create the fixture DB or any dirs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_db = Path(tmpdir) / "deep" / "nested" / "fixture.db"

            env = {
                "F3_DRY_RUN": "1",
                "F3_DB_PATH": str(target_db),
            }

            # Path must not exist before the call
            assert not target_db.exists()
            assert not target_db.parent.exists()

            result = ensure_db_with_env(env)

            # Resolver returns the requested path
            assert result == target_db.resolve()
            # Zero writes: no file, no parent directory created
            assert not target_db.exists()
            assert not target_db.parent.exists()
            assert list(tmpdir.iterdir()) == []

    def test_ensure_db_with_env_dry_run_ignores_frank3_data(self):
        """Dry-run ignores FRANK3_DATA and writes nothing anywhere."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_db = Path(tmpdir) / "dry.db"
            real_dir = Path(tmpdir) / "real"
            real_dir.mkdir()

            env = {
                "F3_DRY_RUN": "1",
                "F3_DB_PATH": str(target_db),
                "FRANK3_DATA": str(real_dir),
            }

            result = ensure_db_with_env(env)

            assert result == target_db.resolve()
            assert not target_db.exists()
            assert list(real_dir.iterdir()) == []

    def test_ensure_db_with_env_normal_mode_creates_parent_dir(self):
        """Non-dry-run ensure_db_with_env creates the parent directory (contrast)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_db = Path(tmpdir) / "new" / "normal.db"

            env = {
                "F3_DB_PATH": str(target_db),
                # F3_DRY_RUN unset -> normal mode
            }

            result = ensure_db_with_env(env)

            assert result == target_db.resolve()
            assert target_db.parent.exists()
            assert not target_db.exists()  # ensure_db does not create the DB file itself


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
