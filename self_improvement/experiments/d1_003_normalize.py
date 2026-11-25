"""MG-D1-003-NORMALIZE (DESIGN 17i): arm E = spell-fix + common-word drop, then D (AND-first, OR fill), vs B+D.

Same probe generator, seed and order as MG-D1-002 (17b), plus P0 = unperturbed tail/ordinary/legacy. Dev only.
Usage: python3 d1_003_normalize.py   (reads ~/.cache/machine-god/d1_001/idx_{A,B}.db read-only)
"""
import json
import os
import random
import sqlite3
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "mgfixed"))
from mg.gate import paired_bootstrap  # noqa: E402  (fixed: sorted keys)

HERE = os.path.dirname(os.path.abspath(__file__))
P = os.path.expanduser("~/.cache/machine-god/d1_001/")
I = {k: sqlite3.connect("file:" + P + f"idx_{k}.db?mode=ro", uri=True) for k in "AB"}
B = I["B"]
B.execute("create virtual table if not exists temp.vr using fts5vocab(main, mem_fts, row)")
common = [r[0] for r in B.execute("select term from temp.vr where length(term)>=4 order by doc desc limit 300")]
DF = dict(B.execute("select term, doc from temp.vr"))
NDOC = B.execute("select count(*) from mem_fts").fetchone()[0]
ALPHA = sorted({ch for t in DF for ch in t if ch.isalpha()} | set("abcdefghijklmnopqrstuvwxyz0123456789"))
COMMON_FRAC = 0.05
ARM = os.environ.get("ARM", "E")  # E = spellfix + common drop (17i); F = spellfix only (17k)


def q(c, e, k=10):
    try:
        return [x[0] for x in c.execute("select rowid from mem_fts where mem_fts match ? order by bm25(mem_fts) limit ?", (e, k))]
    except sqlite3.Error:
        return []


def OR(c, w):
    return q(c, " OR ".join('"%s"' % x for x in w))


def D(c, w):
    ids = q(c, " AND ".join('"%s"' % x for x in w))
    if len(ids) < 10:
        for i in OR(c, w):
            if i not in ids:
                ids.append(i)
    return ids[:10]


def edits1(w):
    s = [(w[:i], w[i:]) for i in range(len(w) + 1)]
    return ({a + b[1:] for a, b in s if b} | {a + b[1] + b[0] + b[2:] for a, b in s if len(b) > 1}
            | {a + ch + b[1:] for a, b in s if b for ch in ALPHA} | {a + ch + b for a, b in s for ch in ALPHA})


def spellfix(w):
    if DF.get(w, 0) > 0:
        return w
    cands = [(DF[x], x) for x in edits1(w) if DF.get(x, 0) > 0]
    return max(cands)[1] if cands else w


def normalize(words):
    fixed = [spellfix(w.lower()) for w in words]
    if ARM == "F":
        return fixed
    keep = [w for w in fixed if DF.get(w, 0) <= COMMON_FRAC * NDOC]
    return keep if len(keep) >= 2 else fixed


def E(c, w):
    return D(c, normalize(w))


def rr5(ids, did):
    return next((1.0 / (i + 1) for i, x in enumerate(ids[:5]) if x == did), 0.0)


def intarget(w, did):
    return bool(B.execute("select 1 from mem_fts where mem_fts match ? and rowid=?", ('"%s"' % w, did)).fetchone())


rows = [json.loads(l) for l in open(os.path.join(HERE, "d1_001_dev_probes.jsonl"))]
nl = [r for r in rows if r["family"] != "legacy"]
rnd = random.Random(1)
allw = [w for r in nl for w in r["query"].split()]


def typo(w):
    if len(w) < 4:
        return w
    i = rnd.randrange(1, len(w) - 2)
    return w[:i] + w[i + 1] + w[i] + w[i + 2:]


cells = {}  # cell -> list of (item_key, doc_id, query words)
for fam in ("tail", "ordinary"):  # identical generator order to MG-D1-002
    fr = [r for r in nl if r["family"] == fam]
    for p in ("P1", "P2", "P3", "P4"):
        for r in fr:
            w = r["query"].split()
            if p == "P1":
                qq = rnd.sample(w, 3)
            elif p == "P2":
                qq = w + [x for x in rnd.sample(allw, 40) if x not in w and not intarget(x, r["doc_id"])][:2]
            elif p == "P3":
                idx = rnd.sample(range(len(w)), 2)
                qq = [typo(x) if i in idx else x for i, x in enumerate(w)]
            else:
                qq = rnd.sample(w, 3) + rnd.sample(common, 4)
            cells.setdefault(f"{fam}_{p}", []).append((str(r["doc_id"]), r["doc_id"], qq))
for fam in ("tail", "ordinary", "legacy"):
    cells[f"{fam}_P0"] = [(str(r["doc_id"]), r["doc_id"], r["query"].split()) for r in rows if r["family"] == fam]

out, lat = {}, {"A_OR": [], "B_D": [], "E": []}
for cell, items in cells.items():
    base = {k: rr5(D(B, w), did) for k, did, w in items}
    cand = {k: rr5(E(B, w), did) for k, did, w in items}
    bs = paired_bootstrap(base, cand, n=10000, seed=0)
    must_gain = cell in (("tail_P3",) if ARM == "F" else ("tail_P3", "tail_P4"))
    ok = bs["ci_low"] > 0 if must_gain else bs["ci_low"] >= -0.02
    out[cell] = {"n": len(items), "BD": round(sum(base.values()) / len(base), 4), "E": round(sum(cand.values()) / len(cand), 4),
                 "E_minus_BD": [round(bs["delta"], 4), round(bs["ci_low"], 4), round(bs["ci_high"], 4)],
                 "better": sum(cand[k] > base[k] for k in base), "worse": sum(cand[k] < base[k] for k in base),
                 "rule": "ci_low>0" if must_gain else "ci_low>=-0.02", "pass": ok}
allq = [w for items in cells.values() for _, _, w in items]
for rep in range(2):
    for w in allq:
        for k, c, fn in (("A_OR", I["A"], OR), ("B_D", B, D), ("E", B, E)):
            t = time.perf_counter()
            fn(c, w)
            if rep == 1:
                lat[k].append((time.perf_counter() - t) * 1000)
p95 = {k: round(sorted(v)[int(.95 * len(v))], 1) for k, v in lat.items()}
out["latency_p95_ms"] = p95
out["latency_ratio_E_over_A"] = round(p95["E"] / p95["A_OR"], 3)
out["latency_pass"] = out["latency_ratio_E_over_A"] <= 1.25
out["ALL_PASS"] = all(v["pass"] for k, v in out.items() if isinstance(v, dict) and "pass" in v) and out["latency_pass"]
json.dump(out, open(os.path.join(HERE, "d1_003_normalize_dev.json" if ARM == "E" else "d1_004_spellfix_dev.json"), "w"), indent=1)
for k, v in out.items():
    print(k, v if not isinstance(v, dict) or "n" not in v else
          f"n={v['n']} BD={v['BD']} E={v['E']} d={v['E_minus_BD']} +{v['better']}/-{v['worse']} pass={v['pass']}")
