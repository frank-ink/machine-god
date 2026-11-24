import sqlite3

import pytest

from mg import ledger


def user_tables(c):
    return sorted(r[0] for r in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'"))


def test_schema_idempotent_and_no_foreign_table_touched(tmp_path):
    c = sqlite3.connect(str(tmp_path / "l.db"))
    c.execute("create table other(x)"); c.execute("insert into other values(1)"); c.commit()
    before = user_tables(c)
    ledger.ensure_schema(c); ledger.ensure_schema(c)
    after = user_tables(c)
    assert set(after) - set(before) == set(ledger.TABLES) and "other" in after
    assert c.execute("select x from other").fetchall() == [(1,)]
    idx = {r[0] for r in c.execute("select name from sqlite_master where type='index'")}
    assert {"ix_mg_run_run", "ix_mg_trial_ts"} <= idx


def test_round_trip_runs_and_trials(tmp_path):
    c = ledger.connect(str(tmp_path / "l.db"))
    s = ledger.new_suite(c, "dev", "v0", 2)
    ledger.write_run_items(c, "r1", s, [("a", "mrr", 0.5), ("b", "mrr", 1.0), ("a", "hit1", 0)])
    assert ledger.run_scores(c, "r1", "mrr") == {"a": 0.5, "b": 1.0} and ledger.run_scores(c, "r1", "hit1") == {"a": 0.0}
    ledger.write_prereg(c, "t1", "h", "mrr", 0.05, 20, 60, "v0")
    ledger.write_trial(c, "t1", "h", "v0", "x:b", "x:c", "dev", "reject", 0, {"k": 1})
    t = ledger.trials(c, 5)
    assert len(t) == 1 and t[0]["decision"] == "reject" and t[0]["trial_id"] == "t1"


def test_write_trial_refuses_without_prereg(tmp_path):
    c = ledger.connect(str(tmp_path / "l.db"))
    with pytest.raises(ledger.PreregMissing):
        ledger.write_trial(c, "nope", "h", "v0", "b", "c", "dev", "reject")
    assert ledger.trials(c) == []


def test_prereg_columns_exact(tmp_path):
    c = ledger.connect(str(tmp_path / "l.db"))
    assert [r[1] for r in c.execute("pragma table_info(mg_prereg)")] == ["trial_id", "hypothesis", "target_metric", "min_effect", "min_n", "budget_s", "bench_version", "ts"]


def test_live_db_path_refused(tmp_path):
    d = tmp_path / "live"; d.mkdir()
    with pytest.raises(PermissionError):
        ledger.connect(str(d / "unified.db"))
    assert not (d / "unified.db").exists()
