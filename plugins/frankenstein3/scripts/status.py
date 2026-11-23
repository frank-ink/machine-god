#!/usr/bin/env python3
"""Misst den Plugin-Zustand (selbstenthalten): Daten-DB, Tabellen, Hooks im Trockenlauf. PASS/FAIL-Tabelle."""
import os, sys, json, sqlite3, subprocess, time
D = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(D, "star"))
import f3_pfade as pf
rows = []
def add(n, s, d=""): rows.append((n, s, str(d)[:90]))
pf.ensure_db()
add("data dir", "PASS" if pf.DATA.is_dir() else "FAIL", pf.DATA)
try:
    c = sqlite3.connect("file:%s?mode=ro" % pf.DB, uri=True, timeout=1)
    tabs = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
    c.close()
    add("unified.db tables", "PASS" if len(tabs) > 50 else "FAIL", "%d tables" % len(tabs))
    for t in ("zero_raum", "star_konfig", "entityos_arbeitspaket"):
        add("table " + t, "PASS" if t in tabs else "FAIL")
except Exception as e:
    add("unified.db", "FAIL", e)
for name in ("digest.py", "reentry.py"):
    t0 = time.time()
    try:
        r = subprocess.run([sys.executable, os.path.join(D, name)], capture_output=True, text=True, timeout=10)
        json.loads(r.stdout)
        add("hook " + name, "PASS" if r.returncode == 0 else "FAIL", "%.0f ms" % ((time.time() - t0) * 1000))
    except Exception as e:
        add("hook " + name, "FAIL", e)
w = max(len(r[0]) for r in rows)
for n, s, d in rows:
    print("%-*s  %-6s %s" % (w, n, s, d))
f = sum(1 for r in rows if r[1] == "FAIL")
print("VERDICT: %d PASS, %d FAIL. %s" % (len(rows) - f, f, "Core measured OK." if not f else "FAILs present - do not claim healthy."))
