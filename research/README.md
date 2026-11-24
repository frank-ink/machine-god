# Research (Forschungsmaterial, SHADOW)

Dieses Verzeichnis ist **Forschungsmaterial**. Es ist nicht in die Rust-App, den `machine-god`-Launcher oder die
Release-Archive verdrahtet und beeinflusst weder Routing noch Handlung. Alles hier läuft nur lokal und nur lesend bzw.
gegen Wegwerf-Datenbanken der Tests.

```
research/
  mg-build/    Messwerkzeug: Gate (gepaarter Bootstrap), Ledger, Retrieval-Benchmark, Schleife  (26 Tests)
  grid10/      Organe E1-E5, Weltmodell WM1/WM2, Selbstmodell, Intent-Cortex, Klassenbedarf V1/V2/V2.1,
               Retina-Thalamus, Zielverfolgung, freellm.py (15 Testdateien, run_tests.py)
  teamkanal/   Referenzskripte der Team-Kanal-Reparatur (bereinigt, nicht lauffähig ohne Kanal-Client)
team/          Dev-Team: Rollen, Denkrahmen, Ziel (siehe team/README.md)
docs/research/ Regelkreis-Studie (PDF + Text), Entscheidungen Claude + ChatGPT, Kern-Idee Pulse/Wiki
```

## Ehrlicher Status (Stand 2026-11-25)

| Teil | Status | Beleg |
|---|---|---|
| Alle grid10-Organe | SHADOW: schreiben nur in eigene Ledger, steuern nichts | Code, Tests |
| S0 (prospektive Erhebung) | `ZU_WENIG_DATEN`: 0 Fenster, ohne Dauertakt läuft kein Sensorzyklus | `s0_eval.py`, Protokoll in `fixtures/wm-s0/` |
| Intent-Cortex V1 | **durchgefallen**: `INTENT_BENCH_V1` macro-F1 0.615 (Soll 0.80), alle fünf Schwellen gerissen; gemessen wurde ein lokales 4B-Modell: es taugt nicht als Absichtskortex; andere Modelle sind nicht gemessen | `fixtures/intent-bench/lauf_voll.json` |
| Klassenbedarf V1 | 89 % ABSTAIN auf 1614 Nachrichten, nur als Basislinie akzeptiert | `docs/research/entscheidungen-*.md` |
| Klassenbedarf V2 / V2.1 | V2 semantisch unzureichend (Pilot 24/40 exakt); V2.1 28/40, aber der Pilot ist Entwicklungsdatensatz, kein unabhängiger Beleg | dto. |
| WM1 (Prognose) | Historischer Vorteil (Brier 0.0861 vs 0.1192) ist retrospektiv und in-sample, nicht unabhängig verifiziert; prospektiver Lernnutzen offen | dto. |
| WM2 (Hypothesen) | unkalibriert; Gewichte sind Plausibilitätsanteile einer ungeprüften Regel, keine Wahrscheinlichkeiten | `weltmodell2.py` |
| E3/E4 (Zielgenese, Wettbewerb) | Zielsätze sind Vorlage + Befund (`rule_template`), nicht emergent; der Wettbewerb führt nichts aus | dto. |
| Selbstmodell | Fähigkeitssonden; `intent_semantik` steht auf FAILED | `selbstmodell.py` |

Es wird **keine** AGI-, Bewusstseins- oder Emergenz-Behauptung gemacht. Kein AGI-Indikator ist als erfüllt belegt
(`team/ZIEL.md`).

## Tests

```bash
python3 research/grid10/run_tests.py          # 15 Testdateien, laufen als Skripte
cd research/mg-build && python3 -m pytest -q  # 26 Tests
```

Nicht enthalten, weil sie private Aufzeichnungen oder die Live-Datenbank brauchen: `test_grid_v2_parity.py`
(war schon vor der Aufnahme rot) und `test_v2_signals_extended.py` (Messskript gegen die Live-DB).

## Free-Pool-Modelle

Alles, was ein Sprachmodell braucht (Intent-Cortex, Teamkanal-Check-in, Rollen unter `team/`), ruft über `grid10/freellm.py` einen beliebigen
OpenAI-kompatiblen Endpunkt auf. Kein Anbieter, kein Schlüssel und kein Modellname ist fest verdrahtet:

```bash
export MG_LLM_URL="https://<anbieter>/v1/chat/completions"
export MG_LLM_MODEL="<modell-id>"
export MG_LLM_KEY="<schluessel>"        # optional, nur aus der Umgebung gelesen
```

Ohne diese Variablen schlägt ein Modellaufruf laut fehl (Intent-Cortex enthält sich dann: ABSTAIN); die Tests brauchen kein Netz und kein Modell.
Optional: `MG_LLM_HEALTH_URL` (Gesundheits-URL für die Selbstmodell-Sonde `lokales_llm`), `MG_REAL_DB` und `MG_THALAMUS_VENDOR`
(nur für zwei optionale Echtdaten-Replays), `MG_TRANSCRIPT_DIR` (nur für die Blindbewertung der Kalibrierung).
Die gemessenen Zahlen oben gelten für das damals genutzte lokale 4B-Modell; für andere Modelle gibt es keine Messung.

## Unterschiede zu den Originalen

- Datenpfade zeigen auf `research/grid10/fixtures/` (Benchmark, S0-Protokoll, Pilot-Aufgaben); die Fixtures sind byte-identisch,
  ihre sha256 werden von den Tests geprüft. Es gibt keine festen Pfade ins Home-Verzeichnis.
- Modellaufrufe gehen über `grid10/freellm.py` an einen frei wählbaren OpenAI-kompatiblen Endpunkt (siehe unten) statt an ein festes lokales Modell.
- Namen von Personen, Rechnern und Hosts sind neutralisiert, die Live-Verdrahtung (`register.py`) fehlt.
- Nicht enthalten: Inhalte der Live-Datenbank, private Chatverläufe, gstack (eigenes Projekt mit eigener Lizenz).
