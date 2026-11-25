use ratatui::widgets::{Block, Borders, BorderType, Paragraph, Alignment, Padding};
use ratatui::style::{Style, Color, Modifier};
use ratatui::layout::{Rect, Direction, Layout, Constraint};
use ratatui::Frame;

/// Render a centered popup with rounded borders, generous padding,
/// a subtle glow animation driven by `tick`, and a dim footer hint.
pub fn render_popup(frame: &mut Frame, area: Rect, title: &str, lines: &[&str], tick: u64) {
    // --- compute a centered, reasonably sized rectangle -----------------
    let width = area.width.saturating_sub(10).min(60);
    let height = area.height.saturating_sub(10).min(lines.len() as u16 + 6);
    let x = area.x + (area.width - width) / 2;
    let y = area.y + (area.height - height) / 2;
    let popup_area = Rect::new(x, y, width, height);

    // --- glow animation (pure function of tick) -------------------------
    let phase = (tick % 60) as f32 / 60.0 * std::f32::consts::PI;
    let intensity = (phase.sin() * 0.5 + 0.5) as f32; // 0.0 … 1.0
    let border_color = interpolate_color((0, 206, 209), (40, 120, 255), intensity);

    // --- build the block ------------------------------------------------
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .style(Style::default().fg(border_color))
        .title(title)
        .title_style(Style::default().fg(Color::White).add_modifier(Modifier::BOLD))
        .title_alignment(Alignment::Center)
        .padding(Padding::uniform(2));

    frame.render_widget(block, popup_area);

    // --- inner area ------------------------------------------------------
    let inner = block.inner(popup_area);
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(0), Constraint::Length(1)])
        .split(inner);

    let content_area = chunks[0];
    let footer_area = chunks[1];

    // --- message lines ---------------------------------------------------
    let content = Paragraph::new(lines.join("\n"))
        .style(Style::default().fg(Color::White))
        .alignment(Alignment::Left);
    frame.render_widget(content, content_area);

    // --- dim footer hint -------------------------------------------------
    let footer = Paragraph::new("Esc to close")
        .style(Style::default().fg(Color::DarkGray))
        .alignment(Alignment::Center);
    frame.render_widget(footer, footer_area);
}

/// Linear interpolation between two RGB triples.
fn interpolate_color(c1: (u8, u8, u8), c2: (u8, u8, u8), t: f32) -> Color {
    let r = (c1.0 as f32 + (c2.0 as f32 - c1.0 as f32) * t).round() as u8;
    let g = (c1.1 as f32 + (c2.1 as f32 - c1.1 as f32) * t).round() as u8;
    let b = (c1.2 as f32 + (c2.2 as f32 - c1.2 as f32) * t).round() as u8;
    Color::Rgb(r, g, b)
}
