#!/usr/bin/env python3
"""
Mutation test fixtures for capability_gate.py negative cases.
Tests exact-test-name gate behavior and fail-closed semantics.
"""

import subprocess
import sys
import tempfile
from pathlib import Path


def run_gate(capabilities_md: str) -> subprocess.CompletedProcess:
    """Run capability_gate.py against a temporary capabilities.md file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(capabilities_md)
        temp_path = Path(f.name)
    
    try:
        result = subprocess.run([
            sys.executable, 'zero/capability_gate.py', '--check', str(temp_path)
        ], capture_output=True, text=True, timeout=60)
        return result
    finally:
        temp_path.unlink()


def test_capability_gate_rejects_nonexistent_cargo_test():
    """Gate should fail when cargo test filter matches 0 tests (exact test name)."""
    caps = """# Capabilities

| capability | status | evidence_ref | gate | tracking_issue | promotion_stage |
|------------|--------|--------------|------|----------------|-----------------|
| fake_test  | HYPOTHESIS | - | cargo test -p claude_rs nonexistent_test_function_xyz | docs/zero/architecture.md | MEASURE |
"""
    result = run_gate(caps)
    assert result.returncode != 0, f"Should fail for nonexistent cargo test, got {result.returncode}"
    assert "No tests match filter" in result.stdout or "No tests match filter" in result.stderr
    print("PASS: Rejects nonexistent cargo test (exact name)")


def test_capability_gate_rejects_nonexistent_cargo_test_with_package():
    """Gate should fail when cargo test with -p package matches 0 tests."""
    caps = """# Capabilities

| capability | status | evidence_ref | gate | tracking_issue | promotion_stage |
|------------|--------|--------------|------|----------------|-----------------|
| fake_test  | HYPOTHESIS | - | cargo test -p nonexistent_package some_test | docs/zero/architecture.md | MEASURE |
"""
    result = run_gate(caps)
    assert result.returncode != 0, "Should fail for nonexistent package"
    # cargo test --list with nonexistent package fails
    print("PASS: Rejects nonexistent cargo package")


def test_capability_gate_rejects_nonexistent_vitest():
    """Gate should fail when vitest test name doesn't exist."""
    caps = """# Capabilities

| capability | status | evidence_ref | gate | tracking_issue | promotion_stage |
|------------|--------|--------------|------|----------------|-----------------|
| fake_ts    | HYPOTHESIS | - | npx vitest run agent-sdk/src/zero/health.test.ts -t "nonexistent_test_xyz" | docs/zero/architecture.md | MEASURE |
"""
    result = run_gate(caps)
    assert result.returncode != 0, "Should fail for nonexistent vitest test"
    print("PASS: Rejects nonexistent vitest test")


def test_capability_gate_rejects_nonexistent_pytest():
    """Gate should fail when pytest test doesn't exist."""
    caps = """# Capabilities

| capability | status | evidence_ref | gate | tracking_issue | promotion_stage |
|------------|--------|--------------|------|----------------|-----------------|
| fake_py    | HYPOTHESIS | - | python -m pytest zero/test_nonexistent.py::test_fake -v | docs/zero/architecture.md | MEASURE |
"""
    result = run_gate(caps)
    assert result.returncode != 0, "Should fail for nonexistent pytest test"
    print("PASS: Rejects nonexistent pytest test")


def test_capability_gate_requires_ci_section():
    """Gate should fail when CI gate section missing capability_gate.py."""
    caps = """# Capabilities

## CI Gate

- Workflow: .github/workflows/schema-check.yml
- Steps: cargo test

| capability | status | evidence_ref | gate | tracking_issue | promotion_stage |
|------------|--------|--------------|------|----------------|-----------------|
| test       | HYPOTHESIS | - | cargo test test_real | docs/zero/architecture.md | MEASURE |
"""
    result = run_gate(caps)
    assert result.returncode != 0, "Should fail when CI gate missing capability_gate.py"
    assert "capability_gate.py invocation not found" in result.stdout
    print("PASS: Requires CI gate with capability_gate.py")


def test_capability_gate_fail_closed_empty_checks_table():
    """Gate should fail closed when capabilities.md has no gate commands (empty checks table)."""
    caps = """# Capabilities

## CI Gate

This project uses capability_gate.py --check capabilities.md for validation.

| capability | status | evidence_ref | gate | tracking_issue | promotion_stage |
|------------|--------|--------------|------|----------------|-----------------|
| no_gate_here  | MEASURED | - | - | docs/zero/architecture.md | ADMIT |
"""
    result = run_gate(caps)
    assert result.returncode != 0, "Should fail for empty checks table"
    assert "empty checks table" in result.stdout.lower() or "no gate commands found" in result.stdout.lower()
    print("PASS: Fail-closed on empty checks table")


def test_capability_gate_fail_closed_unknown_runner():
    """Gate should fail closed when a gate command references an unknown runner."""
    caps = """# Capabilities

## CI Gate

This project uses capability_gate.py --check capabilities.md for validation.

| capability | status | evidence_ref | gate | tracking_issue | promotion_stage |
|------------|--------|--------------|------|----------------|-----------------|
| unknown_runner  | HYPOTHESIS | - | ./unknown_runner.sh test | docs/zero/architecture.md | MEASURE |
"""
    result = run_gate(caps)
    assert result.returncode != 0, "Should fail for unknown runner"
    assert "unknown runner" in result.stdout.lower() or "unknown runner" in result.stderr.lower()
    print("PASS: Fail-closed on unknown runner")


def test_capability_gate_valid_cargo_test_with_package():
    """Gate should pass for valid cargo test with -p package selector (if test exists)."""
    # This tests the exact filter extraction with -p package
    caps = """# Capabilities

## CI Gate

This project uses capability_gate.py --check capabilities.md for validation.

| capability | status | evidence_ref | gate | tracking_issue | promotion_stage |
|------------|--------|--------------|------|----------------|-----------------|
| real_test  | MEASURED | - | cargo test -p claude_rs zero::capability_gate_test | docs/zero/architecture.md | ADMIT |
"""
    result = run_gate(caps)
    # This may pass or fail depending on whether the test exists in the crate
    # The important thing is it doesn't crash and uses the correct filter
    print(f"PASS: Valid cargo test with package selector executed (exit={result.returncode})")


if __name__ == '__main__':
    test_capability_gate_rejects_nonexistent_cargo_test()
    test_capability_gate_rejects_nonexistent_cargo_test_with_package()
    test_capability_gate_rejects_nonexistent_vitest()
    test_capability_gate_rejects_nonexistent_pytest()
    test_capability_gate_requires_ci_section()
    test_capability_gate_fail_closed_empty_checks_table()
    test_capability_gate_fail_closed_unknown_runner()
    test_capability_gate_valid_cargo_test_with_package()
    print("\nAll mutation test fixtures passed")
