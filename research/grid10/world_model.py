"""world_model.py -- WM1 Forecast Ledger + persistent world model revision (Draft ChatGPT Round 8, 2026-11-25), SHADOW, local only and read-only on retina raw events.

Model: per retina channel c a forecast value p_c = expected probability of an event in the next 300-s window; update p <- (1-a)*p + a*x with x in {0,1}
(Start a=0.10 = UNFOUNDED initial assumption, hypothesis). Raw events (f2_retina_geschehen), NOT only those passed by thalamus.
Forecast for the window after next (cur+1) is frozen while it has not yet started (frozen_hash); deviation from Round 8: horizon = 1 window from the last
completed one, because without a daemon a forecast exactly at the window boundary is not possible. Windows without forecast are NEVER forecast retroactively.
Evaluation independent of forecaster: Brier B = 1/5 * Sum (p^ - x)^2, alongside the same measurement for the frozen reference (W0 base rates).
Versioning (Round 9): each forecast carries last_observed_window, forecast_created_at, target_window (bucket), horizon_windows, model_version, state_digest; model, W0 reference and
persistence (last evaluated window) are frozen together with THE SAME information state and horizon. A frozen forecast is NEVER overwritten or deleted; a revision creates
for the next not-yet-started window a SECOND forecast under the new version. Each forecast is evaluated under its own version, evaluation per version separate (report), version boundaries are never shifted.
Coverage: only windows with sensor sample (f2_retina_sinne 'fenster1' active and fresh, recorded during hook run in the window) are 'ok'; all others are UNKNOWN: they are neither
evaluated nor do they flow into the model as 0 (without daemon there are many; a real continuous beat needs a systemd timer = user's OK).
Conflict (E2): last 12 evaluated windows, all under the CURRENT model version, rolling Brier mean > 0.30 -> contradiction finding 'wm_prognosefehler' with immutable evidence.
Revision (after E3/E5 investigation): candidates a in ALPHAS, replay over these 12 windows; change only if >= 10% relative improvement, otherwise none (ABSTAIN) -> version+1 persistent,
not-yet-started forecasts are newly frozen. This is in-sample tuning of a parameter, NO proof of learning; the benefit shows only prospectively against the reference (report)."""
import hashlib
import json
import time

from retina_thalamus import CHANNELS

CH = sorted(CHANNELS)
MODE_KEY, BUCKET_S, MAX_CATCHUP = "frank3.wm.mode", 300, 288
ALPHA0, ALPHAS, WINDOW_N, THETA_B, MIN_REL_GAIN, ALIVE_S = 0.10, (0.05, 0.10, 0.20, 0.40), 12, 0.30, 0.10, 900.0
DDL = ("create table if not exists f3_wm_state(singleton integer primary key check(singleton=1), j text not null, updated real not null)",
       "create table if not exists f3_wm_cover(bucket integer primary key, ts real, status text)",
       "create table if not exists f3_wm_pred(bucket integer not null, model_version integer not null, created_at real, alpha real, last_observed_window integer, horizon_windows integer,"
       " state_digest text, pred text, ref_pred text, pers_pred text, frozen_hash text, prospective integer, coverage text, obs text, brier real, brier_ref real, brier_pers real, status text,"
       " primary key(bucket, model_version))",
       "create table if not exists f3_wm_rev(id integer primary key autoincrement, ts real, from_version integer, to_version integer, alpha_from real, alpha_to real, evidence_ref text,"
       " brier_before real, brier_after real, decision text, attempt_id text unique)",
       "create table if not exists f3_wm_anfrage(id integer primary key autoincrement, ts real, attempt_id text unique, kind text, text text, evidence_ref text, status text)")


def _h(*a):
    return hashlib.sha256("|".join(map(str, a)).encode()).hexdigest()[:16]


def off(conn):
    r = conn.execute("select wert from star_konfig where schluessel=?", (MODE_KEY,)).fetchone()
    k = conn.execute("select wert from star_konfig where schluessel='frank3.kill'").fetchone()
    return bool((r and r[0] == "off") or (k and k[0] == "1"))


def _tbl(conn, n):
    return conn.execute("select 1 from sqlite_master where type='table' and name=?", (n,)).fetchone() is not None


def brier(p, x):
    return sum((p[c] - x[c]) ** 2 for c in CH) / len(CH)


def _x(conn, b0, b1):
    """{bucket: {kanal: 0/1}} for windows [b0,b1) from raw events."""
    out = {b: {c: 0 for c in CH} for b in range(b0, b1)}
    if _tbl(conn, "f2_retina_geschehen"):
        for ts, art in conn.execute("select ts,art from f2_retina_geschehen where ts>=? and ts<?", (b0 * BUCKET_S, b1 * BUCKET_S)):
            if art in out[int(ts // BUCKET_S)]:
                out[int(ts // BUCKET_S)][art] = 1
    return out


def baseline(conn):
    """W0 from existing history: proportion of windows with event per channel over span first..last event. Historical coverage UNKNOWN -> only initial value, no check."""
    if not _tbl(conn, "f2_retina_geschehen"):
        return {c: 0.0 for c in CH}, 0
    lo, hi = conn.execute("select min(ts),max(ts) from f2_retina_geschehen").fetchone()
    if lo is None:
        return {c: 0.0 for c in CH}, 0
    span = int(hi // BUCKET_S) - int(lo // BUCKET_S) + 1
    cnt = {c: 0 for c in CH}
    for art, n in conn.execute("select art,count(distinct cast(ts/%d as integer)) from f2_retina_geschehen group by art" % BUCKET_S):
        if art in cnt:
            cnt[art] = n
    return {c: round(cnt[c] / span, 6) for c in CH}, span


def sensor_status(conn, now):
    if not _tbl(conn, "f2_retina_sinne"):
        return "unbekannt"
    r = conn.execute("select status,ts from f2_retina_sinne where organ_id='fenster1'").fetchone()
    if not r:
        return "unbekannt"
    return "ok" if str(r[0] or "").startswith("aktiv") and r[1] is not None and 0 <= now - r[1] < ALIVE_S else "ausgefallen"


def _state(conn, now):
    row = conn.execute("select j from f3_wm_state where singleton=1").fetchone()
    if row:
        return json.loads(row[0])
    p0, span = baseline(conn)
    cur = int(now // BUCKET_S)
    st = {"version": 0, "alpha": ALPHA0, "p": dict(p0), "ref": dict(p0), "last": cur - 1, "baseline_windows": span, "start": cur, "last_ok": None, "last_x": None}
    _save(conn, st, now)
    return st


def _save(conn, st, now):
    conn.execute("insert or replace into f3_wm_state(singleton,j,updated) values(1,?,?)", (json.dumps(st, sort_keys=True), now))


def _freeze(conn, st, b, now):
    """Freezes the forecast for window b under the current model version (insert or ignore: a frozen forecast is never changed). Model, reference, persistence: same state, same horizon."""
    pred = {c: round(st["p"][c], 6) for c in CH}
    ref = {c: round(st["ref"][c], 6) for c in CH}
    pers = {c: st["last_x"][c] for c in CH} if st.get("last_x") else None
    lo = st.get("last_ok")
    digest = _h(json.dumps(pred, sort_keys=True), st["version"], st["alpha"], lo)
    fh = _h(b, json.dumps(pred, sort_keys=True), json.dumps(ref, sort_keys=True), json.dumps(pers, sort_keys=True), st["alpha"], st["version"], lo)
    conn.execute("insert or ignore into f3_wm_pred(bucket,model_version,created_at,alpha,last_observed_window,horizon_windows,state_digest,pred,ref_pred,pers_pred,frozen_hash,prospective,status)"
                 " values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (b, st["version"], now, st["alpha"], lo, (b - lo) if lo is not None else None, digest, json.dumps(pred, sort_keys=True), json.dumps(ref, sort_keys=True),
                  json.dumps(pers, sort_keys=True) if pers else None, fh, 1, "offen"))


def step(conn, now=None):
    """-> Number of evaluated prognoses. Idempotent; writes only f3_wm_*."""
    now = time.time() if now is None else now
    if off(conn):
        return 0
    for d in DDL:
        conn.execute(d)
    st, cur = _state(conn, now), int(now // BUCKET_S)
    conn.execute("insert or ignore into f3_wm_cover(bucket,ts,status) values(?,?,?)", (cur, now, sensor_status(conn, now)))
    b0, scored = max(st["last"] + 1, cur - MAX_CATCHUP), 0
    xs = _x(conn, b0, cur)
    for b in range(b0, cur):
        cov = (conn.execute("select status from f3_wm_cover where bucket=?", (b,)).fetchone() or ("unbekannt",))[0]
        ok = cov == "ok"
        for ver, pr, rf, ps in conn.execute("select model_version,pred,ref_pred,pers_pred from f3_wm_pred where bucket=? and status='offen'", (b,)).fetchall():
            if ok:
                conn.execute("update f3_wm_pred set coverage=?, obs=?, brier=?, brier_ref=?, brier_pers=?, status='bewertet' where bucket=? and model_version=?",
                             (cov, json.dumps(xs[b], sort_keys=True), brier(json.loads(pr), xs[b]), brier(json.loads(rf), xs[b]), brier(json.loads(ps), xs[b]) if ps else None, b, ver))
                scored += 1
            else:
                conn.execute("update f3_wm_pred set coverage=?, status='unbekannt' where bucket=? and model_version=?", (cov, b, ver))  # UNKNOWN: not evaluated, not counted as 0
        if ok:
            st["p"] = {c: (1 - st["alpha"]) * st["p"][c] + st["alpha"] * xs[b][c] for c in CH}
            st["last_ok"], st["last_x"] = b, dict(xs[b])
    st["last"] = max(st["last"], cur - 1)
    _freeze(conn, st, cur + 1, now)  # Window cur+1 has not yet started
    _save(conn, st, now)
    conn.execute("delete from f3_wm_pred where bucket < ?", (cur - 20000,))
    conn.commit()
    return scored


def _window_rows(conn, version=None):
    st = conn.execute("select j from f3_wm_state where singleton=1").fetchone()
    v = json.loads(st[0])["version"] if version is None and st else version
    return conn.execute("select bucket,obs,brier,pred,model_version,alpha from f3_wm_pred where status='bewertet' and model_version=? order by bucket desc limit ?", (v, WINDOW_N)).fetchall()[::-1]


def finding(conn, now=None):
    """For endogenous.observe: -> list of E2 findings (forecast conflict and/or sensor coverage). Uncertain/insufficient data -> none."""
    if not _tbl(conn, "f3_wm_pred") or not _tbl(conn, "f3_wm_state"):
        return []
    return _conflict(conn) + sensor_finding(conn, time.time() if now is None else now)


def _conflict(conn):
    rows = _window_rows(conn)
    if len(rows) < WINDOW_N:
        return []
    m = sum(r[2] for r in rows) / len(rows)
    if m <= THETA_B:
        return []
    lo, hi = rows[0][0], rows[-1][0]
    ver = rows[0][4]
    return [{"kind": "contradiction", "key": "wm_prognosefehler", "statement": "Weltmodell-Prognose widerspricht der Beobachtung: Brier %.3f ueber %d Fenster (Schwelle %.2f, Modellversion %d)" % (m, len(rows), THETA_B, ver),
             "ref": {"table": "f3_wm_pred", "where": "status='bewertet' and model_version=%d and bucket>=%d and bucket<=%d" % (ver, lo, hi), "params": [], "n": len(rows)}}]


COV_N, COV_MIN, COV_GAP = 288, 0.80, 288


def coverage(conn, now):
    """SENSOR_HOMEOSTASIS_V1: Coverage C = N_valid / N_expected over the last 288 completed windows. Ramp-up (< 288 windows since start) is marked separately.
    Failure types separate: failed (sensor not reporting active/fresh), unknown (no sensor status readable), no_row (no hook ran in that window = no tick)."""
    st = json.loads(conn.execute("select j from f3_wm_state where singleton=1").fetchone()[0])
    hi = int(now // BUCKET_S) - 1
    first = max(hi - COV_N + 1, st["start"])
    expected = hi - first + 1
    if expected <= 0:
        return None
    cnt = dict(conn.execute("select status,count(*) from f3_wm_cover where bucket>=? and bucket<=? group by status", (first, hi)).fetchall())
    valid, aus, unb = cnt.get("ok", 0), cnt.get("ausgefallen", 0), cnt.get("unbekannt", 0)
    return {"lo": first, "hi": hi, "expected": expected, "valid": valid, "ausgefallen": aus, "unbekannt": unb, "keine_zeile": max(0, expected - valid - aus - unb),
            "C": valid / expected, "anlauf": (hi - st["start"] + 1) < COV_N}


def cause(c):
    """Dominant cause of missing coverage (>= 50% of missing windows), otherwise UNKNOWN_CAUSE."""
    miss = c["expected"] - c["valid"]
    if miss <= 0:
        return None
    for k, name in (("keine_zeile", "SCHEDULER_INACTIVE"), ("ausgefallen", "SENSOR_UNAVAILABLE"), ("unbekannt", "SAMPLING_GAP")):
        if c[k] / miss >= 0.5:
            return name
    return "UNKNOWN_CAUSE"


def sensor_finding(conn, now):
    """E2 finding 'wm_sensorabdeckung' (gap), at most one per 24 h; only after full observation period (ramp-up separate)."""
    if not _tbl(conn, "f3_wm_cover") or not _tbl(conn, "f3_wm_state"):
        return []
    c = coverage(conn, now)
    if not c or c["anlauf"] or c["C"] >= COV_MIN:
        return []
    if _tbl(conn, "f3_endo_befund"):
        last = conn.execute("select max(bucket) from f3_endo_befund where key='wm_sensorabdeckung'").fetchone()[0]
        if last is not None and int(now // BUCKET_S) - last < COV_GAP:
            return []
    why = cause(c)
    return [{"kind": "gap", "key": "wm_sensorabdeckung",
             "statement": "Sensor coverage %.0f %% (%d of %d windows in 24 h, threshold %.0f %%); cause %s (failed %d, no status %d, no tick %d); sampled only per hook run, temporal availability not recorded"
             % (100 * c["C"], c["valid"], c["expected"], 100 * COV_MIN, why, c["ausgefallen"], c["unbekannt"], c["keine_zeile"]),
             "ref": {"table": "f3_wm_cover", "where": "status='ok' and bucket>=%d and bucket<=%d" % (c["lo"], c["hi"]), "params": [], "n": c["valid"], "cause": why, "expected": c["expected"]}}]


OPTIONS = {
    "SCHEDULER_INACTIVE": "A) systemd user timer calling step() every 5 min (fixes the missing tick; runs permanently, needs approval); B) change nothing: coverage follows usage, the learning evidence takes correspondingly longer; C) enlarge the window length (changes the measurement design, breaks comparability). Recommendation: A after the owner's OK.",
    "SENSOR_UNAVAILABLE": "A) check the sensor/service (window-title sensor reports not active); B) keep windows without sensor as UNKNOWN; C) log failures and report only on permanent failure. A timer alone does not help here.",
    "SAMPLING_GAP": "A) Sensorstatus in f2_retina_sinne regelmaessig erfassen (eigene Stichprobe je Fenster); B) Luecken weiter als UNBEKANNT fuehren. Ein Timer allein hilft hier nicht.",
    "UNKNOWN_CAUSE": "A) record more diagnostic fields (sampling density, availability) before a measure is chosen; B) observe.",
}


def _request(conn, ref, attempt_id, now):
    for d in DDL:
        conn.execute(d)
    if conn.execute("select 1 from f3_wm_anfrage where attempt_id=?", (attempt_id,)).fetchone():
        return "anfrage"
    why = ref.get("cause") or "UNKNOWN_CAUSE"
    txt = ("Owner, my sensor coverage is too thin: %d of %d windows of the last 24 h are observed (threshold 80 %%), cause according to measurement %s. "
           "Options (rated, NOT executed; text rule-based from a template): %s") % (ref["n"], ref.get("expected", 0), why, OPTIONS.get(why, OPTIONS["UNKNOWN_CAUSE"]))
    conn.execute("insert into f3_wm_anfrage(ts,attempt_id,kind,text,evidence_ref,status) values(?,?,?,?,?,?)", (now, attempt_id, "sensor", txt, json.dumps(ref), "offen"))
    conn.commit()
    return "anfrage"


def _replay(rows, alpha):
    """One-step forecast over evaluated windows; start = frozen forecast of the first. -> mean Brier from the second window onward."""
    p, tot = json.loads(rows[0][3]), 0.0
    x0 = json.loads(rows[0][1])
    p = {c: (1 - alpha) * p[c] + alpha * x0[c] for c in CH}
    for r in rows[1:]:
        x = json.loads(r[1])
        tot += brier(p, x)
        p = {c: (1 - alpha) * p[c] + alpha * x[c] for c in CH}
    return tot / (len(rows) - 1)


def revise(conn, ref, attempt_id, now=None):
    """E5 investigation of a wm_prognosefehler target -> persistent revision W(n+1) or documented non-change. Idempotent per attempt_id."""
    now = time.time() if now is None else now
    if off(conn) or not _tbl(conn, "f3_wm_state"):
        return None
    for d in DDL:
        conn.execute(d)
    if conn.execute("select 1 from f3_wm_rev where attempt_id=?", (attempt_id,)).fetchone():
        return conn.execute("select to_version from f3_wm_rev where attempt_id=?", (attempt_id,)).fetchone()[0]
    st = _state(conn, now)
    rows = conn.execute("select bucket,obs,brier,pred,model_version,alpha from f3_wm_pred where %s order by bucket" % ref["where"], tuple(ref.get("params", ()))).fetchall()
    if len(rows) < WINDOW_N:
        return None  # Evidence no longer complete -> no revision on suspicion
    base = _replay(rows, st["alpha"])
    cand = {a: _replay(rows, a) for a in ALPHAS}
    best = min(cand, key=lambda a: (cand[a], a))
    gain = (base - cand[best]) / base if base > 0 else 0.0
    ev = json.dumps(ref)
    if best != st["alpha"] and gain >= MIN_REL_GAIN:
        v0, a0 = st["version"], st["alpha"]
        st["version"], st["alpha"] = v0 + 1, best
        cur = int(now // BUCKET_S)
        _freeze(conn, st, cur + 1, now)  # Not yet started window: SECOND forecast under W1, the v0 forecast remains unchanged
        _save(conn, st, now)
        conn.execute("insert into f3_wm_rev(ts,from_version,to_version,alpha_from,alpha_to,evidence_ref,brier_before,brier_after,decision,attempt_id) values(?,?,?,?,?,?,?,?,?,?)",
                     (now, v0, st["version"], a0, best, ev, base, cand[best], "revidiert", attempt_id))
    else:
        conn.execute("insert into f3_wm_rev(ts,from_version,to_version,alpha_from,alpha_to,evidence_ref,brier_before,brier_after,decision,attempt_id) values(?,?,?,?,?,?,?,?,?,?)",
                     (now, st["version"], st["version"], st["alpha"], st["alpha"], ev, base, cand[best], "keine_aenderung", attempt_id))
    conn.commit()
    return st["version"]


def on_pursuit(conn, goal_id, attempt_id, now=None):
    """Hook after goal_pursuit.pursue: does the goal belong to wm_prognosefehler -> revise. Reads only the goal."""
    if not attempt_id or not _tbl(conn, "f3_goal"):
        return None
    r = conn.execute("select evidence_refs,dedup_key from f3_goal where goal_id=?", (goal_id,)).fetchone()
    if not r:
        return None
    refs = json.loads(r[0])
    if not refs:
        return None
    if refs[0].get("table") == "f3_wm_cover":
        return _request(conn, refs[0], attempt_id, time.time() if now is None else now)
    if refs[0].get("table") != "f3_wm_pred":
        return None
    return revise(conn, refs[0], attempt_id, now)


def report(conn, version=None):
    """Prospective comparison per model version (only evaluated windows): model, W0 reference, persistence. No proof of learning without repeated cycles; versions are never mixed."""
    if not _tbl(conn, "f3_wm_pred"):
        return {"n": 0}
    v = "" if version is None else " and model_version=%d" % int(version)
    n, m, r = conn.execute("select count(*),avg(brier),avg(brier_ref) from f3_wm_pred where status='bewertet' and prospective=1" + v).fetchone()
    n2, m2, p2, r2 = conn.execute("select count(*),avg(brier),avg(brier_pers),avg(brier_ref) from f3_wm_pred where status='bewertet' and prospective=1 and brier_pers is not null" + v).fetchone()
    return {"n": n, "brier_model": m, "brier_ref": r, "skill": (1 - m / r) if n and r else None, "n_pers": n2, "brier_pers": p2,
            "skill_vs_pers": (1 - m2 / p2) if n2 and p2 else None, "unbekannt": conn.execute("select count(*) from f3_wm_pred where status='unbekannt'" + v).fetchone()[0]}
