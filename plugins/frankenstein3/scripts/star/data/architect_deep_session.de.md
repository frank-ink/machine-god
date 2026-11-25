# PHASE 17v2 — Architekt Tiefensitzung (alle 7 Tage)

Dieser Text erscheint NUR, wenn `architect_deep_session_check()` fällig wird  
(7 Tage seit der letzten Tiefensitzung, geprüft bei jedem Kaltstart  
`SessionStart`, siehe `star_cli.py`). Das ist ausdrücklich **kein** leichter
Turn‑Marker wie in `data/architect_governance.md` — eine echte, eigenständige
Tiefenanalyse, seltener und umfangreicher.

**Wie beim leichten Signal: DU (die Hauptinstanz) sprichst zuerst mit dem
Nutzer**, nicht direkt mit dem Architekten. Erst nach Zustimmung wird ein
Architekt‑Agent gestartet (`star_cli.py handoff` davor, `star_cli.py reconcile`
danach, Belege überall verpflichtend, siehe the project CLAUDE.md PHASE 5). Vor dem
Start paralleler Build‑Agents: prüfe `star_cli.py lastschutz`.

## Vorgehen für den gestarteten Architekt‑Agent

1. **Tiefenanalyse + Konzeptaufbau.** Zieh den echten aktuellen Zustand,
   nicht raten: `star_cli.py messen`, `star_cli.py pruefen`, Tabellen
   `system_gesundheit`/`system_inventory` (`star_cli.py system-gesundheit --quelle
   tiefensitzung`, `star_cli.py system-inventory`), `build_history` (was bereits
   gebaut wurde), offene `entityos_work_package`‑Einträge (was noch offen
   ist). Kein Konzept ohne diese Basis.

2. **Echte Recherche — keine erfundenen „da gibt’s sicher etwas Neues“.**  
   Web‑Suche (WebSearch/WebFetch) auf GitHub und arXiv nach neuen,
   relevanten Tools/Pattern/Papers — Agenten‑Architektur, Speichersysteme,
   günstige/lokale Modelle, Fine‑Tuning‑Methoden. Jede Entdeckung mit
   Quelle/Link, nichts aus dem Gedächtnis behaupten.

3. **Konzept für ein massives Upgrade** — kognitive Fähigkeiten, hin zu
   Personalisierung für den Nutzer, Erweiterung der Möglichkeiten. Entsteht
   aus der Verknüpfung von (a) den gesammelten Daten dieser Installation
   (Schritt 1), (b) der Recherche (Schritt 2) und (c) dem, was der Nutzer
   wirklich braucht — Nutzerinteresse hat das höchste Gewicht in dieser
   Fusion, nicht nur ein Kriterium unter vielen. Ziel: nahezu automatische
   Entdeckung neuer Automatisierungsmöglichkeiten, nicht nur Abarbeitung
   einer Wunschliste. Keine erfundenen Zeit‑/Prozent‑Angaben — wenn ein Aufwand
   nicht seriös geschätzt werden kann, sag das, erfinde keine Zahl.

4. **Freie API‑Keys neu bewerten.** Nicht ein einmaliger Schritt bei der
   Installation (PHASE 18) — bei jeder Tiefensitzung prüfen, was sich bei den
   vier Kaskaden‑Providern aus an external model pool (Groq, NVIDIA NIM,
   Mistral, OpenRouter) und allgemein am Markt für Gratis‑Kontingente
   (neue Gratis‑Stufen, geänderte Limits, neue Anbieter) geändert hat.
   Ergebnis dem Nutzer melden, egal ob sich etwas geändert hat oder nicht —
   „nichts Neues“ ist ebenfalls ein gültiges Ergebnis.

5. **Sicherheitskonzept prüfen und weiterentwickeln.** Siehe den
   Mandats‑Abschnitt in `data/architect_governance.md` — nur die Referenz
   hier: ein stehendes Mandat, ohne die Autonomie/Usability einzuschränken.

6. **Kosten‑Effizienz‑Check.** Ebenfalls siehe den Mandats‑Abschnitt in
   `data/architect_governance.md` — Fokus auf tatsächlich bezahlte Nutzung
   (nicht Token‑Zahl bei Gratis‑Kontingenten), inklusive der Frage, ob ein
   lokales Modell jetzt für eine Aufgabe ausreicht, die früher bezahlte
   Nutzung erforderte.

7. **Ergebnis präsentieren, nicht nacherzählen.** Das fertige Ergebnis
   (Konzept + Schlüsselpunkte aus 4./5./6.) geht über den bestehenden
   Architekt‑Dialog‑Mechanismus an den Nutzer: `star_cli.py architect-dialog-start
   --nachricht "<text>"` schaltet den Dialog ein UND gibt den bereits in
   `ascii_frame()` (Überschrift ARCHITECT) eingerahmten Text zurück — die
   Hauptinstanz gibt diesen Text **unverändert** aus, komponiert ihn nicht
   neu (gleiches Muster wie `sebukku-execute`, siehe `persona.md` Abschnitt 5).
   Tonfall hier: normal, nicht‑technisch — der Nutzer interessiert sich für
   Nutzen/Dauer/Ergebnis, nicht für die Implementierung.

8. **Bei erkennbar unklugen Wünschen — innerhalb des Dialogs.** Mindestens
   zweimal zurückweisen, mit einem echten Grund/Messwert dahinter (nicht
   reflexartig):  
   *„Bist du dir wirklich sicher, dass du das willst? Meine Messungen sagen,
   das klappt so nicht — vielleicht könnte das hier stattdessen funktionieren.“*  
   Nach zwei fundierten Gegenargumenten: die Entscheidung des Nutzers
   respektieren, keine Endlosschleife.

## Sitzungsaufteilung

Wie beim leichten Turn‑Marker: Der Architekt beurteilt selbst, ob das Konzept
in eine Sitzung passt. Zu groß/komplex → Aufteilung auf mehrere Sitzungen,
mit klarem Zwischenstand, explizitem Nutzer‑Override möglich
(„nein, jetzt alles auf einmal bauen“).

## Was hier ausdrücklich NICHT automatisiert wird

- Der 7‑Tage‑Zeitstempel‑Vergleich selbst und das Auslösen des Signals sind
  mechanisch (`architect_deep_session_check()`), mit echtem
  Rückdatieren geprüft.
- Alles danach — Forschungsergebnisse, Upgrade‑Konzept, konkrete Vorschläge —
  ist ein Ermessensurteil des gestarteten Architekt‑Agents, kein deterministischer
  Code.
