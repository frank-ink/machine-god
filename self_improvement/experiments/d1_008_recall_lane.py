"""MG-D1-008-RECALL-LANE (DESIGN 17s): frank-brain udb lane, F off vs on, on the live unified.db (read-only)."""
import importlib.util
import json
import os
import random
import re
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "mgfixed"))
from mg.gate import paired_bootstrap  # noqa: E402

spec = importlib.util.spec_from_file_location("bridge", os.path.expanduser("~/repos/github_all/frank-brain-mcp/server/bridge.py"))
BR = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BR)
c = sqlite3.connect("file:" + BR.DB + "?mode=ro", uri=True)
c.execute("create virtual table if not exists temp.v using fts5vocab(main, uu_fts, row)")
rows = c.execute("select m.memory_id, m.subject, m.value from durable_memory m join uu_fts_doc d on d.memory_id = m.memory_id "
                 "where m.kind != 'ereignis' and length(m.value) >= 200 order by m.memory_id").fetchall()
rnd = random.Random(11)
pick = rnd.sample(rows, 400)
WORD = re.compile(r"[a-z]{6,}")


def typo(w):
    i = rnd.randrange(1, len(w) - 2)
    return w[:i] + w[i + 1] + w[i] + w[i + 2:]


probes = []
for mid, subj, val in pick:
    ws = sorted(set(WORD.findall((str(subj or "") + " " + str(val or "")).lower())))
    df = dict(c.execute("select term, doc from temp.v where term in (%s)" % ",".join("?" * len(ws)), ws)) if ws else {}
    ws = sorted((w for w in ws if df.get(w, 0) > 0), key=lambda w: (df[w], w))[:6]
    if len(ws) < 6:
        continue
    idx = rnd.sample(range(6), 2)
    probes.append((mid, ws, [typo(w) if i in idx else w for i, w in enumerate(ws)]))


def run(flag, words):
    os.environ["FRANK_RECALL_F"] = flag
    return [h["id"][4:] for h in BR._udb_hits(" ".join(words), None, 6)]


def rr5(ids, mid):
    return next((1.0 / (i + 1) for i, x in enumerate(ids[:5]) if x == mid), 0.0)


out = {"n_probes": len(probes)}
for cell, j in (("clean", 1), ("P3", 2)):
    off = {p[0]: rr5(run("0", p[j]), p[0]) for p in probes}
    on = {p[0]: rr5(run("1", p[j]), p[0]) for p in probes}
    bs = paired_bootstrap(off, on, n=10000, seed=0)
    out[cell] = {"off": round(sum(off.values()) / len(off), 4), "on": round(sum(on.values()) / len(on), 4),
                 "delta": round(bs["delta"], 4), "ci": [round(bs["ci_low"], 4), round(bs["ci_high"], 4)],
                 "better": sum(on[k] > off[k] for k in off), "worse": sum(on[k] < off[k] for k in off)}
reps = []
qs = [w for p in probes for w in (p[1], p[2])]
for rep in range(6):
    lat = {"0": [], "1": []}
    for w in qs:
        for f in ("0", "1"):
            t = time.perf_counter()
            run(f, w)
            lat[f].append((time.perf_counter() - t) * 1000)
    if rep:
        p = {f: sorted(v)[int(.95 * len(v))] for f, v in lat.items()}
        reps.append({"p95_off": round(p["0"], 1), "p95_on": round(p["1"], 1), "load1": os.getloadavg()[0]})
med = lambda k: sorted(r[k] for r in reps)[len(reps) // 2]  # noqa: E731
out["latency_reps"] = reps
out["latency_median_p95"] = {"off": med("p95_off"), "on": med("p95_on")}
out["latency_pass"] = med("p95_on") <= 1.25 * med("p95_off") or med("p95_on") <= 150
out["PASS"] = out["P3"]["ci"][0] > 0 and out["clean"]["ci"][0] >= -0.02 and out["latency_pass"]
json.dump(out, open(os.path.join(HERE, "d1_008_recall_lane.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
