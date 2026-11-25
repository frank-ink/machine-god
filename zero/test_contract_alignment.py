#!/usr/bin/env python3
"""Canonical alignment check for the two FranKenstein 3.0 environment contracts.

Compares the repository-root contract (docs/zero/contract_env.json) with the
bundled plugin contract (plugins/frankenstein3/docs/zero/contract_env.json).

Canonical fields that must be identical between the two copies:
    precedence, data_dir_precedence, hook_env_writes, ambient_passthrough,
    admissibility_space

Fields that may legitimately differ (excluded from comparison):
    $schema, schema_version, description, sources

Exits 0 when aligned; exits 1 with a field-level diff on any mismatch.
"""
from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent

ROOT_CONTRACT = REPO / "docs" / "zero" / "contract_env.json"
PLUGIN_CONTRACT = REPO / "plugins" / "frankenstein3" / "docs" / "zero" / "contract_env.json"

CANONICAL_FIELDS = (
    "precedence",
    "data_dir_precedence",
    "hook_env_writes",
    "ambient_passthrough",
    "admissibility_space",
)

REQUIRED_RESOLUTION_RULES = (
    "F3_DB_PATH",
    "FRANK3_DATA",
    "CLAUDE_PLUGIN_DATA",
    "XDG_DATA_HOME",
    "HOME",
)


def load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def canonical(doc: dict) -> dict:
    return {field: doc[field] for field in CANONICAL_FIELDS}


def structural_checks(doc: dict, label: str) -> list[str]:
    problems: list[str] = []
    precedence = doc.get("precedence", [])
    if len(precedence) != 5:
        problems.append(f"{label}: precedence has {len(precedence)} items, expected 5")
    elif precedence[0] != "F3_DB_PATH":
        problems.append(f'{label}: precedence[0] is {precedence[0]!r}, expected "F3_DB_PATH"')

    admiss = doc.get("admissibility_space", {})
    path_vars = admiss.get("path_variables", [])
    if len(path_vars) != 5:
        problems.append(f"{label}: path_variables has {len(path_vars)} items, expected 5")
    if "F3_DB_PATH" not in path_vars:
        problems.append(f'{label}: "F3_DB_PATH" missing from path_variables')

    rules = admiss.get("resolution_rules", {})
    for var in REQUIRED_RESOLUTION_RULES:
        if var not in rules:
            problems.append(f'{label}: resolution_rules missing required key {var!r}')
        elif not isinstance(rules[var], str) or len(rules[var]) < 1:
            problems.append(f'{label}: resolution_rules[{var!r}] must be a non-empty string')

    writes = doc.get("hook_env_writes", [])
    if len(writes) != 3:
        problems.append(f"{label}: hook_env_writes has {len(writes)} items, expected 3")

    return problems


def field_diff(name: str, a: object, b: object) -> str:
    a_text = json.dumps(a, indent=2, sort_keys=True, ensure_ascii=False).splitlines()
    b_text = json.dumps(b, indent=2, sort_keys=True, ensure_ascii=False).splitlines()
    diff = list(
        difflib.unified_diff(
            a_text, b_text, fromfile=f"root:{name}", tofile=f"plugin:{name}", lineterm=""
        )
    )
    return "\n".join(diff)


def main() -> int:
    root = load(ROOT_CONTRACT)
    plugin = load(PLUGIN_CONTRACT)

    problems: list[str] = []
    problems.extend(structural_checks(root, "root contract"))
    problems.extend(structural_checks(plugin, "plugin contract"))

    root_canon = canonical(root)
    plugin_canon = canonical(plugin)

    for field in CANONICAL_FIELDS:
        if root_canon[field] != plugin_canon[field]:
            problems.append(f"canonical mismatch: {field}")
            problems.append(field_diff(field, root_canon[field], plugin_canon[field]))

    if problems:
        sys.stderr.write("CONTRACT ALIGNMENT FAILED\n")
        sys.stderr.write("=" * 70 + "\n")
        for problem in problems:
            sys.stderr.write(problem + "\n")
            sys.stderr.write("-" * 70 + "\n")
        return 1

    print("CONTRACT ALIGNMENT OK: root and plugin contracts are canonically equal")
    return 0


if __name__ == "__main__":
    sys.exit(main())
