use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    style::{Color, Style},
    widgets::{Block, Borders, BorderType, Padding, Paragraph, Wrap},
    Frame,
};

fn lerp_color(a: Color, b: Color, t: f64) -> Color {
    match (a, b) {
        (Color::Rgb(r1, g1, b1), Color::Rgb(r2, g2, b2)) => {
            let t = t.clamp(0.0, 1.0);
            Color::Rgb(
                (r1 as f64 + (r2 as f64 - r1 as f64) * t) as u8,
                (g1 as f64 + (g2 as f64 - g1 as f64) * t) as u8,
                (b1 as f64 + (b2 as f64 - b1 as f64) * t) as u8,
            )
        }
        _ => b,
    }
}

pub fn render_popup(frame: &mut Frame, area: Rect, title: &str, lines: &[&str], tick: u64) {
    let turquoise = Color::Rgb(0, 206, 209);
    let blue = Color::Rgb(40, 120, 255);
    let bg = Color::Rgb(15, 20, 28);
    let dim_bg = Color::Rgb(6, 9, 14);

    // Subtle pulse: 0.0 → 1.0 → 0.0, pure function of tick.
    let pulse = ((tick as f64 * 0.05).sin() + 1.0) / 2.0;
    let border_color = lerp_color(Color::Rgb(0, 70, 85), turquoise, pulse);
    let title_color = lerp_color(turquoise, blue, pulse);

    // Centered geometry with generous bounds.
    let width = area.width.saturating_sub(4).min(72);
    let height = (lines.len() as u16 + 6).min(area.height.saturating_sub(4));
    let x = area.left() + (area.width.saturating_sub(width)) / 2;
    let y = area.top() + (area.height.saturating_sub(height)) / 2;
    let popup_area = Rect::new(x, y, width, height);

    // Dim the surrounding area so the popup feels like a modal.
    let dim = Block::default().style(Style::default().bg(dim_bg));
    frame.render_widget(dim, area);

    // Build body text.
    let mut text = String::new();
    for (i, line) in lines.iter().enumerate() {
        if i > 0 {
            text.push('\n');
        }
        text.push_str(line);
    }

    // Rounded border block with generous padding and a thin accent glyph.
    let block = Block::default()
        .title(format!(" ◈ {} ", title))
        .title_alignment(Alignment::Center)
        .title_style(Style::default().fg(title_color))
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(border_color))
        .style(Style::default().bg(bg))
        .padding(Padding::new(1, 4, 1, 4));

    let inner = block.inner(popup_area);
    frame.render_widget(block, popup_area);

    // Inner layout: top pad, content, footer hint.
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1),
            Constraint::Min(0),
            Constraint::Length(1),
        ])
        .split(inner);

    let paragraph = Paragraph::new(text)
        .style(Style::default().fg(Color::Rgb(220, 230, 240)).bg(bg))
        .alignment(Alignment::Center)
        .wrap(Wrap { trim: true, ..Default::default() });
    frame.render_widget(paragraph, chunks[1]);

    let hint = Paragraph::new("Esc to close")
        .style(Style::default().fg(Color::Rgb(90, 100, 110)).bg(bg))
        .alignment(Alignment::Center);
    frame.render_widget(hint, chunks[2]);
}
