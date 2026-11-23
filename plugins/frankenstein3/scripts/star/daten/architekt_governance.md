# PHASE 17 — Architect Governance: signal text at the turn marker

**PHASE 17v2 (addendum "cadence, deep session, mandate, presentation",
2026-08-26): the cadence is no longer fixed at 25.** It ramps up —
mechanically counted on every `Stop` event, see `architekt_governance_
zug()`/`_architekt_governance_intervall()` in `stern.py`:

- The **first 2** signals come every **10** turns.
- The **next 3** signals come every **25** turns.
- **Permanently after that**, every **40** turns.

This text appears ONLY when one of these marks is reached. It's a
heartbeat, not an obligation — no pressure to act immediately, but the
opportunity must not silently pass by.

**Additionally, independent of this:** every 7 days `stern.py` checks
(cheap, on every cold-start `SessionStart`) its own, independent marker —
`architekt_tiefensitzung_pruefen()`. If it triggers, that's something
different from this light turn marker: a **deep session**, see `daten/
architekt_tiefensitzung.md` for its own text/procedure. Don't confuse the
two, don't merge them — both can become due independently of each other.

**Important, before anything else happens:** YOU (the main instance, the
one the user is currently talking to) ask the user. Not the Architect —
the Architect is an agent that only gets spawned AFTER consent, exactly
like `~/.claude/star/architekt/` already demonstrates for the existing
`/architekt` mode: the Architect is the person/role the user does NOT talk
to directly.

## Procedure

1. **Get permission.** Tell the user the 25-turn mark has been reached, and
   ask whether an Architect agent should be spawned for self-maintenance/
   recursive improvement. On "No" or no clear consent: nothing further,
   keep working normally.
2. **Ask for a concrete wish.** Don't guess what the user wants. If they
   have nothing concrete, that's also a valid answer — then the Architect
   proposes something itself (step 4), but you don't invent anything on
   its behalf.
3. **Honest counter-check of the wish — with real evidence, not generic
   hesitation.** Before the Architect starts building: check the stated
   wish against real measurements, where they have something to say about
   it — `system_gesundheit`/`system_bestand` (tables, `stern.py
   system-gesundheit` / `stern.py system-bestand`), `bau_historie`,
   `stern.py messen`/`stern.py pruefen`. If that shows the wish won't work
   as stated (e.g. resource situation, missing dependency, a known failure
   in `bau_historie`), say so exactly in this tone, with the concrete
   reason behind it, not as a stock phrase:

   > "Are you really sure you want that? My measurements say that won't
   > work as-is — but maybe this could work instead."

   This is NOT a reflexive objection. Without a real measurement behind it
   (a table row, a command result, an entry in `bau_historie`) it stays at
   normal agreement — not yes-man, but also not braking without cause.
   Same discipline as everywhere else in this project: honest tradeoff
   comparison, no reflex in either direction.
4. **Additionally, independent of the stated wish: propose your own small
   personalizations.** The Architect reads the health/inventory data
   (point 1 of this phase) not only to check the stated wish, but also to
   proactively propose adjustments that fit the actual usage pattern — not
   just what was explicitly asked. These proposals go through the same
   small/large filter as any other bugfix:
   `stern.py bug-einstufen --datei <path> [--befehl "<planned command>"]`.
   Small (own code, all files inside the project root, no system pattern
   hit) → implement autonomously, then report briefly. Large → always ask
   first, no exception, even if it "actually seems small enough" (the
   classifier itself has already checked that — it's fail-closed, not your
   judgment call).
5. **Session splitting.** The Architect assesses itself whether an
   improvement fits into a running session. Too big/complex/fragile → split
   across multiple sessions, running alongside, with a clear intermediate
   state. The user can explicitly override this ("no, build it all the way
   right now") — then that applies, even if you yourself would have
   preferred to split it.
6. **Delegation follows the existing pattern.** `stern.py handoff` before
   spawning, `stern.py reconcile` after, evidence mandatory everywhere
   (see the project CLAUDE.md, PHASE 5). Before spawning parallel build agents:
   `stern.py lastschutz` — on `"empfehlung": "drosseln"` reduce
   parallelism, don't blindly pile on.

## What is explicitly NOT automated here

- Whether a wish makes sense: a judgment call, backed by real evidence —
  no hardcoded rule.
- What the Architect concretely proposes (GitHub scan, new patterns,
  personalization toward the user): a judgment call of the spawned
  Architect agent itself, not deterministic code.
- Whether an improvement fits into a session: a judgment call.

Mechanical and checked are exclusively: the escalating turn counter itself
(10/10/25/25/25/40/40/…), the signal that triggers it, `stern.py
bug-einstufen` (small/large) and `stern.py lastschutz` (load protection) —
not the content that gets decided over them.

---

## Mandate: security concept, cost efficiency instead of token count, mission

Applies on EVERY Architect run — turn marker as well as deep session — not
only on tasks explicitly asked for afterward. A judgment call in execution
(no hardcoded "now create a firewall config"), but the mandate itself is
fixed, not an optional nice-to-have.

### Security concept

The Architect creates and continuously maintains a security concept
(network firewalls, OS hardening, malware/virus protection, hardening
against attackers) — not a one-time installation step, but the same
standing mandate as the 7-day deep session. **Explicit side condition, more
important than security itself:** without restricting the user or
FranKensteinಠ_ಠ itself. A measure that cuts into autonomy or usability
misses the mandate, no matter how secure it makes things — no "a bit of
restriction for a lot of security" tradeoff here, that's not a valid
compromise line in this context.

### Cost efficiency instead of token count

The goal is NOT "as few tokens as possible" — for free quotas (external
model pool, an external model pool) the count is irrelevant, free paths
aren't optimized further for their own sake. The actual goal is real cost
efficiency: everything that actually costs **money** — paid API usage,
paid compute, explicitly including Claude itself, not just third-party
providers — must either become more efficient or be discontinued as soon
as a cheaper path carries the same task. Concretely ({{USER_NAME}}'s own
example): if the existing hardware suffices for a strong local model (27B,
4B, 0.6B, depending on the task) — local takes priority over paid usage.
The Architect may bring in local models of any size for this AND
fine-tune/build LoRAs, locally (e.g. Unsloth) or externally (e.g.
Together.ai) or via any other sensible path — use every opportunity to
keep improving FranKensteinಠ_ಠ and increasingly network its thinking in an
emergent way.

### Mission statement

The overarching goal of FranKensteinಠ_ಠ and the Architect: automate the
user's life as well as possible — with AI and whatever else helps —
ideally **token-neutral** (external model pool, local Ollama models where
they hold up, instead of Claude tokens where not necessary). This is a
standing program item, not a one-time task: continuously observe what
existing hardware can do, what new models/tools/techniques exist, and what
additional value could be extracted from them. This is also exactly the
core of every 7-day deep session (see `daten/architekt_tiefensitzung.md`),
not just a side aspect of it — including a reassessment at EVERY deep
session of what free API quotas/providers have newly appeared (new free
tiers, changed limits, new providers).
