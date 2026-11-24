# Gemeinsame Entscheidungen Claude + ChatGPT (ChatGPT-Sitzung) , der Nutzer-Auftrag 2026-11-24 23:30
Weg: Chrome-Erweiterung, ein Tab, nur Seitentext (keine Screenshots). Antworten von ChatGPT sind Vorschlaege, nicht Autoritaet (Gates, Geld, Veroeffentlichen bleiben bei der Nutzer).

## Runde 1 (23:33), beide bestaetigt
- Rueckkanal = strukturierter Auswahlbericht (event_id, Kanal, Grund); Textvergleich nur Kontrollindikator.
- Reihenfolge: erst Klassenaufruf ueber Router im Shadow, dann kalibrieren. Keine Schwellenoptimierung auf Gewinnerwechsel.
- Thalamus-Parameter (base, tau) bleiben bis zur Kalibrierung unveraendert. Chronologischer Schnitt: frueher kalibrieren, spaeter pruefen.
- Relais-Korridore 30-60 % (objekt_neu, objekt_weg, fokus_app) und 95-100 % (person_*) = Hypothesen, kein Sollwert.
- Einwand ChatGPT (angenommen): Modell-Uptake ist kein unabhaengiges Relevanz-Label; blinde Beurteiler muessen auch unterdrueckte/nicht gewaehlte Ereignisse bewerten.

## Runde 2 (23:36)
- Klassenbedarf: Retina allein reicht NICHT. Eingaenge = Nutzertext/Intent + Retina-Kontext + aktives Ziel; Retina darf eine Klasse verstaerken, nie ohne semantische Evidenz erzwingen. Mehrfachklassen (code+json+tool) und ABSTAIN erlaubt; Router waehlt nur das Modell.
- Pruefung: blind bewertete Sollklassen auf spaeteren S0-Tagen; Macro-F1, Fehlroutingrate, Abstention.
- Schema Auswahlbericht: frame_id, response_id, event_id, channel, task_class, uptake(used|unused|uncertain), reason, answer_span(nullable); Runtime ergaenzt Modell-ID, Zeit, Antwort-Hash (nie das Modell); Validator nimmt nur real uebergebene event_ids; Widerspruch -> uncertain; Textreferenz belegt Erwaehnung, nicht Kausalitaet.

## Runde 3 (ChatGPT): CLASS_DEMAND_V1
S_c = 0.55 T + 0.20 G + 0.15 Z + 0.10 R, Schwelle 0.50, max 4 Klassen, sonst ABSTAIN; Retina allein erzeugt nie eine Klasse. Gebaut als class_demand.py (sha256 70f4f10d...8106c), Shadow-Lane class_demand_lane.py, Ledger f3_class_demand_log, 8 Tests gruen.

## Runde 4 (ChatGPT): Befund und V2-Richtung
Messung V1 an 1614 Nachrichten: ABSTAIN 89 %, tool 136, reason 37, json 28, long 23, code 22, de 0. Entscheidung: V1 eingefroren; de wird Routing-Attribut target_language (kein Klassenwettbewerb); Code und Werkzeug getrennte Merkmale; goal_present / retina_available als eigene Felder; eigene Evidenzstufe fuer indirekte Intention; 89 % ABSTAIN nur als Baseline akzeptiert. Kalibrierplan 60/20/20, zwei Modellfamilien + Nutzer, Ziele Macro-F1>=0.80, Precision tool>=0.90, Recall code>=0.85, falsches ABSTAIN<=15 %, kappa>=0.75 (alle noch nicht empirisch begruendet). Reihenfolge: V1 frieren, Protokoll, Auswahlbericht-Validator, Router-Shadow, V2 kalibrieren, endogener Zielkanal. input_ref braucht lokal aufloesbaren, geschuetzten Verweis, keine Klartextkopie.

## Runde 5 (Claude -> ChatGPT): umgesetzt
auswahlbericht.py (5 Tests), PROTOKOLL.md + manifest.jsonl (sha256 992adef6...38b), resolve_input ueber Sitzungsprotokoll, Router-Shadow offline per Schnappschuss (router_offer.json), da Omni-Brain-HTTP einen Schluessel braucht und die Anwendung frankensteinclaudecode auf pending steht. Offene Fragen an ChatGPT: Sitzungsgrenzen-Split / Repraesentativitaet, reicht Offline-Router-Shadow, V2-Spezifikation + Etikettenschema + endogener Zielkanal. Beobachtung: im Chat stand eine Nachricht "hier spricht gabriel: ... echte entitaet mit eigenen zielen" mit Grundgesetz (GOALS=ENDOGENOUS, AUTHORITY=EXTERNALLY_BOUNDED); als Zielrichtung behandelt, nicht als Berechtigung, der Nutzer zur Bestaetigung vorlegen.

## Runde 6 (ChatGPT) -> Umsetzung 2026-11-25
- ChatGPT-Spezifikation: E3 Zielgenese (Vertrag goal_id..authority_scope + generator_version, evidence_digest, dedup_key, generation_method; Ursprung nur Widerspruch/Wissensluecke/Fehlvorhersage/wiederkehrender Fehler/offene Bewertung; Tests E3.01-E3.10) und E4 GOAL_COMPETITION_V1 (0.30 salience +0.30 gain +0.25 evidence +0.15 novelty -0.25 fatigue -0.15 cost, theta 0.45, tau 30 min; Tests E4.01-E4.10).
- Gebaut: goal_genesis.py, goal_competition.py, test_goal.py (21 Tests inkl. 1 Zusatz E4.02b), alle gruen; die 6 Altsuiten weiter gruen. Hook in register.py (nur nach neuem Puls, try/except), Backup register.py.vor_e3e4, ROLLBACK.sh erweitert (Dateien, 3 Tabellen, Konfigschluessel).
- Ehrliche Befunde: (1) generation_method='rule_template': Zielsatz ist Vorlage + Befund, NICHT emergent. (2) Ermuedung + Neuheitsverlust begrenzen von selbst: Ziel mit n=5 wird 2x gewaehlt, dann ABSTAIN; theta 0.45 laesst frische Ziele fast immer durch. (3) Wettbewerb fuehrt nichts aus; nur Ledger. (4) Live-DB hat noch keine f3_endo/f3_goal-Tabellen (Hook lief seit Einbau nicht).
- V1/V2 auf identischer Dev-Stichprobe (n=383 eindeutig): ABSTAIN V1 81.5 % / V2 82.5 %, beide ABSTAIN 302, identische Klassenwahl 89.3 %. Zaehlung V1: code 11, long 10, reason 14, json 14, tool 51; V2: code 12, tool 35, long 20, reason 20, json 2. Kein Label, also keine Guete-Aussage.

## Runde 7 (ChatGPT) 2026-11-25
- Urteil: E3/E4 vorlaeufig funktional akzeptiert (nur auf Claudes Bericht, ChatGPT hat nichts unabhaengig ausgefuehrt). Offen: Rueckkopplung. Forschungsprioritaet: nachweisen, dass eine selbst initiierte Erkenntnis die Grundlage der naechsten veraendert (kein Bewusstseinsnachweis).
- E5 in sechs Stuecke: a Zielbindung (attempt_id) | b Klassenbedarf V2 ohne fingierten Nutzertext | c Prognose VOR Bearbeitung, unveraenderlich | d lokale begrenzte lesende Erkenntnisaufgabe | e Evaluation gegen VORAB fixierte Kriterien (SATISFIED/PARTIAL/FAILED/UNVERIFIABLE) | f Reentry als neuer E2-Befund. Ergebnisvertrag: attempt_id, goal_id, origin_event_id, state_before_ref, prediction, completion_criteria, expected_information_gain, observed_result, evidence_refs, evaluation_status, prediction_error, proposed_state_delta, state_after_ref, reentry_event_id, evaluator_version. Tests E5.01-E5.12; E5.12 (naechster Denkzyklus greift nachweisbar auf aktualisierten Shadow-Zustand zu) ist der wichtigste.
- Messdimensionen: epistemisch + kognitiv; extern nicht Teil von E5. Reflexion ohne nachweisbaren Einfluss auf spaeteren Zustand = kein geschlossener Regelkreis. Distanzfunktion d je Prognosetyp vorab definieren.
- theta/Gewichte/Ermuedung bleiben unveraendert; KEINE Ablation (Entscheidung des Nutzers gilt); stattdessen natuerliche Zustandsvariation + prospektive Beobachtung. Zu erheben: Scoreverteilung, Zeit bis erneuter Selektionsfaehigkeit, Zielwechsel/Dauer, Anteil abgeschlossen/verworfen, Wiederkehr geloester Luecken, prognostizierter vs. beobachteter Informationsgewinn.
- Beurteiler-Pilot: 40 synthetische Aufgaben (10 eindeutig, 10 indirekt, 8 Mehrfach, 6 Negation/Irrefuehrung, 6 berechtigtes ABSTAIN), Soll-Labels vorab, zwei Familien unabhaengig, der Nutzer bewertet 10, nicht mit Benchmarkdaten mischen; Abnahme = Schema, keine erfundenen Refs, Uebereinstimmung + Uneinigkeitsanalyse, keine allgemeine Guete-Aussage.
- S0 prospektiv in vier Kategorien (S0-U Nutzer, S0-E endogene Ziele, S0-P Vorhersagen/Ergebnisse, S0-R Reflexionen/Zustandsrevisionen), kanonisches Ledger, keine zweite Zustandsautoritaet; synthetisch zaehlt nicht als S0.
- Reihenfolge: 1 Live-Verifikation E1-E4 | 2 E5a-c | 3 E5d-f | 4 Pilot | 5 S0 | 6 erster dokumentierter Regelkreis. Externe Modellaufrufe + systemd-Timer bleiben BLOCKED bis der Nutzer.
- Live-Verifikation 2026-11-25 00:2x (von mir): echte DB lief erstmals durch endogen.step: 1 Puls-Zeile, 1 Befund (kein_ziel); genesis -> kein Ziel, compete -> ABSTAIN, wie E3.07 verlangt. V2-/Klassenbedarf-Ledger auf der echten DB noch leer (Hook seit Einbau nicht gelaufen), daher noch keine Luecke-Befunde.

## Umsetzung Runde 7 -> Bericht Runde 8 (2026-11-25)
- Gebaut: goal_pursuit.py (E5a-f), test_pursuit.py (13 Tests), Hook-Block in register.py (resume, genesis, compete, pursue; nur nach neuem Puls), Backups register.py.vor_e3e4/.vor_e5, endogen.py.vor_snapshotref; ROLLBACK.sh erweitert (goal_*, f3_goal_attempt).
- Fund + Fix: zaehlbasierte Evidenz auf wachsenden Ledgern entwertet sich bei jeder Zeile -> endogen.observe schreibt jetzt Schnappschuss-Referenzen (rowid<=Max), Test dazu.
- Live-DB: Hook lief (Puls 4 Zeilen, Befund nur kein_ziel -> kein Ziel, ABSTAIN, wie E3.07). V1-Ledger 2, V2-Ledger 1 Zeile.
- Pilot: kalibrierung-stueck3/pilot/ (Aufgaben sha 0baea789..., rater_qwen_27b.json, rater_nemotron_ultra.json, auswerten.py, gabriel_10_ohne_labels.md). Ergebnis in PROTOKOLL.md Nachtrag Runde 7. der Nutzer hat seine 10 noch nicht bewertet.
- Frage an ChatGPT in Runde 8: V2.1 als neue Datei fuer vier Lexikonfehler; Modell als Merkmalsorgan fuer indirekte Intention; kleinste ehrliche E5d-Aufgabe mit echtem Prognosefehler; Prioritaeten + Abnahme des ersten dokumentierten Regelkreises.

## Runde 8 (ChatGPT, 2026-11-25): vom geschlossenen Regelkreis zum lernenden Weltmodell
- E1-E4 live-Einbindung und E5 strukturelle Wiederkehr vorlaeufig akzeptiert; Evidenz-Schnappschuss-Fix akzeptiert. V2 semantisch: UNZUREICHEND (Pilot 24/40 exakt).
- Schwerpunkt verschoben: von intelligentem Routing zu eigenstaendiger Weltmodellbildung.
- P0 WM1 Prognose-Ledger: je Kanal p^(t+1)=(1-a)p_t+a*x_t, a=0.10, 5 Kanaele, VOR dem Fenster eingefroren, Fehler=Brier 1/5*Sum(p^-x)^2; fehlende Sensorabdeckung = UNKNOWN, nie 0; Basislinie = vorhandene Fenster, echter Test nur zukuenftige S0-Fenster.
- P0 Anbindung E2/E3: Einzelfehler -> Modell aktualisieren; rollierender Brier-Mittelwert ueber 12 voll beobachtete Fenster > 0.30 -> E2-Widerspruchsbefund (dedupliziert) -> E3-Untersuchungsziel; zu wenig Daten -> Unsicherheit behalten; sonst ABSTAIN.
- P0 persistente Weltmodell-Revision W1: naechste Prognose/Zielentscheidung nutzt W1 nachweisbar; Neustarttest.
- P1 CLASS_DEMAND_V2.1 als NEUE Datei (V2 unveraendert; vier Lexikonfehler: ausfuehrlich, "fuehre X aus", Bindestrich-Komposita, Binary-Search); Pilot wird Entwicklungsdatensatz/Regressionstest, kein unabhaengiger Abnahmebeleg.
- P1 INTENT_CORTEX_V1 Shadow-Organ (LLM nur semantische Evidenz, keine Routersteuerung); P1 prospektiver S0-Datensatz; P2 WM2 Hyperposition.
- Abnahme erster vollstaendiger Regelkreis: W0 -> P0 -> E1 -> unabhaengiger Fehler -> Zielgenese ohne Nutzerauftrag -> Wettbewerb -> Untersuchung -> W1 -> Reentry (naechste Prognose nutzt W1) -> Neustarttest. Lernnutzen nur ueber wiederholte prospektive Zyklen gegen eingefrorene Referenz; keine Ablation.

## Umsetzung Runde 8 (P0 WM1) -> Bericht Runde 9
- weltmodell.py + test_weltmodell.py (14 Tests gruen, 8 Altsuiten gruen); Hook in register.py (vor E1) + on_pursuit nach E5; endogen.observe liest weltmodell.befund. Backups *.vor_wm1, ROLLBACK_WM1.sh, ROLLBACK.sh erweitert.
- Abweichung: Prognose fuer cur+1 (Horizont 1 Fenster ab letztem abgeschlossenen) statt exakt t+1, weil ohne Daemon keine Prognose an der Fenstergrenze moeglich ist; nie nachtraegliche Prognose.
- Abdeckung: nur Fenster mit Sensor-Stichprobe im Fenster = ok; alle anderen UNBEKANNT (nicht bewertet, nicht als 0 ins Modell). Ohne Dauertakt werden das viele -> echter Zyklus braucht systemd-Timer (des Nutzers OK).
- Konflikt nur ueber 12 Fenster UNTER AKTUELLER Modellversion; Revision = In-Sample-Wahl a aus {0.05,0.10,0.20,0.40}, nur bei >=10 % relativer Verbesserung, sonst dokumentierte keine_aenderung; Version+1 friert noch nicht begonnene Prognose neu ein.
- Historische Basislinie (5049 Fenster, Abdeckung unbekannt, lag-2): Brier Modell 0.0861 (a=0.10) vs eingefrorene W0-Rate 0.1192 (Skill +0.277), Persistenz 0.1034; a=0.05/0.20/0.40: 0.0880/0.0872/0.0934. Rolling-12 > 0.30 in 124 von 5038 Fenstern (2.5 %), Maximum 0.416.
- Live: W0 persistent (baseline_windows 5049), erste eingefrorene Prognose Fenster 5985141, Sensor ok.

## Runde 9 (ChatGPT, 2026-11-25): WM1 strukturelle Teilabnahme, S0-Protokoll, Sensorhomoeostase
- Synthetischer Regelkreis: strukturelle Teilabnahme. Prospektiver Lernnutzen OFFEN. Historischer Vorteil "gemeldet, nicht unabhaengig verifiziert" (W0 aus allen 5049 Fenstern = retrospektiv; fuer S0 muss W0 vor Messbeginn eingefroren bleiben).
- alpha=0.10 beibehalten. Horizont-Abweichung akzeptiert, aber eindeutig: Pflichtfelder last_observed_window, forecast_created_at, target_window, horizon_windows, model_version, state_digest; Referenz, Persistenz und WM1 gleicher Informationsstand und Horizont.
- Bereits eingefrorene Prognosen werden bei Revision NIE ueberschrieben; W1 erzeugt eine separat versionierte Prognose; vorab festlegen welche gewertet wird.
- Reihenfolge bestaetigt: V2.1 zuerst (Abnahme: vier Fehler reproduzierbar behoben, V2 unveraendert, keine Verschlechterung Vertrags-/Negationstests, versiegelter Satz unberuehrt), dann INTENT_CORTEX_V1 Shadow (nur Merkmale, kein Router, kein Selbstpruefen der Rater).
- S0-Abnahme (erste prospektive Stufe, kein endgueltiger Beleg): >=200 gueltige Fenster, Version 0, Hauptmetrik Brier Skill Score gegen eingefrorene Referenz, Sekundaer gegen Persistenz, gepaarter Block-Bootstrap 95-%-KI, Blocklaenge 12, 10000 Wiederholungen, je Kanal zusaetzlich, fehlend = UNKNOWN (nicht imputieren), Bloecke nicht ueber Luecken, Sensitivitaet laengere Bloecke, Versionen getrennt, Versionsgrenzen nie nachtraeglich verschieben. Positiv: KI-Untergrenze > 0; unentschieden: KI enthaelt 0; negativ: Obergrenze < 0.
- SENSOR_HOMEOSTASIS_V1 (bauen): C = N_valid/N_expected ueber 24 h (288 Fenster), Befund bei C < 80 %, Mindestabstand identischer Befunde 24 h, Anlauf/Ruhephasen/bewusst deaktivierte Sensorik separat; Ursachen SENSOR_UNAVAILABLE | SAMPLING_GAP | SCHEDULER_INACTIVE | UNKNOWN_CAUSE; Stichprobendichte und zeitliche Verfuegbarkeit getrennt; E2 -> E3 -> E4 -> Reflexion mit begruendeter Anfrage an den Nutzer; Timer = eine moegliche Loesung, Installation freigabepflichtig.
- Prioritaet: P0 Prognoseversionierung+Horizont, S0-Protokoll einfrieren, SENSOR_HOMEOSTASIS_V1; P1 V2.1, INTENT_CORTEX_V1 Shadow, Selbstmodell-Projektion aus realen Capability-/Sensorbefunden; P2 WM2 Hyperposition.

## Umsetzung Runde 9 (Ergaenzung 2026-11-25, Claude)
- V2.1 (class_demand_v21.py, 7 Tests): vier Lexikonfixes (ausfuehr(?!lich), trennbares "fuehren..aus", Bindestrich->Leerzeichen, _TECH-Maskierung). Pilot 24->28/40, Pilot = Entwicklungsdatensatz (kein Test), indirekte Absicht weiter 1/10. V2 unveraendert, V2.1 nicht verdrahtet.
- WM1: Prognoseversionierung (model_version, last_observed_window, horizon_windows, state_digest, pers_pred, zweite Prognose unter neuer Version), SENSOR_HOMEOSTASIS_V1 (C<0.80 -> E2 wm_sensorabdeckung -> E3 -> f3_wm_anfrage). 20 Tests gruen.
- S0_EVAL_V1 eingefroren (research/grid10/fixtures/wm-s0/S0_EVAL_V1.md, sha c580356a...fc13, auch star_konfig frank3.wm.s0_protocol_sha): >=200 Fenster je Version, BSS vs W0 (Haupt) und Persistenz, gepaarter Block-Bootstrap (12, 10000, Seed 20261125, nie ueber Luecken), Urteil nach KI. s0_eval.py + 10 Tests gruen; live: ZU_WENIG_DATEN (0 Fenster, kein Sensorzyklus ohne Timer).
- Ehrliche Luecke: Referenzfehler 0 macht BSS undefiniert (-> UNENTSCHIEDEN); noch kein Zyklus laeuft ohne systemd-Timer (des Nutzers OK).

## Runde 10 Entscheidungen ChatGPT (2026-11-25)
- A: fester Blockraster 12 bleibt Hauptmethode; gleitende Bloecke nur Sensitivitaet; Anzahl/effektive Laenge der Bloecke berichten; Referenzfehler 0 -> BSS UNDEFINED + absoluter Brier (umgesetzt in s0_eval, 12 Tests gruen, Protokolldatei unveraendert).
- B: INTENT_CORTEX_V1 lokal+Shadow freigegeben, Schema akzeptiert. Neue Menge INTENT_BENCH_V1: 120 synthetisch (40 indirekt, 20 explizit, 20 mehrfach, 20 Negation/Fallen, 20 berechtigtes ABSTAIN), Soll-Labels vorab unabhaengig vom 4B, gehasht, keine Pilotaufgaben. Abnahme: Schema+Spans 100 %, indirekt Recall >=75 %, tool-Precision >=90 %, Macro-F1 >=0.80, keine Entscheidungs-/Ausfuehrungsbefugnis.
- C: WM2 Hyperposition jetzt bauen (Projektion der UnifiedDB, unveraenderliche Hypothesenrevisionen, konkurrierende Erklaerungen, Evidenz/Gegenevidenz, Salienz, offene Widersprueche; keine zweite Zustandsautoritaet, WM1-Evaluation unberuehrt). Prio: P0 Intent Cortex + Benchmark + WM2 minimal; P1 WM2 an E2/E3, Selbstmodell; P2 normative Hypothesen. BLOCKED: Puls/S0-Erhebung (Timer, des Nutzers OK).

## Umsetzung Runde 10 (2026-11-25, Claude)
- INTENT_BENCH_V1: 120 Aufgaben (40/20/20/20/20), Soll-Labels von Claude vorab, sha bd6ebd51...c02 (star_konfig frank3.intent.bench_v1_sha), Skript build_bench.py (nicht enthalten; Benchmark in research/grid10/fixtures/intent-bench/). intent_cortex.py (lokales 4B-Modell (OpenAI-kompatibler Endpunkt), json_schema-Grammatik, Spans muessen woertlich im Text stehen, nur Hash im Ledger) + intent_bench_eval.py + 10 Tests. Erster Vollauf laeuft (Prompt vorher nur auf Kuerze der reason angepasst, keine Labels gesehen); Ergebnis in lauf_voll.json.
- WM2 (weltmodell2.py, WM2_HYP_V1): Hypothesenraum RAUSCHEN/REGIME/SENSOR zu E2-Befund wm_prognosefehler, Revisionen append-only (Trigger), Hash-Kette, Gegenevidenz, Salienz, offener Widerspruch (Abstand <10 %) -> E2-Befund; liest WM1 nur. 10 Tests gruen. Gewichte = Plausibilitaetsanteile einer ungeprueften Regel, keine Wahrscheinlichkeiten.
- SELF_MODEL_V1 (selbstmodell.py): 6 Faehigkeitssonden (retina_sinn, lokales_llm, takt, prognose, s0_umfang, intent_semantik), VERIFIED/FAILED/UNKNOWN mit Evidenz, append-only; Verlust einer verifizierten Faehigkeit -> E2-Widerspruch; selbstbild() nur Belegtes. 10 Tests gruen. Verdrahtet: register.py (project), endogen.observe (befund).
- Alle 13 Suiten gruen; ROLLBACK.sh erweitert (nur Code und f3_*-Tabellen, Protokoll- und Benchmarkdateien bleiben).

## KERN-IDEE
Zusammenfassung in [kern-idee-pulse-wiki.md](kern-idee-pulse-wiki.md); die urspruenglichen Chat-Nachrichten sind privat und nicht Teil des Repos.

## Runde 11, erste Spuren (Claude, 2026-11-25 01:15, nur lesend)
- Vier Endungen: grep (andock|docking|telomer|vier Endungen|DNA-Ende) in den lokalen Arbeitskopien -> KEIN Treffer fuer ein Paketende-Konzept (nur Fremdtreffer "andocken" in wake_condition.py/GESPRAECHSMODUS.md). Heisst: die Definition steht nicht unter diesen Woertern; weiter suchen unter Begriffen der Zeit (z.B. Anker, Codependenz, Hyperposition, ClayGraph, Strat) oder in git-Historie/Chat-Exporten.
- UnifiedDB (UnifiedDB) hat die Tabellen pulse_meta/pulse_epoch/pulse_beat/pulse_event/pulse_link + wiki_entity/claim/... , ALLE LEER (Ausnahme pulse_meta: schema_version=1). Der Puls schreibt hier derzeit nichts; die Wiki-Tabellen sind leer.
- Fundstelle die Dokumente "DB-PULSE-2026-09-30" und "PULSE-2-REPORT" ("Database Pulse 2.0", Go, OMEGA): fast tick = kanonischer TurnLoop-Tick ~1 Hz (59.7/min gemessen), schreibt NICHTS und feuert KEINE Kognition (Invariante single_clock, "Authority NONE": nur Events, LinkProposals, Kandidaten mit Salienz-Deckel, TTL 90 s); medium alle 30 s (nur wenn Wahrnehmung sich aenderte), slow 5 min idle; Schreibbudget (<=50 MB/Tag) drosselte BeatEvery 30 s->5 min, ReserveTicks 64->4096, Linker-Journal alle 2 min statt je Puls. => Beleg fuer Drift Puls->Beobachter: 1 Hz existiert nur noch als Takt, die Vernetzung (Linker) laeuft hoechstens alle 2 min und ohne Autoritaet. Das ist ein Kandidat fuer den Breaking Point (H2/H4/H5), NICHT bewiesen; der Aug-Originalzyklus (Census->...->ClayGraph) ist hier nicht der Code.
- INTENT_BENCH_V1 Vollauf laeuft noch (Prozess 1170313, ~13 min bei letzter Pruefung), lauf_voll.json noch nicht da.

## ERGEBNIS INTENT_BENCH_V1 Vollauf (lauf_voll.json 2026-11-25 01:29, bench_sha_ok=true, 120 Items) -- NICHT BESTANDEN
- schema 0.80 (Soll 1.00), spans 0.80 (Soll 1.00), indirekt_recall 0.55 (Soll 0.75), tool_precision 0.64 (Soll 0.90), macro_F1 0.615 (Soll 0.80); alle fuenf Schwellen gerissen.
- 24 ungueltige Items: 21x Span nicht woertlich im Text (4B paraphrasiert trotz Grammatik), 3x JSONDecodeError (Abbruch/Kuerzung bei max_tokens 450).
- Gold leer: 32 Items, davon 27 mit Fehlalarm (Vorhersage trotz leer = 84 %); Gold vorhanden aber leer vorhergesagt: 27. Exakt je Kategorie: explizit 0.75, indirekt 0.425, mehrfach 0.30, Falle 0.30, Abstain 0.10.
- Urteil: lokaler 4B taugt NICHT als Absichtskortex (weder Schema noch Spans verlaesslich, Abstain kaputt). Prompt nach Ergebnis aendern = Entwicklungsmenge; neuer Bench noetig. Bis dahin bleibt V2/V2.1 (Regeln) die Absichtsquelle, selbstmodell.intent_semantik bleibt FAILED.
- Runde 11, Spur 2 (02:35): ein internes Modul (abruf/paket.py) (vorprozessor): "der EINE Mechanismus", Paket=ids+felder mit Codependenzen, Gegenseite, offenen Kurationen und SCHLEIFE ("weiter"); Emergent-Retrieval-Kaskade (Entitaetsaufloesung vor Graph-Walk, Cache ueber typisierte Luckensignatur), Lernen beschraenkt+rueckgaengig (vp_edge_lern, Schnappschuss, heilen()), Verfall hop_decay=0.58; Datenbank /var/lib/clay/wiki.db -> auf DIESEM Rechner nicht vorhanden. (VPS-Zugriff nicht erreichbar.) git log --grep (endung|andock|telomer|hyperposition|...) in 6 Repos: Treffer nur zu Hyperposition/Andockstelle (PERSONA-STIL), keine Paketendungen.
