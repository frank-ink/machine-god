"""Tests IC.01-IC.10 for intent_cortex + intent_bench_eval. With mock LLM, no network, no real DB."""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))
import intent_bench_eval as be
import intent_cortex as ic


def item(c, lvl="E3", spans=("x",), imp=False, neg=False, conf=0.9):
    return {"class": c, "evidence_level": lvl, "evidence_spans": list(spans), "implicit_intent": imp, "negation": neg, "confidence": conf, "reason": "r"}


def fake(items):
    return lambda t: json.dumps({"items": items})


def t_ic01_valid_and_selection():
    r = ic.analyse("Schreibe Code", fake([item("code", spans=["Schreibe Code"])]))
    assert r["valid"] and r["selected"] == ["code"] and not r["abstain"]


def t_ic02_span_must_be_in_text():
    r = ic.analyse("Hallo", fake([item("code", spans=["Programmieren"])]))
    assert not r["valid"] and r["selected"] == [] and r["abstain"] and "span_nicht_im_text" in r["errors"][0]


def t_ic03_negation_and_level():
    t = "kein Code, nur json"
    r = ic.analyse(t, fake([item("code", spans=["kein Code"], neg=True), item("json", lvl="E1", spans=["json"]), item("tool", lvl="E2", spans=["nur"], conf=0.3)]))
    assert r["valid"] and r["selected"] == []  # negated / keyword only / too uncertain


def t_ic04_nonsense_becomes_abstain():
    for raw in ("", "kein json", json.dumps({"items": [{"class": "magie"}]}), json.dumps({"items": "x"}), json.dumps({"items": [dict(item("code"), confidence=7)]})):
        r = ic.analyse("x", lambda t, raw=raw: raw)
        assert not r["valid"] and r["abstain"] and r["selected"] == []


def t_ic05_llm_error_becomes_abstain():
    def boom(t):
        raise ConnectionError("weg")
    r = ic.analyse("x", boom)
    assert not r["valid"] and r["abstain"] and r["errors"] == ["llm:ConnectionError"]


def t_ic06_ledger_only_hash():
    c = sqlite3.connect(":memory:")
    ic.analyse("Geheimer Text xyz", fake([item("code", spans=["Geheimer"])]), conn=c, now=1.0)
    row = c.execute("select text_hash,valid,selected,rule_version from f3_intent_log").fetchone()
    assert row[1] == 1 and json.loads(row[2]) == ["code"] and row[3] == ic.RULE_VERSION and "Geheimer" not in json.dumps(row)


def t_ic07_strongest_evidence_per_class():
    t = "abc"
    r = ic.analyse(t, fake([item("tool", lvl="E2", spans=["a"], conf=0.6), item("tool", lvl="E3", spans=["b"], conf=0.8)]))
    assert r["selected"] == ["tool"]


def t_ic08_bench_unchanged_and_numbers():
    items, ok = be.load()
    from collections import Counter
    c = Counter(i["kat"] for i in items)
    assert ok and len(items) == 120 and c == {"indirekt": 40, "explizit": 20, "mehrfach": 20, "falle": 20, "abstain": 20}
    assert len({i["id"] for i in items}) == 120 and all(l in ic.CLASSES for i in items for l in i["labels"])
    assert all((not i["labels"]) == i["abstain"] for i in items)


def t_ic09_metrics_oracle_and_empty():
    items, _ = be.load()
    rows = [{"kat": i["kat"], "gold": i["labels"], "pred": i["labels"], "valid": True, "span_ok": True} for i in items]
    m = be.metrics(rows)
    assert m["bestanden"] and m["macro_f1"] == 1.0 and m["indirekt_recall"] == 1.0 and m["tool_precision"] == 1.0
    rows2 = [dict(r, pred=[]) for r in rows]
    m2 = be.metrics(rows2)
    assert not m2["bestanden"] and m2["indirekt_recall"] == 0.0 and m2["tool_precision"] is None and not m2["abnahme"]["tool_precision"]


def t_ic10_oracle_run_over_analysis():
    gold = {i["text"]: i for i in be.load()[0]}
    def oracle(t):
        return json.dumps({"items": [item(c, spans=[t[:3]]) for c in gold[t]["labels"]]})
    m, rows = be.run(llm=oracle)
    assert m["bestanden"] and m["schema"] == 1.0 and m["spans"] == 1.0 and m["bench_sha_ok"]


if __name__ == "__main__":
    fails = 0
    for n, f in sorted(globals().items()):
        if n.startswith("t_ic"):
            try:
                f(); print("ok  ", n)
            except Exception as e:
                import traceback; fails += 1; print("FAIL", n, repr(e)); traceback.print_exc(limit=3)
    print("ALLE GRUEN" if not fails else "%d FEHLER" % fails)
    sys.exit(1 if fails else 0)
