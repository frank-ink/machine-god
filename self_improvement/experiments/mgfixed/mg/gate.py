"""MG-1: Decision statistics for the Machine God improvement loop."""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from typing import Any


GATE_CONTRACT_VERSION = "v2"


def paired_bootstrap(
    base: dict[str, float],
    cand: dict[str, float],
    n: int = 10000,
    seed: int = 0,
) -> dict[str, Any]:
    """
    Paired bootstrap over items present in both base and candidate.

    Args:
        base: dict mapping item_id -> score
        cand: dict mapping item_id -> score
        n: number of bootstrap resamples (default 10000)
        seed: random seed for reproducibility (default 0)

    Returns:
        dict with keys: delta (mean difference), ci_low (2.5th percentile),
        ci_high (97.5th percentile), n_items (number of overlapping items)

    Raises:
        ValueError: if overlap is below 80% of the smaller input
    """
    common_keys = sorted(set(base.keys()) & set(cand.keys()))  # sorted: set order depends on PYTHONHASHSEED
    n_common = len(common_keys)
    n_base = len(base)
    n_cand = len(cand)
    max_n = max(n_base, n_cand)

    if max_n == 0:
        raise ValueError("One or both inputs are empty")

    if n_common / max_n < 0.8:
        raise ValueError(
            f"Overlap {n_common}/{max_n} = {n_common / max_n:.1%} below 80%"
        )

    deltas = [cand[k] - base[k] for k in common_keys]
    mean_delta = statistics.mean(deltas)

    rng = random.Random(seed)
    bootstrap_means = []
    for _ in range(n):
        sample = [rng.choice(deltas) for _ in range(n_common)]
        bootstrap_means.append(statistics.mean(sample))

    bootstrap_means.sort()
    ci_low = bootstrap_means[int(0.025 * n)]
    ci_high = bootstrap_means[int(0.975 * n)]

    return {
        "delta": mean_delta,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "n_items": n_common,
    }


def decide(
    target: dict[str, Any],
    guards: list[dict[str, Any]],
    min_effect: float = 0.0,
    min_n: int = 1,
) -> dict[str, Any]:
    """
    Decide whether to keep a candidate based on bootstrap results and guards.

    Args:
        target: result from paired_bootstrap with keys delta, ci_low, ci_high, n_items
        guards: list of guard dicts with keys:
            - name: str
            - base: float (baseline value)
            - cand: float (candidate value)
            - kind: "hard" or "soft"
            - tol: float (tolerance for soft guards)
            - direction: "higher" or "lower" (default "higher"; "lower" for cost/latency)
        min_effect: minimum meaningful effect size (preregistered)
        min_n: minimum required sample size (preregistered)

    Returns:
        dict with keys: decision (PASS|FAIL|INSUFFICIENT_EVIDENCE|BLOCKED), reasons (list of str)
    """
    reasons = []

    # Check minimum sample size
    if target["n_items"] < min_n:
        reasons.append(f"n_items={target['n_items']} below min_n={min_n}")
        return {"decision": "INSUFFICIENT_EVIDENCE", "reasons": reasons}

    # Check confidence interval
    ci_low = target["ci_low"]
    ci_high = target["ci_high"]
    delta = target["delta"]

    if ci_low > 0 and delta >= min_effect:
        pass  # Clear improvement
    elif ci_high <= 0 or delta <= -min_effect:
        reasons.append(f"CI [{ci_low:.6f}, {ci_high:.6f}] does not show improvement >= {min_effect}")
        return {"decision": "FAIL", "reasons": reasons}
    else:
        # CI straddles 0 but contains min_effect
        if ci_low <= 0 <= ci_high and ci_high >= min_effect:
            reasons.append(
                f"CI [{ci_low:.6f}, {ci_high:.6f}] straddles 0 but contains min_effect={min_effect}"
            )
            return {"decision": "INSUFFICIENT_EVIDENCE", "reasons": reasons}
        reasons.append(f"CI [{ci_low:.6f}, {ci_high:.6f}] inconclusive")
        return {"decision": "INSUFFICIENT_EVIDENCE", "reasons": reasons}

    # Check hard guards
    for guard in guards:
        if guard.get("kind") != "hard":
            continue
        base_val = guard["base"]
        cand_val = guard["cand"]
        direction = guard.get("direction", "higher")
        name = guard.get("name", "unnamed")

        if direction == "higher":
            if cand_val < base_val:
                reasons.append(f"Hard guard '{name}' failed: {cand_val} < {base_val}")
                return {"decision": "FAIL", "reasons": reasons}
        elif direction == "lower":
            if cand_val > base_val:
                reasons.append(f"Hard guard '{name}' failed: {cand_val} > {base_val}")
                return {"decision": "FAIL", "reasons": reasons}

    # Check soft guards
    for guard in guards:
        if guard.get("kind") != "soft":
            continue
        base_val = guard["base"]
        cand_val = guard["cand"]
        tol = guard.get("tol", 0.0)
        direction = guard.get("direction", "higher")
        name = guard.get("name", "unnamed")

        if direction == "higher":
            if cand_val < base_val - tol:
                reasons.append(
                    f"Soft guard '{name}' exceeded tolerance: {cand_val} < {base_val} - {tol}"
                )
                return {"decision": "FAIL", "reasons": reasons}
        elif direction == "lower":
            if cand_val > base_val + tol:
                reasons.append(
                    f"Soft guard '{name}' exceeded tolerance: {cand_val} > {base_val} + {tol}"
                )
                return {"decision": "FAIL", "reasons": reasons}

    return {"decision": "PASS", "reasons": reasons}


def decide_v2(
    target: dict[str, Any],
    guards: list[dict[str, Any]],
    min_effect: float = 0.0,
    min_n: int = 1,
) -> dict[str, Any]:
    """
    Decide v2: simplified contract with explicit guard format.

    Args:
        target: result from paired_bootstrap with keys delta, ci_low, ci_high, n_items
        guards: list of guard dicts with keys:
            - name: str
            - passed: bool
            - hard: bool (default True)
        min_effect: minimum meaningful effect size (preregistered)
        min_n: minimum required sample size (preregistered)

    Returns:
        dict with keys: decision (PASS|FAIL|FAIL_GUARD|INSUFFICIENT_EVIDENCE),
                       reasons (list of str), contract (str), min_effect (float),
                       ci_low (float), ci_high (float)
    """
    reasons = []

    # Check minimum sample size
    if target["n_items"] < min_n:
        reasons.append(f"n_items={target['n_items']} below min_n={min_n}")
        return {
            "decision": "INSUFFICIENT_EVIDENCE",
            "reasons": reasons,
            "contract": "v2",
            "min_effect": min_effect,
            "ci_low": target["ci_low"],
            "ci_high": target["ci_high"],
        }

    ci_low = target["ci_low"]
    ci_high = target["ci_high"]

    # Check hard guards
    failed_hard_guards = []
    soft_guard_failures = []
    for guard in guards:
        name = guard.get("name", "unnamed")
        passed = guard.get("passed", False)
        hard = guard.get("hard", True)

        if not passed:
            if hard:
                failed_hard_guards.append(name)
            else:
                soft_guard_failures.append(name)

    if failed_hard_guards:
        reasons.append(f"Hard guards failed: {', '.join(failed_hard_guards)}")
        return {
            "decision": "FAIL_GUARD",
            "reasons": reasons,
            "contract": "v2",
            "min_effect": min_effect,
            "ci_low": ci_low,
            "ci_high": ci_high,
        }

    for name in soft_guard_failures:
        reasons.append(f"Soft guard '{name}' failed")

    # Decision based on CI and min_effect
    if ci_low >= min_effect:
        decision = "PASS"
    elif ci_high < min_effect:
        decision = "FAIL"
        reasons.append(f"CI [{ci_low:.6f}, {ci_high:.6f}] entirely below min_effect={min_effect}")
    else:
        decision = "INSUFFICIENT_EVIDENCE"
        reasons.append(f"CI [{ci_low:.6f}, {ci_high:.6f}] straddles min_effect={min_effect}")

    return {
        "decision": decision,
        "reasons": reasons,
        "contract": "v2",
        "min_effect": min_effect,
        "ci_low": ci_low,
        "ci_high": ci_high,
    }


def _load_jsonl(path: str, metric: str) -> dict[str, float]:
    """Load JSONL file and extract scores for the given metric."""
    result = {}
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("metric") == metric:
                item_id = obj["item_id"]
                score = obj["score"]
                result[item_id] = score
    return result


def _load_guards(path: str) -> list[dict[str, Any]]:
    """Load guards from JSON file."""
    with open(path, "r") as f:
        return json.load(f)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MG-1 Gate: paired bootstrap decision")
    parser.add_argument("--base", required=True, help="Baseline JSONL file")
    parser.add_argument("--cand", required=True, help="Candidate JSONL file")
    parser.add_argument("--metric", required=True, help="Metric name to evaluate")
    parser.add_argument("--guards", help="Guards JSON file")
    parser.add_argument("--n", type=int, default=10000, help="Bootstrap resamples")
    parser.add_argument("--seed", type=int, default=0, help="Random seed")
    parser.add_argument("--min-effect", type=float, default=0.0, help="Minimum meaningful effect")
    parser.add_argument("--min-n", type=int, default=1, help="Minimum sample size")
    parser.add_argument("--contract", choices=["v1", "v2"], default="v1", help="Contract version (default: v1)")
    args = parser.parse_args(argv)

    base = _load_jsonl(args.base, args.metric)
    cand = _load_jsonl(args.cand, args.metric)

    if not base or not cand:
        print("ERROR: No data for metric", file=sys.stderr)
        return 1

    try:
        bootstrap_result = paired_bootstrap(base, cand, n=args.n, seed=args.seed)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    guards = _load_guards(args.guards) if args.guards else []

    if args.contract == "v2":
        # Convert v1 guard format to v2 format
        v2_guards = []
        for g in guards:
            v2_guards.append({
                "name": g.get("name", "unnamed"),
                "passed": _guard_passed(g),
                "hard": g.get("kind") == "hard",
            })
        decision_result = decide_v2(
            bootstrap_result,
            v2_guards,
            min_effect=args.min_effect,
            min_n=args.min_n,
        )
    else:
        decision_result = decide(
            bootstrap_result,
            guards,
            min_effect=args.min_effect,
            min_n=args.min_n,
        )

    output = {
        "bootstrap": bootstrap_result,
        "decision": decision_result,
    }
    print(json.dumps(output, indent=2))
    return 0


def _guard_passed(guard: dict[str, Any]) -> bool:
    """Check if a v1 guard passes."""
    base_val = guard["base"]
    cand_val = guard["cand"]
    direction = guard.get("direction", "higher")

    if direction == "higher":
        if guard.get("kind") == "soft":
            tol = guard.get("tol", 0.0)
            return cand_val >= base_val - tol
        return cand_val >= base_val
    else:  # direction == "lower"
        if guard.get("kind") == "soft":
            tol = guard.get("tol", 0.0)
            return cand_val <= base_val + tol
        return cand_val <= base_val


if __name__ == "__main__":
    sys.exit(main())