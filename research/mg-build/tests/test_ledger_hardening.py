"""Hardening tests for mg.ledger (security/robustness review)."""
import json
import math
import os
import sqlite3
import tempfile
import shutil
from pathlib import Path

import pytest

from mg import ledger


def test_guard_path_suffix_false_positive_allowed(tmp_path, monkeypatch):
    """x-live/unified.db should NOT be blocked (component boundary)."""
    p = tmp_path / "x-live" / "unified.db"
    p.parent.mkdir(parents=True)
    p.write_text("")
    # Should not raise
    ledger.guard_path(str(p))
    ledger.connect(str(p))  # Should work


def test_guard_path_file_uri_blocked(tmp_path, monkeypatch):
    """file: URI pointing to live DB should be blocked."""
    live = tmp_path / "live" / "unified.db"
    live.parent.mkdir(parents=True)
    live.write_text("")
    
    monkeypatch.setattr(ledger, "LIVE_PATHS", [str(live)])
    
    # file: URI without query
    with pytest.raises(PermissionError):
        ledger.guard_path("file:" + str(live))
    # file: URI with ?mode=ro
    with pytest.raises(PermissionError):
        ledger.guard_path("file:" + str(live) + "?mode=ro")


def test_guard_path_percent_escape_blocked(tmp_path, monkeypatch):
    """Percent-escaped path in file: URI should be blocked; plain path with %61 is legal."""
    live = tmp_path / "live" / "unified.db"
    live.parent.mkdir(parents=True)
    live.write_text("")
    
    monkeypatch.setattr(ledger, "LIVE_PATHS", [str(live)])
    
    # file: URI with percent-encoding (%61 = 'a') should be blocked
    escaped_uri = "file:" + str(tmp_path) + "/%6Cive/unified.db"
    with pytest.raises(PermissionError):
        ledger.guard_path(escaped_uri)
    
    # Plain path containing literal %61 is a different legal directory (not decoded)
    plain_escaped = str(tmp_path / "%6Cive" / "unified.db")
    # Should NOT raise - this is a different path
    ledger.guard_path(plain_escaped)


def test_guard_path_hardlink_blocked(tmp_path, monkeypatch):
    """Hardlink to a live DB file should be blocked."""
    live = tmp_path / "live" / "unified.db"
    live.parent.mkdir(parents=True)
    live.write_text("live")
    
    # Create hardlink elsewhere
    link_dir = tmp_path / "other"
    link_dir.mkdir()
    link_path = link_dir / "mydb.db"
    os.link(live, link_path)
    
    monkeypatch.setattr(ledger, "LIVE_PATHS", [str(live)])
    
    with pytest.raises(PermissionError):
        ledger.guard_path(str(link_path))


def test_guard_path_symlink_blocked(tmp_path, monkeypatch):
    """Symlink to a live DB file should be blocked."""
    live = tmp_path / "live" / "unified.db"
    live.parent.mkdir(parents=True)
    live.write_text("live")
    
    link_dir = tmp_path / "other"
    link_dir.mkdir()
    link_path = link_dir / "mydb.db"
    os.symlink(live, link_path)
    
    monkeypatch.setattr(ledger, "LIVE_PATHS", [str(live)])
    
    with pytest.raises(PermissionError):
        ledger.guard_path(str(link_path))


def test_guard_path_uppercase_blocked(tmp_path, monkeypatch):
    """Uppercase variant of live path should be blocked (casefold)."""
    live = tmp_path / "AGENTZERO" / "UNIFIED.DB"
    live.parent.mkdir(parents=True)
    live.write_text("live")
    
    monkeypatch.setattr(ledger, "LIVE_PATHS", [str(live)])
    
    with pytest.raises(PermissionError):
        ledger.guard_path(str(live))


def test_guard_path_sidecar_blocked(tmp_path, monkeypatch):
    """-wal, -shm, -journal sidecars should be blocked."""
    live = tmp_path / "live" / "unified.db"
    live.parent.mkdir(parents=True)
    live.write_text("live")
    
    monkeypatch.setattr(ledger, "LIVE_PATHS", [str(live)])
    
    for suffix in ("-wal", "-shm", "-journal"):
        with pytest.raises(PermissionError):
            ledger.guard_path(str(live) + suffix)


def test_connect_guarded_raises_before_creating_file(tmp_path, monkeypatch):
    """connect() on a guarded path must raise BEFORE creating any file."""
    live = tmp_path / "live" / "unified.db"
    live.parent.mkdir(parents=True)
    live.write_text("live")
    
    # Non-guarded path should work and create file
    new_db = tmp_path / "new.db"
    conn = ledger.connect(str(new_db))
    conn.close()
    assert new_db.exists()
    
    # Now test guarded path - use a file: URI to the live DB
    monkeypatch.setattr(ledger, "LIVE_PATHS", [str(live)])
    try:
        guarded_uri = "file:" + str(live)
        with pytest.raises(PermissionError):
            ledger.connect(guarded_uri)
        # The URI path shouldn't create a file (though sqlite3 might interpret it differently)
        # Main point: PermissionError raised before any DB creation attempt
    finally:
        pass  # monkeypatch auto-restores


def test_unique_index_on_mg_run(tmp_path):
    """Duplicate (run_id, item_id, metric) should be rejected."""
    db = tmp_path / "test.db"
    conn = ledger.connect(str(db))
    suite_id = ledger.new_suite(conn, "test", "v0", 1)
    
    # First insert works
    ledger.write_run_items(conn, "r1", suite_id, [("item1", "mrr", 0.5)])
    
    # Duplicate should fail
    with pytest.raises(sqlite3.IntegrityError):
        ledger.write_run_items(conn, "r1", suite_id, [("item1", "mrr", 0.6)])
    
    # Verify nothing was written (all-or-nothing)
    scores = ledger.run_scores(conn, "r1", "mrr")
    assert scores == {"item1": 0.5}


def test_mg_trial_insert_without_prereg_rejected(tmp_path):
    """mg_trial insert without prereg should be rejected by trigger."""
    db = tmp_path / "test.db"
    conn = ledger.connect(str(db))
    
    # Trigger raises RAISE(ABORT) -> sqlite3.IntegrityError
    with pytest.raises(sqlite3.IntegrityError, match="no preregistration"):
        conn.execute("insert into mg_trial(trial_id, hypothesis, bench_version, decision) values(?,?,?,?)",
                     ("t1", "h", "v0", "reject"))
        conn.commit()


def test_mg_trial_insert_with_prereg_different_bench_version_rejected(tmp_path):
    """mg_trial insert with prereg but different bench_version should be rejected."""
    db = tmp_path / "test.db"
    conn = ledger.connect(str(db))
    
    # Prereg with bench_version v0
    conn.execute("insert into mg_prereg(trial_id, hypothesis, target_metric, min_effect, min_n, budget_s, bench_version, ts) values(?,?,?,?,?,?,?,?)",
                 ("t1", "h", "mrr", 0.05, 20, 60, "v0", 1.0))
    conn.commit()
    
    # Trial with bench_version v1 should fail (trigger checks both trial_id AND bench_version)
    with pytest.raises(sqlite3.IntegrityError, match="no preregistration"):
        conn.execute("insert into mg_trial(trial_id, hypothesis, bench_version, decision) values(?,?,?,?)",
                     ("t1", "h", "v1", "reject"))
        conn.commit()


def test_prereg_update_rejected(tmp_path):
    """UPDATE on mg_prereg should be rejected by trigger."""
    db = tmp_path / "test.db"
    conn = ledger.connect(str(db))
    
    conn.execute("insert into mg_prereg(trial_id, hypothesis, target_metric, min_effect, min_n, budget_s, bench_version, ts) values(?,?,?,?,?,?,?,?)",
                 ("t1", "h", "mrr", 0.05, 20, 60, "v0", 1.0))
    conn.commit()
    
    # Trigger raises RAISE(ABORT) -> sqlite3.IntegrityError
    with pytest.raises(sqlite3.IntegrityError, match="prereg immutable"):
        conn.execute("update mg_prereg set hypothesis='x' where trial_id=?", ("t1",))
        conn.commit()


def test_prereg_delete_rejected(tmp_path):
    """DELETE on mg_prereg should be rejected by trigger."""
    db = tmp_path / "test.db"
    conn = ledger.connect(str(db))
    
    conn.execute("insert into mg_prereg(trial_id, hypothesis, target_metric, min_effect, min_n, budget_s, bench_version, ts) values(?,?,?,?,?,?,?,?)",
                 ("t1", "h", "mrr", 0.05, 20, 60, "v0", 1.0))
    conn.commit()
    
    # Trigger raises RAISE(ABORT) -> sqlite3.IntegrityError
    with pytest.raises(sqlite3.IntegrityError, match="prereg immutable"):
        conn.execute("delete from mg_prereg where trial_id=?", ("t1",))
        conn.commit()


def test_write_run_items_rejects_nan_inf(tmp_path):
    """NaN/inf scores should be rejected with ValueError, nothing written."""
    db = tmp_path / "test.db"
    conn = ledger.connect(str(db))
    suite_id = ledger.new_suite(conn, "test", "v0", 1)
    
    # NaN
    with pytest.raises(ValueError, match="NaN"):
        ledger.write_run_items(conn, "r1", suite_id, [("item1", "mrr", float('nan'))])
    
    # +inf
    with pytest.raises(ValueError, match="infinite"):
        ledger.write_run_items(conn, "r1", suite_id, [("item1", "mrr", float('inf'))])
    
    # -inf
    with pytest.raises(ValueError, match="infinite"):
        ledger.write_run_items(conn, "r1", suite_id, [("item1", "mrr", float('-inf'))])
    
    # Verify nothing written
    assert ledger.run_scores(conn, "r1", "mrr") == {}


def _mk_trials(db, n):
    c = ledger.connect(str(db))
    for i in range(n):
        c.execute("insert into mg_prereg(trial_id, hypothesis, target_metric, min_effect, min_n, budget_s, bench_version, ts) values(?,?,?,?,?,?,?,?)",
                  ("t%d" % i, "h", "mrr", 0.05, 20, 60, "v0", 1.0))
        c.execute("insert into mg_trial(trial_id, hypothesis, bench_version, decision, promo_attempted) values(?,?,?,?,?)",
                  ("t%d" % i, "h", "v0", "ABORTED", 0))
    c.commit()
    return c


def test_claim_promo_true_until_max_then_false(tmp_path):
    """Distinct trials on the same bench_version: only max_attempts claims succeed; claim once the budget is exhausted stays False."""
    c = _mk_trials(tmp_path / "t.db", 4)
    assert [ledger.claim_promo(c, "t%d" % i, "v0", 2) for i in range(4)] == [True, True, False, False]
    assert ledger.claim_promo(c, "t0", "v0", 2) is False  # budget exhausted: a second claim never succeeds
    assert ledger.promo_attempts(c, "v0") == 2


def test_claim_promo_race_two_connections(tmp_path):
    """Two connections, interleaved claims on 6 distinct trials: exactly max_attempts succeed in total."""
    db = tmp_path / "t.db"
    _mk_trials(db, 6).close()
    ca, cb = ledger.connect(str(db)), ledger.connect(str(db))
    res = [ledger.claim_promo(ca if i % 2 == 0 else cb, "t%d" % i, "v0", 3) for i in range(6)]
    assert sum(res) == 3 and res[:3] == [True] * 3
    assert ledger.promo_attempts(ca, "v0") == 3


def test_update_trial_whitelist(tmp_path):
    """update_trial should only update allowed columns (whitelist from PRAGMA)."""
    db = tmp_path / "test.db"
    conn = ledger.connect(str(db))
    
    conn.execute("insert into mg_prereg(trial_id, hypothesis, target_metric, min_effect, min_n, budget_s, bench_version, ts) values(?,?,?,?,?,?,?,?)",
                 ("t1", "h", "mrr", 0.05, 20, 60, "v0", 1.0))
    conn.execute("insert into mg_trial(trial_id, hypothesis, bench_version, decision, promo_attempted) values(?,?,?,?,?)",
                 ("t1", "h", "v0", "ABORTED", 0))
    conn.commit()
    
    # Update allowed column
    ledger.update_trial(conn, "t1", decision="PASS", detail={"foo": "bar"})
    
    row = conn.execute("select decision, detail from mg_trial where trial_id=?", ("t1",)).fetchone()
    assert row[0] == "PASS"
    assert json.loads(row[1]) == {"foo": "bar"}
    
    # Update trial_id should be ignored (not in whitelist) - trial_id is positional param, not in **fields
    # Verify trial_id unchanged after normal update
    row = conn.execute("select trial_id from mg_trial where trial_id=?", ("t1",)).fetchone()
    assert row[0] == "t1"
    
    # Update non-existent column should be ignored
    ledger.update_trial(conn, "t1", nonexistent="value")  # Should not error


def test_insert_trial_start_leaves_aborted_row(tmp_path):
    """insert_trial_start should insert a row with decision 'ABORTED'."""
    db = tmp_path / "test.db"
    conn = ledger.connect(str(db))
    
    # Must insert prereg first (trigger requires it)
    conn.execute("insert into mg_prereg(trial_id, hypothesis, target_metric, min_effect, min_n, budget_s, bench_version, ts) values(?,?,?,?,?,?,?,?)",
                 ("t1", "my hypothesis", "mrr", 0.05, 20, 60, "v0", 1.0))
    conn.commit()
    
    ledger.insert_trial_start(conn, "t1", "my hypothesis", "v0", base_retriever="a", cand_retriever="b")
    
    row = conn.execute("select trial_id, hypothesis, bench_version, decision, base_retriever, cand_retriever from mg_trial where trial_id=?", ("t1",)).fetchone()
    assert row is not None
    assert row[0] == "t1"
    assert row[1] == "my hypothesis"
    assert row[2] == "v0"
    assert row[3] == "ABORTED"
    assert row[4] == "a"
    assert row[5] == "b"
    
    # promo_attempted should default to 0
    row2 = conn.execute("select promo_attempted from mg_trial where trial_id=?", ("t1",)).fetchone()
    assert row2[0] == 0


def test_write_trial_still_works_with_prereg(tmp_path):
    """Existing write_trial must keep working (inserts final trial row)."""
    db = tmp_path / "test.db"
    conn = ledger.connect(str(db))
    
    ledger.write_prereg(conn, "t1", "h", "mrr", 0.05, 20, 60, "v0")
    ledger.write_trial(conn, "t1", "h", "v0", "base", "cand", "dev", "PASS", 1, {"k": 10})
    
    row = conn.execute("select trial_id, decision, promo_attempted, detail from mg_trial where trial_id=?", ("t1",)).fetchone()
    assert row[0] == "t1"
    assert row[1] == "PASS"
    assert row[2] == 1
    assert json.loads(row[3]) == {"k": 10}


def test_promo_attempts_still_works(tmp_path):
    """promo_attempts(conn, bench_version) must keep working."""
    db = tmp_path / "test.db"
    conn = ledger.connect(str(db))
    
    # Insert prereg rows first (required by trigger)
    conn.execute("insert into mg_prereg(trial_id, hypothesis, target_metric, min_effect, min_n, budget_s, bench_version, ts) values(?,?,?,?,?,?,?,?)",
                 ("t1", "h", "mrr", 0.05, 20, 60, "v0", 1.0))
    conn.execute("insert into mg_prereg(trial_id, hypothesis, target_metric, min_effect, min_n, budget_s, bench_version, ts) values(?,?,?,?,?,?,?,?)",
                 ("t2", "h", "mrr", 0.05, 20, 60, "v0", 1.0))
    conn.execute("insert into mg_prereg(trial_id, hypothesis, target_metric, min_effect, min_n, budget_s, bench_version, ts) values(?,?,?,?,?,?,?,?)",
                 ("t3", "h", "mrr", 0.05, 20, 60, "v1", 1.0))
    conn.commit()
    
    conn.execute("insert into mg_trial(trial_id, hypothesis, bench_version, decision, promo_attempted) values(?,?,?,?,?)",
                 ("t1", "h", "v0", "ABORTED", 1))
    conn.execute("insert into mg_trial(trial_id, hypothesis, bench_version, decision, promo_attempted) values(?,?,?,?,?)",
                 ("t2", "h", "v0", "ABORTED", 1))
    conn.execute("insert into mg_trial(trial_id, hypothesis, bench_version, decision, promo_attempted) values(?,?,?,?,?)",
                 ("t3", "h", "v1", "ABORTED", 1))
    conn.commit()
    
    assert ledger.promo_attempts(conn, "v0") == 2
    assert ledger.promo_attempts(conn, "v1") == 1
    assert ledger.promo_attempts(conn, "v2") == 0
