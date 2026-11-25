use ratatui::{
    style::{Color, Modifier, Style},
    widgets::{Block, Borders, BorderType, Paragraph},
    layout::{Alignment, Rect},
    Frame,
};

/// Renders a polished, sacral-themed popup.
/// `tick` is used to drive a subtle glow/fade animation (sine wave).
pub fn render_popup(frame: &mut Frame, area: Rect, title: &str, lines: &[&str], tick: u64) {
    // Calculate dynamic animation value (sine wave for breathing glow)
    let glow = ((tick as f64 * 0.05).sin() + 1.0) / 2.0;
    
    // Color palette: Turquoise #00CED1 to Blue #2878FF
    let color_primary = Color::Rgb(0, 206, 209);
    let color_secondary = Color::Rgb(40, 120, 255);
    
    // Interpolate border color based on glow for a "living" effect
    let border_color = if glow > 0.5 { color_primary } else { color_secondary };

    // Define popup dimensions (centered, max 60% of screen)
    let width = (area.width as f32 * 0.6).min(60.0) as u16;
    let height = (lines.len() as u16 + 4).min(area.height);
    let x = area.x + (area.width - width) / 2;
    let y = area.y + (area.height - height) / 2;
    let popup_area = Rect::new(x, y, width, height);

    // The Main Container
    // In ratatui 0.30, .title() takes a string. Styling is applied via .title_style()
    let block = Block::default()
        .title(format!(" ◈ {} ◈ ", title))
        .title_style(Style::default().fg(color_primary).add_modifier(Modifier::BOLD))
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .style(Style::default().fg(border_color));

    // The Content (with generous padding)
    let content = Paragraph::new(lines.join("\n"))
        .style(Style::default().fg(Color::Rgb(200, 230, 255)))
        .alignment(Alignment::Center);

    // The Footer Hint (dimmed)
    let footer_text = " ✠ Esc to close ";
    let footer_style = Style::default().fg(Color::Rgb(100, 140, 160));

    // Render the structure
    frame.render_widget(block, popup_area);
    
    // Inner area for content (padding of 1)
    let inner_area = Rect::new(
        popup_area.x + 1, 
        popup_area.y + 1, 
        popup_area.width.saturating_sub(2), 
        popup_area.height.saturating_sub(3)
    );
    frame.render_widget(content, inner_area);

    // Render footer at the bottom right of the block
    let footer_area = Rect::new(
        popup_area.x + popup_area.width.saturating_sub(footer_text.len() as u16 + 1),
        popup_area.y + popup_area.height - 1,
        footer_text.len() as u16,
        1
    );
    frame.render_widget(Paragraph::new(footer_text).style(footer_style), footer_area);
}
