"""MG-RL2-002 (DESIGN 17w): known-item rows from only a fraction f of train docs; tune f on DEV (digit a), confirm once on audit.

Usage: rl2_002_frac.py sweep            -> rl2_002_dev.json   (fresh copy per f, fit, DEV MRR + real-label AUC)
       rl2_002_frac.py audit <f>        -> rl2_002_audit.json (17u PASS rule, uses rl2_001 evaluate on a fresh copy)
Copies only; the live rl2.db is opened read-only by rl2_001.build().
"""
import hashlib
import json
import os
import sys
from contextlib import closing
from pathlib import Path
import sqlite3

import rl2_001_knownitem as R1

ROOT = Path("~/.cache/machine-god/rl2_002").expanduser()
PROBES = R1.STATE / "probes.jsonl"          # same probes as 17u (built once, deterministic)


def use(d):
    d.mkdir(parents=True, exist_ok=True)
    R1.STATE, R1.COPY = d, str(d / "rl2.db")
    os.environ["RL2_DB"] = R1.COPY


def hx(i):
    return hashlib.sha256(str(i).encode()).hexdigest()


def run_fit(f):
    probes = [json.loads(l) for l in open(PROBES)]
    R1.build()                                                     # fresh copy + base copy + probes (identical to 17u)
    train = sorted((p for p in probes if p["split"] == "train" and hx(p["doc_id"])[-1] != "a"), key=lambda p: hx(p["doc_id"]))
    keep = {p["doc_id"] for p in train[:round(f * len(train))]}
    with open(R1.STATE / "probes.jsonl", "w") as o:               # train() reads only split=='train' rows -> restrict them to the f-subset
        for p in probes:
            if p["split"] != "train" or p["doc_id"] in keep:
                o.write(json.dumps(p) + "\n")
    with closing(sqlite3.connect(R1.COPY)) as c:
        R1.train(c)
    return len(keep)


def dev_eval():
    from mg.gate import paired_bootstrap
    base = sqlite3.connect((R1.STATE / "rl2_base.db").as_uri() + "?mode=ro", uri=True)
    c = sqlite3.connect(R1.COPY)
    old, new = R1.K.Model.load(base), R1.K.Model.load(c)
    dev = [json.loads(l) for l in open(PROBES)]
    dev = [p for p in dev if p["split"] == "train" and hx(p["doc_id"])[-1] == "a"]

    def rr(conn, m, p, cell):
        return next((1 / (i + 1) for i, h in enumerate(R1.rank(conn, m, p[cell])[:5]) if h["id"] == p["doc_id"]), 0.0)
    o = {f"{cell}|{p['doc_id']}": rr(base, old, p, cell) for p in dev for cell in R1.CELLS}
    n = {f"{cell}|{p['doc_id']}": rr(c, new, p, cell) for p in dev for cell in R1.CELLS}
    judged = [r for r in R1.read_rows("judged.jsonl") if R1.split_of(r["doc"]) != "train"]
    auc = [R1.mann_whitney([(m.logit(r["feat"]), r["j"] >= 2) for r in judged]) for m in (old, new)]
    return {"dev_pooled": paired_bootstrap(o, n, n=10000, seed=0), "auc_old": auc[0], "auc_new": auc[1], "n_dev": len(dev)}


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    if sys.argv[1:2] == ["sweep"]:
        out = {}
        for f in [float(x) for x in sys.argv[2:]] or (0.02, 0.05, 0.1):
            use(ROOT / f"f{f}")
            k = run_fit(f)
            r = dict(dev_eval(), n_train_docs=k)
            r["fit_accepted"] = "NOT accepted" not in (R1.STATE / "fit.log").read_text()   # RL2's own blind gate can refuse the refit
            r["qualifies"] = r["fit_accepted"] and r["auc_new"] >= r["auc_old"] - 0.01 and r["dev_pooled"]["ci_low"] > 0
            out[str(f)] = r
            print(f, json.dumps(r), flush=True)
            (here / ("rl2_002_dev.json" if len(sys.argv) == 2 else "rl2_003_dev.json")).write_text(json.dumps(out, indent=1) + "\n")
        if len(sys.argv) > 2:                                       # loop trial (mg_loop.py): one result with a top-level PASS
            import shutil                                           # disk guard: keep only the 3 newest copy dirs (~1 GB each)
            for d in sorted(ROOT.glob("f*"), key=lambda p: p.stat().st_mtime)[:-3]:
                shutil.rmtree(d, ignore_errors=True)
            (here / "rl2_003_result.json").write_text(json.dumps(dict(r, PASS=r["qualifies"], pooled=r["dev_pooled"]), indent=1) + "\n")
    elif sys.argv[1:2] == ["audit"]:
        f = float(sys.argv[2])
        use(ROOT / f"f{f}")
        with closing(sqlite3.connect(Path(R1.COPY).as_uri() + "?mode=rw", uri=True)) as c:
            R1.evaluate(c, "audit")
        os.replace(here / "rl2_001_audit.json", here / "rl2_002_audit.json")
    else:
        sys.exit(__doc__)
