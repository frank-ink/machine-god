"""weltmodell2.py -- WM2 Hyperposition, minimaler Hypothesenraum (Entwurf ChatGPT Runde 10, 2026-11-25), SHADOW, nur lokal.

Reine PROJEKTION der UnifiedDB: keine zweite Zustandsautoritaet, WM1 (f3_wm_*) wird nur gelesen und nie veraendert; die eingefrorene S0-Auswertung bleibt unberuehrt.
Anlass = ein E2-Befund 'wm_prognosefehler' (f3_endo_befund). Dazu konkurrierende Erklaerungen, jede mit unveraenderlichen Revisionen (append-only, per Trigger gegen UPDATE/DELETE gesperrt, Hash-Kette):
  H_RAUSCHEN  zufaellige Streuung/Ausreisser    H_REGIME  Umweltraten haben sich verschoben (gerichteter Fehler, der bleibt)    H_SENSOR  Messartefakt durch Beobachtungsluecken
Indikatoren (deterministisch aus f3_wm_pred, siehe ind()): conc (Konzentration des Fehlers), bias (Richtungskonstanz im groessten Kanal), gap (Luecken im Fensterbereich),
post (Fehler NACH dem Anlass: nur Fenster nach hi, ab 3 Fenstern; neue Revision, sobald sich die Evidenz aendert).
Gewichte sind Plausibilitaetsanteile einer Regel, KEINE kalibrierten Wahrscheinlichkeiten (Startwerte, ungeprueft). Offener Widerspruch: Abstand der beiden Besten < MARGIN -> E2-Befund.
Gegenevidenz je Revision ausgewiesen (counter), Salienz = Anteil des Spitzenreiters x Schwere des Anlasses."""
import hashlib
import json
import re
import time

import weltmodell as wm

RULE_VERSION, MODE_KEY, MARGIN, POST_MIN, FLOOR = "WM2_HYP_V1", "frank3.wm2.mode", 0.10, 3, 0.05
HYP = {"RAUSCHEN": "Der Prognosefehler ist zufaellige Streuung/Ausreisser, das Modell ist im Kern passend.",
       "REGIME": "Die Raten der Umwelt haben sich verschoben (gerichteter, anhaltender Fehler), das Modell ist veraltet.",
       "SENSOR": "Der Prognosefehler ist ein Messartefakt durch Beobachtungsluecken, nicht die Umwelt."}
DDL = ("create table if not exists f3_wm2_anlass(anlass_id text primary key, befund_id integer, ver integer, lo integer, hi integer, created_at real, rule_version text)",
       "create table if not exists f3_wm2_hyp(hyp_id text primary key, anlass_id text, name text, claim text, created_at real)",
       "create table if not exists f3_wm2_rev(rev_id text primary key, anlass_id text, hyp_id text, seq integer, ts real, indicators text, support text, counter text, weight real, score real, rank integer,"
       " salience real, status text, prev_hash text, rule_version text, unique(hyp_id, seq))",
       "create trigger if not exists f3_wm2_rev_noupd before update on f3_wm2_rev begin select raise(abort,'unveraenderlich'); end",
       "create trigger if not exists f3_wm2_rev_nodel before delete on f3_wm2_rev begin select raise(abort,'unveraenderlich'); end")


def _h(*a):
    return hashlib.sha256("|".join(map(str, a)).encode()).hexdigest()[:16]


def off(conn):
    r = conn.execute("select wert from star_konfig where schluessel=?", (MODE_KEY,)).fetchone()
    k = conn.execute("select wert from star_konfig where schluessel='frank3.kill'").fetchone()
    return bool((r and r[0] == "off") or (k and k[0] == "1"))


def _clip(x):
    return max(0.0, min(1.0, x))


def ind(conn, ver, lo, hi):
    """Indikatoren aus f3_wm_pred. Fenster im Bereich [lo,hi] unter Modellversion ver; 'post' = Fenster nach hi (hoechste Version je Bucket)."""
    rows = conn.execute("select bucket,obs,pred,brier from f3_wm_pred where status='bewertet' and model_version=? and bucket>=? and bucket<=? order by bucket", (ver, lo, hi)).fetchall()
    n = len(rows)
    if n == 0:
        return None
    br = [r[3] for r in rows]; tot = sum(br)
    conc = sum(sorted(br, reverse=True)[:2]) / tot if tot > 0 else 0.0
    conc_n = _clip((conc - 2.0 / n) / (0.7 - 2.0 / n)) if n > 3 else 0.0
    d = {c: [json.loads(r[1])[c] - json.loads(r[2])[c] for r in rows] for c in wm.CH}
    c0 = max(wm.CH, key=lambda c: sum(abs(v) for v in d[c]))
    sa = sum(abs(v) for v in d[c0])
    bias = abs(sum(d[c0])) / sa if sa > 0 else 0.0
    bias_n = _clip((bias - 0.5) / 0.5)
    gap = 1.0 - n / float(hi - lo + 1)
    gap_n = _clip(gap / 0.25)
    mean_in = tot / n
    post = conn.execute("select b.bucket, b.brier from f3_wm_pred b where b.status='bewertet' and b.bucket>? and b.model_version=(select max(model_version) from f3_wm_pred x where x.bucket=b.bucket and x.status='bewertet') order by b.bucket limit ?",
                        (hi, wm.WINDOW_N)).fetchall()
    pm = sum(p[1] for p in post) / len(post) if len(post) >= POST_MIN else None
    trans = 1.0 if pm is not None and pm < 0.5 * mean_in else 0.0
    pers = 1.0 if pm is not None and pm >= 0.8 * mean_in else 0.0
    return {"n": n, "mean_in": round(mean_in, 6), "conc": round(conc, 4), "conc_n": round(conc_n, 4), "kanal": c0, "bias": round(bias, 4), "bias_n": round(bias_n, 4),
            "gap": round(gap, 4), "gap_n": round(gap_n, 4), "post_n": len(post), "post_mean": None if pm is None else round(pm, 6), "trans": trans, "pers": pers}


def weights(i):
    """-> {name: (gewicht, [Stuetzen], [Gegenstuetzen])}. Regel WM2_HYP_V1."""
    sup = {"RAUSCHEN": [("conc_n", i["conc_n"], .5), ("trans", i["trans"], .5)], "REGIME": [("bias_n", i["bias_n"], .5), ("pers", i["pers"], .5)], "SENSOR": [("gap_n", i["gap_n"], 1.0)]}
    cnt = {"RAUSCHEN": [("bias_n", i["bias_n"], .25), ("pers", i["pers"], .25)], "REGIME": [("conc_n", i["conc_n"], .25), ("trans", i["trans"], .25)], "SENSOR": []}
    out = {}
    for h in HYP:
        s, c = sum(v * w for _, v, w in sup[h]), sum(v * w for _, v, w in cnt[h])
        out[h] = (max(FLOOR, 0.1 + s - c), [k for k, v, _ in sup[h] if v > 0], [k for k, v, _ in cnt[h] if v > 0])
    return out


def _ref(ver, lo, hi, n):
    return {"table": "f3_wm_pred", "where": "status='bewertet' and model_version=%d and bucket>=%d and bucket<=%d" % (ver, lo, hi), "params": [], "n": n}


def _revise(conn, aid, ver, lo, hi, now):
    i = ind(conn, ver, lo, hi)
    if i is None:
        return 0
    w = weights(i); z = sum(v[0] for v in w.values())
    ranked = sorted(w, key=lambda h: (-w[h][0], h))
    sev = _clip(i["mean_in"] / wm.THETA_B)
    new = 0
    for h in HYP:
        hid = _h("hyp", aid, h)
        last = conn.execute("select seq,indicators,prev_hash,rev_id from f3_wm2_rev where hyp_id=? order by seq desc limit 1", (hid,)).fetchone()
        key = json.dumps({"i": i, "rule": RULE_VERSION}, sort_keys=True)
        if last and last[1] == key:
            continue  # Evidenz unveraendert: keine neue Revision
        seq = (last[0] + 1) if last else 1
        score = w[h][0] / z
        rank = ranked.index(h) + 1
        rid = _h("rev", hid, seq, key)
        conn.execute("insert into f3_wm2_rev values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (rid, aid, hid, seq, now, key, json.dumps({"ind": w[h][1], "ref": _ref(ver, lo, hi, i["n"])}), json.dumps({"ind": w[h][2]}), w[h][0], score, rank, round(score * sev, 6),
                      "leitend" if rank == 1 else "konkurrierend", last[3] if last else "", RULE_VERSION))
        new += 1
    return new


def project(conn, now=None):
    """Projiziert alle E2-Befunde 'wm_prognosefehler' in den Hypothesenraum (idempotent). -> Zahl neuer Revisionen."""
    now = time.time() if now is None else now
    if off(conn) or not wm._tbl(conn, "f3_wm_pred") or not wm._tbl(conn, "f3_endo_befund"):
        return 0
    for d in DDL:
        conn.execute(d)
    new = 0
    for bid, ref_j in conn.execute("select id,evidence_ref from f3_endo_befund where key='wm_prognosefehler' order by id").fetchall():
        ref = json.loads(ref_j)
        m = re.search(r"model_version=(\d+) and bucket>=(\d+) and bucket<=(\d+)", ref.get("where", ""))
        if not m:
            continue
        ver, lo, hi = map(int, m.groups())
        aid = _h("anlass", ver, lo, hi)
        if not conn.execute("select 1 from f3_wm2_anlass where anlass_id=?", (aid,)).fetchone():
            conn.execute("insert into f3_wm2_anlass values(?,?,?,?,?,?,?)", (aid, bid, ver, lo, hi, now, RULE_VERSION))
            for h, claim in HYP.items():
                conn.execute("insert or ignore into f3_wm2_hyp values(?,?,?,?,?)", (_h("hyp", aid, h), aid, h, claim, now))
        new += _revise(conn, aid, ver, lo, hi, now)
    conn.commit()
    return new


def stand(conn, aid):
    """Aktueller Stand eines Anlasses: je Hypothese die letzte Revision."""
    rows = conn.execute("select h.name,r.seq,r.score,r.rank,r.salience,r.status,r.support,r.counter from f3_wm2_rev r join f3_wm2_hyp h on h.hyp_id=r.hyp_id where r.anlass_id=? and r.seq=(select max(seq) from f3_wm2_rev x where x.hyp_id=r.hyp_id) order by r.rank", (aid,)).fetchall()
    return [{"name": n, "seq": s, "score": sc, "rank": rk, "salience": sl, "status": st, "support": json.loads(su)["ind"], "counter": json.loads(co)["ind"]} for n, s, sc, rk, sl, st, su, co in rows]


def befund(conn, now=None):
    """Fuer endogen.observe: offener Widerspruch (Abstand der beiden Besten < MARGIN) -> E2-Befund mit unveraenderlicher Evidenz (alle Revisionen bis zur aktuellen Seq). Projiziert vorher."""
    if off(conn) or not wm._tbl(conn, "f3_wm2_anlass"):
        return []
    out = []
    for (aid,) in conn.execute("select anlass_id from f3_wm2_anlass").fetchall():
        st = stand(conn, aid)
        if len(st) < 2 or st[0]["score"] - st[1]["score"] >= MARGIN:
            continue
        mx = conn.execute("select max(rowid) from f3_wm2_rev where anlass_id=?", (aid,)).fetchone()[0]
        n = conn.execute("select count(*) from f3_wm2_rev where anlass_id=? and rowid<=?", (aid, mx)).fetchone()[0]
        out.append({"kind": "widerspruch", "key": "wm2_offen:" + aid, "statement": "WM2: konkurrierende Erklaerungen des Prognosefehlers nicht unterscheidbar (%s %.0f %% gegen %s %.0f %%, Abstand < %.0f %%)" % (
            st[0]["name"], 100 * st[0]["score"], st[1]["name"], 100 * st[1]["score"], 100 * MARGIN),
            "ref": {"table": "f3_wm2_rev", "where": "anlass_id='%s' and rowid<=%d" % (aid, mx), "params": [], "n": n}})
    return out


def report(conn):
    if not wm._tbl(conn, "f3_wm2_anlass"):
        return {"anlaesse": 0}
    return {"anlaesse": conn.execute("select count(*) from f3_wm2_anlass").fetchone()[0], "revisionen": conn.execute("select count(*) from f3_wm2_rev").fetchone()[0],
            "stand": {a: stand(conn, a) for (a,) in conn.execute("select anlass_id from f3_wm2_anlass").fetchall()}}
