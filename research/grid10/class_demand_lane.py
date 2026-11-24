"""class_demand_lane.py -- Stueck 3 SHADOW: Klassenbedarf je Turn ins Ledger f3_class_demand_log (Regel CLASS_DEMAND_V1, class_demand.py).

Eingaenge: Nutzertext (nur als Hash + Laenge gespeichert, nie Klartext), GRID-Signale des Turns (register.v2_signals, schreibt nichts), gegatetes
Retina-Ergebnis des letzten abgeschlossenen Fensters (f3_retina_thal_log, hoechstens 2 Fenster alt, sonst leer), offenes Ziel (omega_goal, leer
auf dieser Maschine solange keine Zeile offen ist). Schreibt NUR f3_class_demand_log; kein Router-Aufruf, keine Wirkung auf Antworten/Routing.
Schalter star_konfig frank3.class_demand.mode (off|shadow, Standard shadow), frank3.kill=1 stoppt. Felder nach ChatGPT-Runde 3; router_version, model_id,
response_ref, outcome bleiben bis zur Router-Anbindung NULL, evaluation_status='pending'. G9 gilt als gueltig, wenn > 0 (0 = identisch oder keine Historie)."""
import hashlib
import json
import time

from class_demand import RULE_VERSION, derive
from router_shadow import decide
import class_demand_v2 as v2

MODE_KEY = "frank3.class_demand.mode"
BUCKET_S = 300
DDL = ("create table if not exists f3_class_demand_log(id integer primary key autoincrement, rule_version text, event_id text unique, frame_id text,"
       " ts real, input_ref text, goal_ref text, grid_values text, retina_event_ids text, retina_channels text, burst integer, feature_matches text,"
       " scores_by_class text, selected_classes text, overflow text, abstain integer, router_version text, model_id text, response_ref text, outcome text,"
       " evaluation_status text, session_id text)",)


def _h(s):
    return hashlib.sha256((s or "").encode("utf-8", "replace")).hexdigest()[:16]


def retina_state(conn, now):
    """-> (relay, burst, event_ids) des letzten abgeschlossenen Gate-Fensters, hoechstens 2 Fenster alt."""
    try:
        r = conn.execute("select bucket,relay,burst from f3_retina_thal_log order by bucket desc limit 1").fetchone()
        if not r or now // BUCKET_S - r[0] > 2:
            return [], False, []
        relay, burst = json.loads(r[1]), json.loads(r[2])
        if not relay:
            return [], bool(burst), []
        q = "select id from f2_retina_geschehen where ts>=? and ts<? and art in (%s)" % ",".join("?" * len(relay))
        ids = [x[0] for x in conn.execute(q, (r[0] * BUCKET_S, (r[0] + 1) * BUCKET_S, *relay))]
        return relay, bool(burst), ids
    except Exception:
        return [], False, []


DDL2 = ("create table if not exists f3_class_demand_v2_log(id integer primary key autoincrement, rule_version text, event_id text unique, frame_id text, ts real,"
        " session_id text, input_ref text, selected_classes text, abstain integer, fields text)",)


def retina_fresh(conn, now):
    """True, wenn ein Gate-Fenster <= 2 Fenster alt existiert (Retina verfuegbar, auch wenn leer); sonst False = NICHT gemessen (nicht Null)."""
    try:
        r = conn.execute("select max(bucket) from f3_retina_thal_log").fetchone()
        return bool(r and r[0] is not None and now // BUCKET_S - r[0] <= 2)
    except Exception:
        return False


def step(conn, session_id, frame_id, prompt, sig, now=None):
    now = time.time() if now is None else now
    m = conn.execute("select wert from star_konfig where schluessel=?", (MODE_KEY,)).fetchone()
    k = conn.execute("select wert from star_konfig where schluessel='frank3.kill'").fetchone()
    if (m and m[0] == "off") or (k and k[0] == "1"):
        return None
    for d in DDL:
        conn.execute(d)
    if "session_id" not in [c[1] for c in conn.execute("pragma table_info(f3_class_demand_log)")]:
        conn.execute("alter table f3_class_demand_log add column session_id text")
    goal, goal_id = "", None
    try:
        g = conn.execute("select goal,id from omega_goal where lower(status) not in ('done','closed','abandoned','complete','completed') order by priority desc limit 1").fetchone()
        goal, goal_id = (g[0], str(g[1])) if g else ("", None)
    except Exception:
        pass
    relay, burst, eids = retina_state(conn, now)
    grid = {"G6": sig.get("G6", 0.0), "G9": sig.get("G9", 0.0), "G10": sig.get("G10", 0.0), "g9_valid": sig.get("G9", 0.0) > 0}
    o = derive(prompt, goal, grid, relay, burst)
    rv, pick = decide(o["selected"])
    eid = _h("%s|%s|%s" % (session_id, frame_id, now))
    conn.execute("insert or ignore into f3_class_demand_log(rule_version,event_id,frame_id,ts,input_ref,goal_ref,grid_values,retina_event_ids,retina_channels,burst,"
                 "feature_matches,scores_by_class,selected_classes,overflow,abstain,router_version,evaluation_status,session_id,model_id) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (RULE_VERSION, eid, str(frame_id), now, "%s:%d" % (_h(prompt), len(prompt or "")), _h(goal) if goal else "", json.dumps({k2: round(v, 4) if isinstance(v, float) else v for k2, v in grid.items()}),
                  json.dumps(eids), json.dumps(relay), int(burst), json.dumps(o["features"]), json.dumps(o["scores"]), json.dumps(o["selected"]),
                  json.dumps(o["overflow"]), int(o["abstain"]), rv, "pending", str(session_id), json.dumps(pick) if pick else None))
    for d in DDL2:
        conn.execute(d)
    o2 = v2.derive(prompt, goal, {"G9": grid["G9"], "G10": grid["G10"], "g9_valid": grid["g9_valid"]}, relay, burst, goal_id=goal_id, retina_available=retina_fresh(conn, now))
    conn.execute("insert or ignore into f3_class_demand_v2_log(rule_version,event_id,frame_id,ts,session_id,input_ref,selected_classes,abstain,fields) values(?,?,?,?,?,?,?,?,?)",
                 (v2.RULE_VERSION, eid, str(frame_id), now, str(session_id), "%s:%d" % (_h(prompt), len(prompt or "")), json.dumps(o2["selected_classes"]), int(o2["abstain"]),
                  json.dumps(o2)))
    conn.execute("delete from f3_class_demand_v2_log where id < (select coalesce(max(id),0) from f3_class_demand_v2_log) - 20000")
    conn.execute("delete from f3_class_demand_log where id < (select max(id) from f3_class_demand_log) - 20000")
    conn.commit()
    return o


def resolve_input(session_id, input_ref, projects_dir=None):
    """Kalibrierung/Blindbewertung: loest input_ref ('<hash16>:<laenge>') lokal gegen das Sitzungsprotokoll auf (keine zweite Klartextkopie in der DB).
    -> Text oder None. Nur fuer den Auswerter (Aufrufer, nicht der Router); der Text wird nie zurueckgeschrieben."""
    import glob
    import os
    h, _, n = (input_ref or "").partition(":")
    for f in glob.glob(os.path.join(os.path.expanduser(projects_dir or os.environ.get("MG_TRANSCRIPT_DIR", "/nonexistent")), "*", "%s.jsonl" % session_id)):
        for line in open(f, errors="replace"):
            try:
                d = json.loads(line)
            except Exception:
                continue
            c = (d.get("message") or {}).get("content") if d.get("type") == "user" else None
            if isinstance(c, str) and len(c) == int(n or -1) and _h(c) == h:
                return c
    return None
