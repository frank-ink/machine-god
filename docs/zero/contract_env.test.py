#!/usr/bin/env python3
"""
Validation test for docs/zero/contract_env.json against its schema.
Run with: python3 -m pytest docs/zero/contract_env.test.py -v
"""

import json
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def test_contract_validates_against_schema():
    """Contract must validate against its JSON schema (stdlib-only validation)."""
    contract_path = Path(__file__).parent / "contract_env.json"
    schema_path = Path(__file__).parent / "contract_env.schema.json"

    contract = load_json(contract_path)
    schema = load_json(schema_path)

    # Basic structural validation using stdlib only
    # Check required top-level fields
    required_fields = [
        "schema_version", "description", "precedence", "data_dir_precedence",
        "hook_env_writes", "ambient_passthrough", "admissibility_space", "sources"
    ]
    for field in required_fields:
        assert field in contract, f"Missing required field: {field}"

    # Validate schema_version
    assert contract["schema_version"] == 1, "schema_version must be 1"

    # Validate precedence arrays have correct length and unique items
    for key in ["precedence", "data_dir_precedence"]:
        arr = contract[key]
        assert isinstance(arr, list), f"{key} must be array"
        assert len(arr) == 4, f"{key} must have 4 items"
        assert len(set(arr)) == 4, f"{key} must have unique items"

    # Validate hook_env_writes
    hook_writes = contract["hook_env_writes"]
    assert isinstance(hook_writes, list), "hook_env_writes must be array"
    assert len(hook_writes) == 3, "hook_env_writes must have 3 items"
    assert len(set(hook_writes)) == 3, "hook_env_writes must have unique items"

    # Validate ambient_passthrough
    ambient = contract["ambient_passthrough"]
    assert isinstance(ambient, list), "ambient_passthrough must be array"
    assert len(ambient) == 3, "ambient_passthrough must have 3 items"
    assert len(set(ambient)) == 3, "ambient_passthrough must have unique items"

    # Validate admissibility_space structure
    m = contract["admissibility_space"]
    assert isinstance(m, dict), "admissibility_space must be object"
    assert m.get("kind") == "AdmissibilitySpace", "kind must be 'AdmissibilitySpace'"

    required_m_fields = ["path_variables", "mode_flags", "resolution_rules", "invariants"]
    for field in required_m_fields:
        assert field in m, f"admissibility_space missing {field}"

    # Validate path_variables
    pv = m["path_variables"]
    assert isinstance(pv, list), "path_variables must be array"
    assert len(pv) == 5, "path_variables must have 5 items"
    assert len(set(pv)) == 5, "path_variables must have unique items"

    # Validate mode_flags
    mf = m["mode_flags"]
    assert isinstance(mf, list), "mode_flags must be array"
    assert len(mf) == 1, "mode_flags must have 1 item"
    assert mf[0] == "F3_DRY_RUN", "mode_flags must be ['F3_DRY_RUN']"

    # Validate resolution_rules
    rr = m["resolution_rules"]
    assert isinstance(rr, dict), "resolution_rules must be object"
    for var in pv:
        assert var in rr, f"resolution_rules missing {var}"
        assert isinstance(rr[var], str) and rr[var], f"resolution_rules[{var}] must be non-empty string"

    # Validate invariants
    inv = m["invariants"]
    assert isinstance(inv, list), "invariants must be array"
    assert len(inv) >= 3, "invariants must have at least 3 entries"
    assert len(set(inv)) == len(inv), "invariants must be unique"

    # Validate sources
    sources = contract["sources"]
    assert isinstance(sources, dict), "sources must be object"
    required_sources = ["install_sh", "status_py", "path_resolution", "rust", "typescript"]
    for src in required_sources:
        assert src in sources, f"sources missing {src}"


def test_precedence_matches_f3_pfade():
    """Precedence array must match f3_pfade.py PRECEDENCE exactly (4 items, no F3_DB_PATH)."""
    contract_path = Path(__file__).parent / "contract_env.json"
    contract = load_json(contract_path)

    expected_precedence = [
        "FRANK3_DATA",
        "CLAUDE_PLUGIN_DATA",
        "XDG_DATA_HOME",
        "HOME",
    ]

    assert contract["precedence"] == expected_precedence, \
        f"precedence mismatch: got {contract['precedence']}, expected {expected_precedence}"
    assert contract["data_dir_precedence"] == expected_precedence, \
        f"data_dir_precedence mismatch: got {contract['data_dir_precedence']}, expected {expected_precedence}"


def test_f3_dry_run_not_in_precedence():
    """F3_DRY_RUN is a mode flag, must not appear in precedence."""
    contract_path = Path(__file__).parent / "contract_env.json"
    contract = load_json(contract_path)

    assert "F3_DRY_RUN" not in contract["precedence"], \
        "F3_DRY_RUN must not be in precedence (it is a mode flag)"
    assert "F3_DRY_RUN" not in contract["data_dir_precedence"], \
        "F3_DRY_RUN must not be in data_dir_precedence"


def test_f3_db_path_not_in_precedence():
    """F3_DB_PATH is a path variable with resolution_rules entry, not a precedence entry."""
    contract_path = Path(__file__).parent / "contract_env.json"
    contract = load_json(contract_path)

    assert "F3_DB_PATH" not in contract["precedence"], \
        "F3_DB_PATH must not be in precedence (it is a path variable with resolution_rules entry)"
    assert "F3_DB_PATH" not in contract["data_dir_precedence"], \
        "F3_DB_PATH must not be in data_dir_precedence (it is a path variable with resolution_rules entry)"


def test_field_names_match_readme():
    """Field names must match README: hook_env_writes, ambient_passthrough."""
    contract_path = Path(__file__).parent / "contract_env.json"
    contract = load_json(contract_path)

    # Old incorrect names must not exist
    assert "hook_env_write_vars" not in contract, \
        "hook_env_write_vars is the old name; must be hook_env_writes"
    assert "additional_vars" not in contract, \
        "additional_vars is the old name; must be ambient_passthrough"

    # Correct names must exist
    assert "hook_env_writes" in contract, "hook_env_writes field missing"
    assert "ambient_passthrough" in contract, "ambient_passthrough field missing"

    # Values must match f3_pfade.py
    expected_hook_writes = ["FRANK3_DATA", "CLAUDE_PLUGIN_DATA", "F3_DB_PATH"]
    expected_ambient = ["F3_DRY_RUN", "XDG_DATA_HOME", "HOME"]

    assert contract["hook_env_writes"] == expected_hook_writes, \
        f"hook_env_writes mismatch: got {contract['hook_env_writes']}"
    assert contract["ambient_passthrough"] == expected_ambient, \
        f"ambient_passthrough mismatch: got {contract['ambient_passthrough']}"


def test_admissibility_space_typed_structure():
    """M (admissibility_space) must be a single typed structure with required fields."""
    contract_path = Path(__file__).parent / "contract_env.json"
    contract = load_json(contract_path)

    m = contract["admissibility_space"]

    # Kind discriminator
    assert m["kind"] == "AdmissibilitySpace", "admissibility_space.kind must be 'AdmissibilitySpace'"

    # Path variables (exactly the 5 precedence vars including F3_DB_PATH as path variable)
    expected_path_vars = [
        "F3_DB_PATH",
        "FRANK3_DATA",
        "CLAUDE_PLUGIN_DATA",
        "XDG_DATA_HOME",
        "HOME",
    ]
    assert m["path_variables"] == expected_path_vars, \
        f"path_variables mismatch: got {m['path_variables']}"

    # Mode flags (only F3_DRY_RUN)
    assert m["mode_flags"] == ["F3_DRY_RUN"], \
        f"mode_flags mismatch: got {m['mode_flags']}"

    # Resolution rules for all 5 path variables
    for var in expected_path_vars:
        assert var in m["resolution_rules"], f"resolution_rules missing for {var}"
        assert isinstance(m["resolution_rules"][var], str) and m["resolution_rules"][var], \
            f"resolution_rules[{var}] must be non-empty string"

    # Invariants (at least 3)
    assert len(m["invariants"]) >= 3, "invariants must have at least 3 entries"
    invariant_text = " ".join(m["invariants"])
    assert "F3_DRY_RUN never participates in path precedence" in invariant_text, \
        "Missing invariant: F3_DRY_RUN never participates in path precedence"
    assert "Exactly one data directory is selected" in invariant_text, \
        "Missing invariant: Exactly one data directory is selected"
    assert "Missing or unreadable contract is a hard error" in invariant_text, \
        "Missing invariant: Missing or unreadable contract is a hard error"


if __name__ == "__main__":
    test_contract_validates_against_schema()
    test_precedence_matches_f3_pfade()
    test_f3_dry_run_not_in_precedence()
    test_f3_db_path_not_in_precedence()
    test_field_names_match_readme()
    test_admissibility_space_typed_structure()
    print("All contract_env validation tests passed.")
