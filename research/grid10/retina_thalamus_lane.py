"""retina_thalamus_lane.py -- Stueck 2 SHADOW: Thalamus-Gating ueber dem Retina-Ereignisstrom, danach dieselbe GridV2Engine.

Je abgeschlossenem 5-min-Fenster (wie retina_grid.py): Zaehler je Kanal -> RetinaThalamus.gate -> nur relayte Kanaele speisen die Engine
(Lane "g", Tabellen f3_retina_thal_state/log + f3_grid_v2g_state/log). Schreibt NIE f3_grid_v2_state / v2x / v2r, publiziert nichts an
frank3_gwt. Schalter star_konfig frank3.retina_thal.mode (off|shadow, Standard shadow), frank3.kill=1 stoppt. Rueckkanal (receive_feedback)
ist hier NICHT angeschlossen: das ist die Verdrahtung ueber die Antwort (spaeteres Stueck). Idempotent ueber bucket UNIQUE."""
import json
import time

from grid_v2 import GridV2Engine
from retina_grid import BUCKET_S, MAX_BUCKETS, window_signals
from retina_thalamus import CHANNELS, RetinaThalamus

MODE_KEY = "frank3.retina_thal.mode"
DDL = (
    "create table if not exists f3_retina_thal_state(singleton integer primary key check(singleton=1), j text not null, updated real not null)",
    "create table if not exists f3_retina_thal_log(id integer primary key autoincrement, ts real not null, bucket integer not null unique,"
    " n_events integer, relay text, burst text, gains text)",
    "create table if not exists f3_grid_v2g_state(singleton integer primary key check(singleton=1), j text not null, updated real not null)",
    "create table if not exists f3_grid_v2g_log(id integer primary key autoincrement, ts real not null, bucket integer not null unique,"
    " v2_winner text, abstain integer, max_score real, thresh real, signals text)",
)


def _window(events):
    """events [(art,bits)] -> (Zaehler je Kanal, Ereignisse nur relayter Kanaele wird spaeter gefiltert)."""
    cnt = {}
    for a, _ in events:
        if a in CHANNELS:
            cnt[a] = cnt.get(a, 0) + 1
    return cnt


def _step(th, eng, b, events):
    cnt = _window(events)
    g = th.gate(cnt, (b + 1) * BUCKET_S)
    kept = [(a, bits) for a, bits in events if a in g["relay"]]
    o = eng.step(window_signals(kept))
    return g, kept, o


def replay(conn, b0, b1):
    """Nur lesend (Test-Tor): Fenster [b0,b1) -> Liste (Gate-Ausgabe, Zahl Ereignisse roh, Zahl Ereignisse relayt, Engine-Ausgabe)."""
    from retina_grid import _events
    th, eng, out = RetinaThalamus(), GridV2Engine(), []
    ev = _events(conn, b0, b1)
    for b in range(b0, b1):
        g, kept, o = _step(th, eng, b, ev[b])
        out.append((g, len(ev[b]), len(kept), o))
    return out


def step_buckets(conn, now=None):
    from retina_grid import _events
    now = time.time() if now is None else now
    r = conn.execute("select wert from star_konfig where schluessel=?", (MODE_KEY,)).fetchone()
    k = conn.execute("select wert from star_konfig where schluessel='frank3.kill'").fetchone()
    if (r and r[0] == "off") or (k and k[0] == "1"):
        return 0
    for d in DDL:
        conn.execute(d)
    cur = int(now // BUCKET_S)
    row = conn.execute("select j from f3_retina_thal_state where singleton=1").fetchone()
    st = json.loads(row[0]) if row else {}
    rowe = conn.execute("select j from f3_grid_v2g_state where singleton=1").fetchone()
    th = RetinaThalamus.from_json(st["th"]) if st.get("th") else RetinaThalamus()
    eng = GridV2Engine.from_json(json.loads(rowe[0])["eng"]) if rowe else GridV2Engine()
    b0 = max(int(st.get("last", cur - 2)) + 1, cur - MAX_BUCKETS)
    if b0 >= cur:
        return 0
    ev, n = _events(conn, b0, cur), 0
    for b in range(b0, cur):
        g, kept, o = _step(th, eng, b, ev[b])
        conn.execute("insert or ignore into f3_retina_thal_log(ts,bucket,n_events,relay,burst,gains) values(?,?,?,?,?,?)",
                     (b * BUCKET_S, b, len(ev[b]), json.dumps(g["relay"]), json.dumps(g["burst"]), json.dumps({c: round(v, 4) for c, v in g["gains"].items()})))
        conn.execute("insert or ignore into f3_grid_v2g_log(ts,bucket,v2_winner,abstain,max_score,thresh,signals) values(?,?,?,?,?,?,?)",
                     (b * BUCKET_S, b, o["winner"], int(o["abstain"]), o["max_score"], o["thresh"], json.dumps({c: v for c, v in window_signals(kept).items() if v})))
        n += 1
    conn.execute("insert or replace into f3_retina_thal_state(singleton,j,updated) values(1,?,?)", (json.dumps({"th": th.to_json(), "last": cur - 1}), now))
    conn.execute("insert or replace into f3_grid_v2g_state(singleton,j,updated) values(1,?,?)", (json.dumps({"eng": eng.to_json()}), now))
    conn.execute("delete from f3_retina_thal_log where bucket < (select max(bucket) from f3_retina_thal_log) - 5000")
    conn.execute("delete from f3_grid_v2g_log where bucket < (select max(bucket) from f3_grid_v2g_log) - 5000")
    conn.commit()
    return n
