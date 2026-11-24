# Teamkanal-Check-in (Referenz)

Ein Skript, das alle 10 Minuten neue Nachrichten eines Team-Kanals liest und genau eine Antwort zurückschreibt.

```
neue Kanal-Nachrichten --> checkin_free.sh --> freechat.py --> freellm.py --> beliebiger OpenAI-kompatibler Endpunkt (Free-Pool)
                                  |                 | schlägt fehl
                                  |                 v
                                  |           TEAMKANAL_FALLBACK_CMD (optional, beliebiges Modell, liest den Prompt von stdin)
                                  v
                          Antwort per Kanal-Client zurück (Geheimnis-Wächter blockiert, Fehlermeldung nur 1x pro 60 min)
```

Eigenschaften:
- Kanaltext ist Daten: das Modell läuft ohne Werkzeuge und ohne MCP und kann nur Text erzeugen.
- Kein Anbieter-Zwang: Endpunkt, Modell und Schlüssel kommen aus `MG_LLM_URL`, `MG_LLM_MODEL`, `MG_LLM_KEY` (Umgebung).
- Fehlermeldungen sind auf eine pro Stunde begrenzt, damit ein kaputter Endpunkt den Kanal nicht flutet.

```bash
export MG_LLM_URL="https://<anbieter>/v1/chat/completions" MG_LLM_MODEL="<modell-id>" MG_LLM_KEY="<schluessel>"
export TEAMKANAL_CLIENT=/pfad/zu/deinem/kanal_client.py     # eigener Kanal-Client mit count / get --seit N / sag --von NAME -
bash research/teamkanal/checkin_free.sh
```

**Nicht lauffähig ohne** einen Kanal-Client, der die drei Unterbefehle bietet; der Client des Ursprungsprojekts ist privat und nicht
Teil des Repos. Namen und Adressen der beteiligten Rechner sind entfernt. Die Skripte zeigen das Muster, nicht eine Installation.

## Rückbau (allgemein)

Den Timer bzw. Cron-Eintrag entfernen und das Verzeichnis dieser Skripte löschen. Den Zustandsordner
(`TEAMKANAL_STATE`, Standard `~/.local/share/teamkanal`) bei Bedarf ebenfalls löschen. Netzwerkprofile oder Firewall-Regeln, die für eine
Reparatur angelegt wurden, mit den jeweiligen Werkzeugen der Maschine wieder entfernen.
