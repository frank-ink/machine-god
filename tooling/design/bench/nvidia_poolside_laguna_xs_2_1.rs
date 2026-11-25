use ratatui::{
    buffer::Buffer,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span, Spans},
    widgets::{Block, Borders, Paragraph, Wrap},
    Frame,
};

pub fn render_popup(
    frame: &mut Frame,
    area: Rect,
    title: &str,
    lines: &[&str],
    tick: u64,
) {
    let (content_area, footer_area) = layout_popup(area);

    let glow_alpha = ((tick % 20) as f32 / 20.0).sin().abs() * 0.3 + 0.7;
    let border_color = Color::Rgb {
        r: (0x00 * glow_alpha as u8),
        g: (0xCE * glow_alpha as u8),
        b: (0xD1 * glow_alpha as u8),
    };

    let block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(border_color).add_modifier(Modifier::BOLD))
        .border_type(ratatui::widgets::BorderType::Rounded)
        .title(
            Line::from(vec![
                Span::styled(
                    format!(" ◈ {} ", title),
                    Style::default()
                        .fg(Color::Blue)
                        .bg(Color::Rgb {
                            r: (0x28 * glow_alpha as u8),
                            g: (0x78 * glow_alpha as u8),
                            b: (0xFF * glow_alpha as u8),
                        })
                        .add_modifier(Modifier::BOLD),
                ),
            ])
            .centered(),
        )
        .style(Style::default().fg(Color::Reset));

    let padded_area = Rect {
        x: content_area.x + 1,
        y: content_area.y + 1,
        width: content_area.width.saturating_sub(2),
        height: content_area.height.saturating_sub(2),
    };

    let content_lines: Vec<Spans> = lines
        .iter()
        .map(|line| {
            Spans::from(Span::styled(
                *line,
                Style::default()
                    .fg(Color::White)
                    .bg(Color::Rgb {
                        r: (0x28 * glow_alpha as u8),
                        g: (0x78 * glow_alpha as u8),
                        b: (0xFF * glow_alpha as u8),
                    })
                    .add_modifier(Modifier::RESET),
            ))
        })
        .collect();

    let paragraph = Paragraph::new(content_lines)
        .block(block)
        .style(Style::default().fg(Color::Reset))
        .wrap(Wrap { trim: true });

    frame.render_widget(paragraph, padded_area);

    let footer_style = Style::default()
        .fg(Color::Gray)
        .bg(Color::Rgb {
            r: (0x28 * glow_alpha as u8),
            g: (0x78 * glow_alpha as u8),
            b: (0xFF * glow_alpha as u8),
        })
        .add_modifier(Modifier::DIM);

    let footer = Line::from(vec![
        Span::styled("✠ ", footer_style),
        Span::styled("Esc to close", footer_style),
    ])
    .centered();

    frame.render_widget(footer, footer_area);
}

fn layout_popup(area: Rect) -> (Rect, Rect) {
    let vertical_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(0), Constraint::Length(1)].as_ref())
        .split(area);

    let content_area = vertical_chunks[0];
    let footer_area = vertical_chunks[1];

    (content_area, footer_area)
}
