"""MG-3 known-item retrieval runner. DB opened read-only. Stdlib only.
Per probe: item_id, rank (1-based, 0 = miss), hit1, hit5, rr, mrr_at_10, ms, dead_terms."""
import argparse
import importlib
import json
import os
import sqlite3
import sys
import time
from urllib.parse import quote

from mg.retrievers import match_expr, words


# Write-class actions on "main" are let through on purpose: mode=ro + query_only make SQLite itself refuse them with a
# plain OperationalError (readonly database). Everything that could re-open a write path (ATTACH, DETACH, any PRAGMA but
# data_version, temp objects, virtual-table DDL) is denied outright.
_WRITE_MAIN = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE, sqlite3.SQLITE_CREATE_TABLE,
               sqlite3.SQLITE_CREATE_INDEX, sqlite3.SQLITE_DROP_TABLE, sqlite3.SQLITE_DROP_INDEX}


def _authorizer(action, arg1, arg2, dbname, source):
    if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_TRANSACTION):
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA and arg1 == "data_version" and arg2 is None:
        return sqlite3.SQLITE_OK
    if action in _WRITE_MAIN and dbname in ("main", None):
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def open_ro(path):
    """Open database read-only safely.
    Builds URI with quoted absolute path, enables query_only pragma and authorizer.
    Missing file raises (mode=ro never creates).
    Paths with '?', '#', '%', spaces work correctly.
    """
    abs_path = os.path.abspath(path)
    uri = "file:%s?mode=ro" % quote(abs_path)
    conn = sqlite3.connect(uri, uri=True)
    conn.execute("pragma query_only=ON")
    conn.set_authorizer(_authorizer)
    return conn


def load_retriever(spec):
    mod, _, fn = spec.partition(":")
    return getattr(importlib.import_module(mod), fn)


def dead_terms(conn, query):
    """Query words that match nothing in the index (probe-quality check)."""
    out = []
    for w in words(query):
        if conn.execute("SELECT 1 FROM mem_fts WHERE mem_fts MATCH ? LIMIT 1", (match_expr([w]),)).fetchone() is None:
            out.append(w)
    return out


def run_probes(conn, probes, retriever, k=10):
    rows = []
    for p in probes:
        t = time.perf_counter()
        ids = list(retriever(conn, p["query"], k))[:k]
        ms = (time.perf_counter() - t) * 1000
        rank = ids.index(p["expect_doc_id"]) + 1 if p["expect_doc_id"] in ids else 0
        rr = 1.0 / rank if rank else 0.0
        rows.append({"item_id": p["item_id"], "rank": rank, "hit1": int(rank == 1), "hit5": int(1 <= rank <= 5), "rr": rr,
                     "mrr_at_10": rr if 1 <= rank <= 10 else 0.0, "ms": round(ms, 3), "dead_terms": dead_terms(conn, p["query"])})
    return rows


def summary(rows):
    n = len(rows) or 1
    return {"n": len(rows), "hit1": sum(r["hit1"] for r in rows) / n, "hit5": sum(r["hit5"] for r in rows) / n,
            "mrr": sum(r["rr"] for r in rows) / n, "mrr_at_10": sum(r["mrr_at_10"] for r in rows) / n,
            "probes_with_dead_terms": sum(1 for r in rows if r["dead_terms"])}


def load_probes(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]


def main(argv=None):
    p = argparse.ArgumentParser(prog="mg.bench_retrieval")
    p.add_argument("--db", required=True); p.add_argument("--probes", required=True)
    p.add_argument("--retriever", default="mg.retrievers:fts_bm25_or"); p.add_argument("--k", type=int, default=10)
    a = p.parse_args(argv)
    rows = run_probes(open_ro(a.db), load_probes(a.probes), load_retriever(a.retriever), a.k)
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))
    print(json.dumps(summary(rows)), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
