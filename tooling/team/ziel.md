Gabriel's words (German, verbatim, 2026-11-23):
- "zuerst bauen wir entitz os ein als intrinsisches betriebszstem"
- "entyty os als grundlegende auf kerner ebene arbeitende betriebsschicht bzw usichtbares grundlegnedes substrat"
- "sie sollen den grid und entityos das echte also das beytriebsystem zu einer festen einheit machen die eine rueckopllung nicht ermoeglicht sondern auf kernel ebenen zur grundlage der funktion macht"
  (= fuse GRID and the real EntityOS into ONE fixed unit; not a feedback coupling bolted on, but the kernel-level foundation the whole function runs on.)

Host program: our fork of gschaidergabriel/machine-god (Apache-2.0), ~/claude-code-rust, commit 1750588, baseline release build OK.
Layers today: Rust TUI (src/, 386 files, ~143k lines, Ratatui) -> Bun bridge (agent-sdk/src, TypeScript) -> Anthropic Agent SDK -> bundled claude CLI -> model API.
Single per-turn seam found: agent-sdk/src/bridge/session_lifecycle.ts buildQueryOptions() (systemPrompt, programmatic hooks, canUseTool, settings, spawnClaudeCodeProcess).

Sources you get as chunks: live hyperGRID turn loop from machine-b (frankenstein-repo, branch with uncommitted live diff), machine-A GRID10 modules (~/.claude/star/modules/grid10, frank3_gwt.py), EntityOS.git (schema, ARCHITECTURE), EntityOS V1 binding/J-Space code, claude-rs bridge seam.

Hard constraints (non-negotiable):
- Exactly one canonical state store: ~/.local/share/agentzero/unified.db, one-door write authority per table family. No second DB, no second GRID.
- "Kernel level" must be stated honestly: claude-rs is a userspace process. Say precisely which layer becomes the non-bypassable core (process substrate, bridge, OS service/cgroup, etc.) and what real OS-kernel mechanisms (if any) are proposed and why.
- Fail-closed: if the substrate is down or violates an invariant, the host must refuse/degrade visibly, never silently run without it.
- No money/trading/crypto actions anywhere; no secrets in prompts/logs/commits; never read another machine's screen/camera/audio (Retina rule); deleting real data only with Gabriel.
- Machine budget: 24 GB RAM, heavy work under lowprio + mem-guard.
- Evidence rule: finished = verified by test/measurement, not model claims. UNKNOWN stays UNKNOWN.
