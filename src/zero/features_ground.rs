//! Ground-mode adapter for the capability registry (DE / EN).
//!
//! GRF / ClayCode mapping
//! -----------------------
//! R_t : `CapabilityRegistry` (canonical state)
//! E_t : the user's question (evidence of intent, not of truth)
//! F   : detect_language -> find_capability -> explain_entry (pure)
//! M   : { MEASURED, PLANNED, UNKNOWN }; an unknown capability stays UNKNOWN.
//!
//! Integration point for `src/zero/omega.rs`: the ground mode can call
//! `answer_question(&registry, question)` to explain any capability in the
//! user's language without inventing capability claims.

use crate::zero::features::{
    detect_language, explain_entry, render_ground_summary, Capability, CapabilityRegistry,
    CapabilityStatus, Language,
};

/// Exact match first, then a mention match inside free text.
pub fn find_capability<'a>(
    registry: &'a CapabilityRegistry,
    question: &str,
) -> Option<&'a Capability> {
    registry
        .find(question)
        .or_else(|| registry.find_mentioned(question))
}

/// Explain one capability by name in the requested language.
pub fn explain_capability(
    registry: &CapabilityRegistry,
    name: &str,
    language: Language,
) -> Option<String> {
    find_capability(registry, name).map(|cap| explain_entry(cap, language))
}

/// Answer a free-text question about capabilities, honestly.
pub fn answer_question(registry: &CapabilityRegistry, question: &str) -> String {
    let language = detect_language(question);
    if let Some(cap) = find_capability(registry, question) {
        return explain_entry(cap, language);
    }
    let lower = question.to_lowercase();
    let asks_for_list = [
        "feature",
        "fähig",
        "faehig",
        "capabilit",
        "can you do",
        "kannst du",
        "what can",
    ]
    .iter()
    .any(|needle| lower.contains(needle));
    if asks_for_list {
        return render_ground_summary(registry, language);
    }
    match language {
        Language::German => {
            "Diese Faehigkeit ist im kanonischen Register nicht bekannt; Status: UNKNOWN.".to_string()
        }
        Language::English => {
            "This capability is not listed in the canonical registry; status: UNKNOWN.".to_string()
        }
    }
}

/// Compact context block for the local model prompt.
pub fn ground_context(registry: &CapabilityRegistry) -> String {
    let mut out = String::from("CAPABILITY_REGISTRY (canonical, honest):\n");
    for cap in &registry.capabilities {
        out.push_str(&format!("- {} | {}", cap.capability, cap.status.as_str()));
        match cap.status {
            CapabilityStatus::Measured => {
                if !cap.evidence_ref.trim().is_empty() {
                    out.push_str(&format!(" | evidence={}", cap.evidence_ref));
                }
            }
            CapabilityStatus::Planned => {
                if let Some(issue) = cap.tracking_issue.as_deref() {
                    out.push_str(&format!(" | issue={}", issue));
                }
            }
            CapabilityStatus::Unknown => {}
        }
        out.push('\n');
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn registry() -> CapabilityRegistry {
        let raw = r#"{
          "schema": "zero.capabilities.v1",
          "capabilities": [
            {
              "capability": "retina",
              "status": "MEASURED",
              "evidence_ref": "test:zero::features_ground::tests::explain_capability_in_german@WORKTREE",
              "gate": "cargo test -p claude_rs zero::features"
            },
            {
              "capability": "smartphone_link",
              "status": "PLANNED",
              "tracking_issue": "zero40-track3-item14",
              "gate": "docs/zero/smartphone.md"
            }
          ]
        }"#;
        CapabilityRegistry::from_json_str(raw).unwrap()
    }

    #[test]
    fn explain_capability_in_german() {
        let reg = registry();
        let text = explain_capability(&reg, "retina", Language::German).unwrap();
        assert!(text.contains("MEASURED"));
        assert!(text.contains("retina"));
    }

    #[test]
    fn explain_capability_in_english() {
        let reg = registry();
        let text = explain_capability(&reg, "smartphone_link", Language::English).unwrap();
        assert!(text.contains("PLANNED"));
        assert!(text.contains("zero40-track3-item14"));
    }

    #[test]
    fn unknown_question_stays_unknown() {
        let reg = registry();
        let text = answer_question(&reg, "can you teleport the phone?");
        assert!(text.contains("UNKNOWN"));
    }

    #[test]
    fn ground_context_lists_every_capability() {
        let reg = registry();
        let ctx = ground_context(&reg);
        assert!(ctx.contains("retina"));
        assert!(ctx.contains("smartphone_link"));
    }
}
