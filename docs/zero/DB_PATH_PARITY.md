# Cross-Language DB Path Parity

## Overview

This document specifies the unified database path resolution logic shared across Rust, TypeScript, and Python implementations. The goal is **byte-identical path resolution** under identical environment conditions.

## Precedence Rules (Highest to Lowest)

| Priority | Env Variable | Behavior |
|----------|--------------|----------|
| 1 | `FRANK3_DATA` | Treated as **directory**, appends `unified.db` |
| 2 | `F3_DB_PATH` | If path has DB extension (`.db`, `.sqlite`, `.sqlite3`, `.db3`) → use as file; else treat as directory and append `unified.db` |
| 3 | `XDG_DATA_HOME` | Appends `frankenstein3/unified.db` |
| 4 | `HOME` | Appends `.local/share/frankenstein3/unified.db` |
| 5 | `USERPROFILE` (Windows) | Appends `AppData/Local/frankenstein3/unified.db` |

## Implementation Locations

| Language | File | Function |
|----------|------|----------|
| Rust | `src/zero/entity.rs` | `resolve_db_path()` |
| TypeScript | `agent-sdk/src/zero/health.ts` | `resolveDbPath()` |
| Python | `plugins/frankenstein3/f3_paths.py` | `resolve_db_path()` / `_resolve_data_dir()` |

## Test Matrix

The parity test (`plugins/frankenstein3/tests/test_crosslang_db_path.py`) exercises **8 environment combinations**:

| Test Case | Env Vars Set | Expected Path |
|-----------|--------------|---------------|
| FRANK3_DATA only | `FRANK3_DATA=/custom/frank3/data` | `/custom/frank3/data/unified.db` |
| F3_DB_PATH as directory | `F3_DB_PATH=/custom/f3/db/dir` | `/custom/f3/db/dir/unified.db` |
| F3_DB_PATH as file | `F3_DB_PATH=/custom/f3/db.sqlite` | `/custom/f3/db.sqlite` |
| XDG_DATA_HOME only | `XDG_DATA_HOME=/xdg/data` | `/xdg/data/frankenstein3/unified.db` |
| HOME only | `HOME=/home/testuser` | `/home/testuser/.local/share/frankenstein3/unified.db` |
| FRANK3_DATA wins | `FRANK3_DATA=/frank3/wins`, `F3_DB_PATH=/f3/loses` | `/frank3/wins/unified.db` |
| F3_DB_PATH wins | `F3_DB_PATH=/f3/wins`, `XDG_DATA_HOME=/xdg/loses` | `/f3/wins/unified.db` |
| USERPROFILE fallback | `USERPROFILE=C:\Users\testuser` | `C:\Users\testuser\AppData\Local\frankenstein3\unified.db` |

## Running Tests

### All Languages (CI)
```bash
# GitHub Actions runs all three + parity test automatically
```

### Local Development

**Rust:**
```bash
cargo test --test crosslang_db_path
```

**TypeScript:**
```bash
cd agent-sdk && npm test
```

**Python:**
```bash
cd plugins/frankenstein3 && python -m pytest tests/test_f3_paths.py -v
```

**Cross-Language Parity (requires all three runtimes):**
```bash
cd plugins/frankenstein3 && python tests/test_crosslang_db_path.py
```

## Adding New Test Cases

1. Add the test case to `TEST_CASES` in `test_crosslang_db_path.py`
2. Add corresponding unit tests in:
   - `plugins/frankenstein3/tests/test_crosslang_db_path.rs` (Rust)
   - `agent-sdk/src/zero/health.test.ts` (TypeScript)
   - `plugins/frankenstein3/tests/test_f3_paths.py` (Python)
3. Ensure all three resolvers handle the new case identically

## Invariants

- **ON_VIOLATION**: If any resolver returns a different path for the same env, the parity test fails → CI blocks merge
- No resolver may introduce additional precedence levels
- All resolvers must treat `F3_DB_PATH` with DB extension as a file path
- Windows paths must use backslashes when `USERPROFILE` is set (handled by each language's path library)
```
```
module db_path_parity {
  architecture CrossLanguageParity {
    stateAuthority: "FRANK3_DATA > F3_DB_PATH > XDG_DATA_HOME > HOME > USERPROFILE"
    path RustResolver -> TSResolver -> PythonResolver -> ParityAssertion
  }

  invariant PRECEDENCE_ORDER {
    FRANK3_DATA > F3_DB_PATH > XDG_DATA_HOME > HOME > USERPROFILE
  } ON_VIOLATION -> ParityTestFailure

  invariant BYTE_IDENTICAL_PATHS {
    RustResolver(env) == TSResolver(env) == PythonResolver(env)
  } ON_VIOLATION -> ParityTestFailure

  invariant F3_DB_PATH_FILE_DETECTION {
    has_db_extension(F3_DB_PATH) => use_as_file
    !has_db_extension(F3_DB_PATH) => treat_as_directory
  } ON_VIOLATION -> ParityTestFailure

  fn resolve_db_path(env: Env) -> Path {
    match env {
      FRANK3_DATA => join(FRANK3_DATA, "unified.db")
      F3_DB_PATH => if has_db_ext(F3_DB_PATH) then F3_DB_PATH else join(F3_DB_PATH, "unified.db")
      XDG_DATA_HOME => join(XDG_DATA_HOME, "frankenstein3", "unified.db")
      HOME => join(HOME, ".local", "share", "frankenstein3", "unified.db")
      USERPROFILE => join(USERPROFILE, "AppData", "Local", "frankenstein3", "unified.db")
      _ => panic("No resolvable path")
    }
  }

  hypothesis H_PARITY_HOLDS {
    forall env in TEST_MATRIX: resolve_db_path_rust(env) == resolve_db_path_ts(env) == resolve_db_path_py(env)
  }

  promotion MEASURED -> VERIFIED_OUTCOME -> CONTROL_INFLUENCE
}
