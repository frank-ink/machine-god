use ratatui::style::{BorderType, Borders, Color, Modifier, Padding, Style, Title};
use ratatui::text::{Line, Text};
use ratatui::widgets::{Block, Paragraph};

pub fn render_popup(
    frame: &mut ratatui::Frame,
    area: ratatui::layout::Rect,
    title: &str,
    lines: &[&str],
    tick: u64,
) {
    let max_line_width = lines
        .iter()
        .map(|l| l.chars().count())
        .max()
        .unwrap_or(0)
        .max(title.chars().count());

    let popup_width = max_line_width + 6;
    let popup_height = lines.len().max(1) as u16 + 6;

    let popup_x = area.x + area.width.saturating_sub(popup_width) / 2;
    let popup_y = area.y + area.height.saturating_sub(popup_height) / 2;
    let popup_area = ratatui::layout::Rect {
        x: popup_x,
        y: popup_y,
        width: popup_width,
        height: popup_height,
    };

    let progress = (tick as f64 / 18.0).min(1.0);
    let opacity = 1.0 - (1.0 - progress).powi(2);
    let glow = (tick as f64 / 10.0).min(1.0);

    let fg = Color::Rgb(
        (0.0 + 32.0 * opacity) as u8,
        (0.85 + 0.15 * opacity) as u8,
        (0.87 + 0.13 * opacity) as u8,
    );
    let content_style = Style::default().fg(fg).add_modifier(if opacity > 0.75 {
        Modifier::BOLD
    } else {
        Modifier::NORMAL
    });

    let border_color = if glow > 0.5 { Color::Cyan } else { Color::Blue };
    let border_style = Style::default().fg(border_color).add_modifier(if glow > 0.8 {
        Modifier::BOLD
    } else {
        Modifier::NORMAL
    });

    let title_style = Style::default().fg(if glow > 0.6 { Color::Cyan } else { Color::Blue }).add_modifier(Modifier::BOLD);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(border_style)
        .title(Title::from(title.to_string()))
        .padding(Padding::new(2, 2, 2, 2));

    let mut text_lines: Vec<Line> = lines.iter().map(|l| Line::raw(*l)).collect();
    let mut footer = Line::raw("Esc to close");
    footer.style = Some(
        Style::default()
            .fg(Color::DarkGray)
            .add_modifier(Modifier::DIM),
    );
    text_lines.push(footer);

    let paragraph = Paragraph::new(Text::from(text_lines))
        .block(block)
        .style(content_style);

    frame.render_widget(paragraph, popup_area);
}
