use crate::zero::grid::*;
use serde_json::Value;
use std::sync::{Arc, Mutex};
use std::time::{Duration, SystemTime};

#[derive(Debug)]
struct MockTransport {
    requests: Mutex<Vec<GridHttpRequest>>,
    response: Mutex<Result<GridHttpResponse, GridTransportError>>,
}

impl Default for MockTransport {
    fn default() -> Self {
        Self {
            requests: Mutex::new(Vec::new()),
            response: Mutex::new(Ok(GridHttpResponse::ok("{}"))),
        }
    }
}

impl MockTransport {
    fn returning(response: GridHttpResponse) -> Self {
        Self { requests: Mutex::new(Vec::new()), response: Mutex::new(Ok(response)) }
    }

    fn failing(message: &str) -> Self {
        Self {
            requests: Mutex::new(Vec::new()),
            response: Mutex::new(Err(GridTransportError::new(message))),
        }
    }

    fn requests(&self) -> Vec<GridHttpRequest> {
        self.requests.lock().expect("mock lock").clone()
    }
}

impl GridTransport for MockTransport {
    fn request(&self, request: &GridHttpRequest) -> Result<GridHttpResponse, GridTransportError> {
        self.requests.lock().expect("mock lock").push(request.clone());
        self.response.lock().expect("mock lock").clone()
    }
}

fn client_with(transport: Arc<MockTransport>) -> GridClient {
    GridClient::with_shared_transport(
        GridEndpoint::from_port(DEFAULT_GRID_PORT).expect("loopback endpoint"),
        GridPaths::default(),
        transport,
    )
    .expect("client")
}

#[test]
fn grid_default_port_is_8490() {
    assert_eq!(DEFAULT_GRID_PORT, 8490);
}

#[test]
fn grid_endpoint_rejects_non_loopback_hosts() {
    for host in ["0.0.0.0", "192.168.1.10", "localhost", "::1", "example.com", "127.0.0.2"] {
        let error = GridEndpoint::new(host, DEFAULT_GRID_PORT).unwrap_err();
        assert!(error.to_string().contains("127.0.0.1"), "unexpected error for {host}: {error}");
    }
}

#[test]
fn grid_endpoint_accepts_literal_loopback() {
    let endpoint = GridEndpoint::new("127.0.0.1", 8490).unwrap();
    assert_eq!(endpoint.host().to_string(), "127.0.0.1");
    assert_eq!(endpoint.port(), 8490);
    assert_eq!(endpoint.authority(), "127.0.0.1:8490");
}

#[test]
fn grid_endpoint_rejects_port_zero() {
    assert!(GridEndpoint::new("127.0.0.1", 0).is_err());
}

#[test]
fn grid_health_ok_is_measured() {
    let transport = Arc::new(MockTransport::returning(GridHttpResponse::ok(r#"{"status":"ok"}"#)));
    let client = client_with(transport);
    let now = SystemTime::now();

    let health = client.check_health_at(now);

    assert_eq!(health.status.state, HealthState::Ok);
    assert_eq!(health.status.last_success, Some(now));
    assert_eq!(health.http_status, Some(200));
    assert_eq!(health.state_at(now), HealthState::Ok);
}

#[test]
fn grid_health_degraded_is_measured() {
    let transport =
        Arc::new(MockTransport::returning(GridHttpResponse::ok(r#"{"status":"degraded"}"#)));
    let client = client_with(transport);

    let health = client.check_health_at(SystemTime::now());

    assert_eq!(health.status.state, HealthState::Degraded);
    assert!(health.status.last_success.is_some());
}

#[test]
fn grid_health_degraded_on_http_error_status() {
    let transport = Arc::new(MockTransport::returning(GridHttpResponse {
        status: 503,
        body: b"unavailable".to_vec(),
    }));
    let client = client_with(transport);

    let health = client.check_health_at(SystemTime::now());

    assert_eq!(health.status.state, HealthState::Degraded);
    assert_eq!(health.http_status, Some(503));
}

#[test]
fn grid_health_unknown_when_unreachable() {
    let transport = Arc::new(MockTransport::failing("connection refused"));
    let client = client_with(transport);

    let health = client.check_health_at(SystemTime::now());

    assert_eq!(health.status.state, HealthState::Unknown);
    assert_eq!(health.status.last_success, None);
    assert_eq!(health.http_status, None);
}

#[test]
fn grid_event_push_uses_json_post() {
    let transport = Arc::new(MockTransport::returning(GridHttpResponse {
        status: 202,
        body: b"accepted".to_vec(),
    }));
    let client = client_with(transport.clone());
    let event = GridEvent::new("retina", serde_json::json!({"text": "local"}));

    let receipt = client.push_event(&event).unwrap();

    assert!(receipt.accepted);
    assert_eq!(receipt.http_status, 202);

    let requests = transport.requests();
    assert_eq!(requests.len(), 1);
    assert_eq!(requests[0].method, "POST");
    assert_eq!(requests[0].path, "/event");

    let body: Value = serde_json::from_slice(requests[0].body.as_ref().unwrap()).unwrap();
    assert_eq!(body["kind"], "retina");
    assert_eq!(body["payload"]["text"], "local");
}

#[test]
fn grid_event_push_rejects_non_success_response() {
    let transport = Arc::new(MockTransport::returning(GridHttpResponse {
        status: 503,
        body: b"unavailable".to_vec(),
    }));
    let client = client_with(transport);

    let error = client.push_event(&GridEvent::new("test", Value::Null)).unwrap_err();

    assert!(matches!(error, GridError::Rejected { status: 503, .. }));
}

#[test]
fn grid_event_push_targets_loopback_authority_only() {
    let transport = Arc::new(MockTransport::returning(GridHttpResponse::ok("{}")));
    let client = client_with(transport.clone());

    client.push_event(&GridEvent::new("test", Value::Null)).unwrap();

    assert_eq!(client.endpoint().host().to_string(), "127.0.0.1");
    assert_eq!(client.endpoint().port(), DEFAULT_GRID_PORT);
}

#[test]
fn status_line_formats_measured_components() {
    let now = SystemTime::now();
    let measured = ComponentStatus::measured_at(HealthState::Ok, now);
    let input = StatusLineInput {
        now,
        grid: measured.clone(),
        retina: measured.clone(),
        entityos: measured.clone(),
        omnipool: measured,
    };

    assert_eq!(format_status_line(&input), "GRID ok | Retina ok | EntityOS ok | Omnipool ok");
    assert_eq!(
        format_status_line_labeled(&input),
        "GRID MEASURED | Retina MEASURED | EntityOS MEASURED | Omnipool MEASURED"
    );
}

#[test]
fn status_line_formats_unknown_components() {
    let now = SystemTime::now();
    let measured = ComponentStatus::measured_at(HealthState::Ok, now);
    let input = StatusLineInput {
        now,
        grid: measured.clone(),
        retina: ComponentStatus::unknown(),
        entityos: measured.clone(),
        omnipool: ComponentStatus::unknown(),
    };

    assert_eq!(
        format_status_line(&input),
        "GRID ok | Retina UNKNOWN | EntityOS ok | Omnipool UNKNOWN"
    );
    assert_eq!(
        format_status_line_labeled(&input),
        "GRID MEASURED | Retina UNKNOWN | EntityOS MEASURED | Omnipool UNKNOWN"
    );
}

#[test]
fn status_line_formats_degraded_component() {
    let now = SystemTime::now();
    let input = StatusLineInput {
        now,
        grid: ComponentStatus::measured_at(HealthState::Degraded, now),
        retina: ComponentStatus::measured_at(HealthState::Ok, now),
        entityos: ComponentStatus::measured_at(HealthState::Ok, now),
        omnipool: ComponentStatus::measured_at(HealthState::Ok, now),
    };

    assert_eq!(format_status_line(&input), "GRID degraded | Retina ok | EntityOS ok | Omnipool ok");
    assert_eq!(
        format_status_line_labeled(&input),
        "GRID MEASURED | Retina MEASURED | EntityOS MEASURED | Omnipool MEASURED"
    );
}

#[test]
fn staleness_over_thirty_seconds_flips_to_unknown() {
    let now = SystemTime::now();
    let old = now.checked_sub(Duration::from_secs(31)).unwrap();

    let status = evaluate_component_status(Some(old), now);

    assert_eq!(status.state, HealthState::Unknown);
    assert_eq!(status.last_success, None);
}

#[test]
fn exactly_thirty_seconds_is_not_fresh() {
    let now = SystemTime::now();
    let boundary = now.checked_sub(Duration::from_secs(30)).unwrap();

    let status = evaluate_component_status(Some(boundary), now);

    assert_eq!(status.state, HealthState::Unknown);
}

#[test]
fn fresh_measurement_below_thirty_seconds_stays_measured() {
    let now = SystemTime::now();
    let recent = now.checked_sub(Duration::from_secs(29)).unwrap();

    let status = evaluate_component_status(Some(recent), now);

    assert_eq!(status.state, HealthState::Ok);
    assert_eq!(status.last_success, Some(recent));
}

#[test]
fn test_health_status_line_measured_unknown() {
    let now = SystemTime::now();
    let measured_ok = ComponentStatus::measured_at(HealthState::Ok, now);
    let measured_degraded = ComponentStatus::measured_at(HealthState::Degraded, now);
    let unknown = ComponentStatus::unknown();

    let input_all_ok = StatusLineInput {
        now,
        grid: measured_ok.clone(),
        retina: measured_ok.clone(),
        entityos: measured_ok.clone(),
        omnipool: measured_ok.clone(),
    };
    assert_eq!(
        format_status_line(&input_all_ok),
        "GRID ok | Retina ok | EntityOS ok | Omnipool ok"
    );
    assert_eq!(
        format_status_line_labeled(&input_all_ok),
        "GRID MEASURED | Retina MEASURED | EntityOS MEASURED | Omnipool MEASURED"
    );

    let input_mixed = StatusLineInput {
        now,
        grid: measured_ok.clone(),
        retina: unknown.clone(),
        entityos: measured_degraded.clone(),
        omnipool: unknown.clone(),
    };
    assert_eq!(
        format_status_line(&input_mixed),
        "GRID ok | Retina UNKNOWN | EntityOS degraded | Omnipool UNKNOWN"
    );
    assert_eq!(
        format_status_line_labeled(&input_mixed),
        "GRID MEASURED | Retina UNKNOWN | EntityOS MEASURED | Omnipool UNKNOWN"
    );

    let input_all_unknown = StatusLineInput {
        now,
        grid: unknown.clone(),
        retina: unknown.clone(),
        entityos: unknown.clone(),
        omnipool: unknown.clone(),
    };
    assert_eq!(
        format_status_line(&input_all_unknown),
        "GRID UNKNOWN | Retina UNKNOWN | EntityOS UNKNOWN | Omnipool UNKNOWN"
    );
    assert_eq!(
        format_status_line_labeled(&input_all_unknown),
        "GRID UNKNOWN | Retina UNKNOWN | EntityOS UNKNOWN | Omnipool UNKNOWN"
    );
}
