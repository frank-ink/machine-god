use ratatui::{
    layout::Rect,
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, Paragraph},
    Frame,
};

/// Renders a centered, animated popup dialog.
///
/// * `area`: The full screen area (used for centering).
/// * `title`: The header text.
/// * `lines`: The body content lines.
/// * `tick`: Animation frame counter (drives fade-in/glow).
pub fn render_popup(frame: &mut Frame, area: Rect, title: &str, lines: &[&str], tick: u64) {
    // 1. Calculate popup dimensions
    let content_width = lines.iter().map(|l| l.len()).max().unwrap_or(0);
    let title_width = title.len();
    let max_width = content_width.max(title_width).max(20); // Min width 20
    let width = (max_width as u16 + 6).min(area.width.saturating_sub(2)); // +4 padding + 2 border
    let height = (lines.len() as u16 + 4).min(area.height.saturating_sub(2)); // +2 title + 2 footer + 2 border

    // 2. Center the popup
    let x = area.x + (area.width.saturating_sub(width)) / 2;
    let y = area.y + (area.height.saturating_sub(height)) / 2;
    let popup_area = Rect::new(x, y, width, height);

    // 3. Animation Logic (Pure function of tick)
    // Fade-in: 0.0 to 1.0 over ~20 ticks
    let fade_progress = (tick as f32 / 20.0).min(1.0);
    let alpha = (fade_progress * 255.0) as u8;

    // Subtle Glow: Oscillates slightly after fade-in
    let glow_offset = if tick > 20 {
        // Gentle sine wave approximation for subtle breathing effect
        let t = (tick - 20) as f32;
        (t.sin() * 0.1 + 1.0) // 0.9 to 1.1
    } else {
        1.0
    };

    // 4. Color Palette (Turquoise to Blue)
    // Base: #00CED1 (Turquoise), Accent: #2878FF (Blue)
    let base_color = Color::Rgb(0x00, 0xCE, 0xD1);
    let accent_color = Color::Rgb(0x28, 0x78, 0xFF);
    
    // Dynamic border color: Interpolate between dim blue and bright turquoise based on glow
    let border_color = if glow_offset > 1.0 {
        accent_color
    } else {
        base_color
    };

    // 5. Build Widgets
    // Clear background behind popup to ensure clean overlay
    frame.render_widget(Clear, popup_area);

    // Border Style
    let border_style = Style::default()
        .fg(border_color)
        .add_modifier(Modifier::BOLD);

    // Title Style
    let title_style = Style::default()
        .fg(accent_color)
        .add_modifier(Modifier::BOLD);

    // Body Style
    let body_style = Style::default()
        .fg(Color::Rgb(0xE0, 0xF2, 0xF1)) // Very light turquoise/white for readability
        .add_modifier(Modifier::NONE);

    // Footer Style
    let footer_style = Style::default()
        .fg(Color::Rgb(0x70, 0x80, 0x90)) // Dim gray-blue
        .add_modifier(Modifier::DIM);

    // Construct the Block
    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(border_style)
        .border_type(ratatui::widgets::BorderType::Rounded)
        .title(
            Line::from(vec![
                Span::raw(" ◈ "),
                Span::styled(title.to_string(), title_style),
                Span::raw(" ✠ "),
            ])
            .alignment(ratatui::layout::Alignment::Center),
        )
        .padding(ratatui::widgets::Padding {
            top: 1,
            bottom: 1,
            left: 2,
            right: 2,
        });

    // Render Block
    frame.render_widget(block, popup_area);

    // Calculate inner area for content (accounting for borders and padding)
    let inner_area = popup_area
        .inner(ratatui::widgets::Margin {
            vertical: 1,
            horizontal: 1,
        })
        .inner(ratatui::widgets::Margin {
            vertical: 1, // Padding top
            horizontal: 2, // Padding left/right
        });

    // Build Body Paragraph
    let body_spans: Vec<Line> = lines
        .iter()
        .map(|l| Line::from(Span::styled(l.to_string(), body_style)))
        .collect();

    let body_paragraph = Paragraph::new(body_spans)
        .alignment(ratatui::layout::Alignment::Center)
        .wrap(ratatui::widgets::Wrap { trim: true });

    // Render Body
    frame.render_widget(body_paragraph, inner_area);

    // Build Footer
    let footer_line = Line::from(vec![
        Span::styled("Esc to close", footer_style),
    ])
    .alignment(ratatui::layout::Alignment::Center);

    let footer_paragraph = Paragraph::new(footer_line);

    // Render Footer (positioned at the bottom of the inner area)
    if inner_area.height > 0 {
        let footer_area = Rect::new(
            inner_area.x,
            inner_area.y + inner_area.height - 1,
            inner_area.width,
            1,
        );
        frame.render_widget(footer_paragraph, footer_area);
    }
}
