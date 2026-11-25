"""Test gate Retina-GRID part 1 (shadow). Run: python3 -I test_retina_grid.py (Exit 0 = green). Real data replay read-only."""
import json
import os
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import retina_grid as rg

REAL = os.environ.get("MG_REAL_DB", "")
B = rg.BUCKET_S


def mem(events):
    c = sqlite3.connect(":memory:")
    c.execute("create table star_konfig(schluessel text primary key, wert text)")
    c.execute("create table f2_retina_geschehen(id integer primary key, ts real, art text, bits real)")
    c.execute("create table f3_grid_v2_state(singleton integer primary key, j text, updated real)")
    c.executemany("insert into f2_retina_geschehen(ts,art,bits) values(?,?,?)", events)
    c.commit()
    return c


def t_mapping():
    assert rg.window_signals([]) == {"G9": 0.0, "G4": 0.0, "G6": 0.0, "G10": 0.0}  # leer = nichts erfunden
    s = rg.window_signals([("person_kommt", 2.0), ("fokus_app", 8.0)] + [("objekt_neu", 1.0)] * 12)
    assert s["G9"] == 1.0 and s["G4"] == 1.0 and s["G6"] == 1.0 and s["G10"] == 1.0
    assert all(0.0 <= v <= 1.0 for v in s.values())


def t_idempotent_and_isolation():
    now = 1000 * B + 10
    ev = [(996 * B + 5, "person_kommt", 1.5), (997 * B + 5, "fokus_app", 1.6), (998 * B + 1, "objekt_neu", 2.0)]
    c = mem(ev)
    before = c.execute("select count(*) from f3_grid_v2_state").fetchone()
    n1 = rg.step_buckets(c, now)
    n2 = rg.step_buckets(c, now)  # gleiches Zeitfenster nochmal
    assert n1 >= 1 and n2 == 0, (n1, n2)
    rows = c.execute("select bucket,n_events from f3_grid_v2r_log order by bucket").fetchall()
    assert len({r[0] for r in rows}) == len(rows)  # no duplicate windows
    assert c.execute("select count(*) from f3_grid_v2_state").fetchone() == before  # Haupt-State unberuehrt
    c.execute("insert into star_konfig values('frank3.grid_retina.mode','off')")
    assert rg.step_buckets(c, now + 5 * B) == 0  # Schalter off wirkt
    c.execute("update star_konfig set wert='shadow' where schluessel='frank3.grid_retina.mode'")
    c.execute("insert into star_konfig values('frank3.kill','1')")
    assert rg.step_buckets(c, now + 5 * B) == 0  # Kill wirkt


def t_gap_capped():
    c = mem([])
    rg.step_buckets(c, 1000 * B + 1)
    n = rg.step_buckets(c, 1000 * B + 1 + 500 * B)  # long gap: only catch up MAX_BUCKETS
    assert n == rg.MAX_BUCKETS, n


def t_real_data_replay():
    if not os.path.exists(REAL):
        print("  (kein Echtdaten-DB, Replay uebersprungen)")
        return
    c = sqlite3.connect("file:%s?mode=ro" % REAL, uri=True)
    lo, hi = c.execute("select min(ts),max(ts) from f2_retina_geschehen").fetchone()
    outs = rg.replay(c, int(lo // B), int(hi // B))
    n = len(outs)
    ab = sum(1 for o in outs if o["abstain"])
    win = Counter(o["winner"] for o in outs if not o["abstain"])
    gewinner = sum(win.values())
    print("  replay: Fenster=%d enthalten=%.1f%% Gewinne=%d verteilt=%s" % (n, 100.0 * ab / n, gewinner, dict(win)))
    assert gewinner > 0, "Engine entscheidet nie (toter Eingang)"
    assert ab < n, "nur Enthaltung"
    assert max(win.values()) / gewinner <= 0.9, "Fixpunkt: eine Zelle gewinnt >90 %"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("t_"):
            fn()
            print("ok", name)
    print("ALLE GRUEN")
