#!/usr/bin/env python3
"""SessionStart reentry (FULL): measures live state. No LLM, no network ,
read-only DB, fail-silent, exit 0. Target < ~300 ms."""
import json, os, sys, sqlite3, subprocess, time, shutil
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "star"))
import f3_paths as PF

H = os.path.expanduser("~")
NOW = time.time()


def sh(argv, t=1.0):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=t).stdout
    except Exception:
        return ""


def section(L, fn):
    try:
        fn(L)
    except Exception as e:
        L.append("(%s failed: %s)" % (fn.__name__, str(e)[:60]))


def db_part(L):
    PF.ensure_db()
    db = str(PF.DB)
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=0.2)
    try:
        run = con.execute("select work_package_id,substr(task,1,60),(? - changed)/3600.0 from entityos_work_package "
                          "where stand='running' order by changed desc", (NOW,)).fetchall()
        orphan = [r for r in run if r[2] > 6]
        L.append("packages stand=running: %d (orphaned >6h: %d)" % (len(run), len(orphan)))
        for r in [x for x in run if x[2] <= 6][:4]:
            L.append("  - %s %s (%.1fh)" % r)
        for r in orphan[:4]:
            L.append("  - ORPHANED %s %s (%.0fh)" % r)
        last = con.execute("select work_package_id,stand,substr(task,1,50) from entityos_work_package order by changed desc limit 3").fetchall()
        L.append("latest packages:" + "".join("\n  - %s [%s] %s" % r for r in last))
        # organ modes (frank3.*): unset key = code default (shadow), not a measured value
        modes = con.execute("select key,value from star_config where key like 'frank3.%.mode' or key='frank3.kill' order by 1").fetchall()
        L.append("organ modes (star_config frank3.*): " + (", ".join("%s=%s" % (k[7:], v) for k, v in modes) if modes else "none set (code defaults, shadow)"))
        # GRID v2 shadow log
        if con.execute("select 1 from sqlite_master where name='f3_grid_v2_log'").fetchone():
            r = con.execute("select count(*),max(ts) from f3_grid_v2_log").fetchone()
            L.append("GRID f3_grid_v2_log: %d rows, last %s ago" % (r[0], ("%.0fmin" % ((NOW - r[1]) / 60)) if r[1] else "n/a"))
        else:
            L.append("GRID f3_grid_v2_log: table absent (lazily created by grid10 shadow lane)")
        # Room
        rr = con.execute("select human,nickname,state,substr(activity,1,40),(? - since)/60.0 from zero_room "
                         "where state!='free' and (? - since) < 1800 order by since desc limit 5", (NOW, NOW)).fetchall()
        L.append("Room active (<30min): %d" % len(rr) + "".join("\n  - %s/%s %s '%s' (%.0fmin)" % r for r in rr))
    finally:
        con.close()


def sys_part(L):
    d = shutil.disk_usage(H)
    mem = {}
    for ln in open("/proc/meminfo"):
        k, v = ln.split(":", 1)
        mem[k] = int(v.split()[0])
    L.append("disk: %.0f%% used, %.0f GB free; mem avail %.1f/%.1f GB; load %s" % (
        100.0 * d.used / d.total, d.free / 1e9, mem["MemAvailable"] / 1e6, mem["MemTotal"] / 1e6, os.getloadavg()[0]))


def main():
    L = []
    for fn in (db_part, sys_part):
        section(L, fn)
    txt = ("[Frankenstein 3.0 REENTRY @ session start " + time.strftime("%Y-%m-%d %H:%M") + "]\n" + "\n".join(L) + "\n"
           + "Do first: verify these claims against live state (measure before believing; 'orphaned' = stand=running older than 6h, check before trusting). "
             "Then give the user ONE short status plus options (A/B/C). Do not act on old plans unasked.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": txt}}))


try:
    main()
except Exception:
    pass
sys.exit(0)
