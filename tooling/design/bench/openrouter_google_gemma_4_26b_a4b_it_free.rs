use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Wrap},
    Frame,
};

/// Renders a sacral, ultra-modern popup.
/// 
/// # Arguments
/// * `frame` - The current ratatui frame.
/// * `area` - The full screen area (the popup will center itself within this).
/// * `title` - The header text.
/// * `lines` - The body content.
/// * `tick` - A monotonically increasing counter used to drive the glow/fade animation.
pub fn render_popup(frame: &mut Frame, area: Rect, title: &str, lines: &[&str], tick: u64) {
    // 1. Calculate dimensions (Centered, generous padding)
    let popup_width = area.width.saturating_sub(20).max(40);
    let popup_height = area.height.saturating_sub(10).max(8);
    
    let x = area.x + (area.width - popup_width) / 2;
    let y = area.y + (area.height - popup_height) / 2;
    let popup_rect = Rect::new(x, y, popup_width, popup_height);

    // 2. Animation Logic: Subtle pulse/glow effect
    // Uses a sine wave based on tick to oscillate opacity/intensity
    let pulse = ((tick as f64 * 0.1).sin() + 1.0) / 2.0; // 0.0 to 1.0
    
    // Gradient interpolation: #00CED1 (Turquoise) to #2878FF (Blue)
    // We simulate this by blending the color intensity via the pulse
    let accent_color = Color::Rgb {
        r: (0 + (30.0 * pulse) as u8), // Slight shift in RGB to simulate glow
        g: (208 + (47.0 * pulse) as u8),
        b: (209 - (100.0 * pulse) as u8),
    };

    // 3. Construct the Block with "Rounded" feel (using Unicode characters)
    // Note: Ratatui's Rounded borders are standard, but we add a glyph accent.
    let border_style = Style::default()
        .fg(accent_color)
        .add_modifier(Modifier::BOLD);

    let block = Block::default()
        .borders(Borders::ROUNDED)
        .border_style(border_style)
        .title(Line::from(vec![
            Span::styled(" ◈ ", Style::default().fg(accent_color)),
            Span::styled(title, Style::default().add_modifier(Modifier::BOLD)),
            Span::styled(" ◈ ", Style::default().fg(accent_color)),
        ]))
        .title_alignment(Alignment::Center);

    // 4. Body Content
    let body_text = lines.join("\n");
    let body = Paragraph::new(body_text)
        .block(block)
        .wrap(Wrap { trim: true })
        .alignment(Alignment::Center)
        .style(Style::default().fg(Color::White));

    frame.render_widget(body, popup_rect);

    // 5. Footer Hint (Dimmed, positioned at bottom of popup)
    let footer_y = popup_rect.y + popup_rect.height - 1;
    let footer_text = Line::from(vec![
        Span::styled("Esc to close", Style::default().fg(Color::Indexed(244)).add_modifier(Modifier::ITALIC))
    ]);
    
    // Render footer inside the popup area
    let footer_area = Rect::new(popup_rect.x, footer_y, popup_rect.width, 1);
    frame.render_widget(Paragraph::new(footer_text).alignment(Alignment::Center), footer_area);
}
