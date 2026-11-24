"""Test-Tor Retina-Thalamus Stueck 2 (a-e). Lauf: python3 -I test_retina_thalamus.py (Exit 0 = gruen).
(a) Gain gleich Original (vendored Thalamus._compute_final_gain, falls vorhanden; sonst nur Handwerte)  (b) Erholung <0.5 nach 3*tau
(c) kein Fixpunkt / keine zwei Haufen ueber 1000 simulierte Tore  (d) Burst-Anteil >0 und <=50 %  (e) Rueckkanal wirkt."""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import retina_thalamus as rt

VENDOR = os.environ.get("MG_THALAMUS_VENDOR", "/nonexistent")
W = 300.0


def t_a_formel_handwerte():
    g = rt.final_gain(0.5, 0.0, 1.0, 0.0, 0.0, False, 0.0, 0.0)
    assert abs(g - 0.5) < 1e-12
    g = rt.final_gain(0.5, 1.0, 1.0, 0.0, 0.0, False, 0.0, 0.0)  # voll habituiert: 0.5*0.2
    assert abs(g - 0.1) < 1e-12
    assert abs(rt.final_gain(0.1, 0.0, 1.0, 0.0, 0.0, True, 0.0, 0.0) - 0.2) < 1e-12  # Burst x2


def t_a_gegen_original():
    if not os.path.exists(os.path.join(VENDOR, "thalamus.py")):
        print("  (Original nicht vorhanden, Vergleich uebersprungen)")
        return
    sys.path.insert(0, VENDOR)
    import thalamus as T
    rnd, n = random.Random(7), 0
    for _ in range(300):
        ch = rnd.choice(list(T.CHANNELS))
        cs = T.ChannelState(name=ch)
        cs.habituation, cs.burst, cs.prediction_error = rnd.random(), rnd.random() < 0.3, rnd.random()
        nov, attn, vig, fb = rnd.random(), rnd.random() * 1.5, rnd.uniform(-1, 1), rnd.choice([0.0, 0.15, -0.05, 0.07])
        o = object.__new__(T.Thalamus)
        o._feedback_bias = {ch: fb}
        want = o._compute_final_gain(ch, cs, nov, attn, 1.0 + max(-1.0, min(1.0, vig)) * 0.3, False)
        got = rt.final_gain(T.CHANNELS[ch]["base_gain"], cs.habituation, attn, vig, nov, cs.burst, fb, cs.prediction_error)
        assert abs(want - got) < 1e-9, (ch, want, got)
        n += 1
    print("  (a) gegen Original: %d Faelle gleich" % n)


def t_b_erholung():
    for n, c in rt.CHANNELS.items():
        t = rt.RetinaThalamus()
        t.s[n]["h"], t.s[n]["last_ts"] = 1.0, 0.0
        t.gate({}, 3 * c["tau"])  # Pause > 3*tau, kein Inhalt
        assert t.s[n]["h"] < 0.5, (n, t.s[n]["h"])
    # Gegenprobe Original-Defekt: gleicher Inhalt immer wieder -> H waechst (gewollt), erst Stille erholt
    t = rt.RetinaThalamus()
    for i in range(40):
        t.gate({"fokus_app": 3}, i * W)
    assert t.s["fokus_app"]["h"] > 0.9
    t.gate({}, 40 * W + 3 * rt.CHANNELS["fokus_app"]["tau"])
    assert t.s["fokus_app"]["h"] < 0.5


def _sim(seed, n=1000):
    rnd, t, ts, rows = random.Random(seed), rt.RetinaThalamus(), 0.0, []
    for _ in range(n):
        ts += W
        cnt = {k: (rnd.choice([1, 1, 2, 3, 5, 8]) if rnd.random() < p else 0) for k, p in
               {"person_kommt": 0.04, "person_geht": 0.04, "fokus_app": 0.3, "objekt_neu": 0.45, "objekt_weg": 0.45}.items()}
        real = ("amygdala",) if rnd.random() < 0.01 else ()
        r = t.gate({k: v for k, v in cnt.items() if v}, ts, real=real)
        rows.append((cnt, r))
        if r["relay"] and rnd.random() < 0.5:
            t.receive_feedback(rnd.sample(r["relay"], 1))
    return rows


def t_c_kein_fixpunkt_keine_zwei_haufen():
    rows = _sim(1)
    for n in rt.CHANNELS:
        hs = [r["hab"][n] for _, r in rows]
        hi, lo = sum(h > 0.95 for h in hs) / len(hs), sum(h < 0.1 for h in hs) / len(hs)
        print("  (c) %-13s H>0.95: %4.1f %%  H<0.1: %4.1f %%  max %.3f" % (n, 100 * hi, 100 * lo, max(hs)))
        assert hi < 0.5, ("Fixpunkt", n, hi)
        assert not (hi > 0.25 and lo > 0.25), ("zwei Haufen", n, hi, lo)
    rel = sum(1 for cnt, r in rows for k in cnt if cnt[k] and k in r["relay"])
    tot = sum(1 for cnt, r in rows for k in cnt if cnt[k])
    print("  (c) Relais-Anteil mit Inhalt: %.1f %%" % (100.0 * rel / tot))
    assert 0 < rel < tot, "alles oder nichts"


def t_d_burst_anteil():
    rows = _sim(2)
    b = sum(1 for _, r in rows if r["burst"])
    s = sum(1 for _, r in rows if r["relay"] or r["burst"])
    share = b / max(1, s)
    print("  (d) Burst-Tore %d von %d aktiven (%.1f %%)" % (b, s, 100 * share))
    assert b > 0 and share <= 0.5
    t = rt.RetinaThalamus()  # B: nur echte Signale, nie Dauerstatus
    for i in range(50):
        assert not t.gate({"fokus_app": 2}, i * W)["burst"]
    r = t.gate({"person_kommt": 1}, 60 * W)  # Rueckkehr: erste Person nach langer Abwesenheit ohne Vorgaenger -> kein Burst
    t.gate({"person_geht": 1}, 61 * W)
    assert t.gate({"person_kommt": 1}, 61 * W + rt.RETURN_ABSENCE_S + 1)["burst"] == ["person_kommt"]


def t_e_rueckkanal():
    def gain(fb_ref):
        t = rt.RetinaThalamus()
        t.gate({"objekt_neu": 1, "fokus_app": 1}, 0.0)
        t.receive_feedback(fb_ref)
        return t.gate({"objekt_neu": 2, "fokus_app": 2}, W)["gains"]
    base, named = gain([]), gain(["objekt_neu"])
    assert named["objekt_neu"] > base["objekt_neu"] and named["fokus_app"] <= base["fokus_app"] + 1e-12
    t = rt.RetinaThalamus()
    t.receive_feedback(["fokus_app"])
    fb0 = t.s["fokus_app"]["fb"]
    for i in range(10):
        t.gate({}, i * W)
    assert 0 < t.s["fokus_app"]["fb"] < fb0 * 0.3  # klingt ab


def t_lane_idempotent_isolation_schalter():
    import sqlite3
    import retina_thalamus_lane as L
    B = L.BUCKET_S
    c = sqlite3.connect(":memory:")
    c.execute("create table star_konfig(schluessel text primary key, wert text)")
    c.execute("create table f2_retina_geschehen(id integer primary key, ts real, art text, bits real)")
    c.execute("create table f3_grid_v2_state(singleton integer primary key, j text, updated real)")
    c.executemany("insert into f2_retina_geschehen(ts,art,bits) values(?,?,?)",
                  [(996 * B + 5, "person_kommt", 1.5), (997 * B + 5, "fokus_app", 1.6), (998 * B + 1, "objekt_neu", 2.0)])
    now = 1000 * B + 10
    n1, n2 = L.step_buckets(c, now), L.step_buckets(c, now)
    assert n1 >= 1 and n2 == 0, (n1, n2)
    assert c.execute("select count(*) from f3_grid_v2_state").fetchone() == (0,)  # Haupt-State unberuehrt
    rows = c.execute("select bucket from f3_retina_thal_log").fetchall()
    assert len({r[0] for r in rows}) == len(rows) == c.execute("select count(*) from f3_grid_v2g_log").fetchone()[0]
    c.execute("insert into star_konfig values('frank3.retina_thal.mode','off')")
    assert L.step_buckets(c, now + 5 * B) == 0
    c.execute("update star_konfig set wert='shadow' where schluessel='frank3.retina_thal.mode'")
    c.execute("insert into star_konfig values('frank3.kill','1')")
    assert L.step_buckets(c, now + 5 * B) == 0


def t_lane_echtdaten_replay():
    import sqlite3
    import retina_thalamus_lane as L
    real = os.environ.get("MG_REAL_DB", "")
    if not os.path.exists(real):
        print("  (kein Echtdaten-DB, Replay uebersprungen)")
        return
    c = sqlite3.connect("file:%s?mode=ro" % real, uri=True)
    lo, hi = c.execute("select min(ts),max(ts) from f2_retina_geschehen").fetchone()
    out = L.replay(c, int(lo // L.BUCKET_S), int(hi // L.BUCKET_S))
    raw, kept = sum(o[1] for o in out), sum(o[2] for o in out)
    bur = sum(1 for o in out if o[0]["burst"])
    print("  replay: Ereignisse roh=%d relayt=%d (%.1f %%) Burst-Fenster=%d" % (raw, kept, 100.0 * kept / max(1, raw), bur))
    assert kept > 0 and bur > 0
    assert max(s for o in out for s in o[0]["hab"].values()) < 0.99  # kein Fixpunkt 1.0 (Originaldefekt)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("t_"):
            fn()
            print("ok", name)
    print("ALLE GRUEN")
