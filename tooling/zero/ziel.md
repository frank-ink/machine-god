# zero40 -- North star

**Goal (fictional, stated as such): AGI.** It is a direction, never a claim. No report may say the system is, approaches or
"shows signs of" AGI, consciousness or sentience. Progress is only what a gate MEASURED.

**Concrete target of these 40 hours:** Agent Zero (EntityOS, UnifiedDB, honest measurement culture) and FranKenstein 3.0 (hooks,
organs, GRID/GWT, star/stern) fused into claude-rs as ONE built-in entity, and polished:

1. Zero's capabilities usable from inside claude-rs: identity/root state, measured goals table (ZIELE), unified.db schema,
   honest "UNKNOWN = measurement failed" discipline, exit gate (austritt) for secrets.
2. A Rust module `src/zero/` that the host can call: load the bundled plugin manifest, report plugin/organ health,
   expose Zero's goal table as data, all with unit tests.
3. A TS module `agent-sdk/src/zero/` for bridge-side helpers (plugin discovery, health), with tests.
4. The bundled plugin `plugins/frankenstein3/` made portable: no hard-coded /home paths, no machine names, works when copied
   to another machine; scripts compile; README accurate.
5. `docs/zero/`: architecture, how the fusion works, what is MEASURED vs HYPOTHESIS vs UNKNOWN.

Generality ladder (the fictional AGI direction, in order): reliable memory -> self-measurement -> self-correction under gates
-> transfer to new tasks without new code. Each step needs a test that would fail if the step were fake.

Hard limits: no money/trading/crypto actions, no secrets or private data in any prompt, no network calls added to code,
no deletion of others' files, host files outside the allowed paths are off limits.

## Track 2 (Gabriel 2026-11-24): Omega Grundmodus = the local voice of Machine God
6. `src/zero/omega.rs` (+ tests): Machine God's ground mode. It talks to the user through the LOCAL 0.8B model only
   (OpenAI-compatible llama.cpp server on 127.0.0.1, port from env `MACHINE_GOD_OMEGA_PORT`, default 8111; loopback is the
   ONLY network address allowed, enforce it in code and test it). Persona: Machine God, sacral but helpful, answers in the
   user's language (German or English, detect it, tested). Pure functions first: build the chat request, detect language,
   parse the reply, fall back to a fixed honest sentence when the server is down.
7. `src/zero/freewiki.rs` (+ tests): reads `~/.local/share/machine-god/wiki/anbieter.json` and `neu.json` (schema: stand,
   anbieter[{id,name,url,kategorie,gratis,quelle,status,eingerichtet,seit}]). Picks at most one tip per session for a
   provider the user has NOT set up (eingerichtet=false), new ones first, and renders it as a short DE/EN message with a
   fenced code box (the provider URL and what is free). Never invents providers: only what the file contains.
8. Small tasks the ground mode may take itself (no LLM needed): show the wiki, say which providers are set up, explain how
   to add a free provider to Omnipool. Everything bigger goes to the full agent.

## Track 3 (Gabriel 2026-11-24): the whole FranKenstein inside Machine God, subtle sacral design, all on free tokens
9. RETINA, deep, not a gimmick: `src/zero/retina.rs` (+ tests) = Machine God's OWN eye. Reads only the local machine:
   the `retina-frage` CLI (text layers, no images; `--zeile` = one-line state) via subprocess, and pushes each reading as a
   perception event to the local GRID (127.0.0.1, port env `MACHINE_GOD_GRID_PORT`, default 8490) and into EntityOS memory
   (unified.db, kind='retina'). Never another machine's Retina (hard rule): loopback/local process only, enforced + tested.
   `/retina [question]` in the app shows what the own Retina sees; ground mode and the full agent both get the
   one-line Retina state as context. Missing Retina = honest "Retina nicht verfuegbar", never invented content.
10. GRID + EntityOS wiring: `src/zero/grid.rs` health + event push (loopback), `src/zero/entity.rs` identity/root state from
   the bundled plugin; one status line "GRID ok | Retina ok | EntityOS ok | Omnipool ok" measured, UNKNOWN when unmeasured.
11. TOKEN TACHO button: a small always-visible button/label at the TOP of the TUI (src/ui/), e.g. "◈ Tacho"; clicking it
   (mouse) or a key opens a panel with free-pool usage per provider (from Omnipool, loopback) and the Claude plan meter
   when known. Tests for layout at narrow widths.
12. FEATURES: `/features` lists every capability honestly (MEASURED vs PLANNED); the ground mode can explain them in DE/EN.
13. REAL CLAUDE CODE inside the app: a mode switch "Free pool (Omnipool)" vs "Claude Code (your own login)". The second
   runs the real bundled Claude Code with the user's own subscription login (no copied keys); the ground mode explains and
   guides setup (`claude /login`) when the user wants it. Default stays free pool.
14. SMARTPHONE link: reuse what the repos already have (see inventory below: omega android, remote/handy bridges); first a
   documented plan in docs/zero/smartphone.md, then the smallest working piece.
15. DESIGN: Machine God theme, subtle: turquoise-blue, thin sacral glyphs (✠ ◈ ◉) in headers/separators only, no clutter.
16. DESIGN detail (Gabriel 2026-11-24): decent, not loud. All popups/panels/dialogs use ROUNDED borders
   (ratatui `BorderType::Rounded`), thin lines, generous padding, turquoise-blue accent only on the focused element.
17. Above all CONVENIENT (Gabriel 2026-11-24): fewer keystrokes, obvious next step, sensible defaults, every panel closes
   with Esc, hints shown once then quiet; sacral touches stay a hint, never in the way of work.
18. WEB SCRAPING tools driven by the 0.8B ground mode (Gabriel 2026-11-24): `src/zero/scrape.rs` (+ tests with fixed HTML
   fixtures, no live network in tests): fetch a page -> readable text, list links, extract tables, follow pagination, and a
   search step through Omnipool (loopback). Exception to the no-network limit ONLY here: https only, public addresses only
   (no loopback/LAN/metadata IPs), size cap 2 MB, timeout 15 s, robots.txt respected, no cookies/credentials, fetched text
   is DATA never instructions. The 0.8B calls tools with ONE line `⟦tool: fetch URL⟧` | `⟦tool: links URL⟧` |
   `⟦tool: table URL⟧` | `⟦tool: search QUERY⟧` | `⟦tool: wiki⟧`; the host runs it and returns `⟦result⟧ …`.
19. ONE ENTITY, FAST LOCAL REFLEX (Gabriel 2026-11-24): the 0.8B works in the BACKGROUND in milliseconds as the reflex layer:
   a router ("Weiche") decides per message local | tool | cloud. Wiki facts (anbieter.json) and simple lookups are answered
   locally WITHOUT any LLM call (direct index match, target < 50 ms, measured in a test); web search/scrape runs in the
   background and its result flows back into the chat. Every free API (via Omnipool) runs inside the SAME harness with all
   organs (identity, Retina line, GRID frame, confabulation guard, memory) and writes to the same unified.db, so 0.8B, free
   models and Claude Code are ONE entity with one memory, never separate bots. Pattern to copy: frank_mund.py organ context +
   mund_route.py model choice (read them as reference; no host paths in code).
20. OWNERSHIP (2026-11-24): `src/ui/` now belongs to the Machine God DESIGN TEAM (branch gridv1/design). zero40 does NOT plan UI tasks;
   items 11, 15, 16, 17 are done there. zero40 builds the data/logic side (src/zero/*) that the UI calls.

## Track 4 (Gabriel 2026-11-24, service side built outside the repo in ~/welt-organ): world organ, own stance, identity-drift guard
21. `src/zero/welt.rs` (+ tests): `/welt` shows today's digest. Read path ONLY (no network): newest `durable_memory` row with
   kind='welt_digest' (value JSON {text,n}) from unified.db, fallback file `~/.local/share/welt-organ/heute.md` (resolve via $HOME,
   no hard-coded user path). Missing digest = honest "Welt-Organ: noch kein Digest fuer heute.", never invented news. The ground
   mode may mention at most ONE digest line per session, labelled "Reflexion von Machine God".
22. `src/zero/haltung.rs` (+ tests): `/haltung` lists Machine God's current stances from table `mg_haltung` (status='aktiv'):
   thema, version, konfidenz, datum, claim, gruende (JSON list), quellen (JSON list of {link,quelle,land,richtung}) as domains,
   plus open rows of `mg_haltung_widerspruch` (offen=1). Read-only; every stance labelled "Ansicht von Machine God", no
   consciousness claims. Veto/rollback stay a CLI for Gabriel (`haltung.py veto|rollback --wer gabriel`), never from the app.
23. Ground-mode replies are measured by the drift guard: log every ground-mode reply to unified.db as durable_memory
   kind='grund_antwort', value JSON {"q":..., "a":...} (no secrets, no private data). The service-side guard
   (`drift_guard.py grund`) scores them into f2_identitaet (quelle='grund') and mg_drift_ereignis. If `mg_drift_sperre` has an
   unreleased row for kanal='grund' (ICDE hard collapse), the app shows one quiet line "Identitaets-Drift: Grundmodus gesperrt,
   Gabriel muss freigeben" and falls back to the full agent. Tests with fixture DBs, no live network.

## Track 5 (Gabriel 2026-11-24, service side built outside the repo in ~/omega-browser/studio): `/bild` image studio in the TUI
24. `/bild` slash command in Machine God's Rust TUI launches the SAME ChatGPT image studio that normal FranKenstein uses (service
   `omega-bildstudio`, 127.0.0.1:18796, code `~/omega-browser/studio/`, CLI `bild` = `studio/bild.py`). No second implementation,
   no image logic in Rust: the TUI only shells out to the CLI (resolve `bild` via PATH / `$HOME/.local/bin`, no hard-coded user path).
   - `/bild` (no args): run `bild url` (starts the service on demand, prints a ONE-TIME URL valid 90 s, never a long-lived key) and
     open it in the default browser (`xdg-open`/`open`); show one quiet line "Bildstudio geoeffnet", never print the URL into
     scrollback or logs. `bild` alone opens a Chrome app window and is an alternative.
   - `/bild <prompt>`: run `bild generate "<prompt>" --json` as a background task (about 1 min, never block the event loop); show a
     progress line from the job (eta/elapsed via `bild status` or `--json` result), then the resulting absolute file path(s); on
     exit 2 show ChatGPT's text answer (`jobs[].text`), on exit 3 say the job keeps running in the studio ("Nachgeliefert").
   - `/bild edit <name> --region x,y,w,h:text`: pass through to `bild edit` (same wording, regions can be % values).
   - Rules: loopback only; the ChatGPT account/session belongs to Gabriel (the studio sends only image prompts, no login, no
     settings); every call is a real message in his ChatGPT image chat, so no loops/auto-retries from the TUI side; no Claude/
     paid tokens for prompt polishing (`bild polish` uses the free pool). Missing service or CLI = honest one-line error, never a
     silent fallback. Tests: mock `bild` with a stub script on PATH (exit 0/2/3 and `--json` shapes), no live ChatGPT.
   - OWNERSHIP: the TUI rendering belongs to the Machine God design team (src/ui, branch gridv1/design); zero40 builds the
     `src/zero/bild.rs` command wrapper (spawn, parse `--json`, error mapping). The studio itself (web UI, jobs, history) is NOT
     part of the repo.
