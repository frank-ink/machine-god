# Design goal (Gabriel 2026-11-24, replaces the blue goal; old version: ziel.md.bak-blau-20261124)

Base: branch `gridv1/design-mg` = the public repo `main` (github.com/frank-ink/machine-god).
Principle: KEEP the original Claude Code Rust design exactly as it is. Layout, chat flow, input, tool calls,
footer, scrollback, key handling: unchanged. Only two things change:

## 1. The crab becomes the Machine God motif (src/ui/welcome.rs)
- `src/ui/machine_god_art.rs` already exists (generated from `assets/machine-god.gif`, do not edit by hand):
  `FRAME_MS` (450), `FRAME_COUNT` (3), `LARGE_ART`/`LARGE_MASK` (40x20 braille), `SMALL_ART`/`SMALL_MASK` (24x12).
  Mask chars per cell: `.` none, `g` gray, `w` light gray, `r` red, `R` bright red.
- Replace the Ferris column (`ferris_rows(ferris)`) with the motif: same place (left of the overview text),
  LARGE when the terminal is wide enough for 40 cols + gap + text, else SMALL, else text only (as today).
- Animation: frame index = elapsed time since app start / FRAME_MS % FRAME_COUNT (the red pulse: halo, eyes,
  gate, beam). Tick-driven like Ferris today; deterministic for a given instant (testable).
- Colors from the mask: g = Rgb(110,110,110), w = Rgb(205,205,205), r = Rgb(150,30,35), R = Rgb(255,45,45).
  Under NO_COLOR: plain braille, no color.
- Remove the turquoise eye banner from the welcome (`sacred_banner::banner_lines` call in `overview_lines`).
  The module may stay; its own tests must still pass or be adapted.
- Keep the exported names used elsewhere (`ferris_frame`, `ferris_phase`, `FerrisPhase`, `FerrisFrame`,
  `welcome_commit_ready`) compiling; additive changes preferred.

## 2. All colors follow the GIF: black, gray, white, red. No blue, no turquoise. (src/ui/theme.rs)
- `ACCENT` = Rgb(200,30,40) (blood red), `ROLE_ASSISTANT` follows ACCENT.
- `BTW_ACCENT`, `ULTRACODE_ACCENT`, `SLASH_COMMAND`, `SUBAGENT_TOKEN`: red/gray shades, never blue/cyan.
- `USER_MSG_BG` = dark gray-red, e.g. Rgb(38,14,16). `DIM` stays DarkGray.
- Check every `Color::Cyan|LightCyan|Blue|LightBlue|Rgb(` in src/ui for blue/turquoise leftovers and replace them.
- Errors stay distinguishable: STATUS_ERROR must still differ from ACCENT (e.g. bright Rgb(255,80,80) + bold).

## Tests (required with every change)
- Welcome at widths 40 / 80 / 200: no row exceeds the width; 200 shows LARGE, 80 shows SMALL or text only.
- Frame selection deterministic for fixed instants; 3 different frames over 3*FRAME_MS.
- No blue/cyan constant left in theme.rs (test asserts every theme color has b <= r or is a gray).
- Existing tests stay green; adapt tests that asserted turquoise/blue, do not delete coverage.

## Do not
- Do not rename product strings or binaries (claude-rs -> machine-god happens on branch gridv1/rename).
- Do not touch anything outside src/ui/.
