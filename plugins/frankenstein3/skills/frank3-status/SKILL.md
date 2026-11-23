---
name: frank3-status
description: Measure (not assume) the Frankenstein 3.0 state - data dir, unified.db, tables, hooks - and print a PASS/FAIL/SHADOW table with a one-line verdict.
---

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/status.py"` and show its table verbatim, then the verdict line.
Do not re-interpret FAIL as PASS. If a row says STALE-TEXT, report it as a documentation discrepancy, not a runtime fault.
No consciousness claims.
