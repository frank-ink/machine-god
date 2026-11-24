# Ziel (der Nutzer 2026-11-25): "Latenz 0, Qualitaet 100% ueber Fable, alle wissenschaftlichen AGI-Indikatoren erfuellt" + gstack, Codebase maximal perfekt
Ehrliche Uebersetzung (Beleg-Gesetz): 0 ms und 100 % sind Grenzwerte, keine Abnahmekriterien; "AGI-Indikatoren erfuellt" ist nur pruefbar, wenn jeder Indikator als Messung definiert ist. Daher: Richtung + Zahl + Tor.
## Messgroessen (jede mit Baseline, Ziel, Messweg; Verbesserung nur per Gate paired_bootstrap research/mg-build/mg/gate.py)
L1 Latenz kurze Free-Antwort (Free-Pool-Aufruf): Baseline 2026-11-25 end-to-end 1.4-1.8 s (3 Laeufe), Log p50 854 ms, max 9224 ms (n=200, Aufruf-Log). Ziel: p95 senken (Vorwaermen, Routenwahl nach p95), nicht "0".
L2 Latenz Retrieval (Pulse/Wiki-Pfad): Baseline offen (Pulse/Wiki leer, Bruchstelle 2026-10-08 ungeklaert).
Q1 Qualitaet Retrieval: hit@1 0.585 (gemessen, Befund der zweiten Maschine; Korpus 9x gewachsen), 4.7 % Text ueber Zeichen 4000 unsuchbar. Ziel steigt nur ueber PASS im Gate.
Q2 Qualitaet Antworttext: Fehlerrate Mund (erfundene Zahlen/Pfade) pro 100 Antworten: Baseline offen -> messen.
Q3 Tests: grid10-Tests (test_pursuit E5.01-12, weltmodell), mg-build 26 Tests: gruen halten; bekannter Rotstand test_grid_v2_parity.
## AGI-Indikatoren (Rahmen, je Eintrag Pruefweg; Status ehrlich)
Quellen-Typen: Leistungsstufen nach Breite x Tiefe (Morris et al. 2023 "Levels of AGI"), Skill-Erwerbseffizienz (Chollet 2019, ARC-AGI), universelle Intelligenz (Legg/Hutter 2007), Transfer/Out-of-Distribution, Langzeitgedaechtnis, Selbstmodell/Kalibrierung, Kausalitaet/Weltmodell, Planen mit Ziel (E5 Reentry).
Status heute: KEIN Indikator als erfuellt belegt. Intent-Cortex fiel durch (macro-F1 0.615), WM2 unkalibriert, WM1 in-sample, Organe ohne Vorhersagenutzen (Bench 2026-11-11). Behauptung "AGI erfuellt" waere unbelegt -> nicht aussprechen.
## gstack-Einsatz (Teamregel)
Jede Codeaenderung: Architekt (plan-eng-review) -> Bauer (investigate: Ursache zuerst) -> Pruefer (review, unabhaengig) -> Waechter (cso/careful) -> Leiter misst und entscheidet. Pruefer+: nur mit einem staerkeren Modell, falls eines konfiguriert ist (Konflikt mit Free-Token-Regel sichtbar).
