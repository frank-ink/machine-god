"""Hardening tests for mg.bench_retrieval and mg.retrievers."""
import json
import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from mg import bench_retrieval as br
from mg import retrievers as R


def test_open_ro_path_with_space_and_question_mark(tmp_path):
    """open_ro on a path with space and '?' must work."""
    db_path = tmp_path / "my db?.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("create virtual table mem_fts using fts5(body)")
    conn.execute("insert into mem_fts(rowid, body) values(1, 'hello world')")
    conn.commit()
    conn.close()
    
    # Should open successfully
    ro_conn = br.open_ro(str(db_path))
    row = ro_conn.execute("select body from mem_fts where rowid=1").fetchone()
    assert row[0] == "hello world"
    ro_conn.close()


def test_open_ro_missing_file_raises(tmp_path):
    """Missing file must raise (mode=ro never creates)."""
    missing = tmp_path / "does_not_exist.db"
    with pytest.raises(sqlite3.OperationalError):
        br.open_ro(str(missing))
    assert not missing.exists()


def test_open_ro_insert_fails(tmp_path):
    """INSERT through returned connection must fail."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("create virtual table mem_fts using fts5(body)")
    conn.execute("insert into mem_fts(rowid, body) values(1, 'hello')")
    conn.commit()
    conn.close()
    
    ro_conn = br.open_ro(str(db_path))
    with pytest.raises(sqlite3.OperationalError):
        ro_conn.execute("insert into mem_fts(rowid, body) values(2, 'world')")
    ro_conn.close()


def test_open_ro_attach_fails(tmp_path):
    """ATTACH through returned connection must fail."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("create virtual table mem_fts using fts5(body)")
    conn.commit()
    conn.close()
    
    ro_conn = br.open_ro(str(db_path))
    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
        ro_conn.execute("attach database ':memory:' as aux")
    ro_conn.close()


def test_open_ro_create_fails(tmp_path):
    """CREATE through returned connection must fail."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("create virtual table mem_fts using fts5(body)")
    conn.commit()
    conn.close()
    
    ro_conn = br.open_ro(str(db_path))
    with pytest.raises(sqlite3.OperationalError):
        ro_conn.execute("create table foo(x)")
    ro_conn.close()


def test_open_ro_pragma_write_fails(tmp_path):
    """PRAGMA writes through returned connection must fail."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("create virtual table mem_fts using fts5(body)")
    conn.commit()
    conn.close()
    
    ro_conn = br.open_ro(str(db_path))
    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
        ro_conn.execute("pragma journal_mode=WAL")
    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
        ro_conn.execute("pragma query_only=OFF")
    ro_conn.close()


def test_retriever_ties_ordered_by_rowid(tmp_path):
    """Retriever ties must be ordered by rowid (deterministic tie-break)."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("create virtual table mem_fts using fts5(body)")
    # Insert multiple docs with identical text (same bm25 score)
    for i in range(1, 6):
        conn.execute("insert into mem_fts(rowid, body) values(?,?)", (i, "alpha beta gamma"))
    conn.commit()
    conn.close()
    
    ro_conn = br.open_ro(str(db_path))
    # All have same score, should be ordered by rowid ASC (since ORDER BY bm25, rowid)
    ids = R.fts_bm25_or(ro_conn, "alpha", 10)
    assert ids == [1, 2, 3, 4, 5]
    ro_conn.close()


def test_folded_retriever_finds_real_umlaut_and_folded_form(tmp_path):
    """Folded retriever must find doc containing real umlaut AND its folded form."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("create virtual table mem_fts using fts5(body)")
    # Doc with real umlaut
    conn.execute("insert into mem_fts(rowid, body) values(?,?)", (1, "Müller Straße"))
    # Doc with folded form
    conn.execute("insert into mem_fts(rowid, body) values(?,?)", (2, "Mueller Strasse"))
    conn.commit()
    conn.close()
    
    ro_conn = br.open_ro(str(db_path))
    
    # Query with umlaut should find both (union of raw and folded)
    ids = R.fts_bm25_or_folded(ro_conn, "Müller Straße", 10)
    assert set(ids) == {1, 2}
    
    # ASCII-folded query only finds the ASCII doc (FTS5 does not map ue->u); documented behaviour, not a requirement
    ids2 = R.fts_bm25_or_folded(ro_conn, "Mueller Strasse", 10)
    assert set(ids2) == {2}
    
    ro_conn.close()


def test_newest_first_still_works(tmp_path):
    """newest_first retriever must keep working (ignores query, highest rowid first)."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("create virtual table mem_fts using fts5(body)")
    for i in range(1, 6):
        conn.execute("insert into mem_fts(rowid, body) values(?,?)", (i, f"doc {i}"))
    conn.commit()
    conn.close()
    
    ro_conn = br.open_ro(str(db_path))
    ids = R.newest_first(ro_conn, "any query", 3)
    assert ids == [5, 4, 3]
    ro_conn.close()


def test_fts_bm25_or_still_works(tmp_path):
    """Original fts_bm25_or must still work."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("create virtual table mem_fts using fts5(body)")
    conn.execute("insert into mem_fts(rowid, body) values(1, 'alpha beta')")
    conn.execute("insert into mem_fts(rowid, body) values(2, 'gamma delta')")
    conn.commit()
    conn.close()
    
    ro_conn = br.open_ro(str(db_path))
    ids = R.fts_bm25_or(ro_conn, "alpha", 10)
    assert ids == [1]
    ro_conn.close()
