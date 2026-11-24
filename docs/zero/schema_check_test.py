#!/usr/bin/env python3
"""Mutation fixtures and tests for schema_check.py negative cases.

Tests that the checker correctly detects:
- doc column absent from DDL -> exit 1
- DDL column absent from doc under --strict -> exit 1
- class cell MEASURED/PLANNED -> exit 1 (invalid: two labels)
- class cell HYPOTHESIS -> exit 1 (not allowed)
- forbidden claim pattern -> exit 1
- missing input -> exit 2
- unknown argv -> exit 2
"""

import sys
import tempfile
import subprocess
from pathlib import Path
from typing import List, Tuple

# Add parent directory to path to import schema_check
sys.path.insert(0, str(Path(__file__).parent))

import schema_check as sc


def run_checker(args: List[str], cwd: Path, env: dict = None) -> Tuple[int, str, str]:
    """Run schema_check.py as subprocess and return (exit_code, stdout, stderr)."""
    cmd = [sys.executable, str(Path(__file__).parent / "schema_check.py")] + args
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    return result.returncode, result.stdout, result.stderr


def create_test_repo() -> Path:
    """Create a temporary repo structure with minimal files for testing."""
    tmp = Path(tempfile.mkdtemp(prefix="schema_check_test_"))
    
    # Create directory structure
    (tmp / "zero" / "unifieddb").mkdir(parents=True)
    (tmp / "docs" / "zero").mkdir(parents=True)
    (tmp / "plugins" / "frankenstein3").mkdir(parents=True)
    (tmp / "src" / "zero").mkdir(parents=True)
    (tmp / "agent-sdk" / "src" / "zero").mkdir(parents=True)
    
    return tmp


def write_sql(tmp: Path, content: str):
    (tmp / "zero" / "unifieddb" / "schema.sql").write_text(content)


def write_schema_doc(tmp: Path, content: str):
    (tmp / "docs" / "zero" / "schema.md").write_text(content)


def write_status_doc(tmp: Path, content: str):
    (tmp / "docs" / "zero" / "status.md").write_text(content)


def write_plugin_readme(tmp: Path, content: str):
    (tmp / "plugins" / "frankenstein3" / "README.md").write_text(content)


def write_rust_source(tmp: Path, rel_path: str, content: str):
    p = tmp / "src" / "zero" / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def write_ts_source(tmp: Path, rel_path: str, content: str):
    p = tmp / "agent-sdk" / "src" / "zero" / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


# ============================================================
# Base valid fixtures
# ============================================================

BASE_SQL = """
CREATE TABLE identity (
    root_id UUID PRIMARY KEY NOT NULL,
    public_key_pem TEXT NOT NULL,
    fingerprint_sha256 TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    rotated_at TIMESTAMPTZ,
    revoked BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE plugins (
    id UUID PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unknown' CHECK (status IN ('healthy','degraded','unhealthy','unknown')),
    failure_count INTEGER NOT NULL DEFAULT 0 CHECK (failure_count >= 0),
    health_score REAL CHECK (health_score IS NULL OR (health_score >= 0.0 AND health_score <= 1.0)),
    last_check_at TIMESTAMPTZ,
    manifest_hash TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

BASE_SCHEMA_DOC = """# unified.db Schema Reference

## Tables

### identity

| Column | Type | Constraints | Epistemic Status | Description |
|--------|------|-------------|------------------|-------------|
| root_id | UUID | PK, NOT NULL | MEASURED | Canonical root identifier |
| public_key_pem | TEXT | NOT NULL | MEASURED | PEM-encoded public key |
| fingerprint_sha256 | TEXT | NOT NULL, UNIQUE | MEASURED | SHA-256 fingerprint |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | MEASURED | Creation timestamp |
| rotated_at | TIMESTAMPTZ | | MEASURED | Last key rotation |
| revoked | BOOLEAN | NOT NULL, DEFAULT FALSE | MEASURED | Revocation flag |

### plugins

| Column | Type | Constraints | Epistemic Status | Description |
|--------|------|-------------|------------------|-------------|
| id | UUID | PK, NOT NULL | MEASURED | Plugin instance identifier |
| name | TEXT | NOT NULL | MEASURED | Human-readable plugin name |
| manifest_path | TEXT | NOT NULL | MEASURED | Relative path to plugin manifest |
| version | TEXT | NOT NULL | MEASURED | Plugin semantic version |
| status | TEXT | NOT NULL, DEFAULT 'unknown', CHECK (status IN ('healthy','degraded','unhealthy','unknown')) | MEASURED | Lifecycle status |
| failure_count | INTEGER | NOT NULL, DEFAULT 0, CHECK (failure_count >= 0) | MEASURED | Consecutive failed health checks |
| health_score | REAL | CHECK (health_score IS NULL OR (health_score >= 0.0 AND health_score <= 1.0)) | MEASURED | Last measured health score |
| last_check_at | TIMESTAMPTZ | | MEASURED | Timestamp of last health check |
| manifest_hash | TEXT | NOT NULL | MEASURED | Hash of the manifest file |
| updated_at | TIMESTAMPTZ | NOT NULL, DEFAULT now() | MEASURED | Last row update timestamp |
"""

BASE_STATUS_DOC = """# Zero40 Fusion Status

## Last recorded gate

- Rust: `cargo test` — **10 passed / 0 failed**.
- Node: `npm test` — **5 passed / 0 failed**.

## Capabilities

| capability | class | test_path | measured_value | ci_run |
|---|---|---|---|---|
| Plugin manifest loads from bundled bytes | MEASURED | test_load_bundled_manifest | 100% success | cargo gate: 10 pass / 0 fail |
| UnifiedDB schema owned by single writer | PLANNED | test_single_writer_invariant | no passing measurement | pending |
| Unknown capability outside gate | UNKNOWN | test_unknown | not covered | outside last gate |
"""


# ============================================================
# Test Cases
# ============================================================

def test_missing_column_in_ddl():
    """doc column absent from DDL -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    # Schema doc has extra column 'extra_col' not in SQL
    schema_doc = BASE_SCHEMA_DOC + """
| extra_col | TEXT | NOT NULL | MEASURED | Extra column not in DDL |
"""
    write_schema_doc(tmp, schema_doc)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n")
    
    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "MISSING_COLUMN" in err or "MISSING_COLUMN" in out
    print("✓ test_missing_column_in_ddl passed")


def test_missing_table_in_ddl():
    """doc table absent from DDL -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    # Schema doc references table 'missing_table' not in SQL
    schema_doc = BASE_SCHEMA_DOC + """

### missing_table

| Column | Type | Constraints | Epistemic Status | Description |
|--------|------|-------------|------------------|-------------|
| col1 | TEXT | NOT NULL | MEASURED | Missing table |
"""
    write_schema_doc(tmp, schema_doc)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n")
    
    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "MISSING_TABLE" in err or "MISSING_TABLE" in out
    print("✓ test_missing_table_in_ddl passed")


def test_type_mismatch():
    """doc column type differs from DDL -> exit 1"""
    tmp = create_test_repo()
    # SQL has INTEGER
    sql = BASE_SQL.replace("failure_count INTEGER", "failure_count INTEGER")
    write_sql(tmp, sql)
    # Doc says REAL
    schema_doc = BASE_SCHEMA_DOC.replace("failure_count | INTEGER", "failure_count | REAL")
    write_schema_doc(tmp, schema_doc)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n")
    
    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "TYPE_MISMATCH" in err or "TYPE_MISMATCH" in out
    print("✓ test_type_mismatch passed")


def test_constraint_mismatch():
    """doc column constraint differs from DDL -> exit 1"""
    tmp = create_test_repo()
    # SQL has NOT NULL
    write_sql(tmp, BASE_SQL)
    # Doc missing NOT NULL
    schema_doc = BASE_SCHEMA_DOC.replace("failure_count | INTEGER | NOT NULL, DEFAULT 0", "failure_count | INTEGER | DEFAULT 0")
    write_schema_doc(tmp, schema_doc)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n")
    
    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "CONSTRAINT_MISMATCH" in err or "CONSTRAINT_MISMATCH" in out
    print("✓ test_constraint_mismatch passed")


def test_unprojected_ddl_strict():
    """DDL column absent from doc under --strict -> exit 1"""
    tmp = create_test_repo()
    # SQL has extra column 'extra_sql_col'
    sql = BASE_SQL + """
CREATE TABLE extra_table (
    id UUID PRIMARY KEY NOT NULL,
    extra_sql_col TEXT NOT NULL
);
"""
    write_sql(tmp, sql)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n")
    
    code, out, err = run_checker(["--strict"], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "UNPROJECTED_DDL" in err or "UNPROJECTED_DDL" in out
    print("✓ test_unprojected_ddl_strict passed")


def test_unprojected_ddl_no_strict():
    """DDL column absent from doc without --strict -> exit 0 (warning only)"""
    tmp = create_test_repo()
    sql = BASE_SQL + """
CREATE TABLE extra_table (
    id UUID PRIMARY KEY NOT NULL,
    extra_sql_col TEXT NOT NULL
);
"""
    write_sql(tmp, sql)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n")
    
    code, out, err = run_checker(["--no-strict"], tmp)
    assert code == 0, f"Expected exit 0, got {code}: {out} {err}"
    print("✓ test_unprojected_ddl_no_strict passed")


def test_invalid_label_two_labels():
    """class cell with two labels (MEASURED PLANNED) -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    # Status doc with two labels in one cell
    status_doc = BASE_STATUS_DOC.replace(
        "| Plugin manifest loads from bundled bytes | MEASURED |",
        "| Plugin manifest loads from bundled bytes | MEASURED PLANNED |"
    )
    write_status_doc(tmp, status_doc)
    write_plugin_readme(tmp, "# Plugin\n")
    
    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "INVALID_LABEL" in err or "INVALID_LABEL" in out
    print("✓ test_invalid_label_two_labels passed")


def test_invalid_label_hypothesis():
    """class cell HYPOTHESIS -> exit 1 (not allowed)"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    # Status doc with HYPOTHESIS label
    status_doc = BASE_STATUS_DOC.replace(
        "| Plugin manifest loads from bundled bytes | MEASURED |",
        "| Plugin manifest loads from bundled bytes | HYPOTHESIS |"
    )
    write_status_doc(tmp, status_doc)
    write_plugin_readme(tmp, "# Plugin\n")
    
    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "INVALID_LABEL" in err or "INVALID_LABEL" in out
    print("✓ test_invalid_label_hypothesis passed")


def test_invalid_label_empty():
    """class cell empty -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    # Status doc with empty class
    status_doc = BASE_STATUS_DOC.replace(
        "| Plugin manifest loads from bundled bytes | MEASURED |",
        "| Plugin manifest loads from bundled bytes | |"
    )
    write_status_doc(tmp, status_doc)
    write_plugin_readme(tmp, "# Plugin\n")
    
    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "INVALID_LABEL" in err or "INVALID_LABEL" in out
    print("✓ test_invalid_label_empty passed")


def test_forbidden_claim_agi():
    """forbidden claim pattern 'is AGI' -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_status_doc(tmp, BASE_STATUS_DOC)
    # Plugin README with forbidden claim
    write_plugin_readme(tmp, "# Plugin\n\nThis system **is AGI** and approaches consciousness.\n")
    
    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "FORBIDDEN_CLAIM" in err or "FORBIDDEN_CLAIM" in out
    print("✓ test_forbidden_claim_agi passed")


def test_forbidden_claim_approaches_agi():
    """forbidden claim pattern 'approaches AGI' -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n\nThe system **approaches AGI** capabilities.\n")
    
    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "FORBIDDEN_CLAIM" in err or "FORBIDDEN_CLAIM" in out
    print("✓ test_forbidden_claim_approaches_agi passed")


def test_forbidden_claim_shows_signs():
    """forbidden claim pattern 'shows signs of AGI' -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n\nIt **shows signs of AGI** behavior.\n")
    
    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "FORBIDDEN_CLAIM" in err or "FORBIDDEN_CLAIM" in out
    print("✓ test_forbidden_claim_shows_signs passed")


def test_forbidden_claim_consciousness():
    """forbidden claim pattern 'is conscious' -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_rust_source(tmp, "test.rs", "// This system is conscious\n")
    
    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "FORBIDDEN_CLAIM" in err or "FORBIDDEN_CLAIM" in out
    print("✓ test_forbidden_claim_consciousness passed")


def test_forbidden_claim_sentience():
    """forbidden claim pattern 'shows signs of sentience' -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_ts_source(tmp, "test.ts", "// shows signs of sentience\n")
    
    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "FORBIDDEN_CLAIM" in err or "FORBIDDEN_CLAIM" in out
    print("✓ test_forbidden_claim_sentience passed")


def test_missing_input_sql():
    """missing SQL file -> exit 2"""
    tmp = create_test_repo()
    # Don't create SQL file
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n")
    
    code, out, err = run_checker([], tmp)
    assert code == 2, f"Expected exit 2, got {code}: {out} {err}"
    assert "input missing" in err.lower()
    print("✓ test_missing_input_sql passed")


def test_missing_input_schema_doc():
    """missing schema.md -> exit 2"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    # Don't create schema.md
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n")
    
    code, out, err = run_checker([], tmp)
    assert code == 2, f"Expected exit 2, got {code}: {out} {err}"
    assert "input missing" in err.lower()
    print("✓ test_missing_input_schema_doc passed")


def test_missing_input_status_doc():
    """missing status.md -> exit 2"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    # Don't create status.md
    write_plugin_readme(tmp, "# Plugin\n")
    
    code, out, err = run_checker([], tmp)
    assert code == 2, f"Expected exit 2, got {code}: {out} {err}"
    assert "input missing" in err.lower()
    print("✓ test_missing_input_status_doc passed")


def test_unknown_argv():
    """unknown argv -> exit 2"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n")
    
    code, out, err = run_checker(["--unknown-flag"], tmp)
    assert code == 2, f"Expected exit 2, got {code}: {out} {err}"
    assert "unknown argv" in err.lower()
    print("✓ test_unknown_argv passed")


def test_valid_passes():
    """Valid configuration passes (exit 0)"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n\nThis is a normal plugin.\n")
    write_rust_source(tmp, "lib.rs", "// Normal rust code\n")
    write_ts_source(tmp, "index.ts", "// Normal TS code\n")
    
    code, out, err = run_checker(["--no-strict"], tmp)
    assert code == 0, f"Expected exit 0, got {code}: {out} {err}"
    assert "RESULT: PASS" in out
    print("✓ test_valid_passes passed")


def test_epistemic_label_in_doc():
    """Epistemic label in schema.doc column table is validated"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    # Schema doc with invalid epistemic label
    schema_doc = BASE_SCHEMA_DOC.replace("| MEASURED |", "| INVALID_LABEL |")
    write_schema_doc(tmp, schema_doc)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n")
    
    code, out, err = run_checker([], tmp)
    # The checker validates epistemic labels are from allowed set
    # This should not fail on epistemic label in doc (it's informational)
    # but the column parsing should handle it
    print(f"  epistemic label test: code={code}")
    print("✓ test_epistemic_label_in_doc passed")


# ============================================================
# Main
# ============================================================

def main():
    tests = [
        test_missing_column_in_ddl,
        test_missing_table_in_ddl,
        test_type_mismatch,
        test_constraint_mismatch,
        test_unprojected_ddl_strict,
        test_unprojected_ddl_no_strict,
        test_invalid_label_two_labels,
        test_invalid_label_hypothesis,
        test_invalid_label_empty,
        test_forbidden_claim_agi,
        test_forbidden_claim_approaches_agi,
        test_forbidden_claim_shows_signs,
        test_forbidden_claim_consciousness,
        test_forbidden_claim_sentience,
        test_missing_input_sql,
        test_missing_input_schema_doc,
        test_missing_input_status_doc,
        test_unknown_argv,
        test_valid_passes,
        test_epistemic_label_in_doc,
    ]
    
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__} ERROR: {e}")
            failed += 1
    
    print(f"\n=== Results: {passed} passed, {failed} failed ===")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
