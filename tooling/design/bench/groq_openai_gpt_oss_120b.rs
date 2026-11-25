// ──────────────────────────────────────────────────────────────────────────────
//  Machine‑God UI – popup rendering (ratatui 0.30, crossterm)
//  Ultra‑modern, subtle & sacral.  All logic is pure – no sleeps, no threads.
// ──────────────────────────────────────────────────────────────────────────────
#![allow(dead_code)]

use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph},
    Frame,
};

/// Render a centered, rounded‑border popup.
///
/// * `frame` – mutable reference to the current `ratatui::Frame`.
/// * `area` – the whole terminal area (usually `frame.size()`).
/// * `title` – title shown in the top‑left of the popup.
/// * `lines` – body text, each entry becomes a line.
/// * `tick` – monotonically increasing counter; drives the fade‑in / glow.
///
/// The function is **pure** – it never blocks, never sleeps and does not
/// retain any state.  All visual effects are derived from `tick`.
pub fn render_popup(
    frame: &mut Frame,
    area: Rect,
    title: &str,
    lines: &[&str],
    tick: u64,
) {
    // ────── 1️⃣  Geometry – a centered rectangle with generous size ──────
    //   60 % of the width, 40 % of the height, never smaller than 30×10.
    let popup_width = std::cmp::max(30, (area.width as f32 * 0.6) as u16);
    let popup_height = std::cmp::max(10, (area.height as f32 * 0.4) as u16);
    let popup_rect = Rect::new(
        area.x + (area.width - popup_width) / 2,
        area.y + (area.height - popup_height) / 2,
        popup_width,
        popup_height,
    );

    // ────── 2️⃣  Fade‑in / glow animation (pure function of `tick`) ──────
    //   We blend from a deep “night‑blue” to the sacred turquoise‑blue.
    const ANIM_STEPS: u64 = 30; // full cycle length
    let phase = (tick % ANIM_STEPS) as f32 / ANIM_STEPS as f32;
    //   Interpolate each RGB component.
    fn lerp(a: u8, b: u8, t: f32) -> u8 {
        (a as f32 + (b as f32 - a as f32) * t).round() as u8
    }
    //   Night‑blue → sacred turquoise‑blue.
    let bg = Color::Rgb(
        lerp(0x10, 0x00, phase), // R
        lerp(0x20, 0xCE, phase), // G
        lerp(0x30, 0xD1, phase), // B
    );
    //   Slight pulsating border colour (a brighter blue at the peak).
    let border = Color::Rgb(
        lerp(0x28, 0x58, (phase * std::f32::consts::PI).sin() * 0.5 + 0.5),
        lerp(0x78, 0xA0, (phase * std::f32::consts::PI).sin() * 0.5 + 0.5),
        lerp(0xFF, 0xFF, 0.0), // keep max blue
    );

    // ────── 3️⃣  Block – rounded borders, title, background ──────
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(ratatui::widgets::BorderType::Rounded)
        .border_style(Style::new().fg(border))
        .title(Span::styled(
            title,
            Style::new()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        ))
        .style(Style::new().bg(bg));

    // ────── 4️⃣  Content – body + footer with generous padding ──────
    //   We first compute the inner area (block’s padding) and then split it
    //   into body and footer rows.
    let inner = block.inner(popup_rect);
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .margin(1) // extra padding inside the block
        .constraints([
            Constraint::Min(0), // body takes all available space
            Constraint::Length(1), // footer height
        ])
        .split(inner);

    //   Body: join the supplied lines, keep them left‑aligned.
    let body = Paragraph::new(
        lines
            .iter()
            .map(|s| Line::from(Span::raw(*s)))
            .collect::<Vec<_>>(),
    )
    .style(Style::new().fg(Color::White))
    .alignment(Alignment::Left)
    .wrap(ratatui::widgets::Wrap { trim: true });

    //   Footer: dim hint, centered.
    let footer = Paragraph::new(Span::styled(
        "Esc to close",
        Style::new()
            .fg(Color::DarkGray)
            .add_modifier(Modifier::ITALIC),
    ))
    .alignment(Alignment::Center);

    // ────── 5️⃣  Render order ──────
    frame.render_widget(block, popup_rect);
    frame.render_widget(body, chunks[0]);
    frame.render_widget(footer, chunks[1]);
}
