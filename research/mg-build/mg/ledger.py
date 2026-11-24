"""MG-2 ledger: mg_suite / mg_run / mg_trial / mg_prereg in a SQLite file given by --db. Stdlib only.
ASSUMPTION: DESIGN.md section 3 was not available on the mini PC; columns below are derived from the batch text
and Addendum A (mg_prereg columns are exact). Adjust here if the design differs."""
import json
import sqlite3
import time
import uuid

LIVE_NAME = "unified.db"
TABLES = ("mg_suite", "mg_run", "mg_trial", "mg_prereg")
DDL = (
    "create table if not exists mg_suite(suite_id integer primary key autoincrement, name text not null, bench_version text, n_items integer, ts real)",
    "create table if not exists mg_run(run_id text not null, suite_id integer, item_id text not null, metric text not null, score real, ts real)",
    "create table if not exists mg_prereg(trial_id text primary key, hypothesis text, target_metric text, min_effect real, min_n integer, budget_s real, bench_version text, ts real)",
    "create table if not exists mg_trial(trial_id text primary key, ts real, hypothesis text, bench_version text, base_retriever text, cand_retriever text,"
    " stage_reached text, decision text, promo_attempted integer default 0, detail text)",
    "create index if not exists ix_mg_run_run on mg_run(run_id)",
    "create index if not exists ix_mg_trial_ts on mg_trial(ts)",
)


class PreregMissing(ValueError):
    pass


def guard_path(path):
    """Refuse any file named unified.db (the live DB), by resolved path."""
    import os
    if os.path.basename(os.path.realpath(path)) == LIVE_NAME:
        raise PermissionError("refuse live DB: " + path)


def connect(path):
    guard_path(path)
    conn = sqlite3.connect(path)
    ensure_schema(conn)
    return conn


def ensure_schema(conn):
    for s in DDL:
        conn.execute(s)
    conn.commit()


def new_suite(conn, name, bench_version=None, n_items=None):
    cur = conn.execute("insert into mg_suite(name,bench_version,n_items,ts) values(?,?,?,?)", (name, bench_version, n_items, time.time()))
    conn.commit()
    return cur.lastrowid


def write_run_items(conn, run_id, suite_id, rows):
    """rows: iterable of (item_id, metric, score)."""
    now = time.time()
    conn.executemany("insert into mg_run(run_id,suite_id,item_id,metric,score,ts) values(?,?,?,?,?,?)",
                     [(run_id, suite_id, str(i), m, float(s), now) for i, m, s in rows])
    conn.commit()


def write_prereg(conn, trial_id, hypothesis, target_metric, min_effect, min_n, budget_s, bench_version):
    conn.execute("insert into mg_prereg values(?,?,?,?,?,?,?,?)", (trial_id, hypothesis, target_metric, min_effect, min_n, budget_s, bench_version, time.time()))
    conn.commit()


def write_trial(conn, trial_id, hypothesis, bench_version, base_retriever, cand_retriever, stage_reached, decision, promo_attempted=0, detail=None):
    """Refuses (PreregMissing) when no mg_prereg row exists for trial_id."""
    if not conn.execute("select 1 from mg_prereg where trial_id=?", (trial_id,)).fetchone():
        raise PreregMissing("no preregistration for trial " + str(trial_id))
    conn.execute("insert into mg_trial values(?,?,?,?,?,?,?,?,?,?)", (trial_id, time.time(), hypothesis, bench_version, base_retriever, cand_retriever,
                 stage_reached, decision, int(promo_attempted), json.dumps(detail or {}, ensure_ascii=False)))
    conn.commit()


def run_scores(conn, run_id, metric):
    return {r[0]: r[1] for r in conn.execute("select item_id,score from mg_run where run_id=? and metric=?", (run_id, metric))}


def trials(conn, limit=20):
    cols = [r[1] for r in conn.execute("pragma table_info(mg_trial)")]
    return [dict(zip(cols, r)) for r in conn.execute("select * from mg_trial order by ts desc, rowid desc limit ?", (limit,))]


def promo_attempts(conn, bench_version):
    return conn.execute("select count(*) from mg_trial where bench_version is ? and promo_attempted=1", (bench_version,)).fetchone()[0]


def new_trial_id():
    return uuid.uuid4().hex[:16]
