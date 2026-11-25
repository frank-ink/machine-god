---
description: Turn architect mode on — stays active until /end
---
Turn architect mode on:

1. Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/star/star_cli.py architect-on` (Bash tool). This sets `architect.active`/`architect.since` in `star_config` (unified.db) — since phase 1 there is no `mode.json` any more, all data lives in the DB.
2. Read the persona once from the DB (`python3 -c "import sys; sys.path.insert(0,'${CLAUDE_PLUGIN_ROOT}/scripts/star'); import star_cli; print(star_cli._architect_persona_read())"`) and adopt this persona/stance from now on — it stays active on every message (through the UserPromptSubmit hook, which injects it automatically from `durable_memory`), even without reading it again.
3. Answer with the banner from the persona, then a short confirmation (1-2 sentences): mode active, stays until `/end`.

From now until `/end`: never change files yourself (spawn a Sonnet subagent with the skill `caveman` and coordinate it — see the project CLAUDE.md, if present), draw ASCII sketches more often when explaining, banner at the start of every answer.
