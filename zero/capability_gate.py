#!/usr/bin/env python3
"""
Capability Gate Validator (GRF / ClayCode)

State authority: docs/zero/capabilities.md
Transition: parse -> extract_gates -> execute_list -> admit_or_reject
Invariant: GATE_NON_EMPTY (every gate resolves to >=1 listed test)
Invariant: RUNNER_KNOWN (every gate command maps to a known runner)
ON_VIOLATION -> exit non-zero (fail-closed)
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

GATE_RUNNERS = [
    (re.compile(r"^cargo test\b"), "cargo"),
    (re.compile(r"^npx vitest run\b"), "vitest"),
    (re.compile(r"^python -m pytest\b"), "pytest"),
    (re.compile(r"^test -f\b"), "file_exists"),
    (re.compile(r"^python docs/zero/schema_check\.py"), "schema_check"),
]


@dataclass
class GateCheck:
    capability: str
    gate_command: str
    test_runner: str
    valid: bool = False
    error: Optional[str] = None


def table_cells(line: str) -> List[str]:
    """Extract cells from a markdown table row."""
    if not line.strip().startswith("|"):
        return []
    stripped = line.strip().strip("|")
    return [c.strip() for c in stripped.split("|")]


def is_separator(cells: List[str]) -> bool:
    """True when a row is the markdown table separator (--- | ---)."""
    return bool(cells) and all(set(c) <= {"-", ":", " "} and c.strip() for c in cells)


def runner_for(command: str) -> Optional[str]:
    for pattern, runner in GATE_RUNNERS:
        if pattern.match(command):
            return runner
    return None


def parse_capabilities_md(path: Path) -> List[GateCheck]:
    """Parse capabilities.md and extract every gate command from table cells."""
    lines = path.read_text(encoding="utf-8").splitlines()
    checks: List[GateCheck] = []
    for line in lines:
        cells = table_cells(line)
        if not cells or is_separator(cells):
            continue
        capability = cells[0] if cells and cells[0] not in ("-", "") else "unknown"
        for cell in cells:
            if not cell or cell == "-":
                continue
            runner = runner_for(cell)
            if runner:
                checks.append(
                    GateCheck(
                        capability=capability,
                        gate_command=cell,
                        test_runner=runner,
                    )
                )
    # Deduplicate by gate command, preserving first-seen order
    seen = set()
    unique: List[GateCheck] = []
    for c in checks:
        if c.gate_command not in seen:
            seen.add(c.gate_command)
            unique.append(c)
    return unique


def extract_cargo_filter(cmd: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract package selector (-p) and test filter from cargo test command.
    Returns (package, test_filter) or (None, None) if not a cargo test command.
    """
    # Match: cargo test [-p package] [filter]
    m = re.search(r"^cargo test\s+(?:-p\s+(\S+)\s+)?(.*)$", cmd)
    if not m:
        return None, None
    package = m.group(1)
    test_filter = m.group(2).strip() if m.group(2) else ""
    return package, test_filter


def vitest_spec(cmd: str) -> Tuple[str, str]:
    m = re.search(r"npx vitest run\s+(\S+)(?:\s+-t\s+\"([^\"]+)\")?", cmd)
    if m:
        return m.group(1), m.group(2) or ""
    return cmd, ""


def pytest_spec(cmd: str) -> str:
    m = re.search(r"python -m pytest\s+(\S+)", cmd)
    return m.group(1).strip() if m else ""


def run_list(runner: str, command: str) -> Tuple[bool, str]:
    """Execute the gate command's list/collect variant and require >=1 match."""
    try:
        if runner == "cargo":
            package, test_filter = extract_cargo_filter(command)
            if package is None:
                return False, f"Invalid cargo test command: {command}"
            cmd = ["cargo", "test", "--list"]
            if package:
                cmd.extend(["-p", package])
            if test_filter:
                cmd.append(test_filter)
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                return False, f"cargo test --list failed: {res.stderr.strip()}"
            if "0 tests" in res.stdout:
                filter_desc = f"-p {package} {test_filter}".strip()
                return False, f"No tests match filter '{filter_desc}'"
            test_lines = [
                l for l in res.stdout.splitlines() if l.strip() and not l.startswith("[")
            ]
            if not test_lines:
                filter_desc = f"-p {package} {test_filter}".strip()
                return False, f"No tests listed for filter '{filter_desc}'"
            return True, f"{len(test_lines)} test(s) listed"

        if runner == "vitest":
            test_file, test_name = vitest_spec(command)
            if test_name:
                cmd = ["npx", "vitest", "run", test_file, "-t", test_name]
            else:
                cmd = ["npx", "vitest", "run", test_file, "--reporter=verbose"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                return False, f"vitest failed for {test_file}: {res.stderr.strip()}"
            return True, "OK"

        if runner == "pytest":
            spec = pytest_spec(command)
            cmd = ["python", "-m", "pytest", "--collect-only", "-q", spec]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                return False, f"pytest --collect-only failed: {res.stderr.strip()}"
            if "no tests collected" in res.stdout.lower():
                return False, f"No tests collected for {spec}"
            return True, "OK"

        if runner == "file_exists":
            m = re.search(r"test -f\s+(\S+)", command)
            if not m:
                return False, "Invalid test -f command"
            p = Path(m.group(1))
            if p.exists():
                return True, "OK"
            return False, f"File does not exist: {p}"

        if runner == "schema_check":
            res = subprocess.run(command.split(), capture_output=True, text=True, timeout=60)
            if res.returncode == 0:
                return True, "OK"
            return False, f"schema_check failed: {res.stderr.strip()}"

        return False, f"Unknown runner: {runner}"
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as exc:  # noqa: BLE001
        return False, f"Validation error: {exc}"


def ci_gate_present(content: str) -> Tuple[bool, str]:
    if "CI Gate" not in content:
        return False, "CI Gate section not found"
    if "capability_gate.py" not in content:
        return False, "capability_gate.py invocation not found"
    if "--check capabilities.md" not in content:
        return False, "--check capabilities.md not found"
    return True, "OK"


def main() -> int:
    if len(sys.argv) < 3 or sys.argv[1] != "--check":
        print("Usage: python zero/capability_gate.py --check <capabilities.md>")
        return 2

    capabilities_path = Path(sys.argv[2])
    if not capabilities_path.exists():
        print(f"ERROR: {capabilities_path} not found")
        return 2

    content = capabilities_path.read_text(encoding="utf-8")

    ci_ok, ci_msg = ci_gate_present(content)
    if not ci_ok:
        print(f"CI GATE CHECK FAILED: {ci_msg}")
        return 1
    print("CI Gate section: PRESENT with capability_gate.py invocation")

    checks = parse_capabilities_md(capabilities_path)
    
    # Fail-closed: empty checks table is a validation failure
    if not checks:
        print("GATE VALIDATION FAILED: No gate commands found in capabilities.md (empty checks table)")
        return 1

    all_valid = True
    for check in checks:
        valid, msg = run_list(check.test_runner, check.gate_command)
        check.valid = valid
        check.error = None if valid else msg
        status = "PASS" if valid else "FAIL"
        print(f"  [{status}] {check.capability}: {check.gate_command}")
        if not valid:
            print(f"         ERROR: {msg}")
            all_valid = False

    if all_valid:
        print("\nALL GATES VALIDATED SUCCESSFULLY")
        return 0
    print("\nGATE VALIDATION FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
