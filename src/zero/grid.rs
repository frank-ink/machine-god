//! Local GRID health checks and event delivery.
//!
//! GRID is reachable only through the literal IPv4 loopback address
//! `127.0.0.1`. DNS names, LAN addresses, and public addresses are rejected
//! before a socket can be opened. Health is evidence-based: a reachable but
//! unhealthy GRID is DEGRADED, an unreachable GRID is UNKNOWN (never a
//! fabricated failure and never a fabricated success).

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::fmt;
use std::io::{Read, Write};
use std::net::{IpAddr, Ipv4Addr, SocketAddr, TcpStream};
use std::sync::Arc;
use std::time::{Duration, SystemTime};
use thiserror::Error;

pub const GRID_HOST: &str = "127.0.0.1";
pub const DEFAULT_GRID_PORT: u16 = 8490;
pub const GRID_PORT_ENV: &str = "MACHINE_GOD_GRID_PORT";
pub const STATUS_MAX_AGE: Duration = Duration::from_secs(30);

const MAX_REQUEST_BYTES: usize = 1024 * 1024;
const MAX_RESPONSE_BYTES: usize = 1024 * 1024;
const MAX_HEADER_BYTES: usize = 64 * 1024;
const DEFAULT_TIMEOUT: Duration = Duration::from_secs(2);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HealthState {
    Ok,
    Degraded,
    Unknown,
}

impl HealthState {
    pub fn is_measured(self) -> bool {
        !matches!(self, HealthState::Unknown)
    }
}

/// A component observation. `last_success` is evidence, not a default value.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ComponentStatus {
    pub state: HealthState,
    pub last_success: Option<SystemTime>,
}

impl ComponentStatus {
    pub fn measured_at(state: HealthState, at: SystemTime) -> Self {
        Self {
            state,
            last_success: Some(at),
        }
    }

    pub fn unknown() -> Self {
        Self {
            state: HealthState::Unknown,
            last_success: None,
        }
    }

    /// Re-evaluates freshness without mutating the original observation.
    pub fn effective_state(&self, now: SystemTime) -> HealthState {
        if !self.state.is_measured() {
            return HealthState::Unknown;
        }

        match self.last_success {
            Some(at) => match now.duration_since(at) {
                Ok(age) if age < STATUS_MAX_AGE => self.state,
                _ => HealthState::Unknown,
            },
            None => HealthState::Unknown,
        }
    }

    pub fn reevaluated(&self, now: SystemTime) -> Self {
        Self {
            state: self.effective_state(now),
            last_success: self.last_success,
        }
    }
}

/// Pure freshness evaluation. Missing or stale evidence remains UNKNOWN.
pub fn evaluate_component_status(
    last_success: Option<SystemTime>,
    now: SystemTime,
) -> ComponentStatus {
    match last_success {
        Some(at) => match now.duration_since(at) {
            Ok(age) if age < STATUS_MAX_AGE => ComponentStatus::measured_at(HealthState::Ok, at),
            _ => ComponentStatus::unknown(),
        },
        None => ComponentStatus::unknown(),
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StatusLineInput {
    pub now: SystemTime,
    pub grid: ComponentStatus,
    pub retina: ComponentStatus,
    pub entityos: ComponentStatus,
    pub omnipool: ComponentStatus,
}

impl Default for StatusLineInput {
    fn default() -> Self {
        Self {
            now: SystemTime::UNIX_EPOCH,
            grid: ComponentStatus::unknown(),
            retina: ComponentStatus::unknown(),
            entityos: ComponentStatus::unknown(),
            omnipool: ComponentStatus::unknown(),
        }
    }
}

/// Formats the compact status line used by the UI.
///
/// MEASURED/OK -> "ok"; a measured degraded observation -> "degraded";
/// missing or stale evidence -> "UNKNOWN".
pub fn format_status_line(input: &StatusLineInput) -> String {
    format_status_line_at(
        input.now,
        &input.grid,
        &input.retina,
        &input.entityos,
        &input.omnipool,
    )
}

pub fn format_status_line_at(
    now: SystemTime,
    grid: &ComponentStatus,
    retina: &ComponentStatus,
    entityos: &ComponentStatus,
    omnipool: &ComponentStatus,
) -> String {
    [
        component_label("GRID", grid.effective_state(now)),
        component_label("Retina", retina.effective_state(now)),
        component_label("EntityOS", entityos.effective_state(now)),
        component_label("Omnipool", omnipool.effective_state(now)),
    ]
    .join(" | ")
}

/// Explicit epistemic-class rendering for logs and machine-readable surfaces.
pub fn format_status_line_labeled(input: &StatusLineInput) -> String {
    format_status_line_labeled_at(
        input.now,
        &input.grid,
        &input.retina,
        &input.entityos,
        &input.omnipool,
    )
}

pub fn format_status_line_labeled_at(
    now: SystemTime,
    grid: &ComponentStatus,
    retina: &ComponentStatus,
    entityos: &ComponentStatus,
    omnipool: &ComponentStatus,
) -> String {
    [
        component_class_label("GRID", grid.effective_state(now)),
        component_class_label("Retina", retina.effective_state(now)),
        component_class_label("EntityOS", entityos.effective_state(now)),
        component_class_label("Omnipool", omnipool.effective_state(now)),
    ]
    .join(" | ")
}

fn component_label(name: &str, state: HealthState) -> String {
    match state {
        HealthState::Ok => format!("{name} ok"),
        HealthState::Degraded => format!("{name} degraded"),
        HealthState::Unknown => format!("{name} UNKNOWN"),
    }
}

fn component_class_label(name: &str, state: HealthState) -> String {
    match state {
        HealthState::Ok | HealthState::Degraded => format!("{name} MEASURED"),
        HealthState::Unknown => format!("{name} UNKNOWN"),
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GridEndpoint {
    host: IpAddr,
    port: u16,
}

impl GridEndpoint {
    /// Only the literal `127.0.0.1` is admissible.
    pub fn new(host: &str, port: u16) -> Result<Self, GridError> {
        let parsed: IpAddr = host.parse().map_err(|_| {
            GridError::InvalidPort(format!(
                "host must be the literal {GRID_HOST}, got {host:?}"
            ))
        })?;

        if parsed != IpAddr::V4(Ipv4Addr::LOCALHOST) {
            return Err(GridError::InvalidPort(format!(
                "host must be the literal {GRID_HOST}, got {host:?}"
            )));
        }

        if port == 0 {
            return Err(GridError::InvalidPort(
                "port must be between 1 and 65535".to_owned(),
            ));
        }

        Ok(Self {
            host: parsed,
            port,
        })
    }

    pub fn from_port(port: u16) -> Result<Self, GridError> {
        Self::new(GRID_HOST, port)
    }

    pub fn host(&self) -> IpAddr {
        self.host
    }

    pub fn port(&self) -> u16 {
        self.port
    }

    pub fn socket_addr(&self) -> SocketAddr {
        SocketAddr::new(self.host, self.port)
    }

    pub fn authority(&self) -> String {
        format!("{}:{}", self.host, self.port)
    }
}

impl fmt::Display for GridEndpoint {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.authority())
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GridPaths {
    pub health: String,
    pub event: String,
}

impl GridPaths {
    pub fn new(health: impl Into<String>, event: impl Into<String>) -> Self {
        Self {
            health: health.into(),
            event: event.into(),
        }
    }

    fn validate(&self) -> Result<(), GridError> {
        for path in [&self.health, &self.event] {
            if !path.starts_with('/') || path.contains('\r') || path.contains('\n') {
                return Err(GridError::InvalidPath(path.clone()));
            }
        }
        Ok(())
    }
}

impl Default for GridPaths {
    fn default() -> Self {
        Self {
            health: "/health".to_owned(),
            event: "/event".to_owned(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GridHttpRequest {
    pub method: String,
    pub path: String,
    pub body: Option<Vec<u8>>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GridHttpResponse {
    pub status: u16,
    pub body: Vec<u8>,
}

impl GridHttpResponse {
    pub fn ok(body: impl Into<Vec<u8>>) -> Self {
        Self {
            status: 200,
            body: body.into(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Error)]
#[error("{message}")]
pub struct GridTransportError {
    pub message: String,
}

impl GridTransportError {
    pub fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

/// Transport seam permits deterministic mocked HTTP tests.
pub trait GridTransport: Send + Sync {
    fn request(&self, request: &GridHttpRequest) -> Result<GridHttpResponse, GridTransportError>;
}

#[derive(Debug, Error)]
pub enum GridError {
    #[error("invalid GRID port: {0}")]
    InvalidPort(String),
    #[error("invalid GRID path: {0}")]
    InvalidPath(String),
    #[error("GRID transport failed: {0}")]
    Transport(#[from] GridTransportError),
    #[error("could not encode GRID event: {0}")]
    Serialization(#[from] serde_json::Error),
    #[error("GRID rejected event with HTTP {status}: {body}")]
    Rejected { status: u16, body: String },
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct GridEvent {
    pub kind: String,
    #[serde(default)]
    pub payload: Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,
}

impl GridEvent {
    pub fn new(kind: impl Into<String>, payload: Value) -> Self {
        Self {
            kind: kind.into(),
            payload,
            source: None,
        }
    }

    pub fn with_source(mut self, source: impl Into<String>) -> Self {
        self.source = Some(source.into());
        self
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GridPushReceipt {
    pub http_status: u16,
    pub accepted: bool,
}

#[derive(Clone)]
pub struct GridClient {
    endpoint: GridEndpoint,
    paths: GridPaths,
    transport: Arc<dyn GridTransport>,
}

impl GridClient {
    pub fn new(port: u16) -> Result<Self, GridError> {
        let endpoint = GridEndpoint::from_port(port)?;
        let transport = TcpGridTransport::new(endpoint.clone())?;
        Ok(Self {
            endpoint,
            paths: GridPaths::default(),
            transport: Arc::new(transport),
        })
    }

    pub fn from_env() -> Result<Self, GridError> {
        let port = grid_port_from_env()?;
        Self::new(port)
    }

    pub fn with_transport<T>(port: u16, transport: T) -> Result<Self, GridError>
    where
        T: GridTransport + 'static,
    {
        Self::with_endpoint(GridEndpoint::from_port(port)?, transport)
    }

    pub fn from_env_with_transport<T>(transport: T) -> Result<Self, GridError>
    where
        T: GridTransport + 'static,
    {
        let port = grid_port_from_env()?;
        Self::with_transport(port, transport)
    }

    pub fn with_endpoint<T>(endpoint: GridEndpoint, transport: T) -> Result<Self, GridError>
    where
        T: GridTransport + 'static,
    {
        Self::with_shared_transport(endpoint, GridPaths::default(), Arc::new(transport))
    }

    pub fn with_shared_transport(
        endpoint: GridEndpoint,
        paths: GridPaths,
        transport: Arc<dyn GridTransport>,
    ) -> Result<Self, GridError> {
        paths.validate()?;
        Ok(Self {
            endpoint,
            paths,
            transport,
        })
    }

    pub fn endpoint(&self) -> &GridEndpoint {
        &self.endpoint
    }

    pub fn paths(&self) -> &GridPaths {
        &self.paths
    }

    pub fn check_health(&self) -> GridHealth {
        self.check_health_at(SystemTime::now())
    }

    pub fn check_health_at(&self, now: SystemTime) -> GridHealth {
        let request = GridHttpRequest {
            method: "GET".to_owned(),
            path: self.paths.health.clone(),
            body: None,
        };

        let observation = match self.transport.request(&request) {
            Ok(response) => HealthObservation::Response(response),
            Err(error) => HealthObservation::Unreachable {
                reason: error.message,
            },
        };

        evaluate_health(observation, now)
    }

    pub fn push_event(&self, event: &GridEvent) -> Result<GridPushReceipt, GridError> {
        let body = serde_json::to_vec(event)?;
        let request = GridHttpRequest {
            method: "POST".to_owned(),
            path: self.paths.event.clone(),
            body: Some(body),
        };

        let response = self.transport.request(&request)?;
        if !(200..300).contains(&response.status) {
            let mut body = String::from_utf8_lossy(&response.body).into_owned();
            body.truncate(512);
            return Err(GridError::Rejected {
                status: response.status,
                body,
            });
        }

        Ok(GridPushReceipt {
            http_status: response.status,
            accepted: true,
        })
    }
}

/// Reads the GRID port from the environment, defaulting to 8490.
pub fn grid_port_from_env() -> Result<u16, GridError> {
    match std::env::var(GRID_PORT_ENV) {
        Ok(value) => {
            let port = value
                .parse::<u16>()
                .map_err(|_| GridError::InvalidPort(format!("{GRID_PORT_ENV}={value:?}")))?;
            if port == 0 {
                return Err(GridError::InvalidPort(format!(
                    "{GRID_PORT_ENV}={value:?} must be between 1 and 65535"
                )));
            }
            Ok(port)
        }
        Err(_) => Ok(DEFAULT_GRID_PORT),
    }
}

#[derive(Debug, Clone)]
pub enum HealthObservation {
    Response(GridHttpResponse),
    Unreachable { reason: String },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GridHealth {
    pub status: ComponentStatus,
    pub http_status: Option<u16>,
    pub detail: Option<String>,
}

impl GridHealth {
    pub fn state_at(&self, now: SystemTime) -> HealthState {
        self.status.effective_state(now)
    }
}

/// Pure health evaluation. A reachable but unhealthy GRID is DEGRADED;
/// inability to obtain a response is UNKNOWN.
pub fn evaluate_health(observation: HealthObservation, now: SystemTime) -> GridHealth {
    match observation {
        HealthObservation::Response(response) => {
            let detail = String::from_utf8_lossy(&response.body).into_owned();
            let state = if (200..300).contains(&response.status) {
                if response_indicates_degraded(&response.body) {
                    HealthState::Degraded
                } else {
                    HealthState::Ok
                }
            } else {
                HealthState::Degraded
            };

            GridHealth {
                status: ComponentStatus::measured_at(state, now),
                http_status: Some(response.status),
                detail: Some(detail),
            }
        }
        HealthObservation::Unreachable { reason } => GridHealth {
            status: ComponentStatus::unknown(),
            http_status: None,
            detail: Some(reason),
        },
    }
}

fn response_indicates_degraded(body: &[u8]) -> bool {
    let Ok(value) = serde_json::from_slice::<Value>(body) else {
        return false;
    };

    let status_degraded = ["status", "health", "state"]
        .iter()
        .filter_map(|key| value.get(*key))
        .filter_map(Value::as_str)
        .any(|text| text.eq_ignore_ascii_case("degraded"));

    let explicit_degraded = ["degraded", "is_degraded"]
        .iter()
        .filter_map(|key| value.get(*key))
        .any(|flag| flag.as_bool().unwrap_or(false));

    let explicit_not_ok = matches!(value.get("ok"), Some(Value::Bool(false)));

    status_degraded || explicit_degraded || explicit_not_ok
}

/// Minimal HTTP/1.1 transport restricted to a validated loopback endpoint.
#[derive(Debug, Clone)]
pub struct TcpGridTransport {
    endpoint: GridEndpoint,
    timeout: Duration,
}

impl TcpGridTransport {
    pub fn new(endpoint: GridEndpoint) -> Result<Self, GridError> {
        // Re-check at the socket boundary. GridEndpoint fields are private, but
        // this keeps the safety property local to the network implementation.
        if endpoint.host != IpAddr::V4(Ipv4Addr::LOCALHOST) {
            return Err(GridError::InvalidPort(format!(
                "host must be the literal {GRID_HOST}"
            )));
        }
        Ok(Self {
            endpoint,
            timeout: DEFAULT_TIMEOUT,
        })
    }

    pub fn with_timeout(mut self, timeout: Duration) -> Self {
        self.timeout = timeout;
        self
    }
}

impl GridTransport for TcpGridTransport {
    fn request(&self, request: &GridHttpRequest) -> Result<GridHttpResponse, GridTransportError> {
        if self.endpoint.host != IpAddr::V4(Ipv4Addr::LOCALHOST) {
            return Err(GridTransportError::new(
                "refusing non-loopback GRID transport",
            ));
        }

        if request.path.contains('\r') || request.path.contains('\n') {
            return Err(GridTransportError::new("invalid HTTP request path"));
        }

        let body = request.body.as_deref().unwrap_or(&[]);
        if body.len() > MAX_REQUEST_BYTES {
            return Err(GridTransportError::new("GRID request body exceeds limit"));
        }

        let mut stream = TcpStream::connect_timeout(&self.endpoint.socket_addr(), self.timeout)
            .map_err(|error| GridTransportError::new(format!("connect failed: {error}")))?;

        stream
            .set_read_timeout(Some(self.timeout))
            .map_err(|error| GridTransportError::new(format!("read timeout setup failed: {error}")))?;
        stream
            .set_write_timeout(Some(self.timeout))
            .map_err(|error| {
                GridTransportError::new(format!("write timeout setup failed: {error}"))
            })?;

        let mut wire = Vec::with_capacity(256 + body.len());
        wire.extend_from_slice(
            format!(
                "{} {} HTTP/1.1\r\nHost: {}\r\nAccept: application/json\r\nConnection: close\r\n",
                request.method,
                request.path,
                self.endpoint.authority()
            )
            .as_bytes(),
        );
        if !body.is_empty() {
            wire.extend_from_slice(b"Content-Type: application/json\r\n");
        }
        wire.extend_from_slice(format!("Content-Length: {}\r\n\r\n", body.len()).as_bytes());
        wire.extend_from_slice(body);

        stream
            .write_all(&wire)
            .map_err(|error| GridTransportError::new(format!("write failed: {error}")))?;
        stream
            .flush()
            .map_err(|error| GridTransportError::new(format!("flush failed: {error}")))?;

        read_http_response(&mut stream)
    }
}

fn read_http_response(stream: &mut TcpStream) -> Result<GridHttpResponse, GridTransportError> {
    let mut buffer = Vec::with_capacity(4096);
    let mut chunk = [0_u8; 4096];

    let header_end = loop {
        if let Some(position) = find_header_end(&buffer) {
            break position;
        }
        if buffer.len() >= MAX_HEADER_BYTES {
            return Err(GridTransportError::new("HTTP headers exceed limit"));
        }

        let count = stream
            .read(&mut chunk)
            .map_err(|error| GridTransportError::new(format!("read failed: {error}")))?;
        if count == 0 {
            return Err(GridTransportError::new(
                "connection closed before HTTP headers were complete",
            ));
        }
        buffer.extend_from_slice(&chunk[..count]);
    };

    let body_start = header_end + 4;
    let header_text = String::from_utf8_lossy(&buffer[..header_end]);
    let mut lines = header_text.split("\r\n");
    let status_line = lines
        .next()
        .ok_or_else(|| GridTransportError::new("missing HTTP status line"))?;
    let status = status_line
        .split_whitespace()
        .nth(1)
        .and_then(|value| value.parse::<u16>().ok())
        .ok_or_else(|| GridTransportError::new("invalid HTTP status line"))?;

    let content_length = lines.find_map(|line| {
        let (name, value) = line.split_once(':')?;
        if name.trim().eq_ignore_ascii_case("content-length") {
            value.trim().parse::<usize>().ok()
        } else {
            None
        }
    });

    match content_length {
        Some(length) => {
            if length > MAX_RESPONSE_BYTES {
                return Err(GridTransportError::new("HTTP response body exceeds limit"));
            }

            let available = buffer.len().saturating_sub(body_start);
            let mut body = Vec::with_capacity(length);
            body.extend_from_slice(&buffer[body_start..(body_start + available).min(buffer.len())]);

            if body.len() < length {
                let mut remaining = vec![0_u8; length - body.len()];
                stream.read_exact(&mut remaining).map_err(|error| {
                    GridTransportError::new(format!("incomplete HTTP body: {error}"))
                })?;
                body.extend_from_slice(&remaining);
            }

            body.truncate(length);
            Ok(GridHttpResponse { status, body })
        }
        None => {
            let mut body = buffer[body_start..].to_vec();
            let mut rest = Vec::new();
            let limit = MAX_RESPONSE_BYTES.saturating_sub(body.len()) as u64;
            stream
                .take(limit)
                .read_to_end(&mut rest)
                .map_err(|error| GridTransportError::new(format!("read body failed: {error}")))?;
            body.extend_from_slice(&rest);

            if body.len() > MAX_RESPONSE_BYTES {
                return Err(GridTransportError::new("HTTP response body exceeds limit"));
            }

            Ok(GridHttpResponse { status, body })
        }
    }
}

fn find_header_end(buffer: &[u8]) -> Option<usize> {
    buffer.windows(4).position(|window| window == b"\r\n\r\n")
}

#[cfg(test)]
#[path = "grid_test.rs"]
mod tests;
