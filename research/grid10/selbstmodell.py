"""selbstmodell.py -- SELF_MODEL_V1 (Entwurf ChatGPT Runde 9/10, 2026-11-25), SHADOW. Selbstmodell nur aus ueberpruefbaren Faehigkeiten, Messungen und Grenzen, NIE aus einer Persona.

Jede Faehigkeit = Behauptung (claim) + Sonde (lesend, lokal, billig). Ergebnis je Pruefung: VERIFIED | FAILED | UNKNOWN (Sonde nicht anwendbar/Daten fehlen; nie als FAILED oder VERIFIED geraten)
mit Evidenz (Messwerte). Revisionen sind append-only (Trigger gegen UPDATE/DELETE), eine neue Revision nur, wenn sich Status oder Evidenz aendern.
Widerspruch: war eine Faehigkeit VERIFIED und ist jetzt FAILED -> E2-Befund 'widerspruch' (Selbstbild stimmt nicht mehr mit der Messung ueberein).
selbstbild() liefert nur Aussagen mit Beleg und Zeitstempel; keine Bewusstseinsbehauptung, keine Selbstbeschreibung ohne Messung."""
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
    """Hat in den letzten n abgeschlossenen 5-Minuten-Fenstern ein Hook-Lauf stattgefunden (Heartbeat)? Ein Takt ohne Daemon ist nur so dicht wie die Hook-Laeufe."""
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


def p_intent(conn, now, pfad=os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "intent-bench/lauf_voll.json")):
    try:
        m = json.load(open(pfad))["metrics"]
    except Exception:
        return "UNKNOWN", {"grund": "kein Benchmarklauf"}
    return ("VERIFIED" if m.get("bestanden") else "FAILED"), {"indirekt_recall": m.get("indirekt_recall"), "tool_precision": m.get("tool_precision"), "macro_f1": m.get("macro_f1"), "schema": m.get("schema")}


CAPS = {"retina_sinn": ("Die Retina liefert aktuell Beobachtungen (Sinn aktiv und frisch).", p_retina),
        "lokales_llm": ("Der konfigurierte Modell-Endpunkt antwortet (MG_LLM_HEALTH_URL).", p_lokales_llm),
        "takt": ("Es laeuft regelmaessig ein Zyklus (mindestens jedes zweite 5-Minuten-Fenster hatte einen Lauf).", p_takt),
        "prognose": ("Das Weltmodell erzeugt und bewertet prospektive Prognosen.", p_prognose),
        "s0_umfang": ("Fuer die S0-Abnahme liegen mindestens 200 gueltige Fenster der Version 0 vor.", p_s0),
        "intent_semantik": ("Der Intent-Cortex erfuellt die Abnahme auf INTENT_BENCH_V1 (indirekt Recall >= 0.75, tool-Precision >= 0.90, Macro-F1 >= 0.80).", p_intent)}


def project(conn, now=None, caps=None):
    """Fuehrt alle Sonden aus, haengt bei geaendertem Status/Evidenz eine Revision an. -> Zahl neuer Revisionen."""
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


def verlauf(conn, cid):
    return conn.execute("select seq,status,evidence,ts from f3_self_rev where cap_id=? order by seq", (cid,)).fetchall()


def befund(conn, now=None):
    """E2-Befunde: Faehigkeit war VERIFIED und ist jetzt FAILED (Selbstbild widerspricht der Messung). Evidenz = unveraenderlicher Revisionsschnappschuss."""
    if off(conn) or not _tbl(conn, "f3_self_rev"):
        return []
    out = []
    for (cid, claim) in conn.execute("select cap_id,claim from f3_self_cap order by cap_id").fetchall():
        v = verlauf(conn, cid)
        if not v or v[-1][1] != "FAILED" or not any(r[1] == "VERIFIED" for r in v[:-1]):
            continue
        mx = conn.execute("select max(rowid) from f3_self_rev where cap_id=?", (cid,)).fetchone()[0]
        n = conn.execute("select count(*) from f3_self_rev where cap_id=? and rowid<=?", (cid, mx)).fetchone()[0]
        out.append({"kind": "widerspruch", "key": "self_verloren:" + cid, "statement": "Selbstmodell: Faehigkeit '%s' war verifiziert und ist es nicht mehr (%s)" % (cid, v[-1][2]),
                    "ref": {"table": "f3_self_rev", "where": "cap_id='%s' and rowid<=%d" % (cid, mx), "params": [], "n": n}})
    return out


def selbstbild(conn):
    """Nur belegte Aussagen: je Faehigkeit der letzte Stand mit Evidenz und Zeit; UNKNOWN wird als 'nicht pruefbar' benannt, nie als Faehigkeit oder Mangel."""
    if not _tbl(conn, "f3_self_cap"):
        return []
    out = []
    for cid, claim in conn.execute("select cap_id,claim from f3_self_cap order by cap_id").fetchall():
        v = verlauf(conn, cid)
        if not v:
            continue
        s, st, ev, ts = v[-1]
        txt = {"VERIFIED": "belegt", "FAILED": "widerlegt/nicht erfuellt", "UNKNOWN": "nicht pruefbar"}[st]
        out.append({"cap": cid, "status": st, "aussage": "%s [%s; Messung %s; Stand r%d]" % (claim, txt, ev, s), "ts": ts})
    return out
