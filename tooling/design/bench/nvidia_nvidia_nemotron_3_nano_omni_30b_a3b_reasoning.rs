use ratatui::{
    layout::{Alignment, Rect},
    style::{Color, Style, Modifier},
    frame::Frame,
    widget::Borders,
};

pub fn render_popup(
    frame: &mut Frame,
    area: Rect,
    title: &str,
    lines: &[&str],
    tick: u64,
) {
    // Fade‑in / glow intensity (0.0 – 1.0)
    let intensity = (tick % 120) as f32 / 120.0;

    // Border colour – turquoise → blue gradient
    let border_color = Color::new(
        0,
        (206.0 * intensity).min(255.0) as u8,
        (209.0 * intensity).min(255.0) as u8,
    );

    // Styles
    let title_style = Style::default()
        .fg(Color::WHITE)
        .add_modifier(Modifier::BOLD);
    let line_style = Style::default()
        .fg(Color::WHITE)
        .add_modifier(Modifier::DIM);
    let footer_style = Style::default()
        .fg(Color::WHITE)
        .add_modifier(Modifier::DIM);

    // Padding (generous)
    const PADDING: u16 = 2;

    // Content size calculation
    let title_len = title.len() as u16;
    let max_line_len = lines.iter().map(|l| l.len() as u16).max().unwrap_or(0);
    let content_width = title_len.max(max_line_len) + PADDING * 2;
    let content_height = 1 + lines.len() as u16; // title + lines
    let total_height = content_height + 1; // + footer

    // Center the popup inside the given area
    let inner = area.inner();
    let mut popup_rect = Rect {
        x: inner.x + (inner.width - content_width) / 2,
        y: inner.y + (inner.height - total_height) / 2,
        width: content_width,
        height: total_height,
    };

    // ---- Glow (a slightly larger rectangle) ----
    let glow_offset = 1;
    let glow_rect = Rect {
        x: popup_rect.x - glow_offset,
        y: popup_rect.y - glow_offset,
        width: popup_rect.width + glow_offset * 2,
        height: popup_rect.height + glow_offset * 2,
    };
    let glow_color = Color::new(
        0,
        (206.0 * intensity * 0.5).min(255.0) as u8,
        (209.0 * intensity * 0.5).min(255.0) as u8,
    );
    let glow_style = Style::default()
        .fg(glow_color)
        .add_modifier(Modifier::BOLD);
    frame.draw_rect(glow_rect, glow_style);

    // ---- Main rounded rectangle ----
    let border_style = Style::default()
        .fg(border_color)
        .add_modifier(Modifier::BOLD);
    frame.draw_bordered_rect(popup_rect, border_style, Borders::Rounded);

    // ---- Title ----
    let title_x = popup_rect.x + PADDING;
    let title_y = popup_rect.y + PADDING;
    frame.text(title_x, title_y, title, title_style);

    // ---- Lines ----
    let mut cur_y = title_y + 1; // skip title row
    for line in lines {
        let line_x = popup_rect.x + PADDING;
        frame.text(line_x, cur_y, *line, line_style);
        cur_y += 1;
    }

    // ---- Footer hint ----
    let footer_y = popup_rect.y + total_height - 1;
    frame.text(popup_rect.x + PADDING, footer_y, "Esc to close", footer_style);
}
