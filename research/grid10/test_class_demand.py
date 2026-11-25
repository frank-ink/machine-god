"""Test gate segment 3 (CLASS_DEMAND_V1, Shadow). Run: python3 -I test_class_demand.py (Exit 0 = green).
Rule: explicit -> class; Retina alone never; max 4; ABSTAIN; known weaknesses as documented expectation (no patch). Lane: Isolation, switch, idempotency, no plaintext."""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import class_demand as cd
import class_demand_lane as L
import router_shadow as RS

G0 = {"G6": 0.0, "G9": 0.0, "G10": 0.0, "g9_valid": False}


def t_explizit_und_abstain():
    o = cd.derive("Bitte analysiere und vergleiche die beiden Ansaetze", "", G0)
    assert "reason" in o["selected"] and not o["abstain"], o
    o = cd.derive("hallo", "", G0)
    assert o["abstain"] and o["selected"] == [], o
    assert cd.derive("", "", G0)["abstain"]


def t_retina_allein_nie():
    o = cd.derive("hallo", "", G0, relay=["person_kommt", "fokus_app"], burst=True)
    assert o["abstain"], o
    o = cd.derive("Warum ist die Person im Raum?", "", G0, relay=["person_kommt"], burst=True)
    assert o["scores"]["reason"] > cd.derive("Warum ist die Person im Raum?", "", G0)["scores"]["reason"]


def t_max4_und_ueberlauf():
    txt = ("analysiere das ausfuehrlich, schreibe eine funktion in code mit json schema, suche die datei und fuehre aus ```x``` "
           "auf deutsch bitte")
    o = cd.derive(txt, "", {"G6": 1.0, "G9": 1.0, "G10": 1.0, "g9_valid": True})
    assert len(o["selected"]) <= 4 and set(o["selected"]) | set(o["overflow"]) == {c for c, s in o["scores"].items() if s >= cd.THRESH}


def t_goal_primaer_ohne_text():
    o = cd.derive("", "implementiere den parser", G0)
    assert "code" in o["selected"] and all(v == 0.0 for v in o["features"]["Z"].values())


def t_bekannte_schwaechen_dokumentiert():
    assert "code" in cd.derive("Schreibe KEINEN code, nur erklaere", "", G0)["selected"]  # keine Negation (Gegenbeispiel 1)
    o = cd.derive("Das ist nicht so einfach und ich weiss es nicht", "", G0)  # de nur indirekt: 0.275 < 0.5
    assert "de" not in o["selected"]
    assert cd.derive("```x```", "", {"G6": 0.0, "G9": 0, "G10": 0, "g9_valid": 0})["scores"]["code"] >= 0.5  # explizit reicht allein


def _db():
    c = sqlite3.connect(":memory:")
    c.execute("create table star_konfig(schluessel text primary key, wert text)")
    c.execute("create table f3_grid_v2_state(singleton integer primary key, j text)")
    c.execute("create table f3_retina_thal_log(bucket integer primary key, relay text, burst text)")
    c.execute("create table f2_retina_geschehen(id integer primary key, ts real, art text)")
    return c


def t_lane_ledger_isolation_schalter():
    RS.PATH = "/nonexistent/offer.json"
    c, now = _db(), 1000 * 300 + 40.0
    c.execute("insert into f3_retina_thal_log values(999,'[\"fokus_app\"]','[\"fokus_app\"]')")
    c.execute("insert into f2_retina_geschehen(ts,art) values(?,?)", (999 * 300 + 5, "fokus_app"))
    p = "Fuehre das Terminal aus und suche die Datei im Bildschirm"
    o = L.step(c, "s", "f1", p, {"G6": 0.9, "G9": 0.0, "G10": 0.1}, now)
    assert o and "tool" in o["selected"], o
    row = c.execute("select input_ref,retina_event_ids,burst,router_version,model_id,evaluation_status,rule_version from f3_class_demand_log").fetchone()
    assert p not in row[0] and row[0].endswith(":%d" % len(p)) and row[2] == 1 and row[3] == "none-shadow" and row[4] is None and row[5] == "pending" and row[6] == "CLASS_DEMAND_V1"
    assert c.execute("select count(*) from f3_grid_v2_state").fetchone() == (0,)
    assert "Datei" not in repr(c.execute("select * from f3_class_demand_log").fetchall())  # nie Klartext
    r2 = c.execute("select selected_classes,fields from f3_class_demand_v2_log").fetchone()
    import json as _j
    f2 = _j.loads(r2[1])
    assert "tool" in _j.loads(r2[0]) and f2["retina_available"] is True and f2["goal_present"] is False and p not in r2[1]  # V2 mitgeschrieben, nie Klartext
    L.step(c, "s", "f1", p, {}, now)  # gleicher Zeitpunkt+Frame -> gleiche event_id, nicht doppelt
    assert c.execute("select count(*) from f3_class_demand_log").fetchone() == (1,)
    assert c.execute("select count(*) from f3_class_demand_v2_log").fetchone() == (1,)
    c.execute("insert into star_konfig values('frank3.class_demand.mode','off')")
    assert L.step(c, "s", "f2", p, {}, now + 1) is None
    c.execute("update star_konfig set wert='shadow' where schluessel='frank3.class_demand.mode'")
    c.execute("insert into star_konfig values('frank3.kill','1')")
    assert L.step(c, "s", "f3", p, {}, now + 2) is None
    assert c.execute("select count(*) from f3_class_demand_log").fetchone() == (1,)


def t_lane_veraltete_retina():
    c = _db()
    assert L.retina_fresh(c, 1000 * 300 + 1) is False  # kein Fenster: NICHT gemessen
    c.execute("insert into f3_retina_thal_log values(1000,'[]','[]')")
    assert L.retina_fresh(c, 1000 * 300 + 1) is True  # leeres, aber frisches Fenster = verfuegbar
    c = _db()
    c.execute("insert into f3_retina_thal_log values(900,'[\"fokus_app\"]','[\"fokus_app\"]')")
    assert L.retina_state(c, 1000 * 300 + 1) == ([], False, [])


def t_resolve_input_und_alte_tabelle():
    import json
    import tempfile
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "proj"))
    msg = "Suche die Datei im Ordner und fuehre sie aus"
    with open(os.path.join(d, "proj", "sess1.jsonl"), "w") as f:
        f.write(json.dumps({"type": "user", "message": {"content": "anderes"}}) + "\n" + json.dumps({"type": "user", "message": {"content": msg}}) + "\n")
    ref = "%s:%d" % (L._h(msg), len(msg))
    assert L.resolve_input("sess1", ref, d) == msg and L.resolve_input("sess1", "0000:3", d) is None and L.resolve_input("nope", ref, d) is None
    c = _db()  # Table from older version without session_id -> will be supplemented
    c.execute(L.DDL[0].replace(", session_id text", ""))
    L.step(c, "sess1", "f9", msg, {}, 1000 * 300 + 1.0)
    assert c.execute("select session_id from f3_class_demand_log").fetchone() == ("sess1",)


def t_router_shadow_snapshot():
    import json
    import tempfile
    p = os.path.join(tempfile.mkdtemp(), "o.json")
    json.dump({"fetched": 1000.0, "classes": {"tool": {"best_model": "X/y", "score": 0.7}}}, open(p, "w"))
    assert RS.decide(["tool", "code"], p, now=1100.0) == ("offer-snapshot:1000", {"tool": {"model": "X/y", "score": 0.7}})
    assert RS.decide(["tool"], p, now=1000.0 + RS.MAX_AGE_S + 5)[0] == "offer-snapshot-stale:1000"
    assert RS.decide(["tool"], "/nonexistent/x.json") == ("none-shadow", {})
    RS.PATH = p
    c = _db()
    L.step(c, "s", "f1", "Fuehre das Terminal aus und suche die Datei", {"G6": 0.9}, 1100.0)
    rv, mid = c.execute("select router_version,model_id from f3_class_demand_log").fetchone()
    assert rv.startswith("offer-snapshot") and json.loads(mid)["tool"]["model"] == "X/y"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("t_"):
            fn()
            print("ok", name)
    print("ALLE GRUEN")
