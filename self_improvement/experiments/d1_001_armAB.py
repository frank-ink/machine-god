#!/usr/bin/env python3
"""MG-D1-001-FULLTEXT dev diagnostic: arm A (text[:4000], as frank3_improver.task_fts) vs arm B (full text).

Read-only on the source DB (mode=ro). Indexes are built in separate scratch DB files, never in unified.db.
Only the dev split is evaluated; promo/audit doc ids are written sealed (unevaluated) with a sha256.
Query construction mirrors frank3_improver.build_probes/task_probe (regex [A-Za-zÄÖÜäöüß]{6,}, lowercase,
first 12 unique words, 6 lowest-df words, OR-joined quoted terms, ORDER BY bm25).
"""
import argparse, hashlib, json, os, random, re, sqlite3, sys, time

sys.path.insert(0, os.path.expanduser("~/.claude/star/tools"))
import frank3_improver as F  # noqa: E402  (import only; main() is guarded)

DDL = ("CREATE VIRTUAL TABLE mem_fts USING fts5(subject, text, content='', contentless_delete=1, "
       "tokenize='unicode61 remove_diacritics 2')")  # identical to live sqlite_master.sql
WORD = re.compile(r"[A-Za-zÄÖÜäöüß]{6,}")
CUT = 4000


def uniq(words, n=12):
    seen, out = set(), []
    for w in words:
        lw = w.lower()
        if lw not in seen:
            seen.add(lw)
            out.append(lw)
    return out[:n]


def df(c, w):
    try:
        return c.execute("select count(*) from mem_fts where mem_fts match ?", ('"%s"' % w,)).fetchone()[0]
    except sqlite3.Error:
        return 0


def rank(c, query, k=10):
    terms = " OR ".join('"%s"' % w for w in query.split())
    t = time.perf_counter()
    try:
        ids = [r[0] for r in c.execute(
            "select rowid from mem_fts where mem_fts match ? order by bm25(mem_fts) limit ?", (terms, k))]
    except sqlite3.Error:
        ids = []
    return ids, (time.perf_counter() - t) * 1000


def split_of(doc_id, fam):
    h = int(hashlib.sha256(f"{fam}:{doc_id}".encode()).hexdigest()[:8], 16) % 220
    return "dev" if h < 100 else ("promo" if h < 160 else "audit")


def boot(deltas, n=10000, seed=0):
    if not deltas:
        return None
    rnd = random.Random(seed)
    m = len(deltas)
    means = sorted(sum(deltas[rnd.randrange(m)] for _ in range(m)) / m for _ in range(n))
    return {"delta": sum(deltas) / m, "ci_low": means[int(0.025 * n)], "ci_high": means[int(0.975 * n) - 1], "n": m}


def p95(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(0.95 * len(xs)))] if xs else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.expanduser("~/.local/share/agentzero/unified.db"))
    ap.add_argument("--work", default=os.path.expanduser("~/.cache/machine-god/d1_001"))
    ap.add_argument("--out-dir", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    src = sqlite3.connect("file:" + a.src + "?mode=ro", uri=True)
    t0 = time.time()

    docs = src.execute("select doc_id, source_id, source_key, text_len from mem_doc where canon_id=doc_id and fts=1 "
                       "order by doc_id" + (f" limit {a.limit}" if a.limit else "")).fetchall()
    paths = {arm: os.path.join(a.work, f"idx_{arm}.db") for arm in "AB"}
    for p in paths.values():
        if os.path.exists(p):
            os.remove(p)
    idx = {arm: sqlite3.connect(p) for arm, p in paths.items()}
    for c in idx.values():
        c.execute("pragma journal_mode=off")
        c.execute("pragma synchronous=off")
        c.execute(DDL)
    long_docs, all_docs, missing = {}, [], 0
    for i, (did, sid, skey, tlen) in enumerate(docs):
        x = F.source_text(src, sid, skey)
        if x is None:
            missing += 1
            continue
        sj, tx = str(x[0] or ""), str(x[1] or "")
        idx["A"].execute("insert into mem_fts(rowid, subject, text) values(?,?,?)", (did, sj, tx[:CUT]))
        idx["B"].execute("insert into mem_fts(rowid, subject, text) values(?,?,?)", (did, sj, tx))
        if len(tx) >= 120:
            all_docs.append(did)
        if len(tx) > CUT:
            long_docs[did] = (sj, tx)
        if i % 20000 == 0:
            for c in idx.values():
                c.commit()
            print(f"[index] {i}/{len(docs)} {time.time()-t0:.0f}s", file=sys.stderr)
    for c in idx.values():
        c.commit()
    nA = idx["A"].execute("select count(*) from mem_fts").fetchone()[0]
    nB = idx["B"].execute("select count(*) from mem_fts").fetchone()[0]
    for c in idx.values():
        c.close()
    bytes_ = {arm: os.path.getsize(p) for arm, p in paths.items()}
    idx = {arm: sqlite3.connect("file:" + p + "?mode=ro", uri=True) for arm, p in paths.items()}
    print(f"[index] done A={nA} B={nB} missing_source={missing} long={len(long_docs)} {time.time()-t0:.0f}s",
          file=sys.stderr)

    # probe families
    probes = []
    for q, sid, skey in src.execute("select query, expect_source, expect_key from f3_probe order by rowid"):
        w = src.execute("select doc_id from mem_doc where source_id=? and source_key=?", (sid, skey)).fetchone()
        probes.append({"family": "legacy", "split": "dev", "doc_id": w[0] if w else None, "query": q})
    rnd = random.Random(a.seed)
    tail_pool = sorted(long_docs)
    rnd.shuffle(tail_pool)
    tail_n = 0
    for did in tail_pool:
        if tail_n >= 220:
            break
        sj, tx = long_docs[did]
        head = set(w.lower() for w in WORD.findall(sj + " " + tx[:CUT]))
        cand = [w for w in uniq(WORD.findall(tx[CUT:]), 10 ** 9) if w not in head][:12]
        sc = sorted((df(idx["B"], w), w) for w in cand)
        sc = [(d, w) for d, w in sc if d > 0]  # df=0 is a tokenizer mismatch, not rarity
        if len(sc) < 5:
            continue
        probes.append({"family": "tail", "split": split_of(did, "tail"), "doc_id": did,
                       "query": " ".join(w for _, w in sc[:6])})
        tail_n += 1
    ord_pool = list(all_docs)
    rnd.shuffle(ord_pool)
    ord_n = 0
    for did in ord_pool:
        if ord_n >= 220:
            break
        r = src.execute("select source_id, source_key from mem_doc where doc_id=?", (did,)).fetchone()
        x = F.source_text(src, r[0], r[1])
        if not x:
            continue
        sj, tx = str(x[0] or ""), str(x[1] or "")
        cand = uniq(WORD.findall(sj + " " + tx[:CUT]))
        sc = [(d, w) for d, w in sorted((df(idx["A"], w), w) for w in cand) if d > 0]
        if len(sc) < 5:
            continue
        probes.append({"family": "ordinary", "split": split_of(did, "ord"), "doc_id": did,
                       "query": " ".join(w for _, w in sc[:6])})
        ord_n += 1

    sealed = {}
    for p in probes:
        if p["split"] != "dev":
            sealed.setdefault(f'{p["family"]}:{p["split"]}', []).append({"doc_id": p["doc_id"], "query": p["query"]})
    blob = json.dumps(sealed, sort_keys=True).encode()
    with open(os.path.join(a.out_dir, "d1_001_sealed_splits.json"), "w") as f:
        json.dump({"sha256": hashlib.sha256(blob).hexdigest(), "splits": sealed}, f, sort_keys=True)

    # evaluate dev only
    rows = []
    for p in probes:
        if p["split"] != "dev":
            continue
        rec = dict(p)
        for arm, c in idx.items():
            ids, ms = rank(c, p["query"], 10)
            rk = ids.index(p["doc_id"]) + 1 if p["doc_id"] in ids else 0
            rec[arm] = {"rank": rk, "hit1": int(rk == 1), "rr5": 1 / rk if 0 < rk <= 5 else 0.0,
                        "rr10": 1 / rk if rk else 0.0, "ms": round(ms, 3)}
        rows.append(rec)
    with open(os.path.join(a.out_dir, "d1_001_dev_probes.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summ = {"n_docs_A": nA, "n_docs_B": nB, "missing_source": missing, "long_docs": len(long_docs),
            "index_bytes": bytes_, "index_bytes_ratio_B_A": round(bytes_["B"] / bytes_["A"], 4),
            "probes_built": {f: sum(1 for p in probes if p["family"] == f) for f in ("legacy", "tail", "ordinary")},
            "sealed_sha256": hashlib.sha256(blob).hexdigest(), "families": {}, "elapsed_s": round(time.time() - t0, 1)}
    for fam in ("legacy", "tail", "ordinary"):
        fr = [r for r in rows if r["family"] == fam]
        if not fr:
            continue
        d = {"n": len(fr)}
        for arm in "AB":
            d[arm] = {"hit1": round(sum(r[arm]["hit1"] for r in fr) / len(fr), 4),
                      "mrr5": round(sum(r[arm]["rr5"] for r in fr) / len(fr), 4),
                      "mrr10": round(sum(r[arm]["rr10"] for r in fr) / len(fr), 4),
                      "p95_ms": round(p95([r[arm]["ms"] for r in fr]), 3)}
        d["delta_mrr5_B_minus_A"] = boot([r["B"]["rr5"] - r["A"]["rr5"] for r in fr], seed=a.seed)
        d["rank_moves"] = {"better": sum((r["B"]["rank"] or 99) < (r["A"]["rank"] or 99) for r in fr),
                           "worse": sum((r["B"]["rank"] or 99) > (r["A"]["rank"] or 99) for r in fr)}
        summ["families"][fam] = d
    with open(os.path.join(a.out_dir, "d1_001_dev_summary.json"), "w") as f:
        json.dump(summ, f, indent=1)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
