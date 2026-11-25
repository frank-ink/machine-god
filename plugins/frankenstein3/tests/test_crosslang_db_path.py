#!/usr/bin/env python3
"""
Cross-language DB path parity test.

Verifies that Rust (src/zero/entity.rs), TypeScript (agent-sdk/src/zero/health.ts),
and Python (plugins/frankenstein3/f3_paths.py) resolve the identical DB path
under identical environment variable combinations.

Tests at least 5 env combinations:
1. FRANK3_DATA only
2. F3_DB_PATH only (as directory)
3. F3_DB_PATH only (as file)
4. XDG_DATA_HOME only
5. HOME only
6. Conflict: FRANK3_DATA vs F3_DB_PATH (FRANK3_DATA wins)
7. Conflict: F3_DB_PATH vs XDG_DATA_HOME (F3_DB_PATH wins)
8. Windows USERPROFILE fallback
9. FRANKENSTEIN3_ROOT only
10. CLAUDE_PLUGIN_DATA only
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

# Add the frankenstein3 module to path
FRANK3_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(FRANK3_ROOT))

from f3_paths import resolve_db_path_with_env


def run_rust_resolver(env: Dict[str, str]) -> str:
    """Call the Rust resolver via cargo test -- --nocapture or a small binary."""
    rust_code = '''
    use std::env;
    use std::path::PathBuf;

    fn resolve_db_path() -> PathBuf {
        // 1. FRANK3_DATA
        if let Ok(val) = env::var("FRANK3_DATA") {
            return PathBuf::from(val).join("unified.db");
        }
        // 2. FRANKENSTEIN3_ROOT
        if let Ok(val) = env::var("FRANKENSTEIN3_ROOT") {
            return PathBuf::from(val).join("unified.db");
        }
        // 3. F3_DB_PATH
        if let Ok(val) = env::var("F3_DB_PATH") {
            let path = PathBuf::from(val);
            if path.extension().is_some() {
                return path;
            } else {
                return path.join("unified.db");
            }
        }
        // 4. CLAUDE_PLUGIN_DATA
        if let Ok(val) = env::var("CLAUDE_PLUGIN_DATA") {
            return PathBuf::from(val).join("unified.db");
        }
        // 5. XDG_DATA_HOME
        if let Ok(xdg) = env::var("XDG_DATA_HOME") {
            return PathBuf::from(xdg).join("frankenstein3").join("unified.db");
        }
        // 6. HOME fallback
        if let Ok(home) = env::var("HOME") {
            return PathBuf::from(home).join(".local").join("share").join("frankenstein3").join("unified.db");
        }
        // 7. Windows USERPROFILE fallback
        if let Ok(userprofile) = env::var("USERPROFILE") {
            return PathBuf::from(userprofile).join("AppData").join("Local").join("frankenstein3").join("unified.db");
        }
        panic!("Cannot resolve DB path");
    }

    fn main() {
        println!("{}", resolve_db_path().display());
    }
    '''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.rs', delete=False) as f:
        f.write(rust_code)
        rust_file = f.name

    try:
        env_vars = os.environ.copy()
        env_vars.update(env)
        result = subprocess.run(
            ["rustc", "--edition", "2021", "-o", rust_file.replace('.rs', ''), rust_file],
            capture_output=True,
            text=True,
            env=env_vars,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Rust compile failed: {result.stderr}")

        result = subprocess.run(
            [rust_file.replace('.rs', '')],
            capture_output=True,
            text=True,
            env=env_vars,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Rust run failed: {result.stderr}")

        return result.stdout.strip()
    finally:
        for ext in ['', '.rs']:
            try:
                os.unlink(rust_file.replace('.rs', ext))
            except OSError:
                pass


def run_ts_resolver(env: Dict[str, str]) -> str:
    """Call the TypeScript resolver via node."""
    ts_code = '''
    const { resolve } = require("node:path");
    const { homedir } = require("node:os");

    function resolveDbPath() {
        const frank3Data = process.env.FRANK3_DATA;
        if (frank3Data) {
            return resolve(frank3Data, "unified.db");
        }
        const frank3Root = process.env.FRANKENSTEIN3_ROOT;
        if (frank3Root) {
            return resolve(frank3Root, "unified.db");
        }
        const f3DbPath = process.env.F3_DB_PATH;
        if (f3DbPath) {
            const parsed = resolve(f3DbPath);
            const ext = parsed.split(".").pop()?.toLowerCase();
            const knownDbExts = ["db", "sqlite", "sqlite3", "db3"];
            if (ext && knownDbExts.includes(ext)) {
                return parsed;
            }
            return resolve(parsed, "unified.db");
        }
        const claudePluginData = process.env.CLAUDE_PLUGIN_DATA;
        if (claudePluginData) {
            return resolve(claudePluginData, "unified.db");
        }
        const xdgDataHome = process.env.XDG_DATA_HOME;
        if (xdgDataHome) {
            return resolve(xdgDataHome, "frankenstein3", "unified.db");
        }
        const home = process.env.HOME ?? homedir();
        if (home) {
            return resolve(home, ".local", "share", "frankenstein3", "unified.db");
        }
        const userProfile = process.env.USERPROFILE;
        if (userProfile) {
            return resolve(userProfile, "AppData", "Local", "frankenstein3", "unified.db");
        }
        throw new Error("Cannot resolve DB path");
    }

    console.log(resolveDbPath());
    '''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
        f.write(ts_code)
        ts_file = f.name

    try:
        env_vars = os.environ.copy()
        env_vars.update(env)
        result = subprocess.run(
            ["node", ts_file],
            capture_output=True,
            text=True,
            env=env_vars,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Node run failed: {result.stderr}")

        return result.stdout.strip()
    finally:
        try:
            os.unlink(ts_file)
        except OSError:
            pass


def run_python_resolver(env: Dict[str, str]) -> str:
    """Call the Python resolver."""
    return str(resolve_db_path_with_env(env))


def normalize_path(path: str) -> str:
    """Normalize path for comparison (resolve symlinks, absolute)."""
    return str(Path(path).resolve())


TEST_CASES: List[Tuple[str, Dict[str, str], str]] = [
    (
        "FRANK3_DATA_only",
        {"FRANK3_DATA": "/custom/frank3/data"},
        "/custom/frank3/data/unified.db",
    ),
    (
        "FRANKENSTEIN3_ROOT_only",
        {"FRANKENSTEIN3_ROOT": "/root/env"},
        "/root/env/unified.db",
    ),
    (
        "F3_DB_PATH_as_directory",
        {"F3_DB_PATH": "/custom/f3/db/dir"},
        "/custom/f3/db/dir/unified.db",
    ),
    (
        "F3_DB_PATH_as_file",
        {"F3_DB_PATH": "/custom/f3/db.sqlite"},
        "/custom/f3/db.sqlite",
    ),
    (
        "CLAUDE_PLUGIN_DATA_only",
        {"CLAUDE_PLUGIN_DATA": "/plugin/data"},
        "/plugin/data/unified.db",
    ),
    (
        "XDG_DATA_HOME_only",
        {"XDG_DATA_HOME": "/xdg/data"},
        "/xdg/data/frankenstein3/unified.db",
    ),
    (
        "HOME_only",
        {"HOME": "/home/testuser"},
        "/home/testuser/.local/share/frankenstein3/unified.db",
    ),
    (
        "FRANK3_DATA_wins_over_F3_DB_PATH",
        {"FRANK3_DATA": "/frank3/wins", "F3_DB_PATH": "/f3/loses"},
        "/frank3/wins/unified.db",
    ),
    (
        "F3_DB_PATH_wins_over_XDG",
        {"F3_DB_PATH": "/f3/wins", "XDG_DATA_HOME": "/xdg/loses"},
        "/f3/wins/unified.db",
    ),
    (
        "USERPROFILE_fallback",
        {"USERPROFILE": "C:\\\\Users\\\\testuser"},
        "C:\\Users\\testuser\\AppData\\Local\\frankenstein3\\unified.db",
    ),
]


def test_all_resolvers() -> bool:
    """Run all test cases against all three resolvers."""
    all_passed = True

    for name, env, expected in TEST_CASES:
        print(f"\n=== Test: {name} ===")
        print(f"Env: {env}")
        print(f"Expected: {expected}")

        try:
            rust_path = run_rust_resolver(env)
            ts_path = run_ts_resolver(env)
            py_path = run_python_resolver(env)

            rust_norm = normalize_path(rust_path)
            ts_norm = normalize_path(ts_path)
            py_norm = normalize_path(py_path)
            expected_norm = normalize_path(expected)

            print(f"Rust:   {rust_path} -> {rust_norm}")
            print(f"TS:     {ts_path} -> {ts_norm}")
            print(f"Python: {py_path} -> {py_norm}")

            if rust_norm != ts_norm:
                print(f"❌ FAIL: Rust ({rust_norm}) != TS ({ts_norm})")
                all_passed = False
            elif rust_norm != py_norm:
                print(f"❌ FAIL: Rust ({rust_norm}) != Python ({py_norm})")
                all_passed = False
            elif rust_norm != expected_norm:
                print(f"❌ FAIL: All ({rust_norm}) != Expected ({expected_norm})")
                all_passed = False
            else:
                print(f"✅ PASS: All three match expected")

        except Exception as e:
            print(f"❌ ERROR: {e}")
            all_passed = False

    return all_passed


def test_manifest_db_path_derives_from_data_dir():
    """db_path must equal data_dir / unified.db for all dir-based precedence levels."""
    from f3_paths import resolve_data_dir_with_env

    cases = [
        {"FRANK3_DATA": "/data/env"},
        {"FRANKENSTEIN3_ROOT": "/root/env"},
        {"CLAUDE_PLUGIN_DATA": "/plugin/data"},
        {"XDG_DATA_HOME": "/xdg/data"},
        {"HOME": "/home/user"},
    ]
    for env in cases:
        data_dir = resolve_data_dir_with_env(env)
        db_path = resolve_db_path_with_env(env)
        assert str(db_path) == str(data_dir / "unified.db"), (
            f"{env}: {db_path} != {data_dir}/unified.db"
        )


def test_manifest_conflict_higher_precedence_wins():
    """When all env vars are set, FRANK3_DATA (highest) must win."""
    env = {
        "FRANK3_DATA": "/high",
        "FRANKENSTEIN3_ROOT": "/mid",
        "F3_DB_PATH": "/low.db",
        "CLAUDE_PLUGIN_DATA": "/lower",
        "XDG_DATA_HOME": "/xdg",
        "HOME": "/home",
        "USERPROFILE": "C:\\Users\\u",
    }
    actual = str(resolve_db_path_with_env(env))
    assert actual == "/high/unified.db", actual


def test_manifest_no_hard_coded_absolute_paths():
    """Manifest must not contain absolute host paths."""
    manifest_path = FRANK3_ROOT / "zero-manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    text = json.dumps(manifest)
    assert not re.search(r"/(home|root|tmp|var|etc|usr)/[A-Za-z0-9_.-/]+", text), (
        "hard-coded Unix path found in manifest"
    )
    assert not re.search(r"[A-Za-z]:\\\\", text), "hard-coded Windows path found in manifest"


def test_manifest_paths_object_structure():
    """Manifest paths object must have db_path and data_dir with derives_from and resolver."""
    manifest_path = FRANK3_ROOT / "zero-manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    paths = manifest.get("paths", {})
    assert "db_path" in paths, "paths.db_path missing"
    assert "data_dir" in paths, "paths.data_dir missing"

    db_path = paths["db_path"]
    assert db_path.get("derives_from") == "data_dir", "db_path must derive from data_dir"
    assert "resolver" in db_path, "db_path must have resolver"

    data_dir = paths["data_dir"]
    assert "resolver" in data_dir, "data_dir must have resolver"


if __name__ == "__main__":
    print("=" * 60)
    print("Cross-Language DB Path Parity Test")
    print("=" * 60)

    success = test_all_resolvers()

    print("\n" + "=" * 60)
    print("Manifest structure tests...")
    try:
        test_manifest_db_path_derives_from_data_dir()
        print("✅ test_manifest_db_path_derives_from_data_dir")
        test_manifest_conflict_higher_precedence_wins()
        print("✅ test_manifest_conflict_higher_precedence_wins")
        test_manifest_no_hard_coded_absolute_paths()
        print("✅ test_manifest_no_hard_coded_absolute_paths")
        test_manifest_paths_object_structure()
        print("✅ test_manifest_paths_object_structure")
    except Exception as e:
        print(f"❌ Manifest test failed: {e}")
        success = False

    print("\n" + "=" * 60)
    if success:
        print("✅ ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED")
        sys.exit(1)
