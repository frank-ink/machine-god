"""intent_bench_eval.py -- Auswertung INTENT_BENCH_V1 (120 Aufgaben, sha in fixtures/intent-bench/INTENT_BENCH_V1.sha256) fuer INTENT_CORTEX_V1.
Abnahme (ChatGPT Runde 10, experimentelle Festlegung): Schema 100 %, Spans 100 %, indirekter Recall >= 0.75, tool-Precision >= 0.90, Macro-F1 >= 0.80."""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import intent_cortex as ic

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "intent-bench")
THRESH = {"schema": 1.0, "spans": 1.0, "indirekt_recall": 0.75, "tool_precision": 0.90, "macro_f1": 0.80}


def load(path=None):
    path = path or DIR + "/INTENT_BENCH_V1.jsonl"
    body = open(path, "rb").read()
    ok = hashlib.sha256(body).hexdigest() == open(path.replace(".jsonl", ".sha256")).read().strip()
    return [json.loads(l) for l in body.decode().splitlines() if l.strip()], ok


def metrics(rows):
    """rows: [{kat, gold[], pred[], valid, span_ok}] -> Kennzahlen."""
    tp = {c: 0 for c in ic.CLASSES}; fp = dict(tp); fn = dict(tp)
    for r in rows:
        for c in ic.CLASSES:
            g, p = c in r["gold"], c in r["pred"]
            tp[c] += g and p; fp[c] += p and not g; fn[c] += g and not p
    f1 = {c: (2 * tp[c] / (2 * tp[c] + fp[c] + fn[c])) if (2 * tp[c] + fp[c] + fn[c]) else 1.0 for c in ic.CLASSES}
    ind = [r for r in rows if r["kat"] == "indirekt"]
    ig = sum(len(r["gold"]) for r in ind); ih = sum(len(set(r["gold"]) & set(r["pred"])) for r in ind)
    ab = [r for r in rows if not r["gold"]]
    m = {"n": len(rows), "schema": sum(r["valid"] for r in rows) / len(rows), "spans": sum(r["span_ok"] for r in rows) / len(rows),
         "indirekt_recall": ih / ig if ig else None, "tool_precision": tp["tool"] / (tp["tool"] + fp["tool"]) if tp["tool"] + fp["tool"] else None,
         "macro_f1": sum(f1.values()) / len(f1), "f1": f1, "abstain_korrekt": sum(not r["pred"] for r in ab) / len(ab) if ab else None,
         "je_kategorie_exakt": {k: sum(set(r["gold"]) == set(r["pred"]) for r in rows if r["kat"] == k) / max(1, sum(r["kat"] == k for r in rows)) for k in sorted({r["kat"] for r in rows})}}
    m["abnahme"] = {k: (m[k] is not None and m[k] >= v) for k, v in THRESH.items()}
    m["bestanden"] = all(m["abnahme"].values())
    return m


def run(llm=None, limit=None, out=None):
    items, sha_ok = load()
    rows = []
    for it in items[:limit]:
        r = ic.analyse(it["text"], llm=llm)
        rows.append({"id": it["id"], "kat": it["kat"], "gold": it["labels"], "pred": r["selected"], "valid": r["valid"], "span_ok": r["valid"] and not r["errors"], "errors": r["errors"]})
    m = metrics(rows); m["bench_sha_ok"] = sha_ok
    if out:
        json.dump({"metrics": m, "rows": rows}, open(out, "w"), ensure_ascii=False, indent=1)
    return m, rows


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    m, rows = run(limit=lim, out=os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "intent-bench/lauf_%s.json" % ("voll" if not lim else "probe")))
    print(json.dumps(m, ensure_ascii=False, indent=1))
