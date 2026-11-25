#!/usr/bin/env python3
"""
Validation test for docs/zero/contract_env.json against its schema and against
the real data-directory resolver (f3_paths.py :: get_data_dir).

The expected precedence is DERIVED from the resolver implementation (controlled
execution and/or source inspection), never from contract_env.json, so the
assertion cannot be satisfied by editing the contract alone.

Run with: python3 -m pytest docs/zero/test_contract_env.py -v
"""

import ast
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path

CONTRACT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CONTRACT_DIR.parents[1]

# Environment variables that may participate in data-directory resolution.
DATA_DIR_ENV_NAMES = (
    "FRANK3_DATA",
    "CLAUDE_PLUGIN_DATA",
    "XDG_DATA_HOME",
    "HOME",
)

# Variables that are deliberately NOT part of the data-directory precedence.
NON_PRECEDENCE_ENV_NAMES = frozenset({"F3_DB_PATH", "F3_DRY_RUN"})

RESOLVER_FILENAME = "f3_paths.py"
RESOLVER_FUNCTION = "get_data_dir"

SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn", "node_modules", "target", "dist", "build",
    "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache", ".ruff_cache",
})

_RESOLVER_CACHE = {}


def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


# --------------------------------------------------------------------------
# resolver discovery
# --------------------------------------------------------------------------

def _iter_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _iter_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_strings(value)


def _contract_resolver_hints():
    """Strings from contract.sources that point at the resolver file."""
    try:
        contract = load_json(CONTRACT_DIR / "contract_env.json")
    except (OSError, ValueError):
        return []
    hints = []
    for text in _iter_strings(contract.get("sources", {})):
        if RESOLVER_FILENAME in text:
            hints.append(text)
    return hints


def _hint_candidates(hint: str):
    cleaned = hint.strip().strip("`'\"")
    first = cleaned.split("::")[0].strip()
    candidates = [first]
    tokens = first.split()
    if tokens:
        candidates.append(tokens[0])
    candidates.append(Path(first).name)
    return candidates


def _resolve_hint(hint: str):
    for candidate in _hint_candidates(hint):
        if not candidate or RESOLVER_FILENAME not in candidate:
            continue
        path = Path(candidate)
        if path.is_absolute():
            if path.is_file():
                return path
            continue
        for base in (REPO_ROOT, CONTRACT_DIR):
            resolved = base / path
            if resolved.is_file():
                return resolved
    return None


def _iter_resolver_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        if RESOLVER_FILENAME in filenames:
            yield Path(dirpath) / RESOLVER_FILENAME


def _defines_resolver(path: Path) -> bool:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return f"def {RESOLVER_FUNCTION}" in source


def _preferred_roots():
    for rel in (
        "plugins/frankenstein3",
        "docs/zero",
        "src/zero",
        "agent-sdk/src/zero",
        "zero",
    ):
        base = REPO_ROOT / rel
        if base.is_dir():
            yield base


def find_resolver() -> Path:
    """Locate the authoritative f3_paths.py implementing get_data_dir()."""
    if "path" in _RESOLVER_CACHE:
        return _RESOLVER_CACHE["path"]

    for hint in _contract_resolver_hints():
        resolved = _resolve_hint(hint)
        if resolved is not None and _defines_resolver(resolved):
            _RESOLVER_CACHE["path"] = resolved
            return resolved

    for base in _preferred_roots():
        for candidate in sorted(_iter_resolver_files(base)):
            if _defines_resolver(candidate):
                _RESOLVER_CACHE["path"] = candidate
                return candidate

    for candidate in sorted(_iter_resolver_files(REPO_ROOT)):
        if _defines_resolver(candidate):
            _RESOLVER_CACHE["path"] = candidate
            return candidate

    raise AssertionError(
        f"{RESOLVER_FILENAME} defining {RESOLVER_FUNCTION}() was not found under {REPO_ROOT}"
    )


# --------------------------------------------------------------------------
# static (source) derivation of the precedence order
# --------------------------------------------------------------------------

def _resolver_function(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == RESOLVER_FUNCTION:
                return node
    return None


def _collect_env_hits(node, names):
    """Source-ordered env-var names used as call args, tuple/list items or subscripts."""
    hits = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            args = list(sub.args) + [kw.value for kw in sub.keywords]
            for arg in args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value in names:
                    hits.append((arg.lineno, arg.col_offset, arg.value))
        elif isinstance(sub, (ast.Tuple, ast.List)):
            for elt in sub.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str) and elt.value in names:
                    hits.append((elt.lineno, elt.col_offset, elt.value))
        elif isinstance(sub, ast.Subscript):
            sl = sub.slice
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str) and sl.value in names:
                hits.append((sl.lineno, sl.col_offset, sl.value))
    hits.sort()
    ordered = []
    for _, _, value in hits:
        if value not in ordered:
            ordered.append(value)
    return ordered


def _module_precedence_tuple(tree, names):
    for node in tree.body:
        value = None
        if isinstance(node, ast.Assign):
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            value = node.value
        if not isinstance(value, (ast.Tuple, ast.List)):
            continue
        elts = value.elts
        values = [e.value for e in elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        if values and len(values) == len(elts) and all(v in names for v in values):
            return values
    return []


def _source_order(path: Path) -> list:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (OSError, SyntaxError, ValueError):
        return []
    names = set(DATA_DIR_ENV_NAMES)
    func = _resolver_function(tree)
    if func is not None:
        hits = _collect_env_hits(func, names)
        if hits:
            return hits
    tuple_order = _module_precedence_tuple(tree, names)
    if tuple_order:
        return tuple_order
    return _collect_env_hits(tree, names)


def _regex_order(path: Path) -> list:
    """Last-resort static fallback: first textual occurrence inside the resolver."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    segment = source
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        tree = None
    if tree is not None:
        func = _resolver_function(tree)
        if func is not None:
            extracted = ast.get_source_segment(source, func)
            if extracted:
                segment = extracted
    hits = []
    for name in DATA_DIR_ENV_NAMES:
        match = re.search(r"\b" + re.escape(name) + r"\b", segment)
        if match:
            hits.append((match.start(), name))
    hits.sort()
    return [name for _, name in hits]


# --------------------------------------------------------------------------
# behavioural derivation of the precedence order (controlled execution)
# --------------------------------------------------------------------------

def _load_resolver_module(path: Path):
    spec = importlib.util.spec_from_file_location("_f3_paths_contract_probe", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    parent = str(path.parent)
    sys.path.insert(0, parent)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    finally:
        try:
            sys.path.remove(parent)
        except ValueError:
            pass
    return module


def _call_resolver(getter):
    cache_clear = getattr(getter, "cache_clear", None)
    if callable(cache_clear):
        try:
            cache_clear()
        except Exception:
            pass
    try:
        result = getter()
    except Exception:
        return None
    if result is None:
        return None
    try:
        return Path(str(result))
    except Exception:
        return None


def _probe_order(path: Path, tmp_root: Path) -> list:
    """Measure the resolver order by giving each candidate a unique marker dir."""
    backup = dict(os.environ)
    try:
        for var in DATA_DIR_ENV_NAMES:
            os.environ.pop(var, None)
        for var in NON_PRECEDENCE_ENV_NAMES:
            os.environ.pop(var, None)

        # sandbox env for import-time side effects
        for var in DATA_DIR_ENV_NAMES:
            sandbox = tmp_root / ("import_" + var)
            sandbox.mkdir(parents=True, exist_ok=True)
            os.environ[var] = str(sandbox)
        os.environ["F3_DB_PATH"] = str(tmp_root / "import_f3.db")

        module = _load_resolver_module(path)
        if module is None:
            # retry with the original environment (import may depend on real HOME)
            os.environ.clear()
            os.environ.update(backup)
            module = _load_resolver_module(path)
            if module is None:
                return []

        getter = getattr(module, RESOLVER_FUNCTION, None)
        if getter is None or not callable(getter):
            return []

        order = []
        remaining = list(DATA_DIR_ENV_NAMES)
        while remaining:
            for var in DATA_DIR_ENV_NAMES:
                os.environ.pop(var, None)
            markers = {}
            for var in remaining:
                marker = tmp_root / ("probe_" + var)
                marker.mkdir(parents=True, exist_ok=True)
                os.environ[var] = str(marker)
                markers[var] = str(marker)

            result = _call_resolver(getter)
            if result is None:
                break
            real = os.path.realpath(str(result))
            winner = None
            for var in remaining:
                marker = os.path.realpath(markers[var])
                if real == marker or real.startswith(marker + os.sep):
                    winner = var
                    break
            if winner is None or winner in order:
                # no marker matched (or the resolver cached): stop, static fallback remains
                break
            order.append(winner)
            remaining.remove(winner)
        return order
    finally:
        os.environ.clear()
        os.environ.update(backup)


def resolver_precedence(tmp_root: Path) -> list:
    """Expected precedence, derived from the resolver (never from the contract)."""
    path = find_resolver()
    probed = _probe_order(path, tmp_root)
    source = _source_order(path)
    regex = _regex_order(path)
    for candidate in (probed, source, regex):
        if len(candidate) == len(DATA_DIR_ENV_NAMES):
            return candidate
    for candidate in (probed, source, regex):
        if candidate:
            return candidate
    return []


# --------------------------------------------------------------------------
# tests
# --------------------------------------------------------------------------

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
    assert len(hook_writes) == 2, "hook_env_writes must have 2 items"
    assert len(set(hook_writes)) == 2, "hook_env_writes must have unique items"

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
    assert len(pv) == 4, "path_variables must have 4 items"
    assert len(set(pv)) == 4, "path_variables must have unique items"

    # Validate mode_flags
    mf = m["mode_flags"]
    assert isinstance(mf, list), "mode_flags must be array"
    assert len(mf) == 1, "mode_flags must have 1 item"
    assert mf[0] == "F3_DRY_RUN", "mode_flags must be ['F3_DRY_RUN']"

    # Validate resolution_rules
    rr = m["resolution_rules"]
    assert isinstance(rr, dict), "resolution_rules must be object"
    for var in pv:
        assert var in rr, f"resolution_rules missing for {var}"
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


def test_resolver_is_discoverable():
    """The authoritative resolver (f3_paths.py::get_data_dir) must be present."""
    resolver = find_resolver()
    assert resolver.is_file(), f"resolver not found: {resolver}"
    source = resolver.read_text(encoding="utf-8", errors="replace")
    assert f"def {RESOLVER_FUNCTION}" in source, \
        f"{resolver} does not define {RESOLVER_FUNCTION}()"


def test_precedence_matches_f3_paths(tmp_path):
    """Precedence arrays must match f3_paths.py get_data_dir() resolution order.

    The expectation is derived from the resolver implementation itself
    (controlled execution and/or source inspection), never from
    contract_env.json, so this assertion is not self-fulfilling.
    """
    contract_path = Path(__file__).parent / "contract_env.json"
    contract = load_json(contract_path)

    resolver = find_resolver()
    expected_precedence = resolver_precedence(tmp_path)

    assert expected_precedence, \
        f"could not derive data-dir precedence from {resolver}"
    assert set(expected_precedence) == set(DATA_DIR_ENV_NAMES), \
        f"derived precedence has unexpected members: {expected_precedence}"
    assert not (set(expected_precedence) & NON_PRECEDENCE_ENV_NAMES), \
        f"derived precedence must not contain mode/db flags: {expected_precedence}"

    assert contract["precedence"] == expected_precedence, \
        f"precedence mismatch: got {contract['precedence']}, " \
        f"expected {expected_precedence} (derived from {resolver})"
    assert contract["data_dir_precedence"] == expected_precedence, \
        f"data_dir_precedence mismatch: got {contract['data_dir_precedence']}, " \
        f"expected {expected_precedence} (derived from {resolver})"


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

    # Values must match f3_paths.py (4-entry model: F3_DB_PATH removed from hook writes)
    expected_hook_writes = ["FRANK3_DATA", "CLAUDE_PLUGIN_DATA"]
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

    # Path variables (4-entry model: FRANK3_DATA, CLAUDE_PLUGIN_DATA, XDG_DATA_HOME, HOME)
    expected_path_vars = [
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

    # Resolution rules for all 4 path variables
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
    with tempfile.TemporaryDirectory(prefix="contract_env_") as tmp:
        tmp_path = Path(tmp)
        test_contract_validates_against_schema()
        test_resolver_is_discoverable()
        test_precedence_matches_f3_paths(tmp_path)
        test_f3_dry_run_not_in_precedence()
        test_f3_db_path_not_in_precedence()
        test_field_names_match_readme()
        test_admissibility_space_typed_structure()
    print("All contract_env validation tests passed.")
