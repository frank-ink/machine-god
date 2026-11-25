//! A calm, centered popup with a soft fade-in glow.
//! Pure function of `tick` — no timers, no sleeps, no state.

use ratatui::{
    layout::{Alignment, Constraint, Flex, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, BorderType, Borders, Clear, Padding, Paragraph, Wrap},
    Frame,
};

const TURQUOISE: (u8, u8, u8) = (0x00, 0xCE, 0xD1);
const BLUE: (u8, u8, u8) = (0x28, 0x78, 0xFF);

fn mix(a: (u8, u8, u8), b: (u8, u8, u8), t: f32) -> (u8, u8, u8) {
    let t = t.clamp(0.0, 1.0);
    (
        (a.0 as f32 + (b.0 as f32 - a.0 as f32) * t).round() as u8,
        (a.1 as f32 + (b.1 as f32 - a.1 as f32) * t).round() as u8,
        (a.2 as f32 + (b.2 as f32 - a.2 as f32) * t).round() as u8,
    )
}

fn shade(c: (u8, u8, u8), f: f32) -> Color {
    let f = f.clamp(0.0, 1.0);
    Color::Rgb(
        (c.0 as f32 * f).round() as u8,
        (c.1 as f32 * f).round() as u8,
        (c.2 as f32 * f).round() as u8,
    )
}

pub fn render_popup(frame: &mut Frame, area: Rect, title: &str, lines: &[&str], tick: u64) {
    if area.width < 12 || area.height < 6 {
        return;
    }

    // --- animation: smooth fade-in, then a slow breathing glow ----------
    let t = tick as f32;
    let fade = {
        let x = (t / 18.0).clamp(0.0, 1.0);
        x * x * (3.0 - 2.0 * x) // smoothstep
    };
    let vis = 0.10 + 0.90 * fade;
    let pulse = 0.5 + 0.5 * (t * 0.075).sin();

    let accent = mix(TURQUOISE, BLUE, 0.25 + 0.35 * pulse);
    let border_fg = shade(accent, vis);
    let title_fg = shade(accent, vis);
    let body_fg = shade((198, 210, 222), vis);
    let hint_fg = shade((118, 130, 144), vis * 0.95);
    let bg = shade((9, 14, 22), 0.35 + 0.65 * fade);

    // --- geometry: generous padding, centered, content-sized ------------
    let pad_x: u16 = 4;
    let pad_y: u16 = 2;

    let content_w = lines.iter().map(|l| l.chars().count()).max().unwrap_or(0) as u16;
    let title_w = title.chars().count() as u16 + 4;
    let inner_w = content_w.max(title_w).max(20);

    let max_w = area.width.saturating_sub(2);
    let max_h = area.height.saturating_sub(2);
    let w = (inner_w + pad_x * 2 + 2).min(max_w);
    let h = (lines.len() as u16 + pad_y * 2 + 4).min(max_h);

    let row = Layout::vertical([Constraint::Length(h)])
        .flex(Flex::Center)
        .split(area)[0];
    let popup = Layout::horizontal([Constraint::Length(w)])
        .flex(Flex::Center)
        .split(row)[0];

    frame.render_widget(Clear, popup);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(border_fg))
        .style(Style::default().bg(bg))
        .padding(Padding::new(pad_x, pad_x, pad_y, pad_y))
        .title(Line::from(vec![
            Span::styled("◈ ", Style::default().fg(title_fg)),
            Span::styled(
                title,
                Style::default().fg(title_fg).add_modifier(Modifier::BOLD),
            ),
        ]));

    let inner = block.inner(popup);
    frame.render_widget(block, popup);

    let chunks = Layout::vertical([Constraint::Min(0), Constraint::Length(1)]).split(inner);

    let body: Vec<Line> = lines
        .iter()
        .map(|l| Line::from(Span::styled(*l, Style::default().fg(body_fg))))
        .collect();
    frame.render_widget(
        Paragraph::new(body).wrap(Wrap { trim: false }),
        chunks[0],
    );

    let hint = Paragraph::new(Line::from(vec![
        Span::styled(
            "Esc",
            Style::default().fg(hint_fg).add_modifier(Modifier::BOLD),
        ),
        Span::styled(" to close", Style::default().fg(hint_fg)),
    ]))
    .alignment(Alignment::Center);
    frame.render_widget(hint, chunks[1]);
}
