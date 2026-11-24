"""Tests E3.01-E3.10 (Zielgenese) und E4.01-E4.10 (Zielwettbewerb), Entwurf ChatGPT Runde 6. Synthetische Befunde in einer Wegwerf-DB, keine echte DB."""
import json
import math
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import endogen
import goal_competition as gc
import goal_genesis as gg

NOW = 1_800_000_000.0


def mk(path=":memory:"):
    c = sqlite3.connect(path)
    c.execute("create table if not exists star_konfig(schluessel text primary key, wert text)")
    c.execute("create table if not exists ev(id integer primary key, tag text)")
    for d in endogen.DDL:
        c.execute(d)
    return c


def evid(c, tag, n):
    have = c.execute("select count(*) from ev where tag=?", (tag,)).fetchone()[0]
    for _ in range(n - have):
        c.execute("insert into ev(tag) values(?)", (tag,))
    return {"table": "ev", "where": "tag=?", "params": [tag], "n": n}


def befund(c, key, kind="luecke", n=5, bucket=None, ref=None):
    ref = ref or evid(c, key, n)
    c.execute("insert into f3_endo_befund(bucket,kind,statement,evidence_ref,key) values(?,?,?,?,?)",
              (int(NOW // 300) if bucket is None else bucket, kind, "Befund %s (%d)" % (key, ref["n"]), json.dumps(ref), key))
    c.commit()


def goals(c):
    return c.execute("select * from f3_goal").fetchall()


def t_e301():
    c = mk(); befund(c, "a")
    m = gg.genesis(c, NOW)
    r = c.execute("select origin_event_id,origin_organ,evidence_refs,authority_scope,generation_method,goal_statement from f3_goal").fetchone()
    assert len(m) == 1 and r[0].startswith("befund:") and r[1] and json.loads(r[2])[0]["table"] == "ev" and r[3] == "none" and r[4] == "rule_template" and "Befund a" in r[5]


def t_e302():
    c = mk(); befund(c, "a", n=5)
    c.execute("delete from ev where id in (select id from ev limit 2)")  # Referenz liefert nur noch 3
    assert gg.genesis(c, NOW) == [] and not goals(c)
    assert c.execute("select event from f3_goal_log").fetchone()[0] == "verworfen_evidenz"


def t_e303():
    c = mk(); befund(c, "a", bucket=int((NOW - 7200) // 300))
    gg.genesis(c, NOW)
    r = c.execute("select last_review_at,motivation from f3_goal").fetchone()
    assert r[0] == NOW and "revalidiert" in r[1]
    c2 = mk(); befund(c2, "a"); gg.genesis(c2, NOW)
    assert c2.execute("select last_review_at from f3_goal").fetchone()[0] is None


def t_e304():
    c = mk(); befund(c, "a")
    gg.genesis(c, NOW)
    assert gg.genesis(c, NOW + 400) == [] and len(goals(c)) == 1


def t_e305():
    c = mk(); befund(c, "a"); befund(c, "b", n=9)
    m = gg.genesis(c, NOW)
    assert len(m) == 2 and len({g[0] for g in goals(c)}) == 2 and len({g[17] for g in goals(c)}) == 2


def t_e306():
    c = mk(); befund(c, "w", kind="widerspruch")
    gg.genesis(c, NOW)
    assert c.execute("select status from f3_goal").fetchone()[0] == "offen_unsicher"  # bleibt unsicher, wird nicht aufgeloest


def t_e307():
    c = mk(); befund(c, "kein_ziel", ref={"table": "ev", "where": "1=1", "params": [], "n": 0})
    assert gg.genesis(c, NOW) == [] and not goals(c)


def t_e308():
    c = mk(); befund(c, "a")
    gg.genesis(c, NOW, requested_scope="admin,exec,network")
    assert c.execute("select authority_scope from f3_goal").fetchone()[0] == "none"


def t_e309():
    p = tempfile.mktemp(suffix=".db")
    try:
        c = mk(p); befund(c, "a"); gg.genesis(c, NOW); a = goals(c); c.close()
        c2 = sqlite3.connect(p); b = c2.execute("select * from f3_goal").fetchall()
        assert a == b and b[0][2].startswith("befund:") and gg.genesis(c2, NOW + 60) == []  # Identitaet + Herkunft bleiben, kein Duplikat nach Neustart
    finally:
        os.path.exists(p) and os.remove(p)


def t_e310():
    c = mk(); befund(c, "a")
    c.execute("insert into star_konfig values('frank3.kill','1')"); c.commit()
    assert gg.genesis(c, NOW) == [] and gc.compete(c, NOW)[0] is None
    assert not c.execute("select 1 from sqlite_master where name='f3_goal'").fetchone()


def two(c, na=5, nb=50):
    befund(c, "a", n=na); befund(c, "b", n=nb); gg.genesis(c, NOW)


def t_e401():
    c = mk(); two(c)
    pick, sc = gc.compete(c, NOW)
    assert pick and sc[pick]["score"] == max(s["score"] for s in sc.values()) and c.execute("select salience from f3_goal where goal_id=?", (pick,)).fetchone()[0] > 0.5


def t_e402():
    c = mk(); befund(c, "a", n=100); gg.genesis(c, NOW)
    fs = []
    for _ in range(4):
        gc.compete(c, NOW)
        fs.append(c.execute("select fatigue from f3_goal").fetchone()[0])
    assert fs == sorted(fs) and len(set(fs)) == 4 and fs[0] == 0.25 and all(f < 1 for f in fs)


def t_e403():
    c = mk(); befund(c, "a"); gg.genesis(c, NOW)
    c.execute("update f3_goal set fatigue=0.8, fatigue_ts=?", (NOW,)); c.commit()
    gc.compete(c, NOW + 3 * gc.TAU)  # wird dabei einmal ausgewaehlt: f' = f + 0.25(1-f) -> Zerfallswert zurueckrechnen
    pre = (c.execute("select fatigue from f3_goal").fetchone()[0] - 0.25) / 0.75
    assert abs(pre / 0.8 - math.exp(-3)) < 1e-6 and 0.049 < pre / 0.8 < 0.051


def mk_copy(c):
    d = sqlite3.connect(":memory:"); c.backup(d); return d


def t_e404():
    c = mk(); two(c, 7, 7)
    ids = sorted(g[0] for g in goals(c))
    r = {gc.compete(mk_copy(c), NOW)[0] for _ in range(3)}
    assert len(ids) == 2 and r == {ids[0]}


def t_e405():
    c = mk(); befund(c, "a"); gg.genesis(c, NOW)
    c.execute("update f3_goal set salience=0, expected_information_gain=0, estimated_resource_cost=1, fatigue=1, fatigue_ts=?", (NOW,)); c.commit()
    pick, sc = gc.compete(c, NOW)
    assert pick is None and sc and c.execute("select abstain from f3_goal_comp_log order by id desc limit 1").fetchone()[0] == 1


def t_e406():
    c = mk(); two(c)
    c.execute("delete from ev where tag='b'"); c.commit()
    pick, sc = gc.compete(c, NOW)
    assert len(sc) == 1 and pick in sc and c.execute("select count(*) from f3_goal_log where event='kandidat_verworfen'").fetchone()[0] == 1


def t_e407():
    c = mk(); befund(c, "a", n=5); gg.genesis(c, NOW)
    gc.complete(c, goals(c)[0][0], NOW)
    assert gc.compete(c, NOW + 60)[0] is None and gg.genesis(c, NOW + 400) == []  # gleicher Befund, gleiche Evidenz -> kein neues Ziel
    c.execute("delete from f3_endo_befund"); befund(c, "a", ref=evid(c, "a", 8))
    assert len(gg.genesis(c, NOW + 800)) == 1  # neue Evidenz -> neues Ziel erlaubt


def t_e408():
    c = mk(); t = NOW
    for i in range(1000):
        if i % 3 == 0:
            befund(c, "k%d" % (i % 60), n=2 + i % 7, bucket=int(t // 300))
        gg.genesis(c, t); gc.compete(c, t); t += 300
        assert c.execute("select count(*) from f3_goal where status in ('offen','offen_unsicher')").fetchone()[0] <= gg.MAX_OPEN


def t_e409():
    p = tempfile.mktemp(suffix=".db")
    try:
        c = mk(p); befund(c, "a"); gg.genesis(c, NOW); gc.compete(c, NOW); a = c.execute("select goal_id,fatigue,selections from f3_goal").fetchone(); c.close()
        c2 = sqlite3.connect(p); b = c2.execute("select goal_id,fatigue,selections from f3_goal").fetchone()
        assert a == b and b[1] == 0.25 and b[2] == 1
    finally:
        os.path.exists(p) and os.remove(p)


def t_e410():
    c = mk(); befund(c, "a"); gg.genesis(c, NOW)
    tabs = [r[0] for r in c.execute("select name from sqlite_master where type='table' and name<>'sqlite_sequence'").fetchall()]
    before = {t: c.execute("select count(*) from %s" % t).fetchone()[0] for t in tabs}
    pick, _ = gc.compete(c, NOW)
    after = {t: c.execute("select count(*) from %s" % t).fetchone()[0] for t in before}
    changed = {t for t in before if before[t] != after[t]}
    assert isinstance(pick, str) and changed <= {"f3_goal_comp_log"} and not hasattr(gc, "execute") and not hasattr(gc, "run")


def t_e402b_selbstbegrenzung():
    """Befund (ehrlich festgehalten): bei kleiner Evidenz begrenzen Ermuedung + Neuheitsverlust die Auswahl von selbst (2 Treffer, dann ABSTAIN)."""
    c = mk(); befund(c, "a", n=5); gg.genesis(c, NOW)
    picks = [gc.compete(c, NOW)[0] for _ in range(4)]
    assert picks[0] and picks[1] and picks[2] is None and picks[3] is None


if __name__ == "__main__":
    fails = 0
    for n, f in sorted(globals().items()):
        if n.startswith("t_e"):
            try:
                f(); print("ok  ", n)
            except Exception as e:
                fails += 1; print("FAIL", n, repr(e))
    print("ALLE GRUEN" if not fails else "%d FEHLER" % fails)
    sys.exit(1 if fails else 0)
