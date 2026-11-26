"""MG-RL2-004 (DESIGN 18e): one-look grouped 5-fold CV of ONE preregistered config on non-blind sessions. Read-only."""
import hashlib, json, sys, time
from statistics import mean
from collections import defaultdict
import tpl_rl2_hparam as T
from mg.gate import paired_bootstrap

CAND, BASE = dict(rounds=300, minleaf=55, lr=0.3), dict(rounds=60, minleaf=20, lr=0.1)
rows = [r for r in T.load_rows() if not T.J.blind(r["sid"])]
fold = lambda sid: int(hashlib.sha256(sid.encode()).hexdigest(), 16) % 5
pred = {"base": [], "cand": []}
held, tpred = [], {"base": [], "cand": []}
for f in range(5):
    tr = [r for r in rows if fold(r["sid"]) != f]
    te = [r for r in rows if fold(r["sid"]) == f]
    held += te
    for name, p in (("base", BASE), ("cand", CAND)):
        m = T.G.fit(tr, **p)
        t = time.perf_counter()
        pred[name] += [min(0.98, max(0.02, T.G.predict_one(m, r["feat"]))) for r in te]
        tpred[name].append(1000 * (time.perf_counter() - t) / len(te))
    print("fold", f, len(te), flush=True)
loss = {}
for name in pred:
    per = defaultdict(list)
    for r, p in zip(held, pred[name]):
        per[r["sid"]].append((p - r["yb"]) ** 2)
    loss[name] = {s: -mean(v) for s, v in per.items()}
pooled = paired_bootstrap(loss["base"], loss["cand"], n=10000, seed=0)
labels = [r["yb"] for r in held]
auc_old, auc_new = T.auc(pred["base"], labels), T.auc(pred["cand"], labels)
ms_old, ms_new = mean(tpred["base"]), mean(tpred["cand"])
res = dict(PASS=pooled["ci_low"] > 0 and auc_new >= auc_old - 0.005 and ms_new <= 1.25 * ms_old + 0.05,
           pooled=pooled, auc_old=auc_old, auc_new=auc_new, predict_ms_old=ms_old, predict_ms_new=ms_new,
           n_sessions=len(loss["base"]), n_rows=len(held), cand=CAND, base=BASE)
(T.HERE / "rl2_004_confirm.json").write_text(json.dumps(res, indent=1) + "\n")
print(json.dumps(res, indent=1))
