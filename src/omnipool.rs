// SPDX-License-Identifier: Apache-2.0

//! Omnipool (API-OMNI-BRAIN) built into machine-god: every bridge turn runs on the free pool.
//!
//! On bridge start: find Omnipool's data dir, start its daemon if the port is closed, derive this
//! app's access key locally (HMAC-SHA256 of the app name with Omnipool's own `app_key`, identical to
//! `harness_key` in omnipool/server.py) and hand base URL + key to the bridge process env only.
//! No key is typed, stored, printed or logged by machine-god. Off: `MACHINE_GOD_OMNIPOOL=0`.
//! `/api` opens Omnipool's web app in a browser the user picks in chat.

use sha2::{Digest, Sha256};
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::OnceLock;
use std::time::{Duration, Instant};

pub const APP: &str = "machine_god";
pub const DEFAULT_PORT: u16 = 8799;
const BINARY: &str = if cfg!(windows) { "API-OMNI-BRAIN.exe" } else { "API-OMNI-BRAIN" };

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Link {
    pub base_url: String,
    pub key: String,
}

#[must_use]
pub fn hmac_sha256(key: &[u8], msg: &[u8]) -> [u8; 32] {
    let mut k = [0u8; 64];
    if key.len() > 64 {
        k[..32].copy_from_slice(&Sha256::digest(key));
    } else {
        k[..key.len()].copy_from_slice(key);
    }
    let pad = |b: u8| k.iter().map(|x| x ^ b).collect::<Vec<u8>>();
    let inner = Sha256::new().chain_update(pad(0x36)).chain_update(msg).finalize();
    Sha256::new().chain_update(pad(0x5c)).chain_update(inner).finalize().into()
}

/// Same derivation as Omnipool's `harness_key(app)`: `op-<app>-<first 24 hex of HMAC>`.
#[must_use]
pub fn harness_key(app_key: &str, app: &str) -> String {
    let hex: String = hmac_sha256(app_key.as_bytes(), app.as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect();
    format!("op-{app}-{}", &hex[..24])
}

fn data_dirs() -> Vec<PathBuf> {
    let mut v: Vec<PathBuf> =
        std::env::var_os("OMNIPOOL_HOME").map(PathBuf::from).into_iter().collect();
    v.extend(dirs::data_dir().map(|d| d.join("omnipool")));
    v.extend(dirs::home_dir().map(|h| h.join(".local").join("share").join("omnipool")));
    v
}

fn port_open(port: u16) -> bool {
    TcpStream::connect_timeout(
        &SocketAddr::from(([127, 0, 0, 1], port)),
        Duration::from_millis(300),
    )
    .is_ok()
}

/// The native binary if there is one (Linux build), else the universal `Omnipool.pyz` via Python
/// (macOS, Windows, other Linux): next to machine-god, in `$OMNIPOOL_BIN`, or in Omnipool's data dir.
fn daemon_command(dir: &Path) -> Option<Command> {
    let beside = |f: &str| std::env::current_exe().ok().and_then(|e| e.parent().map(|p| p.join(f)));
    let found = |cands: [Option<PathBuf>; 3]| cands.into_iter().flatten().find(|p| p.is_file());
    if let Some(bin) = found([
        std::env::var_os("OMNIPOOL_BIN").map(PathBuf::from),
        beside(BINARY),
        Some(dir.join("bin").join(BINARY)),
    ]) {
        let mut c = Command::new(bin);
        c.arg("--daemon");
        return Some(c);
    }
    let pyz = found([
        beside("Omnipool.pyz"),
        Some(dir.join("bin").join("Omnipool.pyz")),
        dirs::home_dir().map(|h| h.join("omnipool").join("dist").join("Omnipool.pyz")),
    ])?;
    let py = ["python3", "python", "py"].into_iter().find(|p| which::which(p).is_ok())?;
    let mut c = Command::new(py);
    c.arg(pyz).arg("--daemon");
    Some(c)
}

/// Reads Omnipool's settings, starts the daemon if needed (waits up to 15 s), derives the key.
fn connect() -> Option<Link> {
    if std::env::var("MACHINE_GOD_OMNIPOOL").is_ok_and(|v| v == "0") {
        return None;
    }
    let (dir, raw) = data_dirs()
        .into_iter()
        .find_map(|d| std::fs::read_to_string(d.join("settings.json")).ok().map(|r| (d, r)))?;
    let s: serde_json::Value = serde_json::from_str(&raw).ok()?;
    let app_key = s.get("app_key")?.as_str().filter(|k| !k.is_empty())?;
    let port = s
        .get("port")
        .and_then(serde_json::Value::as_u64)
        .and_then(|p| u16::try_from(p).ok())
        .unwrap_or(DEFAULT_PORT);
    if !port_open(port) {
        daemon_command(&dir)?
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .ok()?;
        let t0 = Instant::now();
        while !port_open(port) {
            if t0.elapsed() > Duration::from_secs(15) {
                return None;
            }
            std::thread::sleep(Duration::from_millis(250));
        }
    }
    Some(Link { base_url: format!("http://127.0.0.1:{port}"), key: harness_key(app_key, APP) })
}

/// Cached for the process lifetime; `None` = Omnipool not installed, switched off or not starting.
pub fn link() -> Option<&'static Link> {
    static L: OnceLock<Option<Link>> = OnceLock::new();
    L.get_or_init(connect).as_ref()
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Browser {
    pub name: String,
    launch: Vec<String>,
}

/// Installed browsers on this OS; the first entry is always the system default.
#[must_use]
pub fn browsers() -> Vec<Browser> {
    let b = |name: &str, launch: &[&str]| Browser {
        name: name.into(),
        launch: launch.iter().map(|s| (*s).to_string()).collect(),
    };
    let mut v = Vec::new();
    if cfg!(target_os = "macos") {
        v.push(b("System default", &["open"]));
        for app in [
            "Safari",
            "Google Chrome",
            "Firefox",
            "Brave Browser",
            "Microsoft Edge",
            "Arc",
            "Vivaldi",
            "Chromium",
            "Opera",
        ] {
            if Path::new("/Applications").join(format!("{app}.app")).exists() {
                v.push(b(app, &["open", "-a", app]));
            }
        }
    } else if cfg!(windows) {
        v.push(b("System default", &["cmd", "/C", "start", ""]));
        let roots: Vec<PathBuf> = ["ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"]
            .iter()
            .filter_map(std::env::var_os)
            .map(PathBuf::from)
            .collect();
        for (name, rel) in [
            ("Microsoft Edge", "Microsoft\\Edge\\Application\\msedge.exe"),
            ("Google Chrome", "Google\\Chrome\\Application\\chrome.exe"),
            ("Firefox", "Mozilla Firefox\\firefox.exe"),
            ("Brave", "BraveSoftware\\Brave-Browser\\Application\\brave.exe"),
            ("Vivaldi", "Vivaldi\\Application\\vivaldi.exe"),
        ] {
            if let Some(p) = roots.iter().map(|r| r.join(rel)).find(|p| p.is_file()) {
                v.push(Browser {
                    name: name.into(),
                    launch: vec![p.to_string_lossy().into_owned()],
                });
            }
        }
    } else {
        v.push(b("System default", &["xdg-open"]));
        for (name, bin) in [
            ("Firefox", "firefox"),
            ("Google Chrome", "google-chrome"),
            ("Chromium", "chromium"),
            ("Chromium", "chromium-browser"),
            ("Brave", "brave-browser"),
            ("Microsoft Edge", "microsoft-edge"),
            ("Vivaldi", "vivaldi"),
            ("Opera", "opera"),
        ] {
            if !v.iter().any(|x: &Browser| x.name == name) && which::which(bin).is_ok() {
                v.push(b(name, &[bin]));
            }
        }
    }
    v
}

/// Opens `url` with `browser`, detached; the URL is the only extra argument.
pub fn open(browser: &Browser, url: &str) -> std::io::Result<()> {
    let (exe, args) = browser
        .launch
        .split_first()
        .ok_or_else(|| std::io::Error::other("empty launch command"))?;
    Command::new(exe)
        .args(args)
        .arg(url)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map(drop)
}

/// Web app URL: the running Omnipool, else the default port (opening shows the honest error).
#[must_use]
pub fn web_url() -> String {
    link()
        .map_or_else(|| format!("http://127.0.0.1:{DEFAULT_PORT}/"), |l| format!("{}/", l.base_url))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hmac_matches_rfc4231_case_2() {
        let h = hmac_sha256(b"Jefe", b"what do ya want for nothing?");
        let hex: String = h.iter().map(|b| format!("{b:02x}")).collect();
        assert_eq!(hex, "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843");
    }

    #[test]
    fn harness_key_has_omnipool_shape() {
        let k = harness_key("secret", APP);
        assert!(k.starts_with("op-machine_god-"));
        assert_eq!(k.len(), "op-machine_god-".len() + 24);
        // value computed by Omnipool's own Python derivation (hmac.new(b"secret", b"machine_god", sha256))
        assert_eq!(k, "op-machine_god-65e1249dc8d5254faa1ccfc4");
    }

    #[test]
    fn first_browser_is_system_default() {
        assert_eq!(browsers()[0].name, "System default");
    }
}
