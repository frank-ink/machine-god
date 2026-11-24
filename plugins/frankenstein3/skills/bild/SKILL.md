---
name: bild
description: Bilder mit dem ChatGPT-Bildstudio erzeugen und iterativ bearbeiten (Bereiche markieren, beschreiben, zurueck an ChatGPT). Nutzen bei "mach ein Bild", "Bild bearbeiten", "Bildstudio", /bild.
---
# bild – ChatGPT-Bildstudio

Dienst `omega-bildstudio` (systemd --user, 127.0.0.1:18796), Code `~/omega-browser/studio/`, CLI `bild` (= `studio/bild.py`).

## Ablauf
- Studio oeffnen: `bild url` -> URL (einmalig, 90 s) im Browser-Pane oeffnen (`preview_start` mit `url`) oder `bild` fuer ein Chrome-App-Fenster. Die URL nicht loggen.
- Erzeugen: `bild generate "Prompt" [-n 2] [--style tech-noir]` -> Pfad(e). Dauer ~1 min pro Bild.
- Bearbeiten: `bild edit NAME --region 10%,20%,30%,40%:"Beschreibung" [--region ...] [--general "..."]` -> Pfad. Bis zu 6 Bereiche; ChatGPT bekommt Original + markierte Version.
- Weiteres: `bild variation NAME`, `bild list [-q Suche]`, `bild show NAME` (Versionskette), `bild export NAME --fmt webp --scale 0.5 -o Datei`, `bild upload DATEI`, `bild polish "Prompt"` (Free-Pool), `bild status`.
- `--json` fuer maschinenlesbare Ausgabe, `--no-wait` nur einreihen.

## Grenzen / Regeln
- Exit 2: ChatGPT lieferte kein Bild (Rueckfrage/Text) – Text wiedergeben, Prompt praezisieren. Exit 3: Wartezeit, Job laeuft im Studio weiter, Bild erscheint spaeter als "Nachgeliefert".
- ChatGPT-Konto gehoert Gabriel: keine Anmeldung, keine Einstellungen, nur Bild-Prompts.
- Jede Erzeugung/Bearbeitung ist eine echte Nachricht im ChatGPT-Bildchat (Limits des Kontos): nicht in Schleifen feuern, Varianten (-n) sparsam.
- Keine Screenshots der UI (Retina-Regel): Seitentext/`read_page` nutzen.
- Studio-Schluessel liegt in `~/omega-browser/run/studio_key` (600): nie ausgeben.
