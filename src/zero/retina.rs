//! src/zero/retina.rs
//! Machine God's own Retina eye.
//!
//! GRF / `ClayCode` surface (spec):
//! ```text
//! module retina {
//!   architecture Retina {
//!     stateAuthority unified.db(kind='retina') + GRID(perception event)
//!     path cli(retina-frage --zeile) -> parse_line -> GRID push -> unified.db insert
//!   }
//!   invariant loopback_only        { grid_host == "127.0.0.1" ON_VIOLATION -> TriggerEmergencyDeescalation }
//!   invariant one_reading_per_call { grid_events <= 1 AND db_rows <= 1 ON_VIOLATION -> TriggerEmergencyDeescalation }
//!   invariant no_invented_reading  { cli_missing_or_failed -> RETINA_UNAVAILABLE_DE ON_VIOLATION -> TriggerEmergencyDeescalation }
//!   invariant kind_is_retina       { db.kind == "retina" ON_VIOLATION -> TriggerEmergencyDeescalation }
//!   fn read_and_push(cfg) { E_t = cli stdout; R_t = {reading, grid_event, db_row}; F = read_and_push }
//! }
//! ```
//!
//! Contract (`R_t` = realised state, `E_t` = evidence, F = transition):
//! * `E_t` = stdout of the local `retina-frage --zeile` process (text layers only, no images).
//! * `R_t` = the one-line reading plus exactly one GRID perception event and at most one
//!   unified.db row with kind='retina'.
//! * F = `read_and_push`: deterministic ordering, one reading per call, fail-closed.
//! * Missing/failed CLI => honest "Retina nicht verfuegbar"; never invented content.
//! * GRID target is loopback-only (127.0.0.1). Non-loopback URLs are rejected in code,
//!   before any socket operation.
//! * unified.db rows are written through the local `sqlite3` executable (no linked
//!   `SQLite` driver exists in the available crate set). If that executable is absent the
//!   write fails closed instead of pretending that a row exists.

use std::io::Write;
use std::net::{Ipv4Addr, SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use thiserror::Error;

/// Honest German unavailability sentence (fixed; never invented content).
pub const RETINA_UNAVAILABLE_DE: &str = "Retina nicht verfuegbar";
/// Default GRID port.
pub const DEFAULT_GRID_PORT: u16 = 8490;
/// Retina CLI binary name.
pub const RETINA_CLI: &str = "retina-frage";
/// Environment variable holding the GRID port.
pub const GRID_PORT_ENV: &str = "MACHINE_GOD_GRID_PORT";
/// Optional environment variable holding a full GRID URL (loopback only).
pub const GRID_URL_ENV: &str = "MACHINE_GOD_GRID_URL";
/// Environment variable holding the unified.db path.
pub const UNIFIED_DB_ENV: &str = "MACHINE_GOD_UNIFIED_DB";
/// Environment variable holding the sqlite executable used for unified.db writes.
pub const SQLITE_BIN_ENV: &str = "MACHINE_GOD_SQLITE_BIN";
/// `EntityOS` memory table used for retina rows.
pub const DB_TABLE: &str = "memory";
/// Hard-coded row kind for retina readings.
pub const RETINA_KIND: &str = "retina";
/// GRID connect/write timeout (local only).
pub const GRID_TIMEOUT_MS: u64 = 2000;

/// Compound variable: a Retina reading with epistemic tag.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum RetinaReading {
    /// One-line state from `retina-frage --zeile`.
    Line { line: String, raw: String, ts_ms: u64 },
    /// Honest unavailability marker (UNKNOWN, not a measurement).
    Unavailable { reason: String, ts_ms: u64 },
}

/// Compound variable: GRID perception event.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct GridEvent {
    pub kind: String,
    pub source: String,
    pub r#type: String,
    pub payload: serde_json::Value,
    pub timestamp_ms: u64,
    pub host: String,
    pub port: u16,
}

/// Compound variable: unified.db insert record.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct DbInsert {
    pub kind: String,
    pub payload: String,
    pub sql: String,
    pub ts_ms: u64,
}

/// Compound variable: admissible GRID target (loopback only).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GridTarget {
    pub host: String,
    pub port: u16,
}

/// Configuration for the Retina organ.
#[derive(Debug, Clone)]
pub struct RetinaConfig {
    pub cli_path: PathBuf,
    pub grid_host: String,
    pub grid_port: u16,
    pub db_path: PathBuf,
}

impl Default for RetinaConfig {
    fn default() -> Self {
        Self {
            cli_path: PathBuf::from(RETINA_CLI),
            grid_host: "127.0.0.1".to_owned(),
            grid_port: DEFAULT_GRID_PORT,
            db_path: PathBuf::from("unified.db"),
        }
    }
}

impl RetinaConfig {
    /// Build a configuration from the environment.
    ///
    /// `MACHINE_GOD_GRID_URL` (optional, loopback only) and `MACHINE_GOD_GRID_PORT`
    /// (default 8490) select the GRID target. A non-loopback URL is rejected.
    pub fn from_env() -> Result<Self, RetinaError> {
        let url = std::env::var(GRID_URL_ENV).ok().filter(|v| !v.trim().is_empty());
        let port = std::env::var(GRID_PORT_ENV).ok().filter(|v| !v.trim().is_empty());
        let target = grid_target_from_parts(url.as_deref(), port.as_deref())?;
        Ok(Self {
            cli_path: PathBuf::from(RETINA_CLI),
            grid_host: target.host,
            grid_port: target.port,
            db_path: db_path_from_env(),
        })
    }
}

/// Errors raised by the Retina organ. Fail-closed: never invent readings.
#[derive(Debug, Error)]
pub enum RetinaError {
    #[error("Retina nicht verfuegbar (CLI not found: {})", .0.display())]
    CliNotFound(PathBuf),
    #[error("Retina nicht verfuegbar (CLI failed: {0})")]
    CliFailed(String),
    #[error("grid push failed: {0}")]
    GridPush(String),
    #[error("db write failed: {0}")]
    DbWrite(String),
    #[error("loopback violation: grid host must be 127.0.0.1, got {0}")]
    LoopbackViolation(String),
    #[error("parse failed: {0}")]
    ParseFailed(String),
}

/// Wall-clock milliseconds. Used for timestamps only, never as a causal clock.
pub fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| u64::try_from(d.as_millis()).unwrap_or(u64::MAX))
        .unwrap_or(0)
}

/// unified.db path from the environment (default: relative `unified.db`).
pub fn db_path_from_env() -> PathBuf {
    std::env::var_os(UNIFIED_DB_ENV).map_or_else(|| PathBuf::from("unified.db"), PathBuf::from)
}

/// sqlite executable used for unified.db writes.
pub fn sqlite_binary() -> PathBuf {
    std::env::var_os(SQLITE_BIN_ENV).map_or_else(|| PathBuf::from("sqlite3"), PathBuf::from)
}

/// Pure: parse `retina-frage --zeile` output into a tagged reading.
pub fn parse_line_at(raw: &str, ts_ms: u64) -> RetinaReading {
    let raw = raw.trim_end().to_owned();
    let line = raw.lines().next().unwrap_or("").trim().to_owned();
    if line.is_empty() {
        RetinaReading::Unavailable { reason: "empty zeile output".to_owned(), ts_ms }
    } else {
        RetinaReading::Line { line, raw, ts_ms }
    }
}

/// Parse `retina-frage --zeile` output into a tagged reading (timestamped now).
pub fn parse_line(raw: &str) -> RetinaReading {
    parse_line_at(raw, now_ms())
}

/// Pure: build a GRID perception event from a reading and an admissible target.
pub fn build_grid_event_at(reading: &RetinaReading, target: &GridTarget, ts_ms: u64) -> GridEvent {
    let payload = match reading {
        RetinaReading::Line { line, raw, .. } => serde_json::json!({
            "zeile": line,
            "raw": raw,
        }),
        RetinaReading::Unavailable { reason, .. } => serde_json::json!({
            "unavailable": true,
            "reason": reason,
        }),
    };
    GridEvent {
        kind: "perception".to_owned(),
        source: "retina".to_owned(),
        r#type: "retina_reading".to_owned(),
        payload,
        timestamp_ms: ts_ms,
        host: target.host.clone(),
        port: target.port,
    }
}

/// Build a GRID perception event for a target (timestamped now).
pub fn build_grid_event_for(reading: &RetinaReading, target: &GridTarget) -> GridEvent {
    build_grid_event_at(reading, target, now_ms())
}

/// Build a GRID perception event from a reading. Host/port come from config.
pub fn build_grid_event(reading: &RetinaReading, cfg: &RetinaConfig) -> GridEvent {
    let target = GridTarget { host: cfg.grid_host.clone(), port: cfg.grid_port };
    build_grid_event_for(reading, &target)
}

/// Pure: build the unified.db insert record. Kind is hard-coded 'retina'.
pub fn build_db_insert_at(reading: &RetinaReading, ts_ms: u64) -> DbInsert {
    let payload = serde_json::to_string(reading).unwrap_or_else(|_| "{}".to_owned());
    let sql = format!(
        "INSERT INTO {DB_TABLE} (kind, payload, ts_ms) VALUES ('{RETINA_KIND}', '{}', {});",
        escape_sql(&payload),
        ts_ms
    );
    DbInsert { kind: RETINA_KIND.to_owned(), payload, sql, ts_ms }
}

/// Build the unified.db insert record (timestamped now).
pub fn build_db_insert(reading: &RetinaReading) -> DbInsert {
    build_db_insert_at(reading, now_ms())
}

fn escape_sql(s: &str) -> String {
    s.replace('\'', "''")
}

/// Pure: hard loopback rule. Only the literal 127.0.0.1 is admitted.
pub fn enforce_loopback(host: &str) -> bool {
    host == "127.0.0.1"
}

/// Pure: parse a GRID URL/authority into an admissible loopback target.
///
/// Accepted: `http://127.0.0.1:8490`, `udp://127.0.0.1:8490`, `127.0.0.1:8490`,
/// `http://127.0.0.1` (default port 8490). Everything else is rejected; a
/// non-loopback host yields `RetinaError::LoopbackViolation`.
pub fn parse_grid_url(url: &str) -> Result<GridTarget, RetinaError> {
    let trimmed = url.trim();
    if trimmed.is_empty() {
        return Err(RetinaError::ParseFailed("empty GRID URL".to_owned()));
    }
    let without_scheme = match trimmed.split_once("://") {
        Some((scheme, rest)) => {
            if !scheme.eq_ignore_ascii_case("http") && !scheme.eq_ignore_ascii_case("udp") {
                return Err(RetinaError::ParseFailed(format!("unsupported GRID scheme: {scheme}")));
            }
            rest
        }
        None => trimmed,
    };
    let authority = without_scheme.split('/').next().unwrap_or("").trim();
    if authority.is_empty() {
        return Err(RetinaError::ParseFailed("missing GRID host".to_owned()));
    }
    let (host, port) = match authority.rsplit_once(':') {
        Some((host, port_text)) => {
            let port = port_text
                .parse::<u16>()
                .map_err(|_| RetinaError::ParseFailed(format!("invalid GRID port: {port_text}")))?;
            if port == 0 {
                return Err(RetinaError::ParseFailed(
                    "GRID port must be greater than zero".to_owned(),
                ));
            }
            (host.to_owned(), port)
        }
        None => (authority.to_owned(), DEFAULT_GRID_PORT),
    };
    if !enforce_loopback(&host) {
        return Err(RetinaError::LoopbackViolation(host));
    }
    Ok(GridTarget { host, port })
}

/// Pure: combine optional GRID URL and optional port into an admissible target.
/// The explicit port wins over the port embedded in the URL.
pub fn grid_target_from_parts(
    url: Option<&str>,
    port: Option<&str>,
) -> Result<GridTarget, RetinaError> {
    let mut target = GridTarget { host: "127.0.0.1".to_owned(), port: DEFAULT_GRID_PORT };
    if let Some(url) = url {
        target = parse_grid_url(url)?;
    }
    if let Some(port) = port {
        let trimmed = port.trim();
        let parsed = trimmed
            .parse::<u16>()
            .map_err(|_| RetinaError::ParseFailed(format!("invalid {GRID_PORT_ENV}: {trimmed}")))?;
        if parsed == 0 {
            return Err(RetinaError::ParseFailed(format!(
                "{GRID_PORT_ENV} must be greater than zero"
            )));
        }
        target.port = parsed;
    }
    Ok(target)
}

/// Run an already-configured `Command` and capture stdout. Fails closed on error.
pub fn run_line_command(cmd: &mut Command) -> Result<String, RetinaError> {
    let program = cmd.get_program().to_os_string();
    let output = cmd.output().map_err(|e| {
        if e.kind() == std::io::ErrorKind::NotFound {
            RetinaError::CliNotFound(PathBuf::from(program))
        } else {
            RetinaError::CliFailed(e.to_string())
        }
    })?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_owned();
        return Err(RetinaError::CliFailed(if stderr.is_empty() {
            format!("exit status {}", output.status)
        } else {
            stderr
        }));
    }
    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

/// Spawn `retina-frage --zeile` and capture stdout. Fails closed on missing/broken CLI.
pub fn spawn_retina_line(cfg: &RetinaConfig) -> Result<String, RetinaError> {
    if !cfg.cli_path.exists() {
        return Err(RetinaError::CliNotFound(cfg.cli_path.clone()));
    }
    let mut cmd = Command::new(&cfg.cli_path);
    cmd.arg("--zeile");
    run_line_command(&mut cmd)
}

/// Push a GRID event to the local GRID. Loopback is enforced before any socket operation.
pub fn push_grid_event(event: &GridEvent, cfg: &RetinaConfig) -> Result<(), RetinaError> {
    push_grid_event_to(event, &cfg.grid_host, cfg.grid_port)
}

/// Push a GRID event to an explicit loopback target (newline-delimited JSON).
pub fn push_grid_event_to(event: &GridEvent, host: &str, port: u16) -> Result<(), RetinaError> {
    if !enforce_loopback(host) {
        return Err(RetinaError::LoopbackViolation(host.to_owned()));
    }
    let payload = serde_json::to_string(event).map_err(|e| RetinaError::GridPush(e.to_string()))?;
    let addr = SocketAddr::from((Ipv4Addr::LOCALHOST, port));
    let timeout = Duration::from_millis(GRID_TIMEOUT_MS);
    let mut stream = TcpStream::connect_timeout(&addr, timeout)
        .map_err(|e| RetinaError::GridPush(format!("connect {addr}: {e}")))?;
    let _ = stream.set_write_timeout(Some(timeout));
    stream.write_all(payload.as_bytes()).map_err(|e| RetinaError::GridPush(e.to_string()))?;
    stream.write_all(b"\n").map_err(|e| RetinaError::GridPush(e.to_string()))?;
    stream.flush().map_err(|e| RetinaError::GridPush(e.to_string()))?;
    Ok(())
}

/// Sink contract for `EntityOS` memory writes (mockable in tests).
pub trait RetinaDb {
    fn insert(&mut self, insert: &DbInsert) -> Result<(), RetinaError>;
}

/// Sink contract for the local GRID (mockable in tests).
pub trait GridSink {
    fn push(&mut self, event: &GridEvent) -> Result<(), RetinaError>;
}

/// Source contract for the local Retina CLI (mockable in tests).
pub trait RetinaCli {
    fn read_line_reading(&mut self) -> Result<String, RetinaError>;
}

/// Production CLI source: local `retina-frage --zeile` subprocess.
#[derive(Debug, Clone)]
pub struct ProcessCli {
    pub cfg: RetinaConfig,
}

impl RetinaCli for ProcessCli {
    fn read_line_reading(&mut self) -> Result<String, RetinaError> {
        spawn_retina_line(&self.cfg)
    }
}

/// Production GRID sink: loopback TCP push.
#[derive(Debug, Clone)]
pub struct UdpGridSink {
    pub cfg: RetinaConfig,
}

impl GridSink for UdpGridSink {
    fn push(&mut self, event: &GridEvent) -> Result<(), RetinaError> {
        push_grid_event(event, &self.cfg)
    }
}

/// Production `EntityOS` sink: unified.db row via the local `sqlite3` executable.
///
/// No linked `SQLite` driver is available in the crate set, so the write goes through
/// the local sqlite3 binary. If that binary is missing the write fails closed.
#[derive(Debug, Clone)]
pub struct SqliteDb {
    pub db_path: PathBuf,
    pub sqlite_bin: PathBuf,
}

impl SqliteDb {
    pub fn new(db_path: impl Into<PathBuf>) -> Self {
        Self { db_path: db_path.into(), sqlite_bin: sqlite_binary() }
    }

    pub fn with_binary(db_path: impl Into<PathBuf>, sqlite_bin: impl Into<PathBuf>) -> Self {
        Self { db_path: db_path.into(), sqlite_bin: sqlite_bin.into() }
    }
}

impl RetinaDb for SqliteDb {
    fn insert(&mut self, insert: &DbInsert) -> Result<(), RetinaError> {
        if insert.kind != RETINA_KIND {
            return Err(RetinaError::DbWrite(format!("refusing non-retina kind: {}", insert.kind)));
        }
        let bin = self.sqlite_bin.clone();
        let db_path = self.db_path.clone();
        let sql = format!(
            "CREATE TABLE IF NOT EXISTS {DB_TABLE} (kind TEXT NOT NULL, payload TEXT NOT NULL, ts_ms INTEGER NOT NULL); {}",
            insert.sql
        );
        let output =
            Command::new(&bin).arg("--batch").arg(&db_path).arg(&sql).output().map_err(|e| {
                if e.kind() == std::io::ErrorKind::NotFound {
                    RetinaError::DbWrite(format!("sqlite executable not found: {}", bin.display()))
                } else {
                    RetinaError::DbWrite(e.to_string())
                }
            })?;
        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr).trim().to_owned();
            return Err(RetinaError::DbWrite(if stderr.is_empty() {
                format!("sqlite exit status {}", output.status)
            } else {
                stderr
            }));
        }
        Ok(())
    }
}

/// Write one insert record to unified.db (kind='retina').
pub fn write_db_insert(insert: &DbInsert, db_path: &Path) -> Result<(), RetinaError> {
    let mut db = SqliteDb::new(db_path.to_path_buf());
    db.insert(insert)
}

/// Compound runtime: the three sinks of one Retina transition.
pub struct RetinaRuntime<'a> {
    pub target: GridTarget,
    pub cli: &'a mut dyn RetinaCli,
    pub grid: &'a mut dyn GridSink,
    pub db: &'a mut dyn RetinaDb,
}

/// Transition F: read one line, publish one event, write one row.
///
/// Empty CLI output is UNKNOWN, not a measurement: it is returned as
/// `RetinaReading::Unavailable` and is not published. A missing or failed CLI is an
/// error (fail-closed) and nothing is published.
pub fn read_and_push_with(rt: &mut RetinaRuntime<'_>) -> Result<RetinaReading, RetinaError> {
    let raw = rt.cli.read_line_reading()?;
    let reading = parse_line(&raw);
    if matches!(reading, RetinaReading::Unavailable { .. }) {
        return Ok(reading);
    }
    let event = build_grid_event_for(&reading, &rt.target);
    rt.grid.push(&event)?;
    let insert = build_db_insert(&reading);
    rt.db.insert(&insert)?;
    Ok(reading)
}

/// Read one zeile, push to GRID and DB using the production sinks.
/// CLI failures are surfaced as errors (fail-closed).
pub fn read_and_push_strict(cfg: &RetinaConfig) -> Result<RetinaReading, RetinaError> {
    let mut cli = ProcessCli { cfg: cfg.clone() };
    let mut grid = UdpGridSink { cfg: cfg.clone() };
    let mut db = SqliteDb::new(cfg.db_path.clone());
    let mut rt = RetinaRuntime {
        target: GridTarget { host: cfg.grid_host.clone(), port: cfg.grid_port },
        cli: &mut cli,
        grid: &mut grid,
        db: &mut db,
    };
    read_and_push_with(&mut rt)
}

/// Read one zeile, push to GRID and DB.
///
/// A missing or failed CLI yields the honest `RetinaReading::Unavailable` marker with
/// reason "Retina nicht verfuegbar" (never invented content). GRID/DB failures remain
/// errors so that a broken sink cannot be mistaken for a measurement.
pub fn read_and_push(cfg: &RetinaConfig) -> Result<RetinaReading, RetinaError> {
    match read_and_push_strict(cfg) {
        Ok(reading) => Ok(reading),
        Err(RetinaError::CliNotFound(_) | RetinaError::CliFailed(_)) => {
            Ok(RetinaReading::Unavailable {
                reason: RETINA_UNAVAILABLE_DE.to_owned(),
                ts_ms: now_ms(),
            })
        }
        Err(other) => Err(other),
    }
}

/// Read one zeile, push to GRID and DB, return the user-visible text.
pub fn read_and_push_text(cfg: &RetinaConfig) -> Result<String, RetinaError> {
    Ok(reading_text(&read_and_push(cfg)?))
}

/// Honest context text for ground mode / full agent.
///
/// Returns the measured one-line state, or the fixed sentence
/// "Retina nicht verfuegbar" when the CLI is missing, failed or empty.
/// Never invents content. This function has no side effects.
pub fn retina_context_text(cfg: &RetinaConfig) -> String {
    match spawn_retina_line(cfg) {
        Ok(raw) => reading_text(&parse_line(&raw)),
        Err(_) => RETINA_UNAVAILABLE_DE.to_owned(),
    }
}

/// Honest context text from an injected CLI source (mockable).
pub fn retina_context_text_with(cli: &mut dyn RetinaCli) -> String {
    match cli.read_line_reading() {
        Ok(raw) => reading_text(&parse_line(&raw)),
        Err(_) => RETINA_UNAVAILABLE_DE.to_owned(),
    }
}

/// Pure: user-visible text of a reading (line or honest unavailability sentence).
pub fn reading_text(reading: &RetinaReading) -> String {
    match reading {
        RetinaReading::Line { line, .. } => line.clone(),
        RetinaReading::Unavailable { .. } => RETINA_UNAVAILABLE_DE.to_owned(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_line_tags_empty_as_unavailable() {
        match parse_line_at("   \n", 42) {
            RetinaReading::Unavailable { reason, ts_ms } => {
                assert!(!reason.is_empty());
                assert_eq!(ts_ms, 42);
            }
            RetinaReading::Line { .. } => panic!("expected Unavailable"),
        }
    }

    #[test]
    fn loopback_rule_rejects_remote_hosts() {
        assert!(enforce_loopback("127.0.0.1"));
        assert!(!enforce_loopback("localhost"));
        assert!(!enforce_loopback("10.0.0.1"));
        assert!(!enforce_loopback("0.0.0.0"));
    }

    #[test]
    fn grid_url_rejects_non_loopback() {
        assert!(matches!(
            parse_grid_url("http://10.0.0.1:8490"),
            Err(RetinaError::LoopbackViolation(_))
        ));
        assert!(parse_grid_url("http://127.0.0.1:8490").is_ok());
    }

    #[test]
    fn db_insert_kind_is_retina() {
        let reading =
            RetinaReading::Line { line: "inline".to_owned(), raw: "inline".to_owned(), ts_ms: 7 };
        let insert = build_db_insert_at(&reading, 7);
        assert_eq!(insert.kind, RETINA_KIND);
        assert!(insert.sql.contains("'retina'"));
    }
}
