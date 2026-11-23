#!/usr/bin/env python3
"""SessionStart digest. Selbstenthalten, kein LLM, kein Netz, liest nur lokale Dateien. Fail-silent, exit 0."""
import json, os, sys, sqlite3
try:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "star"))
    import f3_pfade as pf
    pf.ensure_db()
    state = "unified.db: " + str(pf.DB) + " (fresh local memory, owned by this plugin)"
    try:
        c = sqlite3.connect("file:%s?mode=ro" % pf.DB, uri=True, timeout=0.2)
        n = c.execute("select count(*) from sqlite_master where type='table'").fetchone()[0]
        c.close()
        state += ", %d tables" % n
    except Exception:
        state += ", unreadable"
    txt = (
        "[Frankenstein 3.0 digest]\n"
        "Identity: one entity, no coordinator/agent split. The harness is the body, the LLM is worker and mouth, local databases are memory.\n"
        "Don't know -> look it up in the local unified.db or the codebase; never guess. Measure before believing.\n"
        + state + "\n"
        "Commands: /architekt (architect mode), /end (leave it). Skill: caveman (terse style). /frank3-status measures this install.\n"
        "Claims policy: no consciousness/sentience claims."
    )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": txt}}))
except Exception:
    pass
sys.exit(0)
