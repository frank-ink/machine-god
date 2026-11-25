"""MG-1 gate: decision statistics (paired bootstrap + preregistered decision). Stdlib only."""
import argparse
import json
import math
import random
import sys

MIN_OVERLAP = 0.8


def paired_bootstrap(base, cand, n=10000, seed=0):
    """Paired bootstrap of mean(cand - base) over items present in base.
    Items in base but missing in cand count as cand score 0.0.
    Raises ValueError if overlap < 80% of base items, base is empty, or non-finite values exist."""
    if not base:
        raise ValueError("base is empty")
    if n < 1:
        raise ValueError("n must be >= 1")

    base_items = set(base.keys())
    cand_items = set(cand.keys())
    common = base_items & cand_items
    n_missing = len(base_items - cand_items)

    if len(common) / len(base) < MIN_OVERLAP:
        raise ValueError("overlap %d/%d below %.0f%%" % (len(common), len(base), MIN_OVERLAP * 100))

    # Build differences: for items in base, use cand score if present else 0.0
    d = []
    for item in base:
        b_score = base[item]
        c_score = cand.get(item, 0.0)
        if not math.isfinite(b_score) or not math.isfinite(c_score):
            raise ValueError("non-finite score for item %s" % item)
        d.append(c_score - b_score)

    m = len(d)  # == len(base)
    rnd = random.Random(seed)
    means = sorted(sum(rnd.choices(d, k=m)) / m for _ in range(n))
    lo_idx = int(0.025 * (n - 1))
    hi_idx = int(round(0.975 * (n - 1)))
    lo, hi = means[lo_idx], means[hi_idx]

    return {
        "delta": sum(d) / m,
        "ci_low": lo,
        "ci_high": hi,
        "n_items": m,
        "n_missing": n_missing
    }


def _guard_ok(g):
    """-> (ok, reason). kind hard: no worse than base; soft: no worse than base by more than tol.
    direction 'higher' (default, quality) or 'lower' (cost/latency).
    Raises ValueError if guard dict lacks 'base' or 'cand'."""
    if "base" not in g or "cand" not in g:
        raise ValueError("guard missing 'base' or 'cand'")
    lower = g.get("direction", "lower" if g.get("cost") else "higher") == "lower"
    b, c = g["base"], g["cand"]
    tol = 0.0 if g.get("kind", "hard") == "hard" else float(g.get("tol", 0.0))
    ok = c <= b + tol if lower else c >= b - tol
    return ok, None if ok else "guard %s (%s) %s: base %.4g cand %.4g tol %.4g" % (
        g.get("name", "?"), g.get("kind", "hard"), "worse" if not lower else "higher cost", b, c, tol)


def decide(target, guards=(), min_effect=0.0, min_n=1):
    """PASS | FAIL | INSUFFICIENT_EVIDENCE for a preregistered (min_effect, min_n).
    n < min_n -> INSUFFICIENT_EVIDENCE; failed guard -> FAIL; ci_low > 0 and delta >= min_effect -> PASS;
    even the optimistic bound ci_high <= max(min_effect, 0) -> FAIL; otherwise the CI is inconclusive."""
    reasons = []
    if target["n_items"] < min_n:
        return {"decision": "INSUFFICIENT_EVIDENCE", "reasons": ["n_items %d < min_n %d" % (target["n_items"], min_n)]}
    bad = [r for ok, r in map(_guard_ok, guards) if not ok]
    if bad:
        return {"decision": "FAIL", "reasons": bad}
    if target["ci_low"] > 0 and target["delta"] >= min_effect:
        return {"decision": "PASS", "reasons": ["ci_low %.4g > 0, delta %.4g >= min_effect %.4g" % (target["ci_low"], target["delta"], min_effect)]}
    if target["ci_high"] <= max(min_effect, 0.0):
        return {"decision": "FAIL", "reasons": ["ci_high %.4g <= min_effect %.4g: effect excluded" % (target["ci_high"], max(min_effect, 0.0))]}
    return {"decision": "INSUFFICIENT_EVIDENCE", "reasons": ["CI [%.4g, %.4g] inconclusive for min_effect %.4g" % (target["ci_low"], target["ci_high"], min_effect)]}


def load_scores(path, metric):
    out = {}
    seen = set()
    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError("line %d: invalid JSON: %s" % (line_num, e))
            if r.get("metric") != metric:
                continue
            if "item_id" not in r or "score" not in r:
                raise ValueError("line %d: missing item_id or score" % line_num)
            item_id = r["item_id"]
            if item_id in seen:
                raise ValueError("line %d: duplicate item_id %s" % (line_num, item_id))
            seen.add(item_id)
            out[item_id] = float(r["score"])
    return out


def main(argv=None):
    p = argparse.ArgumentParser(prog="mg.gate")
    p.add_argument("--base", required=True)
    p.add_argument("--cand", required=True)
    p.add_argument("--metric", required=True)
    p.add_argument("--guards")
    p.add_argument("--n", type=int, default=10000)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--min-effect", type=float, default=0.0)
    p.add_argument("--min-n", type=int, default=1)
    a = p.parse_args(argv)
    try:
        t = paired_bootstrap(load_scores(a.base, a.metric), load_scores(a.cand, a.metric), a.n, a.seed)
        guards = []
        if a.guards:
            with open(a.guards) as f:
                guards = json.load(f)
        result = decide(t, guards, a.min_effect, a.min_n)
    except (ValueError, KeyError, TypeError, AttributeError, OSError, json.JSONDecodeError) as e:
        print(json.dumps({"error": str(e)}))
        return 2
    print(json.dumps({"bootstrap": t, **result}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
