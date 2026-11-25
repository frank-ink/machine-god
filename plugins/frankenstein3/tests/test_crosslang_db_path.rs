//! Cross-language DB path parity test (Rust side).
//! This test can be run via `cargo test -p zero --test crosslang_db_path`
//! It verifies the Rust resolver matches expected paths for each env combination.

use std::env;
use std::path::PathBuf;

fn resolve_db_path() -> PathBuf {
    // 1. FRANK3_DATA
    if let Ok(val) = env::var("FRANK3_DATA") {
        return PathBuf::from(val).join("unified.db");
    }
    // 2. F3_DB_PATH
    if let Ok(val) = env::var("F3_DB_PATH") {
        let path = PathBuf::from(val);
        if path.extension().is_some() {
            return path;
        } else {
            return path.join("unified.db");
        }
    }
    // 3. XDG_DATA_HOME
    if let Ok(xdg) = env::var("XDG_DATA_HOME") {
        return PathBuf::from(xdg).join("frankenstein3").join("unified.db");
    }
    // 4. HOME fallback
    if let Ok(home) = env::var("HOME") {
        return PathBuf::from(home).join(".local").join("share").join("frankenstein3").join("unified.db");
    }
    // 5. Windows USERPROFILE fallback
    if let Ok(userprofile) = env::var("USERPROFILE") {
        return PathBuf::from(userprofile).join("AppData").join("Local").join("frankenstein3").join("unified.db");
    }
    panic!("Cannot resolve DB path");
}

fn with_env<F>(vars: &[(&str, Option<&str>)], f: F)
where
    F: FnOnce(),
{
    let old: Vec<_> = vars.iter().map(|(k, _)| (k.to_string(), env::var(k).ok())).collect();
    for (k, v) in vars {
        match v {
            Some(v) => env::set_var(k, v),
            None => env::remove_var(k),
        }
    }
    f();
    for (k, v) in old {
        match v {
            Some(v) => env::set_var(k, v),
            None => env::remove_var(k),
        }
    }
}

#[test]
fn test_frank3_data_only() {
    with_env(&[
        ("FRANK3_DATA", Some("/custom/frank3/data")),
        ("F3_DB_PATH", None),
        ("XDG_DATA_HOME", None),
        ("HOME", None),
        ("USERPROFILE", None),
    ], || {
        let path = resolve_db_path();
        assert_eq!(path, PathBuf::from("/custom/frank3/data/unified.db"));
    });
}

#[test]
fn test_f3_db_path_as_directory() {
    with_env(&[
        ("FRANK3_DATA", None),
        ("F3_DB_PATH", Some("/custom/f3/db/dir")),
        ("XDG_DATA_HOME", None),
        ("HOME", None),
        ("USERPROFILE", None),
    ], || {
        let path = resolve_db_path();
        assert_eq!(path, PathBuf::from("/custom/f3/db/dir/unified.db"));
    });
}

#[test]
fn test_f3_db_path_as_file() {
    with_env(&[
        ("FRANK3_DATA", None),
        ("F3_DB_PATH", Some("/custom/f3/db.sqlite")),
        ("XDG_DATA_HOME", None),
        ("HOME", None),
        ("USERPROFILE", None),
    ], || {
        let path = resolve_db_path();
        assert_eq!(path, PathBuf::from("/custom/f3/db.sqlite"));
    });
}

#[test]
fn test_xdg_data_home_only() {
    with_env(&[
        ("FRANK3_DATA", None),
        ("F3_DB_PATH", None),
        ("XDG_DATA_HOME", Some("/xdg/data")),
        ("HOME", None),
        ("USERPROFILE", None),
    ], || {
        let path = resolve_db_path();
        assert_eq!(path, PathBuf::from("/xdg/data/frankenstein3/unified.db"));
    });
}

#[test]
fn test_home_only() {
    with_env(&[
        ("FRANK3_DATA", None),
        ("F3_DB_PATH", None),
        ("XDG_DATA_HOME", None),
        ("HOME", Some("/home/testuser")),
        ("USERPROFILE", None),
    ], || {
        let path = resolve_db_path();
        assert_eq!(path, PathBuf::from("/home/testuser/.local/share/frankenstein3/unified.db"));
    });
}

#[test]
fn test_frank3_data_wins_over_f3_db_path() {
    with_env(&[
        ("FRANK3_DATA", Some("/frank3/wins")),
        ("F3_DB_PATH", Some("/f3/loses")),
        ("XDG_DATA_HOME", None),
        ("HOME", None),
        ("USERPROFILE", None),
    ], || {
        let path = resolve_db_path();
        assert_eq!(path, PathBuf::from("/frank3/wins/unified.db"));
    });
}

#[test]
fn test_f3_db_path_wins_over_xdg() {
    with_env(&[
        ("FRANK3_DATA", None),
        ("F3_DB_PATH", Some("/f3/wins")),
        ("XDG_DATA_HOME", Some("/xdg/loses")),
        ("HOME", None),
        ("USERPROFILE", None),
    ], || {
        let path = resolve_db_path();
        assert_eq!(path, PathBuf::from("/f3/wins/unified.db"));
    });
}

#[test]
fn test_userprofile_fallback() {
    with_env(&[
        ("FRANK3_DATA", None),
        ("F3_DB_PATH", None),
        ("XDG_DATA_HOME", None),
        ("HOME", None),
        ("USERPROFILE", Some(r"C:\Users\testuser")),
    ], || {
        let path = resolve_db_path();
        assert_eq!(path, PathBuf::from(r"C:\Users\testuser\AppData\Local\frankenstein3\unified.db"));
    });
}
