#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Portability test for Frankenstein 3 plugin.

Scans in-scope plugin files for:
  - Hard-coded /home/<user> paths
  - Hard-coded /Users/<user> paths (macOS)
  - Hard-coded /mnt/, /opt/, /media/ paths (Linux mount points)
  - Hard-coded C:/, D:/ paths (Windows)
  - Machine names / hostnames
  - Absolute host paths that would break portability

Byte-compiles in-scope Python scripts to verify syntax.

In-scope files (relative to plugin root):
  - f3_pfade.py
  - install.sh
  - README.md
  - scripts/status.py
  - scripts/digest.py
  - scripts/reentry.py
  - scripts/star/frank_profile.py

Read-only files (NOT scanned, NOT modified):
  - scripts/star/stern*.py
  - scripts/star/f3_pfade.py
  - .claude-plugin/
  - hooks/hooks.json
"""
from __future__ import annotations

import os
import py_compile
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

PLUGIN_ROOT = Path(__file__).resolve().parents[1]

# Files to scan for hard-coded paths (relative to plugin root)
SCAN_FILES = [
    "f3_pfade.py",
    "install.sh",
    "README.md",
    "scripts/status.py",
    "scripts/digest.py",
    "scripts/reentry.py",
    "scripts/star/frank_profile.py",
]

# Python files to byte-compile (subset of SCAN_FILES)
PYTHON_FILES = [
    "f3_pfade.py",
    "scripts/status.py",
    "scripts/digest.py",
    "scripts/reentry.py",
    "scripts/star/frank_profile.py",
]

# Patterns that indicate non-portable hard-coded paths
# /home/<username>/... or /Users/<username>/...
HOME_PATH_PATTERN = re.compile(r"/home/[a-zA-Z0-9_.-]+")
USERS_PATH_PATTERN = re.compile(r"/Users/[a-zA-Z0-9_.-]+")

# Common machine/host names that should not be hard-coded
MACHINE_NAME_PATTERNS = [
    re.compile(r"machine-a", re.IGNORECASE),
    re.compile(r"localhost", re.IGNORECASE),
    re.compile(r"127\.0\.0\.1"),
    re.compile(r"::1"),
]

# Absolute path pattern - catches non-portable absolute paths
# Allows: ~/, $HOME, ${HOME}, %USERPROFILE%, $XDG_DATA_HOME, ${XDG_DATA_HOME},
# $FRANK3_DATA, ${FRANK3_DATA}, $CLAUDE_PLUGIN_DATA, ${CLAUDE_PLUGIN_DATA},
# $F3_DB_PATH, ${F3_DB_PATH}, os.environ[...], Path.home(), expanduser, expandvars
# Catches: /home/user/, /Users/user/, /mnt/, /opt/, /media/, /var/, /etc/, /root/,
# C:/, D:/, etc. but NOT /usr/ (legitimate system paths like /usr/bin, /usr/lib)
ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?<![$~{%])"  # Not preceded by variable/reference chars
    r"(?:"          # Non-capturing group for alternatives
    r"/home/[a-zA-Z0-9_.-]+"  # /home/user/...
    r"|/Users/[a-zA-Z0-9_.-]+"  # /Users/user/...
    r"|/mnt/[a-zA-Z0-9_.-/]+"   # /mnt/...
    r"|/opt/[a-zA-Z0-9_.-/]+"   # /opt/...
    r"|/media/[a-zA-Z0-9_.-/]+" # /media/...
    r"|/var/[a-zA-Z0-9_.-/]+"   # /var/...
    r"|/etc/[a-zA-Z0-9_.-/]+"   # /etc/...
    r"|/root/[a-zA-Z0-9_.-/]+"  # /root/...
    r"|[A-Za-z]:[/\\\\]"        # C:/, C:\, D:/, etc.
    r")"
)

# Allowed portable patterns (these are OK)
ALLOWED_PATTERNS = [
    re.compile(r"\$HOME"),
    re.compile(r"\$\{HOME\}"),
    re.compile(r"\$XDG_DATA_HOME"),
    re.compile(r"\$\{XDG_DATA_HOME\}"),
    re.compile(r"\$FRANK3_DATA"),
    re.compile(r"\$\{FRANK3_DATA\}"),
    re.compile(r"\$CLAUDE_PLUGIN_DATA"),
    re.compile(r"\$\{CLAUDE_PLUGIN_DATA\}"),
    re.compile(r"\$F3_DB_PATH"),
    re.compile(r"\$\{F3_DB_PATH\}"),
    re.compile(r"\$FRANKENSTEIN3_ROOT"),
    re.compile(r"\$\{FRANKENSTEIN3_ROOT\}"),
    re.compile(r"%USERPROFILE%"),
    re.compile(r"~/"),  # tilde expansion
    re.compile(r"^~$"),
    re.compile(r"os\.environ\[[\"']HOME[\"']\]"),
    re.compile(r"os\.environ\[[\"']USERPROFILE[\"']\]"),
    re.compile(r"os\.environ\.get\([\"']HOME[\"']\)"),
    re.compile(r"os\.environ\.get\([\"']USERPROFILE[\"']\)"),
    re.compile(r"Path\.home\(\)"),
    re.compile(r"pathlib\.Path\.home\(\)"),
    re.compile(r"shutil\.which\("),
    re.compile(r"expanduser"),
    re.compile(r"expandvars"),
]


def is_allowed_match(line: str, match: re.Match) -> bool:
    """Check if a matched absolute path is actually an allowed portable pattern."""
    # Check if the matched text is part of an allowed pattern in the line
    for pattern in ALLOWED_PATTERNS:
        if pattern.search(line):
            allowed_match = pattern.search(line)
            if allowed_match and allowed_match.start() <= match.start() < allowed_match.end():
                return True
    return False


def scan_file_for_issues(filepath: Path) -> List[Tuple[int, str, str]]:
    """Scan a file for non-portable patterns. Returns list of (line_num, issue_type, line)."""
    issues = []
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        issues.append((0, f"READ_ERROR: {e}", ""))
        return issues

    for i, line in enumerate(content.splitlines(), 1):
        # Check for /home/<user> patterns
        for match in HOME_PATH_PATTERN.finditer(line):
            if not is_allowed_match(line, match):
                issues.append((i, "HOME_PATH", line.strip()))

        # Check for /Users/<user> patterns
        for match in USERS_PATH_PATTERN.finditer(line):
            if not is_allowed_match(line, match):
                issues.append((i, "USERS_PATH", line.strip()))

        # Check for machine names
        for pattern in MACHINE_NAME_PATTERNS:
            for match in pattern.finditer(line):
                if not is_allowed_match(line, match):
                    issues.append((i, "MACHINE_NAME", line.strip()))

        # Check for other absolute paths
        for match in ABSOLUTE_PATH_PATTERN.finditer(line):
            if not is_allowed_match(line, match):
                issues.append((i, "ABSOLUTE_PATH", line.strip()))

    return issues


def byte_compile_python_file(filepath: Path) -> Tuple[bool, str]:
    """Byte-compile a Python file using py_compile. Returns (success, message)."""
    try:
        py_compile.compile(str(filepath), doraise=True, optimize=0)
        return True, f"OK: {filepath.relative_to(PLUGIN_ROOT)}"
    except py_compile.PyCompileError as e:
        return False, f"SYNTAX ERROR in {filepath.relative_to(PLUGIN_ROOT)}: {e}"
    except Exception as e:
        return False, f"COMPILE ERROR in {filepath.relative_to(PLUGIN_ROOT)}: {e}"


def run_grep_check() -> Tuple[bool, List[str]]:
    """Run grep -RInE '/home/[a-z]|/Users/[a-z]|/mnt/|/opt/|C:/' over the changed files."""
    changed_files = [
        "f3_pfade.py",
        "install.sh",
        "README.md",
        "scripts/status.py",
    ]
    issues = []
    for rel_path in changed_files:
        filepath = PLUGIN_ROOT / rel_path
        if not filepath.exists():
            continue
        try:
            result = subprocess.run(
                ["grep", "-InE", r"/home/[a-z]|/Users/[a-z]|/mnt/|/opt/|[A-Za-z]:[/\\]", str(filepath)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    issues.append(f"{rel_path}: {line}")
        except subprocess.TimeoutExpired:
            issues.append(f"{rel_path}: grep timeout")
        except Exception as e:
            issues.append(f"{rel_path}: grep error: {e}")
    return len(issues) == 0, issues


def test_portability():
    """Main test function."""
    print(f"Plugin root: {PLUGIN_ROOT}")
    print("=" * 60)

    all_passed = True
    all_issues = []

    # 1. Scan in-scope files for hard-coded paths
    print("\n[1/3] Scanning in-scope files for non-portable paths...")
    for rel_path in SCAN_FILES:
        filepath = PLUGIN_ROOT / rel_path
        if not filepath.exists():
            print(f"  SKIP (not found): {rel_path}")
            continue

        issues = scan_file_for_issues(filepath)
        if issues:
            all_passed = False
            print(f"  FAIL: {rel_path} ({len(issues)} issues)")
            for line_num, issue_type, line in issues:
                print(f"    Line {line_num} [{issue_type}]: {line[:120]}")
                all_issues.append(f"{rel_path}:{line_num}:{issue_type}:{line}")
        else:
            print(f"  PASS: {rel_path}")

    # 2. Byte-compile Python files
    print("\n[2/3] Byte-compiling in-scope Python scripts...")
    for rel_path in PYTHON_FILES:
        filepath = PLUGIN_ROOT / rel_path
        if not filepath.exists():
            print(f"  SKIP (not found): {rel_path}")
            continue

        success, msg = byte_compile_python_file(filepath)
        if success:
            print(f"  PASS: {msg}")
        else:
            all_passed = False
            print(f"  FAIL: {msg}")
            all_issues.append(msg)

    # 3. Run grep check on the four changed files
    print("\n[3/3] Running grep check on changed files...")
    grep_passed, grep_issues = run_grep_check()
    if grep_passed:
        print("  PASS: grep found no /home/<user>, /Users/<user>, /mnt/, /opt/, or C:/ patterns")
    else:
        all_passed = False
        print("  FAIL: grep found matches:")
        for issue in grep_issues:
            print(f"    {issue}")
            all_issues.append(f"GREP: {issue}")

    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print("VERDICT: PASS - All portability checks passed")
        return 0
    else:
        print(f"VERDICT: FAIL - {len(all_issues)} issue(s) found")
        return 1


if __name__ == "__main__":
    sys.exit(test_portability())


# --- pytest entry point ---
def test_portable_paths():
    """Pytest entry point."""
    assert test_portability() == 0, "Portability test failed"
