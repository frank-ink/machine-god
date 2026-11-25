"""Compare GBM hyperparameters on held-out RL2 sessions."""
import argparse
from collections import defaultdict
from contextlib import closing
import hashlib
from itertools import groupby
import json
import os
from pathlib import Path
import sqlite3
from statistics import mean
import sys
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "mgfixed"))
from mg.gate import paired_bootstrap

sys.path.insert(0, os.path.expanduser("~/.claude/star/modules/rl2"))
import rl2_judge as J
import rl2_gbm as G


def connect_ro(path, **kwargs):
    return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, **kwargs)


def real(row):
    return all(not (row.get(key) or "").startswith("mgki") for key in ("src", "sid"))


def load_rows():
    judged = [row for row in J.load_judged() if real(row)]
    with closing(connect_ro(J.DB)) as db:
        if not os.path.exists(J.SEM_CF):
            J.augment_sem(judged, db)
        # rows_for_fit opens its own connection to compute semantic features.
        with patch.object(J, "sqlite3", SimpleNamespace(connect=connect_ro)):
            rows = J.rows_for_fit(judged)
        # explicit_rows drops src when it constructs fit rows.
        explicit = SimpleNamespace(execute=lambda sql: db.execute(
            f"SELECT * FROM ({sql}) WHERE COALESCE(substr(src, 1, 4), '') != 'mgki'"
        ))
        rows += J.explicit_rows(explicit)
    return [row for row in rows if real(row)]


def auc(scores, labels):
    """Mann–Whitney AUC with half credit for ties."""
    positives = sum(labels)
    negatives = len(labels) - positives
    if not positives or not negatives:
        raise ValueError("AUC requires both label classes in the selected split")
    wins = negatives_below = 0
    for _, group in groupby(sorted(zip(scores, labels)), key=lambda pair: pair[0]):
        tied = [label for _, label in group]
        tied_positives = sum(tied)
        tied_negatives = len(tied) - tied_positives
        wins += tied_positives * (negatives_below + tied_negatives / 2)
        negatives_below += tied_negatives
    return wins / (positives * negatives)


def score(model, rows):
    scores = [min(0.98, max(0.02, G.predict_one(model, row["feat"]))) for row in rows]
    losses = defaultdict(list)
    for row, prediction in zip(rows, scores):
        losses[row["sid"]].append((prediction - row["yb"]) ** 2)
    return {sid: -mean(values) for sid, values in losses.items()}, auc(scores, [r["yb"] for r in rows])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("split", choices=("dev", "audit"))
    parser.add_argument("rounds", type=int)
    parser.add_argument("minleaf", type=int)
    parser.add_argument("lr", type=float)
    args = parser.parse_args()
    params = dict(rounds=args.rounds, minleaf=args.minleaf, lr=args.lr)
    train, held_out = [], []
    for row in load_rows():
        sid = row["sid"]
        if not J.blind(sid):
            train.append(row)
        elif (hashlib.sha256(sid.encode()).hexdigest()[-1] < "8") == (args.split == "dev"):
            held_out.append(row)

    base, auc_old = score(G.fit(train, rounds=60, minleaf=20), held_out)
    cand, auc_new = score(G.fit(train, **params), held_out)
    pooled = paired_bootstrap(base, cand, n=10000, seed=0)
    result = dict(PASS=pooled["ci_low"] > 0 and auc_new >= auc_old - 0.005,
                  pooled=pooled, auc_old=auc_old, auc_new=auc_new,
                  n_sessions=len(base), n_rows=len(held_out), params=params, fit_accepted=True)
    output = json.dumps(result, indent=2)
    (HERE / f"tpl_rl2_hparam_{args.split}.json").write_text(output + "\n")
    print(output)


if __name__ == "__main__":
    main()
