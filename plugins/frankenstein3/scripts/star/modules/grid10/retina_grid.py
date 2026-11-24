"""retina_grid.py -- Retina als GRID-Unterschicht, Stueck 1 (SHADOW), Gabriel 2026-11-24 "A-GRID zuerst".

Die EIGENE Retina (Ereignisstrom f2_retina_geschehen: objekt_neu/-weg, person_kommt/-geht, fokus_app; nur Text/Zahlen, kein Bild) speist
dieselbe GridV2Engine wie der Text-GRID. Feste Zeitfenster (BUCKET_S): jedes abgeschlossene Fenster ist EIN Schritt, auch ein leeres
(deterministisch, aus dem Ereignislog replizierbar). Eigene Tabellen f3_grid_v2r_*; schreibt NIE nach f3_grid_v2_state / v2x, publiziert
NICHTS an frank3_gwt (Beobachtung, bis Test-Tor gruen und Gabriel auf active stellt). Schalter star_konfig frank3.grid_retina.mode (off|shadow,
Standard shadow), frank3.kill=1 stoppt. Zellzuordnung UNKALIBRIERT (Startwerte, nur monoton im genannten Merkmal):
  G9 Ueberraschung = clamp(max(bits im Fenster)/4)   G4 Bindung = 1 wenn person_kommt/person_geht   G6 Werkzeugdruck = 1 wenn fokus_app
  G10 Umfang = clamp(Ereignisse/10)
Messung 2026-11-24: die 0.8B-Lesungen (f2_retina_lesung) tragen als Signal nicht (98 % Enthaltung, 3-7 Werte je Achse) -> hier nicht benutzt."""
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
    """events: Liste (art, bits) eines Fensters -> {Zelle: Wert in [0,1]}. Leeres Fenster -> alle 0 (keine Erfindung)."""
    arts = {a for a, _ in events}
    bits = [float(b or 0.0) for _, b in events]
    return {
        "G9": _clamp(max(bits) / 4.0) if bits else 0.0,
        "G4": 1.0 if arts & {"person_kommt", "person_geht"} else 0.0,
        "G6": 1.0 if "fokus_app" in arts else 0.0,
        "G10": _clamp(len(events) / 10.0),
    }


def _events(conn, b0, b1):
    """{bucket: [(art, bits)]} fuer die Fenster [b0, b1)."""
    out = {b: [] for b in range(b0, b1)}
    for ts, art, bits in conn.execute("select ts,art,bits from f2_retina_geschehen where ts>=? and ts<? order by ts", (b0 * BUCKET_S, b1 * BUCKET_S)):
        out[int(ts // BUCKET_S)].append((art, bits))
    return out


def replay(conn, b0, b1, engine=None):
    """Nur lesend (fuer das Test-Tor): Schritte ueber die Fenster [b0,b1) -> Liste der Engine-Ausgaben."""
    e = engine or GridV2Engine()
    ev = _events(conn, b0, b1)
    return [e.step(window_signals(ev[b])) for b in range(b0, b1)]


def step_buckets(conn, now=None):
    """Verarbeitet alle abgeschlossenen, noch nicht gesehenen Fenster (idempotent ueber bucket UNIQUE). -> Anzahl neuer Schritte."""
    now = time.time() if now is None else now
    r = conn.execute("select wert from star_konfig where schluessel=?", (MODE_KEY,)).fetchone()
    k = conn.execute("select wert from star_konfig where schluessel='frank3.kill'").fetchone()
    if (r and r[0] == "off") or (k and k[0] == "1"):
        return 0
    for d in DDL:
        conn.execute(d)
    cur = int(now // BUCKET_S)  # laufendes Fenster ist noch offen
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
