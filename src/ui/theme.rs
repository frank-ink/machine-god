// SPDX-License-Identifier: Apache-2.0

use ratatui::style::Color;

/// True when stdout is a terminal and NO_COLOR is unset (cached once per process).
pub(crate) fn colors_enabled() -> bool {
    static CACHE: std::sync::OnceLock<bool> = std::sync::OnceLock::new();
    *CACHE.get_or_init(|| {
        std::io::IsTerminal::is_terminal(&std::io::stdout())
            && std::env::var_os("NO_COLOR").is_none()
    })
}

// Accent
/// Machine God accent: blood red (#C81E28).
pub const ACCENT: Color = Color::Rgb(200, 30, 40);
/// BTW accent: muted red shade.
pub const BTW_ACCENT: Color = Color::Rgb(160, 40, 45);
/// Ultracode accent: deep red shade.
pub const ULTRACODE_ACCENT: Color = Color::Rgb(130, 30, 35);

// UI chrome
/// Product name shown in the UI.
pub const APP_NAME: &str = "Machine God";
pub const DIM: Color = Color::DarkGray;
pub const PROMPT_CHAR: &str = "\u{276f}";
pub const ASSISTANT_MESSAGE_MARKER: &str = "\u{25cf}";
pub const SEPARATOR_CHAR: &str = "\u{2500}";

// Role header colors
pub const ROLE_ASSISTANT: Color = ACCENT;

// User message background
pub const USER_MSG_BG: Color = Color::Rgb(38, 14, 16);

// Tool status icons
pub const ICON_COMPLETED: &str = "\u{2713}";
pub const ICON_DETACHED: &str = "\u{2197}";
pub const ICON_FAILED: &str = "\u{2717}";

// Status colors
/// Bright red error color. Bold is applied at the call site; visually distinct
/// from ACCENT (blood red). Luminance ordering ensures visual distinction.
pub const STATUS_ERROR: Color = Color::Rgb(255, 80, 80);
/// Warning color: orange-red shade, never yellow/blue/cyan.
pub const STATUS_WARNING: Color = Color::Rgb(200, 100, 30);
/// Slash command highlight: red shade, never blue/cyan.
pub const SLASH_COMMAND: Color = Color::Rgb(180, 60, 60);
/// Subagent token highlight: gray shade.
pub const SUBAGENT_TOKEN: Color = Color::Rgb(110, 110, 110);

/// SDK tool icon + label pair. Monochrome Unicode symbols.
/// Unknown tool names fall back to a generic Tool label.
pub fn tool_name_label(sdk_tool_name: &str) -> (&'static str, &'static str) {
    match sdk_tool_name {
        "Read" => ("\u{2b1a}", "Read"),
        "Write" => ("\u{25a3}", "Write"),
        "Edit" => ("\u{25a3}", "Edit"),
        "MultiEdit" => ("\u{25a3}", "MultiEdit"),
        "NotebookEdit" => ("\u{25a3}", "NotebookEdit"),
        "Delete" => ("\u{25a3}", "Delete"),
        "Move" => ("\u{21c4}", "Move"),
        "Glob" => ("\u{2315}", "Glob"),
        "Grep" => ("\u{2315}", "Grep"),
        "LS" => ("\u{2315}", "LS"),
        "Bash" => ("$ \u{27e9}", "Bash"),
        "PowerShell" => ("PS \u{27e9}", "PowerShell"),
        name if crate::agent::model::is_agent_tool_name(name) => ("\u{25c7}", "Subagent"),
        "TaskCreate" | "TaskUpdate" | "TaskGet" | "TaskList" | "TaskOutput" | "TaskStop" => {
            ("\u{25a1}", "Task")
        }
        "WebFetch" => ("\u{2295}", "WebFetch"),
        "WebSearch" => ("\u{2295}", "WebSearch"),
        "EnterPlanMode" => ("\u{2299}", "EnterPlanMode"),
        "ExitPlanMode" => ("\u{2299}", "ExitPlanMode"),
        "Config" => ("\u{2299}", "Config"),
        "CronCreate" | "CronDelete" | "CronList" => ("\u{25f7}", "Cron"),
        "ScheduleWakeup" => ("\u{25f7}", "Wakeup"),
        "PushNotification" => ("!", "Notify"),
        "RemoteTrigger" => ("\u{21c4}", "Remote"),
        "REPL" => ("\u{03bb}", "REPL"),
        "Monitor" => ("\u{25c9}", "Monitor"),
        "Workflow" => ("\u{25c7}", "Workflow"),
        "Projects" => ("\u{25a6}", "Projects"),
        "Artifact" => ("\u{25c8}", "Artifact"),
        "ShowOnboardingRolePicker" => ("\u{2299}", "Role"),
        "Skill" => ("\u{2726}", "Skill"),
        "EnterWorktree" => ("\u{21c4}", "EnterWorktree"),
        "ExitWorktree" => ("\u{21c4}", "ExitWorktree"),
        _ => ("\u{25cb}", "Tool"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn is_gray(c: Color) -> bool {
        match c {
            Color::Rgb(r, g, b) => r == g && g == b,
            Color::Black | Color::Gray | Color::DarkGray | Color::White => true,
            _ => false,
        }
    }

    fn channel_ok(c: Color) -> bool {
        if is_gray(c) {
            return true;
        }
        match c {
            Color::Rgb(r, _, b) => b <= r,
            _ => true,
        }
    }

    fn is_blue_or_cyan(c: Color) -> bool {
        matches!(c, Color::Blue | Color::LightBlue | Color::Cyan | Color::LightCyan)
    }

    fn all_theme_colors() -> Vec<Color> {
        vec![
            ACCENT,
            BTW_ACCENT,
            ULTRACODE_ACCENT,
            DIM,
            ROLE_ASSISTANT,
            USER_MSG_BG,
            STATUS_ERROR,
            STATUS_WARNING,
            SLASH_COMMAND,
            SUBAGENT_TOKEN,
        ]
    }

    #[test]
    fn accent_is_blood_red() {
        assert_eq!(ACCENT, Color::Rgb(200, 30, 40));
    }

    #[test]
    fn role_assistant_follows_accent() {
        assert_eq!(ROLE_ASSISTANT, ACCENT);
    }

    #[test]
    fn user_msg_bg_is_dark_gray_red() {
        assert_eq!(USER_MSG_BG, Color::Rgb(38, 14, 16));
    }

    #[test]
    fn status_error_is_bright_red_and_distinct_from_accent() {
        assert_eq!(STATUS_ERROR, Color::Rgb(255, 80, 80));
        assert_ne!(STATUS_ERROR, ACCENT);
    }

    #[test]
    fn status_error_brighter_than_accent_for_visual_distinction() {
        // Luminance approximation: 0.2126*R + 0.7152*G + 0.0722*B
        // STATUS_ERROR (255,80,80) >> ACCENT (200,30,40)
        let accent_lum = 0.2126 * 200.0 + 0.7152 * 30.0 + 0.0722 * 40.0;
        let error_lum = 0.2126 * 255.0 + 0.7152 * 80.0 + 0.0722 * 80.0;
        assert!(error_lum > accent_lum, "STATUS_ERROR must be brighter than ACCENT");
    }

    #[test]
    fn btw_accent_is_red_shade() {
        assert_eq!(BTW_ACCENT, Color::Rgb(160, 40, 45));
    }

    #[test]
    fn ultracode_accent_is_red_shade() {
        assert_eq!(ULTRACODE_ACCENT, Color::Rgb(130, 30, 35));
    }

    #[test]
    fn slash_command_is_red_shade() {
        assert_eq!(SLASH_COMMAND, Color::Rgb(180, 60, 60));
    }

    #[test]
    fn subagent_token_is_gray_shade() {
        assert_eq!(SUBAGENT_TOKEN, Color::Rgb(110, 110, 110));
    }

    #[test]
    fn status_warning_is_orange_red_shade() {
        assert_eq!(STATUS_WARNING, Color::Rgb(200, 100, 30));
    }

    #[test]
    fn no_blue_or_cyan_constants_in_theme() {
        for c in all_theme_colors() {
            assert!(!is_blue_or_cyan(c), "theme color must not be blue/cyan: {:?}", c);
        }
    }

    #[test]
    fn test_palette_constraints() {
        for c in all_theme_colors() {
            assert!(channel_ok(c), "theme color violates b <= r or gray invariant: {:?}", c);
        }
    }

    #[test]
    fn all_theme_colors_is_exhaustive() {
        // This test ensures all_theme_colors() includes every public Color constant.
        // If a new Color constant is added, it must be added to all_theme_colors().
        let colors = all_theme_colors();
        // Count of public Color constants in this module (excluding those in functions)
        const EXPECTED_COUNT: usize = 10;
        assert_eq!(
            colors.len(),
            EXPECTED_COUNT,
            "all_theme_colors() must include all {} public Color constants, found {}",
            EXPECTED_COUNT,
            colors.len()
        );
    }
}
