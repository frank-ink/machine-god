"""s0_eval.py -- S0_EVAL_V1 (Protokoll fixtures/wm-s0/S0_EVAL_V1.md, sha eingefroren; Entwurf ChatGPT Runde 9, 2026-11-25). Nur lesend, SHADOW.

Prospektive Auswertung der WM1-Prognosen je Modellversion: BSS gegen die eingefrorene W0-Referenz (Haupt) und gegen Persistenz (sekundaer), gesamt und je Kanal,
mit gepaartem Block-Bootstrap (Block 12 Fenster, 10000 Wiederholungen, Seed 20261125). Bloecke nie ueber Beobachtungsluecken. UNKNOWN wird nie aufgefuellt.
Das Ergebnis ist eine Pruefstufe, kein endgueltiger Lernnachweis."""
import hashlib
import json
import os

import numpy as np

import weltmodell as wm

PROTO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "wm-s0/S0_EVAL_V1.md")
MIN_N, BLOCK, REPS, SEED, SENS = 200, 12, 10000, 20261125, (24, 36)
CH = wm.CH


def protocol_ok(path=PROTO):
    """sha256 der Protokolldatei gegen die eingefrorene .sha256-Datei."""
    try:
        h = hashlib.sha256(open(path, "rb").read()).hexdigest()
        return h == open(path[:-3] + ".sha256").read().strip(), h
    except OSError:
        return False, None


def load(conn, version):
    """-> Zeilen (bucket, e_model[5], e_ref[5], e_pers[5]|None) der bewerteten prospektiven Fenster dieser Version, nach Bucket sortiert."""
    if not wm._tbl(conn, "f3_wm_pred"):
        return []
    out = []
    for b, obs, pr, rf, ps in conn.execute("select bucket,obs,pred,ref_pred,pers_pred from f3_wm_pred where status='bewertet' and prospective=1 and model_version=? order by bucket", (int(version),)).fetchall():
        x = json.loads(obs)
        sq = lambda j: np.array([(json.loads(j)[c] - x[c]) ** 2 for c in CH]) if j else None
        out.append((b, sq(pr), sq(rf), sq(ps)))
    return out


def segments(rows):
    """Zusammenhaengende Abschnitte (Bucket-Differenz 1); nie ueber Luecken verbunden."""
    seg, cur = [], []
    for r in rows:
        if cur and r[0] != cur[-1][0] + 1:
            seg.append(cur); cur = []
        cur.append(r)
    if cur:
        seg.append(cur)
    return seg


def blocks(rows, length):
    """Feste, ueberlappungsfreie Bloecke je Abschnitt; Restblock am Abschnittsende bleibt erhalten."""
    out = []
    for s in segments(rows):
        for i in range(0, len(s), length):
            out.append(s[i:i + length])
    return out


def _bss(num, den):
    return 1.0 - num / den if den > 0 else None


def _boot(bl_m, bl_r, rng, reps):
    """bl_m, bl_r: (Bloecke x Kanaele) Summen. Ziehen Bloecke mit Zuruecklegen (gepaart). -> BSS je Wiederholung, gesamt (Spalte 0) und je Kanal."""
    nb = len(bl_m)
    idx = rng.integers(0, nb, size=(reps, nb))
    sm, sr = bl_m[idx].sum(axis=1), bl_r[idx].sum(axis=1)  # reps x Kanaele
    tot = 1.0 - sm.sum(axis=1) / np.where(sr.sum(axis=1) > 0, sr.sum(axis=1), np.nan)
    per = 1.0 - sm / np.where(sr > 0, sr, np.nan)
    return tot, per


def _ci(a):
    a = a[~np.isnan(a)]
    return [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))] if len(a) else [None, None]


def _verdict(ci):
    lo, hi = ci
    if lo is None:
        return "UNDEFINED"
    return "POSITIV" if lo > 0 else ("NEGATIV" if hi < 0 else "UNENTSCHIEDEN")


def _sliding(rows, ref_idx, length, reps, seed):
    """Sensitivitaet (Runde 10): gleitende Bloecke (alle Startpunkte innerhalb eines Abschnitts), nur berichtet, ohne Einfluss auf das Urteil."""
    rows = [r for r in rows if r[ref_idx] is not None]
    bl = []
    for s in segments(rows):
        for i in range(max(1, len(s) - length + 1)):
            bl.append(s[i:i + length])
    if not bl:
        return {"n": 0}
    bm = np.array([sum(r[1] for r in b) for b in bl]); br = np.array([sum(r[ref_idx] for r in b) for b in bl])
    tot, _ = _boot(bm, br, np.random.default_rng(seed), reps)
    ci = _ci(tot)
    return {"bloecke": len(bl), "ci95": ci, "urteil": _verdict(ci)}


def _cmp(rows, ref_idx, length, reps, seed):
    """Vergleich Modell gegen Referenz (ref_idx 2=W0, 3=Persistenz) auf den Zeilen, die die Referenz haben."""
    rows = [r for r in rows if r[ref_idx] is not None]
    if not rows:
        return {"n": 0}
    bl = blocks(rows, length)
    bm = np.array([sum(r[1] for r in b) for b in bl]); br = np.array([sum(r[ref_idx] for r in b) for b in bl])
    abs_b = {"brier_modell": float(bm.sum() / (len(rows) * len(CH))), "brier_referenz": float(br.sum() / (len(rows) * len(CH)))}
    point = _bss(bm.sum(), br.sum()); per_pt = [_bss(bm[:, i].sum(), br[:, i].sum()) for i in range(len(CH))]
    tot, per = _boot(bm, br, np.random.default_rng(seed), reps)
    ci = _ci(tot)
    return {**abs_b, "n": len(rows), "segmente": len(segments(rows)), "bloecke": len(bl), "block": length, "bss": point, "ci95": ci, "urteil": _verdict(ci),
            "kanal": {c: {"bss": per_pt[i], "ci95": _ci(per[:, i]), "urteil": _verdict(_ci(per[:, i]))} for i, c in enumerate(CH)}}


def evaluate(conn, version=0, reps=REPS, seed=SEED, min_n=MIN_N):
    """Haupt: BSS vs W0 (Block 12); sekundaer: vs Persistenz; Sensitivitaet: Block 24/36 und gleitende Bloecke (nur berichtet). Unter min_n Fenstern: ZU_WENIG_DATEN, kein Urteil."""
    ok, h = protocol_ok()
    rows = load(conn, version)
    unk = conn.execute("select count(*) from f3_wm_pred where status='unbekannt' and model_version=?", (int(version),)).fetchone()[0] if wm._tbl(conn, "f3_wm_pred") else 0
    res = {"protokoll": "S0_EVAL_V1", "protokoll_sha": h, "protokoll_unveraendert": ok, "version": int(version), "n_gueltig": len(rows), "n_unknown": unk, "min_n": min_n}
    if len(rows) < min_n:
        res["urteil"] = "ZU_WENIG_DATEN"
        return res
    res["haupt_vs_w0"] = _cmp(rows, 2, BLOCK, reps, seed)
    res["sekundaer_vs_persistenz"] = _cmp(rows, 3, BLOCK, reps, seed)
    res["sensitivitaet"] = {"block%d" % L: {k: v for k, v in _cmp(rows, 2, L, reps, seed).items() if k in ("n", "bloecke", "bss", "ci95", "urteil")} for L in SENS}
    res["sensitivitaet_gleitend"] = {"block%d" % L: _sliding(rows, 2, L, reps, seed) for L in (BLOCK,) + SENS}
    res["urteil"] = res["haupt_vs_w0"]["urteil"]
    return res
