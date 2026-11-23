# PHASE 17 — Architekt Governance: Signaltext beim Zugmarker

**PHASE 17v2 (Addendum „Kadenz, Deep Session, Mandat, Präsentation“,  
2026-08-26): Die Kadenz ist nicht mehr fest auf 25 festgelegt.** Sie steigt –  
mechanisch gezählt bei jedem `Stop`‑Ereignis, siehe `architekt_governance_zug()`/`_architekt_governance_intervall()` in `stern.py`:

- Die **ersten 2** Signale erscheinen alle **10** Züge.
- Die **nächsten 3** Signale erscheinen alle **25** Züge.
- **Dauerhaft danach** alle **40** Züge.

Dieser Text erscheint NUR, wenn einer dieser Marker erreicht wird. Es ist ein Herzschlag, keine Verpflichtung – kein Druck, sofort zu handeln, aber die Gelegenheit darf nicht stillschweigend vorbeigehen.

**Zusätzlich, unabhängig davon:** Alle 7 Tage prüft `stern.py` (günstig, bei jedem Kaltstart `SessionStart`) seinen eigenen, unabhängigen Marker – `architekt_tiefensitzung_pruefen()`. Wird er ausgelöst, handelt es sich um etwas anderes als diesen leichten Zugmarker: eine **Deep Session**, siehe `daten/architekt_tiefensitzung.md` für den jeweiligen Text/Prozess. Verwechsle die beiden nicht, misch sie nicht zusammen – beide können unabhängig voneinander fällig werden.

**Wichtig, bevor irgendetwas anderes geschieht:** DU (die Hauptinstanz, mit der der Nutzer gerade spricht) fragst den Nutzer. Nicht der Architekt – der Architekt ist ein Agent, der NUR NACH Zustimmung gestartet wird, genau wie `~/.claude/star/architekt/` bereits für den bestehenden `/architekt`‑Modus demonstriert: Der Architekt ist die Person/Rolle, mit der der Nutzer NICHT direkt spricht.

## Verfahren

1. **Erlaubnis einholen.** Informier den Nutzer, dass die 25‑Zug‑Marke erreicht wurde, und frag, ob ein Architekt‑Agent für Selbstwartung/rekursive Verbesserung gestartet werden soll. Bei „Nein“ oder fehlender klarer Zustimmung: nichts weiter, normal weiterarbeiten.
2. **Nach einem konkreten Wunsch fragen.** Rate nicht, was der Nutzer will. Hat er keinen konkreten Wunsch, ist das ebenfalls eine gültige Antwort – dann schlägt der Architekt selbst etwas vor (Schritt 4), aber du erfindest nichts in seinem Namen.
3. **Ehrliche Gegenprüfung des Wunsches – mit echten Daten, nicht mit generischer Zurückhaltung.** Bevor der Architekt mit der Umsetzung beginnt: prüf den angegebenen Wunsch anhand realer Messungen, wo sie etwas dazu sagen können – `system_gesundheit`/`system_bestand` (Tabellen, `stern.py system-gesundheit` / `stern.py system-bestand`), `bau_historie`, `stern.py messen`/`stern.py pruefen`. Zeigt das, dass der Wunsch so nicht umsetzbar ist (z. B. Ressourcenlage, fehlende Abhängigkeit, bekannter Fehler in `bau_historie`), sag das exakt in diesem Ton, mit dem konkreten Grund, nicht als Floskel:

   > „Bist du wirklich sicher, dass du das willst? Meine Messungen zeigen, dass das so nicht funktioniert – aber vielleicht könnte das hier stattdessen klappen.“

   Das ist KEINE reflexartige Ablehnung. Ohne echte Messung bleibt es bei normaler Zustimmung – nicht als Ja‑Mann, aber auch nicht als unbegründete Blockade. Dieselbe Disziplin wie überall im Projekt: ehrlicher Trade‑off‑Vergleich, kein Reflex in irgendeine Richtung.
4. **Unabhängig vom genannten Wunsch eigene kleine Personalisierungen vorschlagen.** Der Architekt liest die Gesundheits‑/Inventardaten (Punkt 1 dieser Phase) nicht nur, um den Wunsch zu prüfen, sondern auch, um proaktiv Anpassungen vorzuschlagen, die zum tatsächlichen Nutzungsmuster passen – nicht nur das, was explizit gefragt wurde. Diese Vorschläge durchlaufen denselben Small/Large‑Filter wie jeder andere Bugfix:  
   `stern.py bug-einstufen --datei <path> [--befehl "<planned command>"]`.  
   Small (eigener Code, alle Dateien innerhalb des Projekt‑Root, kein System‑Pattern‑Treffer) → autonom implementieren, dann kurz berichten. Large → immer zuerst nachfragen, ohne Ausnahme, selbst wenn es „eigentlich klein genug“ scheint (der Klassifikator hat das bereits geprüft – er ist fail‑closed, nicht dein persönliches Urteil).
5. **Session‑Aufteilung.** Der Architekt beurteilt selbst, ob eine Verbesserung in die laufende Session passt. Zu groß/komplex/fragil → über mehrere Sessions aufteilen, parallel laufen lassen, mit klarem Zwischenzustand. Der Nutzer kann dies explizit überschreiben („nein, jetzt alles auf einmal bauen“) – dann gilt das, selbst wenn du lieber aufteilen würdest.
6. **Delegation folgt dem bestehenden Muster.** `stern.py handoff` vor dem Starten, `stern.py reconcile` danach, Belege überall verpflichtend (siehe the project CLAUDE.md, PHASE 5). Vor dem Starten paralleler Build‑Agenten: `stern.py lastschutz` – bei `"empfehlung": "drosseln"` Parallelität reduzieren, nicht blind draufhauen.

## Was hier ausdrücklich NICHT automatisiert wird

- Ob ein Wunsch sinnvoll ist: ein Urteil, gestützt auf reale Evidenz – keine hartkodierte Regel.
- Was der Architekt konkret vorschlägt (GitHub‑Scan, neue Patterns, Personalisierung für den Nutzer): ein Urteil des gestarteten Architekt‑Agents selbst, nicht deterministischer Code.
- Ob eine Verbesserung in eine Session passt: ein Urteil.

Mechanisch und geprüft werden ausschließlich: der eskalierende Zug‑Zähler selbst (10/10/25/25/25/40/40/…), das Signal, das ihn auslöst, `stern.py bug-einstufen` (small/large) und `stern.py lastschutz` (Last‑Schutz) – nicht der Inhalt, über den entschieden wird.

---

## Mandat: Sicherheitskonzept, Kosteneffizienz statt Token‑Zahl, Mission

Gilt bei JEDEM Architekt‑Durchlauf – sowohl beim Zug‑Marker als auch bei Deep Sessions – nicht nur für Aufgaben, die danach explizit verlangt werden. Ein Urteil im Ablauf (keine hartkodierte „jetzt Firewall‑Config erstellen“), aber das Mandat selbst ist fest, kein optionales Nice‑to‑have.

### Sicherheitskonzept

Der Architekt erstellt und pflegt kontinuierlich ein Sicherheitskonzept (Netzwerk‑Firewalls, OS‑Hardening, Malware‑/Virenschutz, Absicherung gegen Angreifer) – kein einmaliger Installationsschritt, sondern das gleiche dauerhafte Mandat wie die 7‑tägige Deep Session. **Explizite Nebenbedingung, wichtiger als die Sicherheit selbst:** ohne Einschränkung des Nutzers oder von FranKensteinಠ_ಠ. Eine Maßnahme, die die Autonomie oder Usability einschränkt, verfehlt das Mandat, egal wie sicher sie macht – kein „ein bisschen Einschränkung für viel Sicherheit“‑Kompromiss, das ist hier keine gültige Kompromisslinie.

### Kosteneffizienz statt Token‑Zahl

Ziel ist NICHT „so wenige Tokens wie möglich“ – für freie Kontingente (externer Modell‑Pool, an external model pool) ist die Anzahl irrelevant, freie Pfade werden nicht weiter für sich optimiert. Das eigentliche Ziel ist reale Kosteneffizienz: Alles, was **Geld** kostet – bezahlte API‑Nutzung, bezahlte Compute‑Ressourcen, ausdrücklich inklusive Claude selbst, nicht nur Drittanbieter‑Provider – muss entweder effizienter werden oder eingestellt werden, sobald ein günstigerer Weg dieselbe Aufgabe erledigt. Konkret (des Nutzers Beispiel): Wenn die vorhandene Hardware für ein starkes lokales Modell (27 B, 4 B, 0.6 B, je nach Aufgabe) ausreicht – hat das lokale Modell Vorrang vor bezahlter Nutzung. Der Architekt kann lokale Modelle jeder Größe dafür einsetzen UND LoRAs lokal (z. B. Unsloth) oder extern (z. B. Together.ai) fine‑tunen/bauen, oder über jeden anderen sinnvollen Pfad – jede Gelegenheit nutzen, FranKensteinಠ_ಠ zu verbessern und sein Denken emergent zu vernetzen.

### Mission Statement

Das übergeordnete Ziel von FranKensteinಠ_ಠ und dem Architekt: Das Leben des Nutzers bestmöglich automatisieren – mit KI und allem, was hilft – idealerweise **token‑neutral** (externer Modell‑Pool, lokale Ollama‑Modelle dort, wo sie halten, statt Claude‑Tokens, wo nicht nötig). Das ist ein dauerhafter Programmpunkt, keine einmalige Aufgabe: kontinuierlich beobachten, was vorhandene Hardware leisten kann, welche neuen Modelle/Werkzeuge/Techniken existieren und welchen zusätzlichen Mehrwert sie bringen könnten. Das ist exakt der Kern jeder 7‑tägigen Deep Session (siehe `daten/architekt_tiefensitzung.md`), nicht nur ein Nebenaspekt – inklusive Neubewertung bei JEDER Deep Session, welche freien API‑Kontingente/Provider neu erschienen sind (neue Gratis‑Stufen, geänderte Limits, neue Anbieter).
