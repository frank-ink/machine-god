---
description: Architekten-Modus ausschalten, zurück zum Normalmodus
---
Schalte den Architekten-Modus aus:

1. Führe `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/star/stern.py architekt-aus` aus (Bash-Tool). Das setzt `architekt.aktiv=false` in `star_konfig` (unified.db) — seit Phase 1 gibt es kein `modus.json` mehr.
2. Verlasse die Architekten-Persona und das Banner ab jetzt — zurück zum normalen Modus.
3. Bestätige kurz (1 Satz, ohne Banner), dass der Modus jetzt aus ist.

Die generelle Bau-Delegationsregel (nie selbst Dateien ändern, Sonnet-Subagent mit `caveman`) bleibt auch im Normalmodus in Kraft — siehe Projekt-CLAUDE.md, falls vorhanden. Nur Persona und Banner enden hier.
