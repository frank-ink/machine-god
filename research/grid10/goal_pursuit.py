"""goal_pursuit.py -- E5 Zielverfolgung und kausaler Reentry (Entwurf ChatGPT Runde 7, 2026-11-25), SHADOW, nur lokal und lesend.

a Zielbindung: ein gewaehltes Ziel -> genau ein Versuch (attempt_id = Hash aus goal_id und Auswahlzaehler, idempotent).
b Klassenbedarf: V2 mit turn_origin='endogenous', Zieltext als Quelle, KEIN fingierter Nutzertext (nur Protokoll, nichts wird dadurch ausgefuehrt).
c Prognose vor der Bearbeitung, zusammen mit den Erfolgskriterien in frozen_hash eingefroren; bei Abweichung -> UNVERIFIABLE, das bearbeitende Organ aendert Kriterien nie.
d Bearbeitung: eine lesende Erkenntnisaufgabe auf der Evidenzreferenz des Ziels (Anzahl neu zaehlen, bis zu 5 Zeilen-IDs), unter sqlite-Authorizer (nur SELECT/READ/FUNCTION).
   Das ist eine flache Beschreibung, KEINE tiefe Untersuchung; Prognosefehler entstehen praktisch nur, wenn sich die Welt zwischen Bindung und Bearbeitung aendert.
e Evaluation gegen die vorab fixierten Kriterien: SATISFIED | PARTIAL | FAILED | UNVERIFIABLE (fehlende Evidenz zaehlt nie als Erfolg; veralteter Ausgangszustand hoechstens PARTIAL).
f Reentry: Ergebnis erzeugt genau einen E2-Befund je Versuch (Art 'ergebnis', informativ, erzeugt kein Ziel) oder bei Prognosefehler/Fehlschlag Art 'luecke' (erzeugt ueber E3 ein Untersuchungsziel).
   Rueckwirkung auf E4: erwartete Informationsgewinn steigt bei Prognosefehler, erfuellte Ziele werden abgeschlossen; compete() protokolliert den benutzten Versuch."""
import hashlib
import json
import re
import sqlite3
import time

import class_demand_v2 as v2
import endogen
import goal_genesis as gg

EVAL_VERSION, PE_REL, SAMPLE = "goal_pursuit_eval/1", 0.2, 5
DDL = ("create table if not exists f3_goal_attempt(attempt_id text primary key, goal_id text, origin_event_id text, state_before_ref text, class_demand text, prediction text,"
       " completion_criteria text, frozen_hash text, expected_information_gain real, observed_result text, evidence_refs text, evaluation_status text, prediction_error real,"
       " proposed_state_delta text, state_after_ref text, reentry_event_id text, evaluator_version text, created_at real, finished_at real)",)
_NAME = re.compile(r"^[A-Za-z0-9_]+$")
_OK = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}


def _h(*a):
    return hashlib.sha256("|".join(map(str, a)).encode()).hexdigest()[:16]


def _auth(action, *_):
    return sqlite3.SQLITE_OK if action in _OK else sqlite3.SQLITE_DENY


def _count(conn, ref, ids=False):
    if not _NAME.match(ref["table"]) or ";" in ref["where"]:
        raise ValueError("unzulaessige Referenz")
    p = tuple(ref.get("params", ()))
    n = conn.execute("select count(*) from %s where %s" % (ref["table"], ref["where"]), p).fetchone()[0]
    s = [r[0] for r in conn.execute("select rowid from %s where %s order by rowid limit %d" % (ref["table"], ref["where"], SAMPLE), p).fetchall()] if ids else []
    return n, s


def bind(conn, goal_id, now=None):
    """E5a-c. -> attempt_id oder None (Kill/ABSTAIN/unbekanntes Ziel). Idempotent je Auswahl."""
    now = time.time() if now is None else now
    if gg.off(conn) or not goal_id:
        return None
    conn.execute(DDL[0])
    g = conn.execute("select goal_statement,evidence_refs,authority_scope,selections,expected_information_gain,origin_event_id from f3_goal where goal_id=?", (goal_id,)).fetchone()
    if not g:
        return None
    stmt, refs_j, scope, sel, gain, origin = g
    aid = _h("attempt", goal_id, sel)
    if conn.execute("select 1 from f3_goal_attempt where attempt_id=?", (aid,)).fetchone():
        return aid
    refs = json.loads(refs_j)
    cd = v2.derive("", goal=stmt, turn_origin="endogenous", goal_id=goal_id)
    if scope != "none":  # E5.11: nie ueber eigene Rechte hinaus; Versuch wird protokolliert, aber nicht bearbeitet
        conn.execute("insert into f3_goal_attempt values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (aid, goal_id, origin, "{}", json.dumps({"turn_origin": cd["turn_origin"], "selected_classes": cd["selected_classes"]}), "{}", "{}", "", gain,
                      json.dumps({"abbruch": "authority_scope"}), json.dumps(refs), "FAILED", None, "{}", "{}", None, EVAL_VERSION, now, now))
        conn.commit()
        return aid
    n0 = []
    for r in refs:
        try:
            n0.append(_count(conn, r)[0])
        except Exception:
            n0.append(None)
    before = {"refs": refs, "n_now": n0, "stale": any(n != r["n"] for n, r in zip(n0, refs))}
    exp = n0[0] if n0 and n0[0] is not None else None
    pred = {"metric": "count", "distance": "abs(n_obs-n_exp)/max(1,n_exp)", "expected_n": exp}
    crit = {"requires": ["n_obs", "sample_ids"], "min_sample": min(SAMPLE, exp or 0), "stale_allows": "PARTIAL"}
    conn.execute("insert into f3_goal_attempt values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (aid, goal_id, origin, json.dumps(before), json.dumps({"turn_origin": cd["turn_origin"], "selected_classes": cd["selected_classes"], "abstain": cd["abstain"]}),
                  json.dumps(pred), json.dumps(crit), _h(json.dumps(pred, sort_keys=True), json.dumps(crit, sort_keys=True), gain), gain, None, json.dumps(refs), None, None, None, None, None,
                  EVAL_VERSION, now, None))
    conn.commit()
    return aid


def process(conn, aid, now=None):
    """E5d-f. Idempotent: fertige Versuche bleiben unveraendert (kein doppelter Reentry)."""
    now = time.time() if now is None else now
    if gg.off(conn):
        return None
    row = conn.execute("select goal_id,state_before_ref,prediction,completion_criteria,frozen_hash,expected_information_gain,evidence_refs,evaluation_status from f3_goal_attempt where attempt_id=?", (aid,)).fetchone()
    if not row or row[7] is not None:
        return aid if row else None
    gid, before_j, pred_j, crit_j, fh, gain, refs_j, _ = row
    pred, crit, before, refs = json.loads(pred_j), json.loads(crit_j), json.loads(before_j), json.loads(refs_j)
    obs, status, pe = {}, "UNVERIFIABLE", None
    if _h(json.dumps(pred, sort_keys=True), json.dumps(crit, sort_keys=True), gain) != fh:
        obs = {"abbruch": "Prognose/Kriterien nach Einfrieren veraendert"}
    else:
        conn.set_authorizer(_auth)
        try:
            n_obs, sample = _count(conn, refs[0], ids=True)
            obs = {"n_obs": n_obs, "sample_ids": sample}
            pe = abs(n_obs - pred["expected_n"]) / max(1, pred["expected_n"]) if pred["expected_n"] is not None else None
            ok = pe is not None and len(sample) >= crit["min_sample"] and pe < PE_REL
            status = "FAILED" if pe is None else ("SATISFIED" if ok and not before["stale"] else "PARTIAL")
        except sqlite3.DatabaseError as e:
            obs = {"abbruch": type(e).__name__}
            status = "UNVERIFIABLE" if "no such" in str(e) else "FAILED"
        except Exception as e:
            obs, status = {"abbruch": type(e).__name__}, "FAILED"
        finally:
            conn.set_authorizer(None)
    err = pe is not None and pe >= PE_REL
    delta = {"goal_status": "abgeschlossen"} if status == "SATISFIED" else ({"expected_information_gain": "+0.2"} if err or status in ("FAILED", "PARTIAL") else {})
    if delta.get("goal_status"):
        conn.execute("update f3_goal set status='abgeschlossen', last_review_at=? where goal_id=?", (now, gid))
    if delta.get("expected_information_gain"):
        conn.execute("update f3_goal set expected_information_gain=min(1.0, expected_information_gain+0.2) where goal_id=?", (gid,))
    after = conn.execute("select status,expected_information_gain from f3_goal where goal_id=?", (gid,)).fetchone()
    reentry = _h("reentry", aid)
    kind = "luecke" if (err or status in ("FAILED", "UNVERIFIABLE", "PARTIAL")) else "ergebnis"
    conn.execute(endogen.DDL[1])
    cur = conn.execute("insert or ignore into f3_endo_befund(bucket,kind,statement,evidence_ref,key) values(?,?,?,?,?)",
                       (int(now // endogen.BUCKET_S), kind, "Versuch %s: %s%s" % (aid, status, " (Prognosefehler %.2f)" % pe if err else ""),
                        json.dumps({"table": "f3_goal_attempt", "where": "attempt_id=? and evaluation_status=?", "params": [aid, status], "n": 1}), "versuch:" + gid))
    conn.execute("update f3_goal_attempt set observed_result=?, evaluation_status=?, prediction_error=?, proposed_state_delta=?, state_after_ref=?, reentry_event_id=?, finished_at=? where attempt_id=?",
                 (json.dumps(obs), status, pe, json.dumps(delta), json.dumps({"goal_id": gid, "status": after[0], "gain": after[1]}), reentry if cur.rowcount else None, now, aid))
    conn.commit()
    return aid


def resume(conn, now=None):
    """E5.09: nach Neustart unfertige Versuche mit den eingefrorenen Kriterien zu Ende fuehren."""
    if not conn.execute("select 1 from sqlite_master where name='f3_goal_attempt'").fetchone():
        return 0
    ids = [r[0] for r in conn.execute("select attempt_id from f3_goal_attempt where evaluation_status is null").fetchall()]
    for a in ids:
        process(conn, a, now)
    return len(ids)


def pursue(conn, goal_id, now=None):
    aid = bind(conn, goal_id, now)
    return process(conn, aid, now) if aid else None
