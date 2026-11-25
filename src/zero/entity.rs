//! Entity identity and root-state loading from the bundled frankenstein3 plugin.
//!
//! GRF binding
//! -----------
//! * `R_t`  = persisted plugin state: `zero-manifest.json`, `plugin.json` and
//!   the plugin data directory that owns `unified.db`.
//! * `E_t`  = bytes observed on disk (manifest, plugin metadata, db presence).
//! * `F`    = `load_entity_state_at` / `entity_health_at` (pure with respect to
//!   their explicit inputs).
//! * `M`    = admissibility space: only files below the resolved plugin or
//!   data directory are admissible evidence.
//!
//! Missing or malformed evidence is reported as an error or UNKNOWN; it is
//! never replaced by an invented identity or root state.
//!
//! Path resolution (`f3_paths.py` precedence)
//! ----------------------------------------
//! Plugin directory:
//!   1. `MACHINE_GOD_PLUGIN_DIR`
//!   2. `FRANKENSTEIN3_PLUGIN_DIR`
//!   3. bundled `plugins/frankenstein3` (searched upwards from the crate root)
//!
//! Plugin data directory:
//!   1. `MACHINE_GOD_PLUGIN_DATA_DIR`
//!   2. `FRANKENSTEIN3_DATA_DIR`
//!   3. `FRANKENSTEIN3_PLUGIN_DATA_DIR`
//!   4. `data_dir` declared by `zero-manifest.json` (relative paths resolve
//!      against the plugin directory)
//!   5. `$XDG_DATA_HOME/frankenstein3`
//!   6. `$HOME/.local/share/frankenstein3`
//!   7. the plugin directory itself (portable fallback)
//!
//! `unified.db` always resolves to `<plugin data dir>/unified.db`. This module
//! is the canonical resolver: retina consumes `entity::unified_db_path()` so
//! both organs address one database file.

use crate::zero::grid::{
    ComponentStatus, GridHealth, HealthState, format_status_line_at, format_status_line_labeled_at,
};
use serde_json::Value;
use std::collections::BTreeMap;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::time::SystemTime;
use thiserror::Error;

pub const ZERO_MANIFEST_FILE: &str = "zero-manifest.json";
pub const PLUGIN_FILE: &str = "plugin.json";
pub const UNIFIED_DB_FILE: &str = "unified.db";
pub const CLAUDE_PLUGIN_DIR: &str = ".claude-plugin";
pub const PLUGIN_DIR_ENV: &str = "MACHINE_GOD_PLUGIN_DIR";
pub const FRANKENSTEIN3_PLUGIN_DIR_ENV: &str = "FRANKENSTEIN3_PLUGIN_DIR";
pub const PLUGIN_DATA_DIR_ENV: &str = "MACHINE_GOD_PLUGIN_DATA_DIR";
pub const FRANKENSTEIN3_DATA_DIR_ENV: &str = "FRANKENSTEIN3_DATA_DIR";
pub const FRANKENSTEIN3_PLUGIN_DATA_DIR_ENV: &str = "FRANKENSTEIN3_PLUGIN_DATA_DIR";
pub const XDG_DATA_HOME_ENV: &str = "XDG_DATA_HOME";
pub const HOME_ENV: &str = "HOME";
pub const BUNDLED_PLUGIN_RELATIVE: &str = "plugins/frankenstein3";
pub const PLUGIN_DATA_DIR_NAME: &str = "frankenstein3";

/// Environment keys that participate in path resolution. Only these keys are
/// captured from the process environment; unrelated variables (and therefore
/// unrelated secrets) are never read into the resolver state.
pub const PATH_ENV_KEYS: &[&str] = &[
    PLUGIN_DIR_ENV,
    FRANKENSTEIN3_PLUGIN_DIR_ENV,
    PLUGIN_DATA_DIR_ENV,
    FRANKENSTEIN3_DATA_DIR_ENV,
    FRANKENSTEIN3_PLUGIN_DATA_DIR_ENV,
    XDG_DATA_HOME_ENV,
    HOME_ENV,
];

#[derive(Debug, Error)]
pub enum EntityError {
    #[error("failed to read {path}: {source}")]
    Read {
        path: PathBuf,
        #[source]
        source: io::Error,
    },
    #[error("failed to parse JSON in {path}: {source}")]
    Json {
        path: PathBuf,
        #[source]
        source: serde_json::Error,
    },
    #[error("{path} must contain a JSON object")]
    NotAnObject { path: PathBuf },
    #[error("plugin.json is missing the required string field `name`")]
    MissingPluginName,
}

/// Identity evidence extracted from the bundled plugin.
///
/// `source` is the authority file: `zero-manifest.json` is the primary
/// identity authority; `plugin.json` is only a fallback evidence source.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EntityIdentity {
    pub name: String,
    pub version: Option<String>,
    pub entity_id: Option<String>,
    pub source: PathBuf,
}

/// Root-state evidence extracted from `zero-manifest.json`.
#[derive(Debug, Clone, PartialEq)]
pub struct EntityRootState {
    pub value: Value,
    pub source: PathBuf,
}

impl EntityRootState {
    pub fn get(&self, key: &str) -> Option<&Value> {
        self.value.get(key)
    }
}

/// A measured snapshot of the entity root state.
#[derive(Debug, Clone, PartialEq)]
pub struct EntitySnapshot {
    pub identity: EntityIdentity,
    pub root: EntityRootState,
    pub observed_at: SystemTime,
}

impl EntitySnapshot {
    /// Component status derived from the snapshot timestamp; freshness is
    /// re-evaluated by the caller against `now`.
    pub fn status(&self) -> ComponentStatus {
        ComponentStatus::measured_at(HealthState::Ok, self.observed_at)
    }

    pub fn state_at(&self, now: SystemTime) -> HealthState {
        self.status().effective_state(now)
    }
}

/// Resolved plugin locations. One structure, one authority.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PluginPaths {
    /// Directory that carries the plugin payload (`plugin.json`, manifest).
    pub plugin_dir: PathBuf,
    /// Directory that carries mutable plugin data (`unified.db`).
    pub data_dir: PathBuf,
}

impl PluginPaths {
    /// The one canonical `unified.db` path for every organ.
    pub fn unified_db_path(&self) -> PathBuf {
        self.data_dir.join(UNIFIED_DB_FILE)
    }
}

/// Epistemic class of an entity health measurement.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EntityHealthClass {
    /// The plugin state was actually read and parsed.
    MeasuredOk,
    /// The measurement failed; the cause is carried in `detail`.
    Unknown,
}

/// A measured health record for `EntityOS`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EntityHealth {
    pub class: EntityHealthClass,
    pub detail: Option<String>,
    pub observed_at: SystemTime,
    /// Canonical database path that belongs to this entity.
    pub db_path: PathBuf,
    /// Whether that database file was observed on disk.
    pub db_present: bool,
    /// Identity name, only present when the state was actually loaded.
    pub identity_name: Option<String>,
}

impl EntityHealth {
    pub fn is_measured_ok(&self) -> bool {
        self.class == EntityHealthClass::MeasuredOk
    }

    /// Freshness-gated component status. UNKNOWN is never reported as OK.
    pub fn status(&self, now: SystemTime) -> ComponentStatus {
        match self.class {
            EntityHealthClass::MeasuredOk => {
                ComponentStatus::measured_at(HealthState::Ok, self.observed_at).reevaluated(now)
            }
            EntityHealthClass::Unknown => ComponentStatus::unknown(),
        }
    }
}

/// A deterministic snapshot of the environment variables used for path
/// resolution. Keeping this explicit makes the resolver pure and testable.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct EnvSnapshot {
    vars: BTreeMap<String, String>,
}

impl EnvSnapshot {
    /// Captures only the path-resolution keys from the process environment.
    pub fn from_process() -> Self {
        let mut vars = BTreeMap::new();
        for key in PATH_ENV_KEYS {
            if let Ok(value) = std::env::var(key) {
                vars.insert((*key).to_owned(), value);
            }
        }
        Self { vars }
    }

    /// Builds a snapshot from explicit pairs (test / replay input).
    pub fn from_pairs<I, K, V>(pairs: I) -> Self
    where
        I: IntoIterator<Item = (K, V)>,
        K: Into<String>,
        V: Into<String>,
    {
        let mut vars = BTreeMap::new();
        for (key, value) in pairs {
            vars.insert(key.into(), value.into());
        }
        Self { vars }
    }

    /// Returns a trimmed, non-empty value for `key`.
    pub fn get(&self, key: &str) -> Option<&str> {
        self.vars.get(key).map(|value| value.trim()).filter(|value| !value.is_empty())
    }

    pub fn set(&mut self, key: &str, value: &str) {
        self.vars.insert(key.to_owned(), value.to_owned());
    }

    pub fn unset(&mut self, key: &str) {
        self.vars.remove(key);
    }
}

/// Reads and parses a JSON object from disk.
pub fn read_json_object(path: &Path) -> Result<Value, EntityError> {
    let text = fs::read_to_string(path)
        .map_err(|source| EntityError::Read { path: path.to_path_buf(), source })?;

    let value: Value = serde_json::from_str(&text)
        .map_err(|source| EntityError::Json { path: path.to_path_buf(), source })?;

    if !value.is_object() {
        return Err(EntityError::NotAnObject { path: path.to_path_buf() });
    }

    Ok(value)
}

/// Candidate locations of `zero-manifest.json` inside a plugin directory.
pub fn manifest_candidates(plugin_dir: &Path) -> Vec<PathBuf> {
    vec![
        plugin_dir.join(ZERO_MANIFEST_FILE),
        plugin_dir.join(CLAUDE_PLUGIN_DIR).join(ZERO_MANIFEST_FILE),
    ]
}

/// Candidate locations of `plugin.json` inside a plugin directory.
pub fn plugin_json_candidates(plugin_dir: &Path) -> Vec<PathBuf> {
    vec![plugin_dir.join(PLUGIN_FILE), plugin_dir.join(CLAUDE_PLUGIN_DIR).join(PLUGIN_FILE)]
}

fn find_existing_file(candidates: &[PathBuf]) -> Option<PathBuf> {
    candidates.iter().find(|path| path.is_file()).cloned()
}

/// Resolves the manifest path, or reports a `NotFound` read error.
pub fn resolve_manifest_path(plugin_dir: &Path) -> Result<PathBuf, EntityError> {
    let candidates = manifest_candidates(plugin_dir);
    if let Some(path) = find_existing_file(&candidates) {
        return Ok(path);
    }
    Err(EntityError::Read {
        path: candidates[0].clone(),
        source: io::Error::new(
            io::ErrorKind::NotFound,
            format!("{} not found in {}", ZERO_MANIFEST_FILE, plugin_dir.display()),
        ),
    })
}

/// Resolves the plugin metadata path, or reports a `NotFound` read error.
pub fn resolve_plugin_json_path(plugin_dir: &Path) -> Result<PathBuf, EntityError> {
    let candidates = plugin_json_candidates(plugin_dir);
    if let Some(path) = find_existing_file(&candidates) {
        return Ok(path);
    }
    Err(EntityError::Read {
        path: candidates[0].clone(),
        source: io::Error::new(
            io::ErrorKind::NotFound,
            format!("{} not found in {}", PLUGIN_FILE, plugin_dir.display()),
        ),
    })
}

/// Reads `zero-manifest.json` from a plugin directory.
pub fn read_zero_manifest(plugin_dir: &Path) -> Result<Value, EntityError> {
    let path = resolve_manifest_path(plugin_dir)?;
    read_json_object(&path)
}

/// Reads `plugin.json` from a plugin directory.
pub fn read_plugin_json(plugin_dir: &Path) -> Result<Value, EntityError> {
    let path = resolve_plugin_json_path(plugin_dir)?;
    read_json_object(&path)
}

/// Reads the manifest if it exists and parses; malformed evidence yields
/// `None` here (the strict loader reports the error).
fn read_manifest_if_present(plugin_dir: &Path) -> Option<Value> {
    let path = find_existing_file(&manifest_candidates(plugin_dir))?;
    read_json_object(&path).ok()
}

/// Pure identity extraction. `zero-manifest.json` is the primary authority;
/// `plugin.json` is a fallback evidence source only.
pub fn identity_from_values(
    plugin: &Value,
    manifest: &Value,
    source_path: &Path,
) -> Result<EntityIdentity, EntityError> {
    let name = manifest
        .get("entity_name")
        .and_then(Value::as_str)
        .or_else(|| manifest.get("name").and_then(Value::as_str))
        .or_else(|| {
            manifest.get("entity").and_then(|entity| entity.get("name")).and_then(Value::as_str)
        })
        .or_else(|| plugin.get("name").and_then(Value::as_str))
        .map(str::trim)
        .filter(|name| !name.is_empty())
        .ok_or(EntityError::MissingPluginName)?;

    let version = manifest
        .get("version")
        .and_then(Value::as_str)
        .or_else(|| manifest.get("entity_version").and_then(Value::as_str))
        .or_else(|| plugin.get("version").and_then(Value::as_str))
        .map(str::trim)
        .filter(|version| !version.is_empty())
        .map(str::to_owned);

    let entity_id = manifest
        .get("entity_id")
        .and_then(Value::as_str)
        .or_else(|| manifest.get("id").and_then(Value::as_str))
        .or_else(|| plugin.get("entity_id").and_then(Value::as_str))
        .or_else(|| plugin.get("id").and_then(Value::as_str))
        .map(str::trim)
        .filter(|id| !id.is_empty())
        .map(str::to_owned);

    Ok(EntityIdentity {
        name: name.to_owned(),
        version,
        entity_id,
        source: source_path.to_path_buf(),
    })
}

/// Pure root-state extraction. The manifest is the authority; when no explicit
/// root key exists the whole manifest object is the root state.
pub fn root_state_from_manifest(manifest: &Value, manifest_path: &Path) -> EntityRootState {
    let value = ["root_state", "root", "state", "entity"]
        .iter()
        .find_map(|key| manifest.get(*key))
        .cloned()
        .unwrap_or_else(|| manifest.clone());

    EntityRootState { value, source: manifest_path.to_path_buf() }
}

/// Loads identity and root state from a plugin directory.
pub fn load_entity_state(plugin_dir: &Path) -> Result<EntitySnapshot, EntityError> {
    load_entity_state_at(plugin_dir, SystemTime::now())
}

/// Deterministic variant with an explicit observation timestamp.
pub fn load_entity_state_at(
    plugin_dir: &Path,
    observed_at: SystemTime,
) -> Result<EntitySnapshot, EntityError> {
    let manifest_path = resolve_manifest_path(plugin_dir)?;
    let plugin_path = resolve_plugin_json_path(plugin_dir)?;

    let manifest = read_json_object(&manifest_path)?;
    let plugin = read_json_object(&plugin_path)?;

    let identity = identity_from_values(&plugin, &manifest, &manifest_path)?;
    let root = root_state_from_manifest(&manifest, &manifest_path);

    Ok(EntitySnapshot { identity, root, observed_at })
}

/// The bundled plugin directory, resolved relative to the crate root.
pub fn bundled_plugin_dir() -> PathBuf {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    find_bundled_plugin(root)
}

/// Searches upwards from `start` for the bundled plugin payload.
fn find_bundled_plugin(start: &Path) -> PathBuf {
    let mut current = Some(start);
    while let Some(dir) = current {
        let candidate = dir.join(BUNDLED_PLUGIN_RELATIVE);
        if candidate.join(ZERO_MANIFEST_FILE).is_file() {
            return candidate;
        }
        current = dir.parent();
    }
    start.join(BUNDLED_PLUGIN_RELATIVE)
}

/// Pure plugin-directory resolution (`f3_paths` precedence).
pub fn resolve_plugin_dir(env: &EnvSnapshot, bundled: &Path) -> PathBuf {
    env.get(PLUGIN_DIR_ENV)
        .map(PathBuf::from)
        .or_else(|| env.get(FRANKENSTEIN3_PLUGIN_DIR_ENV).map(PathBuf::from))
        .unwrap_or_else(|| bundled.to_path_buf())
}

/// Data directory declared by the manifest, if any.
pub fn manifest_data_dir(manifest: Option<&Value>) -> Option<&str> {
    let manifest = manifest?;
    ["data_dir", "plugin_data_dir", "state_dir"]
        .iter()
        .find_map(|key| manifest.get(*key).and_then(Value::as_str))
        .map(str::trim)
        .filter(|value| !value.is_empty())
}

/// Pure plugin-data-directory resolution (`f3_paths` precedence).
pub fn resolve_data_dir(env: &EnvSnapshot, plugin_dir: &Path, manifest: Option<&Value>) -> PathBuf {
    if let Some(value) = env.get(PLUGIN_DATA_DIR_ENV) {
        return PathBuf::from(value);
    }
    if let Some(value) = env.get(FRANKENSTEIN3_DATA_DIR_ENV) {
        return PathBuf::from(value);
    }
    if let Some(value) = env.get(FRANKENSTEIN3_PLUGIN_DATA_DIR_ENV) {
        return PathBuf::from(value);
    }
    if let Some(declared) = manifest_data_dir(manifest) {
        let candidate = PathBuf::from(declared);
        return if candidate.is_absolute() { candidate } else { plugin_dir.join(candidate) };
    }
    if let Some(xdg) = env.get(XDG_DATA_HOME_ENV) {
        return PathBuf::from(xdg).join(PLUGIN_DATA_DIR_NAME);
    }
    if let Some(home) = env.get(HOME_ENV) {
        return PathBuf::from(home).join(".local").join("share").join(PLUGIN_DATA_DIR_NAME);
    }
    plugin_dir.to_path_buf()
}

/// Pure resolution of the complete plugin binding.
pub fn resolve_plugin_paths(env: &EnvSnapshot, bundled: &Path) -> PluginPaths {
    let plugin_dir = resolve_plugin_dir(env, bundled);
    let manifest = read_manifest_if_present(&plugin_dir);
    let data_dir = resolve_data_dir(env, &plugin_dir, manifest.as_ref());
    PluginPaths { plugin_dir, data_dir }
}

/// Plugin directory from the environment, falling back to the bundled plugin.
pub fn plugin_dir_from_env() -> PathBuf {
    resolve_plugin_dir(&EnvSnapshot::from_process(), &bundled_plugin_dir())
}

/// Resolved plugin binding from the current process environment.
pub fn plugin_paths_from_env() -> PluginPaths {
    resolve_plugin_paths(&EnvSnapshot::from_process(), &bundled_plugin_dir())
}

/// The canonical `unified.db` path. Retina MUST consume this function so both
/// organs address exactly one database file.
pub fn unified_db_path() -> PathBuf {
    plugin_paths_from_env().unified_db_path()
}

/// The canonical `unified.db` path for an already resolved plugin binding.
pub fn unified_db_path_for(paths: &PluginPaths) -> PathBuf {
    paths.unified_db_path()
}

/// Retina-side entry point: delegates to the canonical resolver.
pub fn retina_unified_db_path() -> PathBuf {
    unified_db_path()
}

/// Loads the bundled plugin state.
pub fn load_bundled_entity_state() -> Result<EntitySnapshot, EntityError> {
    load_entity_state(&plugin_dir_from_env())
}

/// Measures `EntityOS` health. OK is reported only when the plugin state was
/// actually read and parsed; every failure stays UNKNOWN with a cause.
pub fn entity_health_at(paths: &PluginPaths, now: SystemTime) -> EntityHealth {
    let db_path = paths.unified_db_path();
    let db_present = db_path.is_file();

    match load_entity_state_at(&paths.plugin_dir, now) {
        Ok(snapshot) => EntityHealth {
            class: EntityHealthClass::MeasuredOk,
            detail: None,
            observed_at: now,
            db_path,
            db_present,
            identity_name: Some(snapshot.identity.name),
        },
        Err(error) => EntityHealth {
            class: EntityHealthClass::Unknown,
            detail: Some(error.to_string()),
            observed_at: now,
            db_path,
            db_present,
            identity_name: None,
        },
    }
}

/// Measures `EntityOS` health from the current process environment.
pub fn entity_health() -> EntityHealth {
    entity_health_at(&plugin_paths_from_env(), SystemTime::now())
}

/// Component status for the entity, freshness-gated against `now`.
pub fn entity_component_status(snapshot: &EntitySnapshot, now: SystemTime) -> ComponentStatus {
    snapshot.status().reevaluated(now)
}

/// Component status derived from a measured health record.
pub fn entity_health_status(health: &EntityHealth, now: SystemTime) -> ComponentStatus {
    health.status(now)
}

/// Formats the shared status line using a measured entity snapshot.
pub fn format_entity_status_line(
    grid: &GridHealth,
    retina: &ComponentStatus,
    entity: &ComponentStatus,
    omnipool: &ComponentStatus,
    now: SystemTime,
) -> String {
    format_status_line_at(now, &grid.status, retina, entity, omnipool)
}

/// Explicit epistemic-class variant of the shared status line.
pub fn format_entity_status_line_labeled(
    grid: &GridHealth,
    retina: &ComponentStatus,
    entity: &ComponentStatus,
    omnipool: &ComponentStatus,
    now: SystemTime,
) -> String {
    format_status_line_labeled_at(now, &grid.status, retina, entity, omnipool)
}

/// Convenience wrapper that derives the entity component from a snapshot.
pub fn status_line_from_snapshot(
    grid: &GridHealth,
    retina: &ComponentStatus,
    snapshot: &EntitySnapshot,
    omnipool: &ComponentStatus,
    now: SystemTime,
) -> String {
    let entity = entity_component_status(snapshot, now);
    format_entity_status_line(grid, retina, &entity, omnipool, now)
}

/// Convenience wrapper that derives the entity component from measured health.
pub fn status_line_from_health(
    grid: &GridHealth,
    retina: &ComponentStatus,
    health: &EntityHealth,
    omnipool: &ComponentStatus,
    now: SystemTime,
) -> String {
    let entity = entity_health_status(health, now);
    format_entity_status_line(grid, retina, &entity, omnipool, now)
}
