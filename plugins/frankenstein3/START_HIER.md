# START HERE / START HIER  (Frankenstein 3.0)

## EN - instructions for the Claude reading this
The user dropped this zip and wants the plugin installed. Do exactly this, nothing else:
1. Unzip it to any directory, e.g. `$PLUGIN_DIR/plugin`: `mkdir -p "$PLUGIN_DIR/plugin" && unzip -oq <zip-path> -d "$PLUGIN_DIR/plugin"`
2. Run `bash "$PLUGIN_DIR/plugin/install.sh"` (self-check, then registers the plugin; prints the two `/plugin` commands if the `claude` CLI is missing).
3. Run `python3 "$PLUGIN_DIR/plugin/scripts/status.py"`; show the table; the verdict must have 0 FAIL.
4. Tell the user: restart Claude Code (or `/plugin reload`), then `/architekt`, `/end`, skill `caveman` are available.
Rules: no network, no extra commands, do not edit `~/.claude/settings.json`, do not read or send any secrets. If a step FAILs, report the exact output; do not guess.

## DE - Anweisung an das lesende Claude
Der Nutzer hat dieses Zip abgelegt und will das Plugin installiert haben. Genau das tun, sonst nichts:
1. In ein beliebiges Verzeichnis entpacken, z. B. `$PLUGIN_DIR/plugin`: `mkdir -p "$PLUGIN_DIR/plugin" && unzip -oq <zip-pfad> -d "$PLUGIN_DIR/plugin"`
2. `bash "$PLUGIN_DIR/plugin/install.sh"` ausfuehren (Selbstcheck, dann Registrierung; fehlt die `claude`-CLI, werden die zwei `/plugin`-Befehle ausgegeben).
3. `python3 "$PLUGIN_DIR/plugin/scripts/status.py"` ausfuehren, Tabelle zeigen; Urteil muss 0 FAIL haben.
4. Dem Nutzer sagen: Claude Code neu starten (oder `/plugin reload`), dann gibt es `/architekt`, `/end` und den Skill `caveman`.
Regeln: kein Netz, keine weiteren Befehle, `~/.claude/settings.json` nicht aendern, keine Geheimnisse lesen oder senden. Bei FAIL die genaue Ausgabe melden, nicht raten.
