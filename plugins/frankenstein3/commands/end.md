---
description: Turn architect mode off, back to normal mode
---
Turn architect mode off:

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/star/star_cli.py architect-off` (Bash tool). This sets `architect.active=false` in `star_config` (unified.db) — since phase 1 there is no `mode.json` any more.
2. Drop the architect persona and the banner from now on — back to normal mode.
3. Confirm briefly (1 sentence, no banner) that the mode is now off.

The general build-delegation rule (never change files yourself, Sonnet subagent with `caveman`) stays in force in normal mode as well — see the project CLAUDE.md, if present. Only the persona and the banner end here.
