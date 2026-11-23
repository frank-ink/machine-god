// SPDX-License-Identifier: Apache-2.0

//! Machine God welcome banner: an all-seeing machine eye above the name, a sacral motto below,
//! coloured from turquoise (top) to blue (bottom). Narrow terminals get a one-line fallback.

use crate::ui::theme;
use crate::ui::wrap::display_width;
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};

/// Every row has the same display width so the figure stays symmetric when centered.
const ART: [&str; 11] = [
    "         ·         ┃         ·         ",
    "     ·        ╲    ▲    ╱        ·     ",
    "  ━━━━━━━━━━━━━━  ╱ ╲  ━━━━━━━━━━━━━━  ",
    "                 ╱ ◉ ╲                 ",
    "  ━━━━━━━━━━━━  ╱▁▁▁▁▁╲  ━━━━━━━━━━━━  ",
    "     ·        ╱    ┃    ╲        ·     ",
    "         ·         ┃         ·         ",
    "                                       ",
    "┏┳┓ ┏━┓ ┏━╸ ╻ ╻ ╻ ┏┓╻ ┏━╸   ┏━╸ ┏━┓ ╺┳┓",
    "┃┃┃ ┣━┫ ┃   ┣━┫ ┃ ┃┗┫ ┣╸    ┃╺┓ ┃ ┃  ┃┃",
    "╹ ╹ ╹ ╹ ┗━╸ ╹ ╹ ╹ ╹ ╹ ┗━╸   ┗━┛ ┗━┛ ╺┻┛",
];
const EYE: char = '◉';
const MOTTO: [&str; 2] = ["✠  DEUS · EX · MACHINA  ✠", "IN SILICO VERITAS"];
/// Narrow terminals: the widest name that still fits.
const FALLBACK: [&str; 2] = ["✠ MACHINE GOD ✠", "MACHINE GOD"];
const EYE_COLOR: Color = Color::Rgb(220, 255, 255);

fn mix(a: u8, b: u8, i: usize, n: usize) -> u8 {
    let (a, b) = (i32::from(a), i32::from(b));
    let i = i32::try_from(i).unwrap_or(0);
    let span = i32::try_from(n.saturating_sub(1).max(1)).unwrap_or(1);
    u8::try_from((a + (b - a) * i / span).clamp(0, 255)).unwrap_or(0)
}

/// Turquoise (0, 230, 220) on the first row fading to blue (40, 120, 255) on the last.
pub(crate) fn row_color(i: usize, n: usize) -> Color {
    Color::Rgb(mix(0, 40, i, n), mix(230, 120, i, n), mix(220, 255, i, n))
}

fn left_pad(text: &str, width: usize) -> String {
    " ".repeat(width.saturating_sub(display_width(text)) / 2)
}

/// Banner rows for a terminal `width` columns wide.
pub(crate) fn banner_lines(width: usize) -> Vec<Line<'static>> {
    let mut lines = Vec::new();
    if width >= display_width(ART[0]) {
        let pad = left_pad(ART[0], width);
        for (i, row) in ART.iter().enumerate() {
            let style = Style::default().fg(row_color(i, ART.len())).add_modifier(Modifier::BOLD);
            let mut spans = vec![Span::raw(pad.clone())];
            if let Some((before, after)) = row.split_once(EYE) {
                spans.push(Span::styled(before.to_owned(), style));
                spans.push(Span::styled(
                    EYE.to_string(),
                    Style::default().fg(EYE_COLOR).add_modifier(Modifier::BOLD),
                ));
                spans.push(Span::styled(after.to_owned(), style));
            } else {
                spans.push(Span::styled((*row).to_owned(), style));
            }
            lines.push(Line::from(spans));
        }
    } else if let Some(name) = FALLBACK.iter().find(|f| display_width(f) <= width) {
        let style = Style::default().fg(theme::ACCENT).add_modifier(Modifier::BOLD);
        lines.push(Line::from(vec![Span::raw(left_pad(name, width)), Span::styled(*name, style)]));
    }
    for motto in MOTTO {
        if display_width(motto) <= width {
            let style = Style::default().fg(theme::ACCENT).add_modifier(Modifier::ITALIC);
            lines.push(Line::from(vec![Span::raw(left_pad(motto, width)), Span::styled(motto, style)]));
        }
    }
    lines.push(Line::default());
    lines
}

#[cfg(test)]
mod tests {
    use super::*;

    fn text(line: &Line<'_>) -> String {
        line.spans.iter().map(|s| s.content.as_ref()).collect()
    }

    #[test]
    fn art_rows_share_one_odd_width() {
        let w = display_width(ART[0]);
        assert!(ART.iter().all(|row| display_width(row) == w), "uneven art rows");
        assert_eq!(w % 2, 1, "odd width keeps a single centre column for the eye");
        assert_eq!(ART[3].chars().position(|c| c == EYE), Some(w / 2), "eye sits on the centre column");
    }

    #[test]
    fn banner_never_exceeds_the_terminal_width() {
        for width in [1, 8, 11, 14, 15, 16, 20, 38, 39, 40, 80, 200] {
            for line in banner_lines(width) {
                assert!(display_width(&text(&line)) <= width, "width {width}: {}", text(&line));
            }
        }
    }

    #[test]
    fn wide_terminals_show_the_eye_narrow_ones_the_fallback() {
        let wide: Vec<String> = banner_lines(80).iter().map(text).collect();
        assert!(wide.iter().any(|l| l.contains(EYE)));
        assert!(wide.iter().any(|l| l.contains("DEUS")));
        let narrow: Vec<String> = banner_lines(20).iter().map(text).collect();
        assert!(narrow.iter().any(|l| l.contains("MACHINE GOD")));
        assert!(!narrow.iter().any(|l| l.contains(EYE)));
    }

    #[test]
    fn gradient_runs_from_turquoise_to_blue() {
        assert_eq!(row_color(0, ART.len()), Color::Rgb(0, 230, 220));
        assert_eq!(row_color(ART.len() - 1, ART.len()), Color::Rgb(40, 120, 255));
    }
}
