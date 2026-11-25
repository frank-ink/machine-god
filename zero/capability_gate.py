#!/usr/bin/env python3
"""
Capability Gate Validator (GRF / ClayCode)

State authority: docs/zero/capabilities.md
Transition: parse -> extract_gates -> execute_list -> admit_or_reject
Invariant: GATE_NON_EMPTY (every gate resolves to >=1 listed test)
Invariant: RUNNER_KNOWN (every gate command maps to a known runner)
Invariant: REQUIRED_COLUMNS (header must contain exactly the 7 canonical columns)
Invariant: EVIDENCE_REF_FORMAT (evidence_ref is receipt id or dash, never test path)
Invariant: TRACKING_ISSUE_FORMAT (tracking_issue is issue id, file path with optional anchor, or dash)
Invariant: TRACKING_ISSUE_RESOLVES (non-empty tracking_issue must point to existing file/anchor or valid issue id)
Invariant: NO_MEASURED_VALUE_CI_RUN (columns measured_value and ci_run must not exist)
Invariant: SINGLE_CLI_CONTRACT (capabilities.md advertises exactly one canonical CLI contract)
ON_VIOLATION -> exit non-zero (fail-closed)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple, Set, Iterator, Union, overload, Any

# Canonical columns - exactly these seven, no more, no less
CANONICAL_COLUMNS = [
    "capability",
    "status",
    "evidence_ref",
    "gate",
    "tracking_issue",
    "promotion_stage",
    "description",
]

REQUIRED_COLUMNS: Set[str] = set(CANONICAL_COLUMNS)

FORBIDDEN_COLUMNS: Set[str] = {"measured_value", "ci_run", "test_path"}

GATE_RUNNERS = [
    (re.compile(r"^cargo test\b"), "cargo"),
    (re.compile(r"^npx vitest run\b"), "vitest"),
    (re.compile(r"^python -m pytest\b"), "pytest"),
    (re.compile(r"^test -f\b"), "file_exists"),
    (re.compile(r"^python docs/zero/schema_check\.py"), "schema_check"),
]

# Tracking issue patterns
ISSUE_ID_PATTERN = re.compile(r"^[A-Z]+-\d+$")
FILE_PATH_PATTERN = re.compile(r"^([a-zA-Z0-9_\-./]+)(?:#([a-zA-Z0-9_\-]+))?$")


@dataclass
class GateCheck:
    capability: str
    gate_command: str
    test_runner: Optional[str]
    valid: bool = False
    error: Optional[str] = None
    test_count: int = 0


@dataclass
class ParseResult:
    checks: List[GateCheck] = field(default_factory=list)
    unknown_gates: List[GateCheck] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    cli_contract_count: int = 0
    tracking_issue_errors: List[str] = field(default_factory=list)

    def __iter__(self) -> Iterator[GateCheck]:
        return iter(self.checks)

    def __len__(self) -> int:
        return len(self.checks)

    def __bool__(self) -> bool:
        return bool(self.checks)

    @overload
    def __getitem__(self, index: int) -> GateCheck: ...
    @overload
    def __getitem__(self, index: slice) -> List[GateCheck]: ...

    def __getitem__(self, index: Union[int, slice]) -> Union[GateCheck, List[GateCheck]]:
        return self.checks[index]

    def __repr__(self) -> str:
        return f"ParseResult(checks={len(self.checks)}, unknown_gates={len(self.unknown_gates)}, errors={len(self.errors)}, tracking_issue_errors={len(self.tracking_issue_errors)})"


def table_cells(line: str) -> List[str]:
    """Extract cells from a markdown table row."""
    if not line.strip().startswith("|"):
        return []
    stripped = line.strip().strip("|")
    return [c.strip() for c in stripped.split("|")]


def is_separator(cells: List[str]) -> bool:
    """True when a row is the markdown table separator (--- | ---)."""
    return bool(cells) and all(set(c) <= {"-", ":", " "} and c.strip() for c in cells)


def is_table_boundary(line: str) -> bool:
    """True when line ends the table (blank or non-pipe line)."""
    stripped = line.strip()
    return not stripped or not stripped.startswith("|")


def find_capabilities_table(lines: List[str]) -> Tuple[Optional[int], Optional[List[str]]]:
    """
    Locate the capabilities table by required columns.
    Returns (header_row_index, header_cells) or (None, None) if not found.
    """
    for idx, line in enumerate(lines):
        cells = table_cells(line)
        if not cells or is_separator(cells):
            continue
        header_set = set(cells)
        if REQUIRED_COLUMNS.issubset(header_set):
            return idx, cells
    return None, None


def normalize_placeholder(value: str) -> str:
    """Map placeholder '-' to 'unknown' for capability/gate."""
    v = value.strip()
    return "unknown" if v == "-" or v == "" else v


def runner_for(command: str) -> Optional[str]:
    for pattern, runner in GATE_RUNNERS:
        if pattern.match(command):
            return runner
    return None


def validate_header(header: List[str]) -> List[str]:
    """Validate header contains exactly canonical columns, no forbidden columns."""
    errors = []
    header_set = set(header)
    
    # Check required columns present
    missing = REQUIRED_COLUMNS - header_set
    if missing:
        errors.append(f"Missing required columns: {sorted(missing)}")
    
    # Check no forbidden columns
    forbidden_present = FORBIDDEN_COLUMNS & header_set
    if forbidden_present:
        errors.append(f"Forbidden columns present: {sorted(forbidden_present)}")
    
    # Check no extra columns beyond canonical
    extra = header_set - REQUIRED_COLUMNS
    if extra:
        errors.append(f"Extra columns not in canonical schema: {sorted(extra)}")
    
    return errors


def validate_evidence_ref(evidence_ref: str, capability: str) -> List[str]:
    """Validate evidence_ref is receipt id or dash."""
    errors = []
    v = evidence_ref.strip()
    if v == "-" or v == "":
        return errors
    # Receipt format: test:<name>@<commit> or similar receipt id
    if not re.match(r"^(test:[^@]+@[a-f0-9]{7,40}|[a-z]+-[a-f0-9]{7,40})$", v):
        errors.append(f"capability '{capability}': evidence_ref must be receipt id (test:<name>@<commit>) or dash, got: {v}")
    return errors


def validate_tracking_issue_format(tracking_issue: str, capability: str) -> List[str]:
    """Validate tracking_issue format: issue id (GH-123), file path (docs/foo.md), file path with anchor (docs/foo.md#section), or dash."""
    errors = []
    v = tracking_issue.strip()
    if v == "-" or v == "":
        return errors
    # Issue ID format: GH-123, JIRA-456, etc.
    if ISSUE_ID_PATTERN.match(v):
        return errors
    # File path with optional anchor
    m = FILE_PATH_PATTERN.match(v)
    if m:
        return errors
    errors.append(f"capability '{capability}': tracking_issue must be issue id (e.g., GH-123), file path (e.g., docs/zero/architecture.md), file path with anchor (e.g., docs/zero/architecture.md#section), or dash, got: {v}")
    return errors


def resolve_tracking_issue(tracking_issue: str, capability: str, base_path: Path) -> List[str]:
    """
    Resolve tracking_issue against live filesystem.
    - Issue IDs (GH-123): format only, cannot verify remotely
    - File paths: verify file exists
    - File paths with anchors: verify file exists and anchor exists in file
    """
    errors = []
    v = tracking_issue.strip()
    if v == "-" or v == "":
        return errors
    
    # Issue ID - format validated already, cannot resolve remotely
    if ISSUE_ID_PATTERN.match(v):
        return errors
    
    # File path with optional anchor
    m = FILE_PATH_PATTERN.match(v)
    if not m:
        return errors  # Format error already caught
    
    file_path_str, anchor = m.groups()
    file_path = (base_path / file_path_str).resolve()
    
    # Security: ensure resolved path is within base_path (no directory traversal)
    try:
        file_path.relative_to(base_path.resolve())
    except ValueError:
        errors.append(f"capability '{capability}': tracking_issue file path escapes base directory: {file_path_str}")
        return errors
    
    if not file_path.exists():
        errors.append(f"capability '{capability}': tracking_issue file does not exist: {file_path_str}")
        return errors
    
    if not file_path.is_file():
        errors.append(f"capability '{capability}': tracking_issue path is not a file: {file_path_str}")
        return errors
    
    # Validate anchor if present
    if anchor:
        anchor_errors = validate_anchor_in_file(file_path, anchor, capability)
        errors.extend(anchor_errors)
    
    return errors


def validate_anchor_in_file(file_path: Path, anchor: str, capability: str) -> List[str]:
    """Check if a markdown anchor exists in the file."""
    errors = []
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        errors.append(f"capability '{capability}': cannot read tracking_issue file {file_path}: {e}")
        return errors
    
    # Generate expected anchor from headers
    # GitHub-style: ## Header Text -> #header-text
    # We check for any header that would generate this anchor
    found = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            # Count header level
            level = 0
            for ch in stripped:
                if ch == "#":
                    level += 1
                else:
                    break
            if level >= 1 and level <= 6:
                header_text = stripped[level:].strip()
                # Generate anchor: lowercase, spaces/hyphens normalized, special chars removed
                generated_anchor = re.sub(r"[^\w\s-]", "", header_text).strip().lower()
                generated_anchor = re.sub(r"[\s-]+", "-", generated_anchor)
                if generated_anchor == anchor.lower():
                    found = True
                    break
    
    if not found:
        errors.append(f"capability '{capability}': anchor '#{anchor}' not found in {file_path}")
    
    return errors


def parse_capabilities_md(path: Path) -> ParseResult:
    """
    Parse capabilities.md and extract every gate command from the 'gate' column.
    
    - Locates table by required columns (7 canonical columns)
    - Stops at table boundary (blank/non-pipe line)
    - Emits exactly one GateCheck per non-empty gate cell with known runner
    - Validates evidence_ref and tracking_issue format
    - Counts CLI contract advertisements
    - Fail-closed: any validation error -> parse error
    """
    result = ParseResult()
    lines = path.read_text(encoding="utf-8").splitlines()

    start, header = find_capabilities_table(lines)
    if start is None or header is None:
        result.errors.append("No capabilities table found with required columns: capability, status, evidence_ref, gate, tracking_issue, promotion_stage, description")
        return result

    # Validate header
    header_errors = validate_header(header)
    result.errors.extend(header_errors)
    if header_errors:
        return result

    # Get column indices
    try:
        cap_idx = header.index("capability")
        gate_idx = header.index("gate")
        status_idx = header.index("status")
        evidence_idx = header.index("evidence_ref")
        tracking_idx = header.index("tracking_issue")
        promotion_idx = header.index("promotion_stage")
        desc_idx = header.index("description")
    except ValueError as e:
        result.errors.append(f"Required column missing from header: {e}")
        return result

    # Parse rows until table boundary
    for line in lines[start + 1:]:
        if is_table_boundary(line):
            break
        cells = table_cells(line)
        if not cells or is_separator(cells):
            continue

        # Extract capability
        capability = "unknown"
        if cap_idx < len(cells):
            capability = normalize_placeholder(cells[cap_idx])
        else:
            capability = "unknown"

        # Extract status
        status = "UNKNOWN"
        if status_idx < len(cells):
            status = cells[status_idx].strip().upper()

        # Extract evidence_ref
        evidence_ref = "-"
        if evidence_idx < len(cells):
            evidence_ref = cells[evidence_idx].strip()
        result.errors.extend(validate_evidence_ref(evidence_ref, capability))

        # Extract tracking_issue
        tracking_issue = "-"
        if tracking_idx < len(cells):
            tracking_issue = cells[tracking_idx].strip()
        result.errors.extend(validate_tracking_issue_format(tracking_issue, capability))

        # Extract promotion_stage (optional, for completeness)
        promotion_stage = ""
        if promotion_idx < len(cells):
            promotion_stage = cells[promotion_idx].strip()

        # Extract description (optional, for completeness)
        description = ""
        if desc_idx < len(cells):
            description = cells[desc_idx].strip()

        # Extract gate command
        if gate_idx >= len(cells):
            # Missing gate column - only error for MEASURED
            if status == "MEASURED":
                result.errors.append(f"MEASURED row missing gate column: capability={capability}")
            continue

        gate_cell = cells[gate_idx]
        gate_command = normalize_placeholder(gate_cell)

        # '-' placeholder -> 'unknown' and dropped (not a check)
        if gate_command == "unknown":
            continue

        runner = runner_for(gate_command)
        check = GateCheck(
            capability=capability,
            gate_command=gate_command,
            test_runner=runner,
        )

        if runner is None:
            check.error = f"Unknown runner for gate command: {gate_command}"
            result.unknown_gates.append(check)
        else:
            result.checks.append(check)

    # Count CLI contract advertisements in the document
    content = "\n".join(lines)
    # Look for the canonical CLI contract pattern (both python and python3)
    cli_pattern = r"python3? zero/capability_gate\.py --check docs/zero/capabilities\.md"
    result.cli_contract_count = len(re.findall(cli_pattern, content))

    return result


def extract_cargo_filter(cmd: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract package selector (-p) and test filter from cargo test command.
    Returns (package, test_filter) or (None, None) for non-cargo commands.
    """
    m = re.match(r"^cargo test(?:\s+-p\s+(\S+))?(?:\s+(.*))?$", cmd)
    if not m:
        return None, None
    package = m.group(1)
    test_filter = (m.group(2) or "").strip()
    return package, test_filter


def vitest_spec(cmd: str) -> Tuple[str, str]:
    m = re.search(r"npx vitest run\s+(\S+)(?:\s+-t\s+\"([^\"]+)\")?", cmd)
    if m:
        return m.group(1), m.group(2) or ""
    return cmd, ""


def pytest_spec(cmd: str) -> str:
    m = re.search(r"python -m pytest\s+(\S+)", cmd)
    return m.group(1).strip() if m else ""


def run_list(runner: str, command: str) -> Tuple[bool, str, int]:
    """
    Execute the gate command's list/collect variant and require >=1 match.
    Returns (has_tests, message, test_count).
    """
    try:
        if runner == "cargo":
            package, test_filter = extract_cargo_filter(command)
            if package is None and test_filter is None:
                return False, f"Invalid cargo test command: {command}", 0
            cmd = ["cargo", "test", "--list"]
            if package:
                cmd.extend(["-p", package])
            if test_filter:
                cmd.append(test_filter)
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                return False, f"cargo test --list failed: {res.stderr.strip()}", 0
            # Count test lines (non-empty, not starting with [)
            test_lines = [
                l for l in res.stdout.splitlines() 
                if l.strip() and not l.startswith("[")
            ]
            count = len(test_lines)
            if count == 0:
                filter_desc = f"-p {package} {test_filter}".strip()
                return False, f"No tests match filter '{filter_desc}'", 0
            return True, f"{count} test(s) listed", count

        if runner == "vitest":
            test_file, test_name = vitest_spec(command)
            # Use --reporter=json for machine-readable output
            if test_name:
                cmd = ["npx", "vitest", "run", test_file, "-t", test_name, "--reporter=json"]
            else:
                cmd = ["npx", "vitest", "run", test_file, "--reporter=json"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                # vitest returns non-zero when tests fail, but we only care about test discovery
                # Check stderr for "no tests found" pattern
                if "no tests found" in res.stderr.lower() or "no tests found" in res.stdout.lower():
                    return False, f"No tests found for {test_file}", 0
                # Try to parse JSON output for test count
                try:
                    data = json.loads(res.stdout)
                    count = count_vitest_tests(data)
                    if count > 0:
                        return True, f"{count} test(s) found", count
                except json.JSONDecodeError:
                    pass
                return False, f"vitest failed for {test_file}: {res.stderr.strip()}", 0
            try:
                data = json.loads(res.stdout)
                count = count_vitest_tests(data)
                if count == 0:
                    return False, f"No tests found for {test_file}", 0
                return True, f"{count} test(s) found", count
            except json.JSONDecodeError:
                return False, f"vitest output not parseable as JSON", 0

        if runner == "pytest":
            spec = pytest_spec(command)
            cmd = ["python", "-m", "pytest", "--collect-only", "-q", spec]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if res.returncode != 0:
                return False, f"pytest --collect-only failed: {res.stderr.strip()}", 0
            if "no tests collected" in res.stdout.lower():
                return False, f"No tests collected for {spec}", 0
            # Count collected tests (lines with ::)
            test_lines = [l for l in res.stdout.splitlines() if "::" in l and not l.startswith("=")]
            count = len(test_lines)
            if count == 0:
                return False, f"No tests collected for {spec}", 0
            return True, f"{count} test(s) collected", count

        if runner == "file_exists":
            m = re.search(r"test -f\s+(\S+)", command)
            if not m:
                return False, "Invalid test -f command", 0
            p = Path(m.group(1))
            if p.exists():
                return True, "OK", 1
            return False, f"File does not exist: {p}", 0

        if runner == "schema_check":
            res = subprocess.run(command.split(), capture_output=True, text=True, timeout=60)
            if res.returncode == 0:
                return True, "OK", 1
            return False, f"schema_check failed: {res.stderr.strip()}", 0

        return False, f"Unknown runner: {runner}", 0
    except subprocess.TimeoutExpired:
        return False, "Command timed out", 0
    except Exception as exc:  # noqa: BLE001
        return False, f"Validation error: {exc}", 0


def count_vitest_tests(data: Any) -> int:
    """Count tests from vitest JSON reporter output."""
    count = 0
    if isinstance(data, dict):
        if "numTotalTests" in data and isinstance(data["numTotalTests"], int):
            return data["numTotalTests"]
        if "testFiles" in data and isinstance(data["testFiles"], list):
            for tf in data["testFiles"]:
                count += count_vitest_tests(tf)
    elif isinstance(data, list):
        for item in data:
            count += count_vitest_tests(item)
    return count


def current_commit_sha() -> str:
    """Best-effort local commit SHA; 'none' when git is unavailable."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()[:12]
    except Exception:
        pass
    return "none"


def build_gate_receipt(
    checks: List[GateCheck],
    errors: List[str],
    unknown_gates: List[GateCheck],
    tracking_issue_errors: List[str],
) -> dict:
    """Build a machine-readable gate receipt dict."""
    pass_count = sum(1 for c in checks if c.valid)
    fail_count = sum(1 for c in checks if not c.valid)
    all_errors = errors + tracking_issue_errors
    exit_code = 0 if (not all_errors and not unknown_gates and fail_count == 0 and checks) else 1
    return {
        "schema": "zero.gate_receipt.v1",
        "commit_sha": current_commit_sha(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "runner": "capability_gate.py",
        "exit_code": exit_code,
        "test_counts": {"pass": pass_count, "fail": fail_count, "total": len(checks)},
        "errors": all_errors,
        "unknown_gates": [
            {"capability": ug.capability, "gate": ug.gate_command, "error": ug.error}
            for ug in unknown_gates
        ],
        "gates": [
            {
                "capability": c.capability,
                "gate": c.gate_command,
                "runner": c.test_runner,
                "test_count": c.test_count,
                "result": "PASS" if c.valid else "FAIL",
                "receipt": c.error or ("OK" if c.valid else "FAILED"),
            }
            for c in checks
        ],
    }


def validate_single_cli_contract(result: ParseResult) -> List[str]:
    """Validate exactly one canonical CLI contract is advertised."""
    errors = []
    if result.cli_contract_count == 0:
        errors.append("SINGLE_CLI_CONTRACT violation: No canonical CLI contract found (expected: 'python3 zero/capability_gate.py --check docs/zero/capabilities.md')")
    elif result.cli_contract_count > 1:
        errors.append(f"SINGLE_CLI_CONTRACT violation: Multiple ({result.cli_contract_count}) canonical CLI contracts found, expected exactly one")
    return errors


def main() -> int:
    # --json [capabilities.md] -> machine-readable gate receipt
    if len(sys.argv) >= 2 and sys.argv[1] == "--json":
        capabilities_path = Path(sys.argv[2]) if len(sys.argv) >= 3 else Path("docs/zero/capabilities.md")
        if not capabilities_path.exists():
            receipt = build_gate_receipt([], [f"{capabilities_path} not found"], [], [])
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
            return 2
        result = parse_capabilities_md(capabilities_path)
        
        # Validate CLI contract count
        cli_errors = validate_single_cli_contract(result)
        result.errors.extend(cli_errors)
        
        all_valid = True
        for check in result.checks:
            valid, msg, count = run_list(check.test_runner, check.gate_command)
            check.valid = valid
            check.error = None if valid else msg
            check.test_count = count
            if not valid:
                all_valid = False
        
        receipt = build_gate_receipt(result.checks, result.errors, result.unknown_gates, result.tracking_issue_errors)
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return 0 if (all_valid and not result.errors and not result.unknown_gates and not result.tracking_issue_errors and result.checks) else 1

    # --check <capabilities.md> -> human-readable validation
    if len(sys.argv) < 3 or sys.argv[1] != "--check":
        print("Usage: python3 zero/capability_gate.py --check <capabilities.md>")
        print("       python3 zero/capability_gate.py --json [capabilities.md]")
        return 2

    capabilities_path = Path(sys.argv[2])
    if not capabilities_path.exists():
        print(f"ERROR: {capabilities_path} not found")
        return 2

    result = parse_capabilities_md(capabilities_path)

    # Validate CLI contract count
    cli_errors = validate_single_cli_contract(result)
    result.errors.extend(cli_errors)

    # Resolve tracking_issue against live filesystem
    base_path = capabilities_path.parent
    lines = capabilities_path.read_text(encoding="utf-8").splitlines()
    start, header = find_capabilities_table(lines)
    if start is not None and header is not None:
        try:
            cap_idx = header.index("capability")
            tracking_idx = header.index("tracking_issue")
            status_idx = header.index("status")
            gate_idx = header.index("gate")
            for line in lines[start + 1:]:
                if is_table_boundary(line):
                    break
                cells = table_cells(line)
                if not cells or is_separator(cells):
                    continue
                capability = "unknown"
                if cap_idx < len(cells):
                    capability = normalize_placeholder(cells[cap_idx])
                tracking_issue = "-"
                if tracking_idx < len(cells):
                    tracking_issue = cells[tracking_idx].strip()
                status = "UNKNOWN"
                if status_idx < len(cells):
                    status = cells[status_idx].strip().upper()
                gate_command = "-"
                if gate_idx < len(cells):
                    gate_command = normalize_placeholder(cells[gate_idx])
                # Only validate tracking_issue for rows that have gates (MEASURED or HYPOTHESIS with gate)
                # But validate all non-dash tracking_issues
                if tracking_issue != "-" and tracking_issue != "":
                    result.tracking_issue_errors.extend(resolve_tracking_issue(tracking_issue, capability, base_path))
        except ValueError:
            pass  # Column indices not found, errors already captured

    # Fail-closed: any parsing errors are validation failures
    if result.errors:
        for err in result.errors:
            print(f"PARSE ERROR: {err}")
        return 1

    # Fail-closed: tracking_issue resolution errors
    if result.tracking_issue_errors:
        for err in result.tracking_issue_errors:
            print(f"TRACKING_ISSUE ERROR: {err}")
        return 1

    # Fail-closed: unknown gates are validation failures
    if result.unknown_gates:
        for ug in result.unknown_gates:
            print(f"UNKNOWN RUNNER: capability={ug.capability} gate={ug.gate_command} error={ug.error}")
        return 1

    # Fail-closed: empty checks table is a validation failure
    if not result.checks:
        print("GATE VALIDATION FAILED: No gate commands found in capabilities.md (empty checks table)")
        return 1

    all_valid = True
    for idx, check in enumerate(result.checks, start=1):
        valid, msg, count = run_list(check.test_runner, check.gate_command)
        check.valid = valid
        check.error = None if valid else msg
        check.test_count = count
        test_id = f"gate-{idx:04d}"
        record = {
            "capability": check.capability,
            "gate": check.gate_command,
            "test_id": test_id,
            "test_count": count,
            "result": "PASS" if valid else "FAIL",
            "receipt": msg,
        }
        print(json.dumps(record, ensure_ascii=False))
        if not valid:
            all_valid = False

    if all_valid:
        print("\nALL GATES VALIDATED SUCCESSFULLY")
        return 0
    print("\nGATE VALIDATION FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
