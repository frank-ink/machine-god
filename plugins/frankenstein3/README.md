# Frankenstein 3.0 - Claude-Code-Plugin

Ein Zip, selbstenthalten. Kein Netz, keine LLM-Aufrufe, keine Geheimnisse.

## Plugin-Metadaten
- **Name**: frankenstein3
- **Version**: 3.0.0
- **Author**: Frankenstein Team
- **Marketplace**: frankenstein3@frankenstein3

Diese Felder entsprechen `plugin.json` und `marketplace.json`.

## Portabilitaet
Keine hardcodierten Pfade und keine Maschinennamen. Alle Pfade werden zur Laufzeit aus Umgebungsvariablen oder dem Speicherort des Plugins selbst aufgeloest.

### Plugin-Wurzel
`$PLUGIN_ROOT` (falls gesetzt), sonst der Ordner, der `install.sh` enthaelt (automatisch erkannt ueber `.claude-plugin/plugin.json`).

### Datenordner: genau eine Aufloesungsreihenfolge (XDG-konform)
Installer (`install.sh`) und Python (`scripts/star/f3_pfade.py`) loesen den Datenordner nach derselben Reihenfolge auf. Der erste passende Eintrag gewinnt:

1. `$FRANK3_DATA` - muss ein absoluter Pfad sein.
2. `$CLAUDE_PLUGIN_DATA` - muss ein absoluter Pfad sein.
3. `$XDG_DATA_HOME/frankenstein3` - XDG Base Directory Specification.
4. `~/.local/share/frankenstein3` - XDG-Fallback, wenn `$XDG_DATA_HOME` nicht gesetzt.

Es gibt keine weitere Aufloesungsregel.

Die `unified.db` wird aus dem mitgelieferten Schema `daten/schema_leer.sql` frisch angelegt. `~/.claude/star` wird nie gelesen oder veraendert. Die Datenbank wird niemals unterhalb des Plugin-Roots geschrieben.

## Installation auf einer anderen Maschine
1. Den Plugin-Ordner (alles unter `plugins/frankenstein3/`) auf die Zielmaschine kopieren, z. B. in ein beliebiges Verzeichnis `$PLUGIN_DIR`.
2. Optional: `export PLUGIN_ROOT=$PLUGIN_DIR` oder `export FRANK3_DATA=/pfad/zum/datenordner` oder `export CLAUDE_PLUGIN_DATA=/pfad/zum/datenordner` oder `export XDG_DATA_HOME=/pfad/zum/xdg` setzen. Ohne gesetzte Variablen wird der Datenordner nach der oben dokumentierten Reihenfolge bestimmt.
3. `bash $PLUGIN_DIR/install.sh` ausfuehren.
   - Fuer einen Trockenlauf (nur Pfade anzeigen, nichts aendern): `bash $PLUGIN_DIR/install.sh --dry-run`
4. In Claude Code:
   `/plugin marketplace add $PLUGIN_DIR`
   `/plugin install frankenstein3@frankenstein3`
   (Falls die `claude` CLI auf PATH ist, erledigt `install.sh` das automatisch.)
5. Neustart von Claude Code (oder `/plugin reload`).

## Pruefen
`python3 scripts/status.py` - PASS/FAIL-Tabelle.
`python3 -m py_compile scripts/*.py scripts/star/*.py` - alle Dateien kompilieren fehlerfrei.
`python3 -m unittest discover -s tests` - prueft die dokumentierte Datenordner-Reihenfolge der README.
`bash install.sh --dry-run` - validiert Pfadaufloesung ohne Aenderungen.

## Enthalten
- Hooks: SessionStart (Digest + Reentry), PostToolUse (Raum-Puls), SessionEnd (Raum verlassen).
- Befehle `/architekt`, `/end`; Skills `caveman`, `frank3-status`.

## Nicht enthalten
GRID10-Kognition, Organe, Tresor/Einrichtung und Sprachmodus: nicht portabel, fehlen bewusst.
