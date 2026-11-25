"""retina_grid.py -- Retina as GRID sublayer, Piece 1 (SHADOW), the user 2026-11-24 "A-GRID first".

The OWN Retina (event stream f2_retina_geschehen: objekt_neu/-weg, person_kommt/-geht, fokus_app; only text/numbers, no image) feeds
the same GridV2Engine as the Text-GRID. Fixed time windows (BUCKET_S): each completed window is ONE step, even an empty one
(deterministic, replicable from the event log). Own tables f3_grid_v2r_*; NEVER writes to f3_grid_v2_state / v2x, publishes
NOTHING to frank3_gwt (observation, until test gate green and user sets to active). Switch star_konfig frank3.grid_retina.mode (off|shadow,
Default shadow), frank3.kill=1 stops. Cell mapping UNCALIBRATED (initial values, only monotonic in the mentioned feature):
  G9 Surprise = clamp(max(bits in window)/4)   G4 Binding = 1 when person_kommt/person_geht   G6 ToolPressure = 1 when fokus_app
  G10 Scope = clamp(Events/10)
Measurement 2026-11-24: the 0.8B readings (f2_retina_lesung) do not carry as signal (98% abstention, 3-7 values per axis) -> not used here."""
import json
import time

from grid_v2 import GridV2Engine

BUCKET_S = 300
MAX_BUCKETS = 24  # Aufholgrenze je Aufruf (2 h); aeltere Luecken werden uebersprungen, nicht erfunden
MODE_KEY = "frank3.grid_retina.mode"
DDL = (
    "create table if not exists f3_grid_v2r_state(singleton integer primary key check(singleton=1), j text not null, updated real not null)",
    "create table if not exists f3_grid_v2r_log(id integer primary key autoincrement, ts real not null, bucket integer not null unique, n_events integer,"
    " v2_winner text, abstain integer, max_score real, thresh real, signals text)",
)


def _clamp(x):
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def window_signals(events):
    """events: List (type, bits) of a window -> {Cell: Value in [0,1]}. Empty window -> all 0 (no invention)."""
    arts = {a for a, _ in events}
    bits = [float(b or 0.0) for _, b in events]
    return {
        "G9": _clamp(max(bits) / 4.0) if bits else 0.0,
        "G4": 1.0 if arts & {"person_kommt", "person_geht"} else 0.0,
        "G6": 1.0 if "fokus_app" in arts else 0.0,
        "G10": _clamp(len(events) / 10.0),
    }


def _events(conn, b0, b1):
    """{bucket: [(type, bits)]} for the windows [b0, b1)."""
    out = {b: [] for b in range(b0, b1)}
    for ts, art, bits in conn.execute("select ts,art,bits from f2_retina_geschehen where ts>=? and ts<? order by ts", (b0 * BUCKET_S, b1 * BUCKET_S)):
        out[int(ts // BUCKET_S)].append((art, bits))
    return out


def replay(conn, b0, b1, engine=None):
    """Read-only (for the test gate): Steps over the windows [b0,b1) -> List of engine outputs."""
    e = engine or GridV2Engine()
    ev = _events(conn, b0, b1)
    return [e.step(window_signals(ev[b])) for b in range(b0, b1)]


def step_buckets(conn, now=None):
    """Processes all completed, not yet seen windows (idempotent via bucket UNIQUE). -> Number of new steps."""
    now = time.time() if now is None else now
    r = conn.execute("select wert from star_konfig where schluessel=?", (MODE_KEY,)).fetchone()
    k = conn.execute("select wert from star_konfig where schluessel='frank3.kill'").fetchone()
    if (r and r[0] == "off") or (k and k[0] == "1"):
        return 0
    for d in DDL:
        conn.execute(d)
    cur = int(now // BUCKET_S)  # current window is still open
    row = conn.execute("select j from f3_grid_v2r_state where singleton=1").fetchone()
    st = json.loads(row[0]) if row else {}
    e = GridV2Engine.from_json(st["eng"]) if st.get("eng") else GridV2Engine()
    b0 = max(int(st.get("last", cur - 2)) + 1, cur - MAX_BUCKETS)
    if b0 >= cur:
        return 0
    ev, n = _events(conn, b0, cur), 0
    for b in range(b0, cur):
        sig = window_signals(ev[b])
        o = e.step(sig)
        conn.execute("insert or ignore into f3_grid_v2r_log(ts,bucket,n_events,v2_winner,abstain,max_score,thresh,signals) values(?,?,?,?,?,?,?,?)",
                     (b * BUCKET_S, b, len(ev[b]), o["winner"], int(o["abstain"]), o["max_score"], o["thresh"], json.dumps({c: v for c, v in sig.items() if v})))
        n += 1
    conn.execute("insert or replace into f3_grid_v2r_state(singleton,j,updated) values(1,?,?)", (json.dumps({"eng": e.to_json(), "last": cur - 1}), now))
    conn.execute("delete from f3_grid_v2r_log where bucket < (select max(bucket) from f3_grid_v2r_log) - 5000")  # begrenzt
    conn.commit()
    return n
