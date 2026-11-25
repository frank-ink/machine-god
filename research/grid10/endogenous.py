"""endogenous.py -- E1 Pulse + E2 State Observation (Draft ChatGPT Round 5, 2026-11-25), SHADOW, observation only.

E1 Pulse: one internal tick per 300-s window without user text (f3_endo_puls_log, bucket UNIQUE -> no duplicate processing). There is NO daemon yet: the pulse is
caught up on the next hook run (MAX_CATCHUP windows); a real continuous tick needs a systemd timer and thus the user's explicit OK. Switch star_konfig
frank3.endo.mode (off|shadow, default shadow), frank3.kill=1 stops.
E2 Observation: per tick findings (knowledge gap / contradiction / unfinished) from own ledgers, EACH with resolvable evidence reference {table, where, n}; resolve(conn, ref)
counts whether the reference still yields the claimed number. Findings are observations, not goals, and grant no authorization (goal formation = later piece E3)."""
import hashlib
import json
import time

BUCKET_S, MAX_CATCHUP, MODE_KEY = 300, 12, "frank3.endo.mode"
DDL = ("create table if not exists f3_endo_puls_log(id integer primary key autoincrement, bucket integer not null unique, ts real, event_id text, n_findings integer)",
       "create table if not exists f3_endo_befund(id integer primary key autoincrement, bucket integer, kind text, statement text, evidence_ref text, key text, unique(bucket,key))")


def _tbl(conn, name):
    return conn.execute("select 1 from sqlite_master where type='table' and name=?", (name,)).fetchone() is not None


def _maxid(conn, table):
    return conn.execute("select coalesce(max(rowid),0) from %s" % table).fetchone()[0]


def observe(conn, now):
    """-> List {kind, key, statement, ref:{table, where, n}}; only what the own ledgers actually yield."""
    out = []

    def add(kind, key, stmt, table, where, params=()):
        n = conn.execute("select count(*) from %s where %s" % (table, where), params).fetchone()[0]
        if n:
            out.append({"kind": kind, "key": key, "statement": stmt % n, "ref": {"table": table, "where": where, "params": list(params), "n": n}})

    if _tbl(conn, "f3_class_demand_log"):
        add("gap", "offene_bewertung", "%d Klassenbedarf-Eintraege seit >24 h ohne Bewertung (evaluation_status pending)", "f3_class_demand_log",
            "evaluation_status='pending' and ts<?", (now - 86400,))
    if _tbl(conn, "f3_class_demand_v2_log"):
        add("gap", "abstain_v2", "%d V2-Eintraege ohne qualifizierte Klasse (ABSTAIN): Bedarf unbekannt oder keiner", "f3_class_demand_v2_log", "abstain=1 and rowid<=%d" % _maxid(conn, "f3_class_demand_v2_log"))
    if _tbl(conn, "f3_retina_thal_log"):
        mx = _maxid(conn, "f3_retina_thal_log")  # Evidenz = immutable snapshot (id<=Maximum), otherwise every new row invalidates the finding
        y = conn.execute("select count(*) from f3_retina_thal_log where n_events>0 and rowid<=?", (mx,)).fetchone()[0]
        x = conn.execute("select count(*) from f3_retina_thal_log where n_events>0 and relay<>'[]' and rowid<=?", (mx,)).fetchone()[0]
        if y >= 20 and x / y > 0.9:
            out.append({"kind": "contradiction", "key": "gate_transparent", "statement": "Gate passes almost everything in %d of %d windows with events (>90 %%): hardly any filtering, design intent was selection" % (x, y),
                        "ref": {"table": "f3_retina_thal_log", "where": "n_events>0 and relay<>'[]' and rowid<=%d" % mx, "params": [], "n": x}})
    try:  # WM1 (Round 8): repeatedly high world model prediction error -> contradiction finding with immutable evidence
        import world_model
        out.extend(world_model.finding(conn, now))
    except Exception:
        pass
    try:  # WM2 (Runde 10): Hypothesenraum zu wm_prognosefehler projizieren; offener Widerspruch konkurrierender Erklaerungen -> E2-Befund
        import world_model2
        world_model2.project(conn, now)
        out.extend(world_model2.finding(conn, now))
    except Exception:
        pass
    try:  # Self-model (Round 10, project() runs in hook step register.py): capabilities only from probes; loss of a verified capability -> E2 contradiction
        import self_model
        out.extend(self_model.finding(conn, now))
    except Exception:
        pass
    if _tbl(conn, "omega_goal"):
        n = conn.execute("select count(*) from omega_goal where lower(status) not in ('done','closed','abandoned','complete','completed')").fetchone()[0]
        if n == 0:
            out.append({"kind": "gap", "key": "kein_ziel", "statement": "kein offenes Ziel in omega_goal", "ref": {"table": "omega_goal", "where": "lower(status) not in ('done','closed','abandoned','complete','completed')", "params": [], "n": 0}})
    return out


def resolve(conn, ref):
    """Check evidence reference: does the query still yield exactly the claimed number today? -> (ok, current count)."""
    try:
        n = conn.execute("select count(*) from %s where %s" % (ref["table"], ref["where"]), tuple(ref.get("params", ()))).fetchone()[0]
    except Exception:
        return False, None
    return n == ref["n"], n


def step(conn, now=None):
    now = time.time() if now is None else now
    r = conn.execute("select wert from star_konfig where schluessel=?", (MODE_KEY,)).fetchone()
    k = conn.execute("select wert from star_konfig where schluessel='frank3.kill'").fetchone()
    if (r and r[0] == "off") or (k and k[0] == "1"):
        return 0
    for d in DDL:
        conn.execute(d)
    cur = int(now // BUCKET_S)
    last = conn.execute("select max(bucket) from f3_endo_puls_log").fetchone()[0]
    b0 = max((last if last is not None else cur - 2) + 1, cur - MAX_CATCHUP)
    n = 0
    for b in range(b0, cur):  # completed windows; the current state is observed (no retrospective state), therefore only one finding set at the most recent window per catch-up run
        eid = hashlib.sha256(("puls|%d" % b).encode()).hexdigest()[:16]
        cur_ins = conn.execute("insert or ignore into f3_endo_puls_log(bucket,ts,event_id,n_findings) values(?,?,?,0)", (b, b * BUCKET_S, eid))
        if not cur_ins.rowcount:
            continue
        n += 1
        if b == cur - 1:
            fs = observe(conn, now)
            for f in fs:
                conn.execute("insert or ignore into f3_endo_befund(bucket,kind,statement,evidence_ref,key) values(?,?,?,?,?)", (b, f["kind"], f["statement"], json.dumps(f["ref"]), f["key"]))
            conn.execute("update f3_endo_puls_log set n_findings=? where bucket=?", (len(fs), b))
    conn.execute("delete from f3_endo_puls_log where bucket < (select coalesce(max(bucket),0) from f3_endo_puls_log) - 5000")
    conn.execute("delete from f3_endo_befund where bucket < (select coalesce(max(bucket),0) from f3_endo_befund) - 5000")
    conn.commit()
    return n
