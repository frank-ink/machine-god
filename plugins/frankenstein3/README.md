# Frankenstein 3.0 - Claude-Code-Plugin

Ein Zip, selbstenthalten. Kein Netz, keine LLM-Aufrufe, keine Geheimnisse.

## Portabilitaet
Keine hardcodierten Pfade und keine Maschinennamen. Alle Pfade werden zur Laufzeit aus Umgebungsvariablen oder dem Speicherort des Plugins selbst aufgeloest.

### Plugin-Wurzel
`$PLUGIN_ROOT` (falls gesetzt), sonst der Ordner, der `install.sh` enthaelt (automatisch erkannt). `$PLUGIN_ROOT` wird in Schritt 3 der Datenordner-Aufloesung ausgewertet.

### Datenordner: genau eine Aufloesungsreihenfolge
Installer (`install.sh`) und Python (`scripts/f3_pfade.py`) loesen den Datenordner nach derselben Reihenfolge auf. Der erste passende Eintrag gewinnt:

1. `$FRANK3_DATA` - muss ein absoluter Pfad sein.
2. `$CLAUDE_PLUGIN_DATA` - muss ein absoluter Pfad sein.
3. `$PLUGIN_ROOT/.frankenstein3` - Datenordner im Plugin-Ordner.
4. `./frankenstein3/.frankenstein3` - Datenordner im Plugin-Ordner `frankenstein3` unter dem aktuellen Arbeitsverzeichnis.

Es gibt keine weitere Aufloesungsregel. Die Schritte 3 und 4 legen den Datenordner im Plugin-Ordner an.

Die `unified.db` wird aus dem mitgelieferten Schema `daten/schema_leer.sql` frisch angelegt. `~/.claude/star` wird nie gelesen oder veraendert.

## Installation auf einer anderen Maschine
1. Den Plugin-Ordner (alles unter `plugins/frankenstein3/`) auf die Zielmaschine kopieren, z. B. nach `/tmp/test-plugin/`.
2. Optional: `export PLUGIN_ROOT=/pfad/zum/plugin` oder `export FRANK3_DATA=/pfad/zum/datenordner` oder `export CLAUDE_PLUGIN_DATA=/pfad/zum/datenordner` setzen. Ohne gesetzte Variablen wird der Datenordner nach der oben dokumentierten Reihenfolge bestimmt (Schritt 3, sonst Schritt 4).
3. `bash install.sh` aus dem Plugin-Ordner ausfuehren.
4. In Claude Code:
   `/plugin marketplace add <entpackter-ordner>`
   `/plugin install frankenstein3@frankenstein3`
   (Falls die `claude` CLI auf PATH ist, erledigt `install.sh` das automatisch.)
5. Neustart von Claude Code (oder `/plugin reload`).

## Enthalten
- Hooks: SessionStart (Digest + Reentry), PostToolUse (Raum-Puls), SessionEnd (Raum verlassen).
- Befehle `/architekt`, `/end`; Skills `caveman`, `frank3-status`.

## Pruefen
`python3 scripts/status.py` - PASS/FAIL-Tabelle.
`python3 -m py_compile scripts/*.py scripts/star/*.py` - alle Dateien kompilieren fehlerfrei.
`python3 -m unittest discover -s tests` - prueft die dokumentierte Datenordner-Reihenfolge der README.

## Nicht enthalten
GRID10-Kognition, Organe, Tresor/Einrichtung und Sprachmodus: nicht portabel, fehlen bewusst.
