#!/usr/bin/env python3
"""claude-rs / claude-code-rust -> machine-god, mechanical pass over TRACKED text files of a worktree.
usage: rename_mg.py <worktree> [--dry]
visible name everywhere = machine-god; the native binary FILE name in installers/packaging = machine-god-core
(the first-run launcher keeps the name machine-god). Lines mentioning srothgan (upstream credit) are never touched."""
import re, subprocess, sys
from pathlib import Path

wt = Path(sys.argv[1]); dry = "--dry" in sys.argv
SKIP = re.compile(r"^(LICENSE|NOTICE\.md|CHANGELOG\.md|third-party/|recordings/|Cargo\.lock|.*\.(png|jpg|gif|woff2?|ico|zip|gz|wasm|svg|cast))")
NATIVE = re.compile(r"^(scripts/(install|npm|runtime|shared)/|\.github/|bin/|Cargo\.toml$|package\.json$|scripts/[^/]+$)")
FILE_MOVES = {"bin/claude-rs.js": "bin/machine-god.js"}
files = subprocess.run(["git", "-C", str(wt), "ls-files"], capture_output=True, text=True, check=True).stdout.splitlines()
changed = 0; moved = 0

def conv(rel, line):
    if "srothgan" in line: return line
    o = line
    line = line.replace("CLAUDE_RS_", "MACHINE_GOD_").replace("ClaudeRs", "MachineGod")
    line = line.replace("claude_rs", "machine_god").replace("claude_code_rust", "machine_god")
    line = line.replace("Claude Code Rust", "Machine God").replace("claude-code-rust", "machine-god")
    line = line.replace("claude-rs-bridge-bun", "machine-god-bridge-bun").replace("CARGO_BIN_EXE_claude-rs", "CARGO_BIN_EXE_machine-god-core")
    line = line.replace('"claude-rs": "bin/claude-rs.js"', '"machine-god": "bin/machine-god.js"').replace("bin/claude-rs.js", "bin/machine-god.js")
    line = line.replace("claude-rs.js", "machine-god.js")
    if NATIVE.match(rel):
        line = re.sub(r"claude-rs(?![A-Za-z0-9_-])", "machine-god-core", line)
    line = line.replace("claude-rs", "machine-god")
    return line

for rel in files:
    if SKIP.match(rel): continue
    p = wt / rel
    try: txt = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError): continue
    new = "".join(conv(rel, l) for l in txt.splitlines(keepends=True))
    if new != txt:
        changed += 1
        if not dry: p.write_text(new, encoding="utf-8")
    if rel in FILE_MOVES and not dry:
        subprocess.run(["git", "-C", str(wt), "mv", rel, FILE_MOVES[rel]], check=True); moved += 1
print(f"files changed: {changed}, moved: {moved}{' (dry)' if dry else ''}")
