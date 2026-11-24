import json

import pytest

from mg import gate


def items(f, n=40):
    return {"i%d" % k: f(k) for k in range(n)}


def test_identical_inputs_ci_around_zero_and_reject():
    b = items(lambda k: (k % 7) / 7)
    t = gate.paired_bootstrap(b, dict(b), n=500)
    assert t["delta"] == 0 and t["ci_low"] == 0 and t["ci_high"] == 0 and t["n_items"] == 40
    d = gate.decide(t)
    assert d["decision"] == "FAIL"


def test_clear_improvement_passes():
    b = items(lambda k: 0.2 + (k % 5) * 0.01)
    c = {i: v + 0.3 for i, v in b.items()}
    t = gate.paired_bootstrap(b, c, n=500)
    assert t["ci_low"] > 0.25 and gate.decide(t, min_effect=0.1, min_n=30)["decision"] == "PASS"


def test_hard_guard_failure_fails():
    b = items(lambda k: 0.2); c = {i: 0.6 for i in b}
    t = gate.paired_bootstrap(b, c, n=300)
    d = gate.decide(t, [{"name": "hit5", "base": 0.9, "cand": 0.8, "kind": "hard"}])
    assert d["decision"] == "FAIL" and "hit5" in d["reasons"][0]


def test_soft_guard_within_tol_and_cost_direction():
    b = items(lambda k: 0.2); c = {i: 0.6 for i in b}
    t = gate.paired_bootstrap(b, c, n=300)
    ok = [{"name": "hit5", "base": 0.9, "cand": 0.88, "kind": "soft", "tol": 0.05},
          {"name": "ms", "base": 10, "cand": 9, "kind": "hard", "direction": "lower"}]
    assert gate.decide(t, ok)["decision"] == "PASS"
    assert gate.decide(t, [{"name": "ms", "base": 10, "cand": 12, "kind": "hard", "direction": "lower"}])["decision"] == "FAIL"
    assert gate.decide(t, [{"name": "hit5", "base": 0.9, "cand": 0.8, "kind": "soft", "tol": 0.05}])["decision"] == "FAIL"


def test_overlap_below_80_percent_raises():
    b = items(lambda k: 0.1, 10); c = {"i%d" % k: 0.5 for k in range(7)}  # 7/10 overlap
    with pytest.raises(ValueError):
        gate.paired_bootstrap(b, c)
    gate.paired_bootstrap(b, {**c, "i7": 0.5, "i8": 0.5}, n=50)  # 9/10 ok


def test_insufficient_evidence_n_and_inconclusive_ci():
    b = items(lambda k: 0.2, 5); c = {i: 0.9 for i in b}
    assert gate.decide(gate.paired_bootstrap(b, c, n=100), min_n=30)["decision"] == "INSUFFICIENT_EVIDENCE"
    b2 = items(lambda k: 0.5, 20); c2 = {i: 0.5 + (0.4 if k % 2 else -0.4) for k, i in enumerate(b2)}
    t = gate.paired_bootstrap(b2, c2, n=500)
    assert t["ci_low"] < 0 < t["ci_high"] and gate.decide(t)["decision"] == "INSUFFICIENT_EVIDENCE"


def test_min_effect_blocks_small_gain():
    b = items(lambda k: 0.5, 40); c = {i: 0.52 for i in b}
    t = gate.paired_bootstrap(b, c, n=300)
    assert t["ci_low"] > 0 and gate.decide(t, min_effect=0.1)["decision"] == "FAIL"


def test_deterministic_for_fixed_seed():
    b = items(lambda k: (k * 37 % 11) / 11); c = items(lambda k: (k * 53 % 13) / 13)
    assert gate.paired_bootstrap(b, c, n=400, seed=7) == gate.paired_bootstrap(b, c, n=400, seed=7)
    assert gate.paired_bootstrap(b, c, n=400, seed=7) != gate.paired_bootstrap(b, c, n=400, seed=8)


def test_cli(tmp_path, capsys):
    bf, cf = tmp_path / "b.jsonl", tmp_path / "c.jsonl"
    bf.write_text("".join(json.dumps({"item_id": "i%d" % k, "metric": "mrr", "score": 0.2}) + "\n" for k in range(30)))
    cf.write_text("".join(json.dumps({"item_id": "i%d" % k, "metric": "mrr", "score": 0.7}) + "\n" for k in range(30)))
    assert gate.main(["--base", str(bf), "--cand", str(cf), "--metric", "mrr", "--n", "200", "--min-n", "20"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "PASS" and out["bootstrap"]["n_items"] == 30
