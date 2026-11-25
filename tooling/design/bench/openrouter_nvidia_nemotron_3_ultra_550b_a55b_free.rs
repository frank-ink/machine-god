use ratatui::{
    buffer::Buffer,
    layout::{Alignment, Constraint, Layout, Rect},
    prelude::{Color, Line, Style, Stylize, Text, Widget},
    widgets::{Block, BorderType, Borders, Clear, Paragraph, Wrap},
};

pub fn render_popup(frame: &mut ratatui::Frame, area: Rect, title: &str, lines: &[&str], tick: u64) {
    let padding_h = 4;
    let padding_v = 2;
    let footer_h = 1;

    let content_w = lines.iter().map(|l| l.len()).max().unwrap_or(0) as u16 + padding_h * 2;
    let content_h = lines.len() as u16 + padding_v * 2 + footer_h;

    let popup_w = content_w.min(area.width.saturating_sub(4));
    let popup_h = content_h.min(area.height.saturating_sub(4));

    let x = area.x + (area.width.saturating_sub(popup_w)) / 2;
    let y = area.y + (area.height.saturating_sub(popup_h)) / 2;
    let popup_area = Rect { x, y, width: popup_w, height: popup_h };

    let phase = (tick as f32 * 0.08).sin() * 0.5 + 0.5;
    let r = (0x00_f32 + (0x28 - 0x00) as f32 * phase) as u8;
    let g = (0xCE_f32 + (0x78 - 0xCE) as f32 * phase) as u8;
    let b = (0xD1_f32 + (0xFF - 0xD1) as f32 * phase) as u8;
    let glow = Color::Rgb(r, g, b);
    let dim_glow = Color::Rgb((r as f32 * 0.35) as u8, (g as f32 * 0.35) as u8, (b as f32 * 0.35) as u8);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(glow))
        .title(
            Line::from(vec![" ◈ ".fg(glow), title.fg(Color::White).bold(), " ◈ ".fg(glow)])
                .alignment(Alignment::Center),
        )
        .title_alignment(Alignment::Center)
        .style(Style::default().bg(Color::Rgb(0x0A, 0x0F, 0x1A)));

    let inner = block.inner(popup_area);

    let text: Text = lines
        .iter()
        .map(|l| Line::from(l.to_string()).fg(Color::Rgb(0xC8, 0xD8, 0xE8)))
        .collect();

    let paragraph = Paragraph::new(text)
        .wrap(Wrap { trim: false })
        .alignment(Alignment::Left)
        .style(Style::default().bg(Color::Rgb(0x0A, 0x0F, 0x1A)));

    let footer = Paragraph::new(Line::from(" ✠ Esc to close ✠ ").fg(dim_glow))
        .alignment(Alignment::Center)
        .style(Style::default().bg(Color::Rgb(0x0A, 0x0F, 0x1A)));

    let chunks = Layout::vertical([Constraint::Min(0), Constraint::Length(1)]).split(inner);
    let content_area = chunks[0];
    let footer_area = chunks[1];

    frame.render_widget(Clear, popup_area);
    frame.render_widget(block, popup_area);
    frame.render_widget(paragraph, content_area);
    frame.render_widget(footer, footer_area);
}
