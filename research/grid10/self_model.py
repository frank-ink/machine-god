"""self_model.py -- SELF_MODEL_V1 (Draft ChatGPT Round 9/10, 2026-11-25), SHADOW. Self-model only from verifiable capabilities, measurements, and limits, NEVER from a persona.

Each capability = claim + probe (read-only, local, cheap). Result per check: VERIFIED | FAILED | UNKNOWN (probe not applicable/data missing; never guess FAILED or VERIFIED)
with evidence (measurements). Revisions are append-only (trigger against UPDATE/DELETE), a new revision only when status or evidence changes.
Contradiction: a capability was VERIFIED and is now FAILED -> E2 finding 'contradiction' (self-image no longer matches measurement).
self_image() returns only statements with evidence and timestamp; no consciousness claim, no self-description without measurement."""
import hashlib
import json
import os
import time
import urllib.request

RULE_VERSION, MODE_KEY, ALIVE_S = "SELF_MODEL_V1", "frank3.self.mode", 900.0
DDL = ("create table if not exists f3_self_cap(cap_id text primary key, claim text, probe text, created_at real)",
       "create table if not exists f3_self_rev(rev_id text primary key, cap_id text, seq integer, ts real, status text, evidence text, prev_hash text, rule_version text, unique(cap_id, seq))",
       "create trigger if not exists f3_self_rev_noupd before update on f3_self_rev begin select raise(abort,'unveraenderlich'); end",
       "create trigger if not exists f3_self_rev_nodel before delete on f3_self_rev begin select raise(abort,'unveraenderlich'); end")


def _h(*a):
    return hashlib.sha256("|".join(map(str, a)).encode()).hexdigest()[:16]


def off(conn):
    r = conn.execute("select wert from star_konfig where schluessel=?", (MODE_KEY,)).fetchone()
    k = conn.execute("select wert from star_konfig where schluessel='frank3.kill'").fetchone()
    return bool((r and r[0] == "off") or (k and k[0] == "1"))


def _tbl(conn, n):
    return conn.execute("select 1 from sqlite_master where type='table' and name=?", (n,)).fetchone() is not None


def p_retina(conn, now):
    if not _tbl(conn, "f2_retina_sinne"):
        return "UNKNOWN", {"grund": "keine Sinnestabelle"}
    r = conn.execute("select status,ts from f2_retina_sinne where organ_id='fenster1'").fetchone()
    if not r:
        return "UNKNOWN", {"grund": "kein Sinneseintrag"}
    age = now - (r[1] or 0)
    return ("VERIFIED" if r[0] == "aktiv" and age < ALIVE_S else "FAILED"), {"status": r[0], "alter_s": round(age)}


def p_lokales_llm(conn, now, url=None):
    url = url or os.environ.get("MG_LLM_HEALTH_URL")
    if not url:
        return "UNKNOWN", {"grund": "MG_LLM_HEALTH_URL nicht gesetzt"}
    try:
        with urllib.request.urlopen(url, timeout=2) as r:
            return ("VERIFIED" if r.status == 200 else "FAILED"), {"http": r.status}
    except Exception as e:
        return "FAILED", {"fehler": type(e).__name__}


def p_takt(conn, now, n=12):
    """Has a hook run occurred in the last n completed 5-minute windows (heartbeat)? A clock without a daemon is only as dense as the hook runs."""
    if not _tbl(conn, "f3_wm_cover"):
        return "UNKNOWN", {"grund": "kein Heartbeat-Ledger"}
    hi = int(now // 300) - 1
    k = conn.execute("select count(*) from f3_wm_cover where bucket>? and bucket<=?", (hi - n, hi)).fetchone()[0]
    return ("VERIFIED" if k >= n * 0.5 else "FAILED"), {"fenster_mit_lauf": k, "von": n}


def p_prognose(conn, now):
    if not _tbl(conn, "f3_wm_pred"):
        return "UNKNOWN", {"grund": "kein Prognose-Ledger"}
    n = conn.execute("select count(*) from f3_wm_pred where status='bewertet' and prospective=1").fetchone()[0]
    return ("VERIFIED" if n >= 1 else "FAILED"), {"bewertete_prospektive_fenster": n}


def p_s0(conn, now):
    if not _tbl(conn, "f3_wm_pred"):
        return "UNKNOWN", {"grund": "kein Prognose-Ledger"}
    n = conn.execute("select count(*) from f3_wm_pred where status='bewertet' and prospective=1 and model_version=0").fetchone()[0]
    return ("VERIFIED" if n >= 200 else "FAILED"), {"gueltige_fenster_v0": n, "ziel": 200}


def p_intent(conn, now, pfad=os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "intent-bench/full_run.json")):
    try:
        m = json.load(open(pfad))["metrics"]
    except Exception:
        return "UNKNOWN", {"grund": "kein Benchmarklauf"}
    return ("VERIFIED" if m.get("bestanden") else "FAILED"), {"indirekt_recall": m.get("indirekt_recall"), "tool_precision": m.get("tool_precision"), "macro_f1": m.get("macro_f1"), "schema": m.get("schema")}


CAPS = {"retina_sinn": ("Die Retina liefert aktuell Beobachtungen (Sinn aktiv und frisch).", p_retina),
        "lokales_llm": ("Der konfigurierte Modell-Endpunkt antwortet (MG_LLM_HEALTH_URL).", p_lokales_llm),
        "takt": ("Es laeuft regelmaessig ein Zyklus (mindestens jedes zweite 5-Minuten-Fenster hatte einen Lauf).", p_takt),
        "prognose": ("Das Weltmodell erzeugt und bewertet prospektive Prognosen.", p_prognose),
        "s0_coverage": ("At least 200 valid windows of version 0 exist for the S0 acceptance.", p_s0),
        "intent_semantics": ("The intent cortex meets the acceptance on INTENT_BENCH_V1 (indirect recall >= 0.75, tool precision >= 0.90, macro-F1 >= 0.80).", p_intent)}


def project(conn, now=None, caps=None):
    """Runs all probes, appends a revision when status/evidence changes. -> Number of new revisions."""
    now = time.time() if now is None else now
    if off(conn):
        return 0
    for d in DDL:
        conn.execute(d)
    new = 0
    for cid, (claim, fn) in (caps or CAPS).items():
        conn.execute("insert or ignore into f3_self_cap values(?,?,?,?)", (cid, claim, getattr(fn, "__name__", "probe"), now))
        try:
            st, ev = fn(conn, now)
        except Exception as e:
            st, ev = "UNKNOWN", {"fehler": type(e).__name__}
        ev_j = json.dumps(ev, sort_keys=True)
        last = conn.execute("select seq,status,evidence,rev_id from f3_self_rev where cap_id=? order by seq desc limit 1", (cid,)).fetchone()
        if last and last[1] == st and last[2] == ev_j:
            continue
        seq = (last[0] + 1) if last else 1
        conn.execute("insert into f3_self_rev values(?,?,?,?,?,?,?,?)", (_h("rev", cid, seq, st, ev_j), cid, seq, now, st, ev_j, last[3] if last else "", RULE_VERSION))
        new += 1
    conn.commit()
    return new


def history(conn, cid):
    return conn.execute("select seq,status,evidence,ts from f3_self_rev where cap_id=? order by seq", (cid,)).fetchall()


def finding(conn, now=None):
    """E2 findings: capability was VERIFIED and is now FAILED (self-image contradicts measurement). Evidence = immutable revision snapshot."""
    if off(conn) or not _tbl(conn, "f3_self_rev"):
        return []
    out = []
    for (cid, claim) in conn.execute("select cap_id,claim from f3_self_cap order by cap_id").fetchall():
        v = history(conn, cid)
        if not v or v[-1][1] != "FAILED" or not any(r[1] == "VERIFIED" for r in v[:-1]):
            continue
        mx = conn.execute("select max(rowid) from f3_self_rev where cap_id=?", (cid,)).fetchone()[0]
        n = conn.execute("select count(*) from f3_self_rev where cap_id=? and rowid<=?", (cid, mx)).fetchone()[0]
        out.append({"kind": "contradiction", "key": "self_lost:" + cid, "statement": "Self model: capability '%s' was verified and is no longer (%s)" % (cid, v[-1][2]),
                    "ref": {"table": "f3_self_rev", "where": "cap_id='%s' and rowid<=%d" % (cid, mx), "params": [], "n": n}})
    return out


def self_image(conn):
    """Only substantiated statements: for each capability the latest status with evidence and time; UNKNOWN is labeled 'not verifiable', never as a capability or deficiency."""
    if not _tbl(conn, "f3_self_cap"):
        return []
    out = []
    for cid, claim in conn.execute("select cap_id,claim from f3_self_cap order by cap_id").fetchall():
        v = history(conn, cid)
        if not v:
            continue
        s, st, ev, ts = v[-1]
        txt = {"VERIFIED": "verified", "FAILED": "refuted/not met", "UNKNOWN": "not testable"}[st]
        out.append({"cap": cid, "status": st, "statement_text": "%s [%s; measurement %s; as of r%d]" % (claim, txt, ev, s), "ts": ts})
    return out
