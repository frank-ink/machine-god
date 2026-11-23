#!/usr/bin/env bash
# Frankenstein 3.0 installer. Idempotent, non-interactive, no network, never edits settings.json.
# Works from wherever the zip was unpacked: registers THIS folder as a local marketplace.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# PLUGIN_ROOT is honored before defaulting to the installer's own location.
if [ -n "${PLUGIN_ROOT:-}" ]; then
  ROOT="$(cd "${PLUGIN_ROOT}" && pwd)" || { echo "FAIL: cannot access PLUGIN_ROOT ${PLUGIN_ROOT}" >&2; exit 1; }
else
  ROOT="$HERE"
fi

[ -f "$ROOT/.claude-plugin/plugin.json" ] || ROOT="$(cd "$HERE/.." && pwd)"
[ -f "$ROOT/.claude-plugin/plugin.json" ] || { echo "FAIL: plugin.json not found next to install.sh" >&2; exit 1; }

# Data dir: resolve FRANK3_DATA / CLAUDE_PLUGIN_DATA to an absolute path.
# Default lives under PLUGIN_ROOT when set, otherwise under the resolved ROOT.
DATA_ROOT="${PLUGIN_ROOT:-$ROOT}"
[ -n "$DATA_ROOT" ] || DATA_ROOT="$ROOT"
DATA_DEFAULT="$(cd "$DATA_ROOT" && pwd)/.frankenstein3"
RAW_DATA="${FRANK3_DATA:-${CLAUDE_PLUGIN_DATA:-"$DATA_DEFAULT"}}"
DATA="$(cd "$(dirname "$RAW_DATA")" 2>/dev/null && pwd)/$(basename "$RAW_DATA")" || { echo "FAIL: cannot resolve data dir ${RAW_DATA}" >&2; exit 1; }
mkdir -p "$DATA" || { echo "FAIL: cannot create $DATA" >&2; exit 1; }

chmod +x "$ROOT"/scripts/*.py "$ROOT"/scripts/star/*.py 2>/dev/null || true

python3 "$ROOT/scripts/status.py" || { echo "FAIL: self-check (see table)" >&2; exit 1; }

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
