"""MG-D1-005-PROMO (DESIGN 17m): the single look at the sealed promo split. F = spellfix + D on index B.

T1: tail promo F vs A (OR on 4000-char index), decide_v2(min_effect=0.10, min_n=40).
T2: tail promo with P3 typos (random.Random(2)), F vs B+D, decide_v2(min_effect=0.05, min_n=40).
Guards and rules are frozen in 17m. Indexes are opened read-only; zero model calls.
"""
import hashlib
import json
import os
import random
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "mgfixed"))
from mg.gate import decide_v2, paired_bootstrap  # noqa: E402

P = os.path.expanduser("~/.cache/machine-god/d1_001/")
SPLIT = os.environ.get("SPLIT", "promo")  # promo (17m) or audit (17o)
assert SPLIT in ("promo", "audit")


def conn(k):
    return sqlite3.connect("file:" + P + f"idx_{k}.db?mode=ro", uri=True)


A, B = conn("A"), conn("B")
B.execute("create virtual table if not exists temp.vr using fts5vocab(main, mem_fts, row)")
DF = dict(B.execute("select term, doc from temp.vr"))
ALPHA = sorted({ch for t in DF for ch in t if ch.isalpha()} | set("abcdefghijklmnopqrstuvwxyz0123456789"))


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


def F(c, w):
    return D(c, [spellfix(x.lower()) for x in w])


def rr5(ids, did):
    return next((1.0 / (i + 1) for i, x in enumerate(ids[:5]) if x == did), 0.0)


S = json.load(open(os.path.join(HERE, "d1_001_sealed_splits.json")))
assert hashlib.sha256(json.dumps(S["splits"], sort_keys=True).encode()).hexdigest() == S["sha256"], "sealed split altered"
promo = {fam: S["splits"][f"{fam}:{SPLIT}"] for fam in ("tail", "ordinary")}
rnd = random.Random(2 if SPLIT == "promo" else 3)


def typo(w):
    if len(w) < 4:
        return w
    i = rnd.randrange(1, len(w) - 2)
    return w[:i] + w[i + 1] + w[i] + w[i + 2:]


cells = {}
for fam in ("tail", "ordinary"):
    clean, p3 = [], []
    for r in promo[fam]:
        w = r["query"].split()
        idx = rnd.sample(range(len(w)), 2)
        clean.append((str(r["doc_id"]), r["doc_id"], w))
        p3.append((str(r["doc_id"]), r["doc_id"], [typo(x) if i in idx else x for i, x in enumerate(w)]))
    cells[f"{fam}_clean"], cells[f"{fam}_P3"] = clean, p3


def score(fn, c, items):
    return {k: rr5(fn(c, w), did) for k, did, w in items}


def cmp(base, cand):
    bs = paired_bootstrap(base, cand, n=10000, seed=0)
    return {"n": len(base), "base": round(sum(base.values()) / len(base), 4), "cand": round(sum(cand.values()) / len(cand), 4),
            "delta": round(bs["delta"], 4), "ci": [round(bs["ci_low"], 4), round(bs["ci_high"], 4)],
            "better": sum(cand[k] > base[k] for k in base), "worse": sum(cand[k] < base[k] for k in base), "_bs": bs}


out = {}
t1 = cmp(score(OR, A, cells["tail_clean"]), score(F, B, cells["tail_clean"]))
t2 = cmp(score(D, B, cells["tail_P3"]), score(F, B, cells["tail_P3"]))
g_ord = cmp(score(OR, A, cells["ordinary_clean"]), score(F, B, cells["ordinary_clean"]))
g_ord3 = cmp(score(D, B, cells["ordinary_P3"]), score(F, B, cells["ordinary_P3"]))

allq = [w for items in cells.values() for _, _, w in items]
lat = {"A_OR": [], "F": []}
for rep in range(2):
    for w in allq:
        for k, c, fn in (("A_OR", A, OR), ("F", B, F)):
            t = time.perf_counter()
            fn(c, w)
            if rep == 1:
                lat[k].append((time.perf_counter() - t) * 1000)
p95 = {k: round(sorted(v)[int(.95 * len(v))], 1) for k, v in lat.items()}
B2 = conn("B")  # restart test: a fresh read-only connection must rank identically
restart_same = all(F(B, w) == F(B2, w) for w in allq)
size_ratio = os.path.getsize(P + "idx_B.db") / os.path.getsize(P + "idx_A.db")

guards = [
    {"name": "ordinary_F_vs_A_ci_low>=-0.02", "passed": g_ord["ci"][0] >= -0.02},
    {"name": "ordinary_P3_F_vs_BD_ci_low>=-0.02", "passed": g_ord3["ci"][0] >= -0.02},
    {"name": "p95_F<=1.25xA", "passed": p95["F"] <= 1.25 * p95["A_OR"]},
    {"name": "restart_identical", "passed": restart_same},
    {"name": "index_size_B/A<=1.5", "passed": size_ratio <= 1.5},
]
for name, t, me in (("T1_tail_F_vs_A", t1, 0.10), ("T2_tailP3_F_vs_BD", t2, 0.05)):
    bs = t.pop("_bs")
    t["decide_v2"] = decide_v2({**bs, "n_items": t["n"]}, guards, min_effect=me, min_n=40)
    t["original_rule_delta>=0.10_ci_low>0"] = (t["delta"] >= 0.10 and t["ci"][0] > 0) if name.startswith("T1") else None
    out[name] = t
for name, t in (("guard_ordinary_F_vs_A", g_ord), ("guard_ordinaryP3_F_vs_BD", g_ord3)):
    t.pop("_bs")
    out[name] = t
out.update({"latency_p95_ms": p95, "restart_identical": restart_same, "index_size_ratio": round(size_ratio, 3),
            "guards": guards, "overall": "PASS" if all(out[k]["decide_v2"]["decision"] == "PASS" for k in
                                                       ("T1_tail_F_vs_A", "T2_tailP3_F_vs_BD")) else "NOT_PASS"})
json.dump(out, open(os.path.join(HERE, "d1_005_promo.json" if SPLIT == "promo" else "d1_006_audit.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
