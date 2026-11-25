"""Contract drift gate.

Compares the machine-readable environment contract at the repository root
(docs/zero/contract_env.json) against the plugin copy
(plugins/frankenstein3/docs/zero/contract_env.json) over the semantic fields:

    schema_version, precedence, data_dir_precedence, hook_env_writes,
    ambient_passthrough, admissibility_space

Any drift fails the build. A missing or unreadable contract is a hard error,
never a skip.

Run: pytest docs/zero/test_contract_drift_check.py -v
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

REPO_CONTRACT = HERE / "contract_env.json"
PLUGIN_CONTRACT = (
    REPO_ROOT / "plugins" / "frankenstein3" / "docs" / "zero" / "contract_env.json"
)

SEMANTIC_FIELDS: tuple[str, ...] = (
    "schema_version",
    "precedence",
    "data_dir_precedence",
    "hook_env_writes",
    "ambient_passthrough",
    "admissibility_space",
)


def _load_contract(path: Path) -> dict:
    """Load a contract file; fail closed on any read or parse error."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AssertionError(
            f"FAIL_CLOSED: contract is unreadable: {path}: {exc}"
        ) from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"FAIL_CLOSED: contract is not valid JSON: {path}: {exc}"
        ) from exc


def _field_diff(repo: dict, plugin: dict, field: str) -> str:
    repo_value = repo.get(field, "<MISSING>")
    plugin_value = plugin.get(field, "<MISSING>")
    repo_lines = json.dumps(
        repo_value, sort_keys=True, indent=2, ensure_ascii=False
    ).splitlines()
    plugin_lines = json.dumps(
        plugin_value, sort_keys=True, indent=2, ensure_ascii=False
    ).splitlines()
    diff = difflib.unified_diff(
        repo_lines,
        plugin_lines,
        fromfile=f"docs/zero/contract_env.json[{field}]",
        tofile=f"plugins/frankenstein3/docs/zero/contract_env.json[{field}]",
        lineterm="",
    )
    return "\n".join(diff)


def collect_drifts(repo: dict, plugin: dict) -> list[str]:
    """Return a unified diff for every semantic field that diverges."""
    drifts: list[str] = []
    for field in SEMANTIC_FIELDS:
        if repo.get(field) != plugin.get(field):
            drifts.append(_field_diff(repo, plugin, field))
    return drifts


def _load_both() -> tuple[dict, dict]:
    return _load_contract(REPO_CONTRACT), _load_contract(PLUGIN_CONTRACT)


def test_contracts_are_readable() -> None:
    _load_both()


def test_schema_version_matches() -> None:
    repo, plugin = _load_both()
    assert repo["schema_version"] == plugin["schema_version"], _field_diff(
        repo, plugin, "schema_version"
    )


def test_precedence_matches() -> None:
    repo, plugin = _load_both()
    assert repo["precedence"] == plugin["precedence"], _field_diff(
        repo, plugin, "precedence"
    )


def test_data_dir_precedence_matches() -> None:
    repo, plugin = _load_both()
    assert repo["data_dir_precedence"] == plugin["data_dir_precedence"], _field_diff(
        repo, plugin, "data_dir_precedence"
    )


def test_hook_env_writes_matches() -> None:
    repo, plugin = _load_both()
    assert repo["hook_env_writes"] == plugin["hook_env_writes"], _field_diff(
        repo, plugin, "hook_env_writes"
    )


def test_ambient_passthrough_matches() -> None:
    repo, plugin = _load_both()
    assert repo["ambient_passthrough"] == plugin["ambient_passthrough"], _field_diff(
        repo, plugin, "ambient_passthrough"
    )


def test_admissibility_space_matches() -> None:
    repo, plugin = _load_both()
    assert repo["admissibility_space"] == plugin["admissibility_space"], _field_diff(
        repo, plugin, "admissibility_space"
    )


def test_all_semantic_fields_match() -> None:
    repo, plugin = _load_both()
    drifts = collect_drifts(repo, plugin)
    assert not drifts, (
        "Contract drift detected between repo contract and plugin contract. "
        "Diff per semantic field:\n\n" + "\n\n".join(drifts)
    )


def test_detects_divergence_with_clear_diff() -> None:
    """The gate must fail (with a diff) when a semantic field diverges."""
    repo = {
        "schema_version": 1,
        "precedence": ["FRANK3_DATA", "CLAUDE_PLUGIN_DATA"],
        "data_dir_precedence": ["FRANK3_DATA", "CLAUDE_PLUGIN_DATA"],
        "hook_env_writes": ["FRANK3_DATA"],
        "ambient_passthrough": ["F3_DRY_RUN"],
        "admissibility_space": {"kind": "AdmissibilitySpace"},
    }
    plugin = {
        "schema_version": 1,
        "precedence": ["FRANK3_DATA", "F3_DB_PATH"],
        "data_dir_precedence": ["FRANK3_DATA", "CLAUDE_PLUGIN_DATA"],
        "hook_env_writes": ["FRANK3_DATA"],
        "ambient_passthrough": ["F3_DRY_RUN"],
        "admissibility_space": {"kind": "AdmissibilitySpace"},
    }
    drifts = collect_drifts(repo, plugin)
    assert drifts, "expected drift to be detected"
    assert any("precedence" in d for d in drifts)
    assert any("@@" in d for d in drifts)


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
