#!/usr/bin/env python3
"""Schema checker tests — restored parser surface + acceptance gates.

Direct-import tests (parser surface exposed by schema_check.py):
  test_infer_epistemic_label_roundtrip
  test_durable_memory_kinds_mapping          (all 5 kinds)
  test_trigger_index_view_parsing
Contract / subprocess tests:
  test_capabilities_table_seven_columns
  test_schema_projection_staleness           (staleness gate vs checked-in schema.md)
Negative-case fixtures (ported from previous version, updated for 7-column status doc).
"""

import sys
import tempfile
import subprocess
from pathlib import Path
from typing import List, Tuple

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

| capability | class | test_path | measured_value | ci_run | gate | epistemic |
|---|---|---|---|---|---|---|
| Plugin manifest loads from bundled bytes | MEASURED | test_load_bundled_manifest | 100% success | pass | gate-1 | MEASURED |
| UnifiedDB schema owned by single writer | PLANNED | test_single_writer_invariant | no passing measurement | pending | gate-2 | PLANNED |
| Unknown capability outside gate | UNKNOWN | test_unknown | not covered | outside | outside | UNKNOWN |
"""


# ============================================================
# Restored parser surface tests
# ============================================================

def test_infer_epistemic_label_roundtrip():
    """infer_epistemic_label accepts known labels, normalizes case/whitespace, UNKNOWN for unknown."""
    assert sc.infer_epistemic_label("MEASURED") == "MEASURED"
    assert sc.infer_epistemic_label("PLANNED") == "PLANNED"
    assert sc.infer_epistemic_label("UNKNOWN") == "UNKNOWN"
    assert sc.infer_epistemic_label("ERROR") == "ERROR"
    # case-insensitive and whitespace tolerant
    assert sc.infer_epistemic_label("measured") == "MEASURED"
    assert sc.infer_epistemic_label(" Planned ") == "PLANNED"
    assert sc.infer_epistemic_label("  unknown  ") == "UNKNOWN"
    # Honest default: unknown stays unknown, never coerced to MEASURED/PLANNED/ERROR
    assert sc.infer_epistemic_label("HYPOTHESIS") == "UNKNOWN"
    assert sc.infer_epistemic_label("") == "UNKNOWN"
    assert sc.infer_epistemic_label("   ") == "UNKNOWN"


def test_durable_memory_kinds_mapping():
    """DURABLE_MEMORY_KINDS maps exactly 5 durable memory kinds."""
    kinds = sc.DURABLE_MEMORY_KINDS
    assert isinstance(kinds, dict), f"DURABLE_MEMORY_KINDS is not a dict: {type(kinds)}"
    assert len(kinds) == 5, f"Expected 5 durable memory kinds, got {len(kinds)}: {list(kinds)}"
    for kind, info in kinds.items():
        assert isinstance(kind, str) and kind.strip(), f"Invalid kind key: {kind!r}"
        assert info is not None, f"Kind {kind!r} has no associated info"


def test_trigger_index_view_parsing():
    """DDL parsing extracts triggers, indexes and views as separate object classes."""
    sql = """
CREATE TABLE t1 (id INTEGER PRIMARY KEY);
CREATE INDEX idx_t1_id ON t1(id);
CREATE VIEW v1 AS SELECT id FROM t1;
CREATE TRIGGER trg_t1 AFTER INSERT ON t1 BEGIN SELECT 1; END;
"""
    objects = sc.parse_ddl_objects(sql)
    assert len(objects.tables) == 1, f"Expected 1 table, got {len(objects.tables)}"
    assert len(objects.indexes) == 1, f"Expected 1 index, got {len(objects.indexes)}"
    assert len(objects.views) == 1, f"Expected 1 view, got {len(objects.views)}"
    assert len(objects.triggers) == 1, f"Expected 1 trigger, got {len(objects.triggers)}"
    assert objects.indexes[0].name == "idx_t1_id"
    assert objects.views[0].name == "v1"
    assert objects.triggers[0].name == "trg_t1"


# ============================================================
# Capabilities table 7-column contract
# ============================================================

def test_capabilities_table_seven_columns():
    """Capabilities table in status.md must have exactly 7 columns."""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n\nThis is a normal plugin.\n")

    # Valid 7-column table passes
    code, out, err = run_checker(["--no-strict"], tmp)
    assert code == 0, f"Expected exit 0 for valid 7-column table, got {code}: {out} {err}"
    assert "RESULT: PASS" in out

    # Wrong column count (6 instead of 7) -> exit 1
    bad_header = "| capability | class | test_path | measured_value | ci_run | gate |"
    bad_doc = BASE_STATUS_DOC.replace(
        "| capability | class | test_path | measured_value | ci_run | gate | epistemic |",
        bad_header,
    )
    write_status_doc(tmp, bad_doc)
    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1 for wrong column count, got {code}: {out} {err}"
    combined = (out + err).upper()
    assert "CAPABILITIES_COLUMNS" in combined or "7" in combined, f"Expected column-count error: {out} {err}"


# ============================================================
# Schema projection staleness gate
# ============================================================

def test_schema_projection_staleness():
    """Regenerating schema.md from schema.sql must match the checked-in docs/zero/schema.md."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    sql_path = repo_root / "zero" / "unifieddb" / "schema.sql"
    doc_path = repo_root / "docs" / "zero" / "schema.md"
    assert sql_path.exists(), f"schema.sql not found at {sql_path}"
    assert doc_path.exists(), f"schema.md not found at {doc_path}"

    sql = sql_path.read_text()
    checked_in = doc_path.read_text()

    gen_fn = getattr(sc, "generate_schema_projection", None) or getattr(sc, "project_schema", None)
    assert gen_fn is not None, "schema_check.py exposes no schema projection function"
    generated = gen_fn(sql)

    assert generated.strip() == checked_in.strip(), (
        "schema.md is stale: regenerated projection does not match checked-in version. "
        "Run the schema projection generator and commit the updated docs/zero/schema.md."
    )


# ============================================================
# Original negative-case fixtures (ported, updated for 7-column status doc)
# ============================================================

def test_missing_column_in_ddl():
    """doc column absent from DDL -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    schema_doc = BASE_SCHEMA_DOC + """
| extra_col | TEXT | NOT NULL | MEASURED | Extra column not in DDL |
"""
    write_schema_doc(tmp, schema_doc)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n")

    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "MISSING_COLUMN" in (err + out)


def test_missing_table_in_ddl():
    """doc table absent from DDL -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
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
    assert "MISSING_TABLE" in (err + out)


def test_type_mismatch():
    """doc column type differs from DDL -> exit 1"""
    tmp = create_test_repo()
    sql = BASE_SQL.replace("failure_count INTEGER", "failure_count INTEGER")
    write_sql(tmp, sql)
    schema_doc = BASE_SCHEMA_DOC.replace("failure_count | INTEGER", "failure_count | REAL")
    write_schema_doc(tmp, schema_doc)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n")

    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "TYPE_MISMATCH" in (err + out)


def test_constraint_mismatch():
    """doc column constraint differs from DDL -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    schema_doc = BASE_SCHEMA_DOC.replace("failure_count | INTEGER | NOT NULL, DEFAULT 0", "failure_count | INTEGER | DEFAULT 0")
    write_schema_doc(tmp, schema_doc)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n")

    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "CONSTRAINT_MISMATCH" in (err + out)


def test_unprojected_ddl_strict():
    """DDL column absent from doc under --strict -> exit 1"""
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

    code, out, err = run_checker(["--strict"], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "UNPROJECTED_DDL" in (err + out)


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


def test_invalid_label_two_labels():
    """class cell with two labels (MEASURED PLANNED) -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    status_doc = BASE_STATUS_DOC.replace(
        "| Plugin manifest loads from bundled bytes | MEASURED |",
        "| Plugin manifest loads from bundled bytes | MEASURED PLANNED |",
        1,
    )
    write_status_doc(tmp, status_doc)
    write_plugin_readme(tmp, "# Plugin\n")

    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "INVALID_LABEL" in (err + out)


def test_invalid_label_hypothesis():
    """class cell HYPOTHESIS -> exit 1 (not allowed)"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    status_doc = BASE_STATUS_DOC.replace(
        "| Plugin manifest loads from bundled bytes | MEASURED |",
        "| Plugin manifest loads from bundled bytes | HYPOTHESIS |",
        1,
    )
    write_status_doc(tmp, status_doc)
    write_plugin_readme(tmp, "# Plugin\n")

    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "INVALID_LABEL" in (err + out)


def test_invalid_label_empty():
    """class cell empty -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    status_doc = BASE_STATUS_DOC.replace(
        "| Plugin manifest loads from bundled bytes | MEASURED |",
        "| Plugin manifest loads from bundled bytes | |",
        1,
    )
    write_status_doc(tmp, status_doc)
    write_plugin_readme(tmp, "# Plugin\n")

    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "INVALID_LABEL" in (err + out)


def test_forbidden_claim_agi():
    """forbidden claim pattern 'is AGI' -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n\nThis system **is AGI** and approaches consciousness.\n")

    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "FORBIDDEN_CLAIM" in (err + out)


def test_forbidden_claim_approaches_agi():
    """forbidden claim pattern 'approaches AGI' -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n\nThe system **approaches AGI** capabilities.\n")

    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "FORBIDDEN_CLAIM" in (err + out)


def test_forbidden_claim_shows_signs():
    """forbidden claim pattern 'shows signs of AGI' -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n\nIt **shows signs of AGI** behavior.\n")

    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "FORBIDDEN_CLAIM" in (err + out)


def test_forbidden_claim_consciousness():
    """forbidden claim pattern 'is conscious' -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_rust_source(tmp, "test.rs", "// This system is conscious\n")

    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "FORBIDDEN_CLAIM" in (err + out)


def test_forbidden_claim_sentience():
    """forbidden claim pattern 'shows signs of sentience' -> exit 1"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_ts_source(tmp, "test.ts", "// shows signs of sentience\n")

    code, out, err = run_checker([], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    assert "FORBIDDEN_CLAIM" in (err + out)


def test_missing_input_sql():
    """missing SQL file -> exit 2"""
    tmp = create_test_repo()
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n")

    code, out, err = run_checker([], tmp)
    assert code == 2, f"Expected exit 2, got {code}: {out} {err}"
    assert "input missing" in err.lower()


def test_missing_input_schema_doc():
    """missing schema.md -> exit 2"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n")

    code, out, err = run_checker([], tmp)
    assert code == 2, f"Expected exit 2, got {code}: {out} {err}"
    assert "input missing" in err.lower()


def test_missing_input_status_doc():
    """missing status.md -> exit 2"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_plugin_readme(tmp, "# Plugin\n")

    code, out, err = run_checker([], tmp)
    assert code == 2, f"Expected exit 2, got {code}: {out} {err}"
    assert "input missing" in err.lower()


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


def test_epistemic_label_in_doc():
    """Epistemic label in schema.doc column table is validated"""
    tmp = create_test_repo()
    write_sql(tmp, BASE_SQL)
    schema_doc = BASE_SCHEMA_DOC.replace("| MEASURED |", "| INVALID_LABEL |")
    write_schema_doc(tmp, schema_doc)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n")

    code, out, err = run_checker([], tmp)
    assert code in (0, 1), f"Unexpected exit code {code}: {out} {err}"


def test_new_table_missing_epistemic_columns():
    """New table in SQL missing epistemic_label or promotion_stage columns -> exit 1 under --strict"""
    tmp = create_test_repo()
    sql = BASE_SQL + """
CREATE TABLE new_table_missing_epistemic (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
) STRICT;
"""
    write_sql(tmp, sql)
    write_schema_doc(tmp, BASE_SCHEMA_DOC)
    write_status_doc(tmp, BASE_STATUS_DOC)
    write_plugin_readme(tmp, "# Plugin\n")

    code, out, err = run_checker(["--strict"], tmp)
    assert code == 1, f"Expected exit 1, got {code}: {out} {err}"
    combined = (err + out).upper()
    assert "MISSING_EPISTEMIC_COLUMNS" in combined or "EPISTEMIC_LABEL" in combined or "PROMOTION_STAGE" in combined, f"Expected epistemic-columns error: {out} {err}"
