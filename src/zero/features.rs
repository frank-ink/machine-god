//! Capability registry, `/features` command handler, and the capability honesty gate.
//!
//! GRF / `ClayCode` mapping
//! -----------------------
//! `R_t` : `CapabilityRegistry` (canonical JSON registry; single source of truth)
//! `E_t` : registry JSON + `TestReport` (pipeline artifacts; never self-praise)
//! F   : validate -> render -> gate (pure, replayable, journaled by the pipeline)
//! M   : { MEASURED, PLANNED, UNKNOWN } with per-status admissibility rules
//!
//! Honesty laws (machine checked, fail closed):
//!   MEASURED => non-empty `evidence_ref` naming a passing test artifact
//!   PLANNED  => non-empty tracking issue id
//!   UNKNOWN  => no evidence claim at all (unknown stays unknown, never 0/0.5)
//!   A MEASURED capability without a passing test reference fails the CI gate.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::error::Error;
use std::fmt;
use std::fmt::Write as _;
use std::path::Path;

pub const REGISTRY_SCHEMA: &str = "zero.capabilities.v1";
pub const REPORT_SCHEMA: &str = "zero.test-report.v1";
pub const DEFAULT_REGISTRY_PATH: &str = "zero/capabilities.json";
pub const DEFAULT_REPORT_PATH: &str = "zero/test-report.json";
pub const FEATURES_COMMAND: &str = "/features";

/// Exact, documented column order for the `/features` table.
/// Must match docs/zero/capabilities.md one-to-one.
pub const TABLE_COLUMNS: [&str; 6] =
    ["capability", "status", "promotion_stage", "evidence_ref", "gate", "tracking_issue"];

/// The registry compiled into the binary: the same file the pipeline writes.
pub const EMBEDDED_REGISTRY_JSON: &str = include_str!("../../zero/capabilities.json");
/// The seed test report compiled into the binary; the pipeline replaces it.
pub const EMBEDDED_REPORT_JSON: &str = include_str!("../../zero/test-report.json");

// ---------------------------------------------------------------------------
// Compound values
// ---------------------------------------------------------------------------

/// Status is an epistemic class, not a score: UNKNOWN is neither zero nor error.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum CapabilityStatus {
    /// Verified by a passing test artifact.
    Measured,
    /// Intended work, tracked by an issue, not verified.
    Planned,
    /// No verifying measurement available. Does NOT assert absence.
    Unknown,
}

impl CapabilityStatus {
    pub fn as_str(self) -> &'static str {
        match self {
            CapabilityStatus::Measured => "MEASURED",
            CapabilityStatus::Planned => "PLANNED",
            CapabilityStatus::Unknown => "UNKNOWN",
        }
    }
}

impl fmt::Display for CapabilityStatus {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// Promotion stage in the CVIR ladder.
/// Explicit serde renames ensure wire format matches `as_str()` exactly.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize, Default)]
pub enum PromotionStage {
    #[serde(rename = "MEASURE")]
    Measure,
    #[serde(rename = "FALSIFY")]
    Falsify,
    #[serde(rename = "MATCHED_ABLATION")]
    MatchedAblation,
    #[serde(rename = "VERIFIED_OUTCOME")]
    VerifiedOutcome,
    #[serde(rename = "CAUSAL_CREDIT")]
    CausalCredit,
    #[serde(rename = "BOUNDED_ADMISSION")]
    BoundedAdmission,
    #[serde(rename = "REENTRY_TEST")]
    ReentryTest,
    #[serde(rename = "CONTROL_INFLUENCE")]
    ControlInfluence,
    #[serde(rename = "UNKNOWN")]
    #[default]
    Unknown,
}

impl PromotionStage {
    pub fn as_str(self) -> &'static str {
        match self {
            PromotionStage::Measure => "MEASURE",
            PromotionStage::Falsify => "FALSIFY",
            PromotionStage::MatchedAblation => "MATCHED_ABLATION",
            PromotionStage::VerifiedOutcome => "VERIFIED_OUTCOME",
            PromotionStage::CausalCredit => "CAUSAL_CREDIT",
            PromotionStage::BoundedAdmission => "BOUNDED_ADMISSION",
            PromotionStage::ReentryTest => "REENTRY_TEST",
            PromotionStage::ControlInfluence => "CONTROL_INFLUENCE",
            PromotionStage::Unknown => "UNKNOWN",
        }
    }
}

impl fmt::Display for PromotionStage {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct LocalizedText {
    #[serde(default)]
    pub de: String,
    #[serde(default)]
    pub en: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
// `capability` is the registry's wire field name; renaming it would break the on-disk contract.
#[allow(clippy::struct_field_names)]
pub struct Capability {
    pub capability: String,
    pub status: CapabilityStatus,
    #[serde(default)]
    pub promotion_stage: PromotionStage,
    /// `test:<test name>@<commit>` for MEASURED entries, empty otherwise.
    #[serde(default)]
    pub evidence_ref: String,
    /// The command / gate that measures this capability.
    #[serde(default)]
    pub gate: String,
    /// Tracking issue id, required for PLANNED entries.
    #[serde(default)]
    pub tracking_issue: Option<String>,
    #[serde(default)]
    pub description: LocalizedText,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CapabilityRegistry {
    pub schema: String,
    #[serde(default)]
    pub generated_by: Option<String>,
    #[serde(default)]
    pub commit: Option<String>,
    #[serde(default)]
    pub capabilities: Vec<Capability>,
}

/// A parsed evidence pointer: `test:<test name>@<commit>`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EvidenceRef {
    pub test_name: String,
    pub commit: String,
}

impl EvidenceRef {
    pub fn parse(raw: &str) -> Result<Self, String> {
        let trimmed = raw.trim();
        let rest = trimmed
            .strip_prefix("test:")
            .ok_or_else(|| format!("missing 'test:' prefix in {trimmed:?}"))?;
        let (name, commit) =
            rest.rsplit_once('@').ok_or_else(|| format!("missing '@<commit>' in {trimmed:?}"))?;
        let name = name.trim();
        let commit = commit.trim();
        if name.is_empty() {
            return Err(format!("empty test name in {trimmed:?}"));
        }
        if commit.is_empty() {
            return Err(format!("empty commit in {trimmed:?}"));
        }
        Ok(Self { test_name: name.to_owned(), commit: commit.to_owned() })
    }
}

/// Pipeline artifact: which tests passed, at which commit.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TestReport {
    pub schema: String,
    pub commit: String,
    #[serde(default)]
    pub passed_tests: Vec<String>,
}

impl TestReport {
    pub fn from_json_str(raw: &str) -> Result<Self, RegistryError> {
        let report: TestReport =
            serde_json::from_str(raw).map_err(|e| RegistryError::Json(e.to_string()))?;
        if report.schema != REPORT_SCHEMA {
            return Err(RegistryError::SchemaMismatch {
                expected: REPORT_SCHEMA.to_owned(),
                actual: report.schema,
            });
        }
        Ok(report)
    }

    pub fn load(path: &Path) -> Result<Self, RegistryError> {
        let raw = std::fs::read_to_string(path)
            .map_err(|e| RegistryError::Io(format!("{}: {}", path.display(), e)))?;
        Self::from_json_str(&raw)
    }

    pub fn contains(&self, test_name: &str) -> bool {
        self.passed_tests.iter().any(|t| t == test_name)
    }
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RegistryError {
    Io(String),
    Json(String),
    SchemaMismatch { expected: String, actual: String },
    EmptyCapabilityName,
    DuplicateCapability(String),
    MeasuredWithoutEvidence(String),
    MeasuredWithoutGate(String),
    PlannedWithoutTrackingIssue(String),
    UnknownWithEvidence(String),
    MalformedEvidence { capability: String, reason: String },
}

impl fmt::Display for RegistryError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            RegistryError::Io(m) => write!(f, "io error: {m}"),
            RegistryError::Json(m) => write!(f, "json error: {m}"),
            RegistryError::SchemaMismatch { expected, actual } => {
                write!(f, "schema mismatch: expected {expected}, got {actual}")
            }
            RegistryError::EmptyCapabilityName => write!(f, "capability name must not be empty"),
            RegistryError::DuplicateCapability(name) => {
                write!(f, "duplicate capability: {name}")
            }
            RegistryError::MeasuredWithoutEvidence(name) => {
                write!(f, "MEASURED capability '{name}' has no evidence_ref")
            }
            RegistryError::MeasuredWithoutGate(name) => {
                write!(f, "MEASURED capability '{name}' has no gate")
            }
            RegistryError::PlannedWithoutTrackingIssue(name) => {
                write!(f, "PLANNED capability '{name}' has no tracking issue id")
            }
            RegistryError::UnknownWithEvidence(name) => {
                write!(f, "UNKNOWN capability '{name}' must not carry an evidence_ref")
            }
            RegistryError::MalformedEvidence { capability, reason } => {
                write!(f, "malformed evidence for '{capability}': {reason}")
            }
        }
    }
}

impl Error for RegistryError {}

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

impl CapabilityRegistry {
    /// Admissibility check. Fail closed: any violation is an error.
    pub fn validate(&self) -> Result<(), RegistryError> {
        if self.schema != REGISTRY_SCHEMA {
            return Err(RegistryError::SchemaMismatch {
                expected: REGISTRY_SCHEMA.to_owned(),
                actual: self.schema.clone(),
            });
        }
        let mut seen: BTreeSet<String> = BTreeSet::new();
        for cap in &self.capabilities {
            let name = cap.capability.trim();
            if name.is_empty() {
                return Err(RegistryError::EmptyCapabilityName);
            }
            if !seen.insert(name.to_owned()) {
                return Err(RegistryError::DuplicateCapability(name.to_owned()));
            }
            match cap.status {
                CapabilityStatus::Measured => {
                    if cap.evidence_ref.trim().is_empty() {
                        return Err(RegistryError::MeasuredWithoutEvidence(name.to_owned()));
                    }
                    if cap.gate.trim().is_empty() {
                        return Err(RegistryError::MeasuredWithoutGate(name.to_owned()));
                    }
                    EvidenceRef::parse(&cap.evidence_ref).map_err(|reason| {
                        RegistryError::MalformedEvidence { capability: name.to_owned(), reason }
                    })?;
                }
                CapabilityStatus::Planned => {
                    let issue = cap.tracking_issue.as_deref().map_or("", str::trim);
                    if issue.is_empty() {
                        return Err(RegistryError::PlannedWithoutTrackingIssue(name.to_owned()));
                    }
                }
                CapabilityStatus::Unknown => {
                    if !cap.evidence_ref.trim().is_empty() {
                        return Err(RegistryError::UnknownWithEvidence(name.to_owned()));
                    }
                }
            }
        }
        Ok(())
    }

    pub fn from_json_str(raw: &str) -> Result<Self, RegistryError> {
        let registry: CapabilityRegistry =
            serde_json::from_str(raw).map_err(|e| RegistryError::Json(e.to_string()))?;
        registry.validate()?;
        Ok(registry)
    }

    pub fn load(path: &Path) -> Result<Self, RegistryError> {
        let raw = std::fs::read_to_string(path)
            .map_err(|e| RegistryError::Io(format!("{}: {}", path.display(), e)))?;
        Self::from_json_str(&raw)
    }

    /// The registry compiled into the binary (same file as `DEFAULT_REGISTRY_PATH`).
    pub fn embedded() -> Result<Self, RegistryError> {
        Self::from_json_str(EMBEDDED_REGISTRY_JSON)
    }

    /// Prefer the on-disk registry (pipeline output), fall back to the embedded copy.
    pub fn load_or_embedded(path: Option<&Path>) -> Result<Self, RegistryError> {
        match path {
            Some(p) => match Self::load(p) {
                Ok(r) => Ok(r),
                Err(_) => Self::embedded(),
            },
            None => Self::embedded(),
        }
    }

    pub fn find(&self, name: &str) -> Option<&Capability> {
        let needle = name.trim().to_lowercase();
        self.capabilities.iter().find(|c| c.capability.trim().to_lowercase() == needle)
    }

    /// Find a capability whose name is mentioned in free text.
    pub fn find_mentioned(&self, text: &str) -> Option<&Capability> {
        let haystack = text.to_lowercase();
        self.capabilities.iter().find(|c| haystack.contains(&c.capability.trim().to_lowercase()))
    }

    pub fn status_counts(&self) -> BTreeMap<CapabilityStatus, usize> {
        let mut counts = BTreeMap::new();
        for cap in &self.capabilities {
            *counts.entry(cap.status).or_insert(0usize) += 1;
        }
        counts
    }
}

// ---------------------------------------------------------------------------
// CI gate
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GateFailure {
    MissingReport,
    EmptyReportCommit,
    RegistryInvalid(String),
    MeasuredWithoutEvidence(String),
    MeasuredWithoutGate(String),
    MalformedEvidence { capability: String, reason: String },
    TestNotPassing { capability: String, test_name: String },
    CommitMismatch { capability: String, expected: String, actual: String },
}

impl fmt::Display for GateFailure {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            GateFailure::MissingReport => write!(f, "test report missing (fail closed)"),
            GateFailure::EmptyReportCommit => write!(f, "test report has no commit"),
            GateFailure::RegistryInvalid(m) => write!(f, "registry invalid: {m}"),
            GateFailure::MeasuredWithoutEvidence(name) => {
                write!(f, "MEASURED '{name}' has no evidence_ref")
            }
            GateFailure::MeasuredWithoutGate(name) => write!(f, "MEASURED '{name}' has no gate"),
            GateFailure::MalformedEvidence { capability, reason } => {
                write!(f, "malformed evidence for '{capability}': {reason}")
            }
            GateFailure::TestNotPassing { capability, test_name } => write!(
                f,
                "MEASURED '{capability}' references test '{test_name}' which is not in the passing test report"
            ),
            GateFailure::CommitMismatch { capability, expected, actual } => write!(
                f,
                "MEASURED '{capability}' evidence commit '{actual}' differs from report commit '{expected}'"
            ),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct GateReport {
    pub failures: Vec<GateFailure>,
}

impl GateReport {
    pub fn passed(&self) -> bool {
        self.failures.is_empty()
    }

    pub fn render(&self) -> String {
        if self.passed() {
            return "capability gate: PASS\n".to_owned();
        }
        let mut out = format!("capability gate: FAIL ({} failure(s))\n", self.failures.len());
        for failure in &self.failures {
            let _ = writeln!(out, "- {failure}");
        }
        out
    }
}

/// CI gate: every MEASURED capability must point to a passing test artifact
/// of the very commit that was tested. Missing report => fail closed.
pub fn ci_gate(registry: &CapabilityRegistry, report: Option<&TestReport>) -> GateReport {
    let mut failures: Vec<GateFailure> = Vec::new();

    if let Err(err) = registry.validate() {
        failures.push(GateFailure::RegistryInvalid(err.to_string()));
    }

    let Some(report) = report else {
        failures.push(GateFailure::MissingReport);
        return GateReport { failures };
    };

    if report.commit.trim().is_empty() {
        failures.push(GateFailure::EmptyReportCommit);
    }

    for cap in &registry.capabilities {
        if cap.status != CapabilityStatus::Measured {
            continue;
        }
        if cap.evidence_ref.trim().is_empty() {
            failures.push(GateFailure::MeasuredWithoutEvidence(cap.capability.clone()));
            continue;
        }
        if cap.gate.trim().is_empty() {
            failures.push(GateFailure::MeasuredWithoutGate(cap.capability.clone()));
        }
        let evidence = match EvidenceRef::parse(&cap.evidence_ref) {
            Ok(e) => e,
            Err(reason) => {
                failures.push(GateFailure::MalformedEvidence {
                    capability: cap.capability.clone(),
                    reason,
                });
                continue;
            }
        };
        if !report.contains(&evidence.test_name) {
            failures.push(GateFailure::TestNotPassing {
                capability: cap.capability.clone(),
                test_name: evidence.test_name.clone(),
            });
        }
        let report_commit = report.commit.trim();
        if !report_commit.is_empty() && evidence.commit != report_commit {
            failures.push(GateFailure::CommitMismatch {
                capability: cap.capability.clone(),
                expected: report_commit.to_owned(),
                actual: evidence.commit.clone(),
            });
        }
    }

    GateReport { failures }
}

/// Convenience: load registry + report from disk and run the gate.
pub fn ci_gate_from_paths(
    registry_path: &Path,
    report_path: &Path,
) -> Result<GateReport, RegistryError> {
    let registry = CapabilityRegistry::load(registry_path)?;
    let report = TestReport::load(report_path)?;
    Ok(ci_gate(&registry, Some(&report)))
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

fn dash_if_empty(value: &str) -> String {
    if value.trim().is_empty() { "-".to_owned() } else { value.to_owned() }
}

fn push_row(out: &mut String, cells: &[String; 6], widths: &[usize; 6]) {
    let mut parts: Vec<String> = Vec::with_capacity(6);
    for i in 0..6 {
        let mut cell = cells[i].clone();
        let len = cell.chars().count();
        if len < widths[i] {
            cell.push_str(&" ".repeat(widths[i] - len));
        }
        parts.push(cell);
    }
    out.push_str(&parts.join(" | "));
    out.push('\n');
}

/// `/features` table: capability | status | `promotion_stage` | `evidence_ref` | gate | `tracking_issue`
pub fn render_table(registry: &CapabilityRegistry) -> String {
    let headers = TABLE_COLUMNS;

    let mut rows: Vec<[String; 6]> = Vec::with_capacity(registry.capabilities.len());
    for cap in &registry.capabilities {
        rows.push([
            cap.capability.clone(),
            cap.status.as_str().to_owned(),
            cap.promotion_stage.as_str().to_owned(),
            dash_if_empty(&cap.evidence_ref),
            dash_if_empty(&cap.gate),
            dash_if_empty(cap.tracking_issue.as_deref().unwrap_or("")),
        ]);
    }

    let mut widths: [usize; 6] = [0, 0, 0, 0, 0, 0];
    for (i, header) in headers.iter().enumerate() {
        widths[i] = header.chars().count();
    }
    for row in &rows {
        for i in 0..6 {
            widths[i] = widths[i].max(row[i].chars().count());
        }
    }

    let mut out = String::new();
    let header_cells: [String; 6] = [
        headers[0].to_owned(),
        headers[1].to_owned(),
        headers[2].to_owned(),
        headers[3].to_owned(),
        headers[4].to_owned(),
        headers[5].to_owned(),
    ];
    push_row(&mut out, &header_cells, &widths);
    let separator: [String; 6] = [
        "-".repeat(widths[0]),
        "-".repeat(widths[1]),
        "-".repeat(widths[2]),
        "-".repeat(widths[3]),
        "-".repeat(widths[4]),
        "-".repeat(widths[5]),
    ];
    push_row(&mut out, &separator, &widths);
    for row in &rows {
        push_row(&mut out, row, &widths);
    }
    out
}

pub fn render_json(registry: &CapabilityRegistry) -> String {
    serde_json::to_string_pretty(registry)
        .unwrap_or_else(|e| format!("registry serialization failed: {e}"))
}

/// Compact, prompt-safe capability summary for the ground mode.
pub fn render_ground_summary(registry: &CapabilityRegistry, language: Language) -> String {
    let mut out = String::new();
    match language {
        Language::German => out.push_str("Faehigkeitsregister (kanonisch):\n"),
        Language::English => out.push_str("Capability registry (canonical):\n"),
    }
    for cap in &registry.capabilities {
        let _ = write!(
            out,
            "- {} [{}] promotion={}",
            cap.capability,
            cap.status.as_str(),
            cap.promotion_stage.as_str()
        );
        if cap.status == CapabilityStatus::Measured && !cap.evidence_ref.trim().is_empty() {
            let _ = write!(out, " evidence={}", cap.evidence_ref);
        }
        if cap.status == CapabilityStatus::Planned
            && let Some(issue) = cap.tracking_issue.as_deref()
        {
            let _ = write!(out, " issue={issue}");
        }
        out.push('\n');
    }
    out
}

// ---------------------------------------------------------------------------
// Language (DE / EN)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Language {
    German,
    English,
}

impl Language {
    pub fn code(self) -> &'static str {
        match self {
            Language::German => "de",
            Language::English => "en",
        }
    }

    pub fn from_code(code: &str) -> Option<Self> {
        match code.trim().to_lowercase().as_str() {
            "de" | "de-de" | "german" | "deutsch" => Some(Language::German),
            "en" | "en-us" | "en-gb" | "english" => Some(Language::English),
            _ => None,
        }
    }
}

const DE_MARKERS: &[&str] = &[
    "ä", "ö", "ü", "ß", " der ", " die ", " das ", " ist ", " sind ", " nicht ", " und ", " wie ",
    " was ", " bitte ", " kann", " welche ", " erklär", "erklaer", " zeig", "fähig", "faehig",
    "hallo", "danke", "gibt", "warum", "über", "ueber",
];

const EN_MARKERS: &[&str] = &[
    " the ",
    " is ",
    " are ",
    " not ",
    " and ",
    " how ",
    " what ",
    " please ",
    " explain",
    " show ",
    " can ",
    " which ",
    " why ",
    "hello",
    "thanks",
    "measured",
    "planned",
    "unknown",
    "capabilit",
    " with ",
    " for ",
    " will ",
    " have ",
];

/// Deterministic DE/EN detection. Unknown stays English default; never guesses
/// a third language and never claims certainty.
pub fn detect_language(text: &str) -> Language {
    let padded = format!(" {} ", text.to_lowercase());
    let mut de = 0usize;
    let mut en = 0usize;
    for marker in DE_MARKERS {
        de += padded.matches(*marker).count();
    }
    for marker in EN_MARKERS {
        en += padded.matches(*marker).count();
    }
    if de > en { Language::German } else { Language::English }
}

// ---------------------------------------------------------------------------
// Explanation (ground mode)
// ---------------------------------------------------------------------------

pub fn explain_entry(cap: &Capability, language: Language) -> String {
    let mut out = String::new();
    match language {
        Language::German => {
            match cap.status {
                CapabilityStatus::Measured => {
                    let _ = write!(
                        out,
                        "{} ist MEASURED: durch einen bestandenen Test belegt. Beleg: {}.",
                        cap.capability, cap.evidence_ref
                    );
                    if !cap.gate.trim().is_empty() {
                        let _ = write!(out, " Gate: {}.", cap.gate);
                    }
                }
                CapabilityStatus::Planned => {
                    let _ = write!(
                        out,
                        "{} ist PLANNED und noch nicht verifiziert. Tracking: {}.",
                        cap.capability,
                        cap.tracking_issue.as_deref().unwrap_or("UNKNOWN")
                    );
                    if !cap.gate.trim().is_empty() {
                        let _ = write!(out, " Geplantes Gate: {}.", cap.gate);
                    }
                }
                CapabilityStatus::Unknown => {
                    let _ = write!(
                        out,
                        "{} ist UNKNOWN: in dieser Registry liegt keine verifizierende Messung vor. Das heisst nicht, dass die Faehigkeit fehlt.",
                        cap.capability
                    );
                    if !cap.gate.trim().is_empty() {
                        let _ = write!(out, " Offenes Gate: {}.", cap.gate);
                    }
                }
            }
            let desc = cap.description.de.trim();
            if !desc.is_empty() {
                out.push(' ');
                out.push_str(desc);
            }
        }
        Language::English => {
            match cap.status {
                CapabilityStatus::Measured => {
                    let _ = write!(
                        out,
                        "{} is MEASURED: backed by a passing test. Evidence: {}.",
                        cap.capability, cap.evidence_ref
                    );
                    if !cap.gate.trim().is_empty() {
                        let _ = write!(out, " Gate: {}.", cap.gate);
                    }
                }
                CapabilityStatus::Planned => {
                    let _ = write!(
                        out,
                        "{} is PLANNED and not verified yet. Tracking: {}.",
                        cap.capability,
                        cap.tracking_issue.as_deref().unwrap_or("UNKNOWN")
                    );
                    if !cap.gate.trim().is_empty() {
                        let _ = write!(out, " Planned gate: {}.", cap.gate);
                    }
                }
                CapabilityStatus::Unknown => {
                    let _ = write!(
                        out,
                        "{} is UNKNOWN: this registry holds no verifying measurement. That does not mean the capability is absent.",
                        cap.capability
                    );
                    if !cap.gate.trim().is_empty() {
                        let _ = write!(out, " Open gate: {}.", cap.gate);
                    }
                }
            }
            let desc = cap.description.en.trim();
            if !desc.is_empty() {
                out.push(' ');
                out.push_str(desc);
            }
        }
    }
    out
}

// ---------------------------------------------------------------------------
// Command handler
// ---------------------------------------------------------------------------

/// `/features` command handler. Returns `None` when the input is not this command.
pub fn handle_features_command(input: &str, registry: &CapabilityRegistry) -> Option<String> {
    let trimmed = input.trim();
    if trimmed == FEATURES_COMMAND || trimmed.starts_with(&format!("{FEATURES_COMMAND} ")) {
        return Some(render_table(registry));
    }
    None
}

/// Alias kept for host call sites that use a generic command name.
pub fn handle_command(input: &str, registry: &CapabilityRegistry) -> Option<String> {
    handle_features_command(input, registry)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_registry_json() -> &'static str {
        r#"{
          "schema": "zero.capabilities.v1",
          "capabilities": [
            {
              "capability": "sample",
              "status": "MEASURED",
              "evidence_ref": "test:zero::features::tests::sample@WORKTREE",
              "gate": "cargo test -p machine_god zero::features"
            }
          ]
        }"#
    }

    #[test]
    fn registry_roundtrip() {
        let registry = CapabilityRegistry::embedded().unwrap();
        let json = serde_json::to_string(&registry).unwrap();
        let again = CapabilityRegistry::from_json_str(&json).unwrap();
        assert_eq!(registry, again);
    }

    #[test]
    fn render_table_has_required_columns() {
        let registry = CapabilityRegistry::embedded().unwrap();
        let table = render_table(&registry);
        let mut lines = table.lines();
        let header = lines.next().unwrap_or("");
        let separator = lines.next().unwrap_or("");

        let expected: [&str; 6] = TABLE_COLUMNS;

        let cells: Vec<String> = header.split(" | ").map(|c| c.trim().to_owned()).collect();
        assert_eq!(
            cells.len(),
            expected.len(),
            "header must have exactly {} columns",
            expected.len()
        );
        assert_eq!(cells, expected, "header columns must match documented order exactly");

        let sep_cells: Vec<String> = separator.split(" | ").map(|c| c.trim().to_owned()).collect();
        assert_eq!(
            sep_cells.len(),
            expected.len(),
            "separator must have exactly {} columns",
            expected.len()
        );

        // No duplicate columns.
        let mut seen = BTreeSet::new();
        for cell in &cells {
            assert!(seen.insert(cell.as_str()), "duplicate column: {cell}");
        }

        for cap in &registry.capabilities {
            assert!(table.contains(&cap.capability));
            assert!(table.contains(cap.status.as_str()));
        }
    }

    #[test]
    fn ci_gate_rejects_measured_without_passing_test() {
        let registry = CapabilityRegistry::from_json_str(sample_registry_json()).unwrap();
        let report = TestReport {
            schema: REPORT_SCHEMA.to_owned(),
            commit: "WORKTREE".to_owned(),
            passed_tests: Vec::new(),
        };
        let gate = ci_gate(&registry, Some(&report));
        assert!(!gate.passed());
        assert!(gate.failures.iter().any(|f| matches!(f, GateFailure::TestNotPassing { .. })));
    }

    #[test]
    fn ci_gate_accepts_shipped_artifacts() {
        let registry = CapabilityRegistry::embedded().unwrap();
        let report = TestReport::from_json_str(EMBEDDED_REPORT_JSON).unwrap();
        let gate = ci_gate(&registry, Some(&report));
        assert!(gate.passed(), "{}", gate.render());
    }

    #[test]
    fn ci_gate_fails_closed_without_report() {
        let registry = CapabilityRegistry::embedded().unwrap();
        let gate = ci_gate(&registry, None);
        assert!(!gate.passed());
        assert!(gate.failures.iter().any(|f| matches!(f, GateFailure::MissingReport)));
    }

    #[test]
    fn planned_requires_tracking_issue() {
        let raw = r#"{"schema":"zero.capabilities.v1","capabilities":[{"capability":"x","status":"PLANNED"}]}"#;
        let err = CapabilityRegistry::from_json_str(raw).unwrap_err();
        assert!(matches!(err, RegistryError::PlannedWithoutTrackingIssue(_)));
    }

    #[test]
    fn unknown_must_not_carry_evidence() {
        let raw = r#"{"schema":"zero.capabilities.v1","capabilities":[{"capability":"x","status":"UNKNOWN","evidence_ref":"test:a@b"}]}"#;
        let err = CapabilityRegistry::from_json_str(raw).unwrap_err();
        assert!(matches!(err, RegistryError::UnknownWithEvidence(_)));
    }

    #[test]
    fn measured_requires_evidence_and_gate() {
        let raw = r#"{"schema":"zero.capabilities.v1","capabilities":[{"capability":"x","status":"MEASURED"}]}"#;
        let err = CapabilityRegistry::from_json_str(raw).unwrap_err();
        assert!(matches!(err, RegistryError::MeasuredWithoutEvidence(_)));
    }

    #[test]
    fn features_command_renders_table() {
        let registry = CapabilityRegistry::embedded().unwrap();
        let out = handle_features_command("/features", &registry).unwrap();
        assert!(out.contains("promotion_stage"));
        assert!(out.contains("evidence_ref"));
        assert!(out.contains("gate"));
        assert!(out.contains("tracking_issue"));
        assert!(handle_features_command("/help", &registry).is_none());
    }

    #[test]
    fn detects_german_and_english() {
        assert_eq!(detect_language("Was kannst du bitte?"), Language::German);
        assert_eq!(detect_language("What can you do please?"), Language::English);
    }

    #[test]
    fn evidence_ref_parses_test_and_commit() {
        let parsed = EvidenceRef::parse("test:zero::features::tests::x@abc123").unwrap();
        assert_eq!(parsed.test_name, "zero::features::tests::x");
        assert_eq!(parsed.commit, "abc123");
        assert!(EvidenceRef::parse("abc123").is_err());
    }

    #[test]
    fn promotion_stage_roundtrip() {
        // Test that serde wire format matches as_str() for all 7 non-Unknown variants
        // plus Unknown (8 total)
        let stages = [
            PromotionStage::Measure,
            PromotionStage::Falsify,
            PromotionStage::MatchedAblation,
            PromotionStage::VerifiedOutcome,
            PromotionStage::CausalCredit,
            PromotionStage::BoundedAdmission,
            PromotionStage::ReentryTest,
            PromotionStage::ControlInfluence,
            PromotionStage::Unknown,
        ];

        for stage in stages {
            let serialized = serde_json::to_string(&stage).unwrap();
            let expected = format!("\"{}\"", stage.as_str());
            assert_eq!(
                serialized, expected,
                "PromotionStage::{stage:?} serde output '{serialized}' != as_str() '{expected}'"
            );

            // Also test deserialization round-trip
            let deserialized: PromotionStage = serde_json::from_str(&serialized).unwrap();
            assert_eq!(
                deserialized, stage,
                "PromotionStage::{stage:?} deserialization round-trip failed"
            );
        }
    }
}
