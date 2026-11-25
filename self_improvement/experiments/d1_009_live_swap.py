"""MG-D1-009: swap the LIVE mem_fts to full text (procedure proven on a copy in 17r). Backup: ~/backups/recall-f-20261125/.

Build mem_fts_full in short chunked transactions, then in ONE short BEGIN IMMEDIATE transaction: add docs indexed meanwhile,
check row counts, rename mem_fts -> mem_fts_trunc and mem_fts_full -> mem_fts. mem_fts_trunc is kept for rollback
(--rollback renames back). On a count mismatch nothing is swapped and mem_fts_full is dropped.
"""
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.expanduser("~/.claude/star/tools"))
import frank3_improver as FI  # noqa: E402

LIVE = os.environ.get("SWAP_DB") or os.path.expanduser("~/.local/share/agentzero/unified.db")
DDL = ("CREATE VIRTUAL TABLE mem_fts_full USING fts5(subject, text, content='', contentless_delete=1, "
       "tokenize='unicode61 remove_diacritics 2')")
c = sqlite3.connect(LIVE, timeout=30, isolation_level=None)
names = {r[0] for r in c.execute("select name from sqlite_master")}
out = {"ts": time.time()}


def add(rows):
    for did, sid, skey in rows:
        x = FI.source_text(c, sid, skey)
        if x:
            c.execute("insert into mem_fts_full(rowid, subject, text) values(?,?,?)", (did, str(x[0] or ""), str(x[1] or "")))


if "--rollback" in sys.argv:
    assert "mem_fts_trunc" in names, "nothing to roll back"
    c.execute("BEGIN IMMEDIATE")
    c.execute("ALTER TABLE mem_fts RENAME TO mem_fts_full")
    c.execute("ALTER TABLE mem_fts_trunc RENAME TO mem_fts")
    c.execute("COMMIT")
    print("rolled back: mem_fts is the truncated index again, full index kept as mem_fts_full")
    sys.exit(0)

assert "mem_fts_trunc" not in names and "mem_fts_full" not in names, "a previous swap is in place"
t = time.time()
c.execute(DDL)
docs = c.execute("select doc_id, source_id, source_key from mem_doc where canon_id=doc_id and fts=1").fetchall()
for i in range(0, len(docs), 2000):  # short write transactions: live writers wait at most one chunk
    c.execute("BEGIN IMMEDIATE")
    add(docs[i:i + 2000])
    c.execute("COMMIT")
out["build_s"] = round(time.time() - t, 1)
t = time.time()
c.execute("BEGIN IMMEDIATE")
have = {r[0] for r in c.execute("select id from mem_fts_full_docsize")}
delta = [d for d in c.execute("select doc_id, source_id, source_key from mem_doc where canon_id=doc_id and fts=1") if d[0] not in have]
add(delta)
n_old = c.execute("select count(*) from mem_fts_docsize").fetchone()[0]
n_new = c.execute("select count(*) from mem_fts_full_docsize").fetchone()[0]
if n_new != n_old:
    c.execute("ROLLBACK")
    c.execute("DROP TABLE mem_fts_full")
    sys.exit(f"row count mismatch old {n_old} new {n_new}; nothing swapped, mem_fts_full dropped")
c.execute("ALTER TABLE mem_fts RENAME TO mem_fts_trunc")
c.execute("ALTER TABLE mem_fts_full RENAME TO mem_fts")
c.execute("COMMIT")
out.update({"lock_s": round(time.time() - t, 2), "delta_docs": len(delta), "rows": n_new})
c.execute("insert into mem_fts(mem_fts) values('integrity-check')")
out["integrity"] = "ok"
print(json.dumps(out))
