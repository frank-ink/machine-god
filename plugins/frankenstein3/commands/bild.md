---
description: ChatGPT-Bildstudio oeffnen (Bild erzeugen, Bereiche markieren, bearbeiten) oder per CLI generieren/bearbeiten
argument-hint: [Prompt | edit NAME --region x,y,w,h:Text]
---
Bildstudio (`bild`, Dienst `omega-bildstudio`, nur Loopback). Argumente: $ARGUMENTS

1. Ohne Argumente: `bild url` ausfuehren (Bash; startet den Dienst bei Bedarf, gibt eine einmalige URL aus, 90 s gueltig) und diese URL mit `mcp__Claude_Browser__preview_start` (Parameter `url`) im Browser-Pane oeffnen. Die URL nicht weiter ausgeben oder speichern. Danach in einem Satz sagen, dass das Studio offen ist (Erzeugen / Bearbeiten / Info rechts, Pinsel/Rechteck/Lasso im Bild).
2. Mit Prompt-Text: `bild generate "<Text>"` (Bash, dauert ca. 1 Minute, im Hintergrund laufen lassen wenn laenger als 2 Minuten erwartet). Ausgabe = absoluter Dateipfad; Bild mit Read anzeigen. Anschliessend anbieten, es im Studio zu oeffnen (`bild url <NAME>`).
3. Mit `edit NAME --region x,y,w,h[:Text]` (mehrere `--region` moeglich, Prozent erlaubt): `bild edit ...` ausfuehren, Pfad ausgeben.
4. Fehler zuerst nennen (Exit 2 = ChatGPT lieferte kein Bild, `ChatGPT sagt:` wiedergeben; Exit 3 = Wartezeit; Dienst-Probleme: `bild status`).

Regeln: Das ChatGPT-Konto/-Fenster gehoert Gabriel: nur die Bild-Prompts senden, die das Studio vorsieht; nichts einloggen oder umstellen. Keine Screenshots (Retina-Regel): Studio-Zustand per Seitentext/read_page pruefen. Prompt-Verbesserung (`bild polish`) laeuft ueber den Free-Pool (0 Claude-Tokens).
