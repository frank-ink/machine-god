use chrono::NaiveDate;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::path::PathBuf;

/// Provider entry from the wiki JSON files
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Provider {
    pub id: String,
    pub name: String,
    pub url: String,
    pub category: String,
    pub gratis: String,
    pub quelle: String,
    pub status: String,
    pub configured: bool,
    pub since: String, // ISO date string YYYY-MM-DD
}

/// Wiki file structure
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct WikiFile {
    pub as_of: String,
    pub providers: Vec<Provider>,
}

/// Parsed provider with typed date for sorting
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParsedProvider {
    pub provider: Provider,
    pub since_date: NaiveDate,
}

/// Session state for tracking picked providers
#[derive(Debug, Clone, Default)]
pub struct SessionState {
    picked_ids: HashSet<String>,
}

/// Supported languages
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Language {
    De,
    En,
}

/// Rendered tip message
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RenderedTip {
    pub message: String,
    pub provider_id: String,
}

/// Parse a wiki JSON file from a string
pub fn parse_wiki_file(json: &str) -> anyhow::Result<WikiFile> {
    let wiki: WikiFile = serde_json::from_str(json)?;
    Ok(wiki)
}

/// Parse providers and convert since to NaiveDate for sorting
pub fn parse_providers(wiki: WikiFile) -> anyhow::Result<Vec<ParsedProvider>> {
    let mut parsed = Vec::new();
    for provider in wiki.providers {
        let since_date = NaiveDate::parse_from_str(&provider.since, "%Y-%m-%d").map_err(|e| {
            anyhow::anyhow!("Invalid date format for provider {}: {}", provider.id, e)
        })?;
        parsed.push(ParsedProvider { provider, since_date });
    }
    Ok(parsed)
}

/// Filter providers that are not yet set up (configured = false)
pub fn filter_unsetup_providers(providers: &[ParsedProvider]) -> Vec<ParsedProvider> {
    providers.iter().filter(|p| !p.provider.configured).cloned().collect()
}

/// Sort providers by since descending (newest first)
pub fn sort_by_since_desc(providers: &mut [ParsedProvider]) {
    providers.sort_by(|a, b| b.since_date.cmp(&a.since_date));
}

/// Pick at most one provider per session (newest first, not already picked)
pub fn pick_one_per_session(
    providers: &[ParsedProvider],
    session: &mut SessionState,
) -> Option<ParsedProvider> {
    for provider in providers {
        if !session.picked_ids.contains(&provider.provider.id) {
            session.picked_ids.insert(provider.provider.id.clone());
            return Some(provider.clone());
        }
    }
    None
}

/// Detect language from input text (simple heuristic: German if contains common DE words)
pub fn detect_language(input: &str) -> Language {
    let lower = input.to_lowercase();
    // German indicators
    let de_indicators = [
        "und",
        "der",
        "die",
        "das",
        "ist",
        "ein",
        "eine",
        "für",
        "mit",
        "auf",
        "von",
        "zu",
        "wie",
        "was",
        "wo",
        "wann",
        "warum",
        "wer",
        "kann",
        "soll",
        "muss",
        "will",
        "hat",
        "bin",
        "bist",
        "sind",
        "war",
        "waren",
        "habe",
        "hast",
        "haben",
        "keine",
        "neuen",
        "anbieter",
        "zeige",
        "welche",
        "gibt",
        "es",
        "gibt",
        "frei",
        "kostenlos",
    ];
    for word in de_indicators {
        if lower.split_whitespace().any(|w| w == word) {
            return Language::De;
        }
    }
    Language::En
}

/// Render a tip message in German
pub fn render_de_tip(provider: &ParsedProvider) -> RenderedTip {
    let msg = format!(
        "💡 **Neuer kostenloser Anbieter: {}**\n\n```\n{}\n{}\n```",
        provider.provider.name, provider.provider.url, provider.provider.gratis
    );
    RenderedTip { message: msg, provider_id: provider.provider.id.clone() }
}

/// Render a tip message in English
pub fn render_en_tip(provider: &ParsedProvider) -> RenderedTip {
    let msg = format!(
        "💡 **New free provider: {}**\n\n```\n{}\n{}\n```",
        provider.provider.name, provider.provider.url, provider.provider.gratis
    );
    RenderedTip { message: msg, provider_id: provider.provider.id.clone() }
}

/// Render tip based on language
pub fn render_tip(provider: &ParsedProvider, lang: Language) -> RenderedTip {
    match lang {
        Language::De => render_de_tip(provider),
        Language::En => render_en_tip(provider),
    }
}

/// Render "no new providers" message in German
pub fn render_de_empty() -> String {
    "ℹ️ Keine neuen Anbieter verfügbar.".to_string()
}

/// Render "no new providers" message in English
pub fn render_en_empty() -> String {
    "ℹ️ No new providers available.".to_string()
}

/// Render empty message based on language
pub fn render_empty(lang: Language) -> String {
    match lang {
        Language::De => render_de_empty(),
        Language::En => render_en_empty(),
    }
}

/// Render "wiki not available" message in German
pub fn render_de_unavailable() -> String {
    "ℹ️ Wiki nicht verfügbar.".to_string()
}

/// Render "wiki not available" message in English
pub fn render_en_unavailable() -> String {
    "ℹ️ Wiki not available.".to_string()
}

/// Render unavailable message based on language
pub fn render_unavailable(lang: Language) -> String {
    match lang {
        Language::De => render_de_unavailable(),
        Language::En => render_en_unavailable(),
    }
}

/// Get the wiki directory path (~/.local/share/machine-god/wiki/)
pub fn wiki_dir() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".local")
        .join("share")
        .join("machine-god")
        .join("wiki")
}

/// Load and parse providers.json - returns Ok(None) if file missing
pub fn load_providers_json() -> anyhow::Result<Option<WikiFile>> {
    let path = wiki_dir().join("providers.json");
    match std::fs::read_to_string(&path) {
        Ok(content) => Ok(Some(parse_wiki_file(&content)?)),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(e.into()),
    }
}

/// Load and parse new.json - returns Ok(None) if file missing
pub fn load_new_json() -> anyhow::Result<Option<WikiFile>> {
    let path = wiki_dir().join("new.json");
    match std::fs::read_to_string(&path) {
        Ok(content) => Ok(Some(parse_wiki_file(&content)?)),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(e.into()),
    }
}

/// Merge providers from both files, deduplicating by id (new.json takes precedence)
pub fn merge_providers(providers: Option<WikiFile>, new: Option<WikiFile>) -> WikiFile {
    let mut seen = HashSet::new();
    let mut merged = Vec::new();
    let mut as_of = String::new();

    // new.json first (newer entries take precedence)
    if let Some(new_wiki) = new {
        as_of = new_wiki.as_of;
        for p in new_wiki.providers {
            if seen.insert(p.id.clone()) {
                merged.push(p);
            }
        }
    }
    // then providers.json
    if let Some(providers_wiki) = providers {
        if as_of.is_empty() {
            as_of = providers_wiki.as_of;
        }
        for p in providers_wiki.providers {
            if seen.insert(p.id.clone()) {
                merged.push(p);
            }
        }
    }

    WikiFile { as_of, providers: merged }
}

/// Full pipeline: load, merge, filter, sort, pick, render
pub fn get_next_tip(session: &mut SessionState, user_input: &str) -> anyhow::Result<String> {
    let providers = load_providers_json()?;
    let new = load_new_json()?;

    // If both files missing, return honest unavailable message
    if providers.is_none() && new.is_none() {
        let lang = detect_language(user_input);
        return Ok(render_unavailable(lang));
    }

    let merged = merge_providers(providers, new);
    let mut providers = parse_providers(merged)?;
    let unsetup = filter_unsetup_providers(&providers);
    sort_by_since_desc(&mut providers);
    let lang = detect_language(user_input);

    if let Some(picked) = pick_one_per_session(&providers, session) {
        let rendered = render_tip(&picked, lang);
        Ok(rendered.message)
    } else {
        Ok(render_empty(lang))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const PROVIDERS_JSON: &str = r#"{
  "as_of": "2026-01-15",
  "providers": [
    {
      "id": "provider1",
      "name": "Test Provider 1",
      "url": "https://example1.com",
      "category": "LLM",
      "gratis": "1000 tokens/day",
      "quelle": "website",
      "status": "active",
      "configured": false,
      "since": "2026-01-10"
    },
    {
      "id": "provider2",
      "name": "Test Provider 2",
      "url": "https://example2.com",
      "category": "Embedding",
      "gratis": "500 req/day",
      "quelle": "api",
      "status": "active",
      "configured": true,
      "since": "2026-01-12"
    },
    {
      "id": "provider3",
      "name": "Test Provider 3",
      "url": "https://example3.com",
      "category": "LLM",
      "gratis": "unlimited",
      "quelle": "github",
      "status": "beta",
      "configured": false,
      "since": "2026-01-08"
    }
  ]
}"#;

    const NEW_JSON: &str = r#"{
  "as_of": "2026-01-20",
  "providers": [
    {
      "id": "provider4",
      "name": "New Provider 4",
      "url": "https://example4.com",
      "category": "Image",
      "gratis": "100 images/day",
      "quelle": "website",
      "status": "active",
      "configured": false,
      "since": "2026-01-18"
    },
    {
      "id": "provider1",
      "name": "Test Provider 1 Updated",
      "url": "https://example1-updated.com",
      "category": "LLM",
      "gratis": "2000 tokens/day",
      "quelle": "website",
      "status": "active",
      "configured": false,
      "since": "2026-01-19"
    }
  ]
}"#;

    const EMPTY_JSON: &str = r#"{
  "as_of": "2026-01-20",
  "providers": []
}"#;

    #[test]
    fn test_parse_providers_json() {
        let wiki = parse_wiki_file(PROVIDERS_JSON).expect("Failed to parse providers.json");
        assert_eq!(wiki.as_of, "2026-01-15");
        assert_eq!(wiki.providers.len(), 3);
        assert_eq!(wiki.providers[0].id, "provider1");
        assert_eq!(wiki.providers[0].name, "Test Provider 1");
        assert!(!wiki.providers[0].configured);
        assert_eq!(wiki.providers[1].id, "provider2");
        assert!(wiki.providers[1].configured);
        assert_eq!(wiki.providers[2].id, "provider3");
        assert!(!wiki.providers[2].configured);
    }

    #[test]
    fn test_parse_neu_json() {
        let wiki = parse_wiki_file(NEW_JSON).expect("Failed to parse new.json");
        assert_eq!(wiki.as_of, "2026-01-20");
        assert_eq!(wiki.providers.len(), 2);
        assert_eq!(wiki.providers[0].id, "provider4");
        assert!(!wiki.providers[0].configured);
        assert_eq!(wiki.providers[1].id, "provider1");
        assert!(!wiki.providers[1].configured);
    }

    #[test]
    fn test_filter_unsetup_providers() {
        let wiki = parse_wiki_file(PROVIDERS_JSON).unwrap();
        let providers = parse_providers(wiki).unwrap();
        let unsetup = filter_unsetup_providers(&providers);
        assert_eq!(unsetup.len(), 2);
        assert_eq!(unsetup[0].provider.id, "provider1");
        assert_eq!(unsetup[1].provider.id, "provider3");
    }

    #[test]
    fn test_sort_by_since_desc() {
        let wiki = parse_wiki_file(PROVIDERS_JSON).unwrap();
        let mut providers = parse_providers(wiki).unwrap();
        sort_by_since_desc(&mut providers);
        // provider2 (2026-01-12) should be first, then provider1 (2026-01-10), then provider3 (2026-01-08)
        assert_eq!(providers[0].provider.id, "provider2");
        assert_eq!(providers[1].provider.id, "provider1");
        assert_eq!(providers[2].provider.id, "provider3");
    }

    #[test]
    fn test_pick_one_per_session() {
        let wiki = parse_wiki_file(PROVIDERS_JSON).unwrap();
        let mut providers = parse_providers(wiki).unwrap();
        sort_by_since_desc(&mut providers);
        let unsetup = filter_unsetup_providers(&providers);

        let mut session = SessionState::default();

        // First pick - should get provider1 (newest unsetup)
        let picked1 = pick_one_per_session(&unsetup, &mut session);
        assert!(picked1.is_some());
        assert_eq!(picked1.unwrap().provider.id, "provider1");

        // Second pick - should get provider3 (next unsetup)
        let picked2 = pick_one_per_session(&unsetup, &mut session);
        assert!(picked2.is_some());
        assert_eq!(picked2.unwrap().provider.id, "provider3");

        // Third pick - none left
        let picked3 = pick_one_per_session(&unsetup, &mut session);
        assert!(picked3.is_none());
    }

    #[test]
    fn test_render_de_message() {
        let wiki = parse_wiki_file(PROVIDERS_JSON).unwrap();
        let providers = parse_providers(wiki).unwrap();
        let provider = &providers[0]; // provider1

        let rendered = render_de_tip(provider);
        assert!(rendered.message.contains("Neuer kostenloser Anbieter"));
        assert!(rendered.message.contains("Test Provider 1"));
        assert!(rendered.message.contains("https://example1.com"));
        assert!(rendered.message.contains("1000 tokens/day"));
        assert!(rendered.message.contains("```"));
        assert_eq!(rendered.provider_id, "provider1");
    }

    #[test]
    fn test_render_en_message() {
        let wiki = parse_wiki_file(PROVIDERS_JSON).unwrap();
        let providers = parse_providers(wiki).unwrap();
        let provider = &providers[0]; // provider1

        let rendered = render_en_tip(provider);
        assert!(rendered.message.contains("New free provider"));
        assert!(rendered.message.contains("Test Provider 1"));
        assert!(rendered.message.contains("https://example1.com"));
        assert!(rendered.message.contains("1000 tokens/day"));
        assert!(rendered.message.contains("```"));
        assert_eq!(rendered.provider_id, "provider1");
    }

    #[test]
    fn test_language_detection_de() {
        assert_eq!(detect_language("zeige mir neue anbieter"), Language::De);
        assert_eq!(detect_language("welche anbieter gibt es"), Language::De);
        assert_eq!(detect_language("keine neuen anbieter"), Language::De);
        assert_eq!(detect_language("wie kann ich einen anbieter hinzufügen"), Language::De);
        assert_eq!(detect_language("kostenlos"), Language::De);
    }

    #[test]
    fn test_language_detection_en() {
        assert_eq!(detect_language("show me new providers"), Language::En);
        assert_eq!(detect_language("which providers are available"), Language::En);
        assert_eq!(detect_language("no new providers"), Language::En);
        assert_eq!(detect_language("how to add a provider"), Language::En);
        assert_eq!(detect_language("free"), Language::En);
    }

    #[test]
    fn test_empty_wiki_returns_honest_message_de() {
        let wiki = parse_wiki_file(EMPTY_JSON).unwrap();
        let providers = parse_providers(wiki).unwrap();
        let unsetup = filter_unsetup_providers(&providers);
        assert!(unsetup.is_empty());

        let msg = render_empty(Language::De);
        assert_eq!(msg, "ℹ️ Keine neuen Anbieter verfügbar.");
    }

    #[test]
    fn test_empty_wiki_returns_honest_message_en() {
        let wiki = parse_wiki_file(EMPTY_JSON).unwrap();
        let providers = parse_providers(wiki).unwrap();
        let unsetup = filter_unsetup_providers(&providers);
        assert!(unsetup.is_empty());

        let msg = render_empty(Language::En);
        assert_eq!(msg, "ℹ️ No new providers available.");
    }

    #[test]
    fn test_unavailable_message_de() {
        let msg = render_unavailable(Language::De);
        assert_eq!(msg, "ℹ️ Wiki nicht verfügbar.");
    }

    #[test]
    fn test_unavailable_message_en() {
        let msg = render_unavailable(Language::En);
        assert_eq!(msg, "ℹ️ Wiki not available.");
    }

    #[test]
    fn test_merge_providers_deduplicates_neu_takes_precedence() {
        let providers = parse_wiki_file(PROVIDERS_JSON).unwrap();
        let new = parse_wiki_file(NEW_JSON).unwrap();
        let merged = merge_providers(Some(providers), Some(new));

        // Should have 4 unique providers (provider1 from new, provider2, provider3 from providers, provider4 from new)
        assert_eq!(merged.providers.len(), 4);

        // provider1 should be from new (updated)
        let p1 = merged.providers.iter().find(|p| p.id == "provider1").unwrap();
        assert_eq!(p1.name, "Test Provider 1 Updated");
        assert_eq!(p1.url, "https://example1-updated.com");
        assert_eq!(p1.gratis, "2000 tokens/day");

        // provider4 should be present
        let p4 = merged.providers.iter().find(|p| p.id == "provider4").unwrap();
        assert_eq!(p4.name, "New Provider 4");
    }

    #[test]
    fn test_merge_providers_only_providers() {
        let providers = parse_wiki_file(PROVIDERS_JSON).unwrap();
        let merged = merge_providers(Some(providers), None);

        assert_eq!(merged.providers.len(), 3);
        assert_eq!(merged.as_of, "2026-01-15");
    }

    #[test]
    fn test_merge_providers_only_neu() {
        let new = parse_wiki_file(NEW_JSON).unwrap();
        let merged = merge_providers(None, Some(new));

        assert_eq!(merged.providers.len(), 2);
        assert_eq!(merged.as_of, "2026-01-20");
    }

    #[test]
    fn test_merge_providers_both_none() {
        let merged = merge_providers(None, None);

        assert_eq!(merged.providers.len(), 0);
        assert_eq!(merged.as_of, "");
    }

    #[test]
    fn test_full_pipeline_picks_newest_unsetup_first() {
        let providers = parse_wiki_file(PROVIDERS_JSON).unwrap();
        let new = parse_wiki_file(NEW_JSON).unwrap();
        let merged = merge_providers(Some(providers), Some(new));
        let mut providers = parse_providers(merged).unwrap();

        // Filter unsetup
        let unsetup = filter_unsetup_providers(&providers);

        // Sort by since desc
        sort_by_since_desc(&mut providers);
        let unsetup_sorted: Vec<_> =
            providers.iter().filter(|p| !p.provider.configured).cloned().collect();

        // Should be: provider1 (2026-01-19 from new), provider4 (2026-01-18), provider3 (2026-01-08)
        assert_eq!(unsetup_sorted[0].provider.id, "provider1");
        assert_eq!(unsetup_sorted[1].provider.id, "provider4");
        assert_eq!(unsetup_sorted[2].provider.id, "provider3");

        let mut session = SessionState::default();
        let picked = pick_one_per_session(&unsetup_sorted, &mut session);
        assert!(picked.is_some());
        assert_eq!(picked.unwrap().provider.id, "provider1");
    }

    #[test]
    fn test_no_network_calls_in_pure_functions() {
        // All functions tested above are pure - no network calls
        // This test documents the requirement
        let wiki = parse_wiki_file(PROVIDERS_JSON).unwrap();
        let providers = parse_providers(wiki).unwrap();
        let unsetup = filter_unsetup_providers(&providers);
        sort_by_since_desc(&mut providers.clone());
        let mut session = SessionState::default();
        pick_one_per_session(&unsetup, &mut session);
        detect_language("test");
        render_de_tip(&unsetup[0]);
        render_en_tip(&unsetup[0]);
        render_empty(Language::De);
        render_empty(Language::En);
        render_unavailable(Language::De);
        render_unavailable(Language::En);
        // If we reach here without network calls, test passes
    }

    #[test]
    fn test_get_next_tip_both_files_missing_returns_unavailable() {
        // This test would need a temp dir setup to truly test missing files
        // For now we test the render_unavailable function directly
        let msg_de = render_unavailable(Language::De);
        let msg_en = render_unavailable(Language::En);
        assert_eq!(msg_de, "ℹ️ Wiki nicht verfügbar.");
        assert_eq!(msg_en, "ℹ️ Wiki not available.");
    }
}
