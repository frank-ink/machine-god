"""goal_competition.py -- E4 goal competition + fatigue, GOAL_COMPETITION_V1 (draft ChatGPT round 6, 2026-11-25), SHADOW: selects only one goal, executes NOTHING.

score = +0.30 salience +0.30 information_gain +0.25 evidence_quality +0.15 novelty -0.25 fatigue -0.15 resource_cost; permitted from THETA=0.45, otherwise ABSTAIN.
evidence_quality is newly determined from reference at EVERY competition (resolve ok -> 1, otherwise candidate drops out, E4.06). novelty = 1/(1+selections).
Fatigue: on selection f <- f + 0.25*(1-f); all others decay f*exp(-dt/TAU), TAU=1800 s (3*TAU rest -> ~5 %). Tie: highest score, then smallest goal_id (deterministic).
Only status open/open_uncertain are candidates (completed are not chosen again without new finding, E4.07). Parameters are initial values (hypotheses), not calibrated."""
import json
import math
import time

import endogenous
import goal_genesis as gg

RULE_VERSION, THETA, TAU = "GOAL_COMPETITION_V1", 0.45, 1800.0
W = {"salience": 0.30, "gain": 0.30, "evidence": 0.25, "novelty": 0.15, "fatigue": -0.25, "cost": -0.15}
LOG = "create table if not exists f3_goal_comp_log(id integer primary key autoincrement, ts real, goal_id text, score real, parts text, abstain integer, n_candidates integer, rule_version text)"


def _decay(conn, now):
    for gid, f, ts in conn.execute("select goal_id,fatigue,fatigue_ts from f3_goal where status in ('offen','offen_unsicher')").fetchall():
        nf = (f or 0.0) * math.exp(-max(0.0, now - (ts or now)) / TAU)
        conn.execute("update f3_goal set fatigue=?, fatigue_ts=? where goal_id=?", (nf, now, gid))


def compete(conn, now=None):
    """-> (goal_id|None, score_je_kandidat{goal_id:{score,parts}}); writes ledger and fatigue, executes nothing."""
    now = time.time() if now is None else now
    if gg.off(conn):
        return None, {}
    for d in gg.DDL:
        conn.execute(d)
    conn.execute(LOG)
    _decay(conn, now)
    scores = {}
    for gid, sal, gain, cost, fat, sel, refs in conn.execute(
            "select goal_id,salience,expected_information_gain,estimated_resource_cost,fatigue,selections,evidence_refs from f3_goal where status in ('offen','offen_unsicher')").fetchall():
        ok = all(endogenous.resolve(conn, r)[0] for r in json.loads(refs))
        if not ok:
            conn.execute("insert into f3_goal_log(ts,goal_id,event,detail) values(?,?,?,?)", (now, gid, "kandidat_verworfen", "Evidenz nicht mehr aufloesbar"))
            continue
        parts = {"salience": sal or 0.0, "gain": gain or 0.0, "evidence": 1.0, "novelty": 1.0 / (1 + (sel or 0)), "fatigue": fat or 0.0, "cost": cost or 0.0}
        used = conn.execute("select attempt_id,evaluation_status from f3_goal_attempt where goal_id=? and evaluation_status is not null order by created_at desc limit 1", (gid,)).fetchone() \
            if conn.execute("select 1 from sqlite_master where name='f3_goal_attempt'").fetchone() else None  # E5.12: Result of earlier attempts demonstrably feeds into selection (via expected_information_gain)
        scores[gid] = {"score": round(sum(W[k] * parts[k] for k in W), 6), "parts": parts, "used_attempt": list(used) if used else None}
    best = sorted(scores, key=lambda g: (-scores[g]["score"], g))[:1]
    pick = best[0] if best and scores[best[0]]["score"] >= THETA else None
    if pick:
        conn.execute("update f3_goal set fatigue=fatigue+0.25*(1-fatigue), selections=selections+1, fatigue_ts=? where goal_id=?", (now, pick))
    conn.execute("insert into f3_goal_comp_log(ts,goal_id,score,parts,abstain,n_candidates,rule_version) values(?,?,?,?,?,?,?)",
                 (now, pick, scores[pick]["score"] if pick else (scores[best[0]]["score"] if best else None), json.dumps(scores.get(pick or (best[0] if best else ""), {})),
                  0 if pick else 1, len(scores), RULE_VERSION))
    conn.commit()
    return pick, scores


def complete(conn, goal_id, now=None):
    conn.execute("update f3_goal set status='abgeschlossen', last_review_at=? where goal_id=?", (time.time() if now is None else now, goal_id))
    conn.commit()
