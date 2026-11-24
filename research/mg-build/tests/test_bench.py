import json
import math

from conftest import write_probes
from mg import bench_retrieval as br, retrievers as R


def stub(table):
    return lambda conn, q, k: table[q]


def test_rank_math_by_hand(synth_db):
    table = {"p1": [100], "p2": [5, 100], "p3": [1, 2, 3, 4, 5, 100], "p4": [1, 2, 3, 4, 5, 6, 7, 8, 9, 100],
             "p5": [1, 2], "p6": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 100, 13]}
    probes = [{"item_id": k, "query": k, "expect_doc_id": 100} for k in table]
    rows = {r["item_id"]: r for r in br.run_probes(br.open_ro(synth_db), probes, stub(table), 15)}
    got = {k: (r["rank"], r["hit1"], r["hit5"], round(r["rr"], 6), round(r["mrr_at_10"], 6)) for k, r in rows.items()}
    assert got == {"p1": (1, 1, 1, 1.0, 1.0), "p2": (2, 0, 1, 0.5, 0.5), "p3": (6, 0, 0, round(1 / 6, 6), round(1 / 6, 6)),
                   "p4": (10, 0, 0, 0.1, 0.1), "p5": (0, 0, 0, 0.0, 0.0), "p6": (12, 0, 0, round(1 / 12, 6), 0.0)}
    s = br.summary(list(rows.values()))
    assert s["n"] == 6 and math.isclose(s["hit1"], 1 / 6) and math.isclose(s["hit5"], 2 / 6)
    assert math.isclose(s["mrr"], (1 + 0.5 + 1 / 6 + 0.1 + 0 + 1 / 12) / 6) and math.isclose(s["mrr_at_10"], (1 + 0.5 + 1 / 6 + 0.1) / 6)


def test_k_truncates_retriever_output(synth_db):
    r = br.run_probes(br.open_ro(synth_db), [{"item_id": "x", "query": "q", "expect_doc_id": 9}], lambda c, q, k: list(range(1, 20)), 5)
    assert r[0]["rank"] == 0


def test_baseline_finds_known_items_and_dead_terms(synth_db, tmp_path):
    p = write_probes(tmp_path / "p.jsonl", range(10, 20), dead=True)
    rows = br.run_probes(br.open_ro(synth_db), br.load_probes(p), R.fts_bm25_or, 10)
    assert all(r["rank"] == 1 for r in rows)
    dead = {r["item_id"]: r["dead_terms"] for r in rows}
    assert all(dead["p%d" % i] == (["zzzdead"] if i % 2 == 0 else []) for i in range(10, 20))
    assert br.summary(rows)["probes_with_dead_terms"] == 5


def test_db_is_read_only(synth_db):
    import sqlite3
    c = br.open_ro(synth_db)
    try:
        c.execute("insert into mem_fts(rowid, body) values(99,'x')")
        raise AssertionError("write allowed")
    except sqlite3.OperationalError:
        pass


def test_folded_retriever_finds_umlaut_variant(synth_db):
    c = br.open_ro(synth_db)
    assert R.fts_bm25_or(c, "Müller", 5) == []  # unicode61 index folds to 'muller', doc has 'mueller'
    assert R.fts_bm25_or_folded(c, "Müller Straße", 5)[0] == 3


def test_cli_emits_jsonl_and_summary(synth_db, tmp_path, capsys):
    p = write_probes(tmp_path / "p.jsonl", range(1, 6))
    assert br.main(["--db", synth_db, "--probes", p, "--retriever", "mg.retrievers:fts_bm25_or", "--k", "10"]) == 0
    cap = capsys.readouterr()
    lines = [json.loads(l) for l in cap.out.splitlines()]
    assert len(lines) == 5 and set(lines[0]) == {"item_id", "rank", "hit1", "hit5", "rr", "mrr_at_10", "ms", "dead_terms"}
    assert json.loads(cap.err)["n"] == 5
