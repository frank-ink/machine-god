"""MG-4 orchestrator skeleton (dry run: only measures and writes the ledger, never changes a retriever).
Splits: dev -> promo (only after dev PASS) -> audit (only after promo PASS). Promo attempts are counted per bench_version.
Refuses: live DB (any path ending in MG_LIVE_SUFFIX, or a file listed in MG_PROTECTED_DB), kill file (~/.local/share/machine-god/KILL, override MG_KILL_FILE).

Known limitation: candidate retriever code runs in-process (no sandbox).
"""
import argparse
import hashlib
import json
import os
import sys
import time

from mg import bench_retrieval as br, gate, ledger

KILL = os.path.expanduser("~/.local/share/machine-god/KILL")


class Refused(RuntimeError):
    decision = "ABORTED"  # what the trial row records when this refusal ends a run


class PromoBudgetRefused(Refused):
    decision = "REFUSED_PROMO_BUDGET"


def kill_file():
    """Return list of kill file paths to check. Default KILL path always applies; MG_KILL_FILE may ADD an extra path."""
    paths = [KILL]
    env_kill = os.environ.get("MG_KILL_FILE")
    if env_kill:
        paths.append(env_kill)
    return paths


def check_kill():
    """Check all kill file paths. Uses os.path.lexists so dead symlinks count."""
    for path in kill_file():
        if os.path.lexists(path):
            raise Refused("kill file present: " + path)


def _derive_bench_version(dev_probes, promo_probes):
    """Derive bench_version from sorted dev and promo item_ids."""
    item_ids = []
    if dev_probes:
        item_ids.extend(p["item_id"] for p in dev_probes)
    if promo_probes:
        item_ids.extend(p["item_id"] for p in promo_probes)
    item_ids = sorted(set(item_ids))
    data = "\n".join(item_ids).encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()[:16]
    return "b-" + digest


def _check_splits_disjoint(dev, promo, audit):
    """Check that dev, promo, audit are pairwise disjoint by item_id and (query, expect) pair.
    Also check for duplicate item_ids within each split.
    """
    splits = {"dev": dev, "promo": promo, "audit": audit}
    all_item_ids = {}
    all_query_expect = {}
    
    for name, probes in splits.items():
        if probes is None:
            continue
        seen_ids = set()
        for p in probes:
            item_id = p["item_id"]
            qe = (p["query"], p["expect_doc_id"])
            
            # Check duplicate item_id within split (repeated query/expect pairs inside one split are legal)
            if item_id in seen_ids:
                raise Refused(f"duplicate item_id in {name}: {item_id}")
            seen_ids.add(item_id)
            
            # Check across splits
            if item_id in all_item_ids:
                raise Refused(f"item_id {item_id} appears in both {all_item_ids[item_id]} and {name}")
            all_item_ids[item_id] = name
            
            if qe in all_query_expect:
                raise Refused(f"(query, expect) pair appears in both {all_query_expect[qe]} and {name}")
            all_query_expect[qe] = name


def _measure(conn, probes, retr, k):
    rows = br.run_probes(conn, probes, retr, k)
    return rows, {r["item_id"]: r["mrr_at_10"] for r in rows}


def _stage(db_conn, led, trial_id, role, split, probes, retr, k, suite_id):
    rows, scores = _measure(db_conn, probes, retr, k)
    ledger.write_run_items(led, "%s:%s:%s" % (trial_id, split, role), suite_id,
                           [(r["item_id"], m, r[m]) for r in rows for m in ("rr", "hit1", "hit5", "mrr_at_10")])
    return rows, scores


def _compute_summary(rows):
    """Compute summary including mean latency."""
    n = len(rows) or 1
    return {
        "n": len(rows),
        "hit1": sum(r["hit1"] for r in rows) / n,
        "hit5": sum(r["hit5"] for r in rows) / n,
        "mrr": sum(r["rr"] for r in rows) / n,
        "mrr_at_10": sum(r["mrr_at_10"] for r in rows) / n,
        "probes_with_dead_terms": sum(1 for r in rows if r["dead_terms"]),
        "mean_latency_ms": sum(r["ms"] for r in rows) / n,
    }


def trial(db, led_path, hypothesis, base_spec, cand_spec, dev, promo=None, audit=None, bench_version="v0", min_effect=0.0, min_n=10,
          budget_s=600.0, max_promo_attempts=5, k=10, seed=0, n_boot=2000):
    start_time = time.monotonic()
    
    # Initial checks
    ledger.guard_path(db)
    check_kill()
    
    # Check splits disjointness upfront
    _check_splits_disjoint(dev, promo, audit)
    
    # Derive bench_version from dev+promo item_ids
    derived_bench_version = _derive_bench_version(dev, promo)
    
    led = ledger.connect(led_path)
    db_conn = br.open_ro(db)
    base_r = br.load_retriever(base_spec)
    cand_r = br.load_retriever(cand_spec)
    tid = ledger.new_trial_id()
    
    # Write prereg with derived bench_version
    ledger.write_prereg(led, tid, hypothesis, "mrr_at_10", min_effect, min_n, budget_s, derived_bench_version)
    
    # Insert trial start row with ABORTED decision
    ledger.insert_trial_start(led, tid, hypothesis, derived_bench_version,
                              base_retriever=base_spec, cand_retriever=cand_spec,
                              stage_reached="dev", promo_attempted=0,
                              detail={"bench_version_label": bench_version, "seed": seed, "n_boot": n_boot})
    
    suite_id = ledger.new_suite(led, "trial:" + tid, derived_bench_version, len(dev))
    stages, reached, promo_done, final = {}, "dev", 0, "INSUFFICIENT_EVIDENCE"
    
    try:
        for name, probes in (("dev", dev), ("promo", promo), ("audit", audit)):
            if probes is None:
                break
            
            # Check kill file before each stage
            check_kill()
            
            # Check budget
            if time.monotonic() - start_time > budget_s:
                raise Refused("budget exceeded")
            
            if name == "promo":
                # Claim promo attempt using derived bench_version
                if not ledger.claim_promo(led, tid, derived_bench_version, max_promo_attempts):
                    raise PromoBudgetRefused("promo budget exhausted")
                promo_done = 1
            
            reached = name
            
            # Measure base and candidate
            b_rows, b_scores = _stage(db_conn, led, tid, "base", name, probes, base_r, k, suite_id)
            c_rows, c_scores = _stage(db_conn, led, tid, "cand", name, probes, cand_r, k, suite_id)
            
            # Compute summaries for guards
            b_summary = _compute_summary(b_rows)
            c_summary = _compute_summary(c_rows)
            
            # Bootstrap
            boot = gate.paired_bootstrap(b_scores, c_scores, n_boot, seed)
            
            # Build guards
            # Hard guard: hit5 (cand hit5 >= base hit5, kind hard, higher-is-better)
            # Soft guard: mean latency ms (direction lower, kind soft, tol = 25% of base + 1ms)
            guards = [
                {
                    "name": "hit5",
                    "kind": "hard",
                    "base": b_summary["hit5"],
                    "cand": c_summary["hit5"],
                    "direction": "higher",
                },
                {
                    "name": "latency_ms",
                    "kind": "soft",
                    "base": b_summary["mean_latency_ms"],
                    "cand": c_summary["mean_latency_ms"],
                    "direction": "lower",
                    "tol": b_summary["mean_latency_ms"] * 0.25 + 1.0,
                },
            ]
            
            d = gate.decide(boot, guards, min_effect, min_n)
            
            # Record guard values in stage detail
            stage_detail = {"bootstrap": boot, **d, "guards": guards, "base_summary": b_summary, "cand_summary": c_summary}
            stages[name] = stage_detail
            final = d["decision"]
            
            if final != "PASS":
                break
        
        decision = "keep" if (final == "PASS" and reached == "audit") else ("reject" if final == "FAIL" else "insufficient_evidence")
        
        # Update trial with final result
        ledger.update_trial(led, tid, decision=decision, stage_reached=reached, promo_attempted=promo_done,
                           detail={"stages": stages, "bench_version_label": bench_version, "seed": seed, "n_boot": n_boot,
                                   "derived_bench_version": derived_bench_version})
        
        return {"trial_id": tid, "decision": decision, "stage_reached": reached, "stages": stages}
    
    except Exception as e:
        # On any exception, update trial to ABORTED with reason and re-raise
        error_detail = {"error": str(e), "stage_reached": reached, "bench_version_label": bench_version,
                        "seed": seed, "n_boot": n_boot, "derived_bench_version": derived_bench_version}
        ledger.update_trial(led, tid, decision=getattr(e, "decision", "ABORTED"), stage_reached=reached, detail=error_detail)
        raise


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
    except (Refused, PermissionError) as e:
        print(json.dumps({"refused": str(e)})); return 3
    except (ValueError, KeyError, OSError) as e:
        print(json.dumps({"error": str(e)})); return 2
    print(json.dumps(r, indent=1)); return 0


if __name__ == "__main__":
    sys.exit(main())
