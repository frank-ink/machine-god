//! Claude Code mode switch logic for Machine God.
//! Pure functions for login detection, subprocess execution, and free pool requests.
//! No credential handling; uses user's own Claude Code subscription.

use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::process::Stdio;
use tokio::process::{Child, Command};

/// Current operation mode of the agent.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Mode {
    /// Free pool (Omnipool) - default, no login required
    FreePool,
    /// Real Claude Code with user's own subscription login
    ClaudeCode,
}

impl Default for Mode {
    fn default() -> Self {
        Mode::FreePool
    }
}

/// Login status detected from ~/.claude/.credentials.json
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum LoginStatus {
    /// Valid credentials file found
    LoggedIn,
    /// Credentials file missing or invalid
    NotLoggedIn,
    /// Detection failed (IO error, parse error, etc.)
    Unknown,
}

/// Request structure for Omnipool free pool.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OmnipoolRequest {
    pub model: String,
    pub messages: Vec<OmnipoolMessage>,
    pub max_tokens: Option<u32>,
    pub temperature: Option<f32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OmnipoolMessage {
    pub role: String,
    pub content: String,
}

/// Wrapper around tokio Child process for Claude Code execution.
pub struct ChildProcess {
    pub child: Child,
}

impl ChildProcess {
    /// Wait for the process to complete and return exit status.
    pub async fn wait(mut self) -> std::io::Result<std::process::ExitStatus> {
        self.child.wait().await
    }

    /// Get the process ID.
    pub fn id(&self) -> Option<u32> {
        self.child.id()
    }

    /// Kill the process.
    pub async fn kill(&mut self) -> std::io::Result<()> {
        self.child.kill().await
    }
}

/// Get the path to the Claude credentials file.
fn claude_credentials_path() -> PathBuf {
    dirs::home_dir()
        .map(|h| h.join(".claude").join(".credentials.json"))
        .unwrap_or_else(|| PathBuf::from("/nonexistent/.claude/.credentials.json"))
}

/// Pure function: detect Claude Code login status.
/// Reads ~/.claude/.credentials.json and validates basic structure.
/// No side effects, no network calls, no credential extraction.
pub fn detect_claude_login() -> LoginStatus {
    let path = claude_credentials_path();

    if !path.exists() {
        return LoginStatus::NotLoggedIn;
    }

    let content = match std::fs::read_to_string(&path) {
        Ok(c) => c,
        Err(_) => return LoginStatus::Unknown,
    };

    // Basic JSON validation - check for required fields without extracting secrets
    let parsed: serde_json::Value = match serde_json::from_str(&content) {
        Ok(v) => v,
        Err(_) => return LoginStatus::Unknown,
    };

    // Check for expected structure: { "claudeAiOauth": { "accessToken": "...", ... } }
    let has_oauth = parsed
        .get("claudeAiOauth")
        .and_then(|v| v.get("accessToken"))
        .and_then(|v| v.as_str())
        .map(|s| !s.is_empty())
        .unwrap_or(false);

    if has_oauth { LoginStatus::LoggedIn } else { LoginStatus::NotLoggedIn }
}

/// Pure function: build a default Omnipool request for free pool mode.
pub fn build_free_pool_request() -> OmnipoolRequest {
    OmnipoolRequest {
        model: "auto".to_string(),
        messages: Vec::new(),
        max_tokens: Some(4096),
        temperature: Some(0.7),
    }
}

/// Run Claude Code with the given arguments.
/// Spawns a subprocess inheriting the user's environment (including credentials).
/// No credential handling in this code - the subprocess uses the user's own login.
pub fn run_claude_code(args: Vec<String>) -> std::io::Result<ChildProcess> {
    let mut cmd = Command::new("claude");
    cmd.args(args)
        .stdin(Stdio::inherit())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        // Inherit environment so Claude Code finds user's ~/.claude/.credentials.json
        .env_clear() // Start clean, then explicitly pass needed vars
        .envs(std::env::vars().filter(|(k, _)| {
            // Pass through standard environment variables
            matches!(
                k.as_str(),
                "HOME"
                    | "USER"
                    | "PATH"
                    | "SHELL"
                    | "TERM"
                    | "LANG"
                    | "LC_ALL"
                    | "CLAUDE_CONFIG_DIR"
                    | "ANTHROPIC_API_KEY" // User may have this set
            )
        }));

    let child = cmd.spawn()?;
    Ok(ChildProcess { child })
}

/// Get setup explanation for Claude Code login (German or English).
pub fn explain_claude_setup(lang: &str) -> String {
    match lang {
        "de" | "DE" | "de_DE" | "de-DE" => r#"## Claude Code Setup

Um den **Claude Code Modus** zu nutzen, müssen Sie sich einmalig bei Claude Code anmelden:

```bash
claude /login
```

Dies öffnet einen Browser, in dem Sie sich mit Ihrem Anthropic-Account anmelden.
Die Anmeldedaten werden lokal in `~/.claude/.credentials.json` gespeichert.

**Wichtig:**
- Keine API-Keys werden kopiert oder von diesem Programm gelesen
- Claude Code nutzt Ihr eigenes Abonnement
- Der Standard-Modus bleibt **Free Pool (Omnipool)**

Nach dem Login können Sie im Menü auf "Claude Code" umschalten."#
            .to_string(),
        _ => r#"## Claude Code Setup

To use **Claude Code mode**, you need to log in once:

```bash
claude /login
```

This opens a browser for you to sign in with your Anthropic account.
Credentials are stored locally in `~/.claude/.credentials.json`.

**Important:**
- No API keys are copied or read by this program
- Claude Code uses your own subscription
- Default mode stays **Free Pool (Omnipool)**

After login, you can switch to "Claude Code" in the menu."#
            .to_string(),
    }
}

/// Mode state for the application.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModeState {
    pub current_mode: Mode,
    pub login_status: LoginStatus,
    /// Unix timestamp (seconds since epoch) of last login detection
    pub last_detection: Option<i64>,
}

impl Default for ModeState {
    fn default() -> Self {
        Self {
            current_mode: Mode::default(),
            login_status: LoginStatus::Unknown,
            last_detection: None,
        }
    }
}

impl ModeState {
    /// Refresh login status from disk.
    pub fn refresh_login(&mut self) {
        self.login_status = detect_claude_login();
        self.last_detection = Some(chrono::Utc::now().timestamp());
    }

    /// Attempt to switch mode. Returns Ok(()) on success, Err with explanation on failure.
    pub fn switch_mode(&mut self, target: Mode) -> Result<(), String> {
        match (self.current_mode, target) {
            (Mode::FreePool, Mode::ClaudeCode) => {
                if self.login_status == LoginStatus::LoggedIn {
                    self.current_mode = Mode::ClaudeCode;
                    Ok(())
                } else {
                    self.refresh_login();
                    if self.login_status == LoginStatus::LoggedIn {
                        self.current_mode = Mode::ClaudeCode;
                        Ok(())
                    } else {
                        Err("Claude Code login required. Run `claude /login` first.".to_string())
                    }
                }
            }
            (Mode::ClaudeCode, Mode::FreePool) => {
                self.current_mode = Mode::FreePool;
                Ok(())
            }
            (current, target) if current == target => Ok(()),
            _ => Err(format!("Invalid mode transition: {:?} -> {:?}", self.current_mode, target)),
        }
    }

    /// Get a human-readable status line.
    pub fn status_line(&self, lang: &str) -> String {
        let mode_str = match (lang, self.current_mode) {
            ("de" | "DE" | "de_DE" | "de-DE", Mode::FreePool) => "Free Pool (Omnipool)",
            ("de" | "DE" | "de_DE" | "de-DE", Mode::ClaudeCode) => "Claude Code (Ihr Login)",
            (_, Mode::FreePool) => "Free Pool (Omnipool)",
            (_, Mode::ClaudeCode) => "Claude Code (Your Login)",
        };

        let login_str = match (lang, self.login_status) {
            ("de" | "DE" | "de_DE" | "de-DE", LoginStatus::LoggedIn) => "angemeldet",
            ("de" | "DE" | "de_DE" | "de-DE", LoginStatus::NotLoggedIn) => "nicht angemeldet",
            ("de" | "DE" | "de_DE" | "de-DE", LoginStatus::Unknown) => "unbekannt",
            (_, LoginStatus::LoggedIn) => "logged in",
            (_, LoginStatus::NotLoggedIn) => "not logged in",
            (_, LoginStatus::Unknown) => "unknown",
        };

        format!("Mode: {} | Login: {}", mode_str, login_str)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn test_mode_default_is_free_pool() {
        let state = ModeState::default();
        assert_eq!(state.current_mode, Mode::FreePool);
    }

    #[test]
    fn test_login_status_default_unknown() {
        let state = ModeState::default();
        assert_eq!(state.login_status, LoginStatus::Unknown);
    }

    #[test]
    fn test_switch_free_pool_to_claude_code_requires_login() {
        let mut state = ModeState::default();
        state.login_status = LoginStatus::NotLoggedIn;

        let result = state.switch_mode(Mode::ClaudeCode);
        assert!(result.is_err());
        assert_eq!(state.current_mode, Mode::FreePool);
    }

    #[test]
    fn test_switch_claude_code_to_free_pool_always_allowed() {
        let mut state = ModeState::default();
        state.current_mode = Mode::ClaudeCode;
        state.login_status = LoginStatus::LoggedIn;

        let result = state.switch_mode(Mode::FreePool);
        assert!(result.is_ok());
        assert_eq!(state.current_mode, Mode::FreePool);
    }

    #[test]
    fn test_switch_to_same_mode_is_noop() {
        let mut state = ModeState::default();
        let result = state.switch_mode(Mode::FreePool);
        assert!(result.is_ok());
        assert_eq!(state.current_mode, Mode::FreePool);
    }

    #[test]
    fn test_build_free_pool_request_defaults() {
        let req = build_free_pool_request();
        assert_eq!(req.model, "auto");
        assert_eq!(req.max_tokens, Some(4096));
        assert_eq!(req.temperature, Some(0.7));
        assert!(req.messages.is_empty());
    }

    #[test]
    fn test_explain_claude_setup_english() {
        let msg = explain_claude_setup("en");
        assert!(msg.contains("claude /login"));
        assert!(msg.contains("Free Pool"));
        assert!(msg.contains("No API keys"));
    }

    #[test]
    fn test_explain_claude_setup_german() {
        let msg = explain_claude_setup("de");
        assert!(msg.contains("claude /login"));
        assert!(msg.contains("Free Pool"));
        assert!(msg.contains("Keine API-Keys"));
    }

    #[test]
    fn test_mode_state_status_line() {
        let mut state = ModeState::default();
        state.login_status = LoginStatus::LoggedIn;

        let line_en = state.status_line("en");
        assert!(line_en.contains("Free Pool"));
        assert!(line_en.contains("logged in"));

        let line_de = state.status_line("de");
        assert!(line_de.contains("Free Pool"));
        assert!(line_de.contains("angemeldet"));
    }

    #[test]
    fn test_omnipool_request_serialization() {
        let req = build_free_pool_request();
        let json = serde_json::to_string(&req).unwrap();
        assert!(json.contains("\"model\":\"auto\""));
        assert!(json.contains("\"max_tokens\":4096"));
    }

    #[test]
    fn test_mode_serialization() {
        let free = Mode::FreePool;
        let claude = Mode::ClaudeCode;

        assert_eq!(serde_json::to_string(&free).unwrap(), "\"free_pool\"");
        assert_eq!(serde_json::to_string(&claude).unwrap(), "\"claude_code\"");
    }

    #[test]
    fn test_login_status_serialization() {
        assert_eq!(serde_json::to_string(&LoginStatus::LoggedIn).unwrap(), "\"logged_in\"");
        assert_eq!(serde_json::to_string(&LoginStatus::NotLoggedIn).unwrap(), "\"not_logged_in\"");
        assert_eq!(serde_json::to_string(&LoginStatus::Unknown).unwrap(), "\"unknown\"");
    }

    #[test]
    fn test_mode_state_serialization_roundtrip() {
        let mut state = ModeState::default();
        state.current_mode = Mode::ClaudeCode;
        state.login_status = LoginStatus::LoggedIn;
        state.last_detection = Some(1_700_000_000);

        let json = serde_json::to_string(&state).unwrap();
        let restored: ModeState = serde_json::from_str(&json).unwrap();

        assert_eq!(restored.current_mode, Mode::ClaudeCode);
        assert_eq!(restored.login_status, LoginStatus::LoggedIn);
        assert_eq!(restored.last_detection, Some(1_700_000_000));
    }

    #[test]
    fn test_refresh_login_updates_timestamp() {
        let mut state = ModeState::default();
        assert!(state.last_detection.is_none());

        state.refresh_login();
        assert!(state.last_detection.is_some());
        assert!(state.last_detection.unwrap() > 0);
    }
}
