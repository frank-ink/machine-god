# Dev-Team (5): Leiter + 4 Mitglieder, Claude Code, Denkrahmen team/GRF-RAHMEN.md
Leiter = die Hauptsitzung (FranKenstein): entscheidet, misst, berichtet an den Nutzer; skills: gstack-office-hours (Fragen/Hebel). Recherche machen die zweite Maschine + ChatGPT (Kanal), nicht das Team.
Architekt  team-architekt  gstack-plan-eng-review   Design, Schnittstellen, Testplan, Fehlerpfade
Bauer      team-bauer      gstack-investigate        Ursache zuerst (Forensik), dann Minimalbau; Text/Code-Gen zuerst ueber Free-Pool
Pruefer    team-pruefer    gstack-review             Diff/Tests unabhaengig, sucht was brechen kann; nie eigene Arbeit pruefen
Pruefer+    team-pruefer-plus (staerkeres Modell, falls konfiguriert)  nur bei nicht-trivialer Aenderung, NACH Tests + Free-Pruefung, Auftrag mit exakten Pfaden, Bericht <=9 Zeilen (token-neutral)
Waechter   team-waechter   gstack-cso, gstack-careful Sicherheit, Geheimnisse, Zerstoerendes, Nutzer-Freigabe
Regeln: Free-Tokens zuerst (ein Free-Pool-Modell ueber einen OpenAI-kompatiblen Endpunkt, siehe research/grid10/freellm.py), Mitglied nur spawnen wenn Werkzeug/Messung noetig; jedes Mitglied berichtet kurz mit Beleg (test:<exit>, datei:<pfad>:<sha>). Geld/Trading nur lesen. ship/push/extern nur mit der Nutzer.
Rueckbau: die kopierten Dateien wieder loeschen (siehe team/README.md)
