# S0_EVAL_V1: prospektive Auswertung des Weltmodells WM1 (festgelegt 2026-11-25, Entwurf ChatGPT Runde 9)

Zweck: erste prospektive Pruefstufe. Kein endgueltiger Lernnachweis. Die Parameter sind vorgeschlagene Startfestlegungen, empirisch nicht validiert. Nach dem Einfrieren (sha256 in S0_EVAL_V1.sha256) werden sie nicht mehr geaendert; eine Aenderung wird als S0_EVAL_V2 neu festgelegt.

1. Datenbasis: Zeilen aus f3_wm_pred mit status='bewertet' und prospective=1. Prognose vor Fensterbeginn eingefroren (frozen_hash), bewertet unabhaengig vom Prognostiker (Brier gegen Rohereignisse). Fenster ohne Sensor-Stichprobe sind UNKNOWN und gehen nie in die Auswertung ein, nichts wird imputiert. Historische Fenster (Basislinie) sind keine S0-Daten.
2. Version: jede Modellversion wird getrennt ausgewertet (Hauptauswertung: Version 0). Versionsgrenzen werden nie nachtraeglich verschoben; eine Prognose zaehlt unter der Version, unter der sie eingefroren wurde.
3. Referenzen: eingefrorene W0-Referenz (Basisraten, vor Messbeginn eingefroren) und Persistenz (letztes bewertetes Fenster). Modell, W0 und Persistenz haben gleichen Informationsstand und Horizont (Pflichtfelder in f3_wm_pred).
4. Mindestumfang: 200 gueltige Fenster je Version, sonst Ergebnis ZU_WENIG_DATEN.
5. Hauptmetrik: Brier Skill Score gegen W0: BSS = 1 - Summe(B_Modell) / Summe(B_W0). Sekundaer: BSS gegen Persistenz (nur Fenster mit vorhandener Persistenzprognose). Zusaetzlich je Retina-Kanal.
6. Unsicherheit: gepaarter Block-Bootstrap, 95-%-Intervall (Perzentile 2.5 und 97.5), Blocklaenge 12 Fenster (60 min), 10000 Wiederholungen, fester Zufallsstartwert 20261125. Bloecke bestehen nur aus zeitlich unmittelbar aufeinanderfolgenden Fenstern (Bucket-Differenz 1) und werden nie ueber Beobachtungsluecken zusammengesetzt; ein kuerzerer Restblock am Ende eines zusammenhaengenden Abschnitts bleibt erhalten. Sensitivitaet: Blocklaengen 24 und 36, nur berichtet.
7. Urteil: positiv = Untergrenze des KI ueber 0; negativ = Obergrenze unter 0; sonst unentschieden.
8. Keine Ablation. Alle Ergebnisse mit n, Zahl der Abschnitte, Zahl der Bloecke und Zahl der UNKNOWN-Fenster berichten.
