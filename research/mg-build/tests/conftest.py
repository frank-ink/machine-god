import json
import sqlite3

import pytest


@pytest.fixture
def synth_db(tmp_path):
    p = str(tmp_path / "synth.db")
    c = sqlite3.connect(p)
    c.execute("create virtual table mem_fts using fts5(body)")
    for i in range(1, 51):
        c.execute("insert into mem_fts(rowid, body) values(?,?)", (i, "alpha beta tok%d grp%d" % (i, i % 5)))
    c.execute("update mem_fts set body='mueller strasse alpha' where rowid=3")
    c.commit(); c.close()
    return p


def write_probes(path, ids, dead=False):
    with open(path, "w") as f:
        for i in ids:
            q = "tok%d grp%d" % (i, i % 5) + (" zzzdead" if dead and i % 2 == 0 else "")
            f.write(json.dumps({"item_id": "p%d" % i, "query": q, "expect_doc_id": i}) + "\n")
    return str(path)


@pytest.fixture
def probes(tmp_path):
    return (write_probes(tmp_path / "dev.jsonl", range(1, 21)), write_probes(tmp_path / "promo.jsonl", range(21, 36)),
            write_probes(tmp_path / "audit.jsonl", range(36, 51)))
