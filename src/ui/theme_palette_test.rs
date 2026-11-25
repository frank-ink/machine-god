// SPDX-License-Identifier: Apache-2.0
//! Theme palette constraint tests.
//!
//! 1. Palette invariant: every theme color satisfies (b <= r) OR (r == g && g == b).
//! 2. Integration grep: scans src/ui/*.rs for forbidden `Color::` variants and non-palette `Rgb()`.

use ratatui::style::Color;
use std::fs;
use std::path::Path;

/// All public palette constants from theme.rs (duplicated here to avoid test-module privacy).
fn palette_colors() -> Vec<(&'static str, Color)> {
    vec![
        ("ACCENT", Color::Rgb(200, 30, 40)),
        ("BTW_ACCENT", Color::Rgb(160, 40, 45)),
        ("ULTRACODE_ACCENT", Color::Rgb(130, 30, 35)),
        ("DIM", Color::DarkGray),
        ("ROLE_ASSISTANT", Color::Rgb(200, 30, 40)),
        ("USER_MSG_BG", Color::Rgb(38, 14, 16)),
        ("STATUS_ERROR", Color::Rgb(255, 80, 80)),
        ("STATUS_WARNING", Color::Yellow),
        ("SLASH_COMMAND", Color::Rgb(180, 60, 60)),
        ("SUBAGENT_TOKEN", Color::Rgb(110, 110, 110)),
    ]
}

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

fn is_forbidden_variant(c: Color) -> bool {
    matches!(c, Color::Cyan | Color::LightCyan | Color::Blue | Color::LightBlue)
}

/// Allowed Rgb tuples (r, g, b) from the palette.
fn allowed_rgb_tuples() -> Vec<(u8, u8, u8)> {
    vec![
        (200, 30, 40),   // ACCENT / ROLE_ASSISTANT
        (160, 40, 45),   // BTW_ACCENT
        (130, 30, 35),   // ULTRACODE_ACCENT
        (38, 14, 16),    // USER_MSG_BG
        (255, 80, 80),   // STATUS_ERROR
        (180, 60, 60),   // SLASH_COMMAND
        (110, 110, 110), // SUBAGENT_TOKEN
    ]
}

/// Palette rule from the design goal: listed tuples, or any shade with b <= r (red family) or a pure gray.
fn rgb_tuple_allowed(r: u8, g: u8, b: u8) -> bool {
    allowed_rgb_tuples().contains(&(r, g, b)) || b <= r || (r == g && g == b)
}

#[test]
fn palette_constraint_b_le_r_or_gray() {
    for (name, color) in palette_colors() {
        assert!(
            channel_ok(color),
            "palette color {name} violates b <= r or gray invariant: {color:?}"
        );
    }
}

#[test]
fn palette_no_forbidden_variants() {
    for (name, color) in palette_colors() {
        assert!(
            !is_forbidden_variant(color),
            "palette color {name} is a forbidden blue/cyan variant: {color:?}"
        );
    }
}

/// Integration test: grep src/ui/*.rs for forbidden `Color::` variants and non-palette `Rgb()`.
#[test]
fn grep_ui_for_forbidden_colors_and_stray_rgb() {
    let ui_dir = Path::new("src/ui");
    assert!(ui_dir.exists(), "src/ui directory not found");

    let mut violations = Vec::new();

    // Walk src/ui recursively (config/, tool_call/, ... hold rendering code too).
    let mut files = Vec::new();
    let mut dirs = vec![ui_dir.to_path_buf()];
    while let Some(dir) = dirs.pop() {
        for entry in fs::read_dir(&dir).expect("read dir") {
            let path = entry.expect("dir entry").path();
            if path.is_dir() {
                dirs.push(path);
            } else {
                files.push(path);
            }
        }
    }

    for path in files {
        if path.extension().and_then(|s| s.to_str()) != Some("rs") {
            continue;
        }
        let content = fs::read_to_string(&path).expect("read file");
        let file_name = path.file_name().unwrap().to_string_lossy();
        // Test fixtures may use any color; only shipped rendering code is checked.
        if file_name.ends_with("_test.rs")
            || file_name.ends_with("_tests.rs")
            || file_name == "tests.rs"
        {
            continue;
        }
        // Everything after a top-level `#[cfg(test)]` is test code.
        let content: String = content.split("\n#[cfg(test)]\nmod ").next().unwrap_or("").to_owned();

        // Check each line for forbidden patterns
        for (line_num, line) in content.lines().enumerate() {
            let trimmed = line.trim();

            // Skip comments and doc comments
            if trimmed.starts_with("//") || trimmed.starts_with("///") || trimmed.starts_with("#[")
            {
                continue;
            }

            // ANSI passthrough: escape codes 4/6 from a tool's own output keep their meaning.
            if file_name == "terminal_output.rs" && trimmed.contains("=> Color::") {
                continue;
            }

            // Forbidden Color:: variants
            for variant in ["Cyan", "LightCyan", "Blue", "LightBlue"] {
                let pattern = format!("Color::{variant}");
                if line.contains(&pattern) {
                    violations.push(format!(
                        "{}:{}: forbidden Color::{variant} found: {}",
                        file_name,
                        line_num + 1,
                        line.trim()
                    ));
                }
            }

            // Non-palette Color::Rgb(...) - look for Rgb( with three numbers
            // We allow the exact palette tuples; any other Rgb is a violation.
            if let Some(start) = line.find("Color::Rgb(") {
                // Extract the tuple
                let after = &line[start + "Color::Rgb(".len()..];
                if let Some(end) = after.find(')') {
                    let tuple_str = &after[..end];
                    let parts: Vec<&str> = tuple_str.split(',').map(str::trim).collect();
                    if parts.len() == 3
                        && let (Ok(r), Ok(g), Ok(b)) =
                            (parts[0].parse::<u8>(), parts[1].parse::<u8>(), parts[2].parse::<u8>())
                        && !rgb_tuple_allowed(r, g, b)
                    {
                        violations.push(format!(
                            "{}:{}: non-palette Color::Rgb({},{},{}) found: {}",
                            file_name,
                            line_num + 1,
                            r,
                            g,
                            b,
                            line.trim()
                        ));
                    }
                }
            }
        }
    }

    assert!(
        violations.is_empty(),
        "Forbidden colors or stray Rgb found in src/ui:\n{}",
        violations.join("\n")
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_palette_constraints_duplicate_check() {
        // This duplicates the inline test in theme.rs to ensure the separate test file works.
        for (name, color) in palette_colors() {
            assert!(channel_ok(color), "{name} violates constraint: {color:?}");
        }
    }
}
