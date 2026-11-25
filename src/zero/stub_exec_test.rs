// SPDX-License-Identifier: Apache-2.0

#![cfg(unix)]

//! Shared helper for tests that write a shell script and execute it directly.
//!
//! The suite runs many tests on parallel threads and several of them spawn child processes. A
//! `fork` in one thread transiently inherits the writable descriptor another thread still holds
//! on its freshly written script, and an `execve` of that path then fails with `ETXTBSY` until
//! the forked child has exec'd itself. The helper therefore writes the script and waits until
//! the kernel accepts an exec of it. Once the stale descriptors are gone nothing writes the file
//! again, so the script stays executable for the rest of the test.

use std::path::Path;
use std::process::{Command, Stdio};
use std::time::Duration;

use std::os::unix::fs::PermissionsExt;

const PROBE_ENV: &str = "ZERO_STUB_PROBE";
const PROBE_GUARD: &str = "[ -n \"$ZERO_STUB_PROBE\" ] && exit 0\n";
const PROBE_ATTEMPTS: u32 = 1000;
const PROBE_PAUSE: Duration = Duration::from_millis(5);

/// Write `script` (which must start with a shebang line) to `path`, mark it executable and block
/// until it can be executed. The probe run exits before the script body, so stubs observe no
/// extra invocation.
pub(super) fn write_executable_stub(path: &Path, script: &str) {
    let (shebang, rest) = script.split_once('\n').expect("stub script needs a shebang line");
    assert!(shebang.starts_with("#!"), "stub script must start with a shebang");
    std::fs::write(path, format!("{shebang}\n{PROBE_GUARD}{rest}")).expect("write stub");
    let mut perms = std::fs::metadata(path).expect("stat stub").permissions();
    perms.set_mode(0o755);
    std::fs::set_permissions(path, perms).expect("chmod stub");
    wait_until_executable(path);
}

fn wait_until_executable(path: &Path) {
    for _ in 0..PROBE_ATTEMPTS {
        let probe = Command::new(path)
            .env(PROBE_ENV, "1")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
        match probe {
            Err(err) if err.kind() == std::io::ErrorKind::ExecutableFileBusy => {
                std::thread::sleep(PROBE_PAUSE);
            }
            _ => return,
        }
    }
    panic!("stub {} stayed busy for exec", path.display());
}
