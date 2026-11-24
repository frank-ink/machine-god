"""endogen.py -- E1 Puls + E2 Zustandsbeobachtung (Entwurf ChatGPT Runde 5, 2026-11-25), SHADOW, nur Beobachtung.

E1 Puls: ein interner Takt pro 300-s-Fenster ohne Nutzertext (f3_endo_puls_log, bucket UNIQUE -> keine Doppelverarbeitung). Es gibt noch KEINEN Daemon: der Puls wird
beim naechsten Hook-Lauf nachgeholt (MAX_CATCHUP Fenster); ein echter Dauertakt braucht einen systemd-Timer und damit des Nutzers ausdrueckliches OK. Schalter star_konfig
frank3.endo.mode (off|shadow, Standard shadow), frank3.kill=1 stoppt.
E2 Beobachtung: je Takt Befunde (Wissensluecke / Widerspruch / Unerledigtes) aus eigenen Ledgern, JEDER mit aufloesbarer Evidenzreferenz {table, where, n}; resolve(conn, ref)
zaehlt nach, ob die Referenz die behauptete Anzahl noch liefert. Befunde sind Beobachtungen, keine Ziele und geben keine Berechtigung (Zielbildung = spaeteres Stueck E3)."""
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
    """-> Liste {kind, key, statement, ref:{table, where, n}}; nur was die eigenen Ledger tatsaechlich hergeben."""
    out = []

    def add(kind, key, stmt, table, where, params=()):
        n = conn.execute("select count(*) from %s where %s" % (table, where), params).fetchone()[0]
        if n:
            out.append({"kind": kind, "key": key, "statement": stmt % n, "ref": {"table": table, "where": where, "params": list(params), "n": n}})

    if _tbl(conn, "f3_class_demand_log"):
        add("luecke", "offene_bewertung", "%d Klassenbedarf-Eintraege seit >24 h ohne Bewertung (evaluation_status pending)", "f3_class_demand_log",
            "evaluation_status='pending' and ts<?", (now - 86400,))
    if _tbl(conn, "f3_class_demand_v2_log"):
        add("luecke", "abstain_v2", "%d V2-Eintraege ohne qualifizierte Klasse (ABSTAIN): Bedarf unbekannt oder keiner", "f3_class_demand_v2_log", "abstain=1 and rowid<=%d" % _maxid(conn, "f3_class_demand_v2_log"))
    if _tbl(conn, "f3_retina_thal_log"):
        mx = _maxid(conn, "f3_retina_thal_log")  # Evidenz = unveraenderlicher Schnappschuss (id<=Maximum), sonst entwertet jede neue Zeile den Befund
        y = conn.execute("select count(*) from f3_retina_thal_log where n_events>0 and rowid<=?", (mx,)).fetchone()[0]
        x = conn.execute("select count(*) from f3_retina_thal_log where n_events>0 and relay<>'[]' and rowid<=?", (mx,)).fetchone()[0]
        if y >= 20 and x / y > 0.9:
            out.append({"kind": "widerspruch", "key": "gate_durchsichtig", "statement": "Gate reicht in %d von %d Fenstern mit Ereignissen etwas weiter (>90 %%): kaum Filterwirkung, Entwurfsabsicht war Auswahl" % (x, y),
                        "ref": {"table": "f3_retina_thal_log", "where": "n_events>0 and relay<>'[]' and rowid<=%d" % mx, "params": [], "n": x}})
    try:  # WM1 (Runde 8): wiederholt hoher Prognosefehler des Weltmodells -> Widerspruchsbefund mit unveraenderlicher Evidenz
        import weltmodell
        out.extend(weltmodell.befund(conn, now))
    except Exception:
        pass
    try:  # WM2 (Runde 10): Hypothesenraum zu wm_prognosefehler projizieren; offener Widerspruch konkurrierender Erklaerungen -> E2-Befund
        import weltmodell2
        weltmodell2.project(conn, now)
        out.extend(weltmodell2.befund(conn, now))
    except Exception:
        pass
    try:  # Selbstmodell (Runde 10, project() laeuft im Hook-Schritt register.py): Faehigkeiten nur aus Sonden; Verlust einer verifizierten Faehigkeit -> E2-Widerspruch
        import selbstmodell
        out.extend(selbstmodell.befund(conn, now))
    except Exception:
        pass
    if _tbl(conn, "omega_goal"):
        n = conn.execute("select count(*) from omega_goal where lower(status) not in ('done','closed','abandoned','complete','completed')").fetchone()[0]
        if n == 0:
            out.append({"kind": "luecke", "key": "kein_ziel", "statement": "kein offenes Ziel in omega_goal", "ref": {"table": "omega_goal", "where": "lower(status) not in ('done','closed','abandoned','complete','completed')", "params": [], "n": 0}})
    return out


def resolve(conn, ref):
    """Evidenzreferenz pruefen: liefert die Abfrage heute noch genau die behauptete Anzahl? -> (ok, aktuelle Anzahl)."""
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
    for b in range(b0, cur):  # abgeschlossene Fenster; beobachtet wird der Stand jetzt (kein Rueckblick-Zustand), daher pro Nachhol-Lauf nur ein Befundsatz am juengsten Fenster
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
