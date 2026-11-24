#!/usr/bin/env bash
# Frankenstein 3.0 installer. Idempotent, non-interactive, no network, never edits settings.json.
# Works from wherever the zip was unpacked: registers THIS folder as a local marketplace.
# Portable: no hard-coded /home paths, no machine names. Data dir precedence (UNIFIED with runtime):
#   1) FRANK3_DATA
#   2) CLAUDE_PLUGIN_DATA
#   3) XDG_DATA_HOME/frankenstein3
#   4) ~/.local/share/frankenstein3
# PLUGIN_ROOT is used ONLY to locate plugin code (read-only). Never for data.
# The installer writes unified.db to the user-scoped data dir, never under the plugin root.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Parse arguments
DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --dry-run)
      DRY_RUN=true
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

# PLUGIN_ROOT is honored ONLY for locating plugin code (read-only).
# It does NOT influence data directory resolution.
if [ -n "${PLUGIN_ROOT:-}" ]; then
  ROOT="$(cd "${PLUGIN_ROOT}" && pwd)" || { echo "FAIL: cannot access PLUGIN_ROOT ${PLUGIN_ROOT}" >&2; exit 1; }
else
  ROOT="$HERE"
fi

[ -f "$ROOT/.claude-plugin/plugin.json" ] || ROOT="$(cd "$HERE/.." && pwd)"
[ -f "$ROOT/.claude-plugin/plugin.json" ] || { echo "FAIL: plugin.json not found next to install.sh" >&2; exit 1; }

# Data dir resolution with UNIFIED precedence (matches f3_pfade.py exactly).
# Prints ONLY the resolved path on stdout. On error, prints to stderr and returns non-zero.
resolve_data_dir() {
  local raw=""

  # 1) FRANK3_DATA (highest priority, explicit user override)
  if [ -n "${FRANK3_DATA:-}" ]; then
    raw="${FRANK3_DATA}"
  # 2) CLAUDE_PLUGIN_DATA
  elif [ -n "${CLAUDE_PLUGIN_DATA:-}" ]; then
    raw="${CLAUDE_PLUGIN_DATA}"
  # 3) XDG_DATA_HOME/frankenstein3
  elif [ -n "${XDG_DATA_HOME:-}" ]; then
    raw="${XDG_DATA_HOME}/frankenstein3"
  # 4) ~/.local/share/frankenstein3 (XDG default fallback)
  else
    raw="${HOME}/.local/share/frankenstein3"
  fi

  # Expand leading ~ to $HOME
  case "$raw" in
    "~"/*)
      raw="${HOME}/${raw#"~/"}"
      ;;
    "~")
      raw="${HOME}"
      ;;
  esac

  # Ensure parent directory exists (skip in dry-run)
  if [ "$DRY_RUN" = false ]; then
    local parent_dir
    parent_dir="$(dirname "$raw")"
    mkdir -p "$parent_dir" 2>/dev/null || { echo "FAIL: cannot create parent directory $parent_dir" >&2; return 1; }
  fi

  # Resolve to absolute path (handles relative paths)
  local resolved
  resolved="$(cd "$(dirname "$raw")" 2>/dev/null && pwd)/$(basename "$raw")" || { echo "FAIL: cannot resolve data dir ${raw}" >&2; return 1; }

  # Print ONLY the path on stdout
  echo "$resolved"
}

# Call resolve_data_dir without command substitution capturing stderr
DATA=""
if ! DATA="$(resolve_data_dir)"; then
  exit 1
fi

if [ "$DRY_RUN" = true ]; then
  echo "DRY-RUN: Data dir would be: $DATA"
  echo "DRY-RUN: Plugin root: $ROOT"
  echo "DRY-RUN: Self-check and registration skipped."
  exit 0
fi

mkdir -p "$DATA" || { echo "FAIL: cannot create $DATA" >&2; exit 1; }

chmod +x "$ROOT"/scripts/*.py "$ROOT"/scripts/star/*.py 2>/dev/null || true

# Run self-check with the resolved data dir available via env
# Both FRANK3_DATA and CLAUDE_PLUGIN_DATA are set so runtime sees the same dir
FRANK3_DATA="$DATA" CLAUDE_PLUGIN_DATA="$DATA" python3 "$ROOT/scripts/status.py" || { echo "FAIL: self-check (see table)" >&2; exit 1; }

if command -v claude >/dev/null 2>&1; then
  set +o pipefail
  claude plugin marketplace add "$ROOT" 2>&1 | tail -2
  RC="${PIPESTATUS[0]}"
  set -o pipefail
  if [ "$RC" -ne 0 ]; then
    echo "FAIL: marketplace add" >&2
    exit "$RC"
  fi
  claude plugin install frankenstein3@frankenstein3 2>&1 | tail -2 || true
  echo "Registered. Restart Claude Code (or run /plugin reload)."
else
  echo "'claude' CLI not on PATH. Run these two commands inside Claude Code:"
  echo "  /plugin marketplace add $ROOT"
  echo "  /plugin install frankenstein3@frankenstein3"
fi
echo "Data dir: $DATA"
