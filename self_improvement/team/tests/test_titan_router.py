import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from team import titan_router as R

GOOD, NEW = "vendor/proven", "vendor/untried"


def _board(tmp_path, name, entries):
    d = tmp_path / "runs" / name
    d.mkdir(parents=True)
    (d / "board.jsonl").write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return str(d / "board.jsonl")


def _e(role, model, **kw):
    e = dict(role=role, model=model, parse_ok=True, repaired=False, salvaged=False, error="", latency_ms=20000)
    e.update(kw)
    return e


def test_reward_mapping():
    assert R.reward(_e("forscher", GOOD)) == 1.0
    assert R.reward(_e("forscher", GOOD, repaired=True)) == 0.5
    assert R.reward(_e("forscher", GOOD, repaired=True, salvaged=True)) == 0.25
    assert R.reward(_e("forscher", GOOD, parse_ok=False, error="chat: HTTP -1: TimeoutError")) == 0.0
    assert R.reward({"role": "runner"}) is None
    assert R.code_reward({"pytest_rc": 1, "oracle_rc": 0}) == 1.0
    assert R.code_reward({"pytest_rc": 0, "oracle_rc": 1}) == 0.25
    assert R.code_reward({"pytest_rc": 0, "oracle_rc": None}) == 1.0


def test_runner_reward_goes_to_last_bauer_model(tmp_path):
    p = _board(tmp_path, "a", [_e("bauer", "m/x"), {"role": "runner", "pytest_rc": 1, "oracle_rc": 0},
                               _e("pruefer", "m/y")])
    ev = R.evidence([p])
    assert ev[("bauer_code", "m/x")][0] == 1.0 and ("bauer_code", "m/y") not in ev


def test_parse_bench_formats():
    txt = ("nvidia/a   ok=True repaired=False ms=34645 lines=4 err=''\n"
           "z-ai/b     ERROR TimeoutError\n"
           "m/c        ok=False finish=stop ms=17194 out_tok=1 lines=0 err='empty'\n"
           "m/d        ok=False salvage_lines=3 ms=1000 out_tok=1 len=5 err='x'\n    \n")
    b = {x["model"]: x for x in R.parse_bench(txt)}
    assert b["nvidia/a"]["reward"] == 1.0 and b["nvidia/a"]["latency_ms"] == 34645
    assert b["z-ai/b"]["reward"] == 0.0 and b["z-ai/b"]["latency_ms"] == R.BENCH_TIMEOUT_MS
    assert b["m/c"]["reward"] == 0.0 and b["m/d"]["reward"] == 0.25


def _strong_ev(tmp_path):
    ents = []
    for _ in range(15):
        ents += [_e(r, GOOD) for r in R.ROLES] + [{"role": "runner", "pytest_rc": 0, "oracle_rc": 0}]
    return R.evidence([_board(tmp_path, "s", ents)])


def test_untried_model_never_wins_exploit_roles(tmp_path):
    ev = _strong_ev(tmp_path)
    for seed in range(20):
        pick, explore, _ = R.choose(ev, {GOOD: 0.5, NEW: 1.0}, seed=seed)
        assert all(pick[r] == GOOD for r in R.ROLES if r != explore and r != "pruefer")


def test_exactly_one_role_explores_and_seed_is_deterministic(tmp_path):
    ev = _strong_ev(tmp_path)
    a = R.choose(ev, {GOOD: 0.5, NEW: 0.5}, seed=7)
    assert a == R.choose(ev, {GOOD: 0.5, NEW: 0.5}, seed=7)
    assert a[1] in R.ROLES
    picks = {R.choose({}, {GOOD: 0.5, NEW: 0.5}, seed=s, explore_role="forscher")[0]["forscher"] for s in range(30)}
    assert picks == {GOOD, NEW}  # Thompson sampling does try both


def test_pruefer_takes_other_model_when_close():
    ev = {}
    pick, _, _ = R.choose(ev, {GOOD: 0.5, NEW: 0.5}, seed=1, explore_role="architekt")
    assert pick["pruefer"] != pick["bauer"]


def test_pruefer_keeps_bauer_model_when_alternative_is_bad(tmp_path):
    ents = []
    for _ in range(20):
        ents += [_e(r, GOOD) for r in R.ROLES] + [_e("pruefer", NEW, parse_ok=False)]
    ev = R.evidence([_board(tmp_path, "p", ents)])
    pick, _, _ = R.choose(ev, {GOOD: 0.5, NEW: 0.5}, seed=1, explore_role="architekt")
    assert pick["pruefer"] == pick["bauer"] == GOOD


def test_timeouts_push_a_model_down(tmp_path):
    bench = [{"model": NEW, "reward": 0.0, "latency_ms": R.BENCH_TIMEOUT_MS}] * 4
    ev = R.evidence([], bench)
    pick, _, table = R.choose(ev, {GOOD: 0.5, NEW: 0.5}, seed=3, explore_role="waechter")
    assert pick["architekt"] == GOOD
    row = [r for r in table["architekt"] if r["model"] == NEW][0]
    assert row["lat_s"] == 600.0


def test_served_filter_drops_non_chat():
    got = R.served_models("k", _get=lambda: {"data": [{"id": "nvidia/nemotron-3.5-embed-8b"}, {"id": "a/chat"},
                                                       {"id": "nvidia/llama-3.1-nemoguard-8b-topic-control"}]})
    assert got == ["a/chat"]


class FakePB:
    def __init__(self, block=()):
        self.block, self.reports = set(block), []

    def ranking(self, *a, **k):
        return [{"model": GOOD, "avail": 0.9}]

    def can_call(self, provider, model, kind):
        return {"allow": True, "would_allow": model not in self.block, "health": "healthy"}

    def report(self, *a, **k):
        self.reports.append((a, k))


def test_pool_gate_drops_blocked_and_fails_open():
    c, src = R.pool_gate([GOOD, NEW], factory=lambda: FakePB(block={NEW}))
    assert c == {GOOD: 0.9} and src == "poolbrain"

    def boom():
        raise ImportError("x")
    c, src = R.pool_gate([GOOD, NEW], factory=boom)
    assert c == {GOOD: 0.5, NEW: 0.5} and "unavailable" in src


def test_route_logs_decision_without_keys(tmp_path):
    _board(tmp_path, "r", [_e("bauer", GOOD)])
    log = str(tmp_path / "route.jsonl")
    pick, dec = R.route(str(tmp_path / "runs"), "nvapi-SECRET", seed=1, log_path=log, _served=[GOOD, NEW],
                        _pool=lambda m: ({x: 0.5 for x in m}, "test"))
    assert set(pick) == set(R.ROLES) and dec["n_boards"] == 1
    raw = open(log).read()
    assert "SECRET" not in raw and json.loads(raw)["pick"] == pick


def test_feedback_reports_to_pool(tmp_path):
    p = _board(tmp_path, "f", [_e("bauer", GOOD), {"role": "runner", "pytest_rc": 0},
                               _e("waechter", NEW, parse_ok=False, error="chat: HTTP -1: TimeoutError")])
    pb = FakePB()
    assert R.feedback(p, factory=lambda: pb) == 2
    oks = [(a[1], k["ok"], k["err_class"]) for a, k in pb.reports]
    assert oks == [(GOOD, True, ""), (NEW, False, "timeout")]


def test_two_bench_lines_do_not_beat_a_mediocre_proven_model(tmp_path):
    ents = [_e("architekt", GOOD, repaired=i % 2 == 0) for i in range(40)]   # proven, mean 0.75
    ev = R.evidence([_board(tmp_path, "m", ents)], [{"model": NEW, "reward": 1.0, "latency_ms": 20000}] * 2)
    pick, _, _ = R.choose(ev, {GOOD: 0.5, NEW: 0.5}, seed=0, explore_role="waechter")
    assert pick["architekt"] == GOOD


def test_role_mean_is_empirical():
    ev = {("bauer", "a"): [3.0, 1.0, []], ("bauer", "b"): [1.0, 3.0, []], ("*", "a"): [9.0, 0.0, []]}
    assert R.role_mean(ev, "bauer") == 0.5 and R.role_mean(ev, "pruefer") == 0.5


def test_extreme_priors_stay_valid():
    ev = {(r, GOOD): [50.0, 0.0, [1000]] for r in R.ROLES + ("bauer_code",)}
    pick, _, _ = R.choose(ev, {GOOD: 1.0, NEW: 0.0}, seed=0)
    assert set(pick) == set(R.ROLES)


def test_bench_only_model_cannot_take_exploit_seat_even_if_faster(tmp_path):
    ents = [_e("bauer", GOOD, repaired=True, latency_ms=90000) for _ in range(30)]
    ents += [{"role": "runner", "pytest_rc": 1, "oracle_rc": None}] * 5
    ev = R.evidence([_board(tmp_path, "n", ents)], [{"model": NEW, "reward": 1.0, "latency_ms": 10000}] * 4)
    pick, _, _ = R.choose(ev, {GOOD: 0.5, NEW: 0.5}, seed=0, explore_role="waechter")
    assert pick["bauer"] == GOOD


def test_fallbacks_from_decision_table():
    dec = {"pick": {"bauer": "m/a"}, "table": {"bauer": [{"model": "m/a"}, {"model": "m/b"}, {"model": "m/c"}, {"model": "m/d"}]}}
    assert R.fallbacks(dec) == {"bauer": ["m/b", "m/c"]}


def test_feedback_reports_skipped_fallback_models(tmp_path):
    p = tmp_path / "board.jsonl"
    p.write_text(json.dumps({"role": "bauer", "model": "m/b", "parse_ok": True, "fallback_from": ["m/a"],
                             "key_name": "K", "latency_ms": 5}) + "\n")
    got = []

    class PB:
        def report(self, prov, model, key, kind, ok, err_class, latency_ms, src):
            got.append((model, ok, err_class))
    assert R.feedback(str(p), factory=PB) == 2
    assert got == [("m/a", False, "chat_error"), ("m/b", True, "")]
