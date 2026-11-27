"""MG-D1-007 (DESIGN 17q): rollback test on a COPY of unified.db, plus latency re-measure on idx_A / idx_B.

unified.db is opened read-only (mode=ro) and only used as the backup source. All writes go to the copy.
"""
import json
import os
import random
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.expanduser("~/.claude/star/tools"))
import frank3_improver as FI  # noqa: E402  (import only; main() is guarded)

LIVE = os.path.expanduser("~/.local/share/agentzero/unified.db")
P = os.path.expanduser("~/.cache/machine-god/d1_001/")
COPY = P + "rollback_copy.db"
DDL = ("CREATE VIRTUAL TABLE {} USING fts5(subject, text, content='', contentless_delete=1, "
       "tokenize='unicode61 remove_diacritics 2')")
out = {"live_before": [os.path.getsize(LIVE), os.path.getmtime(LIVE)]}

# probe queries: dev (all families) + promo + audit, clean
dev = [json.loads(l) for l in open(os.path.join(HERE, "d1_001_dev_probes.jsonl"))]
S = json.load(open(os.path.join(HERE, "d1_001_sealed_splits.json")))["splits"]
probes = [(r["doc_id"], r["query"].split()) for r in dev] + [(r["doc_id"], r["query"].split()) for v in S.values() for r in v]
out["n_queries"] = len(probes)


def q(c, e, table="mem_fts", k=10):
    try:
        return [x[0] for x in c.execute(f"select rowid from {table} where {table} match ? order by bm25({table}) limit ?", (e, k))]
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


def integrity(c):
    try:
        c.execute("insert into mem_fts(mem_fts) values('integrity-check')")
        return "ok"
    except sqlite3.Error as e:
        return f"error: {e}"


src = sqlite3.connect("file:" + LIVE + "?mode=ro", uri=True)
try:
    src.execute("create table _probe_ro_(a)")
    out["live_readonly_proven"] = False
except sqlite3.Error:
    out["live_readonly_proven"] = True
if os.path.exists(COPY):
    os.remove(COPY)
t = time.time()
dst = sqlite3.connect(COPY)
src.backup(dst)
src.close()
out["copy_s"] = round(time.time() - t, 1)

R0 = [OR(dst, w) for _, w in probes]
n0 = dst.execute("select count(*) from mem_fts_docsize").fetchone()[0]
out["integrity_before"] = integrity(dst)

t = time.time()
dst.execute(DDL.format("mem_fts_full"))
docs = dst.execute("select doc_id, source_id, source_key from mem_doc where canon_id=doc_id and fts=1").fetchall()
nfull = 0
for did, sid, skey in docs:
    x = FI.source_text(dst, sid, skey)
    if not x:
        continue
    dst.execute("insert into mem_fts_full(rowid, subject, text) values(?,?,?)", (did, str(x[0] or ""), str(x[1] or "")))
    nfull += 1
dst.commit()
out.update({"full_build_s": round(time.time() - t, 1), "docsize_trunc": n0, "docs_full": nfull})

# swap in
dst.execute("ALTER TABLE mem_fts RENAME TO mem_fts_trunc")
dst.execute("ALTER TABLE mem_fts_full RENAME TO mem_fts")
dst.commit()
out["integrity_swapped"] = integrity(dst)
out["docsize_swapped"] = dst.execute("select count(*) from mem_fts_docsize").fetchone()[0]
tail = [(r["doc_id"], r["query"].split()) for r in S["tail:promo"]]
out["sanity_tail_promo_mrr5_swapped_D"] = round(sum(next((1 / (i + 1) for i, x in enumerate(D(dst, w)[:5]) if x == did), 0)
                                                    for did, w in tail) / len(tail), 4)
# swap back
dst.execute("ALTER TABLE mem_fts RENAME TO mem_fts_full")
dst.execute("ALTER TABLE mem_fts_trunc RENAME TO mem_fts")
dst.commit()
out["integrity_after"] = integrity(dst)
n1 = dst.execute("select count(*) from mem_fts_docsize").fetchone()[0]
R1 = [OR(dst, w) for _, w in probes]
same = sum(a == b for a, b in zip(R0, R1))
out.update({"docsize_after": n1, "rankings_identical": same, "rankings_total": len(R0)})
dst.close()
out["live_after"] = [os.path.getsize(LIVE), os.path.getmtime(LIVE)]
out["rollback_pass"] = (same == len(R0) and n1 == n0 and out["live_readonly_proven"]
                        and all(out[k] == "ok" for k in ("integrity_before", "integrity_swapped", "integrity_after")))

# latency re-measure (17q): idx_A OR vs idx_B F, promo + audit, clean + P3, 5 interleaved reps after a warm-up
sys.argv = [sys.argv[0]]
A = sqlite3.connect("file:" + P + "idx_A.db?mode=ro", uri=True)
B = sqlite3.connect("file:" + P + "idx_B.db?mode=ro", uri=True)
B.execute("create virtual table if not exists temp.vr using fts5vocab(main, mem_fts, row)")
DF = dict(B.execute("select term, doc from temp.vr"))
ALPHA = sorted({ch for t_ in DF for ch in t_ if ch.isalpha()} | set("abcdefghijklmnopqrstuvwxyz0123456789"))


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


rnd = random.Random(7)
qs = []
for key in ("tail:promo", "ordinary:promo", "tail:audit", "ordinary:audit"):
    for r in S[key]:
        w = r["query"].split()
        qs.append(w)
        idx = rnd.sample(range(len(w)), 2)
        qs.append([(x[:1] + x[2] + x[1] + x[3:]) if i in idx and len(x) >= 4 else x for i, x in enumerate(w)])
reps = []
for rep in range(6):
    lat = {"A": [], "F": []}
    for w in qs:
        for k, c, fn in (("A", A, OR), ("F", B, F)):
            t = time.perf_counter()
            fn(c, w)
            lat[k].append((time.perf_counter() - t) * 1000)
    if rep:  # rep 0 is the warm-up
        p = {k: sorted(v)[int(.95 * len(v))] for k, v in lat.items()}
        reps.append({"p95_A": round(p["A"], 1), "p95_F": round(p["F"], 1), "ratio": round(p["F"] / p["A"], 3),
                     "load1": os.getloadavg()[0]})
ratios = sorted(r["ratio"] for r in reps)
out["latency_reps"] = reps
out["latency_median_ratio"] = ratios[len(ratios) // 2]
out["latency_pass"] = out["latency_median_ratio"] <= 1.25
json.dump(out, open(os.path.join(HERE, "d1_007_rollback.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
