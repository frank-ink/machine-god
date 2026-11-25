use ratatui::{
    buffer::Buffer,
    layout::{Alignment, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, BorderType, Paragraph, Widget},
    Frame,
};

/// Renders a centered, rounded popup with a subtle fade-in/glow animation.
/// `tick` drives the animation (e.g. frame count). Pure function, no side effects.
pub fn render_popup(frame: &mut Frame, area: Rect, title: &str, lines: &[&str], tick: u64) {
    // --- Color constants ---
    const TURQUOISE: Color = Color::Rgb(0x00, 0xCE, 0xD1);
    const BLUE: Color = Color::Rgb(0x28, 0x78, 0xFF);
    const DARK_BASE: Color = Color::Rgb(0x00, 0x1A, 0x1C);
    const DIM_TEXT: Color = Color::Rgb(0x44, 0x44, 0x44);
    const BRIGHT_TEXT: Color = Color::Rgb(0xCC, 0xCC, 0xCC);

    // --- Helpers ---
    fn rgb(c: Color) -> (u8, u8, u8) {
        match c {
            Color::Rgb(r, g, b) => (r, g, b),
            _ => (0, 0, 0),
        }
    }
    fn lerp_color(a: Color, b: Color, t: f32) -> Color {
        let (r1, g1, b1) = rgb(a);
        let (r2, g2, b2) = rgb(b);
        let r = (r1 as f32 + (r2 as f32 - r1 as f32) * t) as u8;
        let g = (g1 as f32 + (g2 as f32 - g1 as f32) * t) as u8;
        let b = (b1 as f32 + (b2 as f32 - b1 as f32) * t) as u8;
        Color::Rgb(r, g, b)
    }

    // --- Animation state derived purely from tick ---
    let progress = (tick as f32 * 0.08).sin() * 0.5 + 0.5; // 0.0..1.0 smooth pulse
    let fade_in = ((tick as f32) / 20.0).min(1.0);          // fade in over ~20 frames

    // Animated colors
    let pulse_color = lerp_color(TURQUOISE, BLUE, progress);
    let border_color = lerp_color(DARK_BASE, pulse_color, fade_in);
    let text_color = lerp_color(DIM_TEXT, BRIGHT_TEXT, fade_in);

    // --- Popup geometry (generous padding, centered) ---
    const HPAD: usize = 4;
    const VPAD: usize = 2;
    let title_line = format!(" ◈ {} ✠ ", title);
    let footer_line = " Esc to close ";
    let max_content_width = lines
        .iter()
        .map(|l| l.chars().count())
        .max()
        .unwrap_or(0)
        .max(title_line.chars().count())
        .max(footer_line.chars().count());

    let popup_width = (max_content_width + HPAD * 2).min(area.width.saturating_sub(4) as usize) as u16;
    let popup_height = (lines.len() + VPAD * 2 + 2).min(area.height.saturating_sub(4) as usize) as u16; // +2 title/footer

    let x = area.x + (area.width.saturating_sub(popup_width)) / 2;
    let y = area.y + (area.height.saturating_sub(popup_height)) / 2;
    let popup_rect = Rect::new(x, y, popup_width, popup_height);

    // --- Build text content ---
    let mut text_lines = Vec::with_capacity(lines.len() + 4);
    // Title
    text_lines.push(Line::from(Span::styled(
        title_line,
        Style::default().fg(text_color).add_modifier(Modifier::BOLD),
    )));
    // Top padding
    text_lines.push(Line::from(""));
    // Body lines
    for line in lines {
        text_lines.push(Line::from(Span::styled(
            format!("  {}  ", line),
            Style::default().fg(text_color),
        )));
    }
    // Bottom padding
    text_lines.push(Line::from(""));
    // Footer hint (dim via color, no Modifier::DIM for compat)
    text_lines.push(Line::from(Span::styled(
        footer_line,
        Style::default().fg(DIM_TEXT),
    )));

    // --- Paragraph with rounded border ---
    let paragraph = Paragraph::new(Text::from(text_lines))
        .alignment(Alignment::Center)
        .block(
            Block::default()
                .border_type(BorderType::Rounded)
                .border_style(Style::default().fg(border_color))
                .style(Style::default().bg(Color::Reset)),
        );

    frame.render_widget(paragraph, popup_rect);
}
