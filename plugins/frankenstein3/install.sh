#!/usr/bin/env bash
# FranKenstein 3.0 installer. Idempotent, non-interactive, no network, never edits settings.json.
# Works from wherever the bundle was unpacked: registers THIS folder as a local marketplace.
# Portable: no hard-coded user paths, no machine names.
# Data dir precedence (UNIFIED with the Python resolver):
#   1) FRANK3_DATA
#   2) FRANKENSTEIN3_ROOT
#   3) F3_DB_PATH (derived: parent dir for a file, the dir itself for a directory)
#   4) CLAUDE_PLUGIN_DATA
#   5) XDG_DATA_HOME/frankenstein3
#   6) $HOME/.local/share/frankenstein3
#   7) $USERPROFILE/AppData/Local/frankenstein3
# PLUGIN_ROOT is used ONLY to locate plugin code (read-only). Never for data.
# The installer writes unified.db to the user-scoped data dir, never under the plugin root.
# Hook environment contract (consumed by Rust/TS/plugin via docs/zero/contract_env.json):
#   FRANK3_DATA, CLAUDE_PLUGIN_DATA, F3_DB_PATH, F3_DRY_RUN, XDG_DATA_HOME, HOME
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse arguments: --dry-run sets F3_DRY_RUN so it passes through the single normalization
for arg in "$@"; do
  case "$arg" in
    --dry-run)
      export F3_DRY_RUN="true"
      ;;
    -h|--help)
      echo "Usage: $0 [--dry-run]"
      echo "  --dry-run  Resolve and validate paths, but do not create directories or register plugin"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: $0 [--dry-run]" >&2
      exit 1
      ;;
  esac
done

# Normalize F3_DRY_RUN to '1' (truthy) or '0' (falsy) using the unified truthy set:
#   truthy  = {'1','true','yes','on'}  (case-insensitive)
#   falsy   = {'0','false','no','off',''} (case-insensitive)
# This matches Python's _normalize_dry_run() in f3_pfade.py exactly.
# UNKNOWN values are an ERROR (fail-closed): refuse/abort, never default to proceed.
_normalize_f3_dry_run() {
  local raw="${1:-}"
  local lower
  lower="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
  case "$lower" in
    1|true|yes|on)
      printf '1'
      ;;
    0|false|no|off|"")
      printf '0'
      ;;
    *)
      # Unknown values: fail-closed - error out, do not default to falsy
      echo "ERROR: F3_DRY_RUN has invalid value '$raw' (allowed: 1|true|yes|on|0|false|no|off|empty)" >&2
      return 1
      ;;
  esac
}

# Single normalized dry-run flag computed once at script entry.
# Combines --dry-run flag (which sets F3_DRY_RUN=true) and F3_DRY_RUN env var.
# The normalized value ('1' or '0') is exported as F3_DRY_RUN; there is no
# separate IS_DRY_RUN (the hook contract knows only F3_DRY_RUN as the mode flag).
F3_DRY_RUN="$(_normalize_f3_dry_run "${F3_DRY_RUN:-}")" || exit 1
export F3_DRY_RUN

# PLUGIN_ROOT is honored ONLY for locating plugin code (read-only).
# It does NOT influence data directory resolution.
if [ -n "${PLUGIN_ROOT:-}" ]; then
  ROOT="$(cd "${PLUGIN_ROOT}" 2>/dev/null && pwd)" || { echo "FAIL: cannot access PLUGIN_ROOT" >&2; exit 1; }
else
  ROOT="$HERE"
fi

if [ ! -f "$ROOT/.claude-plugin/plugin.json" ]; then
  ROOT="$(cd "$HERE/.." 2>/dev/null && pwd)" || ROOT="$HERE"
fi
[ -f "$ROOT/.claude-plugin/plugin.json" ] || { echo "FAIL: plugin.json not found next to install.sh" >&2; exit 1; }

# --- portable path helpers (no host-specific literals) -------------------------

_home_dir() {
  if [ -n "${HOME:-}" ]; then
    printf '%s' "$HOME"
    return 0
  fi
  if [ -n "${USERPROFILE:-}" ]; then
    printf '%s' "$USERPROFILE"
    return 0
  fi
  return 1
}

# Expand a leading '~' against $HOME (or $USERPROFILE). No other rewriting.
expand_tilde() {
  local raw="$1"
  local home
  case "$raw" in
    "~")
      home="$(_home_dir)" || { echo "FAIL: HOME/USERPROFILE not set; cannot expand '~'" >&2; return 1; }
      printf '%s' "$home"
      ;;
    "~/"*)
      home="$(_home_dir)" || { echo "FAIL: HOME/USERPROFILE not set; cannot expand '~/' path" >&2; return 1; }
      printf '%s/%s' "$home" "${raw:2}"
      ;;
    *)
      printf '%s' "$raw"
      ;;
  esac
}

# Make a path absolute without requiring it to exist and without resolving symlinks.
to_absolute() {
  local raw="$1"
  case "$raw" in
    /*)
      printf '%s' "$raw"
      ;;
    *)
      printf '%s/%s' "$PWD" "$raw"
      ;;
  esac
}

# Tagged union for path kind: 'file' | 'directory' (filesystem first, suffix second).
infer_path_kind() {
  local p="$1"
  local lower
  if [ -d "$p" ]; then
    printf 'directory'
    return 0
  fi
  if [ -f "$p" ]; then
    printf 'file'
    return 0
  fi
  lower="$(printf '%s' "$p" | tr '[:upper:]' '[:lower:]')"
  case "$lower" in
    *.db|*.sqlite|*.sqlite3|*.db3)
      printf 'file'
      ;;
    *)
      printf 'directory'
      ;;
  esac
}

# Data root derived from a DB path: parent dir for a file, the dir itself for a dir.
data_root_from_db_path() {
  local p kind
  p="$(expand_tilde "$1")" || return 1
  kind="$(infer_path_kind "$p")"
  if [ "$kind" = "file" ]; then
    dirname "$p"
  else
    printf '%s' "$p"
  fi
}

# Portable temp directory: explicit fallback chain (TMPDIR -> TEMP -> TMP), fail-closed if none set.
# Used for --dry-run temp paths and any other transient files.
# No hard-coded /tmp fallback.
temp_dir() {
  local base="${TMPDIR:-${TEMP:-${TMP:-}}}"
  if [ -z "$base" ] || [ ! -d "$base" ]; then
    echo "FAIL: No temporary directory found (set TMPDIR, TEMP, or TMP to an existing directory)" >&2
    return 1
  fi
  printf '%s' "$base"
}

# Data dir resolution with UNIFIED precedence (matches f3_pfade.py exactly).
# Prints ONLY the resolved path on stdout. On error, prints to stderr and returns non-zero.
resolve_data_dir() {
  local raw=""

  # Unified dry-run mode (either --dry-run flag or F3_DRY_RUN env var)
  if [ "$F3_DRY_RUN" = "1" ]; then
    if [ -n "${F3_DB_PATH:-}" ]; then
      # Fixture mode: explicit F3_DB_PATH provided (test-controlled)
      raw="$(data_root_from_db_path "$F3_DB_PATH")" || return 1
    else
      # Installer dry-run: use temp directory (fail-closed if no temp env var set)
      local tmp_base
      tmp_base="$(temp_dir)" || return 1
      raw="${tmp_base}/frankenstein3-dryrun-$$"
    fi
  # Normal resolution precedence
  elif [ -n "${FRANK3_DATA:-}" ]; then
    raw="${FRANK3_DATA}"
  elif [ -n "${FRANKENSTEIN3_ROOT:-}" ]; then
    raw="${FRANKENSTEIN3_ROOT}"
  elif [ -n "${F3_DB_PATH:-}" ]; then
    raw="$(data_root_from_db_path "$F3_DB_PATH")" || return 1
  elif [ -n "${CLAUDE_PLUGIN_DATA:-}" ]; then
    raw="${CLAUDE_PLUGIN_DATA}"
  elif [ -n "${XDG_DATA_HOME:-}" ]; then
    raw="${XDG_DATA_HOME}/frankenstein3"
  elif [ -n "${HOME:-}" ]; then
    raw="${HOME}/.local/share/frankenstein3"
  elif [ -n "${USERPROFILE:-}" ]; then
    raw="${USERPROFILE}/AppData/Local/frankenstein3"
  else
    echo "FAIL: cannot resolve data dir: set FRANK3_DATA, FRANKENSTEIN3_ROOT, F3_DB_PATH, CLAUDE_PLUGIN_DATA, XDG_DATA_HOME, HOME or USERPROFILE" >&2
    return 1
  fi

  raw="$(expand_tilde "$raw")" || return 1
  raw="$(to_absolute "$raw")"
  printf '%s' "$raw"
}

DATA=""
if ! DATA="$(resolve_data_dir)"; then
  exit 1
fi

# DRY_RUN GUARD: single unified flag (F3_DRY_RUN) covers both --dry-run flag and F3_DRY_RUN env var.
# If active, print info and exit BEFORE any writes.
if [ "$F3_DRY_RUN" = "1" ]; then
  echo "DRY-RUN: Data dir would be: $DATA"
  echo "DRY-RUN: Plugin root: $ROOT"
  echo "DRY-RUN: Self-check, database initialization, and registration skipped."
  exit 0
fi

mkdir -p "$DATA" || { echo "FAIL: cannot create $DATA" >&2; exit 1; }

DB_PATH="$DATA/unified.db"

chmod +x "$ROOT"/scripts/*.py "$ROOT"/scripts/star/*.py 2>/dev/null || true

# Initialise a fresh database from the bundled empty schema (stdlib only, no network).
if [ ! -f "$DB_PATH" ] && [ -f "$ROOT/daten/schema_leer.sql" ]; then
  if command -v python3 >/dev/null 2>&1; then
    if python3 - "$DB_PATH" "$ROOT/daten/schema_leer.sql" <<'PY'
import pathlib
import sqlite3
import sys

db_path, schema_path = sys.argv[1], sys.argv[2]
sql = pathlib.Path(schema_path).read_text(encoding="utf-8")
conn = sqlite3.connect(db_path)
try:
    conn.executescript(sql)
    conn.commit()
finally:
    conn.close()
PY
    then
      echo "Initialised database: $DB_PATH"
    else
      echo "WARN: could not initialise $DB_PATH from bundled schema" >&2
    fi
  else
    echo "WARN: python3 not found; database not initialised" >&2
  fi
fi

# Run the self-check with the resolved data dir available via env.
# Both FRANK3_DATA and CLAUDE_PLUGIN_DATA are set so runtime sees the same dir.
STATUS_SCRIPT=""
for candidate in "$ROOT/scripts/status.py" "$ROOT/tests/status.py"; do
  if [ -f "$candidate" ]; then
    STATUS_SCRIPT="$candidate"
    break
  fi
done

if [ -n "$STATUS_SCRIPT" ] && command -v python3 >/dev/null 2>&1; then
  if ! FRANK3_DATA="$DATA" CLAUDE_PLUGIN_DATA="$DATA" F3_DB_PATH="$DB_PATH" python3 "$STATUS_SCRIPT"; then
    echo "WARN: self-check reported a problem (see table above)" >&2
  fi
else
  echo "INFO: status self-check not available in this bundle (status: UNKNOWN)"
fi

# Registration is best effort: a missing or refusing 'claude' CLI must not break the
# portable install (the user can register the marketplace manually).
if command -v claude >/dev/null 2>&1; then
  set +o pipefail
  claude plugin marketplace add "$ROOT" 2>&1 | tail -2 || true
  set -o pipefail
  claude plugin install frankenstein3@frankenstein3 2>&1 | tail -2 || true
  echo "Registered (best effort). Restart Claude Code (or run /plugin reload)."
else
  echo "'claude' CLI not on PATH. Run these two commands inside Claude Code:"
  echo "  /plugin marketplace add $ROOT"
  echo "  /plugin install frankenstein3@frankenstein3"
fi
echo "Data dir: $DATA"
echo "DB path: $DB_PATH"
