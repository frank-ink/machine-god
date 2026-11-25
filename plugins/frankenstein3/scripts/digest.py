#!/usr/bin/env python3
"""SessionStart digest. Self-contained, no LLM, no network, reads only local files. Fail-silent, exit 0."""
import json
import os
import sys
import sqlite3
from pathlib import Path


def resolve_data_dir() -> Path:
    """Resolve data directory via env vars -> XDG -> fallback. No hardcoded paths."""
    for var in ("FRANK3_DATA", "CLAUDE_PLUGIN_DATA"):
        val = os.environ.get(var)
        if val:
            return Path(val).expanduser().resolve()

    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        return Path(xdg_data).expanduser().resolve() / "frankenstein3"

    home = Path.home()
    return home / ".local" / "share" / "frankenstein3"


def main() -> None:
    try:
        data_dir = resolve_data_dir()
        db_path = data_dir / "unified.db"

        state = f"unified.db: {db_path} (fresh local memory, owned by this plugin)"
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=0.2)
            n = conn.execute("select count(*) from sqlite_master where type='table'").fetchone()[0]
            conn.close()
            state += f", {n} tables"
        except Exception:
            state += ", unreadable"

        txt = (
            "[Frankenstein 3.0 digest]\n"
            "Identity: one entity, no coordinator/agent split. The harness is the body, the LLM is worker and mouth, local databases are memory.\n"
            "Don't know -> look it up in the local unified.db or the codebase; never guess. Measure before believing.\n"
            + state + "\n"
            "Commands: /architect (architect mode), /end (leave it). Skill: caveman (terse style). /frank3-status measures this install.\n"
            "Claims policy: no consciousness/sentience claims."
        )
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": txt}}))
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
