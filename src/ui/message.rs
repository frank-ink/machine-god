// SPDX-License-Identifier: Apache-2.0

// Message role and background colors
pub const USER_MSG_BG: Color = Color::Rgb(58, 24, 26);
pub const USER_MSG_FG: Color = Color::Rgb(255, 255, 255);
pub const ACCENT: Color = Color::Rgb(200, 30, 40);
pub const ROLE_ASSISTANT: Color = ACCENT;
pub const STATUS_ERROR: Color = Color::Rgb(255, 80, 80);

#[cfg(test)]
use crate::app::ChatMessage;
use crate::app::{BlockCache, TextBlock};
use crate::ui::tool_call;
use ratatui::style::Color;
use ratatui::text::Line;

#[cfg(test)]
use super::message_rows::build_user_system_message_rows;

/// Presentation of active status and tool indicators, derived from saved preferences.
#[derive(Clone, Copy)]
pub enum SpinnerState {
    Animated(usize),
    Static,
}

impl SpinnerState {
    pub(crate) const FRAMES: &[&str] = &[
        "\u{280B}", "\u{2819}", "\u{2839}", "\u{2838}", "\u{283C}", "\u{2834}", "\u{2826}",
        "\u{2827}", "\u{2807}", "\u{280F}",
    ];

    pub(crate) fn for_app(app: &crate::app::App) -> Self {
        if app.config.prefers_reduced_motion_effective() {
            Self::Static
        } else {
            Self::Animated(app.spinner_frame)
        }
    }

    pub(crate) fn icon(self) -> &'static str {
        match self {
            Self::Animated(frame) => Self::FRAMES[frame % Self::FRAMES.len()],
            Self::Static => "\u{25C6}",
        }
    }
}

#[derive(Clone, Copy)]
pub(crate) struct MessageRenderContext<'a> {
    pub(crate) tool_render_context: tool_call::ToolCallRenderContext<'a>,
    pub(crate) width: u16,
}

impl<'a> MessageRenderContext<'a> {
    pub(crate) fn new(current_mode_id: Option<&'a str>, width: u16) -> Self {
        Self {
            tool_render_context: tool_call::ToolCallRenderContext {
                current_mode_id,
                clock: crate::app::presentation::ClockFormat::default(),
                control: None,
            },
            width,
        }
    }

    pub(crate) fn with_control(
        current_mode_id: Option<&'a str>,
        width: u16,
        control: &'a super::layout_control::LayoutControl<'a>,
    ) -> Self {
        Self {
            tool_render_context: tool_call::ToolCallRenderContext {
                current_mode_id,
                clock: crate::app::presentation::ClockFormat::default(),
                control: Some(control),
            },
            width,
        }
    }
}

#[cfg(test)]
pub(crate) fn render_message(msg: &mut ChatMessage, width: u16, out: &mut Vec<Line<'static>>) {
    let render_context = MessageRenderContext::new(None, width);
    render_message_rows(msg, render_context, out);
}

#[cfg(test)]
fn render_message_rows(
    msg: &mut ChatMessage,
    render_context: MessageRenderContext<'_>,
    out: &mut Vec<Line<'static>>,
) {
    let rows = build_user_system_message_rows(msg, render_context);
    for segment in rows.segments {
        match segment {
            super::message_rows::MessageRowSegment::Blank => out.push(Line::default()),
            super::message_rows::MessageRowSegment::Lines { lines } => out.extend(lines),
        }
    }
}

/// Render the complete canonical source so paragraph separators and Markdown
/// context survive caching. Streaming splits stable prefixes into text blocks
/// at message construction time; each block retains its own render cache.
pub(super) fn render_text_cached(
    text: &str,
    cache: &mut BlockCache,
    width: u16,
    bg: Option<Color>,
    preserve_newlines: bool,
    out: &mut Vec<Line<'static>>,
    control: &super::layout_control::LayoutControl<'_>,
) {
    // Reuse only lines laid out at this width.
    // Tables and code resolve width-dependent geometry before final row wrapping,
    // so a fresh cache from another width is not safe to reuse.
    if let Some(cached_lines) = cache.get_for_width(width) {
        out.extend_from_slice(cached_lines);
        return;
    }

    let fresh =
        super::markdown::render_markdown_with_control(text, width, bg, preserve_newlines, control);
    if control.cancelled() {
        return;
    }

    // Physical rows, and therefore their height, belong to the final layout pass.
    cache.store_for_width(fresh, width);
    if let Some(stored) = cache.get_for_width(width) {
        out.extend_from_slice(stored);
    }
}

pub(super) fn render_text_block_cached(
    block: &mut TextBlock,
    width: u16,
    bg: Option<Color>,
    preserve_newlines: bool,
    out: &mut Vec<Line<'static>>,
    control: &super::layout_control::LayoutControl<'_>,
) {
    render_text_cached(&block.text, &mut block.cache, width, bg, preserve_newlines, out, control);
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::app::{ChatMessage, MessageBlock, MessageRole, TextBlock};
    use pretty_assertions::assert_eq;

    fn make_text_message(role: MessageRole, text: &str) -> ChatMessage {
        ChatMessage::new(role, vec![MessageBlock::Text(TextBlock::from_complete(text))], None)
    }

    fn render_lines_to_strings(lines: &[Line<'static>]) -> Vec<String> {
        lines.iter().map(|line| line.to_string().trim_end().to_owned()).collect()
    }

    #[test]
    fn user_message_preserves_source_structure_through_cached_resizes() {
        let source = "first line\nsecond line\n\n```text\n  indented\nplain\n```\n\nfinal";
        let mut msg = make_text_message(MessageRole::User, source);
        for width in [80, 80, 28, 80] {
            let mut lines = Vec::new();
            render_message(&mut msg, width, &mut lines);
            let rows = lines.iter().map(ToString::to_string).collect::<Vec<_>>();
            let text = rows.join("\n");
            for expected in ["first line", "second line", "  indented", "plain", "final"] {
                assert!(text.contains(expected), "missing {expected:?} at width {width}: {text}");
            }
            let row_of = |needle: &str| {
                rows.iter()
                    .position(|row| row.contains(needle))
                    .unwrap_or_else(|| panic!("missing row {needle:?} at width {width}: {text}"))
            };
            let first = row_of("first line");
            let second = row_of("second line");
            let code = row_of("indented");
            let plain = row_of("plain");
            let final_row = row_of("final");
            assert!(first < second, "explicit source line break was lost: {rows:?}");
            assert!(second + 1 < code, "paragraph boundary before code was lost: {rows:?}");
            assert!(code < plain && plain < final_row, "source order changed: {rows:?}");
            assert!(text.contains("  indented"), "code indentation must survive");
            let MessageBlock::Text(block) = &msg.blocks[0] else {
                panic!("expected user text");
            };
            assert_eq!(block.text, source);
        }
    }

    #[test]
    fn markdown_table_rerenders_when_width_changes_in_both_directions() {
        let table = "| Key | Val |\n| --- | --- |\n| A | amberpinewood |\n| B | cobaltstream |\n";
        let mut msg = make_text_message(MessageRole::User, table);
        let mut wide_lines = Vec::new();
        render_message(&mut msg, 40, &mut wide_lines);
        let wide = render_lines_to_strings(&wide_lines);
        let mut narrow_lines = Vec::new();
        render_message(&mut msg, 20, &mut narrow_lines);
        let narrow = render_lines_to_strings(&narrow_lines);
        assert_ne!(narrow, wide, "resize must reflow the table");
        for (rows, width) in [(&wide, 40_u16), (&narrow, 20_u16)] {
            let joined = rows.join("\n");
            let compact = joined.chars().filter(|ch| ch.is_alphanumeric()).collect::<String>();
            assert!(
                compact.contains("KeyValAamberpinewoodBcobaltstream"),
                "table lost or reordered a header, row key, or value at width {width}: {joined}"
            );
            assert!(
                rows.iter().all(|row| {
                    unicode_width::UnicodeWidthStr::width(row.as_str()) <= usize::from(width)
                }),
                "a rendered row exceeded terminal width {width}: {rows:?}"
            );
        }
        let mut wide_again_lines = Vec::new();
        render_message(&mut msg, 40, &mut wide_again_lines);
        assert_eq!(
            render_lines_to_strings(&wide_again_lines),
            wide,
            "growing must restore wide layout"
        );
    }

    #[test]
    fn theme_colors_have_no_blue_cyan_leftover() {
        // Assert every theme color has b <= r or is a gray (|r-g|<=8 && |g-b|<=8 && |b-r|<=8)
        fn is_gray(c: Color) -> bool {
            if let Color::Rgb(r, g, b) = c {
                (r.abs_diff(g) <= 8) && (g.abs_diff(b) <= 8) && (b.abs_diff(r) <= 8)
            } else {
                false
            }
        }
        fn no_blue_cyan(c: Color) -> bool {
            if let Color::Rgb(r, _g, b) = c {
                b <= r || is_gray(c)
            } else {
                true // non-Rgb colors (Indexed, Reset) are acceptable
            }
        }
        assert!(no_blue_cyan(USER_MSG_BG), "USER_MSG_BG has blue/cyan cast");
        assert!(no_blue_cyan(USER_MSG_FG), "USER_MSG_FG has blue/cyan cast");
        assert!(no_blue_cyan(ACCENT), "ACCENT has blue/cyan cast");
        assert!(no_blue_cyan(ROLE_ASSISTANT), "ROLE_ASSISTANT has blue/cyan cast");
        assert!(no_blue_cyan(STATUS_ERROR), "STATUS_ERROR has blue/cyan cast");
    }

    #[test]
    fn user_msg_bg_contrast_meets_wcag_aa() {
        // WCAG AA normal text: ≥4.5:1
        // USER_MSG_BG = Rgb(58,24,26), USER_MSG_FG = Rgb(255,255,255)
        // Luminance calculation (sRGB -> linear -> Y)
        fn luminance(r: u8, g: u8, b: u8) -> f32 {
            let to_linear = |c: u8| {
                let c = c as f32 / 255.0;
                if c <= 0.03928 { c / 12.92 } else { ((c + 0.055) / 1.055).powf(2.4) }
            };
            0.2126 * to_linear(r) + 0.7152 * to_linear(g) + 0.0722 * to_linear(b)
        }
        fn contrast_ratio(l1: f32, l2: f32) -> f32 {
            let (lighter, darker) = if l1 > l2 { (l1, l2) } else { (l2, l1) };
            (lighter + 0.05) / (darker + 0.05)
        }
        let bg_l = luminance(58, 24, 26);
        let fg_l = luminance(255, 255, 255);
        let ratio = contrast_ratio(fg_l, bg_l);
        assert!(ratio >= 4.5, "USER_MSG_FG on USER_MSG_BG contrast {ratio:.2}:1 < 4.5:1");
    }

    #[test]
    fn assistant_role_follows_accent() {
        assert_eq!(ROLE_ASSISTANT, ACCENT, "ROLE_ASSISTANT must equal ACCENT (blood red)");
    }

    #[test]
    fn status_error_distinct_from_accent() {
        // STATUS_ERROR = bright red (255,80,80) vs ACCENT = blood red (200,30,40)
        // They must be visually distinct; at minimum different RGB values
        assert_ne!(STATUS_ERROR, ACCENT, "STATUS_ERROR must differ from ACCENT");
        if let (Color::Rgb(r1, g1, b1), Color::Rgb(r2, g2, b2)) = (STATUS_ERROR, ACCENT) {
            // STATUS_ERROR should be brighter (higher luminance)
            fn lum(r: u8, g: u8, b: u8) -> f32 {
                let to_lin = |c: u8| {
                    let c = c as f32 / 255.0;
                    if c <= 0.03928 { c / 12.92 } else { ((c + 0.055) / 1.055).powf(2.4) }
                };
                0.2126 * to_lin(r) + 0.7152 * to_lin(g) + 0.0722 * to_lin(b)
            }
            assert!(lum(r1, g1, b1) > lum(r2, g2, b2), "STATUS_ERROR must be brighter than ACCENT");
        }
    }
}
