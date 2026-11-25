pub mod popup {
    use ratatui::prelude::*;
    use ratatui::widgets::{
        Block, Borders, BorderType, Padding, Paragraph, Layout, Direction, Constraint, Alignment,
        Style, Color, Modifier,
    };

    /// Render a centered, rounded‑border popup with a subtle fade‑in glow.
    ///
    /// * `frame` – the terminal frame to draw on
    /// * `area` – the outer area in which the popup should be centered
    /// * `title` – the popup title (thin glyphs are added automatically)
    /// * `lines` – the content lines to display
    /// * `tick` – a monotonically increasing counter used to drive the animation
    pub fn render_popup(
        frame: &mut Frame,
        area: Rect,
        title: &str,
        lines: &[&str],
        tick: u64,
    ) {
        // ------------------------------------------------------------------
        // 1️⃣  Compute a fade‑in factor (0.0 → 1.0) over the first 20 ticks.
        // ------------------------------------------------------------------
        let fade = if tick < 20 { tick as f64 / 20.0 } else { 1.0 };

        // ------------------------------------------------------------------
        // 2️⃣  Gradient from turquoise (#00CED1) to blue (#2878FF).
        // ------------------------------------------------------------------
        let start = (0u8, 206u8, 209u8); // #00CED1
        let end   = (40u8, 120u8, 255u8); // #2878FF
        let r = (start.0 as f64 + (end.0 as f64 - start.0 as f64) * fade) as u8;
        let g = (start.1 as f64 + (end.1 as f64 - start.1 as f64) * fade) as u8;
        let b = (start.2 as f64 + (end.2 as f64 - start.2 as f64) * fade) as u8;
        let bg_color = Color::Rgb(r, g, b);

        // ------------------------------------------------------------------
        // 3️⃣  Border style with a subtle glow (bold, same colour as background).
        // ------------------------------------------------------------------
        let border_style = Style::default()
            .fg(bg_color)
            .modifier(Modifier::BOLD);

        // ------------------------------------------------------------------
        // 4️⃣  Block with rounded borders and thin glyph accents.
        // ------------------------------------------------------------------
        let block = Block::default()
            .title(format!("◈ {} ◈", title))
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .border_style(border_style)
            .padding(Padding::new(1, 1, 1, 1));

        // ------------------------------------------------------------------
        // 5️⃣  Compute a centered popup area with generous padding.
        // ------------------------------------------------------------------
        let popup_area = Rect {
            x: area.x + area.width / 4,
            y: area.y + area.height / 4,
            width: area.width / 2,
            height: area.height / 2,
        };

        // ------------------------------------------------------------------
        // 6️⃣  Render the block (border + title).
        // ------------------------------------------------------------------
        frame.render_widget(block, popup_area);

        // ------------------------------------------------------------------
        // 7️⃣  Inner area inside the border and padding.
        // ------------------------------------------------------------------
        let inner_area = popup_area.shrink(2, 2);

        // ------------------------------------------------------------------
        // 8️⃣  Split the inner area into main content and a footer line.
        // ------------------------------------------------------------------
        let chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([Constraint::Min(1), Constraint::Length(1)])
            .split(inner_area);

        let main_area   = chunks[0];
        let footer_area = chunks[1];

        // ------------------------------------------------------------------
        // 9️⃣  Render the main content.
        // ------------------------------------------------------------------
        let main_paragraph = Paragraph::new(lines.join("\n"))
            .style(Style::default().fg(Color::White).bg(bg_color))
            .alignment(Alignment::Center);

        frame.render_widget(main_paragraph, main_area);

        // ------------------------------------------------------------------
        // 🔟 Render the footer hint.
        // ------------------------------------------------------------------
        let footer_paragraph = Paragraph::new("✠ Esc to close ✠")
            .style(Style::default().fg(Color::Gray).modifier(Modifier::DIM))
            .alignment(Alignment::Center);

        frame.render_widget(footer_paragraph, footer_area);
    }
}
