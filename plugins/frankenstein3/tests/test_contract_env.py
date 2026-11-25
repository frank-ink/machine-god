#!/usr/bin/env python3
"""
Validation test for FranKenstein 3.0 environment contract (bundle copy).

Validates docs/zero/contract_env.json against docs/zero/contract_env.schema.json
using a stdlib-only JSON Schema (draft-07 subset) validator, and checks the
contract precedence against the real resolver scripts/star/f3_paths.py
(import + get_data_dir call).

Resolver semantics (scripts/star/f3_paths.py):
    get_data_dir() -> ONE resolved path (a directory or a path inside one).

Contract semantics (docs/zero/contract_env.json):
    "precedence" -> a SEQUENCE of candidate directories, in consultation order.

Therefore the contract check is a MEMBERSHIP check: the resolved path must be
located in / directly under one of the precedence directories. It is never an
equality check between a single path and the precedence array (that would be a
type mismatch and would not describe resolver behaviour).

Run:
    cd plugins/frankenstein3 && python -m pytest tests/test_contract_env.py -v
    python tests/test_contract_env.py
"""

import copy
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import pytest

# PLUGIN_ROOT: test file is at plugins/frankenstein3/tests/test_contract_env.py
# parent = plugins/frankenstein3/tests/
# parent.parent = plugins/frankenstein3/  (plugin root = bundle root)
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = PLUGIN_ROOT / "docs/zero" / "contract_env.json"
SCHEMA_PATH = PLUGIN_ROOT / "docs/zero" / "contract_env.schema.json"
RESOLVER_PATH = PLUGIN_ROOT / "scripts" / "star" / "f3_paths.py"


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# stdlib-only JSON Schema validator (draft-07 subset used by the contract schema)
# ---------------------------------------------------------------------------

_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


def _type_ok(instance, type_name):
    if type_name == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if type_name == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    expected = _TYPE_MAP.get(type_name)
    if expected is None:
        return True  # unknown type keyword: do not fail validation on it
    return isinstance(instance, expected)


def _unique_items_ok(items):
    seen = []
    for item in items:
        key = json.dumps(item, sort_keys=True, default=str)
        if key in seen:
            return False
        seen.append(key)
    return True


def validate(instance, schema, path="$"):
    """Return a list of human-readable validation errors (empty == valid)."""
    errors = []
    _validate(instance, schema, path, errors)
    return errors


def _validate(instance, schema, path, errors):
    if not isinstance(schema, dict):
        return

    # type
    if "type" in schema and not _type_ok(instance, schema["type"]):
        errors.append(f"{path}: type violation: expected {schema['type']!r}, got {instance!r}")
        return  # type mismatch: deeper checks are meaningless

    # const
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: const violation: expected {schema['const']!r}, got {instance!r}")

    # enum
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: enum violation: {instance!r} not in {schema['enum']!r}")

    # pattern (strings only)
    if "pattern" in schema and isinstance(instance, str):
        if not re.search(schema["pattern"], instance):
            errors.append(f"{path}: pattern violation: {instance!r} does not match {schema['pattern']!r}")

    # minLength / maxLength
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: minLength violation: {len(instance)} < {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: maxLength violation: {len(instance)} > {schema['maxLength']}")

    # arrays
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: minItems violation: {len(instance)} < {schema['minItems']}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: maxItems violation: {len(instance)} > {schema['maxItems']}")
        if (
            "uniqueItems" in schema
            and schema["uniqueItems"] is True
            and not _unique_items_ok(instance)
        ):
            errors.append(f"{path}: uniqueItems violation: duplicate items present")
        if "items" in schema:
            for idx, item in enumerate(instance):
                _validate(item, schema["items"], f"{path}[{idx}]", errors)

    # objects
    if isinstance(instance, dict):
        if "required" in schema:
            for req in schema["required"]:
                if req not in instance:
                    errors.append(f"{path}: required violation: missing key {req!r}")
        allowed_keys = set()
        if "properties" in schema:
            allowed_keys = set(schema["properties"].keys())
            for key, subschema in schema["properties"].items():
                if key in instance:
                    _validate(instance[key], subschema, f"{path}.{key}", errors)
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in allowed_keys:
                    errors.append(
                        f"{path}: additionalProperties violation: unexpected key {key!r}"
                    )


# ---------------------------------------------------------------------------
# Precedence-directory resolution helpers
#
# A precedence entry may be:
#   * an environment variable name  (e.g. "FRANKENSTEIN3_DATA_DIR")
#   * a path template               (e.g. "$XDG_DATA_HOME/frankenstein3",
#                                             "~/.local/share/frankenstein3",
#                                             "data")
# Unset / unresolvable entries stay UNKNOWN: they contribute no candidate.
# ---------------------------------------------------------------------------

_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# Optional resolver-side declarations, used only as ADDITIONAL candidate
# directories (never as an equality oracle).
_RESOLVER_PRECEDENCE_ATTRS = (
    "PRECEDENCE",
    "DATA_DIR_PRECEDENCE",
    "DATA_PRECEDENCE",
    "PRECEDENCE_DIRS",
    "DATA_DIRS",
    "DATA_DIR_CANDIDATES",
    "DATA_DIR",
    "DEFAULT_DATA_DIR",
    "FALLBACK_DATA_DIR",
    "_PRECEDENCE",
    "_DATA_DIR_PRECEDENCE",
)


def _norm(path) -> Path:
    """Normalize a path for comparison: expand ~, resolve symlinks/..."""
    return Path(os.path.realpath(os.path.expanduser(str(path))))


def _relative_bases():
    """Bases used to anchor relative precedence entries."""
    return (
        Path.cwd(),
        PLUGIN_ROOT,
        PLUGIN_ROOT.parent,
        PLUGIN_ROOT.parent.parent,
    )


def _entry_to_paths(entry):
    """Translate one precedence entry into concrete candidate directories."""
    text = str(entry)
    out = []

    if _ENV_NAME_RE.match(text):
        raw = os.environ.get(text)
        if raw:
            out.append(Path(os.path.expanduser(os.path.expandvars(raw))))
        return out  # unset env var -> UNKNOWN, no candidate

    expanded = os.path.expandvars(os.path.expanduser(text))
    if not expanded:
        return out
    candidate = Path(expanded)
    if candidate.is_absolute():
        out.append(candidate)
    else:
        for base in _relative_bases():
            out.append(base / candidate)
    return out


def _resolver_precedence_entries(resolver):
    """Precedence entries declared by the resolver module itself (if any)."""
    entries = []
    for attr in _RESOLVER_PRECEDENCE_ATTRS:
        value = getattr(resolver, attr, None)
        if value is None:
            continue
        if callable(value):
            try:
                value = value()
            except Exception:
                continue
        if isinstance(value, (list, tuple)):
            entries.extend(value)
        elif isinstance(value, (str, Path)):
            entries.append(value)
    return entries


def _precedence_directories(contract, resolver):
    """Concrete directories declared by the contract (plus resolver extras)."""
    dirs = []
    for entry in contract.get("precedence", []):
        dirs.extend(_entry_to_paths(entry))
    for entry in _resolver_precedence_entries(resolver):
        dirs.extend(_entry_to_paths(entry))

    seen = set()
    unique = []
    for directory in dirs:
        key = str(_norm(directory))
        if key not in seen:
            seen.add(key)
            unique.append(directory)
    return unique


def _load_resolver():
    spec = importlib.util.spec_from_file_location("f3_paths", RESOLVER_PATH)
    resolver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(resolver)
    return resolver


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_contract_validates_against_schema():
    """Contract must validate against its schema (stdlib-only, no external deps)."""
    contract = load_json(CONTRACT_PATH)
    schema = load_json(SCHEMA_PATH)
    errors = validate(contract, schema)
    assert not errors, f"contract_env.json violates contract_env.schema.json: {errors}"


def test_schema_catches_additional_properties():
    """additionalProperties: false must reject unknown top-level keys."""
    contract = copy.deepcopy(load_json(CONTRACT_PATH))
    contract["unsupported_extra_key"] = "x"
    schema = load_json(SCHEMA_PATH)
    errors = validate(contract, schema)
    assert any("additionalProperties" in e for e in errors), f"expected additionalProperties error, got: {errors}"


def test_schema_catches_const_violation():
    """const must reject schema_version != 1."""
    contract = copy.deepcopy(load_json(CONTRACT_PATH))
    contract["schema_version"] = 2
    schema = load_json(SCHEMA_PATH)
    errors = validate(contract, schema)
    assert any("const" in e for e in errors), f"expected const error, got: {errors}"


def test_schema_catches_pattern_violation():
    """pattern must reject sources values that do not match the required path."""
    contract = copy.deepcopy(load_json(CONTRACT_PATH))
    contract["sources"]["install_sh"] = "scripts/other/install.sh"
    schema = load_json(SCHEMA_PATH)
    errors = validate(contract, schema)
    assert any("pattern" in e for e in errors), f"expected pattern error, got: {errors}"


def test_schema_catches_min_items():
    """minItems must reject a precedence array shorter than 5 (schema minItems=5)."""
    contract = copy.deepcopy(load_json(CONTRACT_PATH))
    contract["precedence"] = contract["precedence"][:4]  # 4 items < minItems=5
    schema = load_json(SCHEMA_PATH)
    errors = validate(contract, schema)
    assert any("minItems" in e for e in errors), f"expected minItems error, got: {errors}"


def test_schema_catches_max_items():
    """maxItems must reject a precedence array longer than 5 (schema maxItems=5)."""
    contract = copy.deepcopy(load_json(CONTRACT_PATH))
    contract["precedence"] = list(contract["precedence"]) + ["EXTRA_VAR"]
    schema = load_json(SCHEMA_PATH)
    errors = validate(contract, schema)
    assert any("maxItems" in e for e in errors), f"expected maxItems error, got: {errors}"


def test_resolver_output_is_under_precedence_directory():
    """get_data_dir() must resolve to a path located in a precedence directory.

    The resolver returns ONE path; the contract precedence is a SEQUENCE of
    candidate directories. The assertion is therefore a membership check on
    the resolved path's parent (or the path itself when the resolver returns
    the directory), never an equality check against the precedence array.
    """
    contract = load_json(CONTRACT_PATH)
    resolver = _load_resolver()

    raw = resolver.get_data_dir()
    assert raw is not None, "resolver get_data_dir() returned None"

    if isinstance(raw, (list, tuple)):
        raw_paths = [Path(str(item)).expanduser() for item in raw]
    else:
        raw_paths = [Path(str(raw)).expanduser()]
    assert raw_paths, "resolver get_data_dir() returned an empty result"

    directories = _precedence_directories(contract, resolver)
    assert directories, (
        "no precedence directories could be resolved from contract precedence "
        f"{contract.get('precedence')!r} or the resolver module"
    )

    normalized_dirs = [_norm(d) for d in directories]
    for resolved in raw_paths:
        candidates = (
            [resolved]
            if resolved.is_absolute()
            else [base / resolved for base in _relative_bases()]
        )
        for candidate in candidates:
            parent = _norm(candidate.parent)
            self_dir = _norm(candidate)
            if parent in normalized_dirs:
                return  # resolved path lives directly inside a precedence directory
            if self_dir in normalized_dirs:
                return  # resolver returned the precedence directory itself
            if any(self_dir == d or d in self_dir.parents for d in normalized_dirs):
                return  # resolved path lives inside a precedence directory

    pytest.fail(
        "resolver get_data_dir() returned "
        f"{[str(p) for p in raw_paths]!r}; its parent does not match any "
        f"precedence directory {[str(d) for d in normalized_dirs]!r} "
        f"(contract precedence: {contract.get('precedence')!r})"
    )


# ---------------------------------------------------------------------------
# Script runner: `python tests/test_contract_env.py` runs the drift check
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
