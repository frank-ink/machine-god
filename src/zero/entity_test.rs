use crate::zero::entity::*;
use crate::zero::grid::{ComponentStatus, GridHealth, HealthState};
use std::ffi::OsStr;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, SystemTime};

static COUNTER: AtomicU64 = AtomicU64::new(0);

struct TempPlugin {
    dir: PathBuf,
}

impl TempPlugin {
    fn new(manifest: &str, plugin: &str) -> Self {
        let id = COUNTER.fetch_add(1, Ordering::Relaxed);
        let dir =
            std::env::temp_dir().join(format!("zero-entity-test-{}-{}", std::process::id(), id));
        fs::create_dir_all(&dir).expect("create temp plugin dir");
        fs::write(dir.join(ZERO_MANIFEST_FILE), manifest).expect("write zero-manifest.json");
        fs::write(dir.join(PLUGIN_FILE), plugin).expect("write plugin.json");
        Self { dir }
    }

    fn path(&self) -> &Path {
        &self.dir
    }
}

impl Drop for TempPlugin {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.dir);
    }
}

fn ok_grid(now: SystemTime) -> GridHealth {
    GridHealth {
        status: ComponentStatus::measured_at(HealthState::Ok, now),
        http_status: Some(200),
        detail: None,
    }
}

/// Independent re-implementation of the documented f3_paths data-directory
/// precedence. Used only as a cross-check against the production resolver.
fn reference_data_dir(env: &EnvSnapshot, plugin_dir: &Path) -> PathBuf {
    let explicit =
        [PLUGIN_DATA_DIR_ENV, FRANKENSTEIN3_DATA_DIR_ENV, FRANKENSTEIN3_PLUGIN_DATA_DIR_ENV]
            .iter()
            .find_map(|key| env.get(key));

    if let Some(value) = explicit {
        return PathBuf::from(value);
    }
    if let Some(xdg) = env.get(XDG_DATA_HOME_ENV) {
        return PathBuf::from(xdg).join(PLUGIN_DATA_DIR_NAME);
    }
    if let Some(home) = env.get(HOME_ENV) {
        return PathBuf::from(home).join(".local").join("share").join(PLUGIN_DATA_DIR_NAME);
    }
    plugin_dir.to_path_buf()
}

#[test]
fn identity_from_plugin_manifest() {
    let plugin = TempPlugin::new(
        r#"{"entity_name":"zero-entity","version":"3.1.0","entity_id":"zero-42","root_state":{"mode":"ground"}}"#,
        r#"{"name":"frankenstein3","version":"0.0.1"}"#,
    );

    let snapshot = load_entity_state(plugin.path()).unwrap();

    // The manifest is the identity authority, not plugin.json.
    assert_eq!(snapshot.identity.name, "zero-entity");
    assert_eq!(snapshot.identity.version.as_deref(), Some("3.1.0"));
    assert_eq!(snapshot.identity.entity_id.as_deref(), Some("zero-42"));
    assert!(snapshot.identity.source.ends_with(ZERO_MANIFEST_FILE));
}

#[test]
fn root_state_loads() {
    let plugin = TempPlugin::new(
        r#"{"entity_name":"zero-entity","root_state":{"mode":"ground","goals":[]}}"#,
        r#"{"name":"frankenstein3","version":"3.0.0"}"#,
    );

    let snapshot = load_entity_state(plugin.path()).unwrap();

    assert_eq!(snapshot.root.value["mode"], "ground");
    assert!(snapshot.root.value["goals"].is_array());
    assert!(snapshot.root.source.ends_with(ZERO_MANIFEST_FILE));
}

#[test]
fn health_check_measured() {
    let plugin = TempPlugin::new(
        r#"{"entity_name":"zero-entity","root_state":{"mode":"ground"}}"#,
        r#"{"name":"frankenstein3"}"#,
    );
    let now = SystemTime::now();

    let paths = PluginPaths {
        plugin_dir: plugin.path().to_path_buf(),
        data_dir: plugin.path().join("data"),
    };
    let health = entity_health_at(&paths, now);

    assert_eq!(health.class, EntityHealthClass::MeasuredOk);
    assert!(health.is_measured_ok());
    assert!(health.detail.is_none());
    assert_eq!(health.identity_name.as_deref(), Some("zero-entity"));
    // The database file was not created: presence is measured, not assumed.
    assert!(!health.db_present);
    assert_eq!(health.status(now).effective_state(now), HealthState::Ok);

    // A missing manifest is UNKNOWN, never OK.
    let broken = std::env::temp_dir().join(format!(
        "zero-entity-health-{}-{}",
        std::process::id(),
        COUNTER.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir_all(&broken).expect("create temp dir");
    let broken_paths = PluginPaths { plugin_dir: broken.clone(), data_dir: broken.join("data") };
    let broken_health = entity_health_at(&broken_paths, now);
    let _ = fs::remove_dir_all(&broken);

    assert_eq!(broken_health.class, EntityHealthClass::Unknown);
    assert!(broken_health.detail.is_some());
    assert_eq!(broken_health.status(now).effective_state(now), HealthState::Unknown);
}

#[test]
fn db_path_matches_retina() {
    let plugin = TempPlugin::new(
        r#"{"entity_name":"zero-entity","root_state":{}}"#,
        r#"{"name":"frankenstein3"}"#,
    );

    let env = EnvSnapshot::from_pairs([
        (PLUGIN_DIR_ENV, plugin.path().to_string_lossy().to_string()),
        (PLUGIN_DATA_DIR_ENV, plugin.path().join("data").to_string_lossy().to_string()),
    ]);

    let paths = resolve_plugin_paths(&env, &bundled_plugin_dir());
    let entity_db = paths.unified_db_path();

    // The retina-side entry point resolves to the very same file.
    assert_eq!(unified_db_path_for(&paths), entity_db);
    assert_eq!(retina_unified_db_path(), unified_db_path());

    // Cross-check against an independent implementation of the precedence.
    let reference = reference_data_dir(&env, plugin.path()).join(UNIFIED_DB_FILE);
    assert_eq!(entity_db, reference);
    assert_eq!(entity_db.file_name(), Some(OsStr::new(UNIFIED_DB_FILE)));
    assert_eq!(entity_db.parent(), Some(plugin.path().join("data").as_path()));
}

#[test]
fn entity_reads_zero_manifest_root_state() {
    let plugin = TempPlugin::new(
        r#"{"root_state":{"mode":"ground","goals":[]}}"#,
        r#"{"name":"frankenstein3","version":"3.0.0"}"#,
    );

    let snapshot = load_entity_state(plugin.path()).unwrap();

    assert_eq!(snapshot.root.value["mode"], "ground");
    assert!(snapshot.root.value["goals"].is_array());
    assert!(snapshot.root.source.ends_with(ZERO_MANIFEST_FILE));
}

#[test]
fn entity_reads_plugin_json_identity_as_fallback() {
    let plugin = TempPlugin::new(
        r#"{"root_state":{"mode":"ground"}}"#,
        r#"{"name":"frankenstein3","version":"3.0.0"}"#,
    );

    let snapshot = load_entity_state(plugin.path()).unwrap();

    assert_eq!(snapshot.identity.name, "frankenstein3");
    assert_eq!(snapshot.identity.version.as_deref(), Some("3.0.0"));
    assert!(snapshot.identity.source.ends_with(ZERO_MANIFEST_FILE));
}

#[test]
fn entity_reads_manifest_entity_id() {
    let plugin =
        TempPlugin::new(r#"{"entity_id":"zero-1","root_state":{}}"#, r#"{"name":"frankenstein3"}"#);

    let snapshot = load_entity_state(plugin.path()).unwrap();

    assert_eq!(snapshot.identity.entity_id.as_deref(), Some("zero-1"));
}

#[test]
fn entity_root_state_falls_back_to_manifest_object() {
    let plugin = TempPlugin::new(r#"{"custom":"value"}"#, r#"{"name":"frankenstein3"}"#);

    let snapshot = load_entity_state(plugin.path()).unwrap();

    assert_eq!(snapshot.root.value["custom"], "value");
}

#[test]
fn entity_missing_manifest_is_error() {
    let dir = std::env::temp_dir().join(format!(
        "zero-entity-missing-{}-{}",
        std::process::id(),
        COUNTER.fetch_add(1, Ordering::Relaxed)
    ));
    fs::create_dir_all(&dir).expect("create temp dir");
    fs::write(dir.join(PLUGIN_FILE), r#"{"name":"frankenstein3"}"#).expect("write plugin.json");

    let result = load_entity_state(&dir);
    let _ = fs::remove_dir_all(&dir);

    assert!(matches!(result, Err(EntityError::Read { .. })));
}

#[test]
fn entity_malformed_plugin_json_is_error() {
    let plugin = TempPlugin::new(r#"{"root_state":{}}"#, "{not json");

    let result = load_entity_state(plugin.path());

    assert!(matches!(result, Err(EntityError::Json { .. })));
}

#[test]
fn entity_missing_plugin_name_is_error() {
    let plugin = TempPlugin::new(r#"{"root_state":{}}"#, r#"{"version":"3.0.0"}"#);

    let result = load_entity_state(plugin.path());

    assert!(matches!(result, Err(EntityError::MissingPluginName)));
}

#[test]
fn entity_data_dir_precedence() {
    let plugin_dir = PathBuf::from("plugin");
    let bundled = PathBuf::from("bundled");

    let explicit = EnvSnapshot::from_pairs([
        (PLUGIN_DATA_DIR_ENV, "explicit".to_owned()),
        (XDG_DATA_HOME_ENV, "xdg".to_owned()),
        (HOME_ENV, "home".to_owned()),
    ]);
    assert_eq!(resolve_data_dir(&explicit, &plugin_dir, None), PathBuf::from("explicit"));

    let xdg = EnvSnapshot::from_pairs([
        (XDG_DATA_HOME_ENV, "xdg".to_owned()),
        (HOME_ENV, "home".to_owned()),
    ]);
    assert_eq!(
        resolve_data_dir(&xdg, &plugin_dir, None),
        PathBuf::from("xdg").join(PLUGIN_DATA_DIR_NAME)
    );

    let home = EnvSnapshot::from_pairs([(HOME_ENV, "home".to_owned())]);
    assert_eq!(
        resolve_data_dir(&home, &plugin_dir, None),
        PathBuf::from("home").join(".local").join("share").join(PLUGIN_DATA_DIR_NAME)
    );

    let empty = EnvSnapshot::default();
    assert_eq!(resolve_data_dir(&empty, &plugin_dir, None), plugin_dir);

    // Plugin directory precedence: env wins over the bundled plugin.
    let env_plugin = EnvSnapshot::from_pairs([(PLUGIN_DIR_ENV, "chosen".to_owned())]);
    assert_eq!(resolve_plugin_dir(&env_plugin, &bundled), PathBuf::from("chosen"));
    assert_eq!(resolve_plugin_dir(&empty, &bundled), bundled);
}

#[test]
fn entity_manifest_declared_data_dir_is_used() {
    let plugin = TempPlugin::new(
        r#"{"entity_name":"zero-entity","data_dir":"state","root_state":{}}"#,
        r#"{"name":"frankenstein3"}"#,
    );

    let env =
        EnvSnapshot::from_pairs([(PLUGIN_DIR_ENV, plugin.path().to_string_lossy().to_string())]);
    let paths = resolve_plugin_paths(&env, &bundled_plugin_dir());

    assert_eq!(paths.data_dir, plugin.path().join("state"));
    assert_eq!(paths.unified_db_path(), plugin.path().join("state").join(UNIFIED_DB_FILE));
}

#[test]
fn entity_status_line_marks_entity_measured() {
    let plugin =
        TempPlugin::new(r#"{"root_state":{"mode":"ground"}}"#, r#"{"name":"frankenstein3"}"#);
    let now = SystemTime::now();
    let snapshot = load_entity_state_at(plugin.path(), now).unwrap();

    let retina = ComponentStatus::measured_at(HealthState::Ok, now);
    let omnipool = ComponentStatus::measured_at(HealthState::Ok, now);

    let line = status_line_from_snapshot(&ok_grid(now), &retina, &snapshot, &omnipool, now);

    assert_eq!(line, "GRID ok | Retina ok | EntityOS ok | Omnipool ok");
}

#[test]
fn entity_status_line_unknown_when_stale() {
    let plugin =
        TempPlugin::new(r#"{"root_state":{"mode":"ground"}}"#, r#"{"name":"frankenstein3"}"#);
    let now = SystemTime::now();
    let old = now.checked_sub(Duration::from_secs(31)).unwrap();
    let snapshot = load_entity_state_at(plugin.path(), old).unwrap();

    let retina = ComponentStatus::measured_at(HealthState::Ok, now);
    let omnipool = ComponentStatus::measured_at(HealthState::Ok, now);

    let line = status_line_from_snapshot(&ok_grid(now), &retina, &snapshot, &omnipool, now);

    assert_eq!(line, "GRID ok | Retina ok | EntityOS UNKNOWN | Omnipool ok");
}

#[test]
fn entity_status_line_unknown_components_are_not_failures() {
    let now = SystemTime::now();
    let entity = ComponentStatus::unknown();

    let line = format_entity_status_line(
        &ok_grid(now),
        &ComponentStatus::unknown(),
        &entity,
        &ComponentStatus::unknown(),
        now,
    );

    assert_eq!(line, "GRID ok | Retina UNKNOWN | EntityOS UNKNOWN | Omnipool UNKNOWN");
    let labeled = format_entity_status_line_labeled(
        &ok_grid(now),
        &ComponentStatus::unknown(),
        &entity,
        &ComponentStatus::unknown(),
        now,
    );
    assert_eq!(labeled, "GRID MEASURED | Retina UNKNOWN | EntityOS UNKNOWN | Omnipool UNKNOWN");
}

#[test]
fn entity_bundled_plugin_dir_points_to_bundled_plugin() {
    let dir = bundled_plugin_dir();

    assert!(dir.ends_with(BUNDLED_PLUGIN_RELATIVE));
    assert!(dir.ends_with("frankenstein3"));
}
