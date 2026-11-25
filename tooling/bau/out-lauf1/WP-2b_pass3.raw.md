Looking at the code, the `phase_b.rs` is cut off mid-function and several implementations are missing. Let me provide the complete fixed files.

=== FILE: docs/gridv1/WP2B_CLAYCODE.clay ===
```
module gridv1.phase_b_orchestrator {
  architecture PhaseBOrchestrator {
    stateAuthority = "PhaseBOrchestrator owns: config: PhaseBConfig. No external mutable state. Accepts PrepResult, ModelToken, LLMClient as arguments to F."
    path PrepResult -> PhaseBOrchestrator -> CellCandidates
  }

  struct PrepResult {
    turn_id: TurnId,
    epoch: Epoch,
    context_bundle: ContextBundle,
    cell_seeds: [CellSeed; 10],
    prep_digest: Digest,
    timestamp_ns: u64,
  }

  struct ModelToken {
    token: String,
    issued_at_ns: u64,
    expires_at_ns: u64,
    scope: TokenScope,
  }

  trait LLMClient {
    fn call(&self, request: LLMRequest) -> Result<LLMResponse, LLMError>;
    fn call_async(&self, request: LLMRequest) -> impl Future<Output = Result<LLMResponse, LLMError>> + Send;
  }

  struct PhaseBConfig {
    timeout_ms: u64,
    max_retries: u8,
    retry_backoff_ms: u64,
    parallelism: u8,
  }

  struct CellCandidate {
    cell_index: u8,
    seed: CellSeed,
    response: LLMResponse,
    digest: Digest,
    attempt: u8,
    latency_ms: u64,
  }

  struct CellCandidates {
    turn_id: TurnId,
    candidates: [CellCandidate; 10],
    completed_count: u8,
    timed_out_indices: [u8; 10],
    phase_b_digest: Digest,
    started_at_ns: u64,
    completed_at_ns: u64,
  }

  enum LLMResponseClass {
    Measured { content: String, model: String, tokens: TokenUsage, finish_reason: FinishReason },
    Timeout { cell_index: u8, elapsed_ms: u64 },
    Error { cell_index: u8, error: LLMError, attempt: u8 },
  }

  invariant I_PARALLELISM_FIXED {
    config.parallelism == 10
  } ON_VIOLATION -> TriggerEmergencyDeescalation("PhaseB parallelism must be exactly 10")

  invariant I_CELL_COUNT_FIXED {
    prep_result.cell_seeds.len() == 10 && candidates.len() == 10
  } ON_VIOLATION -> TriggerEmergencyDeescalation("PhaseB requires exactly 10 cells")

  invariant I_MODEL_TOKEN_VALID {
    model_token.expires_at_ns > now_ns() && model_token.scope == TokenScope::PhaseB
  } ON_VIOLATION -> TriggerEmergencyDeescalation("Model token expired or invalid scope")

  invariant I_DIGEST_VERIFIED {
    forall c in candidates where c.completed: sha256(c.response.content) == c.digest
  } ON_VIOLATION -> TriggerEmergencyDeescalation("Candidate digest mismatch")

  invariant I_NO_DB_LOCK { true } ON_VIOLATION -> TriggerEmergencyDeescalation("Phase B must not hold DB lock")

  invariant I_TIMEOUT_BOUNDED {
    config.timeout_ms > 0 && config.timeout_ms <= 300_000
  } ON_VIOLATION -> TriggerEmergencyDeescalation("Timeout out of bounds")

  invariant I_RETRY_BOUNDED {
    config.max_retries <= 3
  } ON_VIOLATION -> TriggerEmergencyDeescalation("Max retries exceeded")

  fn F_phase_b(
    prep: PrepResult,
    token: ModelToken,
    client: LLMClient,
    config: PhaseBConfig,
  ) -> Result<CellCandidates, PhaseBError> {
    require I_PARALLELISM_FIXED(config)
    require I_CELL_COUNT_FIXED(prep)
    require I_MODEL_TOKEN_VALID(token)
    require I_TIMEOUT_BOUNDED(config)
    require I_RETRY_BOUNDED(config)

    let started = now_ns()
    let mut candidates: [Option<CellCandidate>; 10] = [None; 10]
    let mut timed_out: [bool; 10] = [false; 10]
    let mut completed = 0u8

    let handles = prep.cell_seeds.into_iter().enumerate().map(|(idx, seed)| {
      let client = client.clone()
      let token = token.clone()
      let config = config.clone()
      let prep = prep.clone()
      async move { call_cell_with_retry(idx as u8, seed, prep, token, client, config).await }
    }).collect::<Vec<_>>()

    let results = timeout(config.timeout_ms, join_all(handles)).await

    match results {
      Ok(cell_results) => {
        for (idx, result) in cell_results.into_iter().enumerate() {
          match result {
            Ok(candidate) => { candidates[idx] = Some(candidate); completed += 1 }
            Err(PhaseBError::Timeout) => { timed_out[idx] = true }
            Err(e) => { timed_out[idx] = true; log_error("Cell {} failed: {}", idx, e) }
          }
        }
      }
      Err(_) => {
        for idx in 0..10 { if candidates[idx].is_none() { timed_out[idx] = true } }
      }
    }

    let completed_at = now_ns()
    let final_candidates: [CellCandidate; 10] = std::array::from_fn(|idx| {
      candidates[idx].unwrap_or(CellCandidate {
        cell_index: idx as u8, seed: prep.cell_seeds[idx],
        response: LLMResponse::timeout(), digest: Digest::zero(),
        attempt: config.max_retries + 1, latency_ms: config.timeout_ms,
      })
    })

    let digest_inputs: Vec<u8> = final_candidates.iter()
      .flat_map(|c| c.digest.0).copied().collect()
    let phase_b_digest = Digest(sha256(&digest_inputs))

    let result = CellCandidates {
      turn_id: prep.turn_id, candidates: final_candidates,
      completed_count: completed, timed_out_indices: timed_out.map(|b| b as u8),
      phase_b_digest, started_at_ns: started, completed_at_ns: completed_at,
    }

    ensure I_CELL_COUNT_FIXED(result)
    ensure I_DIGEST_VERIFIED(result)
    Ok(result)
  }

  fn call_cell_with_retry(
    idx: u8, seed: CellSeed, prep: PrepResult,
    token: ModelToken, client: LLMClient, config: PhaseBConfig,
  ) -> Result<CellCandidate, PhaseBError> {
    let mut last_error = None
    for attempt in 0..=config.max_retries {
      let cell_started = now_ns()
      let request = build_llm_request(idx, seed, prep, token)
      match client.call_async(request).await {
        Ok(response) => {
          let latency = (now_ns() - cell_started) / 1_000_000
          let digest = Digest(sha256(response.content.as_bytes()))
          return Ok(CellCandidate { cell_index: idx, seed, response, digest, attempt, latency_ms: latency })
        }
        Err(e) => {
          last_error = Some(e)
          if attempt < config.max_retries { sleep(config.retry_backoff_ms * (attempt + 1) as u64).await }
        }
      }
    }
    Err(PhaseBError::MaxRetriesExceeded(last_error.unwrap()))
  }

  fn build_llm_request(idx: u8, seed: CellSeed, prep: PrepResult, token: ModelToken) -> LLMRequest {
    LLMRequest {
      cell_index: idx,
      system_prompt: prep.context_bundle.conversation_summary.clone(),
      user_prompt: format!("{}\n\nVariant: {}", prep.context_bundle.user_message, seed.prompt_variant),
      temperature: seed.temperature, max_tokens: seed.max_tokens,
      model_token: token.token,
      request_id: format!("{}-{}-{}", prep.turn_id.0, prep.epoch.0, idx),
    }
  }

  hypothesis H_PARALLEL_SPEEDUP { "10 parallel calls complete in ~max(single_call_latency) not sum(latencies)" } promotion MEASURE -> FALSIFY -> VERIFIED_OUTCOME
  hypothesis H_TIMEOUT_ISOLATION { "One cell timeout does not block other cells" } promotion MEASURE -> FALSIFY -> VERIFIED_OUTCOME
  hypothesis H_DIGEST_INTEGRITY { "All returned candidates have verifiable sha256 digests" } promotion MEASURE -> MATCHED_ABLATION -> VERIFIED_OUTCOME
}
```

=== FILE: src/gridv1/mod.rs ===
```rust
//! GRID10 Phase B Orchestration Module
//!
//! This module implements the 10-cell LLM competition phase (Phase B)
//! of the GRID10 turn engine. It runs without holding any database locks.

pub mod phase_b;
pub mod types;
pub mod client;
pub mod error;

pub use phase_b::{PhaseBOrchestrator, PhaseBConfig};
pub use types::{
    PrepResult, ModelToken, CellSeed, CellCandidate, CellCandidates,
    LLMRequest, LLMResponse, TokenScope, Digest, TurnId, Epoch,
    ContextBundle, TokenUsage, FinishReason,
};
pub use client::{LLMClient, BridgeLLMClient, LLMError, MockLLMClient};
pub use error::{PhaseBError, PhaseBResult};
```

=== FILE: src/gridv1/types.rs ===
```rust
//! Core types for GRID10 Phase B Orchestration

use serde::{Deserialize, Serialize};
use std::fmt;
use std::time::{SystemTime, UNIX_EPOCH};
use sha2::{Digest as Sha2Digest, Sha256};

/// Unique identifier for a turn
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct TurnId(pub u64);

impl TurnId {
    pub fn new() -> Self {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("Time went backwards")
            .as_nanos() as u64;
        TurnId(nanos)
    }
}

/// Epoch number for entity synchronization
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Epoch(pub u64);

/// Cryptographic digest (SHA-256)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Digest(pub [u8; 32]);

impl Digest {
    pub fn zero() -> Self {
        Digest([0u8; 32])
    }

    pub fn from_bytes(bytes: &[u8]) -> Self {
        let mut hasher = Sha256::new();
        hasher.update(bytes);
        let result = hasher.finalize();
        let mut arr = [0u8; 32];
        arr.copy_from_slice(&result);
        Digest(arr)
    }

    pub fn as_hex(&self) -> String {
        hex::encode(self.0)
    }
}

impl fmt::Display for Digest {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.as_hex())
    }
}

/// Token scope for capability-based authorization
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum TokenScope {
    PhaseA,
    PhaseB,
    PhaseC,
    Full,
}

/// Model authentication token with expiry
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ModelToken {
    pub token: String,
    pub issued_at_ns: u64,
    pub expires_at_ns: u64,
    pub scope: TokenScope,
}

impl ModelToken {
    pub fn is_valid(&self, now_ns: u64, required_scope: TokenScope) -> bool {
        now_ns < self.expires_at_ns && (self.scope == required_scope || self.scope == TokenScope::Full)
    }
}

/// Seed for a single cell in the 10-cell competition
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CellSeed {
    pub index: u8,
    pub prompt_variant: String,
    pub temperature: f32,
    pub max_tokens: u32,
    pub system_prompt_hash: Digest,
}

/// Context bundle passed to all cells
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ContextBundle {
    pub turn_id: TurnId,
    pub epoch: Epoch,
    pub user_message: String,
    pub conversation_summary: String,
    pub relevant_memories: Vec<String>,
    pub constraints: Vec<String>,
}

/// Result from Phase A preparation
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PrepResult {
    pub turn_id: TurnId,
    pub epoch: Epoch,
    pub context_bundle: ContextBundle,
    pub cell_seeds: [CellSeed; 10],
    pub prep_digest: Digest,
    pub timestamp_ns: u64,
}

impl PrepResult {
    pub fn validate(&self) -> Result<(), &'static str> {
        if self.cell_seeds.len() != 10 {
            return Err("PrepResult must contain exactly 10 cell seeds");
        }
        for (i, seed) in self.cell_seeds.iter().enumerate() {
            if seed.index != i as u8 {
                return Err("Cell seed index mismatch");
            }
        }
        Ok(())
    }
}

/// Token usage statistics
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct TokenUsage {
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub total_tokens: u32,
}

/// Finish reason from LLM
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum FinishReason {
    Stop,
    Length,
    ToolUse,
    Error,
    Timeout,
}

/// Request to LLM
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LLMRequest {
    pub cell_index: u8,
    pub system_prompt: String,
    pub user_prompt: String,
    pub temperature: f32,
    pub max_tokens: u32,
    pub model_token: String,
    pub request_id: String,
}

/// Response from LLM (epistemically tagged)
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum LLMResponse {
    Measured {
        content: String,
        model: String,
        tokens: TokenUsage,
        finish_reason: FinishReason,
    },
    Timeout {
        cell_index: u8,
        elapsed_ms: u64,
    },
    Error {
        cell_index: u8,
        error: String,
        attempt: u8,
    },
}

impl LLMResponse {
    pub fn timeout(cell_index: u8, elapsed_ms: u64) -> Self {
        LLMResponse::Timeout { cell_index, elapsed_ms }
    }

    pub fn error(cell_index: u8, error: String, attempt: u8) -> Self {
        LLMResponse::Error { cell_index, error, attempt }
    }

    pub fn content(&self) -> Option<&str> {
        match self {
            LLMResponse::Measured { content, .. } => Some(content),
            _ => None,
        }
    }

    pub fn is_measured(&self) -> bool {
        matches!(self, LLMResponse::Measured { .. })
    }
}

/// Single cell candidate result
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CellCandidate {
    pub cell_index: u8,
    pub seed: CellSeed,
    pub response: LLMResponse,
    pub digest: Digest,
    pub attempt: u8,
    pub latency_ms: u64,
}

impl CellCandidate {
    pub fn is_completed(&self) -> bool {
        self.response.is_measured()
    }

    pub fn verify_digest(&self) -> bool {
        match &self.response {
            LLMResponse::Measured { content, .. } => {
                Digest::from_bytes(content.as_bytes()) == self.digest
            }
            _ => self.digest == Digest::zero(),
        }
    }
}

/// Aggregated results from Phase B
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CellCandidates {
    pub turn_id: TurnId,
    pub candidates: [CellCandidate; 10],
    pub completed_count: u8,
    pub timed_out_indices: [u8; 10],
    pub phase_b_digest: Digest,
    pub started_at_ns: u64,
    pub completed_at_ns: u64,
}

impl CellCandidates {
    pub fn verify_all_digests(&self) -> bool {
        self.candidates.iter().all(|c| c.verify_digest())
    }

    pub fn verify_phase_digest(&self) -> bool {
        let mut hasher = Sha256::new();
        for c in &self.candidates {
            hasher.update(&c.digest.0);
        }
        let result = hasher.finalize();
        let mut arr = [0u8; 32];
        arr.copy_from_slice(&result);
        Digest(arr) == self.phase_b_digest
    }

    pub fn duration_ms(&self) -> u64 {
        (self.completed_at_ns - self.started_at_ns) / 1_000_000
    }
}

/// Configuration for Phase B orchestrator
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PhaseBConfig {
    pub timeout_ms: u64,
    pub max_retries: u8,
    pub retry_backoff_ms: u64,
    pub parallelism: u8,
}

impl Default for PhaseBConfig {
    fn default() -> Self {
        PhaseBConfig {
            timeout_ms: 120_000,
            max_retries: 2,
            retry_backoff_ms: 1_000,
            parallelism: 10,
        }
    }
}

impl PhaseBConfig {
    pub fn validate(&self) -> Result<(), &'static str> {
        if self.parallelism != 10 {
            return Err("Parallelism must be exactly 10");
        }
        if self.timeout_ms == 0 || self.timeout_ms > 300_000 {
            return Err("Timeout must be between 1ms and 300000ms");
        }
        if self.max_retries > 3 {
            return Err("Max retries must not exceed 3");
        }
        Ok(())
    }
}
```

=== FILE: src/gridv1/client.rs ===
```rust
//! LLM Client trait and implementations for Phase B

use async_trait::async_trait;
use crate::gridv1::types::{LLMRequest, LLMResponse, TokenUsage, FinishReason};
use crate::gridv1::error::LLMError;
use std::fmt::Debug;

/// Trait for LLM clients used in Phase B
/// 
/// Implementations must be thread-safe (Send + Sync) and support
/// concurrent calls from the Phase B orchestrator.
#[async_trait]
pub trait LLMClient: Send + Sync + Debug {
    /// Make a synchronous call (blocking)
    fn call(&self, request: LLMRequest) -> Result<LLMResponse, LLMError>;

    /// Make an asynchronous call (non-blocking)
    async fn call_async(&self, request: LLMRequest) -> Result<LLMResponse, LLMError>;
}

/// Bridge client that communicates via the Bun bridge (NDJSON over stdin/stdout)
#[derive(Debug, Clone)]
pub struct BridgeLLMClient {
    pub bridge_endpoint: String,
    pub default_model: String,
    pub http_client: reqwest::Client,
}

impl BridgeLLMClient {
    pub fn new(bridge_endpoint: String, default_model: String) -> Self {
        BridgeLLMClient {
            bridge_endpoint,
            default_model,
            http_client: reqwest::Client::new(),
        }
    }

    fn build_request(&self, request: &LLMRequest) -> serde_json::Value {
        serde_json::json!({
            "type": "llm_call",
            "cell_index": request.cell_index,
            "system_prompt": request.system_prompt,
            "user_prompt": request.user_prompt,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "model": self.default_model,
            "model_token": request.model_token,
            "request_id": request.request_id,
        })
    }

    fn parse_response(&self, value: serde_json::Value, cell_index: u8) -> Result<LLMResponse, LLMError> {
        let response_type = value.get("type").and_then(|v| v.as_str()).unwrap_or("unknown");
        
        match response_type {
            "llm_response" => {
                let content = value.get("content").and_then(|v| v.as_str()).unwrap_or("").to_string();
                let model = value.get("model").and_then(|v| v.as_str()).unwrap_or("unknown").to_string();
                let input_tokens = value.get("input_tokens").and_then(|v| v.as_u64()).unwrap_or(0) as u32;
                let output_tokens = value.get("output_tokens").and_then(|v| v.as_u64()).unwrap_or(0) as u32;
                let finish_reason_str = value.get("finish_reason").and_then(|v| v.as_str()).unwrap_or("stop");
                let finish_reason = match finish_reason_str {
                    "stop" => FinishReason::Stop,
                    "length" => FinishReason::Length,
                    "tool_use" => FinishReason::ToolUse,
                    "error" => FinishReason::Error,
                    _ => FinishReason::Stop,
                };
                
                Ok(LLMResponse::Measured {
                    content,
                    model,
                    tokens: TokenUsage {
                        input_tokens,
                        output_tokens,
                        total_tokens: input_tokens + output_tokens,
                    },
                    finish_reason,
                })
            }
            "llm_timeout" => {
                let elapsed_ms = value.get("elapsed_ms").and_then(|v| v.as_u64()).unwrap_or(0);
                Ok(LLMResponse::timeout(cell_index, elapsed_ms))
            }
            "llm_error" => {
                let error = value.get("error").and_then(|v| v.as_str()).unwrap_or("unknown error").to_string();
                let attempt = value.get("attempt").and_then(|v| v.as_u64()).unwrap_or(0) as u8;
                Ok(LLMResponse::error(cell_index, error, attempt))
            }
            _ => Err(LLMError::Model(format!("Unknown response type: {}", response_type))),
        }
    }
}

#[async_trait]
impl LLMClient for BridgeLLMClient {
    fn call(&self, request: LLMRequest) -> Result<LLMResponse, LLMError> {
        let rt = tokio::runtime::Handle::try_current()
            .map(|h| h.block_on(self.call_async(request)))
            .unwrap_or_else(|_| {
                let rt = tokio::runtime::Runtime::new().map_err(|e| LLMError::Unknown(e.to_string()))?;
                rt.block_on(self.call_async(request))
            });
        rt
    }

    async fn call_async(&self, request: LLMRequest) -> Result<LLMResponse, LLMError> {
        let payload = self.build_request(&request);
        
        let response = self.http_client
            .post(&self.bridge_endpoint)
            .json(&payload)
            .timeout(std::time::Duration::from_millis(180_000))
            .send()
            .await
            .map_err(|e| LLMError::Network(e.to_string()))?;

        if !response.status().is_success() {
            let status = response.status();
            let text = response.text().await.unwrap_or_default();
            if status == 401 || status == 403 {
                return Err(LLMError::Auth(text));
            }
            if status == 429 {
                let retry_after = response.headers()
                    .get("retry-after")
                    .and_then(|v| v.to_str().ok())
                    .and_then(|v| v.parse().ok())
                    .unwrap_or(5000);
                return Err(LLMError::RateLimited { retry_after_ms: retry_after });
            }
            return Err(LLMError::Model(format!("HTTP {}: {}", status, text)));
        }

        let value: serde_json::Value = response.json().await
            .map_err(|e| LLMError::Network(e.to_string()))?;

        self.parse_response(value, request.cell_index)
    }
}

/// Mock client for testing
#[cfg(test)]
#[derive(Debug, Clone)]
pub struct MockLLMClient {
    pub responses: std::sync::Arc<tokio::sync::Mutex<Vec<Result<LLMResponse, LLMError>>>>,
    pub call_count: std::sync::Arc<std::sync::atomic::AtomicUsize>,
}

#[cfg(test)]
impl MockLLMClient {
    pub fn new(responses: Vec<Result<LLMResponse, LLMError>>) -> Self {
        MockLLMClient {
            responses: std::sync::Arc::new(tokio::sync::Mutex::new(responses)),
            call_count: std::sync::Arc::new(std::sync::atomic::AtomicUsize::new(0)),
        }
    }

    pub fn call_count(&self) -> usize {
        self.call_count.load(std::sync::atomic::Ordering::SeqCst)
    }
}

#[cfg(test)]
#[async_trait]
impl LLMClient for MockLLMClient {
    fn call(&self, request: LLMRequest) -> Result<LLMResponse, LLMError> {
        let rt = tokio::runtime::Handle::try_current()
            .map(|h| h.block_on(self.call_async(request)))
            .unwrap_or_else(|_| {
                let rt = tokio::runtime::Runtime::new().unwrap();
                rt.block_on(self.call_async(request))
            });
        rt
    }

    async fn call_async(&self, _request: LLMRequest) -> Result<LLMResponse, LLMError> {
        self.call_count.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        let mut responses = self.responses.lock().await;
        if responses.is_empty() {
            return Err(LLMError::Unknown("No more mock responses".to_string()));
        }
        responses.remove(0)
    }
}
```

=== FILE: src/gridv1/error.rs ===
```rust
//! Error types for Phase B Orchestration

use crate::gridv1::types::LLMError as TypesLLMError;
use thiserror::Error;

/// Errors that can occur during Phase B orchestration
#[derive(Debug, Clone, PartialEq, Eq, Error)]
pub enum PhaseBError {
    #[error("Configuration invalid: {0}")]
    ConfigInvalid(String),
    #[error("PrepResult validation failed: {0}")]
    PrepValidationFailed(String),
    #[error("Model token invalid or expired")]
    TokenInvalid,
    #[error("Model token scope mismatch: required {required:?}, got {actual:?}")]
    TokenScopeMismatch { required: crate::gridv1::types::TokenScope, actual: crate::gridv1::types::TokenScope },
    #[error("Cell {cell_index} timeout after {elapsed_ms}ms")]
    CellTimeout { cell_index: u8, elapsed_ms: u64 },
    #[error("Global timeout after {elapsed_ms}ms, {completed}/10 cells completed")]
    GlobalTimeout { elapsed_ms: u64, completed: u8 },
    #[error("Cell {cell_index} max retries ({max_retries}) exceeded: {last_error}")]
    MaxRetriesExceeded { cell_index: u8, max_retries: u8, last_error: String },
    #[error("LLM client error: {0}")]
    ClientError(#[from] TypesLLMError),
    #[error("Digest verification failed for cell {cell_index}")]
    DigestMismatch { cell_index: u8 },
    #[error("Phase B digest verification failed")]
    PhaseDigestMismatch,
    #[error("Internal error: {0}")]
    Internal(String),
}

/// Result type for Phase B operations
pub type PhaseBResult<T> = Result<T, PhaseBError>;

impl PhaseBError {
    pub fn is_timeout(&self) -> bool {
        matches!(self, PhaseBError::CellTimeout { .. } | PhaseBError::GlobalTimeout { .. })
    }

    pub fn is_retryable(&self) -> bool {
        matches!(self, PhaseBError::ClientError(e) if e.is_retryable())
    }
}

/// Error types for LLM client operations
#[derive(Debug, Clone, PartialEq, Eq, Error)]
pub enum LLMError {
    #[error("Network error: {0}")]
    Network(String),
    #[error("Authentication failed: {0}")]
    Auth(String),
    #[error("Rate limited: retry after {retry_after_ms}ms")]
    RateLimited { retry_after_ms: u64 },
    #[error("Model error: {0}")]
    Model(String),
    #[error("Timeout after {elapsed_ms}ms")]
    Timeout { elapsed_ms: u64 },
    #[error("Invalid request: {0}")]
    InvalidRequest(String),
    #[error("Unknown error: {0}")]
    Unknown(String),
}

impl LLMError {
    pub fn is_retryable(&self) -> bool {
        matches!(self, LLMError::Network(_) | LLMError::RateLimited { .. } | LLMError::Timeout { .. })
    }
}

// Conversion from LLMError to PhaseBError for ClientError variant
impl From<LLMError> for PhaseBError {
    fn from(e: LLMError) -> Self {
        PhaseBError::ClientError(e)
    }
}
```

=== FILE: src/gridv1/phase_b.rs ===
```rust
//! GRID10 Phase B Orchestrator Implementation
//!
//! Orchestrates the 10-cell LLM competition phase.
//! Runs without holding any database locks.

use crate::gridv1::types::*;
use crate::gridv1::client::LLMClient;
use crate::gridv1::error::{PhaseBError, PhaseBResult, LLMError};
use futures::future::join_all;
use sha2::{Digest as Sha2Digest, Sha256};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::time::{timeout, Duration, sleep};
use tracing::{debug, error, info, warn};

/// Current time in nanoseconds since epoch
fn now_ns() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("Time went backwards")
        .as_nanos() as u64
}

/// Phase B Orchestrator
#[derive(Debug, Clone)]
pub struct PhaseBOrchestrator {
    config: PhaseBConfig,
}

impl PhaseBOrchestrator {
    /// Create a new Phase B orchestrator with the given configuration
    pub fn new(config: PhaseBConfig) -> PhaseBResult<Self> {
        config.validate().map_err(PhaseBError::ConfigInvalid)?;
        if config.parallelism != 10 {
            return Err(PhaseBError::ConfigInvalid("Parallelism must be exactly 10".to_string()));
        }
        Ok(PhaseBOrchestrator { config })
    }

    /// Execute Phase B: 10-cell parallel LLM competition
    /// 
    /// Takes a PrepResult from Phase A, a valid ModelToken, and an LLMClient.
    /// Returns CellCandidates with all 10 cell results (completed or timed out).
    /// 
    /// # Invariants
    /// - No database locks are held during execution
    /// - Exactly 10 cells are processed
    /// - Each completed candidate has a verified SHA-256 digest
    /// - Global timeout bounds total execution time
    pub async fn execute(
        &self,
        prep: PrepResult,
        token: ModelToken,
        client: Arc<dyn LLMClient>,
    ) -> PhaseBResult<CellCandidates> {
        // Precondition checks (invariants)
        self.check_preconditions(&prep, &token)?;

        let started_at = now_ns();
        info!(turn_id = %prep.turn_id.0, "Phase B started: 10-cell competition");

        // Spawn 10 parallel tasks
        let cell_futures: Vec<_> = prep.cell_seeds.iter().enumerate().map(|(idx, seed)| {
            let idx = idx as u8;
            let seed = seed.clone();
            let prep = prep.clone();
            let token = token.clone();
            let client = client.clone();
            let config = self.config.clone();
            
            async move {
                Self::call_cell_with_retry(idx, seed, prep, token, client, config).await
            }
        }).collect();

        // Execute with global timeout
        let global_timeout = Duration::from_millis(self.config.timeout_ms);
        let results = timeout(global_timeout, join_all(cell_futures)).await;

        let completed_at = now_ns();
        let mut candidates: [Option<CellCandidate>; 10] = [None; 10];
        let mut timed_out: [bool; 10] = [false; 10];
        let mut completed_count = 0u8;

        match results {
            Ok(cell_results) => {
                for (idx, result) in cell_results.into_iter().enumerate() {
                    match result {
                        Ok(candidate) => {
                            // Verify digest
                            if !candidate.verify_digest() {
                                error!(cell_index = idx, "Digest verification failed");
                                return Err(PhaseBError::DigestMismatch { cell_index: idx as u8 });
                            }
                            candidates[idx] = Some(candidate);
                            completed_count += 1;
                        }
                        Err(PhaseBError::CellTimeout { cell_index, .. }) | 
                        Err(PhaseBError::GlobalTimeout { .. }) => {
                            timed_out[idx] = true;
                        }
                        Err(e) => {
                            timed_out[idx] = true;
                            warn!(cell_index = idx, error = %e, "Cell failed, marking as timed out");
                        }
                    }
                }
            }
            Err(_) => {
                // Global timeout - mark all incomplete as timed out
                for idx in 0..10 {
                    if candidates[idx].is_none() {
                        timed_out[idx] = true;
                    }
                }
                warn!("Global timeout reached, {} cells completed", completed_count);
            }
        }

        // Build final candidates array (fill timed-out with placeholder)
        let final_candidates: [CellCandidate; 10] = std::array::from_fn(|idx| {
            candidates[idx].clone().unwrap_or_else(|| {
                let seed = prep.cell_seeds[idx].clone();
                CellCandidate {
                    cell_index: idx as u8,
                    seed,
                    response: LLMResponse::timeout(idx as u8, self.config.timeout_ms),
                    digest: Digest::zero(),
                    attempt: self.config.max_retries + 1,
                    latency_ms: self.config.timeout_ms,
                }
            })
        });

        // Compute phase B digest
        let mut hasher = Sha256::new();
        for c in &final_candidates {
            hasher.update(&c.digest.0);
        }
        let result_bytes = hasher.finalize();
        let mut digest_arr = [0u8; 32];
        digest_arr.copy_from_slice(&result_bytes);
        let phase_b_digest = Digest(digest_arr);

        let result = CellCandidates {
            turn_id: prep.turn_id,
            candidates: final_candidates,
            completed_count,
            timed_out_indices: timed_out.map(|b| b as u8),
            phase_b_digest,
            started_at_ns: started_at,
            completed_at_ns: completed_at,
        };

        // Postcondition checks
        if result.candidates.len() != 10 {
            return Err(PhaseBError::Internal("Candidate array length mismatch".to_string()));
        }
        if !result.verify_all_digests() {
            return Err(PhaseBError::PhaseDigestMismatch);
        }

        info!(
            turn_id = %prep.turn_id.0,
            completed = completed_count,
            duration_ms = result.duration_ms(),
            "Phase B completed"
        );

        Ok(result)
    }

    /// Check preconditions before execution
    fn check_preconditions(&self, prep: &PrepResult, token: &ModelToken) -> PhaseBResult<()> {
        // I_CELL_COUNT_FIXED
        prep.validate().map_err(PhaseBError::PrepValidationFailed)?;

        // I_MODEL_TOKEN_VALID
        let now = now_ns();
        if !token.is_valid(now, TokenScope::PhaseB) {
            if now >= token.expires_at_ns {
                return Err(PhaseBError::TokenInvalid);
            }
            return Err(PhaseBError::TokenScopeMismatch {
                required: TokenScope::PhaseB,
                actual: token.scope,
            });
        }

        // I_TIMEOUT_BOUNDED
        if self.config.timeout_ms == 0 || self.config.timeout_ms > 300_000 {
            return Err(PhaseBError::ConfigInvalid("Timeout out of bounds".to_string()));
        }

        // I_RETRY_BOUNDED
        if self.config.max_retries > 3 {
            return Err(PhaseBError::ConfigInvalid("Max retries exceeded".to_string()));
        }

        // I_PARALLELISM_FIXED
        if self.config.parallelism != 10 {
            return Err(PhaseBError::ConfigInvalid("Parallelism must be exactly 10".to_string()));
        }

        Ok(())
    }

    /// Call a single cell with retry logic
    async fn call_cell_with_retry(
        idx: u8,
        seed: CellSeed,
        prep: PrepResult,
        token: ModelToken,
        client: Arc<dyn LLMClient>,
        config: PhaseBConfig,
    ) -> PhaseBResult<CellCandidate> {
        let mut last_error: Option<LLMError> = None;

        for attempt in 0..=config.max_retries {
            let cell_started = now_ns();
            let request = Self::build_llm_request(idx, &seed, &prep, &token);
            
            match client.call_async(request).await {
                Ok(response) => {
                    let latency = (now_ns() - cell_started) / 1_000_000;
                    let content = response.content().unwrap_or("").to_string();
                    let digest = Digest::from_bytes(content.as_bytes());
                    
                    return Ok(CellCandidate {
                        cell_index: idx,
                        seed,
                        response,
                        digest,
                        attempt: attempt as u8,
                        latency_ms: latency,
                    });
                }
                Err(e) => {
                    last_error = Some(e.clone());
                    
                    // Check if we should retry
                    if attempt < config.max_retries && e.is_retryable() {
                        let backoff = config.retry_backoff_ms * (attempt + 1) as u64;
                        debug!(cell_index = idx, attempt = attempt + 1, backoff_ms = backoff, "Retrying cell call");
                        sleep(Duration::from_millis(backoff)).await;
                    } else {
                        break;
                    }
                }
            }
        }

        // All retries exhausted
        let elapsed = now_ns() - (now_ns().saturating_sub(config.timeout_ms * 1_000_000));
        Err(PhaseBError::MaxRetriesExceeded {
            cell_index: idx,
            max_retries: config.max_retries,
            last_error: last_error.map(|e| e.to_string()).unwrap_or_else(|| "Unknown error".to_string()),
        })
    }

    /// Build LLM request from cell seed and prep context
    fn build_llm_request(
        idx: u8,
        seed: &CellSeed,
        prep: &PrepResult,
        token: &ModelToken,
    ) -> LLMRequest {
        LLMRequest {
            cell_index: idx,
            system_prompt: prep.context_bundle.conversation_summary.clone(),
            user_prompt: format!("{}\n\nVariant: {}", prep.context_bundle.user_message, seed.prompt_variant),
            temperature: seed.temperature,
            max_tokens: seed.max_tokens,
            model_token: token.token.clone(),
            request_id: format!("{}-{}-{}", prep.turn_id.0, prep.epoch.0, idx),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::gridv1::client::MockLLMClient;
    use crate::gridv1::types::*;
    use std::sync::Arc;

    fn make_test_prep() -> PrepResult {
        let turn_id = TurnId(1);
        let epoch = Epoch(1);
        let context = ContextBundle {
            turn_id,
            epoch,
            user_message: "Test message".to_string(),
            conversation_summary: "Test summary".to_string(),
            relevant_memories: vec![],
            constraints: vec![],
        };
        let seeds: [CellSeed; 10] = std::array::from_fn(|i| CellSeed {
            index: i as u8,
            prompt_variant: format!("Variant {}", i),
            temperature: 0.7,
            max_tokens: 100,
            system_prompt_hash: Digest::zero(),
        });
        PrepResult {
            turn_id,
            epoch,
            context_bundle: context,
            cell_seeds: seeds,
            prep_digest: Digest::zero(),
            timestamp_ns: now_ns(),
        }
    }

    fn make_test_token() -> ModelToken {
        ModelToken {
            token: "test-token".to_string(),
            issued_at_ns: now_ns(),
            expires_at_ns: now_ns() + 3600_000_000_000, // 1 hour
            scope: TokenScope::PhaseB,
        }
    }

    #[tokio::test]
    async fn test_phase_b_execute_success() {
        let config = PhaseBConfig::default();
        let orchestrator = PhaseBOrchestrator::new(config).unwrap();
        
        let prep = make_test_prep();
        let token = make_test_token();
        
        // Create mock client that returns successful responses
        let responses: Vec<Result<LLMResponse, LLMError>> = (0..10).map(|i| {
            Ok(LLMResponse::Measured {
                content: format!("Response {}", i),
                model: "test-model".to_string(),
                tokens: TokenUsage { input_tokens: 10, output_tokens: 20, total_tokens: 30 },
                finish_reason: FinishReason::Stop,
            })
        }).collect();
        
        let mock_client = Arc::new(MockLLMClient::new(responses));
        let result = orchestrator.execute(prep, token, mock_client).await;
        
        assert!(result.is_ok());
        let candidates = result.unwrap();
        assert_eq!(candidates.completed_count, 10);
        assert!(candidates.verify_all_digests());
        assert!(candidates.verify_phase_digest());
    }

    #[tokio::test]
    async fn test_phase_b_execute_timeout() {
        let mut config = PhaseBConfig::default();
        config.timeout_ms = 1; // Very short timeout
        let orchestrator = PhaseBOrchestrator::new(config).unwrap();
        
        let prep = make_test_prep();
        let token = make_test_token();
        
        // Mock client that delays
        let responses: Vec<Result<LLMResponse, LLMError>> = (0..10).map(|_| {
            Err(LLMError::Timeout { elapsed_ms: 100 })
        }).collect();
        
        let mock_client = Arc::new(MockLLMClient::new(responses));
        let result = orchestrator.execute(prep, token, mock_client).await;
        
        assert!(result.is_ok()); // Should complete with timeouts
        let candidates = result.unwrap();
        assert_eq!(candidates.completed_count, 0);
        assert!(candidates.timed_out_indices.iter().all(|&x| x == 1));
    }

    #[tokio::test]
    async fn test_phase_b_invalid_config() {
        let mut config = PhaseBConfig::default();
        config.parallelism = 5;
        let result = PhaseBOrchestrator::new(config);
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_phase_b_invalid_token() {
        let config = PhaseBConfig::default();
        let orchestrator = PhaseBOrchestrator::new(config).unwrap();
        
        let prep = make_test_prep();
        let mut token = make_test_token();
        token.expires_at_ns = now_ns() - 1000; // Expired
        
        let mock_client = Arc::new(MockLLMClient::new(vec![]));
        let result = orchestrator.execute(prep, token, mock_client).await;
        
        assert!(matches!(result, Err(PhaseBError::TokenInvalid)));
    }
}
```