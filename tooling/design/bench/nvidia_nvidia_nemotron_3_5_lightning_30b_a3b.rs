use ratatui::prelude::*;
use ratatui::widgets::{Block, BorderType, Borders, Paragraph};
use ratatui::style::{Color, Style};
use ratatui::layout::Rect;

pub fn render_popup(frame: &mut Frame, area: Rect, title: &str, lines: &[&str], tick: u64) {
    // Centered popup area: 60% width, ~40% height, integer-safe sizing
    let popup_w = (area.width * 6 / 10).max(30);
    let popup_h = (area.height * 2 / 5).max(10).min(area.height);
    let popup_x = area.x + (area.width - popup_w) / 2;
    let popup_y = area.y + (area.height - popup_h) / 2;
    let popup_area = Rect::new(popup_x, popup_y, popup_w, popup_h);

    // Subtle tick-driven animation: pure math, no sleeping, no blocking
    let t = tick as f64;
    let progress = (t * 0.004).sin() * 0.3 + 0.5; // oscillates [0.2, 0.8]

    // Interpolated accent between turquoise #00CED1 and blue #2878FF
    let tr = (0.0 + 40.0 * progress) as u8;
    let tg = (206.0 + (120.0 - 206.0) * progress) as u8;
    let tb = (209.0 + (255.0 - 209.0) * progress) as u8;
    let accent = Color::Rgb(tr, tg, tb);

    // Content with thin glyph accent and footer hint
    let text = format!("{} ◈\n{}\n\nEsc to close", title, lines.join("\n"));

    // Rounded border block with subtle black background
    let block = Block::new()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .style(Style::default().bg(Color::Rgb(0, 0, 0)));

    frame.render_widget(block, popup_area);

    // Inner padded area for the paragraph
    let inner = Rect::new(
        popup_area.x + 3,
        popup_area.y + 3,
        popup_area.width.saturating_sub(6),
        popup_area.height.saturating_sub(6),
    );

    let paragraph = Paragraph::new(text)
        .style(Style::default().fg(accent))
        .block(Block::default().borders(Borders::NONE));

    frame.render_widget(paragraph, inner);
}
