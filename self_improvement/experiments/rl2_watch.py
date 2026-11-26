"""Live re-measure of an adopted RL2 model (DESIGN 2.5, 19 item 3). Read-only.
Scores the SERVED model and the pre-adoption model (backup db) on real labels judged AFTER the adoption time.
PASS 'pending' until >= 5 new sessions; PASS false if served AUC < pre-adoption AUC - 0.01."""
import json, os, sqlite3, sys
from pathlib import Path
sys.path.insert(0, os.path.expanduser("~/.claude/star/modules/rl2"))
import rl2_core as K
import tpl_rl2_hparam as T

since, backup, out = float(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
ro = lambda p: sqlite3.connect(Path(p).resolve().as_uri() + "?mode=ro", uri=True)
new = [r for r in T.J.load_judged() if T.real(r) and float(r.get("t") or 0) > since]
sids = {r["sid"] for r in new}
res = {"n_sessions": len(sids), "n_rows": len(new), "since": since}
if len(sids) < 5 or len({r["j"] >= 2 for r in new}) < 2:
    res["PASS"] = "pending"
else:
    served, old = K.Model.load(ro(K.DB if hasattr(K, "DB") else os.path.expanduser("~/.claude/star/rl2/rl2.db"))), K.Model.load(ro(backup))
    labels = [r["j"] >= 2 for r in new]
    res["auc_served"] = T.auc([served.logit(r["feat"]) for r in new], labels)
    res["auc_before"] = T.auc([old.logit(r["feat"]) for r in new], labels)
    res["PASS"] = res["auc_served"] >= res["auc_before"] - 0.01
out.write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res))
