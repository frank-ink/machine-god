//! `bild` CLI wrapper for the local omega-bildstudio service (Track 5, item 24).
//!
//! Scope: this module only spawns the external `bild` CLI and maps its
//! observable output into typed records. It contains no image logic, no HTTP
//! client and no retry of the ChatGPT message: one spawn is one real message.
//!
//! Hard invariants (see ClayCode block):
//!   * the studio is loopback-only (`127.0.0.1:18796`),
//!   * URLs are secrets: they never appear in `Debug`, `Display` or error text,
//!   * missing CLI / missing service are reported honestly, never faked.

use std::ffi::OsStr;
use std::fmt;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::time::{Duration, Instant};

use serde_json::Value;
use tokio::process::Command;

/// Executable name of the studio CLI.
pub const CLI_NAME: &str = "bild";
/// Loopback host of the studio service.
pub const SERVICE_HOST: &str = "127.0.0.1";
/// Loopback port of the studio service.
pub const SERVICE_PORT: u16 = 18796;
/// Canonical loopback authority of the studio service.
pub const SERVICE_ADDR: &str = "127.0.0.1:18796";

/// Placeholder used wherever a URL would otherwise be rendered.
const REDACTED: &str = "[url redacted]";

/// Errors of the wrapper. Every message is safe to show in the TUI.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum ImageStudioError {
    /// The `bild` executable could not be found (PATH or `$HOME/.local/bin`).
    #[error("bild CLI not found (searched PATH and $HOME/.local/bin)")]
    CliNotFound,
    /// The studio service is not reachable.
    #[error("bild service unavailable at {addr}")]
    ServiceUnavailable { addr: String },
    /// A non-loopback or wrong-port service address was observed.
    #[error("bild service address is not loopback-only: {0}")]
    InvalidServiceAddress(String),
    /// The CLI produced output that is not valid JSON.
    #[error("bild returned invalid JSON: {message}")]
    InvalidJson { message: String },
    /// The CLI failed for a reason that is not a service outage.
    #[error("bild command failed: {message}")]
    CommandFailed { message: String },
    /// The process could not be started.
    #[error("bild could not be started: {message}")]
    SpawnFailed { message: String },
    /// The background job did not finish inside the allowed window.
    #[error("bild job did not finish within {seconds}s")]
    Timeout { seconds: u64 },
}

/// Meaning of the CLI exit code.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ImageStudioExit {
    /// Exit 0: the job finished, files are available.
    Success,
    /// Exit 2: ChatGPT answered with text instead of an image.
    TextAnswer,
    /// Exit 3: the job is still running in the studio (delivered later).
    JobRunning,
    /// Any other exit code.
    Failure,
}

/// Map a raw exit code onto its meaning.
pub fn map_exit_code(code: i32) -> ImageStudioExit {
    match code {
        0 => ImageStudioExit::Success,
        2 => ImageStudioExit::TextAnswer,
        3 => ImageStudioExit::JobRunning,
        _ => ImageStudioExit::Failure,
    }
}

/// Progress information of a studio job. Missing fields stay UNKNOWN (`None`).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Progress {
    /// Completion in percent (0..=100).
    pub percent: Option<u8>,
    /// Remaining seconds, if reported.
    pub eta_seconds: Option<u64>,
    /// Elapsed seconds, if reported.
    pub elapsed_seconds: Option<u64>,
    /// Free-form status text of the studio.
    pub status: Option<String>,
}

impl Progress {
    /// One-line progress rendering for the TUI (no URLs, no secrets).
    pub fn line(&self) -> String {
        let mut parts: Vec<String> = Vec::new();
        if let Some(percent) = self.percent {
            parts.push(format!("{percent}%"));
        }
        if let Some(elapsed) = self.elapsed_seconds {
            parts.push(format!("elapsed {elapsed}s"));
        }
        if let Some(eta) = self.eta_seconds {
            parts.push(format!("eta {eta}s"));
        }
        if let Some(status) = &self.status {
            parts.push(redact_urls(status));
        }
        if parts.is_empty() { "progress unknown".to_string() } else { parts.join(" | ") }
    }
}

/// Result of one `bild` invocation.
#[derive(Clone, PartialEq)]
pub struct ImageStudioResult {
    /// Meaning of the exit code.
    pub kind: ImageStudioExit,
    /// Absolute paths of produced files.
    pub files: Vec<PathBuf>,
    /// ChatGPT text answer, if any.
    pub text: Option<String>,
    /// Studio job id, if reported.
    pub job_id: Option<String>,
    /// Progress, if reported.
    pub progress: Option<Progress>,
    /// Raw JSON payload, already URL-redacted so accidental logging is safe.
    pub raw: Value,
}

impl fmt::Debug for ImageStudioResult {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let text = self.text.as_deref().map(redact_urls);
        f.debug_struct("ImageStudioResult")
            .field("kind", &self.kind)
            .field("files", &self.files)
            .field("text", &text)
            .field("job_id", &self.job_id)
            .field("progress", &self.progress)
            .field("raw", &self.raw)
            .finish()
    }
}

impl ImageStudioResult {
    /// True when the job finished successfully.
    pub fn is_success(&self) -> bool {
        self.kind == ImageStudioExit::Success
    }

    /// True when ChatGPT answered with text instead of an image.
    pub fn is_text_answer(&self) -> bool {
        self.kind == ImageStudioExit::TextAnswer
    }

    /// True when the studio keeps working on the job.
    pub fn is_job_running(&self) -> bool {
        self.kind == ImageStudioExit::JobRunning
    }
}

/// One-time studio URL. The URL itself is never rendered by `Debug`/`Display`.
#[derive(Clone, PartialEq)]
pub struct ImageStudioUrl {
    url: String,
    expires_in_seconds: Option<u64>,
}

impl ImageStudioUrl {
    /// The raw URL. Callers must not log it.
    pub fn url(&self) -> &str {
        &self.url
    }

    /// Validity window in seconds, if the studio reported one.
    pub fn expires_in_seconds(&self) -> Option<u64> {
        self.expires_in_seconds
    }

    /// Open the URL in the default browser without logging it.
    pub async fn open_in_browser(&self) -> Result<(), ImageStudioError> {
        open_in_browser(&self.url).await
    }
}

impl fmt::Debug for ImageStudioUrl {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ImageStudioUrl")
            .field("url", &REDACTED)
            .field("expires_in_seconds", &self.expires_in_seconds)
            .finish()
    }
}

impl fmt::Display for ImageStudioUrl {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(REDACTED)
    }
}

/// Short user-facing line for an outcome (DE/EN).
pub fn outcome_message(kind: ImageStudioExit, lang: &str) -> &'static str {
    let german = matches!(lang, "de" | "DE" | "de_DE" | "de-DE");
    match (kind, german) {
        (ImageStudioExit::Success, true) => "Bildstudio: fertig.",
        (ImageStudioExit::Success, false) => "Image studio: done.",
        (ImageStudioExit::TextAnswer, true) => {
            "Bildstudio: ChatGPT hat eine Textantwort geliefert."
        }
        (ImageStudioExit::TextAnswer, false) => "Image studio: ChatGPT returned a text answer.",
        (ImageStudioExit::JobRunning, true) => {
            "Nachgeliefert: der Auftrag laeuft im Studio weiter."
        }
        (ImageStudioExit::JobRunning, false) => {
            "Delivered later: the job keeps running in the studio."
        }
        (ImageStudioExit::Failure, true) => "Bildstudio: Auftrag fehlgeschlagen.",
        (ImageStudioExit::Failure, false) => "Image studio: job failed.",
    }
}

/// Canonical loopback authority of the studio service.
pub fn service_addr() -> &'static str {
    SERVICE_ADDR
}

/// True for the loopback host names accepted by the wrapper.
pub fn is_loopback_host(host: &str) -> bool {
    matches!(host, "127.0.0.1" | "localhost" | "[::1]" | "::1")
}

/// Resolve the `bild` executable from an explicit PATH and HOME.
pub fn resolve_cli_from(
    path: Option<&OsStr>,
    home: Option<&OsStr>,
) -> Result<PathBuf, ImageStudioError> {
    if let Some(path) = path {
        for dir in std::env::split_paths(path) {
            if dir.as_os_str().is_empty() {
                continue;
            }
            let candidate = dir.join(CLI_NAME);
            if is_executable(&candidate) {
                return Ok(candidate);
            }
        }
    }
    if let Some(home) = home {
        let candidate = Path::new(home).join(".local").join("bin").join(CLI_NAME);
        if is_executable(&candidate) {
            return Ok(candidate);
        }
    }
    Err(ImageStudioError::CliNotFound)
}

/// Resolve the `bild` executable from the process environment.
pub fn resolve_cli() -> Result<PathBuf, ImageStudioError> {
    resolve_cli_from(std::env::var_os("PATH").as_deref(), std::env::var_os("HOME").as_deref())
}

fn is_executable(path: &Path) -> bool {
    let meta = match std::fs::metadata(path) {
        Ok(meta) => meta,
        Err(_) => return false,
    };
    if !meta.is_file() {
        return false;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        meta.permissions().mode() & 0o111 != 0
    }
    #[cfg(not(unix))]
    {
        true
    }
}

/// Enforce the loopback-only invariant on a `host:port` authority.
pub fn validate_service_addr(addr: &str) -> Result<(), ImageStudioError> {
    let (host, port) = addr
        .rsplit_once(':')
        .ok_or_else(|| ImageStudioError::InvalidServiceAddress("missing port".to_string()))?;
    let port = port
        .parse::<u16>()
        .map_err(|_| ImageStudioError::InvalidServiceAddress("invalid port".to_string()))?;
    if !is_loopback_host(host) || port != SERVICE_PORT {
        return Err(ImageStudioError::InvalidServiceAddress(format!("{host}:{port}")));
    }
    Ok(())
}

/// Enforce the loopback-only invariant on a full URL. The URL is never echoed.
pub fn validate_service_url(url: &str) -> Result<(), ImageStudioError> {
    let rest =
        url.strip_prefix("http://").or_else(|| url.strip_prefix("https://")).ok_or_else(|| {
            ImageStudioError::InvalidServiceAddress("scheme is not http(s)".to_string())
        })?;
    let authority = rest.split(|c| c == '/' || c == '?' || c == '#').next().unwrap_or("");
    let (host, port) = authority
        .rsplit_once(':')
        .ok_or_else(|| ImageStudioError::InvalidServiceAddress("missing port".to_string()))?;
    let port_num = port
        .parse::<u16>()
        .map_err(|_| ImageStudioError::InvalidServiceAddress("invalid port".to_string()))?;
    if !is_loopback_host(host) || port_num != SERVICE_PORT {
        return Err(ImageStudioError::InvalidServiceAddress(format!("{host}:{port_num}")));
    }
    Ok(())
}

/// Remove every `http(s)://...` token from a text.
pub fn redact_urls(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut index = 0usize;
    while index < text.len() {
        let rest = &text[index..];
        if rest.starts_with("http://") || rest.starts_with("https://") {
            let end = rest
                .find(|c: char| {
                    c.is_whitespace() || c == '"' || c == '\'' || c == ')' || c == '<' || c == '>'
                })
                .unwrap_or(rest.len());
            out.push_str(REDACTED);
            index += end;
        } else {
            let ch = rest.chars().next().unwrap_or(' ');
            out.push(ch);
            index += ch.len_utf8();
        }
    }
    out
}

/// Redact every URL inside a JSON document (in place).
pub fn redact_json_urls(value: &mut Value) {
    match value {
        Value::String(text) => {
            if text.contains("http://") || text.contains("https://") {
                *text = REDACTED.to_string();
            }
        }
        Value::Array(items) => {
            for item in items.iter_mut() {
                redact_json_urls(item);
            }
        }
        Value::Object(map) => {
            for (_, item) in map.iter_mut() {
                redact_json_urls(item);
            }
        }
        _ => {}
    }
}

/// Classify a failing invocation. Service outages are distinguished from
/// ordinary command failures; URLs are redacted from the message.
pub fn classify_failure(exit_code: i32, stderr: &str) -> ImageStudioError {
    let lower = stderr.to_ascii_lowercase();
    const SERVICE_MARKERS: [&str; 10] = [
        "connection refused",
        "service unavailable",
        "service not running",
        "service is not running",
        "could not connect",
        "cannot connect",
        "unable to connect",
        "not reachable",
        "unreachable",
        "failed to start service",
    ];
    if SERVICE_MARKERS.iter().any(|marker| lower.contains(marker)) {
        return ImageStudioError::ServiceUnavailable { addr: SERVICE_ADDR.to_string() };
    }
    let message = redact_urls(stderr.trim());
    if message.is_empty() {
        ImageStudioError::CommandFailed { message: format!("exit code {exit_code}") }
    } else {
        ImageStudioError::CommandFailed { message: format!("exit code {exit_code}: {message}") }
    }
}

fn value_at<'a>(value: &'a Value, keys: &[&str]) -> Option<&'a Value> {
    for key in keys {
        if let Some(found) = value.get(*key) {
            if !found.is_null() {
                return Some(found);
            }
        }
    }
    None
}

fn number_to_u64(value: &Value) -> Option<u64> {
    if let Some(number) = value.as_u64() {
        return Some(number);
    }
    if let Some(number) = value.as_i64() {
        return if number >= 0 { Some(number as u64) } else { None };
    }
    if let Some(number) = value.as_f64() {
        if number.is_finite() && number >= 0.0 {
            return Some(number as u64);
        }
    }
    None
}

fn number_to_f64(value: &Value) -> Option<f64> {
    value.as_f64().or_else(|| value.as_u64().map(|n| n as f64))
}

/// Normalise a progress value to percent. Values in `(0, 1)` are fractions,
/// values `>= 1` are already percent.
fn percent_from_value(value: &Value) -> Option<u8> {
    if let Some(text) = value.as_str() {
        let trimmed = text.trim().trim_end_matches('%');
        return trimmed.parse::<f64>().ok().map(|n| n.clamp(0.0, 100.0).round() as u8);
    }
    let number = number_to_f64(value)?;
    let percent = if number > 0.0 && number < 1.0 { number * 100.0 } else { number };
    Some(percent.clamp(0.0, 100.0).round() as u8)
}

fn collect_progress(value: &Value, out: &mut Progress, found: &mut bool, depth: usize) {
    if depth > 4 {
        return;
    }
    match value {
        Value::Object(map) => {
            for (key, item) in map {
                match key.as_str() {
                    "percent" | "percentage" | "progress_percent" => {
                        if let Some(percent) = percent_from_value(item) {
                            out.percent = Some(percent);
                            *found = true;
                        }
                    }
                    "progress" => {
                        if let Some(percent) = percent_from_value(item) {
                            out.percent = Some(percent);
                            *found = true;
                        } else {
                            collect_progress(item, out, found, depth + 1);
                        }
                    }
                    "eta" | "eta_seconds" | "eta_s" | "seconds_remaining" | "remaining" => {
                        if let Some(seconds) = number_to_u64(item) {
                            out.eta_seconds = Some(seconds);
                            *found = true;
                        }
                    }
                    "elapsed" | "elapsed_seconds" | "elapsed_s" => {
                        if let Some(seconds) = number_to_u64(item) {
                            out.elapsed_seconds = Some(seconds);
                            *found = true;
                        }
                    }
                    "status" | "state" => {
                        if let Some(text) = item.as_str() {
                            out.status = Some(text.to_string());
                            *found = true;
                        }
                    }
                    _ => {}
                }
                if matches!(item, Value::Object(_) | Value::Array(_)) {
                    collect_progress(item, out, found, depth + 1);
                }
            }
        }
        Value::Array(items) => {
            for item in items {
                collect_progress(item, out, found, depth + 1);
            }
        }
        _ => {}
    }
}

/// Parse progress from a `--json` payload. `None` means UNKNOWN.
pub fn parse_progress(value: &Value) -> Option<Progress> {
    let mut progress = Progress::default();
    let mut found = false;
    collect_progress(value, &mut progress, &mut found, 0);
    if found { Some(progress) } else { None }
}

fn push_path(out: &mut Vec<PathBuf>, raw: &str) {
    let trimmed = raw.trim();
    if trimmed.is_empty() {
        return;
    }
    out.push(PathBuf::from(trimmed));
}

fn collect_files(value: &Value, out: &mut Vec<PathBuf>, depth: usize) {
    if depth > 4 {
        return;
    }
    match value {
        Value::Object(map) => {
            for (key, item) in map {
                match key.as_str() {
                    "files" | "paths" | "outputs" | "images" => match item {
                        Value::Array(items) => {
                            for entry in items {
                                if let Some(path) = entry.as_str() {
                                    push_path(out, path);
                                }
                            }
                        }
                        Value::String(path) => push_path(out, path),
                        _ => {}
                    },
                    "output" | "path" | "file" => {
                        if let Some(path) = item.as_str() {
                            push_path(out, path);
                        }
                    }
                    _ => {}
                }
                if matches!(item, Value::Object(_) | Value::Array(_)) {
                    collect_files(item, out, depth + 1);
                }
            }
        }
        Value::Array(items) => {
            for item in items {
                collect_files(item, out, depth + 1);
            }
        }
        _ => {}
    }
}

fn absolutize(paths: Vec<PathBuf>) -> Vec<PathBuf> {
    let cwd = std::env::current_dir().ok();
    paths
        .into_iter()
        .map(|path| {
            if path.is_absolute() {
                path
            } else {
                match &cwd {
                    Some(dir) => dir.join(&path),
                    None => path,
                }
            }
        })
        .collect()
}

fn collect_text(value: &Value) -> Option<String> {
    fn from_obj(v: &Value, depth: usize) -> Option<String> {
        if depth > 4 {
            return None;
        }
        match v {
            Value::Object(map) => {
                for key in ["text", "answer", "response", "message"] {
                    if let Some(text) = map.get(key).and_then(|x| x.as_str()) {
                        if !text.trim().is_empty() {
                            return Some(text.to_string());
                        }
                    }
                }
                for key in ["jobs", "job", "result", "data"] {
                    if let Some(child) = map.get(key) {
                        if let Some(found) = from_obj(child, depth + 1) {
                            return Some(found);
                        }
                    }
                }
                None
            }
            Value::Array(items) => {
                for item in items {
                    if let Some(found) = from_obj(item, depth + 1) {
                        return Some(found);
                    }
                }
                None
            }
            _ => None,
        }
    }
    from_obj(value, 0)
}

fn collect_job_id(value: &Value) -> Option<String> {
    fn from_obj(v: &Value, depth: usize) -> Option<String> {
        if depth > 4 {
            return None;
        }
        match v {
            Value::Object(map) => {
                for key in ["job_id", "jobId", "id"] {
                    if let Some(id) = map.get(key).and_then(|x| x.as_str()) {
                        if !id.trim().is_empty() {
                            return Some(id.to_string());
                        }
                    }
                }
                for key in ["jobs", "job", "result", "data"] {
                    if let Some(child) = map.get(key) {
                        if let Some(found) = from_obj(child, depth + 1) {
                            return Some(found);
                        }
                    }
                }
                None
            }
            Value::Array(items) => {
                for item in items {
                    if let Some(found) = from_obj(item, depth + 1) {
                        return Some(found);
                    }
                }
                None
            }
            _ => None,
        }
    }
    from_obj(value, 0)
}

fn build_result(kind: ImageStudioExit, raw: Value) -> ImageStudioResult {
    let mut files = Vec::new();
    collect_files(&raw, &mut files, 0);
    let files = absolutize(files);
    let mut text = collect_text(&raw);
    if text.is_none() {
        if let Value::String(plain) = &raw {
            if !plain.trim().is_empty() {
                text = Some(plain.clone());
            }
        }
    }
    let job_id = collect_job_id(&raw);
    let progress = parse_progress(&raw);
    let mut safe_raw = raw;
    redact_json_urls(&mut safe_raw);
    ImageStudioResult { kind, files, text, job_id, progress, raw: safe_raw }
}

/// Parse a `--json` payload. Invalid JSON is an error, except for exit code 2
/// where plain text is accepted as the ChatGPT answer.
pub fn parse_result(exit_code: i32, stdout: &str) -> Result<ImageStudioResult, ImageStudioError> {
    let kind = map_exit_code(exit_code);
    let trimmed = stdout.trim();
    if trimmed.is_empty() {
        return Ok(build_result(kind, Value::Null));
    }
    match serde_json::from_str::<Value>(trimmed) {
        Ok(raw) => Ok(build_result(kind, raw)),
        Err(err) => {
            if kind == ImageStudioExit::TextAnswer {
                Ok(build_result(kind, Value::String(trimmed.to_string())))
            } else {
                Err(ImageStudioError::InvalidJson { message: redact_urls(&err.to_string()) })
            }
        }
    }
}

/// Like [`parse_result`] but never fails on non-JSON output (used for
/// `bild edit`, which is passed through unchanged).
pub fn parse_result_lenient(
    exit_code: i32,
    stdout: &str,
) -> Result<ImageStudioResult, ImageStudioError> {
    let kind = map_exit_code(exit_code);
    let trimmed = stdout.trim();
    if trimmed.is_empty() {
        return Ok(build_result(kind, Value::Null));
    }
    match serde_json::from_str::<Value>(trimmed) {
        Ok(raw) => Ok(build_result(kind, raw)),
        Err(_) => Ok(build_result(kind, Value::String(trimmed.to_string()))),
    }
}

/// Parse the output of `bild url` (JSON object or plain URL line).
pub fn parse_url_output(stdout: &str) -> Result<ImageStudioUrl, ImageStudioError> {
    let trimmed = stdout.trim();
    if trimmed.is_empty() {
        return Err(ImageStudioError::InvalidJson { message: "empty output".to_string() });
    }
    let parsed = serde_json::from_str::<Value>(trimmed).ok();
    let candidate = match parsed.as_ref() {
        Some(Value::String(text)) => text.clone(),
        Some(value) => value_at(value, &["url", "link", "href"])
            .and_then(|v| v.as_str())
            .map(|s| s.to_string())
            .ok_or_else(|| ImageStudioError::InvalidJson {
                message: "no url field in output".to_string(),
            })?,
        None => trimmed.to_string(),
    };
    validate_service_url(&candidate)?;
    let expires = parsed.as_ref().and_then(|value| {
        value_at(value, &["expires_in", "expires_in_seconds", "ttl", "valid_for"])
            .and_then(number_to_u64)
    });
    Ok(ImageStudioUrl { url: candidate, expires_in_seconds: expires })
}

/// Open a loopback studio URL in the default browser. The URL is never logged.
pub async fn open_in_browser(url: &str) -> Result<(), ImageStudioError> {
    validate_service_url(url)?;
    let opener = if cfg!(target_os = "macos") { "open" } else { "xdg-open" };
    let mut cmd = Command::new(opener);
    cmd.arg(url)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .kill_on_drop(true);
    match cmd.status().await {
        Ok(status) if status.success() => Ok(()),
        Ok(status) => Err(ImageStudioError::CommandFailed {
            message: format!("browser opener exited with {}", status.code().unwrap_or(-1)),
        }),
        Err(err) => Err(ImageStudioError::SpawnFailed { message: redact_urls(&err.to_string()) }),
    }
}

/// Options for the background generate loop.
#[derive(Debug, Clone)]
pub struct GenerateOptions {
    /// Delay between two `bild status` polls.
    pub poll_interval: Duration,
    /// Hard timeout for the whole background job.
    pub timeout: Option<Duration>,
    /// Maximum number of status polls.
    pub max_polls: u32,
}

impl Default for GenerateOptions {
    fn default() -> Self {
        Self {
            poll_interval: Duration::from_secs(2),
            timeout: Some(Duration::from_secs(300)),
            max_polls: 150,
        }
    }
}

struct Captured {
    code: i32,
    stdout: String,
    stderr: String,
}

/// Wrapper around the external `bild` CLI.
#[derive(Debug, Clone)]
pub struct BildCli {
    path: PathBuf,
}

impl BildCli {
    /// Resolve the CLI from PATH / `$HOME/.local/bin`.
    pub fn resolve() -> Result<Self, ImageStudioError> {
        Ok(Self { path: resolve_cli()? })
    }

    /// Use an explicit executable path (used by tests with a stub script).
    pub fn from_path(path: impl Into<PathBuf>) -> Self {
        Self { path: path.into() }
    }

    /// Path of the resolved executable.
    pub fn path(&self) -> &Path {
        &self.path
    }

    async fn capture(&self, args: &[String]) -> Result<Captured, ImageStudioError> {
        let mut cmd = Command::new(&self.path);
        cmd.args(args)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true);
        let output = cmd.output().await.map_err(|err| match err.kind() {
            std::io::ErrorKind::NotFound => ImageStudioError::CliNotFound,
            _ => ImageStudioError::SpawnFailed { message: redact_urls(&err.to_string()) },
        })?;
        Ok(Captured {
            code: output.status.code().unwrap_or(-1),
            stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
        })
    }

    /// `bild url`: one-time studio URL (never logged by this module).
    pub async fn url(&self) -> Result<ImageStudioUrl, ImageStudioError> {
        let captured = self.capture(&["url".to_string()]).await?;
        if map_exit_code(captured.code) != ImageStudioExit::Success {
            return Err(classify_failure(captured.code, &captured.stderr));
        }
        parse_url_output(&captured.stdout)
    }

    /// `bild generate "<prompt>" --json`.
    pub async fn generate(&self, prompt: &str) -> Result<ImageStudioResult, ImageStudioError> {
        let args = vec!["generate".to_string(), prompt.to_string(), "--json".to_string()];
        let captured = self.capture(&args).await?;
        match map_exit_code(captured.code) {
            ImageStudioExit::Failure => Err(classify_failure(captured.code, &captured.stderr)),
            _ => parse_result(captured.code, &captured.stdout),
        }
    }

    /// `bild edit <name> [--region x,y,w,h:text] --json`.
    pub async fn edit(
        &self,
        name: &str,
        region: Option<&str>,
    ) -> Result<ImageStudioResult, ImageStudioError> {
        let mut args = vec!["edit".to_string(), name.to_string()];
        if let Some(region) = region {
            args.push("--region".to_string());
            args.push(region.to_string());
        }
        self.edit_args(&args[1..]).await
    }

    /// Raw pass-through for `bild edit` (regions may contain `%` values).
    pub async fn edit_args(&self, extra: &[String]) -> Result<ImageStudioResult, ImageStudioError> {
        let mut args = vec!["edit".to_string()];
        args.extend(extra.iter().cloned());
        args.push("--json".to_string());
        let captured = self.capture(&args).await?;
        match map_exit_code(captured.code) {
            ImageStudioExit::Failure => Err(classify_failure(captured.code, &captured.stderr)),
            _ => parse_result_lenient(captured.code, &captured.stdout),
        }
    }

    /// `bild status <job_id> --json`.
    pub async fn status(&self, job_id: &str) -> Result<ImageStudioResult, ImageStudioError> {
        let args = vec!["status".to_string(), job_id.to_string(), "--json".to_string()];
        let captured = self.capture(&args).await?;
        match map_exit_code(captured.code) {
            ImageStudioExit::Failure => Err(classify_failure(captured.code, &captured.stderr)),
            _ => parse_result_lenient(captured.code, &captured.stdout),
        }
    }

    /// Background generate: one `generate` spawn, then `status` polling.
    /// The ChatGPT message is never retried.
    pub async fn generate_with_progress<F>(
        &self,
        prompt: &str,
        opts: &GenerateOptions,
        mut on_progress: F,
    ) -> Result<ImageStudioResult, ImageStudioError>
    where
        F: FnMut(&Progress),
    {
        let first = self.generate(prompt).await?;
        if first.kind != ImageStudioExit::JobRunning {
            return Ok(first);
        }
        let job_id = match first.job_id.clone() {
            Some(id) => id,
            None => return Ok(first),
        };
        if let Some(progress) = &first.progress {
            on_progress(progress);
        }
        let start = Instant::now();
        let mut polls: u32 = 0;
        loop {
            if polls >= opts.max_polls {
                return Err(ImageStudioError::Timeout { seconds: start.elapsed().as_secs() });
            }
            if let Some(timeout) = opts.timeout {
                if start.elapsed() >= timeout {
                    return Err(ImageStudioError::Timeout { seconds: timeout.as_secs() });
                }
            }
            polls += 1;
            tokio::time::sleep(opts.poll_interval).await;
            let captured =
                self.capture(&["status".to_string(), job_id.clone(), "--json".to_string()]).await?;
            match map_exit_code(captured.code) {
                ImageStudioExit::Failure => {
                    return Err(classify_failure(captured.code, &captured.stderr));
                }
                ImageStudioExit::TextAnswer => {
                    let result = parse_result_lenient(captured.code, &captured.stdout)?;
                    if let Some(progress) = &result.progress {
                        on_progress(progress);
                    }
                    return Ok(result);
                }
                _ => {
                    let result = parse_result_lenient(captured.code, &captured.stdout)?;
                    if let Some(progress) = &result.progress {
                        on_progress(progress);
                    }
                    if status_is_done(&result) {
                        let mut done = result;
                        done.kind = ImageStudioExit::Success;
                        return Ok(done);
                    }
                }
            }
        }
    }
}

/// True when a `bild status` payload reports a finished job.
pub fn status_is_done(result: &ImageStudioResult) -> bool {
    if !result.files.is_empty() {
        return true;
    }
    if let Some(progress) = &result.progress {
        if progress.percent == Some(100) {
            return true;
        }
        if let Some(status) = &progress.status {
            let lower = status.to_ascii_lowercase();
            if lower.contains("done")
                || lower.contains("complete")
                || lower.contains("finished")
                || lower.contains("fertig")
            {
                return true;
            }
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Mutex};

    #[cfg(unix)]
    fn write_stub(name: &str, body: &str) -> (PathBuf, PathBuf) {
        use std::os::unix::fs::PermissionsExt;
        let dir = std::env::temp_dir().join(format!("zero-bild-{}-{}", std::process::id(), name));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).expect("create stub dir");
        let script = dir.join(CLI_NAME);
        std::fs::write(&script, body).expect("write stub");
        let mut perms = std::fs::metadata(&script).expect("stat stub").permissions();
        perms.set_mode(0o755);
        std::fs::set_permissions(&script, perms).expect("chmod stub");
        (dir, script)
    }

    #[test]
    fn map_exit_codes_are_explicit() {
        assert_eq!(map_exit_code(0), ImageStudioExit::Success);
        assert_eq!(map_exit_code(2), ImageStudioExit::TextAnswer);
        assert_eq!(map_exit_code(3), ImageStudioExit::JobRunning);
        assert_eq!(map_exit_code(1), ImageStudioExit::Failure);
        assert_eq!(map_exit_code(42), ImageStudioExit::Failure);
    }

    #[test]
    fn outcome_messages_cover_all_kinds() {
        assert!(outcome_message(ImageStudioExit::JobRunning, "de").contains("Nachgeliefert"));
        assert!(outcome_message(ImageStudioExit::JobRunning, "en").contains("Delivered later"));
        assert!(outcome_message(ImageStudioExit::TextAnswer, "de").contains("Textantwort"));
        assert!(outcome_message(ImageStudioExit::Success, "en").contains("done"));
    }

    #[test]
    fn resolve_cli_reports_missing_cli() {
        let err = resolve_cli_from(
            Some(OsStr::new("/nonexistent-zero-bild-path")),
            Some(OsStr::new("/nonexistent-zero-bild-home")),
        )
        .unwrap_err();
        assert_eq!(err, ImageStudioError::CliNotFound);
    }

    #[cfg(unix)]
    #[test]
    fn resolve_cli_finds_home_local_bin() {
        use std::os::unix::fs::PermissionsExt;
        let home = std::env::temp_dir().join(format!("zero-bild-home-{}", std::process::id()));
        let bin = home.join(".local").join("bin");
        std::fs::create_dir_all(&bin).expect("create home bin");
        let script = bin.join(CLI_NAME);
        std::fs::write(&script, "#!/bin/sh\nexit 0\n").expect("write stub");
        let mut perms = std::fs::metadata(&script).expect("stat").permissions();
        perms.set_mode(0o755);
        std::fs::set_permissions(&script, perms).expect("chmod");
        let resolved = resolve_cli_from(None, Some(home.as_os_str())).expect("resolve");
        assert_eq!(resolved, script);
        let _ = std::fs::remove_dir_all(&home);
    }

    #[test]
    fn redact_urls_removes_token() {
        let text = "open http://127.0.0.1:18796/?token=SECRET now";
        let redacted = redact_urls(text);
        assert!(!redacted.contains("SECRET"));
        assert!(!redacted.contains("http://"));
        assert!(redacted.contains("[url redacted]"));
    }

    #[test]
    fn validate_service_url_is_loopback_only() {
        assert!(validate_service_url("http://127.0.0.1:18796/?token=x").is_ok());
        assert!(validate_service_url("http://localhost:18796/").is_ok());
        assert!(validate_service_url("http://10.0.0.5:18796/").is_err());
        assert!(validate_service_url("http://127.0.0.1:9999/").is_err());
        assert!(validate_service_url("https://example.com/").is_err());
        assert!(validate_service_addr("127.0.0.1:18796").is_ok());
        assert!(validate_service_addr("127.0.0.1:1234").is_err());
    }

    #[test]
    fn classify_failure_maps_service_outage() {
        let err = classify_failure(1, "connection refused");
        assert_eq!(err, ImageStudioError::ServiceUnavailable { addr: SERVICE_ADDR.to_string() });
    }

    #[test]
    fn classify_failure_redacts_urls() {
        let err = classify_failure(1, "boom http://127.0.0.1:18796/?token=SECRET");
        let message = err.to_string();
        assert!(!message.contains("SECRET"));
        assert!(!message.contains("http://"));
    }

    #[test]
    fn parse_progress_reads_json_shapes() {
        let value: Value =
            serde_json::from_str(r#"{"jobs":[{"progress":{"percent":42,"eta_seconds":12}}]}"#)
                .expect("json");
        let progress = parse_progress(&value).expect("progress");
        assert_eq!(progress.percent, Some(42));
        assert_eq!(progress.eta_seconds, Some(12));

        let fraction: Value = serde_json::from_str(r#"{"percent":0.5}"#).expect("json");
        assert_eq!(parse_progress(&fraction).expect("progress").percent, Some(50));

        let flat: Value =
            serde_json::from_str(r#"{"percent":100,"elapsed":42,"status":"done"}"#).expect("json");
        let progress = parse_progress(&flat).expect("progress");
        assert_eq!(progress.percent, Some(100));
        assert_eq!(progress.elapsed_seconds, Some(42));
        assert_eq!(progress.status.as_deref(), Some("done"));

        let empty: Value = serde_json::from_str(r#"{"files":["/tmp/a.png"]}"#).expect("json");
        assert!(parse_progress(&empty).is_none());
    }

    #[test]
    fn parse_result_rejects_invalid_json() {
        let err = parse_result(0, "not json at all").unwrap_err();
        assert!(matches!(err, ImageStudioError::InvalidJson { .. }));
    }

    #[test]
    fn parse_result_accepts_plain_text_for_exit_two() {
        let result = parse_result(2, "ChatGPT says: no image today").expect("result");
        assert_eq!(result.kind, ImageStudioExit::TextAnswer);
        assert_eq!(result.text.as_deref(), Some("ChatGPT says: no image today"));
    }

    #[test]
    fn result_debug_never_contains_url() {
        let result = parse_result(
            0,
            r#"{"files":["/tmp/a.png"],"url":"http://127.0.0.1:18796/?token=SECRET"}"#,
        )
        .expect("result");
        let rendered = format!("{result:?}");
        assert!(!rendered.contains("SECRET"));
        assert!(!rendered.contains("http://"));
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn url_command_exit_zero() {
        let (dir, script) = write_stub(
            "url",
            r#"#!/bin/sh
if [ "$1" = "url" ]; then
  printf '%s\n' '{"url":"http://127.0.0.1:18796/?token=SECRET-TOKEN","expires_in":90}'
  exit 0
fi
exit 1
"#,
        );
        let cli = BildCli::from_path(&script);
        let url = cli.url().await.expect("url");
        assert!(url.url().starts_with("http://127.0.0.1:18796/"));
        assert_eq!(url.expires_in_seconds(), Some(90));
        let rendered = format!("{url:?} {url}");
        assert!(!rendered.contains("SECRET-TOKEN"));
        assert!(!rendered.contains("http://"));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn generate_exit_zero_reports_files_and_progress() {
        let (dir, script) = write_stub(
            "generate0",
            r#"#!/bin/sh
if [ "$1" = "generate" ]; then
  printf '%s\n' '{"job_id":"job-1","files":["/tmp/zero-bild-out.png"],"jobs":[{"id":"job-1","percent":100,"eta":0,"elapsed":42}]}'
  exit 0
fi
exit 1
"#,
        );
        let cli = BildCli::from_path(&script);
        let result = cli.generate("a cat").await.expect("generate");
        assert_eq!(result.kind, ImageStudioExit::Success);
        assert!(result.is_success());
        assert_eq!(result.files.len(), 1);
        assert!(result.files[0].to_string_lossy().ends_with("zero-bild-out.png"));
        assert_eq!(result.job_id.as_deref(), Some("job-1"));
        let progress = result.progress.expect("progress");
        assert_eq!(progress.percent, Some(100));
        assert_eq!(progress.elapsed_seconds, Some(42));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn generate_exit_two_returns_text_answer() {
        let (dir, script) = write_stub(
            "generate2",
            r#"#!/bin/sh
if [ "$1" = "generate" ]; then
  printf '%s\n' '{"jobs":[{"text":"Ich kann kein Bild erzeugen."}]}'
  exit 2
fi
exit 1
"#,
        );
        let cli = BildCli::from_path(&script);
        let result = cli.generate("a cat").await.expect("generate");
        assert_eq!(result.kind, ImageStudioExit::TextAnswer);
        assert!(result.is_text_answer());
        assert!(result.text.as_deref().unwrap_or_default().contains("kein Bild"));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn generate_exit_three_reports_running_job() {
        let (dir, script) = write_stub(
            "generate3",
            r#"#!/bin/sh
if [ "$1" = "generate" ]; then
  printf '%s\n' '{"job_id":"job-1","percent":10,"eta":30}'
  exit 3
fi
exit 1
"#,
        );
        let cli = BildCli::from_path(&script);
        let result = cli.generate("a cat").await.expect("generate");
        assert_eq!(result.kind, ImageStudioExit::JobRunning);
        assert!(result.is_job_running());
        assert_eq!(result.job_id.as_deref(), Some("job-1"));
        let progress = result.progress.expect("progress");
        assert_eq!(progress.percent, Some(10));
        assert_eq!(progress.eta_seconds, Some(30));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn edit_command_passes_region_through() {
        let (dir, script) = write_stub(
            "edit",
            r#"#!/bin/sh
if [ "$1" = "edit" ]; then
  printf '%s\n' '{"files":["/tmp/zero-bild-edit.png"]}'
  exit 0
fi
exit 1
"#,
        );
        let cli = BildCli::from_path(&script);
        let result = cli.edit("cat.png", Some("10%,20%,30%,40%:make it blue")).await.expect("edit");
        assert_eq!(result.kind, ImageStudioExit::Success);
        assert_eq!(result.files.len(), 1);
        assert!(result.files[0].to_string_lossy().ends_with("zero-bild-edit.png"));
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn generate_with_progress_polls_status() {
        let (dir, script) = write_stub(
            "progress",
            r#"#!/bin/sh
if [ "$1" = "generate" ]; then
  printf '%s\n' '{"job_id":"job-1","percent":10,"eta":30}'
  exit 3
fi
if [ "$1" = "status" ]; then
  printf '%s\n' '{"job_id":"job-1","percent":100,"files":["/tmp/zero-bild-bg.png"]}'
  exit 0
fi
exit 1
"#,
        );
        let cli = BildCli::from_path(&script);
        let seen: Arc<Mutex<Vec<Progress>>> = Arc::new(Mutex::new(Vec::new()));
        let sink = Arc::clone(&seen);
        let opts = GenerateOptions {
            poll_interval: Duration::from_millis(5),
            timeout: Some(Duration::from_secs(5)),
            max_polls: 10,
        };
        let result = cli
            .generate_with_progress("a cat", &opts, move |progress| {
                sink.lock().expect("lock").push(progress.clone());
            })
            .await
            .expect("generate");
        assert_eq!(result.kind, ImageStudioExit::Success);
        assert_eq!(result.files.len(), 1);
        let seen = seen.lock().expect("lock");
        assert!(!seen.is_empty());
        assert_eq!(seen.last().expect("last").percent, Some(100));
        drop(seen);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn missing_cli_maps_to_cli_not_found() {
        let cli = BildCli::from_path("/nonexistent-zero-bild-dir/bild");
        let err = cli.generate("a cat").await.unwrap_err();
        assert_eq!(err, ImageStudioError::CliNotFound);
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn missing_service_maps_to_service_unavailable() {
        let (dir, script) = write_stub(
            "service",
            r#"#!/bin/sh
printf '%s\n' 'connection refused' >&2
exit 1
"#,
        );
        let cli = BildCli::from_path(&script);
        let err = cli.generate("a cat").await.unwrap_err();
        assert_eq!(err, ImageStudioError::ServiceUnavailable { addr: SERVICE_ADDR.to_string() });
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn failure_message_never_leaks_url() {
        let (dir, script) = write_stub(
            "leak",
            r#"#!/bin/sh
printf '%s\n' 'failed http://127.0.0.1:18796/?token=SECRET' >&2
exit 1
"#,
        );
        let cli = BildCli::from_path(&script);
        let err = cli.generate("a cat").await.unwrap_err();
        let message = err.to_string();
        assert!(!message.contains("SECRET"));
        assert!(!message.contains("http://"));
        let _ = std::fs::remove_dir_all(&dir);
    }
}
