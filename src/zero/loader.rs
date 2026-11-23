//! Compile-time embedded loader for the bundled FranKenstein plugin manifest.
//!
//! The manifest source is embedded with [`include_str!`]. Loading therefore
//! performs no filesystem access at runtime. A missing source file is a
//! compile-time error; malformed JSON or invalid declarations return
//! [`LoadError`].
//!
//! A parsed manifest describes the bundled plugin. It is not evidence that
//! hooks are installed, executable, or healthy.

use serde::{Deserialize, Serialize};
use thiserror::Error;

/// UTF-8 manifest source baked into the binary at compile time.
///
/// The path is relative to `src/zero/loader.rs` and resolves to the repository
/// root's `plugins/frankenstein3/zero-manifest.json` (Zero's own declarations; the Claude Code manifest `.claude-plugin/plugin.json` stays untouched).
pub const BUILTIN_MANIFEST_JSON: &str =
    include_str!("../../plugins/frankenstein3/zero-manifest.json");

/// Declarative manifest for the bundled plugin.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PluginManifest {
    /// Stable plugin identifier.
    pub name: String,
    /// Plugin release version.
    pub version: String,
    /// Human-readable summary of the plugin declaration.
    #[serde(default)]
    pub description: String,
    /// Hook-point declarations. These do not constitute runtime health evidence.
    #[serde(default)]
    pub hooks: Vec<PluginHook>,
}

/// A named association between the plugin and a host hook event.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PluginHook {
    /// Stable identifier within this manifest.
    pub id: String,
    /// Host event at which the hook may be invoked.
    pub event: HookEvent,
}

/// Hook events understood by this manifest format.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum HookEvent {
    SessionStart,
    PreToolUse,
    PostToolUse,
}

/// Failure to parse or validate the embedded manifest.
///
/// There is deliberately no runtime `NotFound` variant: `include_str!` rejects
/// a missing manifest while compiling the crate.
#[derive(Debug, Error)]
pub enum LoadError {
    #[error("failed to parse embedded plugin manifest: {source}")]
    Parse {
        #[source]
        source: serde_json::Error,
    },
    #[error("embedded plugin manifest failed validation: {reason}")]
    Validation { reason: String },
}

/// Parse and validate the manifest embedded in this binary.
///
/// This function reads only [`BUILTIN_MANIFEST_JSON`] and performs no runtime
/// filesystem or network operations.
pub fn load_builtin_manifest() -> Result<PluginManifest, LoadError> {
    parse_manifest(BUILTIN_MANIFEST_JSON)
}

/// Pure parsing transition used by both the embedded loader and unit tests.
fn parse_manifest(source: &str) -> Result<PluginManifest, LoadError> {
    let manifest: PluginManifest =
        serde_json::from_str(source).map_err(|source| LoadError::Parse { source })?;
    validate_manifest(&manifest)?;
    Ok(manifest)
}

fn validate_manifest(manifest: &PluginManifest) -> Result<(), LoadError> {
    if manifest.name.trim().is_empty() {
        return Err(validation_error("name must not be empty"));
    }

    if !is_semver_core(&manifest.version) {
        return Err(validation_error(
            "version must contain a numeric major.minor.patch core",
        ));
    }

    for (index, hook) in manifest.hooks.iter().enumerate() {
        if hook.id.trim().is_empty() {
            return Err(validation_error("hook ids must not be empty"));
        }

        if manifest.hooks[..index]
            .iter()
            .any(|previous| previous.id == hook.id)
        {
            return Err(validation_error("hook ids must be unique"));
        }
    }

    Ok(())
}

fn validation_error(reason: impl Into<String>) -> LoadError {
    LoadError::Validation {
        reason: reason.into(),
    }
}

/// Validate the numeric core while permitting semver pre-release/build suffixes.
fn is_semver_core(version: &str) -> bool {
    let core_end = version
        .find(|character| character == '-' || character == '+')
        .unwrap_or(version.len());
    let core = &version[..core_end];
    let parts: Vec<&str> = core.split('.').collect();

    parts.len() == 3
        && parts.iter().all(|part| {
            !part.is_empty() && part.chars().all(|character| character.is_ascii_digit())
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn builtin_manifest_has_expected_identity_and_hooks() {
        let manifest = load_builtin_manifest().expect("embedded manifest must be valid");

        assert_eq!(manifest.name, "frankenstein3");
        assert_eq!(manifest.version, "3.0.0");
        assert!(!manifest.description.trim().is_empty());

        let ids: Vec<&str> = manifest
            .hooks
            .iter()
            .map(|hook| hook.id.as_str())
            .collect();
        assert_eq!(ids, ["session-start", "pre-tool-use", "post-tool-use"]);

        let events: Vec<HookEvent> = manifest.hooks.iter().map(|hook| hook.event).collect();
        assert_eq!(
            events,
            [
                HookEvent::SessionStart,
                HookEvent::PreToolUse,
                HookEvent::PostToolUse,
            ]
        );
    }

    #[test]
    fn loading_the_embedded_manifest_is_deterministic() {
        let first = load_builtin_manifest().expect("first load must succeed");
        let second = load_builtin_manifest().expect("second load must succeed");
        assert_eq!(first, second);
    }

    #[test]
    fn optional_fields_default_without_runtime_discovery() {
        let manifest = parse_manifest(
            r#"{
                "name": "frankenstein3",
                "version": "3.0.0"
            }"#,
        )
        .expect("minimal manifest must parse");

        assert!(manifest.description.is_empty());
        assert!(manifest.hooks.is_empty());
    }

    #[test]
    fn unknown_standard_metadata_does_not_break_loading() {
        let manifest = parse_manifest(
            r#"{
                "name": "frankenstein3",
                "version": "3.0.0-alpha.1",
                "license": "UNSPECIFIED",
                "keywords": ["zero"]
            }"#,
        )
        .expect("unknown metadata must be ignored");

        assert_eq!(manifest.version, "3.0.0-alpha.1");
    }

    #[test]
    fn malformed_json_returns_a_parse_error() {
        let error = parse_manifest("{not-json").expect_err("malformed JSON must fail");
        assert!(matches!(error, LoadError::Parse { .. }));
    }

    #[test]
    fn unknown_hook_event_returns_a_parse_error() {
        let error = parse_manifest(
            r#"{
                "name": "frankenstein3",
                "version": "3.0.0",
                "hooks": [{"id": "unknown", "event": "not_an_event"}]
            }"#,
        )
        .expect_err("unknown event must fail closed");

        assert!(matches!(error, LoadError::Parse { .. }));
    }

    #[test]
    fn blank_name_is_rejected() {
        let error = parse_manifest(
            r#"{
                "name": "  ",
                "version": "3.0.0"
            }"#,
        )
        .expect_err("blank name must fail validation");

        assert!(matches!(error, LoadError::Validation { .. }));
    }

    #[test]
    fn invalid_version_is_rejected() {
        let error = parse_manifest(
            r#"{
                "name": "frankenstein3",
                "version": "three"
            }"#,
        )
        .expect_err("invalid version must fail validation");

        assert!(matches!(error, LoadError::Validation { .. }));
    }

    #[test]
    fn duplicate_or_blank_hook_ids_are_rejected() {
        for hooks in [
            r#"[{"id": "", "event": "session_start"}]"#,
            r#"[
                {"id": "duplicate", "event": "session_start"},
                {"id": "duplicate", "event": "pre_tool_use"}
            ]"#,
        ] {
            let source = format!(
                r#"{{
                    "name": "frankenstein3",
                    "version": "3.0.0",
                    "hooks": {hooks}
                }}"#
            );
            let error = parse_manifest(&source).expect_err("invalid hook ids must fail");
            assert!(matches!(error, LoadError::Validation { .. }));
        }
    }
}
