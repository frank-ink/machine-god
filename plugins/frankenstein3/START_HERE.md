# START HERE  (Frankenstein 3.0)

## Instructions for the Claude reading this
The user dropped this zip and wants the plugin installed. Do exactly this, nothing else:
1. Unzip it to any directory, e.g. `$PLUGIN_DIR/plugin`: `mkdir -p "$PLUGIN_DIR/plugin" && unzip -oq <zip-path> -d "$PLUGIN_DIR/plugin"`
2. Run `bash "$PLUGIN_DIR/plugin/install.sh"` (self-check, then registers the plugin; prints the two `/plugin` commands if the `claude` CLI is missing).
3. Run `python3 "$PLUGIN_DIR/plugin/scripts/status.py"`; show the table; the verdict must have 0 FAIL.
4. Tell the user: restart Claude Code (or `/plugin reload`), then `/architect`, `/end`, skill `caveman` are available.
Rules: no network, no extra commands, do not edit `~/.claude/settings.json`, do not read or send any secrets. If a step FAILs, report the exact output; do not guess.
