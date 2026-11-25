# -*- coding: utf-8 -*-
"""Contract tests for the scripts/star/f3_paths.py re-export shim."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SHIM_PATH = (
    REPO_ROOT / "plugins" / "frankenstein3" / "scripts" / "star" / "f3_paths.py"
)
SCRIPTS_STAR = SHIM_PATH.parent
PUBLIC_API = ("resolve_data_dir", "resolve_db_path", "ensure_db")


def _load_shim():
    spec = importlib.util.spec_from_file_location("zero40_f3_paths_shim", SHIM_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_authority():
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from plugins.frankenstein3 import f3_paths

    return f3_paths


def test_shim_reexports_authoritative_objects():
    shim = _load_shim()
    authority = _load_authority()
    for name in PUBLIC_API:
        assert getattr(shim, name) is getattr(authority, name), name
    assert tuple(shim.__all__) == PUBLIC_API


def test_shim_contains_no_resolver_logic():
    source = SHIM_PATH.read_text(encoding="utf-8")
    assert len(source.splitlines()) < 100
    for name in PUBLIC_API:
        assert f"def {name}" not in source
    assert "plugins.frankenstein3.f3_paths" in source


def test_shim_imports_when_scripts_star_is_on_sys_path():
    code = (
        "import f3_paths as s; "
        "assert all(callable(getattr(s, n, None)) for n in "
        "('resolve_data_dir','resolve_db_path','ensure_db'))"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SCRIPTS_STAR)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(SCRIPTS_STAR),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
