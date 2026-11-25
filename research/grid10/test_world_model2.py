"""Tests WM2.01-WM2.10 (Hypothesenraum, Projektion), Entwurf ChatGPT Runde 10. Synthetische Wegwerf-DB."""
import hashlib
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))
import endogenous
import goal_genesis as gg
import world_model as wm
import world_model2 as w2

B0, NOW = 6_000_000, 1_800_000_000.0
CH = list(wm.CH)


def mk():
    c = sqlite3.connect(":memory:")
    c.execute("create table star_konfig(schluessel text primary key, wert text)")
    for d in endogenous.DDL + wm.DDL:
        c.execute(d)
    return c


def win(c, b, p, x, ver=0, ch=None):
    """Window b: Forecast p, Observation x (Scalar for all channels, ch overrides individual channels of p)."""
    pr = {k: p for k in CH}; ob = {k: x for k in CH}
    for k, v in (ch or {}).items():
        pr[k] = v
    c.execute("insert into f3_wm_pred(bucket,model_version,pred,ref_pred,obs,brier,brier_ref,status,prospective) values(?,?,?,?,?,?,?,?,1)",
              (b, ver, json.dumps(pr), json.dumps(pr), json.dumps(ob), wm.brier(pr, ob), 0.0, "bewertet"))


def anlass(c, lo, hi, ver=0):
    n = c.execute("select count(*) from f3_wm_pred where bucket>=? and bucket<=? and model_version=?", (lo, hi, ver)).fetchone()[0]
    ref = {"table": "f3_wm_pred", "where": "status='bewertet' and model_version=%d and bucket>=%d and bucket<=%d" % (ver, lo, hi), "params": [], "n": n}
    c.execute("insert into f3_endo_befund(bucket,kind,statement,evidence_ref,key) values(?,?,?,?,?)", (int(NOW // 300), "contradiction", "wm", json.dumps(ref), "wm_prognosefehler"))
    c.commit()


def top(c):
    (aid,) = c.execute("select anlass_id from f3_wm2_anlass").fetchone()
    return w2.stand(c, aid)


def dump(c, t):
    return hashlib.sha256(json.dumps(c.execute("select * from %s order by rowid" % t).fetchall()).encode()).hexdigest()


def t_wm201_ausreisser_rauschen():
    c = mk()
    for i in range(12):
        win(c, B0 + i, 0.3, 0.3 if i not in (4, 9) else 1.0)  # zwei Ausreisser, sonst exakt
    anlass(c, B0, B0 + 11)
    assert w2.project(c, NOW) == 3
    s = top(c)
    assert s[0]["name"] == "NOISE" and s[0]["status"] == "leitend" and "conc_n" in s[0]["support"] and abs(sum(h["score"] for h in s) - 1) < 1e-9


def t_wm202_regime_gerichtet_und_anhaltend():
    c = mk()
    for i in range(12):
        win(c, B0 + i, 0.1, 1.0, ch={"fokus_app": 0.5})  # in allen Fenstern zu niedrig vorhergesagt
    for i in range(12, 16):
        win(c, B0 + i, 0.1, 1.0)  # Error persists after the trigger
    anlass(c, B0, B0 + 11); w2.project(c, NOW)
    s = top(c)
    assert s[0]["name"] == "REGIME" and "pers" in s[0]["support"] and s[0]["salience"] > 0.5


def t_wm203_luecken_stuetzen_sensor():
    c = mk()
    for i in range(18):
        if i % 3 != 2:
            win(c, B0 + i, 0.2, 0.2 if i % 2 else 0.6)  # jedes dritte Fenster fehlt (UNBEKANNT), Fehler wechselnd
    anlass(c, B0, B0 + 17); w2.project(c, NOW)
    s = {h["name"]: h for h in top(c)}
    assert "gap_n" in s["SENSOR"]["support"] and s["SENSOR"]["score"] > 0.3 and not s["NOISE"]["counter"] == ["pers"] * 5


def t_wm204_revisionen_unveraenderlich():
    c = mk()
    for i in range(12):
        win(c, B0 + i, 0.3, 0.3 if i != 5 else 1.0)
    anlass(c, B0, B0 + 11); w2.project(c, NOW)
    for sql in ("update f3_wm2_rev set score=1", "delete from f3_wm2_rev"):
        try:
            c.execute(sql); raise AssertionError("Aenderung erlaubt")
        except sqlite3.DatabaseError as e:
            assert "unveraenderlich" in str(e)
    assert c.execute("select count(*) from f3_wm2_rev").fetchone()[0] == 3


def t_wm205_idempotent_und_neue_evidenz_neue_revision():
    c = mk()
    for i in range(12):
        win(c, B0 + i, 0.3, 0.3 if i not in (2, 8) else 1.0)
    anlass(c, B0, B0 + 11)
    assert w2.project(c, NOW) == 3 and w2.project(c, NOW + 1) == 0
    for i in range(12, 16):
        win(c, B0 + i, 0.3, 0.3)  # Fehler klingt ab -> 'trans'
    assert w2.project(c, NOW + 2) == 3  # neue Evidenz (post) -> je Hypothese Revision 2
    rows = c.execute("select hyp_id,seq,rev_id,prev_hash from f3_wm2_rev order by hyp_id,seq").fetchall()
    by = {}
    for h, s, r, p in rows:
        by.setdefault(h, []).append((s, r, p))
    assert all([x[0] for x in v] == [1, 2] and v[1][2] == v[0][1] and v[0][2] == "" for v in by.values())
    assert w2.project(c, NOW + 3) == 0


def t_wm206_offener_widerspruch_befund():
    c = mk()
    for i in range(12):
        win(c, B0 + i, 0.3, 0.3 if i % 4 else 0.9)  # gemischtes Bild
    anlass(c, B0, B0 + 11); w2.project(c, NOW)
    s = top(c); close = s[0]["score"] - s[1]["score"] < w2.MARGIN
    b = w2.finding(c, NOW)
    assert (len(b) == 1) == close
    if b:
        assert b[0]["kind"] == "contradiction" and b[0]["key"].startswith("wm2_offen:") and endogenous.resolve(c, b[0]["ref"]) == (True, b[0]["ref"]["n"])
    # eindeutiger Fall -> kein Befund
    c2 = mk()
    for i in range(12):
        win(c2, B0 + i, 0.1, 1.0, ch={"fokus_app": 0.5})
    for i in range(12, 16):
        win(c2, B0 + i, 0.1, 1.0)
    anlass(c2, B0, B0 + 11); w2.project(c2, NOW)
    s2 = top(c2)
    assert (s2[0]["score"] - s2[1]["score"] >= w2.MARGIN) == (w2.finding(c2, NOW) == [])


def t_wm207_aus_und_kill():
    for k, v in (("frank3.wm2.mode", "off"), ("frank3.kill", "1")):
        c = mk()
        for i in range(12):
            win(c, B0 + i, 0.3, 1.0)
        anlass(c, B0, B0 + 11)
        c.execute("insert into star_konfig values(?,?)", (k, v)); c.commit()
        assert w2.project(c, NOW) == 0 and not c.execute("select 1 from sqlite_master where name='f3_wm2_rev'").fetchone() and w2.finding(c, NOW) == []


def t_wm208_wm1_unberuehrt():
    c = mk()
    for i in range(12):
        win(c, B0 + i, 0.3, 1.0 if i % 3 == 0 else 0.3)
    anlass(c, B0, B0 + 11)
    before = (dump(c, "f3_wm_pred"), dump(c, "f3_endo_befund"))
    w2.project(c, NOW); w2.finding(c, NOW)
    assert before == (dump(c, "f3_wm_pred"), dump(c, "f3_endo_befund"))


def t_wm209_ohne_anlass_oder_fenster_nichts():
    c = mk()
    assert w2.project(c, NOW) == 0 and w2.report(c)["anlaesse"] == 0 and w2.report(c)["revisionen"] == 0
    anlass(c, B0, B0 + 11)  # Befund ohne Fensterzeilen
    assert w2.project(c, NOW) == 0


def t_wm210_kette_befund_zu_ziel():
    """Offener WM2-Widerspruch fliesst durch E2 (Ledger) in E3 (Ziel) ohne Nutzerauftrag."""
    c = mk()
    for i in range(12):
        win(c, B0 + i, 0.3, 0.3 if i % 4 else 0.9)
    anlass(c, B0, B0 + 11); w2.project(c, NOW)
    # Force state: narrow margin, if the rule is unambiguous here, verify result honestly
    b = w2.finding(c, NOW)
    assert len(b) == 1  # deterministische Testdaten: knapper Abstand (REGIME vs NOISE)
    c.execute("insert into f3_endo_befund(bucket,kind,statement,evidence_ref,key) values(?,?,?,?,?)", (int(NOW // 300), b[0]["kind"], b[0]["statement"], json.dumps(b[0]["ref"]), b[0]["key"])); c.commit()
    made = gg.genesis(c, NOW)
    g = c.execute("select g.origin_event_id,g.authority_scope,b.key from f3_goal g join f3_endo_befund b on 'finding:'||b.id=g.origin_event_id where b.key like 'wm2_offen:%'").fetchall()
    assert len(made) == 2 and len(g) == 1 and g[0][1] == "none"  # Trigger finding (wm_prognosefehler) and WM2 contradiction each generate a target


if __name__ == "__main__":
    fails = 0
    for n, f in sorted(globals().items()):
        if n.startswith("t_wm2"):
            try:
                f(); print("ok  ", n)
            except Exception as e:
                import traceback; fails += 1; print("FAIL", n, repr(e)); traceback.print_exc(limit=3)
    print("ALLE GRUEN" if not fails else "%d FEHLER" % fails)
    sys.exit(1 if fails else 0)
