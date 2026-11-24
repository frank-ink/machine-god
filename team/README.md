# Dev-Team (Referenz)

Fünf Rollen als **modellneutrale Prompts**: Leiter (die Hauptsitzung) plus vier Mitglieder. Die Dateien sind einfache Markdown-Rollenbeschreibungen
(mit kleinem YAML-Kopf); sie laufen mit jedem Chat-Modell, auch mit Free-Pool-Modellen.

| Rolle | Datei | Aufgabe |
|---|---|---|
| Architekt | `agents/team-architekt.md` | Design, Schnittstellen, Testplan, Fehlerpfade; schreibt keinen Code |
| Bauer | `agents/team-bauer.md` | Ursache zuerst, dann Minimalbau |
| Prüfer | `agents/team-pruefer.md` | unabhängige Prüfung von Diff und Tests, nie die eigene Arbeit |
| Prüfer+ | `agents/team-pruefer-plus.md` | zweite Prüfung nur bei nicht-trivialer Änderung, mit einem stärkeren Modell, falls eines konfiguriert ist |
| Wächter | `agents/team-waechter.md` | Sicherheit, Geheimnisse, Zerstörendes, Freigabe-Tore |

Dokumente: `TEAM.md` (Regeln), `GRF-RAHMEN.md` (acht Denkprinzipien des Generative Reality Framework als Arbeitsregeln),
`ZIEL.md` (Messgrößen und ehrliche Übersetzung des Ziels).

## Mit einem Free-Pool-Modell benutzen

Jeder OpenAI-kompatible Endpunkt genügt; es gibt keinen Anbieter-Zwang.

```bash
export MG_LLM_URL="https://<anbieter>/v1/chat/completions"   # beliebiger OpenAI-kompatibler Endpunkt
export MG_LLM_MODEL="<modell-id>"
export MG_LLM_KEY="<schluessel>"                              # nur in der Umgebung, nie in eine Datei
echo "Prüfe diesen Diff: ..." | python3 research/grid10/freellm.py --system team/agents/team-pruefer.md
```

`freellm.py` entfernt den YAML-Kopf der Rollendatei und nutzt den Rest als Systemprompt. In einem anderen Werkzeug
(Agenten-Harness, Chat-Client) kopiert man den Text der Rollendatei einfach als Systemprompt hinein.

## Hinweise

- Die Rollen verweisen auf gstack-Skills (`gstack-plan-eng-review`, `gstack-investigate`, `gstack-review`, `gstack-cso`,
  `gstack-careful`) nur **namentlich** und optional. gstack ist ein eigenes Projekt mit eigener Lizenz und nicht Teil dieses Repos.
- Die Rollen sind eine Arbeitsweise, kein Beleg für Leistung. `ZIEL.md` sagt ausdrücklich: Kein AGI-Indikator ist als
  erfüllt belegt.
- Rückbau: einfach die kopierten Dateien wieder löschen; die Rollen schreiben nichts außerhalb ihres Auftrags.
