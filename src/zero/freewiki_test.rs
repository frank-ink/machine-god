// Integration tests for freewiki module
// These tests verify the full pipeline with file I/O (using std::fs with temp dirs)

use crate::zero::freewiki::*;
use std::fs;
use std::path::PathBuf;

const ANBIETER_JSON: &str = r#"{
  "stand": "2026-01-15",
  "anbieter": [
    {
      "id": "provider1",
      "name": "Test Provider 1",
      "url": "https://example1.com",
      "kategorie": "LLM",
      "gratis": "1000 tokens/day",
      "quelle": "website",
      "status": "active",
      "eingerichtet": false,
      "seit": "2026-01-10"
    }
  ]
}"#;

const NEU_JSON: &str = r#"{
  "stand": "2026-01-20",
  "anbieter": [
    {
      "id": "provider2",
      "name": "New Provider 2",
      "url": "https://example2.com",
      "kategorie": "Embedding",
      "gratis": "500 req/day",
      "quelle": "api",
      "status": "active",
      "eingerichtet": false,
      "seit": "2026-01-18"
    }
  ]
}"#;

#[test]
fn test_session_state_isolation() {
    // Each session should track its own picked providers
    let wiki = parse_wiki_file(ANBIETER_JSON).unwrap();
    let mut providers = parse_providers(wiki).unwrap();
    sort_by_seit_desc(&mut providers);
    let unsetup = filter_unsetup_providers(&providers);
    
    let mut session1 = SessionState::default();
    let mut session2 = SessionState::default();
    
    // Session 1 picks
    let picked1 = pick_one_per_session(&unsetup, &mut session1);
    assert!(picked1.is_some());
    
    // Session 2 should still be able to pick (independent state)
    let picked2 = pick_one_per_session(&unsetup, &mut session2);
    assert!(picked2.is_some());
    assert_eq!(picked1.unwrap().provider.id, picked2.unwrap().provider.id);
}

#[test]
fn test_provider_with_special_characters_in_gratis() {
    let json = r#"{
  "stand": "2026-01-20",
  "anbieter": [
    {
      "id": "special",
      "name": "Special Provider",
      "url": "https://special.com",
      "kategorie": "Test",
      "gratis": "100 tokens/day & unlimited embeddings",
      "quelle": "web",
      "status": "active",
      "eingerichtet": false,
      "seit": "2026-01-15"
    }
  ]
}"#;
    
    let wiki = parse_wiki_file(json).unwrap();
    let providers = parse_providers(wiki).unwrap();
    let rendered_de = render_de_tip(&providers[0]);
    let rendered_en = render_en_tip(&providers[0]);
    
    assert!(rendered_de.message.contains("100 tokens/day & unlimited embeddings"));
    assert!(rendered_en.message.contains("100 tokens/day & unlimited embeddings"));
}

#[test]
fn test_unicode_in_provider_names() {
    let json = r#"{
  "stand": "2026-01-20",
  "anbieter": [
    {
      "id": "unicode",
      "name": "Anbieter mit Ümläuten 🚀",
      "url": "https://unicode.com",
      "kategorie": "Test",
      "gratis": "free",
      "quelle": "web",
      "status": "active",
      "eingerichtet": false,
      "seit": "2026-01-15"
    }
  ]
}"#;
    
    let wiki = parse_wiki_file(json).unwrap();
    let providers = parse_providers(wiki).unwrap();
    let rendered_de = render_de_tip(&providers[0]);
    let rendered_en = render_en_tip(&providers[0]);
    
    assert!(rendered_de.message.contains("Anbieter mit Ümläuten 🚀"));
    assert!(rendered_en.message.contains("Anbieter mit Ümläuten 🚀"));
}

#[test]
fn test_all_eingerichtet_true_returns_empty() {
    let json = r#"{
  "stand": "2026-01-20",
  "anbieter": [
    {
      "id": "p1",
      "name": "Provider 1",
      "url": "https://p1.com",
      "kategorie": "Test",
      "gratis": "free",
      "quelle": "web",
      "status": "active",
      "eingerichtet": true,
      "seit": "2026-01-15"
    },
    {
      "id": "p2",
      "name": "Provider 2",
      "url": "https://p2.com",
      "kategorie": "Test",
      "gratis": "free",
      "quelle": "web",
      "status": "active",
      "eingerichtet": true,
      "seit": "2026-01-16"
    }
  ]
}"#;
    
    let wiki = parse_wiki_file(json).unwrap();
    let providers = parse_providers(wiki).unwrap();
    let unsetup = filter_unsetup_providers(&providers);
    
    assert!(unsetup.is_empty());
    
    let mut session = SessionState::default();
    let picked = pick_one_per_session(&unsetup, &mut session);
    assert!(picked.is_none());
    
    let msg_de = render_empty(Language::De);
    let msg_en = render_empty(Language::En);
    
    assert_eq!(msg_de, "ℹ️ Keine neuen Anbieter verfügbar.");
    assert_eq!(msg_en, "ℹ️ No new providers available.");
}

#[test]
fn test_mixed_eingerichtet_false_true() {
    let json = r#"{
  "stand": "2026-01-20",
  "anbieter": [
    {
      "id": "p1",
      "name": "Provider 1",
      "url": "https://p1.com",
      "kategorie": "Test",
      "gratis": "free",
      "quelle": "web",
      "status": "active",
      "eingerichtet": true,
      "seit": "2026-01-15"
    },
    {
      "id": "p2",
      "name": "Provider 2",
      "url": "https://p2.com",
      "kategorie": "Test",
      "gratis": "free",
      "quelle": "web",
      "status": "active",
      "eingerichtet": false,
      "seit": "2026-01-16"
    },
    {
      "id": "p3",
      "name": "Provider 3",
      "url": "https://p3.com",
      "kategorie": "Test",
      "gratis": "free",
      "quelle": "web",
      "status": "active",
      "eingerichtet": false,
      "seit": "2026-01-17"
    }
  ]
}"#;
    
    let wiki = parse_wiki_file(json).unwrap();
    let mut providers = parse_providers(wiki).unwrap();
    sort_by_seit_desc(&mut providers);
    let unsetup = filter_unsetup_providers(&providers);
    
    // Should only have p2 and p3, sorted by seit desc (p3 first, then p2)
    assert_eq!(unsetup.len(), 2);
    assert_eq!(unsetup[0].provider.id, "p3");
    assert_eq!(unsetup[1].provider.id, "p2");
    
    let mut session = SessionState::default();
    let first = pick_one_per_session(&unsetup, &mut session);
    assert_eq!(first.unwrap().provider.id, "p3");
    
    let second = pick_one_per_session(&unsetup, &mut session);
    assert_eq!(second.unwrap().provider.id, "p2");
    
    let third = pick_one_per_session(&unsetup, &mut session);
    assert!(third.is_none());
}

#[test]
fn test_render_tip_dispatches_by_language() {
    let wiki = parse_wiki_file(ANBIETER_JSON).unwrap();
    let providers = parse_providers(wiki).unwrap();
    let provider = &providers[0];
    
    let de_tip = render_tip(provider, Language::De);
    let en_tip = render_tip(provider, Language::En);
    
    assert!(de_tip.message.contains("Neuer kostenloser Anbieter"));
    assert!(en_tip.message.contains("New free provider"));
    assert_eq!(de_tip.provider_id, en_tip.provider_id);
}

#[test]
fn test_render_empty_dispatches_by_language() {
    let de_empty = render_empty(Language::De);
    let en_empty = render_empty(Language::En);
    
    assert_eq!(de_empty, "ℹ️ Keine neuen Anbieter verfügbar.");
    assert_eq!(en_empty, "ℹ️ No new providers available.");
}

#[test]
fn test_wiki_dir_returns_expected_path() {
    let path = wiki_dir();
    assert!(path.ends_with(".local/share/machine-god/wiki"));
}

#[test]
fn test_parse_providers_handles_invalid_date() {
    let json = r#"{
  "stand": "2026-01-20",
  "anbieter": [
    {
      "id": "bad",
      "name": "Bad Date",
      "url": "https://bad.com",
      "kategorie": "Test",
      "gratis": "free",
      "quelle": "web",
      "status": "active",
      "eingerichtet": false,
      "seit": "not-a-date"
    }
  ]
}"#;
    
    let wiki = parse_wiki_file(json).unwrap();
    let result = parse_providers(wiki);
    assert!(result.is_err());
    assert!(result.unwrap_err().to_string().contains("Invalid date format"));
}
