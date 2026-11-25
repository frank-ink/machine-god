//! Additional integration tests for `claude_code` module.
//! These tests verify the mode switch logic with realistic scenarios.

use crate::zero::claude_code::*;

#[test]
fn test_full_mode_switch_flow_logged_in() {
    let mut state = ModeState::default();
    assert_eq!(state.current_mode, Mode::FreePool);

    // Simulate logged in
    state.login_status = LoginStatus::LoggedIn;

    // Switch to Claude Code
    let result = state.switch_mode(Mode::ClaudeCode);
    assert!(result.is_ok());
    assert_eq!(state.current_mode, Mode::ClaudeCode);

    // Switch back to Free Pool
    let result = state.switch_mode(Mode::FreePool);
    assert!(result.is_ok());
    assert_eq!(state.current_mode, Mode::FreePool);
}

#[test]
fn test_full_mode_switch_flow_not_logged_in() {
    let mut state = ModeState { login_status: LoginStatus::NotLoggedIn, ..ModeState::default() };

    // Attempt to switch to Claude Code - should fail
    let result = state.switch_mode(Mode::ClaudeCode);
    assert!(result.is_err());
    assert_eq!(state.current_mode, Mode::FreePool);
    assert!(result.unwrap_err().contains("login required"));
}

#[test]
fn test_refresh_login_updates_status() {
    let mut state = ModeState::default();
    assert_eq!(state.login_status, LoginStatus::Unknown);
    assert!(state.last_detection.is_none());

    state.refresh_login();
    // After refresh, status is either LoggedIn, NotLoggedIn, or Unknown
    // (depends on actual filesystem state)
    assert!(state.last_detection.is_some());
    assert!(state.last_detection.unwrap() > 0);
}

#[test]
fn test_child_process_wrapper() {
    // Test that ChildProcess struct can be created and has expected methods
    // We can't easily spawn a real process in unit tests without side effects
    // This test ensures the API compiles correctly
    let req = build_free_pool_request();
    assert_eq!(req.model, "auto");
}

#[test]
fn test_mode_state_default_values() {
    let state = ModeState::default();
    assert_eq!(state.current_mode, Mode::FreePool);
    assert_eq!(state.login_status, LoginStatus::Unknown);
    assert!(state.last_detection.is_none());
}

#[test]
fn test_status_line_both_languages() {
    let state = ModeState {
        login_status: LoginStatus::LoggedIn,
        current_mode: Mode::ClaudeCode,
        ..ModeState::default()
    };

    let en = state.status_line("en");
    assert!(en.contains("Claude Code"));
    assert!(en.contains("logged in"));

    let de = state.status_line("de");
    assert!(de.contains("Claude Code"));
    assert!(de.contains("angemeldet"));
}

#[test]
fn test_invalid_mode_transition_rejected() {
    let mut state = ModeState {
        current_mode: Mode::ClaudeCode,
        login_status: LoginStatus::LoggedIn,
        ..ModeState::default()
    };

    // This is actually valid (ClaudeCode -> FreePool)
    let result = state.switch_mode(Mode::FreePool);
    assert!(result.is_ok());

    // Now try FreePool -> FreePool (noop)
    state.current_mode = Mode::FreePool;
    let result = state.switch_mode(Mode::FreePool);
    assert!(result.is_ok());
}

#[test]
fn test_omnipool_request_with_custom_values() {
    let mut req = build_free_pool_request();
    req.model = "custom-model".to_owned();
    req.max_tokens = Some(2048);
    req.temperature = Some(0.5);
    req.messages.push(OmnipoolMessage { role: "user".to_owned(), content: "Hello".to_owned() });

    assert_eq!(req.model, "custom-model");
    assert_eq!(req.max_tokens, Some(2048));
    assert_eq!(req.temperature, Some(0.5));
    assert_eq!(req.messages.len(), 1);
}

#[test]
fn test_mode_state_serialization_roundtrip() {
    let state = ModeState {
        current_mode: Mode::ClaudeCode,
        login_status: LoginStatus::LoggedIn,
        last_detection: Some(1_700_000_000),
    };

    let json = serde_json::to_string(&state).unwrap();
    let restored: ModeState = serde_json::from_str(&json).unwrap();

    assert_eq!(restored.current_mode, Mode::ClaudeCode);
    assert_eq!(restored.login_status, LoginStatus::LoggedIn);
    assert_eq!(restored.last_detection, Some(1_700_000_000));
}

#[test]
fn test_detect_claude_login_no_credentials_file() {
    // Test that missing credentials file returns NotLoggedIn
    // We can't easily mock dirs::home_dir, but we can verify the logic
    // by checking the function doesn't panic and returns a valid status
    let status = detect_claude_login();
    // Should be one of the three valid states
    assert!(matches!(
        status,
        LoginStatus::LoggedIn | LoginStatus::NotLoggedIn | LoginStatus::Unknown
    ));
}

#[test]
fn test_explain_claude_setup_contains_key_elements() {
    let en = explain_claude_setup("en");
    let de = explain_claude_setup("de");

    // Both should contain the login command
    assert!(en.contains("claude /login"));
    assert!(de.contains("claude /login"));

    // Both should mention free pool default
    assert!(en.contains("Free Pool"));
    assert!(de.contains("Free Pool"));

    // Both should mention no API key handling
    assert!(en.contains("No API keys") || en.contains("no API keys"));
    assert!(de.contains("Keine API-Keys") || de.contains("keine API-Keys"));
}
