//! Retina-side adapter for the canonical EntityOS database path.
//!
//! The retina organ must not re-derive `unified.db` on its own: it consumes
//! this adapter, which delegates to the canonical resolver in
//! `crate::zero::entity`. Both organs therefore address one database file.
//!
//! GRF: `R_t` = resolved plugin binding, `E_t` = environment snapshot,
//! `F` = `unified_db_path` (pure delegation), `M` = { plugin_dir, data_dir }.

use std::path::PathBuf;

use crate::zero::entity::PluginPaths;

/// Canonical `unified.db` path used by the retina organ.
pub fn unified_db_path() -> PathBuf {
    crate::zero::entity::unified_db_path()
}

/// Canonical `unified.db` path for an already resolved plugin binding.
pub fn unified_db_path_for(paths: &PluginPaths) -> PathBuf {
    crate::zero::entity::unified_db_path_for(paths)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::zero::entity::{
        resolve_plugin_paths, EnvSnapshot, PLUGIN_DATA_DIR_ENV, PLUGIN_DIR_ENV, UNIFIED_DB_FILE,
    };

    #[test]
    fn retina_db_path_is_the_entity_db_path() {
        let env = EnvSnapshot::from_pairs([
            (PLUGIN_DIR_ENV, "plugin".to_owned()),
            (PLUGIN_DATA_DIR_ENV, "data".to_owned()),
        ]);
        let paths = resolve_plugin_paths(&env, &PathBuf::from("bundled"));

        assert_eq!(unified_db_path_for(&paths), paths.unified_db_path());
        assert_eq!(
            paths.unified_db_path().file_name().and_then(|n| n.to_str()),
            Some(UNIFIED_DB_FILE)
        );
    }
}
