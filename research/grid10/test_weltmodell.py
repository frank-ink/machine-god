"""Tests WM1.01-WM1.14 (Prognose-Ledger, Konflikt, Revision, Regelkreis), Entwurf ChatGPT Runde 8. Synthetische Wegwerf-DB, keine echte DB."""
import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import endogen
import goal_competition as gc
import goal_genesis as gg
import goal_pursuit as gp
import weltmodell as wm

B0 = 6_000_000  # 1_800_000_000 / 300
ALL = list(wm.CH)


def mk(path=":memory:"):
    c = sqlite3.connect(path)
    c.execute("create table if not exists star_konfig(schluessel text primary key, wert text)")
    c.execute("create table if not exists f2_retina_geschehen(id integer primary key, ts real, art text)")
    c.execute("create table if not exists f2_retina_sinne(organ_id text primary key, status text, ts real)")
    for d in endogen.DDL:
        c.execute(d)
    return c


def alive(c, b, ok=True):
    c.execute("insert or replace into f2_retina_sinne values('fenster1',?,?)", ("aktiv" if ok else "aus", b * 300 + 150.0))


def ev(c, b, arts):
    for a in arts:
        c.execute("insert into f2_retina_geschehen(ts,art) values(?,?)", (b * 300 + 100.0, a))


def tick(c, b, arts=(), ok=True, with_endo=False):
    """Fenster b: Ereignisse, Sensor-Stichprobe, Hook-Lauf mitten im Fenster."""
    ev(c, b, arts); alive(c, b, ok)
    n = wm.step(c, b * 300 + 200.0)
    if with_endo:
        endogen.step(c, b * 300 + 210.0)
    return n


def state(c):
    return json.loads(c.execute("select j from f3_wm_state").fetchone()[0])


def setp(c, p, alpha=None):
    st = state(c); st["p"] = {k: p for k in ALL}
    if alpha:
        st["alpha"] = alpha
    c.execute("update f3_wm_state set j=?", (json.dumps(st),)); c.commit()


def flip(c, start, n_calm=30, n_hot=16, with_endo=False):
    """ruhig (nichts) -> alle Kanaele jedes Fenster. -> naechstes freies Fenster."""
    b = start
    for _ in range(n_calm):
        tick(c, b, with_endo=with_endo); b += 1
    for _ in range(n_hot):
        tick(c, b, ALL, with_endo=with_endo); b += 1
    return b


def t_wm101_start_und_einfrieren():
    c = mk(); tick(c, B0)
    st = state(c)
    r = c.execute("select bucket,model_version,prospective,created_at,frozen_hash,status,state_digest,last_observed_window,horizon_windows from f3_wm_pred").fetchall()
    assert st["version"] == 0 and st["alpha"] == 0.10 and len(r) == 1 and r[0][0] == B0 + 1 and r[0][2] == 1 and r[0][3] < (B0 + 1) * 300 and r[0][5] == "offen" and r[0][4] and r[0][6]
    assert r[0][7] is None and r[0][8] is None  # noch kein bewertetes Fenster beobachtet: Horizont unbekannt, nicht erfunden
    h = r[0][4]
    tick(c, B0)  # gleicher Takt noch einmal: nichts wird ueberschrieben
    assert c.execute("select count(*) from f3_wm_pred").fetchone()[0] == 1 and c.execute("select frozen_hash from f3_wm_pred").fetchone()[0] == h


def t_wm102_brier_von_hand():
    c = mk(); tick(c, B0); setp(c, 0.2); c.execute("delete from f3_wm_pred"); tick(c, B0)  # Prognose fuer B0+1 mit p=0.2 neu einfrieren (Takt im selben Fenster)
    tick(c, B0 + 1, ["fokus_app"]); tick(c, B0 + 2)
    r = c.execute("select status,brier,brier_ref,coverage from f3_wm_pred where bucket=?", (B0 + 1,)).fetchone()
    assert r[0] == "bewertet" and abs(r[1] - (0.64 + 4 * 0.04) / 5) < 1e-9 and abs(r[2] - 1 / 5) < 1e-9 and r[3] == "ok"  # Referenz: W0-Basisraten 0 -> fokus_app-Fehler 1


def t_wm103_unbekannt_ist_nicht_null():
    c = mk(); tick(c, B0); setp(c, 0.2); c.execute("delete from f3_wm_pred"); tick(c, B0)
    # Fenster B0+1 ohne Hook-Lauf: keine Sensor-Stichprobe
    ev(c, B0 + 1, ["fokus_app"]); alive(c, B0 + 2); wm.step(c, (B0 + 2) * 300 + 200.0)
    r = c.execute("select status,brier,obs from f3_wm_pred where bucket=?", (B0 + 1,)).fetchone()
    assert r == ("unbekannt", None, None)
    assert abs(state(c)["p"]["fokus_app"] - 0.18) < 1e-12  # nur Fenster B0 (ok, x=0) zaehlt; B0+1 (unbekannt) NICHT als 0 gezaehlt


def t_wm104_sensor_ausgefallen():
    c = mk(); tick(c, B0); tick(c, B0 + 1, ok=False); tick(c, B0 + 2)
    r = c.execute("select status,coverage from f3_wm_pred where bucket=?", (B0 + 1,)).fetchone()
    assert r == ("unbekannt", "ausgefallen")


def t_wm105_kein_konflikt_bei_ruhe_und_zu_wenig_daten():
    c = mk(); b = B0
    for _ in range(40):
        tick(c, b); b += 1
    assert wm.befund(c) == [] and wm.report(c)["brier_model"] == 0
    c2 = mk(); b = B0
    for _ in range(5):
        tick(c2, b, ALL); b += 1
    assert wm.befund(c2) == []  # weniger als 12 bewertete Fenster -> Unsicherheit bleibt


def until_conflict(c, start=B0, n_calm=30, with_endo=False):
    """ruhig, dann Regimewechsel (alle Kanaele jedes Fenster) bis der Konflikt erstmals sichtbar wird. -> (naechstes Fenster, Befund)."""
    b = start
    for _ in range(n_calm):
        tick(c, b, with_endo=with_endo); b += 1
    for _ in range(40):
        tick(c, b, ALL, with_endo=with_endo); b += 1
        f = wm.befund(c)
        if f:
            return b, f
    raise AssertionError("kein Konflikt")


def t_wm106_konflikt_und_unveraenderliche_evidenz():
    c = mk(); b, f = until_conflict(c)
    assert len(f) == 1 and f[0]["kind"] == "widerspruch" and f[0]["key"] == "wm_prognosefehler" and f[0]["ref"]["n"] == 12
    ok, n = endogen.resolve(c, f[0]["ref"]); assert ok and n == 12
    for _ in range(10):
        tick(c, b, ALL); b += 1
    assert endogen.resolve(c, f[0]["ref"])[0]  # spaetere Fenster entwerten die Evidenz nicht


def t_wm107_revision_persistent_und_naechste_prognose():
    c = mk(); b, f = until_conflict(c)
    ref = f[0]["ref"]
    old = c.execute("select bucket,model_version,alpha from f3_wm_pred where status='bewertet'").fetchall()
    v = wm.revise(c, ref, "a1", b * 300 + 220.0)
    st = state(c)
    nxt = c.execute("select model_version,alpha,status from f3_wm_pred where bucket>? ", (b,)).fetchall()
    rev = c.execute("select decision,alpha_from,alpha_to,brier_before,brier_after,from_version,to_version from f3_wm_rev").fetchall()
    assert v == 1 and st["version"] == 1 and st["alpha"] > 0.10 and rev[0][0] == "revidiert" and rev[0][4] < 0.9 * rev[0][3] and rev[0][5:] == (0, 1)
    assert nxt == [(1, st["alpha"], "offen")]  # die naechste noch nicht begonnene Prognose nutzt W1
    assert old == c.execute("select bucket,model_version,alpha from f3_wm_pred where status='bewertet'").fetchall()  # Vergangenes bleibt unveraendert
    assert wm.befund(c) == []  # Konflikt zaehlt nur Fenster unter der aktuellen Version (12 neue noetig)


def t_wm108_keine_aenderung_ohne_nachweis():
    c = mk(); b = B0
    for _ in range(30):
        tick(c, b); b += 1
    ref = {"table": "f3_wm_pred", "where": "status='bewertet' and bucket>=%d and bucket<=%d" % (B0 + 5, B0 + 16), "params": [], "n": 12}
    assert endogen.resolve(c, ref)[0]
    v = wm.revise(c, ref, "a2", b * 300.0)
    assert v == 0 and state(c)["alpha"] == 0.10 and c.execute("select decision from f3_wm_rev").fetchone()[0] == "keine_aenderung"


def t_wm109_revision_idempotent():
    c = mk(); b, f = until_conflict(c); ref = f[0]["ref"]
    wm.revise(c, ref, "a1", b * 300 + 220.0); wm.revise(c, ref, "a1", b * 300 + 230.0)
    assert c.execute("select count(*) from f3_wm_rev").fetchone()[0] == 1 and state(c)["version"] == 1


def t_wm110_neustart():
    p = tempfile.mktemp(suffix=".db")
    try:
        c = mk(p); b, f = until_conflict(c); wm.revise(c, f[0]["ref"], "a1", b * 300 + 220.0); c.close()
        c2 = sqlite3.connect(p); tick(c2, b + 2, ALL)
        st = state(c2)
        assert st["version"] == 1 and st["alpha"] > 0.10 and c2.execute("select model_version from f3_wm_pred where bucket=?", (b + 3,)).fetchone()[0] == 1
    finally:
        os.path.exists(p) and os.remove(p)


def t_wm111_kill_und_schalter():
    c = mk(); c.execute("insert into star_konfig values('frank3.kill','1')"); c.commit()
    assert wm.step(c, B0 * 300 + 10.0) == 0 and not c.execute("select 1 from sqlite_master where name like 'f3_wm_%'").fetchone()
    c2 = mk(); c2.execute("insert into star_konfig values(?,?)", (wm.MODE_KEY, "off")); c2.commit()
    assert wm.step(c2, B0 * 300 + 10.0) == 0 and not c2.execute("select 1 from sqlite_master where name like 'f3_wm_%'").fetchone()


def t_wm112_schreibt_nur_eigene_tabellen():
    c = mk(); ev(c, B0, ["fokus_app"]); c.commit()
    tabs = [r[0] for r in c.execute("select name from sqlite_master where type='table' and name not like 'f3_wm_%' and name<>'sqlite_sequence'")]
    snap = lambda: {t: c.execute("select * from %s" % t).fetchall() for t in tabs}
    before = snap()
    tick(c, B0); tick(c, B0 + 1)
    after = snap()
    assert {t for t in tabs if before[t] != after[t]} == {"f2_retina_sinne"}  # nur die Test-Eingabe (Sensor-Stichprobe); wm selbst schreibt dort nichts
    assert c.execute("select count(*) from f3_endo_befund").fetchone()[0] == 0 and not c.execute("select 1 from sqlite_master where name='f3_goal'").fetchone()


def t_wm113_baseline_aus_historie():
    c = mk()
    for b in range(B0 - 100, B0 - 50):
        ev(c, b, ["person_kommt"] if b % 2 == 0 else [])
    c.commit()
    p0, span = wm.baseline(c)
    assert span == 49
    assert abs(p0["person_kommt"] - 25 / span) < 1e-3 and p0["fokus_app"] == 0


def t_wm115_pflichtfelder_horizont_persistenz():
    c = mk(); tick(c, B0, ["fokus_app"]); tick(c, B0 + 1, ["person_kommt"]); tick(c, B0 + 2)
    r = c.execute("select last_observed_window,horizon_windows,created_at,pers_pred,state_digest,model_version from f3_wm_pred where bucket=?", (B0 + 3,)).fetchone()
    assert r[0] == B0 + 1 and r[1] == 2 and r[2] < (B0 + 3) * 300 and r[4] and r[5] == 0
    assert json.loads(r[3]) == {"fokus_app": 0, "objekt_neu": 0, "objekt_weg": 0, "person_geht": 0, "person_kommt": 1}  # Persistenz = letztes bewertetes Fenster, gleicher Stand wie Modell und Referenz


def t_wm116_revision_ueberschreibt_nicht():
    c = mk(); b, f = until_conflict(c)
    tick(c, b)  # im aktuellen Fenster entsteht die v0-Prognose fuer b+1
    old = c.execute("select * from f3_wm_pred where bucket=? and model_version=0", (b + 1,)).fetchone()
    assert old
    wm.revise(c, f[0]["ref"], "a1", b * 300 + 250.0)
    rows = c.execute("select model_version,frozen_hash,alpha from f3_wm_pred where bucket=? order by model_version", (b + 1,)).fetchall()
    assert [r[0] for r in rows] == [0, 1] and rows[0][1] == old[10] and c.execute("select * from f3_wm_pred where bucket=? and model_version=0", (b + 1,)).fetchone() == old and rows[1][2] > 0.10
    tick(c, b + 1, ALL); tick(c, b + 2, ALL)  # beide werden unter ihrer eigenen Version bewertet
    st = c.execute("select model_version,status,brier from f3_wm_pred where bucket=? order by model_version", (b + 1,)).fetchall()
    assert [(v, s_) for v, s_, _ in st] == [(0, "bewertet"), (1, "bewertet")]
    assert st[0][2] == st[1][2]  # Uebergangsfenster: gleicher Zustand p, also gleiche Prognose -> gleicher Fehler; die Versionen unterscheiden sich erst ab dem Folgefenster (ehrlich: dort kein v0-Vergleich)
    assert wm.report(c, 1)["n"] == 1 and wm.report(c)["n"] == wm.report(c, 0)["n"] + 1


def t_wm117_persistenz_brier_von_hand():
    c = mk(); tick(c, B0); tick(c, B0 + 1, ["fokus_app"]); tick(c, B0 + 2, ["fokus_app"]); tick(c, B0 + 3)
    tick(c, B0 + 4)
    r = c.execute("select brier_pers,pers_pred,obs from f3_wm_pred where bucket=?", (B0 + 3,)).fetchone()
    assert r and json.loads(r[1])["fokus_app"] == 1 and json.loads(r[2])["fokus_app"] == 0 and abs(r[0] - 1 / 5) < 1e-12  # Persistenz sagte fokus_app voraus, es kam nicht


def t_wm118_sensorabdeckung_befund():
    c = mk(); tick(c, B0)
    for b in range(B0 + 1, B0 + 120):
        tick(c, b) if b % 3 == 0 else None
    now = (B0 + 120) * 300 + 10.0
    assert wm.sensor_befund(c, now) == []  # Anlauf: weniger als 288 Fenster seit Start -> kein Befund
    for b in range(B0 + 120, B0 + 330):
        tick(c, b) if b % 3 == 0 else None
    now = (B0 + 330) * 300 + 10.0
    f = wm.sensor_befund(c, now)
    cv = wm.coverage(c, now)
    assert len(f) == 1 and f[0]["key"] == "wm_sensorabdeckung" and f[0]["kind"] == "luecke" and f[0]["ref"]["cause"] == "SCHEDULER_INACTIVE" and 0.30 < cv["C"] < 0.36 and not cv["anlauf"]
    assert endogen.resolve(c, f[0]["ref"])[0] and cv["keine_zeile"] > cv["ausgefallen"] == 0


def t_wm119_abdeckung_gut_oder_ausgefallen():
    c = mk(); tick(c, B0)
    for b in range(B0 + 1, B0 + 330):
        tick(c, b)
    assert wm.sensor_befund(c, (B0 + 330) * 300 + 10.0) == []  # Abdeckung 100 % -> kein Befund
    c2 = mk(); tick(c2, B0)
    for b in range(B0 + 1, B0 + 330):
        tick(c2, b, ok=(b % 5 == 0))
    f = wm.sensor_befund(c2, (B0 + 330) * 300 + 10.0)
    assert f and f[0]["ref"]["cause"] == "SENSOR_UNAVAILABLE"


def t_wm120_mindestabstand_24h_und_anfrage():
    c = mk(); tick(c, B0)
    for b in range(B0 + 1, B0 + 330):
        tick(c, b) if b % 3 == 0 else None
    now = (B0 + 330) * 300 + 10.0
    endogen.step(c, now); endogen.step(c, now + 600)
    n1 = c.execute("select count(*) from f3_endo_befund where key='wm_sensorabdeckung'").fetchone()[0]
    endogen.step(c, now + 3000)
    assert n1 == 1 and c.execute("select count(*) from f3_endo_befund where key='wm_sensorabdeckung'").fetchone()[0] == 1  # innerhalb 24 h kein zweiter identischer Befund
    made = gg.genesis(c, now + 700)
    assert len(made) == 1 and c.execute("select goal_statement from f3_goal").fetchone()[0].startswith("Wissensluecke klaeren: Sensorabdeckung")
    pick, _ = gc.compete(c, now + 701); a = gp.pursue(c, pick, now + 702)
    assert wm.on_pursuit(c, pick, a, now + 703) == "anfrage" and wm.on_pursuit(c, pick, a, now + 704) == "anfrage"
    r = c.execute("select count(*),kind,text,status from f3_wm_anfrage").fetchone()
    assert r[0] == 1 and r[1] == "sensor" and "SCHEDULER_INACTIVE" in r[2] and "systemd-User-Timer" in r[2] and "NICHT ausgefuehrt" in r[2] and r[3] == "offen"


def t_wm114_regelkreis_ohne_nutzerauftrag():
    """W0 -> P0 -> E1 -> unabhaengiger Fehler -> E2-Befund -> E3-Ziel -> E4-Auswahl -> E5-Untersuchung -> W1 -> naechste Prognose nutzt W1 -> Neustart."""
    p = tempfile.mktemp(suffix=".db")
    try:
        c = mk(p); b, _f = until_conflict(c, with_endo=True)
        bf = c.execute("select id,kind,key from f3_endo_befund where key='wm_prognosefehler'").fetchall()
        assert len(bf) >= 1 and bf[0][1] == "widerspruch"
        made = gg.genesis(c, b * 300 + 215.0)
        g = [r for r in c.execute("select goal_id,origin_event_id,authority_scope,evidence_refs from f3_goal")]
        assert len(made) == 1 and g[0][2] == "none" and g[0][1].startswith("befund:") and json.loads(g[0][3])[0]["table"] == "f3_wm_pred"
        pick, _ = gc.compete(c, b * 300 + 216.0)
        assert pick == made[0]
        a = gp.pursue(c, pick, b * 300 + 217.0)
        assert c.execute("select evaluation_status from f3_goal_attempt where attempt_id=?", (a,)).fetchone()[0] in ("SATISFIED", "PARTIAL")
        assert state(c)["version"] == 0 and wm.on_pursuit(c, pick, a, b * 300 + 218.0) == 1
        assert c.execute("select decision,attempt_id from f3_wm_rev").fetchone() == ("revidiert", a)
        assert c.execute("select model_version from f3_wm_pred where bucket=?", (b + 1,)).fetchone()[0] == 1 or c.execute("select model_version from f3_wm_pred where bucket>? and status='offen'", (b,)).fetchone()[0] == 1
        c.close()
        c2 = sqlite3.connect(p); tick(c2, b + 3, ALL)
        assert state(c2)["version"] == 1 and c2.execute("select count(*) from f3_goal_attempt").fetchone()[0] == 1 and c2.execute("select model_version from f3_wm_pred where bucket=?", (b + 4,)).fetchone()[0] == 1
    finally:
        os.path.exists(p) and os.remove(p)


if __name__ == "__main__":
    fails = 0
    for n, f in sorted(globals().items()):
        if n.startswith("t_wm"):
            try:
                f(); print("ok  ", n)
            except Exception as e:
                import traceback; fails += 1; print("FAIL", n, repr(e)); traceback.print_exc(limit=3)
    print("ALLE GRUEN" if not fails else "%d FEHLER" % fails)
    sys.exit(1 if fails else 0)
