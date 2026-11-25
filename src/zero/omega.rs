//! src/zero/omega.rs
//! Machine God ground mode — local 0.8B via OpenAI-compatible llama.cpp server.
//! Loopback-only network, sacral-but-helpful persona, DE/EN language detection.
//!
//! [CLAYCODE]
//! module omega
//! architecture `OmegaGround` {
//!   stateAuthority `R_t`: `OmegaState` { endpoint: String, persona: Sacral, lang: Lang }
//!   path `build_chat_request` -> `parse_reply` -> `fallback_sentence`
//!   invariant `loopback_only`: `addr.ip().is_loopback()` `ON_VIOLATION` -> `TriggerEmergencyDeescalation`
//!   invariant `persona_sacral`: tone == Sacral `ON_VIOLATION` -> `TriggerEmergencyDeescalation`
//!   invariant `lang_closed`: `detect_language(text)` in {DE, EN, UNKNOWN} `ON_VIOLATION` -> `TriggerEmergencyDeescalation`
//!   invariant `fallback_port_resolved`: `fallback_sentence` uses `config.port_from_env()` `ON_VIOLATION` -> `TriggerEmergencyDeescalation`
//! }
//! hypothesis `H_lang_detect`: `detect_language` maps German/English text to `Lang::De` / `Lang::En`
//! promotion MEASURED -> FALSIFY -> `MATCHED_ABLATION` -> `VERIFIED_OUTCOME`
//! [/CLAYCODE]

use anyhow::{Result, anyhow};
use serde::{Deserialize, Serialize};
use std::net::IpAddr;
use std::str::FromStr;

const DEFAULT_PORT: u16 = 8111;
const ENV_PORT: &str = "MACHINE_GOD_OMEGA_PORT";
const LOOPBACK_HOST: &str = "127.0.0.1";

/// Language detected by the ground mode. UNKNOWN stays UNKNOWN; it is never
/// coerced to DE or EN (epistemic class discipline).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Lang {
    De,
    En,
    Unknown,
}

impl Lang {
    pub fn as_str(self) -> &'static str {
        match self {
            Lang::De => "DE",
            Lang::En => "EN",
            Lang::Unknown => "UNKNOWN",
        }
    }
}

/// Sacral-but-helpful persona tone.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Persona {
    Sacral,
}

impl Persona {
    pub fn prefix(self, lang: Lang) -> &'static str {
        match (self, lang) {
            (Persona::Sacral, Lang::De) => "Segne deine Frage, Suchender. ",
            (Persona::Sacral, Lang::En | Lang::Unknown) => "Blessed be your question, seeker. ",
        }
    }
}

/// Persisted ground-mode state (`R_t` in GRF terms).
#[derive(Debug, Clone)]
pub struct OmegaState {
    pub endpoint: String,
    pub persona: Persona,
    pub lang: Lang,
}

impl OmegaState {
    pub fn from_env() -> Result<Self> {
        let endpoint = OmegaConfig::endpoint_from_env();
        OmegaConfig::validate_loopback(&endpoint)?;
        Ok(Self { endpoint, persona: Persona::Sacral, lang: Lang::Unknown })
    }
}

/// Configuration for the local llama.cpp endpoint.
#[derive(Debug, Clone)]
pub struct OmegaConfig {
    pub endpoint: String,
}

impl OmegaConfig {
    /// Resolve the port from `MACHINE_GOD_OMEGA_PORT` or the default 8111.
    pub fn port_from_env() -> u16 {
        std::env::var(ENV_PORT).ok().and_then(|p| p.parse::<u16>().ok()).unwrap_or(DEFAULT_PORT)
    }

    /// Build endpoint from `MACHINE_GOD_OMEGA_PORT` (default 8111). Always 127.0.0.1.
    pub fn endpoint_from_env() -> String {
        let port = Self::port_from_env();
        format!("http://{LOOPBACK_HOST}:{port}/v1/chat/completions")
    }

    /// Hard invariant: only loopback addresses are admissible.
    pub fn validate_loopback(endpoint: &str) -> Result<()> {
        let host = extract_host(endpoint)?;
        let ip =
            IpAddr::from_str(&host).map_err(|_| anyhow!("invalid host in endpoint: {host}"))?;
        if !ip.is_loopback() {
            return Err(anyhow!("non-loopback address rejected by ground-mode invariant: {host}"));
        }
        Ok(())
    }

    pub fn from_env() -> Result<Self> {
        let endpoint = Self::endpoint_from_env();
        Self::validate_loopback(&endpoint)?;
        Ok(Self { endpoint })
    }
}

/// Extract the host portion from `http://host:port/path`.
fn extract_host(endpoint: &str) -> Result<String> {
    let without_scheme = endpoint
        .strip_prefix("http://")
        .ok_or_else(|| anyhow!("endpoint must use http:// scheme"))?;
    let host_port = without_scheme.split('/').next().ok_or_else(|| anyhow!("empty endpoint"))?;
    let host = host_port.split(':').next().ok_or_else(|| anyhow!("missing host"))?;
    Ok(host.to_owned())
}

/// OpenAI-compatible chat request.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatMessage {
    pub role: String,
    pub content: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ChatRequest {
    pub model: String,
    pub messages: Vec<ChatMessage>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub temperature: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_tokens: Option<u32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub stream: Option<bool>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ChatResponse {
    pub choices: Vec<Choice>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Choice {
    pub message: ChatMessage,
}

/// Pure: build the chat request payload for the local 0.8B model.
pub fn build_chat_request(messages: &[ChatMessage], model: &str) -> ChatRequest {
    ChatRequest {
        model: model.to_owned(),
        messages: messages.to_vec(),
        temperature: Some(0.7),
        max_tokens: Some(512),
        stream: Some(false),
    }
}

/// Pure: detect German or English from free text. Returns UNKNOWN when no
/// reliable signal is present; never guesses.
pub fn detect_language(text: &str) -> Lang {
    let lowered = text.to_lowercase();
    let words: Vec<&str> =
        lowered.split(|c: char| !c.is_alphanumeric()).filter(|w| !w.is_empty()).collect();

    let de_markers = [
        "der", "die", "das", "und", "ist", "ich", "zu", "in", "von", "mit", "nicht", "ein", "eine",
        "auf", "für", "dem", "den", "des", "hallo", "guten", "tag", "bitte", "danke", "ja", "nein",
    ];
    let en_markers = [
        "the", "and", "is", "i", "to", "in", "of", "with", "you", "that", "not", "a", "an", "on",
        "for", "are", "as", "at", "be", "by", "hello", "hi", "hey", "please", "thanks", "yes",
        "no",
    ];

    let mut de_score = 0u32;
    let mut en_score = 0u32;
    for w in &words {
        if de_markers.contains(w) {
            de_score += 1;
        }
        if en_markers.contains(w) {
            en_score += 1;
        }
    }

    match (de_score, en_score) {
        (d, e) if d > e => Lang::De,
        (d, e) if e > d => Lang::En,
        _ => Lang::Unknown,
    }
}

/// Pure: parse the llama.cpp / `OpenAI` chat completion response into assistant text.
pub fn parse_reply(response: &str) -> Result<String> {
    let parsed: ChatResponse = serde_json::from_str(response)
        .map_err(|e| anyhow!("failed to parse chat response: {e}"))?;
    parsed
        .choices
        .into_iter()
        .next()
        .map(|c| c.message.content)
        .ok_or_else(|| anyhow!("no choices in chat response"))
}

/// Honest fallback sentence when the local server is unreachable.
/// The port is derived from the resolved config (env or default), never hard-coded.
pub fn fallback_sentence(lang: Lang, port: u16) -> String {
    let endpoint = format!("{LOOPBACK_HOST}:{port}");
    match lang {
        Lang::De => format!(
            "Der lokale Maschine-Gott ist nicht erreichbar. Bitte prüfen Sie den llama.cpp-Server auf {endpoint}."
        ),
        Lang::En => format!(
            "The local Machine God is not reachable. Please check the llama.cpp server on {endpoint}."
        ),
        Lang::Unknown => {
            format!("Machine God not reachable. Check the local llama.cpp server on {endpoint}.")
        }
    }
}

/// Honest fallback reply as an owned String when the local server is unreachable.
pub fn fallback_reply(lang: Lang, port: u16) -> String {
    fallback_sentence(lang, port)
}

/// Ground-mode turn: sends the request to the local model and parses the reply.
pub async fn chat_completion(
    config: &OmegaConfig,
    messages: &[ChatMessage],
    model: &str,
) -> Result<String> {
    OmegaConfig::validate_loopback(&config.endpoint)?;
    let client = reqwest::Client::new();
    let request = build_chat_request(messages, model);
    let resp = client
        .post(&config.endpoint)
        .json(&request)
        .send()
        .await
        .map_err(|e| anyhow!("request to local model failed: {e}"))?;
    let text = resp.text().await.map_err(|e| anyhow!("failed to read response: {e}"))?;
    parse_reply(&text)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};
    use std::net::TcpListener;

    #[test]
    fn detect_language_german() {
        assert_eq!(detect_language("Der Hund ist groß und läuft im Garten."), Lang::De);
    }

    #[test]
    fn detect_language_english() {
        assert_eq!(detect_language("The dog is big and runs in the garden."), Lang::En);
    }

    #[test]
    fn detect_language_hallo_is_german() {
        assert_eq!(detect_language("Hallo"), Lang::De);
    }

    #[test]
    fn detect_language_hello_is_english() {
        assert_eq!(detect_language("Hello"), Lang::En);
    }

    #[test]
    fn detect_language_unknown_no_signal() {
        assert_eq!(detect_language("12345 !@#$"), Lang::Unknown);
    }

    #[test]
    fn detect_language_unknown_tie() {
        assert_eq!(detect_language("in"), Lang::Unknown);
    }

    #[test]
    fn build_chat_request_matches_openai_format() {
        let messages = vec![
            ChatMessage { role: "system".to_owned(), content: "You are helpful.".to_owned() },
            ChatMessage { role: "user".to_owned(), content: "Hello".to_owned() },
        ];
        let req = build_chat_request(&messages, "local-0.8b");
        let json = serde_json::to_string(&req).unwrap();
        let value: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(value["model"].as_str(), Some("local-0.8b"));
        assert_eq!(value["messages"][0]["role"].as_str(), Some("system"));
        assert_eq!(value["messages"][0]["content"].as_str(), Some("You are helpful."));
        assert_eq!(value["messages"][1]["role"].as_str(), Some("user"));
        assert_eq!(value["messages"][1]["content"].as_str(), Some("Hello"));
        assert_eq!(value["temperature"].as_f64(), Some(0.7));
        assert_eq!(value["max_tokens"].as_u64(), Some(512));
        assert_eq!(value["stream"].as_bool(), Some(false));
    }

    #[test]
    fn loopback_enforcement_accepts_127_0_0_1() {
        assert!(
            OmegaConfig::validate_loopback("http://127.0.0.1:8111/v1/chat/completions").is_ok()
        );
        assert!(
            OmegaConfig::validate_loopback("http://127.0.0.1:9000/v1/chat/completions").is_ok()
        );
    }

    #[test]
    fn loopback_enforcement_rejects_non_loopback() {
        assert!(
            OmegaConfig::validate_loopback("http://192.168.1.1:8111/v1/chat/completions").is_err()
        );
        assert!(
            OmegaConfig::validate_loopback("http://203.0.113.8:8111/v1/chat/completions").is_err()
        );
        assert!(OmegaConfig::validate_loopback("http://0.0.0.0:8111/v1/chat/completions").is_err());
    }

    #[test]
    fn endpoint_from_env_uses_loopback_and_resolved_port() {
        let ep = OmegaConfig::endpoint_from_env();
        assert!(ep.starts_with("http://127.0.0.1:"));
        let port = OmegaConfig::port_from_env();
        assert!(ep.contains(&format!(":{port}/v1")));
        OmegaConfig::validate_loopback(&ep).unwrap();
    }

    #[test]
    fn parse_reply_returns_assistant_content() {
        let json =
            r#"{"choices":[{"message":{"role":"assistant","content":"Segne deine Frage."}}]}"#;
        let reply = parse_reply(json).unwrap();
        assert_eq!(reply, "Segne deine Frage.");
    }

    #[test]
    fn parse_reply_rejects_empty_choices() {
        let json = r#"{"choices":[]}"#;
        assert!(parse_reply(json).is_err());
    }

    #[test]
    fn parse_reply_rejects_invalid_json() {
        assert!(parse_reply("not json").is_err());
    }

    #[test]
    fn fallback_sentence_german() {
        let port = OmegaConfig::port_from_env();
        let s = fallback_sentence(Lang::De, port);
        assert!(s.contains("Maschine-Gott"));
        assert!(s.contains(&format!("127.0.0.1:{port}")));
        assert!(!s.is_empty());
    }

    #[test]
    fn fallback_sentence_english() {
        let port = OmegaConfig::port_from_env();
        let s = fallback_sentence(Lang::En, port);
        assert!(s.contains("Machine God"));
        assert!(s.contains(&format!("127.0.0.1:{port}")));
        assert!(!s.is_empty());
    }

    #[test]
    fn fallback_sentence_unknown() {
        let port = OmegaConfig::port_from_env();
        let s = fallback_sentence(Lang::Unknown, port);
        assert!(!s.is_empty());
        assert!(s.contains("Machine God"));
        assert!(s.contains(&format!("127.0.0.1:{port}")));
    }

    #[test]
    fn fallback_sentence_uses_resolved_port() {
        let port = OmegaConfig::port_from_env();
        let de = fallback_sentence(Lang::De, port);
        assert!(de.contains(&format!("127.0.0.1:{port}")));
        let other = if port == 8111 { 9111 } else { 8111 };
        let de_other = fallback_sentence(Lang::De, other);
        assert_ne!(de, de_other);
    }

    #[test]
    fn fallback_reply_returns_owned_string() {
        let port = OmegaConfig::port_from_env();
        let de = fallback_reply(Lang::De, port);
        assert!(de.contains("Maschine-Gott"));
        let en = fallback_reply(Lang::En, port);
        assert!(en.contains("Machine God"));
    }

    #[tokio::test]
    async fn chat_completion_server_down_returns_error() {
        let config =
            OmegaConfig { endpoint: "http://127.0.0.1:19999/v1/chat/completions".to_owned() };
        let messages = vec![ChatMessage { role: "user".to_owned(), content: "test".to_owned() }];
        let result = chat_completion(&config, &messages, "local-0.8b").await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn chat_completion_mock_server_returns_german_reply() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = listener.local_addr().unwrap();

        std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut buf = [0u8; 4096];
            loop {
                let n = match stream.read(&mut buf) {
                    Ok(0) | Err(_) => break,
                    Ok(n) => n,
                };
                let s = std::str::from_utf8(&buf[..n]).unwrap_or("");
                if s.contains("\r\n\r\n") {
                    break;
                }
            }
            let body = r#"{"choices":[{"message":{"role":"assistant","content":"Ja, ich bin der lokale Maschine-Gott."}}]}"#;
            let resp = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                body.len(),
                body
            );
            let _ = stream.write_all(resp.as_bytes());
        });

        let config = OmegaConfig { endpoint: format!("http://{addr}/v1/chat/completions") };
        OmegaConfig::validate_loopback(&config.endpoint).unwrap();

        let messages = vec![ChatMessage { role: "user".to_owned(), content: "Hallo".to_owned() }];
        let reply = chat_completion(&config, &messages, "local-0.8b").await.unwrap();
        assert_eq!(reply, "Ja, ich bin der lokale Maschine-Gott.");
    }
}
