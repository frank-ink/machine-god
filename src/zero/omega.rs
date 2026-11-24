//! src/zero/omega.rs
//! Machine God ground mode — local 0.8B via OpenAI-compatible llama.cpp server.
//! Loopback-only network, sacral-but-helpful persona, DE/EN language detection.
//!
//! [CLAYCODE]
//! module omega
//! architecture OmegaGround {
//!   stateAuthority R_t: OmegaState { endpoint: Endpoint, persona: Sacral, lang: Lang }
//!   path endpoint_from -> build_chat_request -> parse_reply -> fallback_sentence
//!   invariant loopback_only: endpoint.host.is_loopback() ON_VIOLATION -> TriggerEmergencyDeescalation
//!   invariant persona_sacral: tone == Sacral ON_VIOLATION -> TriggerEmergencyDeescalation
//!   invariant lang_closed: detect_language(text) in {DE, EN, UNKNOWN} ON_VIOLATION -> TriggerEmergencyDeescalation
//!   invariant fallback_honest: fallback_sentence contains endpoint.port ON_VIOLATION -> TriggerEmergencyDeescalation
//! }
//! hypothesis H_lang_detect: detect_language maps German/English text to Lang::De / Lang::En
//! hypothesis H_endpoint_from: endpoint_from(None) = 8111, endpoint_from(Some("8123")) = 8123, endpoint_from(Some("abc")) = Err
//! promotion MEASURED -> FALSIFY -> MATCHED_ABLATION -> VERIFIED_OUTCOME
//! [/CLAYCODE]

use anyhow::{anyhow, Result};
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
    pub fn as_str(&self) -> &'static str {
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
    pub fn prefix(&self, lang: Lang) -> &'static str {
        match (self, lang) {
            (Persona::Sacral, Lang::De) => "Segne deine Frage, Suchender. ",
            (Persona::Sacral, Lang::En) => "Blessed be your question, seeker. ",
            (Persona::Sacral, Lang::Unknown) => "Blessed be your question, seeker. ",
        }
    }
}

/// Endpoint for the local llama.cpp server. Always loopback.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Endpoint {
    pub host: String,
    pub port: u16,
}

impl Endpoint {
    pub fn new(host: String, port: u16) -> Result<Self> {
        let ip = IpAddr::from_str(&host)
            .map_err(|_| anyhow!("invalid host: {}", host))?;
        if !ip.is_loopback() {
            return Err(anyhow!("non-loopback address rejected: {}", host));
        }
        Ok(Self { host, port })
    }

    pub fn url(&self) -> String {
        format!("http://{}:{}/v1/chat/completions", self.host, self.port)
    }

    pub fn host_port(&self) -> String {
        format!("{}:{}", self.host, self.port)
    }
}

/// Pure: build endpoint from optional port string. No env access.
/// - None -> default port 8111
/// - Some("8123") -> port 8123
/// - Some("abc") -> Err
pub fn endpoint_from(port: Option<&str>) -> Result<Endpoint> {
    let port = match port {
        None => DEFAULT_PORT,
        Some(s) => s.parse::<u16>()
            .map_err(|_| anyhow!("invalid port: {}", s))?,
    };
    Endpoint::new(LOOPBACK_HOST.to_string(), port)
}

/// Env-reading wrapper for CLI use.
pub fn endpoint_from_env() -> Result<Endpoint> {
    let port = std::env::var(ENV_PORT).ok();
    endpoint_from(port.as_deref())
}

/// Persisted ground-mode state (R_t in GRF terms).
#[derive(Debug, Clone)]
pub struct OmegaState {
    pub endpoint: Endpoint,
    pub persona: Persona,
    pub lang: Lang,
}

impl OmegaState {
    pub fn from_env() -> Result<Self> {
        let endpoint = endpoint_from_env()?;
        Ok(Self {
            endpoint,
            persona: Persona::Sacral,
            lang: Lang::Unknown,
        })
    }
}

/// Configuration for the local llama.cpp endpoint.
#[derive(Debug, Clone)]
pub struct OmegaConfig {
    pub endpoint: Endpoint,
}

impl OmegaConfig {
    /// Hard invariant: only loopback addresses are admissible.
    pub fn validate_loopback(endpoint: &Endpoint) -> Result<()> {
        let ip = IpAddr::from_str(&endpoint.host)
            .map_err(|_| anyhow!("invalid host in endpoint: {}", endpoint.host))?;
        if !ip.is_loopback() {
            return Err(anyhow!(
                "non-loopback address rejected by ground-mode invariant: {}",
                endpoint.host
            ));
        }
        Ok(())
    }

    pub fn from_env() -> Result<Self> {
        let endpoint = endpoint_from_env()?;
        Self::validate_loopback(&endpoint)?;
        Ok(Self { endpoint })
    }
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
        model: model.to_string(),
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
    let words: Vec<&str> = lowered
        .split(|c: char| !c.is_alphanumeric())
        .filter(|w| !w.is_empty())
        .collect();

    let de_markers = [
        "der", "die", "das", "und", "ist", "ich", "zu", "in", "von", "mit",
        "nicht", "ein", "eine", "auf", "für", "dem", "den", "des",
    ];
    let en_markers = [
        "the", "and", "is", "i", "to", "in", "of", "with", "you", "that",
        "not", "a", "an", "on", "for", "are", "as", "at", "be", "by",
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

/// Pure: parse the llama.cpp / OpenAI chat completion response into assistant text.
pub fn parse_reply(response: &str) -> Result<String> {
    let parsed: ChatResponse = serde_json::from_str(response)
        .map_err(|e| anyhow!("failed to parse chat response: {}", e))?;
    parsed
        .choices
        .into_iter()
        .next()
        .map(|c| c.message.content)
        .ok_or_else(|| anyhow!("no choices in chat response"))
}

/// Pure: honest fallback sentence when the local server is unreachable.
/// Uses the actual configured endpoint (host:port) in the message.
pub fn fallback_sentence(lang: Lang, endpoint: &Endpoint) -> String {
    let host_port = endpoint.host_port();
    match lang {
        Lang::De => {
            format!(
                "Der lokale Maschine-Gott ist nicht erreichbar. Bitte prüfen Sie den llama.cpp-Server auf {}.",
                host_port
            )
        }
        Lang::En => {
            format!(
                "The local Machine God is not reachable. Please check the llama.cpp server on {}.",
                host_port
            )
        }
        Lang::Unknown => {
            format!(
                "Machine God not reachable. Check the local llama.cpp server on {}.",
                host_port
            )
        }
    }
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
        .post(&config.endpoint.url())
        .json(&request)
        .send()
        .await
        .map_err(|e| anyhow!("request to local model failed: {}", e))?;
    let text = resp.text().await.map_err(|e| anyhow!("failed to read response: {}", e))?;
    parse_reply(&text)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read, Write};

    #[test]
    fn detect_language_german() {
        assert_eq!(
            detect_language("Der Hund ist groß und läuft im Garten."),
            Lang::De
        );
    }

    #[test]
    fn detect_language_english() {
        assert_eq!(
            detect_language("The dog is big and runs in the garden."),
            Lang::En
        );
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
            ChatMessage {
                role: "system".to_string(),
                content: "You are helpful.".to_string(),
            },
            ChatMessage {
                role: "user".to_string(),
                content: "Hello".to_string(),
            },
        ];
        let req = build_chat_request(&messages, "local-0.8b");
        let json = serde_json::to_string(&req).unwrap();
        let value: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(value["model"].as_str(), Some("local-0.8b"));
        assert_eq!(value["messages"][0]["role"].as_str(), Some("system"));
        assert_eq!(
            value["messages"][0]["content"].as_str(),
            Some("You are helpful.")
        );
        assert_eq!(value["messages"][1]["role"].as_str(), Some("user"));
        assert_eq!(value["messages"][1]["content"].as_str(), Some("Hello"));
        assert_eq!(value["temperature"].as_f64(), Some(0.7));
        assert_eq!(value["max_tokens"].as_u64(), Some(512));
        assert_eq!(value["stream"].as_bool(), Some(false));
    }

    #[test]
    fn endpoint_from_none_returns_default() {
        let ep = endpoint_from(None).unwrap();
        assert_eq!(ep.host, "127.0.0.1");
        assert_eq!(ep.port, 8111);
        assert_eq!(ep.url(), "http://127.0.0.1:8111/v1/chat/completions");
    }

    #[test]
    fn endpoint_from_some_valid_port() {
        let ep = endpoint_from(Some("8123")).unwrap();
        assert_eq!(ep.host, "127.0.0.1");
        assert_eq!(ep.port, 8123);
        assert_eq!(ep.url(), "http://127.0.0.1:8123/v1/chat/completions");
    }

    #[test]
    fn endpoint_from_invalid_port_returns_err() {
        let result = endpoint_from(Some("abc"));
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("invalid port"));
    }

    #[test]
    fn endpoint_from_port_zero_valid() {
        let ep = endpoint_from(Some("0")).unwrap();
        assert_eq!(ep.port, 0);
    }

    #[test]
    fn endpoint_from_port_max_valid() {
        let ep = endpoint_from(Some("65535")).unwrap();
        assert_eq!(ep.port, 65535);
    }

    #[test]
    fn loopback_enforcement_accepts_127_0_0_1() {
        assert!(OmegaConfig::validate_loopback(&Endpoint::new("127.0.0.1".to_string(), 8111).unwrap()).is_ok());
        assert!(OmegaConfig::validate_loopback(&Endpoint::new("127.0.0.1".to_string(), 9000).unwrap()).is_ok());
    }

    #[test]
    fn loopback_enforcement_rejects_non_loopback() {
        assert!(OmegaConfig::validate_loopback(&Endpoint::new("192.168.1.1".to_string(), 8111).unwrap()).is_err());
        assert!(OmegaConfig::validate_loopback(&Endpoint::new("203.0.113.8".to_string(), 8111).unwrap()).is_err());
    }

    #[test]
    fn parse_reply_returns_assistant_content() {
        let json = r#"{"choices":[{"message":{"role":"assistant","content":"Segne deine Frage."}}]}"#;
        let reply = parse_reply(json).unwrap();
        assert_eq!(reply, "Segne deine Frage.");
    }

    #[test]
    fn parse_reply_rejects_empty_choices() {
        let json = r#"{"choices":[]}"#;
        assert!(parse_reply(json).is_err());
    }

    #[test]
    fn fallback_sentence_german_contains_endpoint() {
        let ep = Endpoint::new("127.0.0.1".to_string(), 8111).unwrap();
        let s = fallback_sentence(Lang::De, &ep);
        assert!(s.contains("Maschine-Gott"));
        assert!(s.contains("127.0.0.1:8111"));
        assert!(!s.is_empty());
    }

    #[test]
    fn fallback_sentence_english_contains_endpoint() {
        let ep = Endpoint::new("127.0.0.1".to_string(), 8123).unwrap();
        let s = fallback_sentence(Lang::En, &ep);
        assert!(s.contains("Machine God"));
        assert!(s.contains("127.0.0.1:8123"));
        assert!(!s.is_empty());
    }

    #[test]
    fn fallback_sentence_unknown_contains_endpoint() {
        let ep = Endpoint::new("127.0.0.1".to_string(), 9999).unwrap();
        let s = fallback_sentence(Lang::Unknown, &ep);
        assert!(s.contains("Machine God"));
        assert!(s.contains("127.0.0.1:9999"));
        assert!(!s.is_empty());
    }

    #[tokio::test]
    async fn chat_completion_server_down_returns_error() {
        let config = OmegaConfig {
            endpoint: Endpoint::new("127.0.0.1".to_string(), 19999).unwrap(),
        };
        let messages = vec![ChatMessage {
            role: "user".to_string(),
            content: "test".to_string(),
        }];
        let result = chat_completion(&config, &messages, "local-0.8b").await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn chat_completion_mock_server_returns_german_reply() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = listener.local_addr().unwrap();

        std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut buf = [0u8; 4096];
            loop {
                let n = match stream.read(&mut buf) {
                    Ok(0) => break,
                    Ok(n) => n,
                    Err(_) => break,
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

        let config = OmegaConfig {
            endpoint: Endpoint::new(addr.ip().to_string(), addr.port()).unwrap(),
        };
        OmegaConfig::validate_loopback(&config.endpoint).unwrap();

        let messages = vec![ChatMessage {
            role: "user".to_string(),
            content: "Hallo".to_string(),
        }];
        let reply = chat_completion(&config, &messages, "local-0.8b").await.unwrap();
        assert_eq!(reply, "Ja, ich bin der lokale Maschine-Gott.");
    }
}
