"""Test-Tor E1 Puls + E2 Beobachtung (Shadow). Lauf: python3 -I test_endogen.py (Exit 0 = gruen)."""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import endogen as E

B = E.BUCKET_S


def _db(goal_open=False):
    c = sqlite3.connect(":memory:")
    c.execute("create table star_konfig(schluessel text primary key, wert text)")
    c.execute("create table omega_goal(id text, goal text, status text)")
    if goal_open:
        c.execute("insert into omega_goal values('g1','x','open')")
    c.execute("create table f3_class_demand_log(id integer primary key, ts real, evaluation_status text)")
    c.execute("create table f3_class_demand_v2_log(id integer primary key, abstain integer)")
    c.execute("create table f3_retina_thal_log(bucket integer primary key, n_events integer, relay text, burst text)")
    return c


def t_puls_100_takte_keine_doppelverarbeitung():
    c, total = _db(), 0
    for i in range(100):
        now = (1000 + i) * B + 10
        total += E.step(c, now)
        total += E.step(c, now + 1)  # gleicher Takt nochmal: nichts
    rows = c.execute("select count(*), count(distinct bucket), count(distinct event_id) from f3_endo_puls_log").fetchone()
    assert rows[0] == rows[1] == rows[2] and total == rows[0] and 90 <= rows[0] <= 100, (rows, total)


def t_nachholen_gedeckelt():
    c = _db()
    E.step(c, 1000 * B + 1)
    assert E.step(c, 5000 * B + 1) == E.MAX_CATCHUP  # lange Pause: nur begrenzt nachgeholt


def t_kill_und_schalter():
    c = _db()
    c.execute("insert into star_konfig values('frank3.endo.mode','off')")
    assert E.step(c, 1000 * B) == 0
    c.execute("update star_konfig set wert='shadow' where schluessel='frank3.endo.mode'")
    c.execute("insert into star_konfig values('frank3.kill','1')")
    assert E.step(c, 1000 * B) == 0
    assert c.execute("select count(*) from sqlite_master where name='f3_endo_puls_log'").fetchone() == (0,)


def t_befunde_haben_aufloesbare_evidenz_und_zustaende_unterscheiden_sich():
    c = _db()
    c.execute("insert into f3_class_demand_log values(1, 1.0, 'pending')")  # uralt, unbewertet
    c.execute("insert into f3_class_demand_v2_log values(1,1)")
    now = 5000 * B + 10
    E.step(c, now)
    E.step(c, now + B)
    keys1 = {r[0] for r in c.execute("select key from f3_endo_befund")}
    assert keys1 == {"offene_bewertung", "abstain_v2", "kein_ziel"}, keys1
    import json
    for kind, ref in c.execute("select kind, evidence_ref from f3_endo_befund"):
        ok, n = E.resolve(c, json.loads(ref))
        assert ok and n >= 0 and kind in ("luecke", "widerspruch")
    c2 = _db(goal_open=True)  # anderer Zustand -> anderer Befundsatz
    E.step(c2, now)
    E.step(c2, now + B)
    assert {r[0] for r in c2.execute("select key from f3_endo_befund")} == set()
    c.execute("update f3_class_demand_log set evaluation_status='done'")  # Referenz wird ungueltig, wenn die Welt sich aendert
    ref = json.loads(c.execute("select evidence_ref from f3_endo_befund where key='offene_bewertung'").fetchone()[0])
    assert E.resolve(c, ref)[0] is False


def t_gate_durchsichtig_nur_mit_genug_daten():
    c = _db(goal_open=True)
    for b in range(20):
        c.execute("insert into f3_retina_thal_log values(?,?,?,?)", (b, 3, '["fokus_app"]', "[]"))
    ks = {f["key"] for f in E.observe(c, 1e9)}
    assert "gate_durchsichtig" in ks
    c.execute("delete from f3_retina_thal_log where bucket>=5")
    assert "gate_durchsichtig" not in {f["key"] for f in E.observe(c, 1e9)}


def t_schreibt_keine_fremden_tabellen():
    c = _db()
    before = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
    E.step(c, 1000 * B + 5)
    E.step(c, 1002 * B + 5)
    new = {r[0] for r in c.execute("select name from sqlite_master where type='table'")} - before
    assert new <= {"f3_endo_puls_log", "f3_endo_befund", "sqlite_sequence"} and {"f3_endo_puls_log", "f3_endo_befund"} <= new, new


def t_evidenz_ist_unveraenderlicher_schnappschuss():
    """Append-only-Ledger: neue Zeilen duerfen einen frueheren Befund nicht entwerten (sonst sterben Ziele an jedem Zuwachs)."""
    c = _db()
    c.execute("create table if not exists f3_class_demand_v2_log(id integer primary key, abstain integer)")
    for _ in range(4):
        c.execute("insert into f3_class_demand_v2_log(abstain) values(1)")
    f = [x for x in E.observe(c, 1000 * B) if x["key"] == "abstain_v2"][0]
    for _ in range(3):
        c.execute("insert into f3_class_demand_v2_log(abstain) values(1)")
    assert E.resolve(c, f["ref"]) == (True, 4) and f["ref"]["n"] == 4


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("t_"):
            fn()
            print("ok", name)
    print("ALLE GRUEN")
