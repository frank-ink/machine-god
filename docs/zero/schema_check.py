#!/usr/bin/env python3
"""
Capabilities table schema checker for zero/unifieddb/schema.sql.

Validates the capabilities table contract (seven columns):

    capability, status, promotion_stage, test_path, evidence_ref, gate, tracking_issue

- `evidence_ref` is receipt-or-dash: a receipt reference (`receipt:<id>`), test reference (`test:<name>@<hash>`), or `-`.
- `status` must be one of MEASURED / HYPOTHESIS / UNKNOWN.
- `promotion_stage` and `evidence_ref` are required; a table missing either is rejected.
- Column names and label semantics are validated, not row counts.
- `tracking_issue` values must resolve to existing markdown files/anchors.

Restored validators (1:1 with docs/zero/schema_check.clay):
  - NoUnknownDefault            (CVIR law UNKNOWN != ZERO)
  - LabelExclusive              (exactly one epistemic class per row)
  - FailClosedCapabilitiesTable (fail-closed on missing table)

Usage:
  python3 schema_check.py --strict <path>        # Validate capabilities.md (exit 1 on violation)
  python3 schema_check.py --emit-md              # Generate docs/zero/schema.md projection
  python3 schema_check.py --test                 # Run mutation test fixtures (exit 1 on failure)
  python3 schema_check.py --emit-invariants      # Emit check names for the 1:1 Clay projection check
  python3 schema_check.py --self-test            # Run self-test fixtures for the restored validators
"""

import argparse
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

SCHEMA_SQL_PATH = Path(__file__).parent.parent / "zero" / "unifieddb" / "schema.sql"
MARKDOWN_PATH = Path(__file__).parent / "schema.md"
CAPABILITIES_MD_PATH = Path(__file__).parent / "capabilities.md"
CLAY_PATH = Path(__file__).parent / "schema_check.clay"

CAPABILITIES_TABLE = "capabilities"

EXPECTED_COLUMNS: List[str] = [
    "capability",
    "status",
    "promotion_stage",
    "test_path",
    "evidence_ref",
    "gate",
    "tracking_issue",
]

REQUIRED_COLUMNS: Set[str] = {"promotion_stage", "evidence_ref"}
VALID_STATUSES: Set[str] = {"MEASURED", "HYPOTHESIS", "UNKNOWN"}
EXPECTED_SET: Set[str] = set(EXPECTED_COLUMNS)

# Updated regex: accepts receipt:<id>, test:<name>@<hash> (7-40 hex chars), or -
RECEIPT_OR_DASH = re.compile(r"^(test:[A-Za-z0-9_:.\-]+@[A-Fa-f0-9]{7,40}|receipt:[A-Za-z0-9_.\-]+|-)$")

CVIR_STAGES = [
    'MEASURE', 'FALSIFY', 'MATCHED_ABLATION', 'VERIFIED_OUTCOME',
    'CAUSAL_CREDIT', 'BOUNDED_ADMISSION', 'REENTRY_TEST', 'CONTROL_INFLUENCE'
]

EPISTEMIC_LABELS = ['MEASURED', 'HYPOTHESIS', 'UNKNOWN']

FORBIDDEN_CLAIMS = ['AGI', 'consciousness', 'sentience', 'approaches AGI', 'shows signs of']

REMOVED_COLUMNS = {'measured_value', 'ci_run'}

# Restored check names. Must match docs/zero/schema_check.clay 1:1.
# Alphabetical order == declaration order in the Clay file, so the projection is
# identical whether the emitter preserves declaration order or sorts names.
RESTORED_INVARIANTS: List[str] = [
    "FailClosedCapabilitiesTable",
    "LabelExclusive",
    "NoUnknownDefault",
]

BASE_CAPABILITIES_DDL = """CREATE TABLE capabilities (
    capability TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('MEASURED','HYPOTHESIS','UNKNOWN')),
    promotion_stage TEXT NOT NULL CHECK (promotion_stage IN ('MEASURE','FALSIFY','MATCHED_ABLATION','VERIFIED_OUTCOME','CAUSAL_CREDIT','BOUNDED_ADMISSION','REENTRY_TEST','CONTROL_INFLUENCE')),
    test_path TEXT NOT NULL,
    evidence_ref TEXT NOT NULL CHECK (evidence_ref GLOB 'receipt:*' OR evidence_ref GLOB 'test:*@*' OR evidence_ref = '-'),
    gate TEXT NOT NULL,
    tracking_issue TEXT NOT NULL
) STRICT;"""


def extract_create_table(sql: str, table_name: str) -> Optional[str]:
    """Return the CREATE TABLE ... STRICT ; block for table_name, or None."""
    pattern = re.compile(
        rf'CREATE\s+TABLE\s+{table_name}\s*\((.*?)\)\s*STRICT\s*;',
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(sql)
    if not m:
        return None
    return sql[m.start():m.end()]


def split_columns(body: str) -> List[str]:
    """Split a CREATE TABLE body on top-level commas."""
    parts: List[str] = []
    depth = 0
    cur: List[str] = []
    for ch in body:
        if ch == '(':
            depth += 1
            cur.append(ch)
        elif ch == ')':
            depth -= 1
            cur.append(ch)
        elif ch == ',' and depth == 0:
            parts.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append(''.join(cur).strip())
    return [p for p in parts if p]


def parse_columns(create_sql: str) -> List[Dict[str, str]]:
    """Parse column definitions from a CREATE TABLE statement."""
    m = re.search(r'\((.*)\)\s*STRICT\s*;', create_sql, re.DOTALL | re.IGNORECASE)
    if not m:
        return []
    body = m.group(1)
    columns: List[Dict[str, str]] = []
    for part in split_columns(body):
        upper = part.upper()
        if upper.startswith(('CONSTRAINT', 'PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE', 'CHECK', 'PRAGMA')):
            continue
        tokens = part.split()
        if len(tokens) < 2:
            continue
        columns.append({
            'name': tokens[0],
            'type': tokens[1],
            'constraints': ' '.join(tokens[2:]),
        })
    return columns


def parse_schema(sql: str) -> Dict[str, Any]:
    """Parse all CREATE TABLE statements from schema.sql (cross-reference helper)."""
    tables: Dict[str, Any] = {}
    sql_nocomments = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
    table_pattern = re.compile(
        r'CREATE TABLE\s+(\w+)\s*\((.*?)\)\s*STRICT\s*;',
        re.DOTALL | re.IGNORECASE
    )
    for match in table_pattern.finditer(sql_nocomments):
        table_name = match.group(1)
        columns_sql = match.group(2)
        col_parts = []
        paren_depth = 0
        current: List[str] = []
        for ch in columns_sql:
            if ch == '(':
                paren_depth += 1
                current.append(ch)
            elif ch == ')':
                paren_depth -= 1
                current.append(ch)
            elif ch == ',' and paren_depth == 0:
                col_parts.append(''.join(current).strip())
                current = []
            else:
                current.append(ch)
        if current:
            col_parts.append(''.join(current).strip())
        columns = []
        for col_sql in col_parts:
            col_sql = col_sql.strip()
            if not col_sql:
                continue
            upper = col_sql.upper()
            if upper.startswith(('CONSTRAINT', 'PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE', 'CHECK', 'PRAGMA')):
                continue
            parts = col_sql.split()
            if len(parts) < 2:
                continue
            columns.append({
                'name': parts[0],
                'type': parts[1],
                'constraints': ' '.join(parts[2:]),
            })
        tables[table_name] = {'columns': columns}
    return {'tables': tables}


def get_capabilities_table_body(sql: str) -> Optional[str]:
    """Extract the body (inside parentheses) of the capabilities CREATE TABLE."""
    pattern = re.compile(
        rf'CREATE\s+TABLE\s+{CAPABILITIES_TABLE}\s*\((.*?)\)\s*STRICT\s*;',
        re.DOTALL | re.IGNORECASE,
    )
    m = pattern.search(sql)
    if not m:
        return None
    return sql[m.start():m.end()]


def validate_capabilities_table(create_sql: str) -> List[str]:
    """Validate a capabilities CREATE TABLE DDL string. Returns error messages."""
    errors: List[str] = []
    columns = parse_columns(create_sql)
    col_names = {c['name'] for c in columns}

    # Required columns first
    missing_required = REQUIRED_COLUMNS - col_names
    if missing_required:
        errors.append(f"capabilities: missing required columns: {', '.join(sorted(missing_required))}")

    # Exact column set
    if col_names != EXPECTED_SET:
        extra = col_names - EXPECTED_SET
        missing_exp = EXPECTED_SET - col_names
        if extra:
            errors.append(f"capabilities: unexpected columns: {', '.join(sorted(extra))}")
        if missing_exp:
            errors.append(f"capabilities: missing expected columns: {', '.join(sorted(missing_exp))}")

    # Removed columns must not be present (scoped to capabilities table only)
    removed_present = col_names & REMOVED_COLUMNS
    if removed_present:
        errors.append(f"capabilities: removed columns still present: {', '.join(sorted(removed_present))}")

    # Status CHECK constraint
    status_col = next((c for c in columns if c['name'] == 'status'), None)
    if status_col:
        cons = status_col['constraints'].upper()
        if 'CHECK' not in cons:
            errors.append("capabilities: status column lacks CHECK constraint")
        else:
            for label in VALID_STATUSES:
                if label not in cons:
                    errors.append(f"capabilities: status CHECK constraint missing label: {label}")
    else:
        errors.append("capabilities: status column not found")

    # evidence_ref receipt-or-dash constraint hint
    evidence_col = next((c for c in columns if c['name'] == 'evidence_ref'), None)
    if evidence_col:
        cons = evidence_col['constraints']
        if 'CHECK' in cons.upper():
            low = cons.lower()
            # Check that constraint expresses receipt-or-dash pattern
            if 'receipt' not in low and 'test:' not in low and '-' not in cons:
                errors.append("capabilities: evidence_ref CHECK constraint does not express receipt-or-dash (receipt:*, test:*@*, or -)")
    else:
        errors.append("capabilities: evidence_ref column not found")

    # promotion_stage CHECK constraint (CVIR stages)
    promo_col = next((c for c in columns if c['name'] == 'promotion_stage'), None)
    if promo_col:
        cons = promo_col['constraints'].upper()
        if 'CHECK' not in cons:
            errors.append("capabilities: promotion_stage column lacks CHECK constraint")
    else:
        errors.append("capabilities: promotion_stage column not found")

    return errors


def validate_forbidden_claims_in_capabilities(sql: str) -> List[str]:
    """Scan ONLY the capabilities table body for forbidden claims."""
    errors: List[str] = []
    body = get_capabilities_table_body(sql)
    if body is None:
        return errors
    for claim in FORBIDDEN_CLAIMS:
        if claim.lower() in body.lower():
            errors.append(f"forbidden claim found in capabilities table: {claim}")
    return errors


def validate_removed_columns_in_capabilities(sql: str) -> List[str]:
    """Scan ONLY the capabilities table body for removed columns."""
    errors: List[str] = []
    body = get_capabilities_table_body(sql)
    if body is None:
        return errors
    for col in REMOVED_COLUMNS:
        if re.search(rf'\b{col}\b', body, re.IGNORECASE):
            errors.append(f"removed column '{col}' still referenced in capabilities table")
    return errors


def md_table_rows(path: Path, required_cols: Tuple[str, ...]) -> List[Tuple[int, List[str], Dict[str, int]]]:
    """
    Parse the capabilities markdown table.

    Returns a list of (line_number, cells, column_index_map) for every data row.
    Only rows of a table whose header starts with '| capability' and contains all
    `required_cols` are considered.
    """
    rows: List[Tuple[int, List[str], Dict[str, int]]] = []
    if not path.exists():
        return rows
    content = path.read_text(encoding='utf-8')
    lines = content.split('\n')
    in_table = False
    header_seen = False
    col_indices: Dict[str, int] = {}

    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if (line_stripped.startswith('| capability')
                and all(c in line_stripped for c in required_cols)):
            headers = [h.strip() for h in line_stripped.split('|')[1:-1]]
            col_indices = {h: idx for idx, h in enumerate(headers)}
            header_seen = True
            in_table = True
            continue
        if in_table and line_stripped.startswith('|---'):
            continue
        if in_table and line_stripped.startswith('|') and header_seen:
            cells = [c.strip() for c in line_stripped.split('|')[1:-1]]
            rows.append((i + 1, cells, col_indices))
    return rows


def validate_tracking_issues(capabilities_md_path: Path) -> List[str]:
    """Validate that tracking_issue values in capabilities.md resolve to existing markdown files/anchors."""
    errors: List[str] = []
    if not capabilities_md_path.exists():
        errors.append(f"capabilities.md not found at {capabilities_md_path}")
        return errors

    for line_no, cells, col_indices in md_table_rows(capabilities_md_path, ('tracking_issue',)):
        idx = col_indices.get('tracking_issue', -1)
        if idx < 0 or len(cells) <= idx:
            continue
        tracking_issue = cells[idx]
        if tracking_issue and tracking_issue != '-':
            if not validate_tracking_issue_ref(tracking_issue, capabilities_md_path.parent):
                errors.append(
                    f"capabilities.md line {line_no}: tracking_issue '{tracking_issue}' "
                    "does not resolve to existing markdown file/anchor"
                )
    return errors


def validate_tracking_issue_ref(ref: str, base_dir: Path) -> bool:
    """Check if a tracking_issue reference resolves to an existing markdown file/anchor."""
    # Format: file.md or file.md#anchor or path/to/file.md#anchor
    if '#' in ref:
        file_part, anchor = ref.split('#', 1)
    else:
        file_part, anchor = ref, None

    # Resolve relative to base_dir
    target_path = (base_dir / file_part).resolve()
    try:
        target_path.relative_to(base_dir.resolve())
    except ValueError:
        # Path escapes base_dir
        return False

    if not target_path.exists() or not target_path.is_file():
        return False

    if anchor:
        # Check if anchor exists in the markdown file
        content = target_path.read_text(encoding='utf-8')
        # Look for heading with this anchor (## anchor or # anchor)
        anchor_pattern = rf'^#+\s+{re.escape(anchor)}\b'
        if not re.search(anchor_pattern, content, re.MULTILINE | re.IGNORECASE):
            # Also check for explicit HTML anchor <a name="anchor"> or <a id="anchor">
            html_anchor_pattern = rf'<a\s+(?:name|id)=["\']{re.escape(anchor)}["\']'
            if not re.search(html_anchor_pattern, content, re.IGNORECASE):
                return False
    return True


def validate_evidence_refs_in_capabilities_md(capabilities_md_path: Path) -> List[str]:
    """Validate evidence_ref values in capabilities.md against RECEIPT_OR_DASH regex."""
    errors: List[str] = []
    if not capabilities_md_path.exists():
        return errors

    for line_no, cells, col_indices in md_table_rows(capabilities_md_path, ('evidence_ref',)):
        idx = col_indices.get('evidence_ref', -1)
        if idx < 0 or len(cells) <= idx:
            continue
        evidence_ref = cells[idx]
        if evidence_ref and not RECEIPT_OR_DASH.match(evidence_ref):
            errors.append(
                f"capabilities.md line {line_no}: evidence_ref '{evidence_ref}' does not match "
                "receipt-or-dash pattern (expected receipt:<id>, test:<name>@<hash>, or -)"
            )
    return errors


# =============================================================================
# RESTORED VALIDATORS (1:1 with docs/zero/schema_check.clay)
# =============================================================================

def validate_no_unknown_default(capabilities_md_path: Path) -> List[str]:
    """
    NoUnknownDefault (CVIR law: UNKNOWN != ZERO).

    When status = UNKNOWN, evidence_ref MUST be '-' (no receipt, no test ref).
    No numeric or semantic default may be substituted for UNKNOWN.
    """
    errors: List[str] = []
    if not capabilities_md_path.exists():
        return errors

    for line_no, cells, col_indices in md_table_rows(capabilities_md_path, ('status', 'evidence_ref')):
        status_idx = col_indices.get('status', -1)
        evidence_idx = col_indices.get('evidence_ref', -1)
        if status_idx < 0 or evidence_idx < 0:
            continue
        if len(cells) <= max(status_idx, evidence_idx):
            continue
        status = cells[status_idx]
        evidence_ref = cells[evidence_idx]
        if status == 'UNKNOWN' and evidence_ref != '-':
            errors.append(
                f"capabilities.md line {line_no}: NoUnknownDefault violation — "
                f"status=UNKNOWN but evidence_ref='{evidence_ref}' (must be '-')"
            )
    return errors


def validate_label_exclusive(capabilities_md_path: Path) -> List[str]:
    """
    LabelExclusive (exactly one epistemic class per row).

    Each row must carry exactly one status from {MEASURED, HYPOTHESIS, UNKNOWN},
    and evidence_ref must be consistent with that status:
      MEASURED   -> receipt:* or test:*@* (non-dash)
      HYPOTHESIS -> '-'
      UNKNOWN    -> '-'
    """
    errors: List[str] = []
    if not capabilities_md_path.exists():
        return errors

    for line_no, cells, col_indices in md_table_rows(capabilities_md_path, ('status', 'evidence_ref')):
        status_idx = col_indices.get('status', -1)
        evidence_idx = col_indices.get('evidence_ref', -1)
        if status_idx < 0 or evidence_idx < 0:
            continue
        if len(cells) <= max(status_idx, evidence_idx):
            continue
        status = cells[status_idx]
        evidence_ref = cells[evidence_idx]

        # Exactly one epistemic class per row
        if status not in VALID_STATUSES:
            errors.append(
                f"capabilities.md line {line_no}: LabelExclusive violation — "
                f"invalid status '{status}' (must be exactly one of {sorted(VALID_STATUSES)})"
            )
            continue

        # Evidence consistency with the single declared class
        if status == 'MEASURED':
            if evidence_ref == '-':
                errors.append(
                    f"capabilities.md line {line_no}: LabelExclusive violation — "
                    "status=MEASURED requires non-dash evidence_ref (receipt:* or test:*@*), got '-'"
                )
            elif not RECEIPT_OR_DASH.match(evidence_ref):
                errors.append(
                    f"capabilities.md line {line_no}: LabelExclusive violation — "
                    f"status=MEASURED but evidence_ref='{evidence_ref}' does not match receipt-or-dash pattern"
                )
        else:  # HYPOTHESIS or UNKNOWN
            if evidence_ref != '-':
                errors.append(
                    f"capabilities.md line {line_no}: LabelExclusive violation — "
                    f"status={status} requires evidence_ref='-', got '{evidence_ref}'"
                )
    return errors


def validate_fail_closed_capabilities_table(sql: str) -> List[str]:
    """
    FailClosedCapabilitiesTable (fail-closed on missing table).

    The capabilities table MUST exist in schema.sql.
    Missing table = hard validation failure (exit 1), never a silent pass.
    """
    errors: List[str] = []
    if extract_create_table(sql, CAPABILITIES_TABLE) is None:
        errors.append(
            "FailClosedCapabilitiesTable: capabilities table not defined in schema.sql (fail-closed)"
        )
    return errors


def validate_schema(sql: str) -> List[str]:
    """Validate schema.sql for capabilities-table violations (scoped to capabilities table)."""
    errors: List[str] = []

    # Fail-closed: capabilities table must exist (FailClosedCapabilitiesTable)
    errors.extend(validate_fail_closed_capabilities_table(sql))

    create_sql = extract_create_table(sql, CAPABILITIES_TABLE)
    if create_sql is None:
        return errors  # already reported fail-closed

    # Validate capabilities table structure
    errors.extend(validate_capabilities_table(create_sql))

    # Scan ONLY capabilities table for forbidden claims and removed columns
    errors.extend(validate_forbidden_claims_in_capabilities(sql))
    errors.extend(validate_removed_columns_in_capabilities(sql))

    return errors


def validate_capabilities_md(capabilities_md_path: Path) -> List[str]:
    """Validate capabilities.md against all row-level invariants."""
    errors: List[str] = []
    errors.extend(validate_tracking_issues(capabilities_md_path))
    errors.extend(validate_evidence_refs_in_capabilities_md(capabilities_md_path))
    errors.extend(validate_no_unknown_default(capabilities_md_path))
    errors.extend(validate_label_exclusive(capabilities_md_path))
    return errors


def generate_markdown(parsed: Dict[str, Any]) -> str:
    """Generate markdown projection for the capabilities table."""
    lines: List[str] = []
    lines.append("# Schema Projection — capabilities table")
    lines.append("")
    lines.append("## Source of truth")
    lines.append("")
    lines.append("`zero/unifieddb/schema.sql` is the **only** authoritative DDL. This markdown file is a")
    lines.append("projection generated by `docs/zero/schema_check.py --emit-md` and checked by the same")
    lines.append("script in CI. Never edit this file by hand; edit the SQL and regenerate.")
    lines.append("")
    lines.append("## Capabilities table contract")
    lines.append("")
    lines.append("Seven columns, exact set — no more, no less:")
    lines.append("")
    lines.append("| column | type | constraints | epistemic_label | promotion_stage | description |")
    lines.append("|--------|------|-------------|-----------------|-----------------|-------------|")
    col_descriptions = {
        'capability': 'Capability name from registry',
        'status': 'Epistemic status: MEASURED / HYPOTHESIS / UNKNOWN',
        'promotion_stage': 'CVIR promotion stage',
        'test_path': 'Test file exercising the capability',
        'evidence_ref': 'receipt:<id> or test:<name>@<hash> or - (receipt-or-dash)',
        'gate': 'Command to run the gate',
        'tracking_issue': 'Tracking issue reference (markdown file/anchor)',
    }
    col_labels = {
        'capability': ('MEASURED', 'VERIFIED_OUTCOME'),
        'status': ('MEASURED', 'VERIFIED_OUTCOME'),
        'promotion_stage': ('MEASURED', 'VERIFIED_OUTCOME'),
        'test_path': ('MEASURED', 'MEASURE'),
        'evidence_ref': ('MEASURED', 'MEASURE'),
        'gate': ('MEASURED', 'MEASURE'),
        'tracking_issue': ('MEASURED', 'MEASURE'),
    }
    for col_name in EXPECTED_COLUMNS:
        label, stage = col_labels[col_name]
        lines.append(f"| {col_name} | TEXT | NOT NULL | {label} | {stage} | {col_descriptions[col_name]} |")
    lines.append("")
    lines.append("## Label semantics")
    lines.append("")
    lines.append("| Label | Meaning |")
    lines.append("|-------|---------|")
    lines.append("| MEASURED | Outcome backed by a non-empty `receipt:<id>` or `test:<name>@<hash>` evidence reference. |")
    lines.append("| HYPOTHESIS | Claim under test; `evidence_ref` is `-` and a gate/tracking issue is required. |")
    lines.append("| UNKNOWN | No measurement yet; `evidence_ref` must be `-`. |")
    lines.append("")
    lines.append("## CVIR Promotion Ladder")
    lines.append("")
    lines.append("| Stage | Meaning |")
    lines.append("|-------|---------|")
    meanings = {
        'MEASURE': 'Baseline measurement recorded',
        'FALSIFY': 'Falsification attempt evaluated',
        'MATCHED_ABLATION': 'Matched intervention/control evidence',
        'VERIFIED_OUTCOME': 'Independently verified outcome',
        'CAUSAL_CREDIT': 'Causal attribution substantiated',
        'BOUNDED_ADMISSION': 'Explicit authority and resource bounds',
        'REENTRY_TEST': 'Reentry/replay validation passed',
        'CONTROL_INFLUENCE': 'Bounded control effect verified',
    }
    for i, stage in enumerate(CVIR_STAGES):
        lines.append(f"| {i} | {stage} — {meanings[stage]} |")
    lines.append("")
    lines.append("## Validation Rules (enforced by schema_check.py)")
    lines.append("")
    lines.append("1. **Exact columns**: The capabilities table defines exactly the seven columns above.")
    lines.append("2. **Required columns**: `promotion_stage` and `evidence_ref` must be present; a table missing either is rejected.")
    lines.append("3. **Status label**: `status` CHECK constraint permits only MEASURED, HYPOTHESIS, UNKNOWN.")
    lines.append("4. **Evidence reference**: `evidence_ref` is receipt-or-dash (`receipt:<id>`, `test:<name>@<hash>`, or `-`).")
    lines.append("5. **Removed columns**: columns removed from the previous contract must not appear in capabilities table.")
    lines.append("6. **Label semantics, not row counts**: The checker validates column names and MEASURED/HYPOTHESIS/UNKNOWN label semantics, not the number of rows.")
    lines.append("7. **Forbidden claims**: No \"AGI\", \"consciousness\", \"sentience\", \"approaches AGI\", \"shows signs of\" in capabilities table.")
    lines.append("8. **Tracking issues**: `tracking_issue` values must resolve to existing markdown files/anchors.")
    lines.append("9. **Schema projection match**: This markdown must match `zero/unifieddb/schema.sql` column-for-column.")
    lines.append("")
    lines.append("## Mutation Test Fixtures")
    lines.append("")
    lines.append("| Fixture | Violation | Expected Exit |")
    lines.append("|---------|-----------|---------------|")
    lines.append("| `test_missing_promotion_stage` | capabilities table lacks `promotion_stage` | 1 |")
    lines.append("| `test_missing_evidence_ref` | capabilities table lacks `evidence_ref` | 1 |")
    lines.append("| `test_extra_column` | capabilities table has an unexpected column | 1 |")
    lines.append("| `test_removed_column` | removed columns still present in capabilities table | 1 |")
    lines.append("| `test_invalid_status_label` | status CHECK missing MEASURED/HYPOTHESIS/UNKNOWN | 1 |")
    lines.append("| `test_invalid_evidence_ref` | evidence_ref not receipt-or-dash | 1 |")
    lines.append("| `test_valid_table` | All seven columns present with correct constraints | 0 |")
    lines.append("| `test_forbidden_claim_in_other_table` | FORBIDDEN_CLAIM in unrelated table passes (scoped) | 0 |")
    lines.append("| `test_evidence_ref_test_format` | evidence_ref='test:foo@abc1234' passes regex | 0 |")
    lines.append("")
    return '\n'.join(lines)


def run_strict_check(target_path: Optional[str] = None) -> int:
    """Run strict validation, return exit code. Fail-closed: missing file = error."""
    if target_path:
        # Validate capabilities.md
        target = Path(target_path)
        if not target.exists():
            print(f"ERROR: File not found: {target}", file=sys.stderr)
            return 1

        errors: List[str] = []
        errors.extend(validate_capabilities_md(target))

        if errors:
            for err in errors:
                print(f"ERROR: {err}", file=sys.stderr)
            return 1
        print(f"OK: {target} validation passed")
        return 0

    # Default: validate schema.sql
    if not SCHEMA_SQL_PATH.exists():
        print(f"ERROR: {SCHEMA_SQL_PATH} not found (fail-closed)", file=sys.stderr)
        return 1

    sql = SCHEMA_SQL_PATH.read_text(encoding='utf-8')
    errors = validate_schema(sql)

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    print("OK: capabilities schema validation passed")
    return 0


def run_emit_md() -> int:
    """Generate markdown projection."""
    sql = ""
    if SCHEMA_SQL_PATH.exists():
        sql = SCHEMA_SQL_PATH.read_text(encoding='utf-8')
    parsed: Dict[str, Any] = {'source': sql}
    generated_md = generate_markdown(parsed)
    MARKDOWN_PATH.write_text(generated_md, encoding='utf-8')
    print(f"Generated {MARKDOWN_PATH}")
    return 0


def run_emit_invariants() -> int:
    """
    Emit the restored check names, one per line, alphabetically.

    Output must be byte-identical to `clayc docs/zero/schema_check.clay --emit-invariants`.
    """
    for name in sorted(RESTORED_INVARIANTS):
        print(name)
    return 0


def run_mutation_tests() -> int:
    """Run mutation test fixtures against the capabilities-table validator."""
    tests_passed = 0
    tests_failed = 0

    def check(ddl: str, expect_fail: bool, name: str) -> None:
        nonlocal tests_passed, tests_failed
        errors = validate_capabilities_table(ddl)
        failed = len(errors) > 0
        if expect_fail and failed:
            print(f"PASS: {name} ({errors[0]})")
            tests_passed += 1
        elif not expect_fail and not failed:
            print(f"PASS: {name}")
            tests_passed += 1
        else:
            print(f"FAIL: {name} - errors={errors}")
            tests_failed += 1

    base = BASE_CAPABILITIES_DDL

    # 1. Valid table accepted
    check(base, False, "test_valid_table")

    # 2. Missing promotion_stage
    ddl = base.replace("    promotion_stage TEXT NOT NULL CHECK (promotion_stage IN ('MEASURE','FALSIFY','MATCHED_ABLATION','VERIFIED_OUTCOME','CAUSAL_CREDIT','BOUNDED_ADMISSION','REENTRY_TEST','CONTROL_INFLUENCE')),\n", "")
    check(ddl, True, "test_missing_promotion_stage")

    # 3. Missing evidence_ref
    ddl = base.replace("    evidence_ref TEXT NOT NULL CHECK (evidence_ref GLOB 'receipt:*' OR evidence_ref GLOB 'test:*@*' OR evidence_ref = '-'),\n", "")
    check(ddl, True, "test_missing_evidence_ref")

    # 4. Extra column
    ddl = base.replace(") STRICT;", ",    measured_value REAL NOT NULL) STRICT;")
    check(ddl, True, "test_extra_column")

    # 5. Removed column ci_run in capabilities table
    ddl = base.replace(") STRICT;", ",    ci_run INTEGER NOT NULL DEFAULT 0) STRICT;")
    check(ddl, True, "test_removed_column")

    # 6. Invalid status label (missing UNKNOWN)
    ddl = base.replace("CHECK (status IN ('MEASURED','HYPOTHESIS','UNKNOWN'))", "CHECK (status IN ('MEASURED','HYPOTHESIS'))")
    check(ddl, True, "test_invalid_status_label")

    # 7. Invalid evidence_ref constraint (no receipt-or-dash)
    ddl = base.replace("CHECK (evidence_ref GLOB 'receipt:*' OR evidence_ref GLOB 'test:*@*' OR evidence_ref = '-')", "CHECK (length(evidence_ref) > 0)")
    check(ddl, True, "test_invalid_evidence_ref")

    # 8. Forbidden claim in OTHER table (should PASS - scoped to capabilities only)
    other_table_ddl = """CREATE TABLE other_table (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT CHECK (description NOT LIKE '%AGI%')
) STRICT;"""
    sql_with_other = base + "\n" + other_table_ddl.replace("CHECK (description NOT LIKE '%AGI%')", "CHECK (description LIKE '%AGI%')")
    errors = validate_schema(sql_with_other)
    forbidden_errors = [e for e in errors if 'forbidden claim' in e.lower()]
    if not forbidden_errors:
        print("PASS: test_forbidden_claim_in_other_table (scoped to capabilities only)")
        tests_passed += 1
    else:
        print(f"FAIL: test_forbidden_claim_in_other_table - errors={forbidden_errors}")
        tests_failed += 1

    # 9. evidence_ref='test:foo@abc1234' passes regex
    if RECEIPT_OR_DASH.match("test:foo@abc1234"):
        print("PASS: test_evidence_ref_test_format (regex accepts test:foo@abc1234)")
        tests_passed += 1
    else:
        print("FAIL: test_evidence_ref_test_format (regex rejects test:foo@abc1234)")
        tests_failed += 1

    # 10. Fail-closed: missing capabilities table
    sql_no_caps = """CREATE TABLE other_table (id INTEGER PRIMARY KEY) STRICT;"""
    errors = validate_schema(sql_no_caps)
    if any('capabilities table not defined' in e for e in errors):
        print("PASS: test_missing_capabilities_table_fail_closed")
        tests_passed += 1
    else:
        print(f"FAIL: test_missing_capabilities_table_fail_closed - errors={errors}")
        tests_failed += 1

    print(f"\nMutation tests: {tests_passed} passed, {tests_failed} failed")
    return 0 if tests_failed == 0 else 1


def _write_fixture(dirpath: Path, name: str, content: str) -> Path:
    path = dirpath / name
    path.write_text(content, encoding='utf-8')
    return path


def run_self_test() -> int:
    """
    Self-test: run the checker against fixture documents that violate each
    restored invariant and confirm rejection (plus positive controls).
    """
    passed = 0
    failed = 0

    def expect(name: str, condition: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"PASS: {name}")
        else:
            failed += 1
            suffix = f" - {detail}" if detail else ""
            print(f"FAIL: {name}{suffix}")

    header = "| capability | status | promotion_stage | test_path | evidence_ref | gate | tracking_issue |"
    separator = "|---|---|---|---|---|---|---|"

    def md(*rows: str) -> str:
        return "\n".join([header, separator, *rows]) + "\n"

    valid_rows = [
        "| alpha | MEASURED | MEASURE | t.py | receipt:abc123 | cmd | - |",
        "| beta | HYPOTHESIS | MEASURE | t.py | - | cmd | - |",
        "| gamma | UNKNOWN | MEASURE | t.py | - | cmd | - |",
    ]
    unknown_default_row = "| delta | UNKNOWN | MEASURE | t.py | receipt:abc123 | cmd | - |"
    label_exclusive_row = "| epsilon | MEASURED | MEASURE | t.py | - | cmd | - |"
    multi_label_row = "| zeta | MEASURED+HYPOTHESIS | MEASURE | t.py | receipt:abc123 | cmd | - |"

    with tempfile.TemporaryDirectory(prefix="schema_check_selftest_") as tmp:
        d = Path(tmp)
        valid_md = _write_fixture(d, "valid.md", md(*valid_rows))
        unknown_md = _write_fixture(d, "unknown_default.md", md(*valid_rows, unknown_default_row))
        label_md = _write_fixture(d, "label_exclusive.md", md(*valid_rows, label_exclusive_row))
        multi_label_md = _write_fixture(d, "multi_label.md", md(*valid_rows, multi_label_row))

        # --- NoUnknownDefault -------------------------------------------------
        errs = validate_no_unknown_default(unknown_md)
        expect("test_no_unknown_default_rejects_fixture", len(errs) > 0, f"errors={errs}")
        expect("test_no_unknown_default_accepts_valid", not validate_no_unknown_default(valid_md))
        expect(
            "test_no_unknown_default_rejected_by_capabilities_md",
            len(validate_capabilities_md(unknown_md)) > 0,
        )

        # --- LabelExclusive ---------------------------------------------------
        errs = validate_label_exclusive(label_md)
        expect("test_label_exclusive_rejects_fixture", len(errs) > 0, f"errors={errs}")
        errs_multi = validate_label_exclusive(multi_label_md)
        expect("test_label_exclusive_rejects_multi_label", len(errs_multi) > 0, f"errors={errs_multi}")
        expect("test_label_exclusive_accepts_valid", not validate_label_exclusive(valid_md))
        expect(
            "test_label_exclusive_rejected_by_capabilities_md",
            len(validate_capabilities_md(label_md)) > 0,
        )

        # --- FailClosedCapabilitiesTable --------------------------------------
        sql_missing = "CREATE TABLE other_table (id INTEGER PRIMARY KEY) STRICT;"
        errs = validate_fail_closed_capabilities_table(sql_missing)
        expect("test_fail_closed_capabilities_table_rejects_fixture", len(errs) > 0, f"errors={errs}")
        expect(
            "test_fail_closed_capabilities_table_accepts_present",
            not validate_fail_closed_capabilities_table(BASE_CAPABILITIES_DDL),
        )
        expect(
            "test_fail_closed_reported_by_validate_schema",
            any('FailClosedCapabilitiesTable' in e for e in validate_schema(sql_missing)),
        )

    # --- 1:1 Clay projection -------------------------------------------------
    clay_names: List[str] = []
    if CLAY_PATH.exists():
        clay_text = CLAY_PATH.read_text(encoding='utf-8')
        clay_names = re.findall(
            r'^\s*invariant\s+([A-Za-z_][A-Za-z0-9_]*)\s*\{',
            clay_text,
            re.MULTILINE,
        )
    expect("test_clay_file_present", bool(clay_names), f"path={CLAY_PATH}")
    expect(
        "test_clay_invariant_set_matches_python",
        sorted(clay_names) == sorted(RESTORED_INVARIANTS),
        f"clay={sorted(clay_names)} python={sorted(RESTORED_INVARIANTS)}",
    )
    expect(
        "test_clay_invariant_order_is_alphabetical",
        clay_names == sorted(clay_names),
        f"clay={clay_names}",
    )
    expect(
        "test_emit_invariants_matches_clay",
        sorted(RESTORED_INVARIANTS) == sorted(clay_names),
    )

    print(f"\nSelf-test: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


def main():
    parser = argparse.ArgumentParser(description="Capabilities schema validation and projection tool")
    parser.add_argument("--emit-md", action="store_true", help="Generate markdown projection")
    parser.add_argument("--strict", nargs='?', const=True, default=None, help="Validate schema or capabilities.md (exit 1 on violation)")
    parser.add_argument("--test", action="store_true", help="Run mutation test fixtures")
    parser.add_argument("--emit-invariants", action="store_true", help="Emit restored check names (1:1 Clay projection check)")
    parser.add_argument("--self-test", action="store_true", help="Run self-test fixtures for the restored validators")
    args = parser.parse_args()

    if args.emit_md:
        return run_emit_md()
    elif args.emit_invariants:
        return run_emit_invariants()
    elif args.self_test:
        return run_self_test()
    elif args.test:
        return run_mutation_tests()
    elif args.strict is not None:
        # --strict with optional argument
        target = args.strict if isinstance(args.strict, str) else None
        return run_strict_check(target)
    else:
        # Default: strict validation of schema.sql
        return run_strict_check()


if __name__ == "__main__":
    sys.exit(main())
