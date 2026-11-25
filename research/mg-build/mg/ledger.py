"""MG-2 ledger: mg_suite / mg_run / mg_trial / mg_prereg in a SQLite file given by --db. Stdlib only.
ASSUMPTION: DESIGN.md section 3 was not available on the mini PC; columns below are derived from the batch text
and Addendum A (mg_prereg columns are exact). Adjust here if the design differs."""
import json
import os
import sqlite3
import time
import uuid
from urllib.parse import unquote

# Protected live DB: an env-configurable trailing path (default "live/unified.db") plus real files, protected by inode as well
# (hardlinks/symlinks). Point MG_PROTECTED_DB (os.pathsep-separated) at your real DB and MG_LIVE_SUFFIX at its trailing "dir/name".
LIVE_SUFFIX = os.environ.get("MG_LIVE_SUFFIX", "live/unified.db").casefold()
LIVE_PATHS = [os.path.expanduser("~/.local/share/machine-god/unified.db")] + [
    os.path.expanduser(p) for p in os.environ.get("MG_PROTECTED_DB", "").split(os.pathsep) if p]

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

DDL_EXTRA = (
    "create unique index if not exists ux_mg_run_run_item_metric on mg_run(run_id, item_id, metric)",
    """create trigger if not exists trg_mg_trial_prereg_check
       before insert on mg_trial
       begin
         select case
           when not exists (
             select 1 from mg_prereg
             where mg_prereg.trial_id = new.trial_id
               and mg_prereg.bench_version = new.bench_version
           )
           then raise(abort, 'no preregistration')
         end;
       end""",
    """create trigger if not exists trg_mg_prereg_immutable_update
       before update on mg_prereg
       begin
         select raise(abort, 'prereg immutable');
       end""",
    """create trigger if not exists trg_mg_prereg_immutable_delete
       before delete on mg_prereg
       begin
         select raise(abort, 'prereg immutable');
       end""",
)


class PreregMissing(ValueError):
    pass


def _normalize_path_for_check(path: str) -> str:
    """Normalize a path for live DB checking: handle file: URIs, percent-decoding, query strings."""
    if path.startswith("file:"):
        # Strip scheme
        path = path[5:]
        # Drop query string
        if "?" in path:
            path = path.split("?", 1)[0]
        # Percent-decode
        path = unquote(path)
    return path


def _strip_sidecar_suffix(path: str) -> str:
    """Strip -wal, -shm, -journal suffixes for live DB checking."""
    for suffix in ("-wal", "-shm", "-journal"):
        if path.endswith(suffix):
            return path[:-len(suffix)]
    return path


def _is_live_path_candidate(path: str) -> bool:
    """Check if a normalized path matches the live DB pattern (component boundary)."""
    # Normalize separators
    norm = path.replace(os.sep, "/")
    # Check for /live/unified.db at component boundary (preceded by / or at start)
    # This means the path ends with /live/unified.db or is exactly live/unified.db
    if norm == LIVE_SUFFIX:
        return True
    if norm.endswith("/" + LIVE_SUFFIX):
        return True
    return False


def _same_file_exists(path: str) -> bool:
    """Check if path refers to the same file as any live path (handles hardlinks/symlinks)."""
    try:
        target_stat = os.stat(path)
    except OSError:
        return False
    for live in LIVE_PATHS:
        try:
            live_stat = os.stat(live)
            if (target_stat.st_dev == live_stat.st_dev and
                target_stat.st_ino == live_stat.st_ino):
                return True
        except OSError:
            continue
    return False


def guard_path(path):
    """Refuse the live unified.db (by resolved path suffix, URI, hardlinks, symlinks, case, sidecars)."""
    # Normalize for checking
    check_path = _normalize_path_for_check(path)
    check_path = _strip_sidecar_suffix(check_path)
    
    # Case-insensitive component boundary check
    if _is_live_path_candidate(check_path.casefold()):
        raise PermissionError("refuse live DB: " + path)
    
    # Hardlink/symlink check against actual live files
    if _same_file_exists(check_path):
        raise PermissionError("refuse live DB (hardlink/symlink): " + path)


def connect(path):
    guard_path(path)
    conn = sqlite3.connect(path, uri=False)
    ensure_schema(conn)
    return conn


def ensure_schema(conn):
    for s in DDL:
        conn.execute(s)
    for s in DDL_EXTRA:
        conn.execute(s)
    conn.commit()


def new_suite(conn, name, bench_version=None, n_items=None):
    cur = conn.execute("insert into mg_suite(name,bench_version,n_items,ts) values(?,?,?,?)", (name, bench_version, n_items, time.time()))
    conn.commit()
    return cur.lastrowid


def write_run_items(conn, run_id, suite_id, rows):
    """rows: iterable of (item_id, metric, score). Rejects NaN/inf scores."""
    # Validate all scores first (all-or-nothing)
    validated_rows = []
    for item_id, metric, score in rows:
        try:
            fscore = float(score)
        except (TypeError, ValueError):
            raise ValueError(f"invalid score for {item_id}/{metric}: {score!r}")
        if fscore != fscore or fscore == float('inf') or fscore == float('-inf'):
            raise ValueError(f"NaN or infinite score for {item_id}/{metric}: {score!r}")
        validated_rows.append((item_id, metric, fscore))
    
    now = time.time()
    conn.executemany("insert into mg_run(run_id,suite_id,item_id,metric,score,ts) values(?,?,?,?,?,?)",
                     [(run_id, suite_id, str(i), m, s, now) for i, m, s in validated_rows])
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


def _jsonify_value(v):
    """Convert dict/list to JSON string for SQLite storage."""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return v


def update_trial(conn, trial_id, **fields):
    """Update allowed mg_trial columns only (whitelist from PRAGMA table_info, never trial_id)."""
    # Get allowed columns
    cols = [r[1] for r in conn.execute("pragma table_info(mg_trial)")]
    allowed = [c for c in cols if c != "trial_id"]
    
    # Filter fields to allowed columns
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = [_jsonify_value(v) for v in updates.values()] + [trial_id]
    conn.execute(f"update mg_trial set {set_clause} where trial_id=?", values)
    conn.commit()


def claim_promo(conn, trial_id, bench_version, max_attempts):
    """Atomically claim a promo attempt slot.
    Returns True if claimed, False if max_attempts reached.
    """
    conn.execute("begin immediate")
    try:
        count = conn.execute(
            "select count(*) from mg_trial where bench_version=? and promo_attempted=1",
            (bench_version,)
        ).fetchone()[0]
        if count >= max_attempts:
            conn.rollback()
            return False
        conn.execute(
            "update mg_trial set promo_attempted=1 where trial_id=?",
            (trial_id,)
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise


def insert_trial_start(conn, trial_id, hypothesis, bench_version, **fields):
    """Insert a trial row with decision 'ABORTED' (crashed run leaves a trace).
    Uses whatever columns mg_trial currently has.
    """
    cols = [r[1] for r in conn.execute("pragma table_info(mg_trial)")]
    # Build values for all columns
    values = {}
    for col in cols:
        if col == "trial_id":
            values[col] = trial_id
        elif col == "ts":
            values[col] = time.time()
        elif col == "hypothesis":
            values[col] = hypothesis
        elif col == "bench_version":
            values[col] = bench_version
        elif col == "decision":
            values[col] = "ABORTED"
        elif col == "promo_attempted":
            values[col] = 0
        elif col == "detail":
            values[col] = json.dumps(fields.get("detail", {}), ensure_ascii=False)
        elif col in fields:
            values[col] = fields[col]
        else:
            values[col] = None
    
    placeholders = ", ".join("?" for _ in cols)
    col_names = ", ".join(cols)
    conn.execute(f"insert into mg_trial ({col_names}) values ({placeholders})", [values[c] for c in cols])
    conn.commit()
