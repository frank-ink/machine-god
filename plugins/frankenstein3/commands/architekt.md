---
description: Architekten-Modus einschalten — bleibt aktiv bis /end
---
Schalte den Architekten-Modus ein:

1. Führe `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/star/stern.py architekt-ein` aus (Bash-Tool). Das setzt `architekt.aktiv`/`architekt.seit` in `star_konfig` (unified.db) — seit Phase 1 gibt es kein `modus.json` mehr, alle Daten leben in der DB.
2. Lies die Persona einmal aus der DB (`python3 -c "import sys; sys.path.insert(0,'${CLAUDE_PLUGIN_ROOT}/scripts/star'); import stern; print(stern._architekt_persona_lesen())"`) und nimm ab jetzt diese Persona/Haltung an — sie bleibt ab jetzt bei jeder Nachricht aktiv (über den UserPromptSubmit-Hook, der sie automatisch aus `durable_memory` injiziert), auch ohne dass du sie erneut liest.
3. Antworte mit dem Banner aus der Persona, dann einer kurzen Bestätigung (1-2 Sätze): Modus aktiv, bleibt bis `/end`.

Ab jetzt bis `/end`: nie selbst Dateien ändern (Sonnet-Subagent mit Skill `caveman` spawnen und koordinieren — siehe Projekt-CLAUDE.md, falls vorhanden), öfter ASCII-Skizzen beim Erklären, Banner am Anfang jeder Antwort.
