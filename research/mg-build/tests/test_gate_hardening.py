"""Hardening tests for mg.gate (pytest, no network)."""
import json
import math
import random
import tempfile
import os

import pytest

from mg import gate


def test_missing_cand_items_count_as_zero_and_fail():
    """Kandidat laesst die 20 schwersten Items weg und ist auf dem Rest nur minimal besser:
    ohne Null-Regel saehe das nach Gewinn aus, mit Null-Regel ist das Delta negativ -> FAIL."""
    base = {"i%d" % k: 0.5 for k in range(100)}
    cand = {"i%d" % k: 0.55 for k in range(80)}  # 20 fehlen
    t = gate.paired_bootstrap(base, cand, n=1000, seed=42)
    assert abs(t["delta"] - (80 * 0.05 - 20 * 0.5) / 100) < 1e-9 and t["delta"] < 0
    d = gate.decide(t, min_effect=0.0, min_n=50)
    assert d["decision"] != "PASS"
    assert t["n_missing"] == 20 and t["n_items"] == 100


def test_overlap_threshold():
    """21 of 100 missing -> ValueError; exactly 20 missing allowed."""
    base = {"i%d" % k: 0.5 for k in range(100)}
    # 21 missing -> 79 common -> 79/100 = 0.79 < 0.8 -> ValueError
    cand_21_missing = {"i%d" % k: 0.9 for k in range(79)}
    with pytest.raises(ValueError, match="overlap 79/100 below 80%"):
        gate.paired_bootstrap(base, cand_21_missing)
    
    # 20 missing -> 80 common -> 80/100 = 0.8 >= 0.8 -> OK
    cand_20_missing = {"i%d" % k: 0.9 for k in range(80)}
    t = gate.paired_bootstrap(base, cand_20_missing, n=100, seed=1)
    assert t["n_missing"] == 20
    assert t["n_items"] == 100


def test_empty_base_raises():
    """Empty base -> ValueError."""
    with pytest.raises(ValueError, match="base is empty"):
        gate.paired_bootstrap({}, {"a": 1.0})


def test_nan_in_cand_raises():
    """NaN in cand (among used scores) -> ValueError."""
    base = {"a": 0.5, "b": 0.5}
    cand = {"a": float("nan"), "b": 0.6}
    with pytest.raises(ValueError, match="non-finite score"):
        gate.paired_bootstrap(base, cand)


def test_duplicate_item_id_in_scores_file():
    """Duplicate item_id for the metric -> ValueError."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write('{"item_id": "a", "metric": "m", "score": 0.1}\n')
        f.write('{"item_id": "a", "metric": "m", "score": 0.2}\n')
        fname = f.name
    try:
        with pytest.raises(ValueError, match="duplicate item_id"):
            gate.load_scores(fname, "m")
    finally:
        os.unlink(fname)


def test_bad_json_line_raises():
    """Bad JSON line -> ValueError with line number."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write('{"item_id": "a", "metric": "m", "score": 0.1}\n')
        f.write('not valid json\n')
        fname = f.name
    try:
        with pytest.raises(ValueError, match="line 2: invalid JSON"):
            gate.load_scores(fname, "m")
    finally:
        os.unlink(fname)


def test_missing_item_id_or_score_raises():
    """Line lacks item_id or score -> ValueError with line number."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write('{"metric": "m", "score": 0.1}\n')  # missing item_id
        fname = f.name
    try:
        with pytest.raises(ValueError, match="line 1: missing item_id or score"):
            gate.load_scores(fname, "m")
    finally:
        os.unlink(fname)


def test_main_returns_2_for_errors():
    """main returns 2 for missing file, bad guards json, guard without base."""
    # Missing base file
    assert gate.main(["--base", "/nonexistent", "--cand", "/dev/null", "--metric", "m"]) == 2
    
    # Bad guards JSON
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as bf, \
         tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as cf, \
         tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as gf:
        bf.write('{"item_id": "a", "metric": "m", "score": 0.5}\n')
        cf.write('{"item_id": "a", "metric": "m", "score": 0.6}\n')
        gf.write('not valid json')
        bname, cname, gname = bf.name, cf.name, gf.name
    try:
        assert gate.main(["--base", bname, "--cand", cname, "--metric", "m", "--guards", gname]) == 2
    finally:
        os.unlink(bname)
        os.unlink(cname)
        os.unlink(gname)
    
    # Guard without base
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as bf, \
         tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as cf, \
         tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as gf:
        bf.write('{"item_id": "a", "metric": "m", "score": 0.5}\n')
        cf.write('{"item_id": "a", "metric": "m", "score": 0.6}\n')
        gf.write('[{"name": "g1", "cand": 0.5}]')  # missing "base"
        bname, cname, gname = bf.name, cf.name, gf.name
    try:
        assert gate.main(["--base", bname, "--cand", cname, "--metric", "m", "--guards", gname]) == 2
    finally:
        os.unlink(bname)
        os.unlink(cname)
        os.unlink(gname)


def test_decide_boundaries():
    """decide boundaries with hand-made target dicts."""
    # delta == min_effect with ci_low > 0 -> PASS
    t = {"delta": 0.1, "ci_low": 0.05, "ci_high": 0.15, "n_items": 100}
    assert gate.decide(t, min_effect=0.1, min_n=50)["decision"] == "PASS"
    
    # delta just below min_effect with ci_low > 0 -> not PASS (FAIL because ci_high <= min_effect? No, ci_high=0.15 > 0.1)
    # Wait: delta=0.09, min_effect=0.1, ci_low=0.05, ci_high=0.15
    # ci_low > 0 but delta < min_effect -> not PASS
    # ci_high (0.15) > max(min_effect, 0) = 0.1 -> not FAIL by that rule
    # So INSUFFICIENT_EVIDENCE
    t2 = {"delta": 0.09, "ci_low": 0.05, "ci_high": 0.15, "n_items": 100}
    assert gate.decide(t2, min_effect=0.1, min_n=50)["decision"] == "INSUFFICIENT_EVIDENCE"
    
    # n_items == min_n is NOT insufficient, min_n-1 is
    t3 = {"delta": 0.2, "ci_low": 0.1, "ci_high": 0.3, "n_items": 50}
    assert gate.decide(t3, min_effect=0.1, min_n=50)["decision"] == "PASS"
    t4 = {"delta": 0.2, "ci_low": 0.1, "ci_high": 0.3, "n_items": 49}
    assert gate.decide(t4, min_effect=0.1, min_n=50)["decision"] == "INSUFFICIENT_EVIDENCE"
    
    # Soft guard at exact tolerance passes, slightly beyond fails
    t5 = {"delta": 0.2, "ci_low": 0.1, "ci_high": 0.3, "n_items": 50}
    guards_pass = [{"name": "g", "base": 0.5, "cand": 0.45, "kind": "soft", "tol": 0.05, "direction": "higher"}]
    # higher direction: ok if cand >= base - tol -> 0.45 >= 0.5 - 0.05 = 0.45 -> ok (equal passes)
    assert gate.decide(t5, guards_pass)["decision"] == "PASS"
    
    guards_fail = [{"name": "g", "base": 0.5, "cand": 0.44, "kind": "soft", "tol": 0.05, "direction": "higher"}]
    # 0.44 >= 0.45? No -> fail
    assert gate.decide(t5, guards_fail)["decision"] == "FAIL"
    
    # Hard guard equal passes
    guards_hard = [{"name": "g", "base": 0.5, "cand": 0.5, "kind": "hard", "direction": "higher"}]
    assert gate.decide(t5, guards_hard)["decision"] == "PASS"


def test_percentile_indices():
    """Percentile: recompute expected ci_low/ci_high independently with random.Random(seed) and same index formulas."""
    # Small example: base = [0, 1, 2], cand = [1, 2, 3] -> d = [1, 1, 1]
    # All differences are 1, so all bootstrap means = 1, CI = [1, 1]
    base = {"a": 0.0, "b": 1.0, "c": 2.0}
    cand = {"a": 1.0, "b": 2.0, "c": 3.0}
    n = 100
    seed = 123
    t = gate.paired_bootstrap(base, cand, n=n, seed=seed)
    assert t["delta"] == 1.0
    assert t["ci_low"] == 1.0
    assert t["ci_high"] == 1.0
    
    # Now with varying differences, manually compute
    base2 = {"a": 0.0, "b": 1.0, "c": 2.0}
    cand2 = {"a": 0.5, "b": 1.5, "c": 2.5}  # d = [0.5, 0.5, 0.5] -> all same
    t2 = gate.paired_bootstrap(base2, cand2, n=n, seed=seed)
    assert t2["delta"] == 0.5
    assert t2["ci_low"] == 0.5
    assert t2["ci_high"] == 0.5
    
    # With actual variation: d = [0, 1, 2]
    base3 = {"a": 0.0, "b": 0.0, "c": 0.0}
    cand3 = {"a": 0.0, "b": 1.0, "c": 2.0}
    n2 = 1000
    seed2 = 456
    t3 = gate.paired_bootstrap(base3, cand3, n=n2, seed=seed2)
    
    # Independent computation
    d = [0.0, 1.0, 2.0]
    m = len(d)
    rnd = random.Random(seed2)
    means = sorted(sum(rnd.choices(d, k=m)) / m for _ in range(n2))
    lo_idx = int(0.025 * (n2 - 1))
    hi_idx = int(round(0.975 * (n2 - 1)))
    expected_lo = means[lo_idx]
    expected_hi = means[hi_idx]
    
    assert t3["ci_low"] == expected_lo
    assert t3["ci_high"] == expected_hi
    assert t3["delta"] == 1.0  # mean of [0,1,2]
    assert t3["n_items"] == 3
    assert t3["n_missing"] == 0


def test_n_missing_reported():
    """n_missing reported in bootstrap result."""
    base = {"a": 1.0, "b": 2.0, "c": 3.0, "d": 1.0, "e": 2.0}
    cand = {"a": 1.5, "b": 2.5, "c": 3.5, "d": 1.5}  # e fehlt (4/5 = 0.8, erlaubt)
    t = gate.paired_bootstrap(base, cand, n=100, seed=1)
    assert t["n_missing"] == 1
    assert t["n_items"] == 5
    assert abs(t["delta"] - ((0.5 + 0.5 + 0.5 + 0.5) - 2.0) / 5) < 1e-10


def test_items_only_in_cand_ignored():
    """Items only in cand are ignored."""
    base = {"a": 1.0, "b": 2.0}
    cand = {"a": 1.5, "b": 2.5, "c": 100.0}  # c only in cand
    t = gate.paired_bootstrap(base, cand, n=100, seed=1)
    assert t["n_items"] == 2
    assert t["n_missing"] == 0
    # delta = ((1.5-1) + (2.5-2)) / 2 = 0.5
    assert abs(t["delta"] - 0.5) < 1e-10


def test_guard_without_base_or_cand_raises_valueerror():
    """_guard_ok: guard dict without 'base' or 'cand' -> ValueError."""
    with pytest.raises(ValueError, match="guard missing 'base' or 'cand'"):
        gate._guard_ok({"name": "g", "cand": 0.5})
    with pytest.raises(ValueError, match="guard missing 'base' or 'cand'"):
        gate._guard_ok({"name": "g", "base": 0.5})
    with pytest.raises(ValueError, match="guard missing 'base' or 'cand'"):
        gate._guard_ok({"name": "g"})


def test_non_finite_in_base_raises():
    """Non-finite in base -> ValueError."""
    base = {"a": float("inf"), "b": 0.5}
    cand = {"a": 0.6, "b": 0.6}
    with pytest.raises(ValueError, match="non-finite score"):
        gate.paired_bootstrap(base, cand)


def test_load_scores_skips_other_metrics():
    """load_scores only loads the requested metric."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write('{"item_id": "a", "metric": "m1", "score": 0.1}\n')
        f.write('{"item_id": "b", "metric": "m2", "score": 0.2}\n')
        f.write('{"item_id": "c", "metric": "m1", "score": 0.3}\n')
        fname = f.name
    try:
        scores = gate.load_scores(fname, "m1")
        assert scores == {"a": 0.1, "c": 0.3}
    finally:
        os.unlink(fname)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_n_zero_and_guards_not_a_list():
    import pytest, json as _j
    with pytest.raises(ValueError):
        gate.paired_bootstrap({"a": 1.0}, {"a": 1.0}, n=0)
    import tempfile, os
    d = tempfile.mkdtemp()
    f = os.path.join(d, "s.jsonl"); open(f, "w").write(_j.dumps({"item_id": "a", "metric": "m", "score": 1.0}) + "\n")
    g = os.path.join(d, "g.json"); open(g, "w").write('{"x": 1}')
    assert gate.main(["--base", f, "--cand", f, "--metric", "m", "--guards", g, "--n", "50"]) == 2


def test_percentile_indices_exact_independent():
    import random
    base = {"i%d" % k: 0.0 for k in range(40)}
    cand = {"i%d" % k: random.Random(k).random() for k in range(40)}
    for n in (1000, 41, 2):
        t = gate.paired_bootstrap(base, cand, n=n, seed=9)
        d = [cand["i%d" % k] - base["i%d" % k] for k in range(40)]
        r = random.Random(9)
        means = sorted(sum(r.choices(d, k=40)) / 40 for _ in range(n))
        assert t["ci_low"] == means[int(0.025 * (n - 1))]
        assert t["ci_high"] == means[int(round(0.975 * (n - 1)))]
