//! `src/zero/omega_test.rs`
//! Dedicated acceptance tests for the Machine God ground mode (omega).
//! Covers: `test_loopback_enforcement`, `test_language_detection`,
//! `test_fallback_on_down`.

use crate::zero::omega::*;

#[test]
fn test_loopback_enforcement() {
    // Literal loopback on any port is accepted.
    assert!(OmegaConfig::validate_loopback("http://127.0.0.1:8111/v1/chat/completions").is_ok());
    assert!(OmegaConfig::validate_loopback("http://127.0.0.1:1/v1/chat/completions").is_ok());
    assert!(OmegaConfig::validate_loopback("http://127.0.0.1:65535/v1/chat/completions").is_ok());

    // Host names are not literal loopback IPs and are rejected by the host-string rule.
    assert!(OmegaConfig::validate_loopback("http://localhost:8111/v1/chat/completions").is_err());

    // Non-loopback addresses are rejected.
    assert!(OmegaConfig::validate_loopback("http://192.168.1.1:8111/v1/chat/completions").is_err());
    assert!(OmegaConfig::validate_loopback("http://203.0.113.8:8111/v1/chat/completions").is_err());
    assert!(OmegaConfig::validate_loopback("http://0.0.0.0:8111/v1/chat/completions").is_err());

    // The env-derived endpoint always uses 127.0.0.1 regardless of the port.
    let ep = OmegaConfig::endpoint_from_env();
    assert!(ep.starts_with("http://127.0.0.1:"));
}

#[test]
fn test_language_detection() {
    assert_eq!(detect_language("Der Hund ist groß und läuft im Garten."), Lang::De);
    assert_eq!(detect_language("Die Katze sitzt auf der Matte."), Lang::De);
    assert_eq!(detect_language("The dog is big and runs in the garden."), Lang::En);
    assert_eq!(detect_language("The cat sits on the mat."), Lang::En);

    // Acceptance: greetings map to their language.
    assert_eq!(detect_language("Hallo"), Lang::De);
    assert_eq!(detect_language("Hello"), Lang::En);

    // No reliable signal -> UNKNOWN; never coerced to DE or EN.
    assert_eq!(detect_language("12345 !@#$"), Lang::Unknown);
    assert_eq!(detect_language(""), Lang::Unknown);

    // Tie -> UNKNOWN.
    assert_eq!(detect_language("in"), Lang::Unknown);
}

#[test]
fn test_fallback_on_down() {
    let port = OmegaConfig::port_from_env();
    let expected = format!("127.0.0.1:{port}");

    let de = fallback_sentence(Lang::De, port);
    assert!(de.contains("Maschine-Gott"));
    assert!(de.contains(&expected));
    assert!(!de.is_empty());

    let en = fallback_sentence(Lang::En, port);
    assert!(en.contains("Machine God"));
    assert!(en.contains(&expected));
    assert!(!en.is_empty());

    let unk = fallback_sentence(Lang::Unknown, port);
    assert!(unk.contains("Machine God"));
    assert!(unk.contains(&expected));
    assert!(!unk.is_empty());

    // fallback_reply returns an owned String with the same content.
    assert!(fallback_reply(Lang::De, port).contains("Maschine-Gott"));
    assert!(fallback_reply(Lang::En, port).contains("Machine God"));
}

#[test]
fn test_build_chat_request_shape() {
    let messages = vec![ChatMessage { role: "user".to_owned(), content: "Hallo".to_owned() }];
    let req = build_chat_request(&messages, "local-0.8b");
    let json = serde_json::to_string(&req).unwrap();
    let value: serde_json::Value = serde_json::from_str(&json).unwrap();
    assert_eq!(value["model"].as_str(), Some("local-0.8b"));
    assert_eq!(value["messages"][0]["role"].as_str(), Some("user"));
    assert_eq!(value["messages"][0]["content"].as_str(), Some("Hallo"));
    assert_eq!(value["temperature"].as_f64(), Some(0.7));
    assert_eq!(value["max_tokens"].as_u64(), Some(512));
    assert_eq!(value["stream"].as_bool(), Some(false));
}

#[test]
fn test_parse_reply() {
    let json = r#"{"choices":[{"message":{"role":"assistant","content":"Segne deine Frage."}}]}"#;
    assert_eq!(parse_reply(json).unwrap(), "Segne deine Frage.");
    assert!(parse_reply(r#"{"choices":[]}"#).is_err());
    assert!(parse_reply("not json").is_err());
}
