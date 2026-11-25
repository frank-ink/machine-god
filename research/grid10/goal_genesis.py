"""goal_genesis.py -- E3 Goal Genesis (Draft ChatGPT Round 6, 2026-11-25), SHADOW: goals are only ledger entries, no execution, no authorization.

Source exclusively E2 findings (f3_endo_befund), each finding is resolved anew at the time of goal formation (endogenous.resolve); unresolvable -> no goal (E3.02);
Finding older than STALE_S is re-validated and noted as such (E3.03). 'no_goal' alone is a system state, not a motivation -> ABSTAIN (E3.07, no employment compulsion).
Goal statement arises from the concrete finding (type, count value, evidence), generation_method='rule_template': this is RULE-BASED and must not be referred to as emergent goal genesis.
Duplicate (same dedup_key open, or completed with same evidence_digest) -> no new goal (E3.04/E4.07). Contradiction findings retain
status 'open_uncertain' (E3.06). authority_scope is ALWAYS 'none', regardless of what is requested (E3.08). Persistence in f3_goal (E3.09). Switches frank3.goal.mode, frank3.kill (E3.10)."""
import hashlib
import json
import time

import endogenous

MODE_KEY, STALE_S, MAX_OPEN, GENERATOR = "frank3.goal.mode", 3600.0, 8, "goal_genesis/1"
DDL = ("create table if not exists f3_goal(goal_id text primary key, parent_goal_id text, origin_event_id text, origin_organ text, goal_statement text, motivation text,"
       " evidence_refs text, expected_information_gain real, priority real, estimated_resource_cost real, status text, created_at real, review_at real, completion_criteria text,"
       " authority_scope text, generator_version text, evidence_digest text, dedup_key text, last_review_at real, generation_method text, salience real, fatigue real default 0,"
       " fatigue_ts real, selections integer default 0)",
       "create table if not exists f3_goal_log(id integer primary key autoincrement, ts real, goal_id text, event text, detail text)")
COST = {"gap": 0.2, "contradiction": 0.35}
TEMPLATE = {"gap": "Resolve knowledge gap: %s", "contradiction": "Investigate contradiction: %s"}


def _h(*a):
    return hashlib.sha256("|".join(map(str, a)).encode()).hexdigest()[:16]


def off(conn):
    r = conn.execute("select wert from star_konfig where schluessel=?", (MODE_KEY,)).fetchone()
    k = conn.execute("select wert from star_konfig where schluessel='frank3.kill'").fetchone()
    return bool((r and r[0] == "off") or (k and k[0] == "1"))


def genesis(conn, now=None, requested_scope=None):
    """-> Liste neu angelegter goal_id (leer = ABSTAIN / nichts Neues)."""
    now = time.time() if now is None else now
    if off(conn):
        return []
    for d in DDL:
        conn.execute(d)
    made = []
    rows = conn.execute("select id,bucket,kind,key,statement,evidence_ref from f3_endo_befund where id in (select max(id) from f3_endo_befund group by key) order by id").fetchall() \
        if conn.execute("select 1 from sqlite_master where name='f3_endo_befund'").fetchone() else []
    for bid, bucket, kind, key, stmt, ref_j in rows:
        if key == "kein_ziel" or kind not in TEMPLATE:
            continue  # E3.07: missing goal is not a motivation
        ref = json.loads(ref_j)
        ok, n = endogenous.resolve(conn, ref)
        if not ok:
            conn.execute("insert into f3_goal_log(ts,goal_id,event,detail) values(?,?,?,?)", (now, None, "verworfen_evidenz", key))
            continue  # E3.02
        digest, dedup = _h(ref["table"], ref["where"], n), _h(kind, key)
        dup = conn.execute("select 1 from f3_goal where dedup_key=? and (status in ('offen','offen_unsicher') or (status='abgeschlossen' and evidence_digest=?))", (dedup, digest)).fetchone()
        if dup or conn.execute("select count(*) from f3_goal where status in ('offen','offen_unsicher')").fetchone()[0] >= MAX_OPEN:
            continue  # E3.04, E4.08
        stale = now - bucket * endogenous.BUCKET_S > STALE_S
        gid = _h("goal", dedup, digest, int(now))
        sal = min(1.0, __import__("math").log1p(n) / __import__("math").log1p(100))
        conn.execute("insert into f3_goal values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,0)",
                     (gid, None, "finding:%d" % bid, "endogenous.observe", TEMPLATE[kind] % stmt, "revalidiert (Befund alt)" if stale else "Befund frisch aufgeloest", json.dumps([ref]),
                      round(min(1.0, 0.3 + 0.7 * sal), 4), round(0.5 + 0.5 * sal, 4), COST[kind], "offen_unsicher" if kind == "contradiction" else "offen", now, now + 86400,
                      "Evidence reference yields a changed count or an assessment/clarification exists", "none", GENERATOR, digest, dedup, now if stale else None, "rule_template", sal, now))
        conn.execute("insert into f3_goal_log(ts,goal_id,event,detail) values(?,?,?,?)", (now, gid, "erzeugt", json.dumps({"kind": kind, "key": key, "requested_scope_ignored": requested_scope})))
        made.append(gid)
    conn.commit()
    return made
