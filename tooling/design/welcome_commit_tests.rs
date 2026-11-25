// SPDX-License-Identifier: Apache-2.0

use crate::app::{App, AppStatus, ChatMessage, WelcomeBlock};
use crate::ui::machine_god_art::{LARGE_ART, SMALL_ART};
use crate::ui::welcome::{welcome_commit_ready, ferris_column_visible, ferris_column_width};
use std::time::{Duration, Instant};

fn make_test_app() -> App {
    let mut app = App::test_default();
    app.status = AppStatus::Connected;
    app.config.snapshot = Some(crate::app::ConfigSnapshot::default());
    app.show_session_overview = true;
    app.startup.mark_first_connected();
    app
}

fn make_welcome_block() -> WelcomeBlock {
    let msg = ChatMessage::welcome("1.0.0", "Enterprise", "/workspace/test", "session-abc123");
    crate::ui::welcome::welcome_block(&msg).expect("welcome block").clone()
}

#[test]
fn commit_ready_after_hello_window_closes() {
    let mut app = make_test_app();
    let welcome = make_welcome_block();
    let width = 200;
    let base_time = Instant::now();
    app.startup.first_connected_at = Some(base_time);
    
    // During hello window (1200ms), not ready
    for elapsed_ms in [0, 100, 500, 1000, 1199] {
        let now = base_time + Duration::from_millis(elapsed_ms);
        assert!(
            !welcome_commit_ready(&app, &welcome, width, now),
            "Should not be commit-ready at {}ms into hello window",
            elapsed_ms
        );
    }
    
    // After hello window closes, ready
    let now = base_time + Duration::from_millis(1200);
    assert!(
        welcome_commit_ready(&app, &welcome, width, now),
        "Should be commit-ready after hello window (1200ms)"
    );
    
    // Still ready later
    let now = base_time + Duration::from_millis(5000);
    assert!(
        welcome_commit_ready(&app, &welcome, width, now),
        "Should remain commit-ready after hello window"
    );
}

#[test]
fn commit_ready_immediately_when_motion_disabled() {
    let mut app = make_test_app();
    app.config.prefers_reduced_motion = true;
    let welcome = make_welcome_block();
    let width = 200;
    let base_time = Instant::now();
    app.startup.first_connected_at = Some(base_time);
    
    // Should be ready immediately, no hello window
    assert!(
        welcome_commit_ready(&app, &welcome, width, base_time),
        "Should be commit-ready immediately when motion disabled"
    );
}

#[test]
fn commit_ready_immediately_when_overview_hidden() {
    let mut app = make_test_app();
    app.show_session_overview = false;
    let welcome = make_welcome_block();
    let width = 200;
    let base_time = Instant::now();
    app.startup.first_connected_at = Some(base_time);
    
    assert!(
        welcome_commit_ready(&app, &welcome, width, base_time),
        "Should be commit-ready immediately when overview hidden"
    );
}

#[test]
fn commit_ready_immediately_when_shutdown() {
    let mut app = make_test_app();
    app.shutdown = true;
    let welcome = make_welcome_block();
    let width = 200;
    let base_time = Instant::now();
    app.startup.first_connected_at = Some(base_time);
    
    assert!(
        welcome_commit_ready(&app, &welcome, width, base_time),
        "Should be commit-ready immediately when shutdown"
    );
}

#[test]
fn commit_ready_when_values_not_loaded() {
    let mut app = make_test_app();
    let welcome = make_welcome_block();
    let width = 200;
    let base_time = Instant::now();
    app.startup.first_connected_at = Some(base_time);
    
    // Create welcome with missing values
    let msg = ChatMessage::welcome("1.0.0", "", "/workspace/test", "");
    let welcome_missing = crate::ui::welcome::welcome_block(&msg).expect("welcome block");
    
    // Not ready while values missing, even after hello window
    let now = base_time + Duration::from_millis(2000);
    assert!(
        !welcome_commit_ready(&app, welcome_missing, width, now),
        "Should not be commit-ready when values missing"
    );
}

#[test]
fn commit_ready_when_motif_not_visible_text_only() {
    let mut app = make_test_app();
    let welcome = make_welcome_block();
    // Width 40: motif column (42 for LARGE, 26 for SMALL) + gap (2) = 44/28 > 40
    // So motif not visible, text only
    let width = 40;
    let base_time = Instant::now();
    app.startup.first_connected_at = Some(base_time);
    
    // Should be ready immediately since motif not visible (no hello window)
    assert!(
        welcome_commit_ready(&app, &welcome, width, base_time),
        "Should be commit-ready immediately when motif not visible (text only)"
    );
}

#[test]
fn commit_ready_with_small_motif_at_width_80() {
    let mut app = make_test_app();
    let welcome = make_welcome_block();
    // Width 80: SMALL motif (24 + 2 padding = 26) + gap (2) = 28, overview needs ~30
    // So SMALL should be visible
    let width = 80;
    let base_time = Instant::now();
    app.startup.first_connected_at = Some(base_time);
    
    // During hello window, not ready
    assert!(!welcome_commit_ready(&app, &welcome, width, base_time + Duration::from_millis(500)));
    
    // After hello window, ready
    assert!(welcome_commit_ready(&app, &welcome, width, base_time + Duration::from_millis(1200)));
}

#[test]
fn commit_ready_with_large_motif_at_width_200() {
    let mut app = make_test_app();
    let welcome = make_welcome_block();
    // Width 200: LARGE motif (40 + 2 padding = 42) + gap (2) = 44, plenty of room
    let width = 200;
    let base_time = Instant::now();
    app.startup.first_connected_at = Some(base_time);
    
    // During hello window, not ready
    assert!(!welcome_commit_ready(&app, &welcome, width, base_time + Duration::from_millis(500)));
    
    // After hello window, ready
    assert!(welcome_commit_ready(&app, &welcome, width, base_time + Duration::from_millis(1200)));
}

#[test]
fn motif_dimensions_large_is_20_rows() {
    // LARGE_ART is 20 rows (vs old Ferris 4 rows)
    assert_eq!(LARGE_ART.len(), 20, "LARGE motif should be 20 rows");
}

#[test]
fn motif_dimensions_small_is_12_rows() {
    // SMALL_ART is 12 rows (vs old Ferris 4 rows)
    assert_eq!(SMALL_ART.len(), 12, "SMALL motif should be 12 rows");
}

#[test]
fn ferris_column_width_matches_large_motif() {
    // ferris_column_width should account for LARGE motif width (40) + padding
    let col_width = ferris_column_width();
    // FERRIS_LEFT_PADDING is "  " (2 chars) + max line width of motif
    // For LARGE: 2 + 40 = 42
    assert_eq!(col_width, 42, "Column width should be 42 for LARGE motif (2 padding + 40 art)");
}

#[test]
fn ferris_column_visible_at_width_200_for_large() {
    assert!(ferris_column_visible(200), "LARGE motif should be visible at width 200");
}

#[test]
fn ferris_column_visible_at_width_80_for_small() {
    assert!(ferris_column_visible(80), "SMALL motif should be visible at width 80");
}

#[test]
fn ferris_column_not_visible_at_width_40() {
    assert!(!ferris_column_visible(40), "No motif should be visible at width 40 (text only)");
}

#[test]
fn hello_window_only_when_motif_visible_and_whole_transcript() {
    let mut app = make_test_app();
    let welcome = make_welcome_block();
    let base_time = Instant::now();
    app.startup.first_connected_at = Some(base_time);
    
    // At width 200: motif visible, whole transcript (only welcome message)
    assert!(crate::ui::welcome::hello_window(&app, 200, base_time + Duration::from_millis(100)).is_some());
    
    // At width 40: motif NOT visible
    assert!(crate::ui::welcome::hello_window(&app, 40, base_time + Duration::from_millis(100)).is_none());
    
    // Add a second message: not whole transcript anymore
    app.transcript.messages.push(ChatMessage::user("hello"));
    assert!(crate::ui::welcome::hello_window(&app, 200, base_time + Duration::from_millis(100)).is_none());
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn hello_window_duration_is_1200ms() {
        // HELLO_WINDOW is 1200ms (private const, tested via behavior)
        let mut app = make_test_app();
        let welcome = make_welcome_block();
        let base_time = Instant::now();
        app.startup.first_connected_at = Some(base_time);
        
        // Just before 1200ms
        assert!(!welcome_commit_ready(&app, &welcome, 200, base_time + Duration::from_millis(1199)));
        // At 1200ms
        assert!(welcome_commit_ready(&app, &welcome, 200, base_time + Duration::from_millis(1200)));
    }
}
