use crate::zero::retina::*;
use serde_json::Value;
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::Command;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::thread;
use std::time::Instant;

#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;

// ---------------------------------------------------------------- mocks

#[derive(Debug, Default)]
struct MockDb {
    rows: Vec<DbInsert>,
}

impl RetinaDb for MockDb {
    fn insert(&mut self, insert: &DbInsert) -> Result<(), RetinaError> {
        self.rows.push(insert.clone());
        Ok(())
    }
}

#[derive(Debug, Default)]
struct MockGrid {
    events: Vec<GridEvent>,
}

impl GridSink for MockGrid {
    fn push(&mut self, event: &GridEvent) -> Result<(), RetinaError> {
        self.events.push(event.clone());
        Ok(())
    }
}

struct MockCli {
    stdout: Option<String>,
    fail: bool,
}

impl MockCli {
    fn line(text: &str) -> Self {
        Self {
            stdout: Some(text.to_string()),
            fail: false,
        }
    }

    fn missing() -> Self {
        Self {
            stdout: None,
            fail: false,
        }
    }

    fn failing() -> Self {
        Self {
            stdout: None,
            fail: true,
        }
    }
}

impl RetinaCli for MockCli {
    fn read_zeile(&mut self) -> Result<String, RetinaError> {
        if self.fail {
            return Err(RetinaError::CliFailed("mock cli failure".to_string()));
        }
        match &self.stdout {
            Some(text) => Ok(text.clone()),
            None => Err(RetinaError::CliNotFound(PathBuf::from(RETINA_CLI))),
        }
    }
}

// ---------------------------------------------------------------- helpers

fn unique_dir(tag: &str) -> PathBuf {
    static COUNTER: AtomicUsize = AtomicUsize::new(0);
    let n = COUNTER.fetch_add(1, Ordering::SeqCst);
    let dir = std::env::temp_dir().join(format!(
        "zero-retina-{}-{}-{}",
        tag,
        std::process::id(),
        n
    ));
    fs::create_dir_all(&dir).expect("create temp dir");
    dir
}

#[cfg(unix)]
fn write_script(dir: &PathBuf, name: &str, body: &str) -> PathBuf {
    let path = dir.join(name);
    let mut file = fs::File::create(&path).expect("script file");
    writeln!(file, "#!/bin/sh").expect("shebang");
    write!(file, "{}", body).expect("script body");
    let mut perms = fs::metadata(&path).expect("metadata").permissions();
    perms.set_mode(0o755);
    fs::set_permissions(&path, perms).expect("perms");
    path
}

fn sqlite_available() -> bool {
    Command::new("sqlite3")
        .arg("-version")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

// ---------------------------------------------------------------- pure functions

#[test]
fn test_parse_zeile_single_line() {
    let reading = parse_zeile("retina-zeile-eins\nzweite zeile\n");
    match reading {
        RetinaReading::Zeile { line, raw, ts_ms } => {
            assert_eq!(line, "retina-zeile-eins");
            assert_eq!(raw, "retina-zeile-eins\nzweite zeile");
            assert!(ts_ms > 0);
        }
        RetinaReading::Unavailable { .. } => panic!("expected Zeile"),
    }
}

#[test]
fn test_parse_zeile_empty_is_unavailable() {
    let reading = parse_zeile("");
    match reading {
        RetinaReading::Unavailable { reason, .. } => {
            assert!(!reason.is_empty());
        }
        RetinaReading::Zeile { .. } => panic!("expected Unavailable"),
    }
}

#[test]
fn test_parse_zeile_under_50ms() {
    let start = Instant::now();
    for _ in 0..1000 {
        parse_zeile("retina-timing-line");
    }
    let elapsed = start.elapsed();
    assert!(
        elapsed.as_millis() < 50,
        "one-line parse too slow: {:?}",
        elapsed
    );
}

#[test]
fn test_build_grid_event_json() {
    let cfg = RetinaConfig {
        cli_path: PathBuf::from("retina-frage"),
        grid_host: "127.0.0.1".to_string(),
        grid_port: 8490,
        db_path: PathBuf::from("unified.db"),
    };
    let reading = RetinaReading::Zeile {
        line: "test-zeile".to_string(),
        raw: "test-zeile\n".to_string(),
        ts_ms: 1700000000000,
    };
    let event = build_grid_event(&reading, &cfg);
    let json = serde_json::to_string(&event).expect("serialize");
    assert_eq!(event.kind, "perception");
    assert_eq!(event.source, "retina");
    assert_eq!(event.r#type, "retina_reading");
    assert_eq!(event.host, "127.0.0.1");
    assert_eq!(event.port, 8490);
    assert!(json.contains("\"zeile\":\"test-zeile\""));
    assert!(json.contains("\"host\":\"127.0.0.1\""));
}

#[test]
fn test_build_db_insert_kind_retina() {
    let reading = RetinaReading::Zeile {
        line: "db-zeile".to_string(),
        raw: "db-zeile\n".to_string(),
        ts_ms: 1700000000000,
    };
    let insert = build_db_insert(&reading);
    assert_eq!(insert.kind, "retina");
    assert!(insert.sql.contains("INSERT INTO memory (kind, payload, ts_ms)"));
    assert!(insert.sql.contains("'retina'"));
    assert!(insert.sql.contains("1700000000000"));
    assert!(!insert.payload.is_empty());
}

#[test]
fn test_enforce_loopback_only() {
    assert!(enforce_loopback("127.0.0.1"));
    assert!(!enforce_loopback("0.0.0.0"));
    assert!(!enforce_loopback("10.0.0.1"));
    assert!(!enforce_loopback("::1"));
    assert!(!enforce_loopback("192.168.1.1"));
    assert!(!enforce_loopback("localhost"));
}

#[test]
fn test_push_grid_event_rejects_non_loopback() {
    let mut cfg = RetinaConfig::default();
    cfg.grid_host = "10.0.0.1".to_string();
    let reading = RetinaReading::Zeile {
        line: "x".to_string(),
        raw: "x\n".to_string(),
        ts_ms: 1,
    };
    let event = build_grid_event(&reading, &cfg);
    let err = push_grid_event(&event, &cfg).expect_err("non-loopback must be rejected");
    match err {
        RetinaError::LoopbackViolation(host) => assert_eq!(host, "10.0.0.1"),
        other => panic!("expected LoopbackViolation, got {:?}", other),
    }
}

// ---------------------------------------------------------------- GRID URL admission

#[test]
fn test_non_loopback_grid_url_rejected() {
    for url in [
        "http://10.0.0.1:8490",
        "http://192.168.1.10:8490",
        "http://example.com:8490",
        "http://[::1]:8490",
        "http://0.0.0.0:8490",
        "http://localhost:8490",
    ] {
        let err = parse_grid_url(url).expect_err("non-loopback URL must be rejected");
        assert!(
            matches!(err, RetinaError::LoopbackViolation(_)),
            "url {url} produced {err:?}"
        );
    }
}

#[test]
fn test_loopback_grid_url_accepted() {
    let target = parse_grid_url("http://127.0.0.1:8490").expect("loopback url");
    assert_eq!(target.host, "127.0.0.1");
    assert_eq!(target.port, 8490);

    let target = parse_grid_url("127.0.0.1:1234").expect("authority form");
    assert_eq!(target.host, "127.0.0.1");
    assert_eq!(target.port, 1234);

    let target = parse_grid_url("http://127.0.0.1").expect("default port");
    assert_eq!(target.port, DEFAULT_GRID_PORT);

    assert!(matches!(
        parse_grid_url("http://127.0.0.1:not-a-port"),
        Err(RetinaError::ParseFailed(_))
    ));
    assert!(matches!(
        parse_grid_url("ftp://127.0.0.1:8490"),
        Err(RetinaError::ParseFailed(_))
    ));
}

#[test]
fn test_grid_target_from_parts() {
    let target = grid_target_from_parts(None, Some("9000")).expect("port only");
    assert_eq!(target.host, "127.0.0.1");
    assert_eq!(target.port, 9000);

    let target = grid_target_from_parts(Some("http://127.0.0.1:7777"), Some("9000")).expect("both");
    assert_eq!(target.port, 9000);

    let target = grid_target_from_parts(None, None).expect("defaults");
    assert_eq!(target.port, DEFAULT_GRID_PORT);

    assert!(matches!(
        grid_target_from_parts(Some("http://10.0.0.1:7777"), None),
        Err(RetinaError::LoopbackViolation(_))
    ));
    assert!(matches!(
        grid_target_from_parts(None, Some("not-a-port")),
        Err(RetinaError::ParseFailed(_))
    ));
}

// ---------------------------------------------------------------- CLI behaviour

#[test]
fn test_spawn_missing_cli_returns_error() {
    let dir = unique_dir("missing");
    let cfg = RetinaConfig {
        cli_path: dir.join("retina-frage-does-not-exist"),
        ..RetinaConfig::default()
    };
    let err = spawn_retina_zeile(&cfg).expect_err("missing CLI must fail");
    assert!(matches!(err, RetinaError::CliNotFound(_)));
    assert_eq!(RETINA_UNAVAILABLE_DE, "Retina nicht verfuegbar");
    assert!(
        err.to_string().contains("Retina nicht verfuegbar"),
        "error text: {err}"
    );
}

#[test]
fn test_missing_cli_returns_honest_unavailable_text() {
    let dir = unique_dir("missing-text");
    let cfg = RetinaConfig {
        cli_path: dir.join("retina-frage-does-not-exist"),
        ..RetinaConfig::default()
    };
    let text = retina_context_text(&cfg);
    assert_eq!(text, "Retina nicht verfuegbar");
    assert!(!text.contains("mock"));
}

#[test]
fn test_read_and_push_missing_cli_is_honest_and_publishes_nothing() {
    let dir = unique_dir("missing-pipeline");
    let cfg = RetinaConfig {
        cli_path: dir.join("retina-frage-does-not-exist"),
        db_path: dir.join("unified.db"),
        ..RetinaConfig::default()
    };
    let reading = read_and_push(&cfg).expect("honest unavailable reading");
    match reading {
        RetinaReading::Unavailable { reason, .. } => {
            assert_eq!(reason, RETINA_UNAVAILABLE_DE);
        }
        RetinaReading::Zeile { .. } => panic!("expected Unavailable"),
    }
    assert!(!cfg.db_path.exists(), "no db row may be invented");
}

#[test]
fn test_failing_cli_returns_honest_unavailable_text() {
    let mut cli = MockCli::failing();
    assert_eq!(
        retina_context_text_with(&mut cli),
        "Retina nicht verfuegbar"
    );
}

#[cfg(unix)]
#[test]
fn test_spawn_retina_zeile_with_local_script() {
    let dir = unique_dir("script");
    let path = write_script(
        &dir,
        "retina-frage-test",
        "if [ \"$1\" = \"--zeile\" ]; then echo 'retina-script-line'; exit 0; fi; exit 9\n",
    );

    let mut cfg = RetinaConfig::default();
    cfg.cli_path = path;
    let output = spawn_retina_zeile(&cfg).expect("local script must run");
    assert!(output.contains("retina-script-line"));
}

#[cfg(unix)]
#[test]
fn test_spawn_retina_zeile_failing_script_is_error() {
    let dir = unique_dir("script-fail");
    let path = write_script(&dir, "retina-frage-fail", "echo boom >&2\nexit 3\n");

    let mut cfg = RetinaConfig::default();
    cfg.cli_path = path;
    let err = spawn_retina_zeile(&cfg).expect_err("failing CLI must fail");
    assert!(matches!(err, RetinaError::CliFailed(_)));
    assert!(err.to_string().contains("Retina nicht verfuegbar"));
}

// ---------------------------------------------------------------- mocked pipeline

#[test]
fn test_mock_pipeline_pushes_event_and_row() {
    let mut cli = MockCli::line("mock-zeile\n");
    let mut grid = MockGrid::default();
    let mut db = MockDb::default();
    let target = GridTarget {
        host: "127.0.0.1".to_string(),
        port: 8490,
    };
    let mut rt = RetinaRuntime {
        target: target.clone(),
        cli: &mut cli,
        grid: &mut grid,
        db: &mut db,
    };

    let reading = read_and_push_with(&mut rt).expect("pipeline must succeed");
    match &reading {
        RetinaReading::Zeile { line, .. } => assert_eq!(line, "mock-zeile"),
        RetinaReading::Unavailable { .. } => panic!("expected Zeile"),
    }

    assert_eq!(grid.events.len(), 1, "exactly one GRID event");
    let event = &grid.events[0];
    assert_eq!(event.kind, "perception");
    assert_eq!(event.source, "retina");
    assert_eq!(event.r#type, "retina_reading");
    assert_eq!(event.host, "127.0.0.1");
    assert_eq!(event.port, 8490);
    assert_eq!(event.payload["zeile"].as_str(), Some("mock-zeile"));

    assert_eq!(db.rows.len(), 1, "exactly one unified.db row");
    assert_eq!(db.rows[0].kind, "retina");
    assert!(db.rows[0].payload.contains("mock-zeile"));
    assert!(db.rows[0].sql.contains("'retina'"));
    assert!(db.rows[0].sql.contains("INSERT INTO memory"));
}

#[test]
fn test_mock_pipeline_missing_cli_publishes_nothing() {
    let mut cli = MockCli::missing();
    let mut grid = MockGrid::default();
    let mut db = MockDb::default();
    let mut rt = RetinaRuntime {
        target: GridTarget {
            host: "127.0.0.1".to_string(),
            port: 8490,
        },
        cli: &mut cli,
        grid: &mut grid,
        db: &mut db,
    };

    let err = read_and_push_with(&mut rt).expect_err("missing CLI must fail");
    assert!(matches!(err, RetinaError::CliNotFound(_)));
    assert!(grid.events.is_empty(), "no GRID event may be invented");
    assert!(db.rows.is_empty(), "no db row may be invented");
}

#[test]
fn test_mock_pipeline_empty_output_is_unknown_and_publishes_nothing() {
    let mut cli = MockCli::line("\n");
    let mut grid = MockGrid::default();
    let mut db = MockDb::default();
    let mut rt = RetinaRuntime {
        target: GridTarget {
            host: "127.0.0.1".to_string(),
            port: 8490,
        },
        cli: &mut cli,
        grid: &mut grid,
        db: &mut db,
    };

    let reading = read_and_push_with(&mut rt).expect("empty output is UNKNOWN, not an error");
    assert!(matches!(reading, RetinaReading::Unavailable { .. }));
    assert!(grid.events.is_empty());
    assert!(db.rows.is_empty());
}

// ---------------------------------------------------------------- real loopback GRID mock

#[test]
fn test_mock_grid_endpoint_receives_perception_event() {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind loopback listener");
    let port = listener.local_addr().expect("local addr").port();

    let handle = thread::spawn(move || {
        let (stream, _) = listener.accept().expect("accept");
        let mut reader = BufReader::new(stream);
        let mut line = String::new();
        reader.read_line(&mut line).expect("read event");
        line
    });

    let cfg = RetinaConfig {
        cli_path: PathBuf::from(RETINA_CLI),
        grid_host: "127.0.0.1".to_string(),
        grid_port: port,
        db_path: PathBuf::from("unified.db"),
    };
    let reading = RetinaReading::Zeile {
        line: "tcp-zeile".to_string(),
        raw: "tcp-zeile\n".to_string(),
        ts_ms: 1700000000002,
    };
    let event = build_grid_event(&reading, &cfg);
    push_grid_event(&event, &cfg).expect("push to loopback mock");

    let received = handle.join().expect("join listener");
    let value: serde_json::Value = serde_json::from_str(received.trim()).expect("json event");
    assert_eq!(value["kind"].as_str(), Some("perception"));
    assert_eq!(value["source"].as_str(), Some("retina"));
    assert_eq!(value["type"].as_str(), Some("retina_reading"));
    assert_eq!(value["payload"]["zeile"].as_str(), Some("tcp-zeile"));
    assert_eq!(value["host"].as_str(), Some("127.0.0.1"));
    assert_eq!(value["port"].as_u64(), Some(port as u64));
}

// ---------------------------------------------------------------- unified.db

#[test]
fn test_write_db_insert_rejects_foreign_kind() {
    let dir = unique_dir("kind");
    let db_path = dir.join("unified.db");
    let insert = DbInsert {
        kind: "other".to_string(),
        payload: "{}".to_string(),
        sql: "INSERT INTO memory (kind, payload, ts_ms) VALUES ('other', '{}', 1);".to_string(),
        ts_ms: 1,
    };
    let err = write_db_insert(&insert, &db_path).expect_err("foreign kind must be rejected");
    assert!(matches!(err, RetinaError::DbWrite(_)));
}

#[test]
fn test_sqlite_db_inserts_retina_row() {
    if !sqlite_available() {
        // UNKNOWN: no local sqlite3 binary -> the real DB write cannot be measured here.
        return;
    }
    let dir = unique_dir("sqlite");
    let db_path = dir.join("unified.db");
    let reading = RetinaReading::Zeile {
        line: "sqlite-zeile".to_string(),
        raw: "sqlite-zeile\n".to_string(),
        ts_ms: 1700000000000,
    };
    let insert = build_db_insert(&reading);
    let mut db = SqliteDb::with_binary(db_path.clone(), PathBuf::from("sqlite3"));
    db.insert(&insert).expect("sqlite insert");

    let out = Command::new("sqlite3")
        .arg(&db_path)
        .arg("SELECT kind FROM memory;")
        .output()
        .expect("query");
    assert!(out.status.success(), "sqlite query failed");
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(text.contains("retina"), "expected kind='retina' row, got: {text}");
}

// ================================================================
// ACCEPTANCE TESTS - exact names required by the task
// ================================================================

/// test_retina_cli_one_line_state: verifies the CLI --zeile output is parsed as a one-line state
#[test]
fn test_retina_cli_one_line_state() {
    let mut cli = MockCli::line("retina-one-line-state\n");
    let mut grid = MockGrid::default();
    let mut db = MockDb::default();
    let target = GridTarget {
        host: "127.0.0.1".to_string(),
        port: 8490,
    };
    let mut rt = RetinaRuntime {
        target,
        cli: &mut cli,
        grid: &mut grid,
        db: &mut db,
    };

    let reading = read_and_push_with(&mut rt).expect("pipeline must succeed");
    match reading {
        RetinaReading::Zeile { line, raw, ts_ms } => {
            assert_eq!(line, "retina-one-line-state");
            assert_eq!(raw, "retina-one-line-state");
            assert!(ts_ms > 0);
        }
        RetinaReading::Unavailable { .. } => panic!("expected Zeile reading"),
    }
}

/// test_push_to_grid_loopback: verifies a perception event is pushed to loopback GRID
#[test]
fn test_push_to_grid_loopback() {
    let listener = TcpListener::bind("127.0.0.1:0").expect("bind loopback listener");
    let port = listener.local_addr().expect("local addr").port();

    let handle = thread::spawn(move || {
        let (stream, _) = listener.accept().expect("accept");
        let mut reader = BufReader::new(stream);
        let mut line = String::new();
        reader.read_line(&mut line).expect("read event");
        line
    });

    let cfg = RetinaConfig {
        cli_path: PathBuf::from(RETINA_CLI),
        grid_host: "127.0.0.1".to_string(),
        grid_port: port,
        db_path: PathBuf::from("unified.db"),
    };
    let reading = RetinaReading::Zeile {
        line: "loopback-test-zeile".to_string(),
        raw: "loopback-test-zeile\n".to_string(),
        ts_ms: 1700000000003,
    };
    let event = build_grid_event(&reading, &cfg);
    push_grid_event(&event, &cfg).expect("push to loopback GRID");

    let received = handle.join().expect("join listener");
    let value: Value = serde_json::from_str(received.trim()).expect("json event");
    assert_eq!(value["kind"].as_str(), Some("perception"));
    assert_eq!(value["source"].as_str(), Some("retina"));
    assert_eq!(value["type"].as_str(), Some("retina_reading"));
    assert_eq!(value["payload"]["zeile"].as_str(), Some("loopback-test-zeile"));
    assert_eq!(value["host"].as_str(), Some("127.0.0.1"));
    assert_eq!(value["port"].as_u64(), Some(port as u64));
}

/// test_push_to_entityos_unified_db: verifies a retina reading is written to unified.db with kind='retina'
#[test]
fn test_push_to_entityos_unified_db() {
    if !sqlite_available() {
        // UNKNOWN: no local sqlite3 binary -> the real DB write cannot be measured here.
        return;
    }
    let dir = unique_dir("entityos");
    let db_path = dir.join("unified.db");
    let reading = RetinaReading::Zeile {
        line: "entityos-test-zeile".to_string(),
        raw: "entityos-test-zeile\n".to_string(),
        ts_ms: 1700000000004,
    };
    let insert = build_db_insert(&reading);
    let mut db = SqliteDb::with_binary(db_path.clone(), PathBuf::from("sqlite3"));
    db.insert(&insert).expect("sqlite insert");

    let out = Command::new("sqlite3")
        .arg(&db_path)
        .arg("SELECT kind, payload FROM memory;")
        .output()
        .expect("query");
    assert!(out.status.success(), "sqlite query failed");
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(text.contains("retina"), "expected kind='retina' row, got: {text}");
    assert!(text.contains("entityos-test-zeile"), "payload not found: {text}");
}
