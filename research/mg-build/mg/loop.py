"""MG-4 orchestrator skeleton (dry run: only measures and writes the ledger, never changes a retriever).
Splits: dev -> promo (only after dev PASS) -> audit (only after promo PASS). Promo attempts are counted per bench_version.
Refuses: live DB (any unified.db), kill file (~/.local/share/machine-god/KILL, override MG_KILL_FILE)."""
import argparse
import json
import os
import sys

from mg import bench_retrieval as br, gate, ledger

KILL = os.path.expanduser("~/.local/share/machine-god/KILL")


class Refused(RuntimeError):
    pass


def kill_file():
    return os.environ.get("MG_KILL_FILE", KILL)


def _measure(conn, probes, retr, k):
    rows = br.run_probes(conn, probes, retr, k)
    return rows, {r["item_id"]: r["mrr_at_10"] for r in rows}


def _stage(db_conn, led, trial_id, role, split, probes, retr, k, suite_id):
    rows, scores = _measure(db_conn, probes, retr, k)
    ledger.write_run_items(led, "%s:%s:%s" % (trial_id, split, role), suite_id,
                           [(r["item_id"], m, r[m]) for r in rows for m in ("rr", "hit1", "hit5", "mrr_at_10")])
    return scores


def trial(db, led_path, hypothesis, base_spec, cand_spec, dev, promo=None, audit=None, bench_version="v0", min_effect=0.0, min_n=10,
          budget_s=600.0, max_promo_attempts=5, k=10, seed=0, n_boot=2000):
    ledger.guard_path(db)
    if os.path.exists(kill_file()):
        raise Refused("kill file present: " + kill_file())
    led = ledger.connect(led_path)
    db_conn = br.open_ro(db)
    base_r, cand_r = br.load_retriever(base_spec), br.load_retriever(cand_spec)
    tid = ledger.new_trial_id()
    ledger.write_prereg(led, tid, hypothesis, "mrr_at_10", min_effect, min_n, budget_s, bench_version)
    suite_id = ledger.new_suite(led, "trial:" + tid, bench_version, len(dev))
    stages, reached, promo_done, final = {}, "dev", 0, "INSUFFICIENT_EVIDENCE"
    for name, probes in (("dev", dev), ("promo", promo), ("audit", audit)):
        if probes is None:
            break
        if name == "promo":
            if ledger.promo_attempts(led, bench_version) >= max_promo_attempts:
                ledger.write_trial(led, tid, hypothesis, bench_version, base_spec, cand_spec, "dev", "REFUSED_PROMO_BUDGET", 0, {"stages": stages})
                raise Refused("promo attempts for bench_version %s exhausted (%d)" % (bench_version, max_promo_attempts))
            promo_done = 1
        reached = name
        b = _stage(db_conn, led, tid, "base", name, probes, base_r, k, suite_id)
        c = _stage(db_conn, led, tid, "cand", name, probes, cand_r, k, suite_id)
        boot = gate.paired_bootstrap(b, c, n_boot, seed)
        d = gate.decide(boot, [], min_effect, min_n)
        stages[name] = {"bootstrap": boot, **d}
        final = d["decision"]
        if final != "PASS":
            break
    decision = "keep" if (final == "PASS" and reached == "audit") else ("reject" if final == "FAIL" else "insufficient_evidence")
    ledger.write_trial(led, tid, hypothesis, bench_version, base_spec, cand_spec, reached, decision, promo_done, {"stages": stages})
    return {"trial_id": tid, "decision": decision, "stage_reached": reached, "stages": stages}


def main(argv=None):
    p = argparse.ArgumentParser(prog="mg.loop")
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("trial")
    t.add_argument("--hypothesis", required=True); t.add_argument("--base-retriever", required=True); t.add_argument("--cand-retriever", required=True)
    t.add_argument("--db", required=True); t.add_argument("--ledger", required=True)
    t.add_argument("--probes-dev", required=True); t.add_argument("--probes-promo", required=True); t.add_argument("--probes-audit", required=True)
    t.add_argument("--bench-version", default="v0"); t.add_argument("--min-effect", type=float, default=0.0); t.add_argument("--min-n", type=int, default=10)
    t.add_argument("--budget-s", type=float, default=600.0); t.add_argument("--max-promo-attempts", type=int, default=5)
    a = p.parse_args(argv)
    try:
        r = trial(a.db, a.ledger, a.hypothesis, a.base_retriever, a.cand_retriever, br.load_probes(a.probes_dev), br.load_probes(a.probes_promo),
                  br.load_probes(a.probes_audit), a.bench_version, a.min_effect, a.min_n, a.budget_s, a.max_promo_attempts)
    except (Refused, PermissionError, ValueError) as e:
        print(json.dumps({"refused": str(e)})); return 3
    print(json.dumps(r, indent=1)); return 0


if __name__ == "__main__":
    sys.exit(main())
