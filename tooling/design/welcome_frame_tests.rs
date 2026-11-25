// SPDX-License-Identifier: Apache-2.0

use crate::app::{App, AppStatus, ChatMessage, WelcomeBlock};
use crate::ui::machine_god_art::{FRAME_COUNT, FRAME_MS, LARGE_ART, LARGE_MASK, SMALL_ART, SMALL_MASK};
use crate::ui::welcome::{ferris_frame, ferris_phase, FerrisPhase, welcome_commit_ready};
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
fn frame_index_formula_elapsed_div_frame_ms_mod_frame_count() {
    // Frame index = elapsed / FRAME_MS % FRAME_COUNT
    let test_cases = [
        (Duration::from_millis(0), 0),
        (Duration::from_millis(FRAME_MS - 1), 0),
        (Duration::from_millis(FRAME_MS), 1),
        (Duration::from_millis(2 * FRAME_MS), 2),
        (Duration::from_millis(3 * FRAME_MS), 0), // wraps around
        (Duration::from_millis(4 * FRAME_MS), 1),
        (Duration::from_millis(5 * FRAME_MS), 2),
        (Duration::from_millis(6 * FRAME_MS), 0),
    ];
    
    for (elapsed, expected_frame) in test_cases {
        let frame_index = (elapsed.as_millis() / FRAME_MS as u128) % FRAME_COUNT as u128;
        assert_eq!(
            frame_index as usize, expected_frame,
            "elapsed={:?}, expected frame={}, got={}",
            elapsed, expected_frame, frame_index
        );
    }
}

#[test]
fn three_distinct_frames_over_three_frame_ms() {
    let app = make_test_app();
    let welcome = make_welcome_block();
    let width = 200; // Wide enough for LARGE
    
    let base_time = Instant::now();
    
    // Get frames at t, t+FRAME_MS, t+2*FRAME_MS
    let phase0 = ferris_phase(&app, &welcome, width, base_time);
    let frame0 = ferris_frame(phase0);
    
    let phase1 = ferris_phase(&app, &welcome, width, base_time + Duration::from_millis(FRAME_MS));
    let frame1 = ferris_frame(phase1);
    
    let phase2 = ferris_phase(&app, &welcome, width, base_time + Duration::from_millis(2 * FRAME_MS));
    let frame2 = ferris_frame(phase2);
    
    // All three frames should be distinct
    assert_ne!(frame0, frame1, "Frame 0 and 1 should differ");
    assert_ne!(frame1, frame2, "Frame 1 and 2 should differ");
    assert_ne!(frame0, frame2, "Frame 0 and 2 should differ");
    
    // Each frame should be one of the FRAME_COUNT frames
    // Since FRAME_COUNT=3, we should see all 3 frames
    let frames = [frame0, frame1, frame2];
    let unique_frames: std::collections::HashSet<_> = frames.iter().collect();
    assert_eq!(unique_frames.len(), 3, "Should have 3 distinct frames over 3*FRAME_MS");
}

#[test]
fn frame_deterministic_for_fixed_instant() {
    let app = make_test_app();
    let welcome = make_welcome_block();
    let width = 200;
    let fixed_time = Instant::now();
    
    // Same instant should always produce same frame
    for _ in 0..10 {
        let phase = ferris_phase(&app, &welcome, width, fixed_time);
        let frame = ferris_frame(phase);
        let phase2 = ferris_phase(&app, &welcome, width, fixed_time);
        let frame2 = ferris_frame(phase2);
        assert_eq!(frame, frame2, "Frame must be deterministic for fixed instant");
    }
}

#[test]
fn frame_advances_every_frame_ms() {
    let app = make_test_app();
    let welcome = make_welcome_block();
    let width = 200;
    let base_time = Instant::now();
    
    let mut prev_frame = ferris_frame(ferris_phase(&app, &welcome, width, base_time));
    
    for i in 1..=FRAME_COUNT * 2 {
        let elapsed = Duration::from_millis(i as u64 * FRAME_MS);
        let frame = ferris_frame(ferris_phase(&app, &welcome, width, base_time + elapsed));
        
        if i % FRAME_COUNT == 0 {
            // After FRAME_COUNT steps, should wrap to first frame
            assert_eq!(frame, prev_frame, "Frame should wrap after FRAME_COUNT steps");
        } else {
            // Should be different from previous
            assert_ne!(frame, prev_frame, "Frame should advance at step {}", i);
        }
        prev_frame = frame;
    }
}

#[test]
fn connecting_phase_uses_spinner_frame() {
    let mut app = App::test_default();
    app.status = AppStatus::Connecting;
    app.spinner_frame = 0;
    let welcome = make_welcome_block();
    let width = 200;
    let now = Instant::now();
    
    let phase = ferris_phase(&app, &welcome, width, now);
    match phase {
        FerrisPhase::Connecting { spinner_frame } => {
            assert_eq!(spinner_frame, 0);
        }
        _ => panic!("Expected Connecting phase"),
    }
    
    // Advance spinner
    app.spinner_frame = 12; // 2 * CONNECTING_FRAME_DIVISOR (6)
    let phase = ferris_phase(&app, &welcome, width, now);
    match phase {
        FerrisPhase::Connecting { spinner_frame } => {
            assert_eq!(spinner_frame, 12);
        }
        _ => panic!("Expected Connecting phase"),
    }
}

#[test]
fn hello_phase_elapsed_tracks_time_since_first_connect() {
    let mut app = make_test_app();
    let welcome = make_welcome_block();
    let width = 200;
    let base_time = Instant::now();
    
    // Manually set first_connected_at to base_time
    app.startup.first_connected_at = Some(base_time);
    
    // At base_time, elapsed = 0
    let phase = ferris_phase(&app, &welcome, width, base_time);
    match phase {
        FerrisPhase::Hello { elapsed } => {
            assert_eq!(elapsed, Duration::from_millis(0));
        }
        _ => panic!("Expected Hello phase at t=0"),
    }
    
    // At base_time + 500ms, elapsed = 500ms
    let phase = ferris_phase(&app, &welcome, width, base_time + Duration::from_millis(500));
    match phase {
        FerrisPhase::Hello { elapsed } => {
            assert_eq!(elapsed, Duration::from_millis(500));
        }
        _ => panic!("Expected Hello phase at t=500ms"),
    }
}

#[test]
fn rest_phase_when_motion_not_allowed() {
    let mut app = App::test_default();
    app.config.prefers_reduced_motion = true; // Disable motion
    let welcome = make_welcome_block();
    let width = 200;
    let now = Instant::now();
    
    let phase = ferris_phase(&app, &welcome, width, now);
    assert_eq!(phase, FerrisPhase::Rest);
}

#[test]
fn rest_phase_when_shutdown_requested() {
    let mut app = make_test_app();
    app.shutdown = true;
    let welcome = make_welcome_block();
    let width = 200;
    let now = Instant::now();
    
    let phase = ferris_phase(&app, &welcome, width, now);
    assert_eq!(phase, FerrisPhase::Rest);
}

#[test]
fn rest_phase_when_overview_hidden() {
    let mut app = make_test_app();
    app.show_session_overview = false;
    let welcome = make_welcome_block();
    let width = 200;
    let now = Instant::now();
    
    let phase = ferris_phase(&app, &welcome, width, now);
    assert_eq!(phase, FerrisPhase::Rest);
}

#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn frame_ms_is_450() {
        assert_eq!(FRAME_MS, 450);
    }
    
    #[test]
    fn frame_count_is_3() {
        assert_eq!(FRAME_COUNT, 3);
    }
}
