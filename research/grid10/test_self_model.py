"""Tests SM.01-SM.10 (SELF_MODEL_V1). Synthetische Wegwerf-DB, Sonden ersetzbar."""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))
import self_model as sm
import world_model as wm

NOW = 1_800_000_000.0


def mk():
    c = sqlite3.connect(":memory:")
    c.execute("create table star_konfig(schluessel text primary key, wert text)")
    return c


def caps(state):
    return {"a": ("Faehigkeit A", lambda conn, now: (state["a"], {"x": state.get("x", 1)}))}


def t_sm01_revision_nur_bei_aenderung():
    c = mk(); st = {"a": "VERIFIED"}
    assert sm.project(c, NOW, caps(st)) == 1 and sm.project(c, NOW + 1, caps(st)) == 0
    st["a"] = "FAILED"
    assert sm.project(c, NOW + 2, caps(st)) == 1 and [r[1] for r in sm.history(c, "a")] == ["VERIFIED", "FAILED"]
    st["x"] = 2
    assert sm.project(c, NOW + 3, caps(st)) == 1  # gleiche Statusart, neue Evidenz


def t_sm02_unveraenderlich_und_kette():
    c = mk(); st = {"a": "VERIFIED"}; sm.project(c, NOW, caps(st)); st["a"] = "FAILED"; sm.project(c, NOW, caps(st))
    for sql in ("update f3_self_rev set status='VERIFIED'", "delete from f3_self_rev"):
        try:
            c.execute(sql); raise AssertionError("erlaubt")
        except sqlite3.DatabaseError as e:
            assert "unveraenderlich" in str(e)
    r = c.execute("select seq,rev_id,prev_hash from f3_self_rev order by seq").fetchall()
    assert r[0][2] == "" and r[1][2] == r[0][1]


def t_sm03_widerspruch_nur_nach_verifiziert():
    c = mk(); st = {"a": "FAILED"}; sm.project(c, NOW, caps(st))
    assert sm.finding(c) == []  # never verified: no contradiction, only deficiency
    st["a"] = "VERIFIED"; sm.project(c, NOW + 1, caps(st)); assert sm.finding(c) == []
    st["a"] = "FAILED"; sm.project(c, NOW + 2, caps(st))
    b = sm.finding(c)
    assert len(b) == 1 and b[0]["key"] == "self_lost:a" and b[0]["ref"]["n"] == 3
    import endogenous
    assert endogenous.resolve(c, b[0]["ref"]) == (True, 3)
    st["a"] = "VERIFIED"; sm.project(c, NOW + 3, caps(st)); assert sm.finding(c) == []  # erholt -> Befund erlischt


def t_sm04_sonde_wirft_wird_unknown():
    c = mk()
    def boom(conn, now): raise RuntimeError("x")
    sm.project(c, NOW, {"b": ("B", boom)})
    assert sm.history(c, "b")[0][1] == "UNKNOWN"


def t_sm05_retina_sonde():
    c = mk()
    assert sm.p_retina(c, NOW)[0] == "UNKNOWN"
    c.execute("create table f2_retina_sinne(organ_id text primary key, status text, ts real)")
    assert sm.p_retina(c, NOW)[0] == "UNKNOWN"
    c.execute("insert into f2_retina_sinne values('fenster1','aktiv',?)", (NOW - 100,))
    assert sm.p_retina(c, NOW)[0] == "VERIFIED"
    assert sm.p_retina(c, NOW + 5000)[0] == "FAILED"  # veraltet
    c.execute("update f2_retina_sinne set status='aus', ts=?", (NOW,))
    assert sm.p_retina(c, NOW)[0] == "FAILED"


def t_sm06_takt_und_prognose_und_s0():
    c = mk()
    assert sm.p_takt(c, NOW)[0] == "UNKNOWN" and sm.p_prognose(c, NOW)[0] == "UNKNOWN" and sm.p_s0(c, NOW)[0] == "UNKNOWN"
    for d in wm.DDL:
        c.execute(d)
    hi = int(NOW // 300) - 1
    for b in range(hi - 5, hi + 1):
        c.execute("insert into f3_wm_cover values(?,?,?)", (b, 0.0, "ok"))
    assert sm.p_takt(c, NOW)[0] == "VERIFIED"
    assert sm.p_prognose(c, NOW)[0] == "FAILED" and sm.p_s0(c, NOW) == ("FAILED", {"gueltige_fenster_v0": 0, "ziel": 200})
    c.execute("insert into f3_wm_pred(bucket,model_version,status,prospective) values(1,0,'bewertet',1)")
    assert sm.p_prognose(c, NOW)[0] == "VERIFIED"
    c2 = mk()
    for d in wm.DDL:
        c2.execute(d)
    c2.execute("insert into f3_wm_cover values(?,?,?)", (hi, 0.0, "ok"))
    assert sm.p_takt(c2, NOW)[0] == "FAILED"


def t_sm07_intent_sonde(tmp=None):
    import tempfile
    c = mk(); p = tempfile.mktemp(suffix=".json")
    assert sm.p_intent(c, NOW, p)[0] == "UNKNOWN"
    json.dump({"metrics": {"bestanden": False, "indirekt_recall": 0.4, "tool_precision": 0.5, "macro_f1": 0.5, "schema": 1.0}}, open(p, "w"))
    assert sm.p_intent(c, NOW, p)[0] == "FAILED"
    json.dump({"metrics": {"bestanden": True}}, open(p, "w"))
    assert sm.p_intent(c, NOW, p)[0] == "VERIFIED"
    os.remove(p)


def t_sm08_lokales_llm_sonde():
    c = mk()
    assert sm.p_lokales_llm(c, NOW, "http://127.0.0.1:9/health")[0] == "FAILED"  # nichts hoert dort


def t_sm09_selbstbild_nur_belegtes():
    c = mk(); st = {"a": "UNKNOWN"}; sm.project(c, NOW, caps(st))
    b = sm.self_image(c)
    assert len(b) == 1 and "not testable" in b[0]["statement_text"] and "measurement" in b[0]["statement_text"]
    assert sm.self_image(mk()) == []


def t_sm10_aus_und_kill_und_echte_sonden_laufen():
    for k, v in (("frank3.self.mode", "off"), ("frank3.kill", "1")):
        c = mk(); c.execute("insert into star_konfig values(?,?)", (k, v)); c.commit()
        assert sm.project(c, NOW) == 0 and sm.finding(c) == []
    c = mk()
    assert sm.project(c, NOW) == len(sm.CAPS)  # all standard probes return a result (on empty DB mostly UNKNOWN), none propagates outward


if __name__ == "__main__":
    fails = 0
    for n, f in sorted(globals().items()):
        if n.startswith("t_sm"):
            try:
                f(); print("ok  ", n)
            except Exception as e:
                import traceback; fails += 1; print("FAIL", n, repr(e)); traceback.print_exc(limit=3)
    print("ALLE GRUEN" if not fails else "%d FEHLER" % fails)
    sys.exit(1 if fails else 0)
