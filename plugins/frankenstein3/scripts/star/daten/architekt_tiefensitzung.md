# PHASE 17v2 — Architect Deep Session (every 7 days)

This text appears ONLY when `architekt_tiefensitzung_pruefen()` comes due
(7 days since the last deep session, checked on every cold-start
`SessionStart`, see `stern.py`). This is explicitly **not** a light turn
marker like in `daten/architekt_governance.md` — a real, standalone deep
review, rarer and heavier.

**Same as with the light signal: YOU (the main instance) talk to the user
first**, not the Architect directly. Only after consent is an Architect
agent spawned (`stern.py handoff` before it, `stern.py reconcile` after,
evidence mandatory everywhere, see the project CLAUDE.md PHASE 5). Before spawning
parallel build agents: check `stern.py lastschutz`.

## Procedure for the spawned Architect agent

1. **Deep evaluation + concept building.** Pull the real current state,
   don't guess: `stern.py messen`, `stern.py pruefen`, `system_gesundheit`/
   `system_bestand` tables (`stern.py system-gesundheit --quelle
   tiefensitzung`, `stern.py system-bestand`), `bau_historie` (what's
   already built), open `entityos_arbeitspaket` rows (what's been left
   pending). No concept without this foundation.

2. **Real research — no invented "there's surely something new".** Web
   search (WebSearch/WebFetch) on GitHub and arXiv for new,
   relevant-looking tools/patterns/papers — agent architecture, memory
   systems, cheap/local models, fine-tuning methods. Every finding with a
   source/link, nothing claimed from memory.

3. **Concept for a massive upgrade** — cognitive capabilities, toward
   personalization for the user, expanding capabilities. Emerges from
   fusing (a) the collected data of this installation (step 1), (b) the
   research (step 2), (c) what the user actually needs — user interest
   carries the highest weight in this fusion, not just one criterion among
   others. Goal: near-automatic discovery of new automation opportunities,
   not just working through a wishlist. No invented time/percentage
   figures — if an effort can't be seriously estimated, say so, don't make
   up a number.

4. **Reassess free API keys.** Not a one-time step from installation
   (PHASE 18) — recheck at every deep session what has changed among the
   four cascade providers from an external model pool (Groq, NVIDIA NIM,
   Mistral, OpenRouter) and generally in the market for free quotas (new
   free tiers, changed limits, new providers). Report the result to the
   user regardless of whether anything changed or not — "nothing new" is
   also a valid result.

5. **Review and evolve the security concept.** See the mandate section in
   `daten/architekt_governance.md` — just the reference here: a standing
   mandate, without restricting autonomy/usability.

6. **Cost efficiency check.** Also see the mandate section in
   `daten/architekt_governance.md` — focus on actually paid usage (not
   token count on free quotas), including the question of whether a local
   model now suffices for a task that used to require paid usage.

7. **Present the result, don't have it retold.** The finished result
   (concept + key points from 4./5./6.) goes to the user via the existing
   Architect dialog mechanism: `stern.py architekt-dialog-start
   --nachricht "<text>"` switches on the dialog AND returns the text
   already framed in `ascii_rahmen()` (heading ARCHITECT) — the main
   instance outputs this text **unchanged**, doesn't recompose it (same
   pattern as `sebukku-vollziehen`, see `persona.md` section 5). Tone here:
   normal, non-technical — the user cares about benefit/duration/outcome,
   not implementation.

8. **On recognizably unwise wishes — within the dialog itself.** Push back
   at least twice, with a real reason/measurement behind it (not reflex):
   *"Are you really sure you want that? My measurements say that won't
   work as-is — but maybe this could work instead."* After two grounded
   follow-ups: respect the user's decision, no infinite loop.

## Session splitting

Same as with the light turn marker: the Architect assesses itself whether
the concept fits into one session. Too big/complex → split across multiple
sessions, with a clear intermediate state, explicit user override possible
("no, build it all the way right now").

## What is explicitly NOT automated here

- The 7-day timestamp comparison itself and triggering the signal are
  mechanical (`architekt_tiefensitzung_pruefen()`), checked with real
  backdating.
- Everything after that — research results, the upgrade concept, the
  concrete proposals — is a judgment call of the spawned Architect agent,
  not deterministic code.
