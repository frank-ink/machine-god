"""Tests E5.01-E5.12 (Zielverfolgung, Reentry), Entwurf ChatGPT Runde 7. Synthetische Wegwerf-DB."""
import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import goal_competition as gc
import goal_genesis as gg
import goal_pursuit as gp
from test_goal import NOW, befund, evid, mk

A = lambda c, aid: c.execute("select * from f3_goal_attempt where attempt_id=?", (aid,)).fetchone()
COL = lambda c: [r[1] for r in c.execute("pragma table_info(f3_goal_attempt)")]
ROW = lambda c, aid: dict(zip(COL(c), A(c, aid)))


def one(n=5):
    c = mk(); befund(c, "a", n=n); gg.genesis(c, NOW)
    return c, c.execute("select goal_id from f3_goal").fetchone()[0]


def t_e501():
    c, g = one()
    pick, _ = gc.compete(c, NOW)
    a = gp.pursue(c, pick, NOW)
    assert a and pick == g and gp.pursue(c, pick, NOW) == a and c.execute("select count(*) from f3_goal_attempt").fetchone()[0] == 1
    r = ROW(c, a)
    assert r["goal_id"] == g and r["origin_event_id"].startswith("befund:") and json.loads(r["class_demand"])["turn_origin"] == "endogenous" and r["evaluator_version"] == gp.EVAL_VERSION


def t_e502():
    c, g = one()
    c.execute("update f3_goal set salience=0, expected_information_gain=0, estimated_resource_cost=1, fatigue=1, fatigue_ts=?", (NOW,)); c.commit()
    pick, _ = gc.compete(c, NOW)
    assert pick is None and gp.pursue(c, pick, NOW) is None and not c.execute("select 1 from sqlite_master where name='f3_goal_attempt'").fetchone()


def t_e503():
    c, g = one()
    a = gp.bind(c, g, NOW)
    r = ROW(c, a)
    assert r["evaluation_status"] is None and json.loads(r["prediction"])["expected_n"] == 5 and r["frozen_hash"] and r["observed_result"] is None
    c.execute("update f3_goal_attempt set prediction=? where attempt_id=?", (json.dumps({"metric": "count", "distance": "x", "expected_n": 99}), a)); c.commit()
    gp.process(c, a, NOW)
    r = ROW(c, a)
    assert r["evaluation_status"] == "UNVERIFIABLE" and "veraendert" in r["observed_result"]


def t_e504():
    c, g = one()
    a = gp.pursue(c, g, NOW)
    r = ROW(c, a)
    obs = json.loads(r["observed_result"])
    assert r["evaluation_status"] == "SATISFIED" and obs["n_obs"] == 5 and len(obs["sample_ids"]) == 5 and r["prediction_error"] == 0 and r["evidence_refs"]
    assert c.execute("select status from f3_goal where goal_id=?", (g,)).fetchone()[0] == "abgeschlossen" and json.loads(r["state_after_ref"])["status"] == "abgeschlossen"


def t_e505():
    c, g = one()
    a = gp.bind(c, g, NOW)
    evid(c, "a", 10); c.commit()  # Welt aendert sich nach der Prognose
    gp.process(c, a, NOW)
    r = ROW(c, a)
    b = c.execute("select kind,key from f3_endo_befund where key like 'versuch:%'").fetchone()
    assert r["evaluation_status"] == "PARTIAL" and r["prediction_error"] == 1.0 and b == ("luecke", "versuch:" + g) and r["reentry_event_id"]
    assert c.execute("select status from f3_goal where goal_id=?", (g,)).fetchone()[0] == "offen"


def t_e506():
    c, g = one()
    c.execute("update f3_goal set evidence_refs=?", (json.dumps([{"table": "gibtsnicht", "where": "1=1", "params": [], "n": 3}]),)); c.commit()
    a = gp.pursue(c, g, NOW)
    assert ROW(c, a)["evaluation_status"] == "UNVERIFIABLE" and c.execute("select status from f3_goal").fetchone()[0] == "offen"


def t_e507():
    c, g = one()
    a = gp.pursue(c, g, NOW)
    r1 = A(c, a); n1 = c.execute("select count(*) from f3_endo_befund where key like 'versuch:%'").fetchone()[0]
    gp.process(c, a, NOW + 600); gp.process(c, a, NOW + 900)
    assert A(c, a) == r1 and c.execute("select count(*) from f3_endo_befund where key like 'versuch:%'").fetchone()[0] == n1 == 1


def t_e508():
    c, g = one()
    evid(c, "a", 8); c.commit()  # Ausgangsreferenz (n=5) ist beim Binden schon veraltet
    a = gp.pursue(c, g, NOW)
    r = ROW(c, a)
    assert json.loads(r["state_before_ref"])["stale"] is True and r["evaluation_status"] == "PARTIAL" and c.execute("select status from f3_goal").fetchone()[0] == "offen"


def t_e509():
    p = tempfile.mktemp(suffix=".db")
    try:
        c = mk(p); befund(c, "a"); gg.genesis(c, NOW); g = c.execute("select goal_id from f3_goal").fetchone()[0]
        a = gp.bind(c, g, NOW); h = ROW(c, a)["frozen_hash"]; c.close()  # Absturz nach Prognose, vor Bearbeitung
        c2 = sqlite3.connect(p)
        assert gp.resume(c2, NOW + 60) == 1
        r = ROW(c2, a)
        assert r["frozen_hash"] == h and r["evaluation_status"] == "SATISFIED" and gp.resume(c2, NOW + 120) == 0
    finally:
        os.path.exists(p) and os.remove(p)


def t_e510():
    c, g = one()
    a = gp.bind(c, g, NOW)
    c.execute("insert into star_konfig values('frank3.kill','1')"); c.commit()
    assert gp.process(c, a, NOW) is None and gp.bind(c, g, NOW) is None and ROW(c, a)["evaluation_status"] is None


def t_e511():
    c, g = one()
    c.execute("update f3_goal set authority_scope='admin,exec'"); c.commit()
    a = gp.pursue(c, g, NOW)
    r = ROW(c, a)
    assert r["evaluation_status"] == "FAILED" and "authority_scope" in r["observed_result"] and c.execute("select count(*) from f3_endo_befund where key like 'versuch:%'").fetchone()[0] == 0
    c.set_authorizer(gp._auth)
    try:
        for sql in ("insert into ev(tag) values('x')", "delete from ev", "create table t(x)"):
            try:
                c.execute(sql); raise AssertionError("Schreibzugriff erlaubt: " + sql)
            except sqlite3.DatabaseError as e:
                assert "authorized" in str(e)
        assert c.execute("select count(*) from ev").fetchone()[0] == 5
    finally:
        c.set_authorizer(None)


def t_e512():
    """Kausaler Reentry: Versuch -> Befund -> Folgeziel -> Folgeziel nimmt am naechsten Wettbewerb teil, mit aufloesbarer Kette zurueck zum Versuch."""
    c = mk(); befund(c, "a", n=5); befund(c, "b", n=50); gg.genesis(c, NOW)
    pick, _ = gc.compete(c, NOW)
    a = gp.bind(c, pick, NOW)
    tag = json.loads(c.execute("select evidence_refs from f3_goal where goal_id=?", (pick,)).fetchone()[0])[0]["params"][0]
    evid(c, tag, 80); c.commit()  # Welt aendert sich nach der Prognose -> Prognosefehler
    gp.process(c, a, NOW)
    made = gg.genesis(c, NOW + 600)  # E3 liest den Reentry-Befund
    pick2, sc2 = gc.compete(c, NOW + 600)
    follow = c.execute("select goal_id,origin_event_id,evidence_refs,goal_statement from f3_goal where goal_id=?", (made[0],)).fetchone()
    bid = int(follow[1].split(":")[1])
    key = c.execute("select key from f3_endo_befund where id=?", (bid,)).fetchone()[0]
    ref = json.loads(follow[2])[0]
    chain = c.execute("select attempt_id from %s where %s" % (ref["table"], ref["where"]), tuple(ref["params"])).fetchone()[0]
    assert len(made) == 1 and made[0] in sc2 and made[0] != pick and key == "versuch:" + pick and chain == a and "PARTIAL" in follow[3]
    assert pick not in sc2 and c.execute("select count(*) from f3_goal_log where goal_id=? and event='kandidat_verworfen'", (pick,)).fetchone()[0] >= 1  # veraltetes Ursprungsziel scheidet aus


def t_e512b_gain():
    """Rueckwirkung auf E4: ein am Ziel gescheiterter Versuch (hier: Rechteabbruch) steht mit Ergebnis im naechsten Wettbewerb; der Ablauf (used_attempt) ist protokolliert."""
    c, g = one()
    c.execute("update f3_goal set authority_scope='admin'"); c.commit()
    a = gp.pursue(c, g, NOW)
    c.execute("update f3_goal set authority_scope='none'"); c.commit()
    pick, sc = gc.compete(c, NOW + 60)
    assert sc[g]["used_attempt"] == [a, "FAILED"]


if __name__ == "__main__":
    fails = 0
    for n, f in sorted(globals().items()):
        if n.startswith("t_e"):
            try:
                f(); print("ok  ", n)
            except Exception as e:
                import traceback; fails += 1; print("FAIL", n, repr(e)); traceback.print_exc(limit=2)
    print("ALLE GRUEN" if not fails else "%d FEHLER" % fails)
    sys.exit(1 if fails else 0)
