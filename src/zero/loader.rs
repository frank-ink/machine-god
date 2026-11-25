//! Compile-time embedded loader for the bundled FranKenstein plugin manifest.
//!
//! The manifest source is embedded with [`include_str!`]. Loading therefore
//! performs no filesystem access at runtime. A missing source file is a
//! compile-time error; malformed JSON or invalid declarations return
//! [`LoadError`].
//!
//! A parsed manifest describes the bundled plugin. It is not evidence that
//! hooks are installed, executable, or healthy.
//!
//! Health reporting and goal table exposure are **measurement surfaces**.
//! Unmeasured fields yield [`Epistemic::Unknown`] — never `false`, `0`, or
//! an empty collection masquerading as success.

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
        return Err(validation_error("version must contain a numeric major.minor.patch core"));
    }

    for (index, hook) in manifest.hooks.iter().enumerate() {
        if hook.id.trim().is_empty() {
            return Err(validation_error("hook ids must not be empty"));
        }

        if manifest.hooks[..index].iter().any(|previous| previous.id == hook.id) {
            return Err(validation_error("hook ids must be unique"));
        }
    }

    Ok(())
}

fn validation_error(reason: impl Into<String>) -> LoadError {
    LoadError::Validation { reason: reason.into() }
}

/// Validate the numeric core while permitting semver pre-release/build suffixes.
fn is_semver_core(version: &str) -> bool {
    let core_end =
        version.find(|character| character == '-' || character == '+').unwrap_or(version.len());
    let core = &version[..core_end];
    let parts: Vec<&str> = core.split('.').collect();

    parts.len() == 3
        && parts.iter().all(|part| {
            !part.is_empty() && part.chars().all(|character| character.is_ascii_digit())
        })
}

/// Epistemic status of a measurement.
///
/// **Invariant**: `Unknown` means "measurement not performed or failed", never
/// "false", "zero", or "empty". Consumers must match on all variants.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum Epistemic<T> {
    /// Measurement succeeded; value is present.
    Measured(T),
    /// Measurement was attempted but failed (IO, parse, timeout, etc.).
    Failed(String),
    /// Measurement has not been performed; no evidence either way.
    Unknown,
}

impl<T> Epistemic<T> {
    /// Returns `true` only for `Measured(_)`. Never true for `Unknown` or `Failed`.
    pub const fn is_measured(&self) -> bool {
        matches!(self, Epistemic::Measured(_))
    }

    /// Returns the measured value or `None`. Does not conflate `Unknown` with absence.
    pub fn value(&self) -> Option<&T> {
        match self {
            Epistemic::Measured(v) => Some(v),
            Epistemic::Failed(_) | Epistemic::Unknown => None,
        }
    }

    /// Maps the measured value, preserving `Failed` and `Unknown`.
    pub fn map<U>(self, f: impl FnOnce(T) -> U) -> Epistemic<U> {
        match self {
            Epistemic::Measured(v) => Epistemic::Measured(f(v)),
            Epistemic::Failed(e) => Epistemic::Failed(e),
            Epistemic::Unknown => Epistemic::Unknown,
        }
    }
}

/// Health status for a single organ.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct OrganHealth {
    /// Stable organ identifier (e.g., "retina", "grid", "entityos", "omnipool").
    pub id: String,
    /// Human-readable name.
    pub name: String,
    /// Current health measurement.
    pub status: Epistemic<OrganStatus>,
    /// Optional detail from the last measurement attempt.
    #[serde(default)]
    pub detail: String,
}

/// Concrete health states — no boolean "healthy/unhealthy" collapse.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OrganStatus {
    /// Organ responded to health probe within expected bounds.
    Nominal,
    /// Organ responded but reported degraded function.
    Degraded,
    /// Organ responded but reported critical failure.
    Critical,
    /// Organ did not respond to probe (timeout, not running, etc.).
    Unresponsive,
}

/// Aggregated plugin health report.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PluginHealth {
    /// Plugin identifier from the manifest.
    pub plugin_id: String,
    /// Plugin version from the manifest.
    pub plugin_version: String,
    /// Overall plugin health — `Unknown` if no measurement performed.
    pub overall: Epistemic<OrganStatus>,
    /// Per-organ measurements. Empty vec means "no organs declared", not "all healthy".
    pub organs: Vec<OrganHealth>,
    /// Timestamp of the measurement attempt (RFC3339), or `Unknown` if not measured.
    pub measured_at: Epistemic<String>,
}

/// Complete health report returned by [`measure_health`].
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct HealthReport {
    /// Plugin-level health.
    pub plugin: PluginHealth,
    /// Additional organs not declared in the plugin manifest (e.g., host-level organs).
    #[serde(default)]
    pub extra_organs: Vec<OrganHealth>,
}

/// Measure plugin and organ health.
///
/// **This is a measurement surface, not a discovery mechanism.** It performs
/// no network calls and no filesystem access outside the embedded manifest.
/// Unmeasured organs yield `Epistemic::Unknown` — never `Nominal` by default.
///
/// The current implementation measures only what is available from the
/// embedded manifest (plugin identity/version). Organ probes are stubbed to
/// `Unknown` to uphold the epistemic invariant; real probes are added in
/// follow-up modules (grid.rs, entity.rs, retina.rs, etc.).
pub fn measure_health(manifest: &PluginManifest) -> HealthReport {
    let plugin = PluginHealth {
        plugin_id: manifest.name.clone(),
        plugin_version: manifest.version.clone(),
        overall: Epistemic::Unknown,
        organs: manifest
            .hooks
            .iter()
            .map(|hook| OrganHealth {
                id: hook.id.clone(),
                name: format!("hook:{}", hook.id),
                status: Epistemic::Unknown,
                detail: "no probe implemented".to_string(),
            })
            .collect(),
        measured_at: Epistemic::Unknown,
    };

    HealthReport { plugin, extra_organs: Vec::new() }
}

/// Measure plugin and organ health with explicit probe results.
///
/// This is a measurement surface for tests and for follow-up organ probes
/// (grid.rs, entity.rs, retina.rs, etc.). It performs no network calls and no
/// filesystem access. The `overall` status is derived from the organ probes:
/// all `Nominal` and at least one organ -> `Measured(Nominal)`; any
/// `Measured(Degraded)` -> `Measured(Degraded)`; otherwise `Unknown`.
pub fn measure_health_with_probes(
    manifest: &PluginManifest,
    probes: &[(String, OrganStatus, String)],
) -> HealthReport {
    let organs: Vec<OrganHealth> = probes
        .iter()
        .map(|(id, status, detail)| OrganHealth {
            id: id.clone(),
            name: format!("hook:{}", id),
            status: Epistemic::Measured(*status),
            detail: detail.clone(),
        })
        .collect();

    let overall = if !organs.is_empty()
        && organs
            .iter()
            .all(|organ| matches!(organ.status, Epistemic::Measured(OrganStatus::Nominal)))
    {
        Epistemic::Measured(OrganStatus::Nominal)
    } else if organs
        .iter()
        .any(|organ| matches!(organ.status, Epistemic::Measured(OrganStatus::Degraded)))
    {
        Epistemic::Measured(OrganStatus::Degraded)
    } else {
        Epistemic::Unknown
    };

    let plugin = PluginHealth {
        plugin_id: manifest.name.clone(),
        plugin_version: manifest.version.clone(),
        overall,
        organs,
        measured_at: Epistemic::Unknown,
    };

    HealthReport { plugin, extra_organs: Vec::new() }
}

/// A single goal row from Zero's goal table.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GoalRow {
    /// Stable goal identifier.
    pub id: String,
    /// Human-readable title.
    pub title: String,
    /// Current epistemic status of this goal.
    pub status: Epistemic<GoalStatus>,
    /// Optional metric or evidence reference.
    #[serde(default)]
    pub evidence_ref: String,
}

/// Goal lifecycle states — measured, not assumed.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum GoalStatus {
    /// Goal is declared but not yet acted upon.
    Pending,
    /// Work is in progress; measurable progress exists.
    InProgress,
    /// Goal achieved; verified by measurement.
    Achieved,
    /// Goal failed or was abandoned; verified by measurement.
    Failed,
    /// Goal blocked on external dependency.
    Blocked,
}

/// Goal table exposed as data.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GoalTable {
    /// All goal rows. Empty means "no goals declared", not "all achieved".
    pub rows: Vec<GoalRow>,
    /// Source of the goal data (e.g., "embedded", "unified.db", "unknown").
    pub source: String,
    /// Timestamp of the load attempt (RFC3339), or `Unknown` if not measured.
    pub loaded_at: Epistemic<String>,
}

/// Load Zero's goal table as data.
///
/// **This is a measurement surface.** It performs no network calls.
/// The current implementation returns an `Epistemic::Unknown` table with
/// `source = "unmeasured"` to uphold the invariant that missing measurement
/// is `Unknown`, never an empty table masquerading as "no goals".
/// Real implementations (reading from unified.db, embedded JSON, etc.) replace
/// this stub while preserving the `Epistemic` wrapper.
pub fn load_goals() -> GoalTable {
    GoalTable { rows: Vec::new(), source: "unmeasured".to_string(), loaded_at: Epistemic::Unknown }
}

/// Attempt to load goals from an embedded JSON source (for testing/stubbing).
///
/// Returns `Epistemic::Measured(GoalTable)` on success, `Epistemic::Failed`
/// on parse/validation error, `Epistemic::Unknown` if the source is not
/// provided (i.e., `None` input). This helper makes the epistemic discipline
/// explicit in tests.
pub fn load_goals_from_json(source: Option<&str>) -> Epistemic<GoalTable> {
    let Some(json) = source else {
        return Epistemic::Unknown;
    };

    #[derive(Deserialize)]
    struct RawGoal {
        id: String,
        title: String,
        #[serde(default)]
        status: Option<String>,
        #[serde(default)]
        evidence_ref: String,
    }

    let raw: Vec<RawGoal> = match serde_json::from_str(json) {
        Ok(v) => v,
        Err(e) => return Epistemic::Failed(e.to_string()),
    };

    let rows: Vec<GoalRow> = raw
        .into_iter()
        .map(|g| GoalRow {
            id: g.id,
            title: g.title,
            status: g
                .status
                .and_then(|s| match s.as_str() {
                    "pending" => Some(GoalStatus::Pending),
                    "in_progress" => Some(GoalStatus::InProgress),
                    "achieved" => Some(GoalStatus::Achieved),
                    "failed" => Some(GoalStatus::Failed),
                    "blocked" => Some(GoalStatus::Blocked),
                    _ => None,
                })
                .map(Epistemic::Measured)
                .unwrap_or(Epistemic::Unknown),
            evidence_ref: g.evidence_ref,
        })
        .collect();

    Epistemic::Measured(GoalTable {
        rows,
        source: "embedded_json".to_string(),
        loaded_at: Epistemic::Unknown, // timestamp would come from caller
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    // ===== Manifest loading =====

    #[test]
    fn builtin_manifest_has_expected_identity_and_hooks() {
        let manifest = load_builtin_manifest().expect("embedded manifest must be valid");

        assert_eq!(manifest.name, "frankenstein3");
        assert_eq!(manifest.version, "3.0.0");
        assert!(!manifest.description.trim().is_empty());

        let ids: Vec<&str> = manifest.hooks.iter().map(|hook| hook.id.as_str()).collect();
        assert_eq!(ids, ["session-start", "pre-tool-use", "post-tool-use"]);

        let events: Vec<HookEvent> = manifest.hooks.iter().map(|hook| hook.event).collect();
        assert_eq!(
            events,
            [HookEvent::SessionStart, HookEvent::PreToolUse, HookEvent::PostToolUse,]
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
    fn empty_manifest_source_returns_a_parse_error() {
        // Simulates a missing/empty manifest source: no JSON document to parse.
        let error = parse_manifest("").expect_err("empty manifest source must fail");
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

    // ===== Health reporting =====

    #[test]
    fn measure_health_returns_plugin_identity_from_manifest() {
        let manifest = load_builtin_manifest().expect("manifest must load");
        let report = measure_health(&manifest);

        assert_eq!(report.plugin.plugin_id, "frankenstein3");
        assert_eq!(report.plugin.plugin_version, "3.0.0");
    }

    #[test]
    fn measure_health_overall_is_unknown_not_nominal() {
        let manifest = load_builtin_manifest().expect("manifest must load");
        let report = measure_health(&manifest);

        // Critical invariant: unmeasured overall health is Unknown, never Measured(Nominal)
        assert_eq!(report.plugin.overall, Epistemic::Unknown);
        assert!(!report.plugin.overall.is_measured());
    }

    #[test]
    fn measure_health_organs_are_unknown_not_nominal() {
        let manifest = load_builtin_manifest().expect("manifest must load");
        let report = measure_health(&manifest);

        // Each hook becomes an organ; all must be Unknown (no probe implemented)
        assert_eq!(report.plugin.organs.len(), 3);
        for organ in &report.plugin.organs {
            assert_eq!(
                organ.status,
                Epistemic::Unknown,
                "organ {} defaulted to measured",
                organ.id
            );
            assert!(!organ.status.is_measured());
        }
    }

    #[test]
    fn measure_health_organ_ids_match_hook_ids() {
        let manifest = load_builtin_manifest().expect("manifest must load");
        let report = measure_health(&manifest);

        let organ_ids: Vec<&str> = report.plugin.organs.iter().map(|o| o.id.as_str()).collect();
        assert_eq!(organ_ids, ["session-start", "pre-tool-use", "post-tool-use"]);
    }

    #[test]
    fn measure_health_measured_at_is_unknown() {
        let manifest = load_builtin_manifest().expect("manifest must load");
        let report = measure_health(&manifest);

        assert_eq!(report.plugin.measured_at, Epistemic::Unknown);
    }

    #[test]
    fn measure_health_extra_organs_empty_by_default() {
        let manifest = load_builtin_manifest().expect("manifest must load");
        let report = measure_health(&manifest);

        assert!(report.extra_organs.is_empty());
    }

    #[test]
    fn measure_health_with_probes_all_nominal_yields_measured_nominal() {
        let manifest = load_builtin_manifest().expect("manifest must load");
        let probes = [
            ("session-start".to_string(), OrganStatus::Nominal, "ok".to_string()),
            ("pre-tool-use".to_string(), OrganStatus::Nominal, "ok".to_string()),
            ("post-tool-use".to_string(), OrganStatus::Nominal, "ok".to_string()),
        ];
        let report = measure_health_with_probes(&manifest, &probes);

        assert_eq!(report.plugin.overall, Epistemic::Measured(OrganStatus::Nominal));
        assert!(report.plugin.overall.is_measured());
        assert_eq!(report.plugin.organs.len(), 3);
        for organ in &report.plugin.organs {
            assert_eq!(organ.status, Epistemic::Measured(OrganStatus::Nominal));
        }
    }

    #[test]
    fn measure_health_with_probes_any_degraded_yields_measured_degraded() {
        let manifest = load_builtin_manifest().expect("manifest must load");
        let probes = [
            ("session-start".to_string(), OrganStatus::Nominal, "ok".to_string()),
            ("pre-tool-use".to_string(), OrganStatus::Degraded, "slow".to_string()),
            ("post-tool-use".to_string(), OrganStatus::Nominal, "ok".to_string()),
        ];
        let report = measure_health_with_probes(&manifest, &probes);

        assert_eq!(report.plugin.overall, Epistemic::Measured(OrganStatus::Degraded));
        assert!(report.plugin.overall.is_measured());
        // The degraded organ must be visible per-organ, not collapsed into a bool.
        let degraded: Vec<&OrganHealth> = report
            .plugin
            .organs
            .iter()
            .filter(|o| matches!(o.status, Epistemic::Measured(OrganStatus::Degraded)))
            .collect();
        assert_eq!(degraded.len(), 1);
        assert_eq!(degraded[0].id, "pre-tool-use");
    }

    #[test]
    fn measure_health_with_probes_empty_probes_yields_unknown() {
        let manifest = load_builtin_manifest().expect("manifest must load");
        let report = measure_health_with_probes(&manifest, &[]);

        assert_eq!(report.plugin.overall, Epistemic::Unknown);
        assert!(!report.plugin.overall.is_measured());
        assert!(report.plugin.organs.is_empty());
    }

    #[test]
    fn measure_health_with_probes_critical_without_degraded_yields_unknown() {
        // Per the transition rule, only Measured(Degraded) forces a measured
        // degraded overall; Critical alone without Degraded and without all
        // Nominal stays Unknown because no probe rule covers it.
        let manifest = load_builtin_manifest().expect("manifest must load");
        let probes = [("session-start".to_string(), OrganStatus::Critical, "down".to_string())];
        let report = measure_health_with_probes(&manifest, &probes);

        assert_eq!(report.plugin.overall, Epistemic::Unknown);
        assert!(!report.plugin.overall.is_measured());
        assert_eq!(report.plugin.organs[0].status, Epistemic::Measured(OrganStatus::Critical));
    }

    #[test]
    fn epistemic_unknown_is_not_measured_and_not_false() {
        // Direct test of the epistemic invariant
        let unknown: Epistemic<OrganStatus> = Epistemic::Unknown;
        assert!(!unknown.is_measured());
        assert!(unknown.value().is_none());

        let failed: Epistemic<OrganStatus> = Epistemic::Failed("timeout".into());
        assert!(!failed.is_measured());
        assert!(failed.value().is_none());

        let measured = Epistemic::Measured(OrganStatus::Nominal);
        assert!(measured.is_measured());
        assert_eq!(measured.value(), Some(&OrganStatus::Nominal));
    }

    #[test]
    fn epistemic_map_preserves_unknown_and_failed() {
        let unknown: Epistemic<i32> = Epistemic::Unknown;
        let mapped = unknown.map(|x| x * 2);
        assert_eq!(mapped, Epistemic::Unknown);

        let failed: Epistemic<i32> = Epistemic::Failed("err".into());
        let mapped = failed.map(|x| x * 2);
        assert_eq!(mapped, Epistemic::Failed("err".into()));

        let measured: Epistemic<i32> = Epistemic::Measured(21);
        let mapped = measured.map(|x| x * 2);
        assert_eq!(mapped, Epistemic::Measured(42));
    }

    // ===== Goal table =====

    #[test]
    fn load_goals_returns_unmeasured_table() {
        let table = load_goals();

        assert_eq!(table.source, "unmeasured");
        assert_eq!(table.loaded_at, Epistemic::Unknown);
        // Empty rows with source="unmeasured" means "not measured", not "no goals"
        assert!(table.rows.is_empty());
    }

    #[test]
    fn load_goals_from_json_none_returns_unknown() {
        let result = load_goals_from_json(None);
        assert_eq!(result, Epistemic::Unknown);
    }

    #[test]
    fn load_goals_from_json_malformed_returns_failed() {
        let result = load_goals_from_json(Some("{not json"));
        assert!(matches!(result, Epistemic::Failed(_)));
    }

    #[test]
    fn load_goals_from_json_valid_returns_measured_table() {
        let json = r#"[
            {"id": "g1", "title": "Goal One", "status": "pending", "evidence_ref": ""},
            {"id": "g2", "title": "Goal Two", "status": "achieved", "evidence_ref": "ref-123"}
        ]"#;

        let result = load_goals_from_json(Some(json));
        let measured = result.value().expect("must be Measured");

        assert_eq!(measured.source, "embedded_json");
        assert_eq!(measured.rows.len(), 2);
        assert_eq!(measured.rows[0].id, "g1");
        assert_eq!(measured.rows[0].title, "Goal One");
        assert_eq!(measured.rows[0].status, Epistemic::Measured(GoalStatus::Pending));
        assert_eq!(measured.rows[1].id, "g2");
        assert_eq!(measured.rows[1].status, Epistemic::Measured(GoalStatus::Achieved));
        assert_eq!(measured.rows[1].evidence_ref, "ref-123");
    }

    #[test]
    fn load_goals_from_json_unknown_status_yields_unknown() {
        let json =
            r#"[{"id": "g1", "title": "Goal One", "status": "not_a_status", "evidence_ref": ""}]"#;

        let result = load_goals_from_json(Some(json));
        let measured = result.value().expect("must be Measured");

        // Unknown status string -> Epistemic::Unknown, not a default status
        assert_eq!(measured.rows[0].status, Epistemic::Unknown);
    }

    #[test]
    fn load_goals_from_json_missing_status_yields_unknown() {
        let json = r#"[{"id": "g1", "title": "Goal One", "evidence_ref": ""}]"#;

        let result = load_goals_from_json(Some(json));
        let measured = result.value().expect("must be Measured");

        assert_eq!(measured.rows[0].status, Epistemic::Unknown);
    }

    #[test]
    fn goal_table_empty_rows_with_measured_source_is_distinct_from_unmeasured() {
        // An explicitly measured empty table (source="embedded_json", loaded_at=Measured)
        // is epistemically different from the unmeasured default.
        let json = "[]";
        let result = load_goals_from_json(Some(json));
        let measured = result.value().expect("must be Measured");

        assert_eq!(measured.rows.len(), 0);
        assert_eq!(measured.source, "embedded_json");
        // This table WAS measured (it's empty by declaration), unlike load_goals() default
        assert_ne!(measured.source, "unmeasured");
    }

    #[test]
    fn load_goals_from_json_populated_table_preserves_all_fields() {
        let json = r#"[
            {"id": "z1", "title": "Zero memory", "status": "in_progress", "evidence_ref": "unified.db#goals"},
            {"id": "z2", "title": "Exit gate", "status": "blocked", "evence_ref": "secrets/austritt"}
        ]"#;

        let result = load_goals_from_json(Some(json));
        let measured = result.value().expect("must be Measured");

        assert_eq!(measured.rows.len(), 2);
        assert_eq!(measured.rows[0].id, "z1");
        assert_eq!(measured.rows[0].status, Epistemic::Measured(GoalStatus::InProgress));
        assert_eq!(measured.rows[0].evidence_ref, "unified.db#goals");
        assert_eq!(measured.rows[1].id, "z2");
        assert_eq!(measured.rows[1].status, Epistemic::Measured(GoalStatus::Blocked));
        // Unknown/misspelled evidence_ref key is ignored by serde default, not treated as failure.
        assert_eq!(measured.rows[1].evidence_ref, "");
    }
}
