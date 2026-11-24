"""Tests S0.01-S0.10 fuer s0_eval (S0_EVAL_V1). Synthetische Wegwerf-DB."""
import json
import os
import sqlite3
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import s0_eval as s0
import weltmodell as wm

CH = wm.CH


def mk():
    c = sqlite3.connect(":memory:")
    c.execute(wm.DDL[2])
    return c


def P(v):
    return json.dumps({k: v for k in CH}, sort_keys=True)


def put(c, b, p, x, ref, pers=None, ver=0, status="bewertet", prosp=1):
    c.execute("insert into f3_wm_pred(bucket,model_version,pred,ref_pred,pers_pred,obs,status,prospective) values(?,?,?,?,?,?,?,?)",
              (b, ver, P(p), P(ref), P(pers) if pers is not None else None, P(x), status, prosp))


def fill(c, n, p, ref, pers=None, start=0, ver=0, x=0.0):
    for i in range(n):
        put(c, start + i, p, x, ref, pers, ver)


def t_s001_protokoll():
    ok, h = s0.protocol_ok()
    assert ok and len(h) == 64
    assert not s0.protocol_ok("/nonexistent/x.md")[0]


def t_s002_zu_wenig():
    c = mk(); fill(c, 199, 0.0, 0.5)
    r = s0.evaluate(c, 0, reps=200)
    assert r["urteil"] == "ZU_WENIG_DATEN" and r["n_gueltig"] == 199 and "haupt_vs_w0" not in r
    assert s0.evaluate(sqlite3.connect(":memory:"), 0)["urteil"] == "ZU_WENIG_DATEN"


def t_s003_positiv():
    c = mk(); fill(c, 240, 0.0, 0.5, pers=0.5)  # Modell perfekt, Referenz schlecht
    r = s0.evaluate(c, 0, reps=500)
    h = r["haupt_vs_w0"]
    assert h["bss"] == 1.0 and h["urteil"] == "POSITIV" and h["n"] == 240 and h["bloecke"] == 20 and h["segmente"] == 1
    assert all(v["urteil"] == "POSITIV" for v in h["kanal"].values()) and r["urteil"] == "POSITIV"


def t_s004_negativ():
    c = mk(); fill(c, 240, 0.5, 0.1)  # Referenz mit Rest-Fehler (bei Referenzfehler 0 ist der BSS undefiniert)
    assert s0.evaluate(c, 0, reps=500)["urteil"] == "NEGATIV"


def t_s005_unentschieden():
    c = mk(); rng = np.random.default_rng(1)
    for i in range(240):  # Modell und Referenz gleich gut im Mittel, aber rauschend
        x = float(rng.integers(0, 2))
        put(c, i, 0.5 + rng.normal(0, .01), x, 0.5 + rng.normal(0, .01))
    r = s0.evaluate(c, 0, reps=1000)["haupt_vs_w0"]
    assert r["urteil"] == "UNENTSCHIEDEN" and r["ci95"][0] < 0 < r["ci95"][1]


def t_s006_versionen_getrennt():
    c = mk(); fill(c, 210, 0.0, 0.5, ver=0); fill(c, 210, 0.5, 0.1, start=1000, ver=1)
    assert s0.evaluate(c, 0, reps=200)["urteil"] == "POSITIV" and s0.evaluate(c, 1, reps=200)["urteil"] == "NEGATIV"
    assert s0.evaluate(c, 0, reps=200)["n_gueltig"] == 210


def t_s007_unknown_und_nichtprospektiv_zaehlen_nicht():
    c = mk(); fill(c, 200, 0.0, 0.5)
    for i in range(50):
        put(c, 5000 + i, 0.0, 0.0, 0.5, status="unbekannt"); put(c, 6000 + i, 0.0, 0.0, 0.5, prosp=0)
    r = s0.evaluate(c, 0, reps=200)
    assert r["n_gueltig"] == 200 and r["n_unknown"] == 50 and r["urteil"] == "POSITIV"


def t_s008_keine_bloecke_ueber_luecken():
    rows = [(b, None, None, None) for b in list(range(0, 30)) + list(range(100, 125)) + [200]]
    seg = s0.segments(rows)
    assert [len(s) for s in seg] == [30, 25, 1]
    bl = s0.blocks(rows, 12)
    assert [len(b) for b in bl] == [12, 12, 6, 12, 12, 1, 1]  # Restbloecke bleiben, kein Block ueberspringt eine Luecke
    assert all(b[-1][0] - b[0][0] == len(b) - 1 for b in bl)


def t_s009_reproduzierbar_und_persistenz():
    c = mk(); fill(c, 100, 0.0, 0.5, pers=0.2); fill(c, 100, 0.1, 0.5, pers=None, start=300)  # Persistenz fehlt in Haelfte -> nur 100 Fenster
    r1 = s0.evaluate(c, 0, reps=300, min_n=100); r2 = s0.evaluate(c, 0, reps=300, min_n=100)
    assert r1 == r2 and r1["sekundaer_vs_persistenz"]["n"] == 100 and r1["haupt_vs_w0"]["n"] == 200 and r1["haupt_vs_w0"]["segmente"] == 2
    assert set(r1["sensitivitaet"]) == {"block24", "block36"}


def t_s011_referenzfehler_null_undefined():
    c = mk(); fill(c, 200, 0.5, 0.0)  # Referenz perfekt: BSS undefiniert, absoluter Brier wird berichtet
    h = s0.evaluate(c, 0, reps=100)["haupt_vs_w0"]
    assert h["bss"] is None and h["urteil"] == "UNDEFINED" and abs(h["brier_modell"] - 0.25) < 1e-9 and h["brier_referenz"] == 0.0


def t_s012_gleitend_nur_sensitivitaet():
    c = mk(); fill(c, 240, 0.0, 0.5)
    r = s0.evaluate(c, 0, reps=200)
    g = r["sensitivitaet_gleitend"]
    assert set(g) == {"block12", "block24", "block36"} and g["block12"]["bloecke"] == 229 and r["urteil"] == r["haupt_vs_w0"]["urteil"] == "POSITIV"


def t_s010_formel():
    c = mk(); fill(c, 200, 0.3, 0.5, x=0.0)  # Modell 0.09, Referenz 0.25 -> BSS 0.64
    h = s0.evaluate(c, 0, reps=100)["haupt_vs_w0"]
    assert abs(h["bss"] - 0.64) < 1e-9 and all(abs(v["bss"] - 0.64) < 1e-9 for v in h["kanal"].values())


if __name__ == "__main__":
    fails = 0
    for n, f in sorted(globals().items()):
        if n.startswith("t_s"):
            try:
                f(); print("ok  ", n)
            except Exception as e:
                import traceback; fails += 1; print("FAIL", n, repr(e)); traceback.print_exc(limit=3)
    print("ALLE GRUEN" if not fails else "%d FEHLER" % fails)
    sys.exit(1 if fails else 0)
