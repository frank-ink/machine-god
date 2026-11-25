> KORREKTUR durch Claude (gemessen 2026-11-23): Die Aussage 'GRID10-Loop-Code ist in keinem Repo' gilt nur fuer EntityOS.git. Der GRID10-Turn-Loop existiert als Code: machine-b ~/frankenstein-repo/scripts/f2wp1207_grid10_turn_loop.py (LIVE, 1749 Zeilen inkl. uncommitted diff) und Maschine A ~/.claude/star/modules/grid10/ (1928 Zeilen, live mit f3_grid_v2_log). Siehe Chunks c01-c06.

# EntityOS — Extraktion aus den drei Quelldokumenten

---

## 1. Was ist EntityOS in 3 Sätzen

- EntityOS ist eine **selbstcontainierte Laufzeitumgebung** (in der Praxis ein `systemd-nspawn`-Container), die einen kognitiven GRID10-Loop (intern „FranKenstein“ genannt), ein Dashboard zur Beobachtung/Steuerung und **exakt eine SQLite-Datenbank (`unified.db` / `wiki.db`)** als einzigen persistenten State-Store hostet — VM, Dashboard und Kognitions-Loop sind drei unabhängig schaltbare Schichten.  
  **[Dokument B, Abschnitte „What EntityOS is“ + „Data persistence boundary“]**

- Der **Architekt** läuft **auf dem Wirt (Host)**, nicht im Container: er baut Kanarien-Container und den Live-Container, wendet Patches an, steuert das Schwarm-Tor (Replicator/Abyss) und schreibt unveränderliche Quittungen in die gemeinsame DB — der Container darf sich **nicht selbst** neu bauen (Sicherheitsspezifikation).  
  **[Dokument A, Abschnitte 1.1, 1.7, 4.1, 4.4]**

- Stand der Dokumente: **GRID10-Loop-Code ist in keinem der drei Repos enthalten** (nur Schema + Scaffold), der **General-Purpose ClayCode-Compiler ist `FAIL`** (nur skalare Int/Real/Bool-Funktionen ausführbar), die **Kanarie hat nie einen Container gebaut** (`docker images` zeigt kein Kanarie-Image), und der **Architekt ist konfiguratorisch deaktiviert** (`ENABLED=0`, `AUTO_LIVE_NACH_KANARIE=0`).  
  **[Dokument A, Abschnitte 1.11, 2.3, 2.6; Dokument B, Abschnitt „GRID10 cognition loop“; Dokument C, Abschnitt „Package findings“]**

---

## 2. Harte Invarianten / Regeln des Substrats (mit Quellzitat-Stelle)

| Invarianze / Regel | Quelldokument + Abschnitt |
|---|---|
| **One-Door Datenhoheit**: Jeder Schreibzugriff auf `unified.db` für eine Tabellenfamilie geht durch **exakt ein typisiertes Interface** — nie verstreute `sqlite3.connect()`-Aufrufe. | **B**, „One door data authority“ |
| **Eine einzige DB**: `unified.db` (bzw. `wiki.db` auf Host-Pfad `/var/lib/clay/wiki.db`) ist der **sole persistent state store**; keine zweite Datenbank, kein zweiter GRID. | **B**, „Data persistence boundary“; **C**, Schritt 3 („No second database, no second GRID“) |
| **Lebenszyklus (3 Stufen)**: Stage 0 (Socket lauscht) → Stage 1 (Dashboard + VM laufen, via systemd-Socket-Aktivierung) → Stage 2 (Kognitions-Runtime AN via **expliziter typisierter Request** an das laufende Dashboard, **kein** systemd-Unit). Soft-Off (Runtime aus, VM/Dashboard bleiben) und Hard-Off (ganze VM runter) sind **zwei distincte, unabhängig erreichbare Zustände**. | **B**, „The three-stage lifecycle“ |
| **Epochen-Binding**: Ein offener Runtime-Epoch in `unified.db` (Tabelle `continuity`) bindet Entity, Installation, State-Root, Host. **Geschlossene Epoch = kein live Runtime** (`bound: false`); nach Neustart passt ein Paket der alten Epoch nicht mehr. | **C**, Schritt 3 („Canonical state/runtime ABI“) |
| **Binding-ABI (Host → EntityOS)**: `GET /api/entityos/binding` liefert: `entity_id`, `installation_id`, `state_root`, **offene** `epoch_id`, `host_binding` (`host_id` = `app-installation`, `owner` = `local-installation`, `host_attested` = `false`). **Kein** Maschinenname/Adresse im App-Record. | **C**, Schritt 3 |
| **J-Space Shadow-Modus**: Inbound-Paket (`jspace_to_entityos`) **muss** an *diese* Runtime gebunden sein (Entity, Installation, State-Root, Epoch, Host) → sonst **409 + Error-Record `jspace.rejected`**. Gebunden → **ein** Hypothesis-Record `jspace.inbound` auf ClayBus (`credit: not_admitted`, 24-char Digest, Größe, Keynamen). Outbound: App baut `entityos_to_jspace`-Paket, validiert, **returned nur** (kein Transport), Record `jspace.outbound`. **Ein** Paket schreibt **exakt eine** append-only ClayBus-Zeile (Authority `NONE` per Constraint). | **C**, Schritt 4 |
| **ClayCode-Pfad (nur über App-eigene Routes)**: Dispatcher = token-gated Server-Routes (`POST /api/entityos/clay/task`, `GET /api/entityos/clay/tasks`); Task-Store = `fk_clay_task` in `unified.db` (1 Zeile/Task, ID = Content-Hash, State `queued → verified|refuted|unknown|error`, **ein** Transition); Verifier = **pinned** `claycode_base_compiler.py` (SHA-256 `e95556ad…`) aus **read-only** Source-Dir (`CLAYCODE_BASE_DIR`), **eigener Prozess**, minimales Env (kein Key/Token), 20s Limit, **kein Netz**; Result-Store = ClayBus-Record (`Measured clay.task` / Unknown / Error). `verified` = Compiler-Wert == Claim in **allen** gegebenen Fällen. Kein Compiler / nicht der gepinnte = `unknown`. **Keine Promotion, kein Provider-Call** auf dem Pfad. | **C**, Schritt 5 |
| **Architekt-Schleife (Takt)**: 1) Selbstzustand messen (VORHER) → 2) **Eine** Hypothese wählen (höchster Wert, nicht quittiert) → 3) Reproduzieren (kein Fix ohne reproduzierten Befund) → 4) Zweig `architekt-<kurz>`, GLM synthetisiert Fix → 5) Voller Testlauf + Selbstzustand (NACHHER); Boden gesunken/schlechter → verwerfen → 6) **TOR** (sicherer Rahmen? + grün? + nicht schlechter?) → **Schwarm-Tor** (REPLICATOR verifiziert unabhängig, ABYSS attackiert, Anti-Echo) → Kanarie; Kanarie gesund → **wartet auf Freigabe** (Standard) → 7) Quittung schreiben (**immer**, auch ergebnislos). | **A**, 1.1 (Kopfkommentar `architekt.py` Z.11-27) |
| **TOR (sicherer_rahmen)**: Geschützte Pfade (`clayverse/effects.py`, `effect_journal.py`, `fence_hook.py`, `policy/`, `clerk_auth.py`, `autonomy.py`) **dürfen im Diff nicht geändert werden** (Präfix-Sperre bei Ordnern). **Fail-closed** bei leerem Diff. | **A**, 1.6 (`tor.py` Z.30ff., 86-92) |
| **Schwarm-Tor (Anti-Echo)**: `darf_flaggschiff` = **True nur wenn** REPLICATOR **unabhängig bestätigt** UND ABYSS **unabhängig hält** (fail-closed). **Anti-Echo-Regel**: „Gleiches Modell + gleicher Promptrumpf = EINE Abstammungslinie“ — zählt **unabhängige Abstammungslinien**, nicht Quittungen. Zwei Modelle für zweite Linie vorgesehen (`GROQ_MODELL_ZWEITLINIE`). | **A**, 1.5 (`schwarm.py` Z.272ff., 325ff., 344) |
| **Kanarie-Sperren**: `bauen()` verweigert, wenn `container_name`/`projekt` = `"entityos"` (`_LIVE_NAMEN`). `live_neubau()` **verlangt** `ich_bin_sicher=True` (sonst Exception) — **kein Default-Pfad** live. Standardname `entityos-kanarie`, Port `3099` (weit weg von 3000). | **A**, 1.7 (`kanarie.py` Z.9, 33, 72, 153-154) |
| **Rollback**: Vor jedem Live-Apply `rollbackpunkt_aufzeichnen()` (Code + ggf. UnifiedDB-Migration). Rollback muss **beides** rückgängig machen können. | **A**, 1.8 (`rollback.py` Docstring) |
| **Quittungen**: **Eine pro Takt**, unveränderlich, redigiert (nur `zusammenfassung`-Zeilen aus Selbstzustand), in `wiki.db` Tabelle `eos_architekt_quittungen` via `UnifiedDB.tx()` (Transaktionsdisziplin). | **A**, 1.9 (`quittungen.py` Docstring) |
| **Konfiguration (Zwei-Schalter-Regel)**: `ENABLED=0` **UND** `systemctl enable --now eos-architekt.timer` müssen **beide** an stehen, bevor ein Takt automatisch läuft. `AUTO_LIVE_NACH_KANARIE=0` = gesunde Kanarie wartet auf menschliche Freigabe. **Beide aktuell 0**. | **A**, 1.10 (`architekt.conf`) |
| **Host-only Architekt**: `architekt/` erscheint **weder im Dockerfile noch in compose.yaml** — betritt Container nie (weder gebacken noch gemountet). | **A**, 4.1 (Dockerfile COPY-Zeilen, compose.yaml Volumes) |
| **Deploy-Mechanismus**: `docker compose --env-file /etc/clayverse/entityos-deploy.env up -d --build` (NIEMALS `source` von Env-Files mit JSON-Werten — `CLAYVERSE_CLERK_MAP_JSON` bricht sonst). | **A**, 4.5 (`betrieb/BAUEN.md`) |
| **GRF-Injektion**: `_GRF_RAHMEN` wird **jeden Turn** in System-Prompt injiziert (Schalter `ENTITYOS_GRF_INJEKTION=1` Default, reversibel ohne Rebuild). **Keine** GRF-Begriffe (`GRF`, `R_t`, `E_t`, `state-transition`, `invariant`) in Ausgabe an Mensch. | **A**, 5.1 (`headless_zero.py` Z.159-199, `compose.yaml`) |
| **Messprinzip „Gemessen, nicht selbstberichtet“**: Kanarie-Gesundheit verlangt Status `"GEMESSEN"` + `besteht=true` (keine Modell-Selbsteinschätzung). `outcome_ok` = mechanische Kombination aus `self_adapted` + `translation_raw_fallback` (keine Modellbewertung). | **A**, 5.2 (`kanarie.py::pruefen()`, `store.py` Z.150-171) |
| **Persistenz-Grenze**: Exakt **ein Verzeichnis** überlebt VM-Restarts/Rebuilds/Reinstalls: `ENTITYOS_DATA_DIR` (Default `/var/lib/entityos/data`), bind-mounted nach `/var/lib/entityos` — hält `unified.db`, sonst nichts. Container-Rootfs wird **jeden Start neu gebaut**, jeden Stop gelöscht. | **B**, „Data persistence boundary“ |

---

## 3. GRID10-Zug: Phasen/Schritte in Reihenfolge, was rein, was raus

> **Hinweis**: Der GRID10-Loop-Code ist **in keinem der drei Repos enthalten** (nur Schema + Scaffold). Die folgende Sequenz stammt aus dem **Zielarchitektur-Dokument** (privates Repo `frankenstein-2.0`), wie in Dokument B referenziert.

| Phase / Schritt | Input | Output / Wirkung |
|---|---|---|
| **1. Typed Entry öffnet GRID10 „Frame“** | Typisierter Eintrag (Request/Event) | Neuer Frame-Record (persistiert) |
| **2. Mandatory Reentry** | Vorheriger Frame / Epoch / Genesis Pointer (aus `unified.db`) | **Hard `ReentryError`** wenn Pointer fehlt — **niemals stillschweigend ignoriert** |
| **3. Working-Memory Fill („J-Space“)** | Reentry-State + relevante Memories | Gefüllter J-Space (Arbeitsgedächtnis) |
| **4. Zehn parallele Zellen generieren Kandidaten** | J-Space | 10 Kandidaten-Antworten (Cell Observations) |
| **5. Competition / Selection** | 10 Kandidaten | **Ein Winner** (Selection-Record) |
| **6. Broadcast (Global-Workspace-Style)** | Winner | Broadcast an alle Komponenten → diese updaten eigenen State |
| **7. Atomare Persistierung** | Neuer rekurrenter State + **alle** intermediären Schritte | Alles in `unified.db` (Frames, Cell Observations, Cell State, Effect Journal, …) |
| **8. Nächster Turn re-entered exakt am gespeicherten Pointer** | Gespeicherter Pointer | **Kein** assumed default — strikte Kontinuität |

**Leitprinzip**: „LLM as mouth/contractor, not as the seat of cognition“ — Sprachmodelle formulieren Output oder arbeiten als Worker an typisierten Sub-Tasks, **entscheiden nicht**.  
**[Dokument B, Abschnitt „The GRID10 cognition loop“]**

---

## 4. Schnittstellen (ABI), die ein Wirt (Host-Programm) erfüllen muss, damit EntityOS darunter läuft

| ABI / Anforderung | Detail | Quelle |
|---|---|---|
| **Host-OS**: Linux mit `systemd` (Socket-Aktivierung, `systemd-nspawn` Container) | `entityos-dashboard@<port>.socket` + `entityos-vm.service` | **B**, „Three-stage lifecycle“, `vm/README.md` |
| **Persistenz-Verzeichnis**: `ENTITYOS_DATA_DIR` (Default `/var/lib/entityos/data`) **muss auf Host existieren** und wird bind-mounted nach `/var/lib/entityos` im Container — hält `unified.db` | **B**, „Data persistence boundary“ |
| **Rootfs-Build**: `vm/build-rootfs.sh` baut **einmal** wiederverwendbares Base-Rootfs (idempotent, sicher wiederholbar) | **B**, „Data persistence boundary“ |
| **Data-Seeding**: `install.sh` erstellt persistentes Data-Dir **einmal** (idempotent) und kopiert initiale `unified.db` hinein | **B**, „Data persistence boundary“ |
| **Deploy-Env-File**: `/etc/clayverse/entityos-deploy.env` (für `docker compose --env-file …`) — **NIEMALS** `source` von JSON-haltigen Env-Files | **A**, 4.5 (`betrieb/BAUEN.md`) |
| **Port-Freigabe**: Dashboard-Port (Default 3000) auf Host erreichbar (Socket-Aktivierung lauscht darauf) | **B**, `compose.yaml` Port-Mapping `127.0.0.1:3000` |
| **Architekt auf Wirt**: `architekt/` Paket liegt auf Host (`/opt/entityos/the artefact/architekt/`), **nicht im Container** — Wirt muss Python-Umgebung + `clayverse` Module bereitstellen | **A**, 1.1, 4.1, 4.4 |
| **Docker / Compose**: `docker` + `docker compose` auf Wirt installiert | **A**, 4.1, 4.5 |
| **UnifiedDB-Zugriff**: Host-seitig `wiki.db` unter `/var/lib/clay/wiki.db` (wird von Container via Bind-Mount `CLAYVERSE_DB_PATH` geöffnet) — **kein** frisches Volume | **A**, 4.1 (compose.yaml Kommentar) |
| **Systemd-Timer für Architekt (optional)**: `eos-architekt.timer` (wird von Koordinator erst nach manueller Durchsicht aktiviert) | **A**, 1.10 |
| **GRF-Injektions-Schalter**: `ENTITYOS_GRF_INJEKTION` in Deploy-Env (Default `1`) — reversibel per Container-Neustart | **A**, 5.1, `compose.yaml` |

---

## 5. Widersprüche / Offene Punkte zwischen den Dokumenten

| Punkt | Dokument A (2026-08-22) | Dokument B (2026-09-10) | Dokument C (2026-11-16) | Bewertung |
|---|---|---|---|---|
| **Datenbank-Name / Pfad** | `wiki.db` unter `/var/lib/clay/wiki.db` (Host), im Container via `CLAYVERSE_DB_PATH` | `unified.db` unter `/var/lib/entityos/data/unified.db` (im Container `/var/lib/entityos/unified.db`) | `unified.db` (kanonisch), `wiki.db` nicht erwähnt | **Widerspruch**: Unterschiedliche DB-Namen, Pfade, Mount-Strategien. A nutzt Host-Bind-Mount für bestehende `wiki.db` (87 Tabellen + 19 Runtime-Spine), B/C bauen `unified.db` neu in eigenem Data-Dir. |
| **Container-Technologie** | `docker compose` + `Dockerfile` (Image `entityos:latest`, Python-Basis) | `systemd-nspawn` Container („S2“ Sandbox Tier), `vm/build-rootfs.sh` baut Rootfs | Nicht explizit, aber Overlay läuft in **AppImage** (App-Image) | **Widerspruch**: A = Docker, B = systemd-nspawn, C = AppImage. Drei verschiedene Deployment-Modelle. |
| **Architekt-Lage** | **Host-only** (`architekt/` nie in Container) | Nicht erwähnt (Architekt nicht Teil des Scaffold-Repos) | Nicht erwähnt | **Offen**: B/C sagen nichts zum Architekten; A insistiert auf Host-only aus Sicherheitsgründen. |
| **GRID10-Loop** | Nicht existent (nur Architekt-Schleife) | **Designziel** (in privatem Repo `frankenstein-2.0`), **nicht in diesem Repo** | **Nicht vorhanden** — Overlay hat **keinen** J-Space-Transport, **keinen** Store, **keine** State-Writes, **kein** GRID | **Konsistent**: Alle drei bestätigen: GRID10-Loop-Code **läuft nirgends**. |
| **ClayCode-Status** | Basis-Compiler **läuft** (1000/1000 Differential-Tests), General-Purpose **FAIL** (nur skalare Fn) | Nicht erwähnt | Basis-Compiler **pinned** (SHA `e95556ad…`), **Slice executes pure scalar only**, **kein Operator-Precedence** (`a+b*c` = `(a+b)*c`), **kein 0.8B-Modell** | **Konsistent**: Alle drei: nur skalare Teilmenge ausführbar. C fügt harte Limiten hinzu (Precedence, Pinned Hash mismatch). |
| **J-Space / ClayBus** | Nicht existent (nur `gw_*`, `mv_*`, `eos_bewertungen`, `mv_eval_runs`) | Schema definiert Tabellen (`frames`, `cell_observations`, `cell_state`, `effect_journal`, …) — **alle leer** | **Shadow-Modus only**: Inbound → 1 Hypothesis `jspace.inbound` auf ClayBus (`credit: not_admitted`), Outbound → Return only, **kein Transport**, 1 ClayBus-Row (`authority NONE`) | **Entwicklung**: A kennt J-Space/ClayBus nicht → B definiert Schema leer → C implementiert **Shadow-Validierung + ClayBus-Append** (kein Transport). |
| **Epochen / Binding** | Nicht explizit (nur `architekt` Quittungen, Kanarie) | Nicht explizit (nur `continuity` Tabellen in Schema) | **Zentral**: Offene Epoch in `continuity` bindet Entity/Installation/State-Root/Host; **geschlossene Epoch = nicht live** | **Offen**: A/B haben kein Epoch-Binding-Konzept; C führt es als **harte ABI** ein. |
| **Kanarie** | Code + Sperren vorhanden, **nie gebaut** (kein Image, kein Container) | Nicht erwähnt | Nicht erwähnt | **Offen**: Nur A dokumentiert Kanarie-Mechanismus. |
| **GRF / Hyperposition** | Live im Prompt (`_GRF_RAHMEN`), Hyperposition in `wettbewerb.py` konsumiert, **Shannon-Entropie §7.3 / `do(E_t)` NICHT im Repo** | Nicht erwähnt | Nicht erwähnt | **Offen**: Nur A hat GRF/Hyperposition. B/C ignorieren es. |
| **VERFASSUNG.md / ClayCode-only-Kognition** | **Absichtstext** (Vision: „Zero denkt in ClayCode“, „Alles nach ClayCode verwandeln“) | Nicht erwähnt | Nicht erwähnt | **Offen**: Nur A hat diese Vision; Compiler-Reality (alle 3) widerspricht (nur skalare Fn). |
| **Provenance / Source-Lock** | Nicht erwähnt | Nicht erwähnt | **Gemessen**: `provenance/source-lock.json` SHA-256 **matchen nicht** die Dateien am genannten Commit (`cd3ab86`) — Blobs sind byte-identisch mit Research Working Copy. **Verifier pinnt gemessenen Hash** (`e95556ad…`), nicht Lock-Hash (`76220989…`). | **Neu in C**: Konkreter Supply-Chain-Widerspruch (Lockfile vs. Realität). |
| **„0.8B Model in ClayCode“** | Nicht erwähnt | Nicht erwähnt | **Explizit widerlegt**: „Nothing in the compiler, runtime or the package is such a model; the five axes still come from organ-r4.“ | **Neu in C**: Widerlegt eine Behauptung (vermutlich aus früherer Kommunikation). |
| **Deploy-Mechanismus** | `docker compose --env-file /etc/clayverse/entityos-deploy.env up -d --build` (A, 4.5) | `install.sh` + systemd Units (`entityos-dashboard@.socket`, `entityos-vm.service`) | Nicht explizit (Overlay läuft in AppImage) | **Widerspruch**: Drei verschiedene Deploy-Wege. |
| **Ports** | Live: 3000, Kanarie: 3099 (A) | Dashboard-Port parametrisiert (`entityos-dashboard@<port>`) | Nicht erwähnt | **Offen**: Keine Einheit. |
| **Sicherheitsmodell (Tor / Fence)** | `tor.py` schützt Pfade, `fence_hook.py` als Tiefenstaffelung, echte Schranke `wache-koenig.py` **außerhalb Repo** (A, 1.6) | Nicht erwähnt | Nicht erwähnt | **Offen**: Nur A dokumentiert Sicherheits-Layer. |

---

### Zusammenfassung der Diskrepanzen

1. **Drei verschiedene Deployment-Modelle**: Docker (A) vs. systemd-nspawn (B) vs. AppImage (C) — **kein gemeinsames Substrat**.
2. **Zwei verschiedene Datenbanken**: `wiki.db` (A, Host-Bind, Bestands-DB) vs. `unified.db` (B/C, neu im Data-Dir) — **Inkompatibel**.
3. **GRID10 existiert in keinem Repo als Code** — nur Schema (B) und Shadow-Validierung (C).
4. **ClayCode nur skalare Teilmenge** — alle drei Dokumente bestätigen `GENERAL_PURPOSE_GATE: FAIL`.
5. **Epoch-Binding nur in C** — A/B kennen das Konzept nicht.
6. **S
