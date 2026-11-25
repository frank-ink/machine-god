from contextlib import closing
import json

import pytest

import mg_loop
import mg_propose


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "trials"
    (root / "queue").mkdir(parents=True)
    (root / "done").mkdir()
    state = tmp_path / "state"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MG_STATE", str(state))
    monkeypatch.setattr(mg_propose, "ask", lambda _: pytest.fail("unexpected LLM call"))
    return root, state, tmp_path / "unified.db"


def reply(f):
    return json.dumps({"template": "rl2_frac", "params": {"f": f}, "hypothesis": "Try a fraction"})


def mock_ask(monkeypatch, *replies):
    remaining = iter(replies)
    prompts = []

    def ask(prompt):
        prompts.append(prompt)
        return next(remaining)

    monkeypatch.setattr(mg_propose, "ask", ask)
    return prompts


def run(workspace, capsys, *options):
    root, _, udb = workspace
    assert mg_propose.main(["--root", str(root), "--udb", str(udb), *options]) == 0
    return json.loads(capsys.readouterr().out)


def test_write_proposal(workspace, monkeypatch, capsys):
    root, _, udb = workspace
    (root / "done/0040-old.json").write_text("{}")
    (root / "done/MG-AUTO-0042.json").write_text('{"private":"done-only text"}')
    with closing(mg_loop.connect(udb)) as db, db:
        db.executemany(
            "INSERT INTO mg_trial (trial_id, hypothesis, decision, delta, ci_low, reason, ts) "
            "VALUES (?, ?, 'pass', 0.1, 0.05, 'private reason', ?)",
            [(f"trial-{i}", f"hypothesis-{i}", i) for i in range(21)],
        )
    prompts = mock_ask(monkeypatch, "Model reply:\n" + reply(0.12349))
    spec = run(workspace, capsys)
    assert spec == {
        "id": "MG-AUTO-0043",
        "hypothesis": 'Try a fraction [tpl:rl2_frac {"f": 0.123}]',
        "proposer": "free-pool",
        "target_metric": "dev MRR@5 + real-label AUC",
        "cmd": ["python3", "experiments/rl2_002_frac.py", "sweep", "0.123"],
        "result": "experiments/rl2_003_result.json",
        "timeout_s": 5400,
        "tpl_key": 'rl2_frac {"f": 0.123}',
    }
    assert json.loads((root / "queue/0043-auto-rl2_frac.json").read_text()) == spec
    assert len(prompts) == 1
    assert '["trial-20","hypothesis-20","pass",0.1,0.05,null,null,null]' in prompts[0]
    assert '"trial-0"' not in prompts[0]
    assert "private reason" not in prompts[0]
    assert "done-only text" not in prompts[0]


def test_out_of_range_retries(workspace, monkeypatch, capsys):
    prompts = mock_ask(monkeypatch, reply(0.5001), reply(0.5))
    assert run(workspace, capsys)["cmd"][-1] == "0.5"
    assert len(prompts) == 2


@pytest.mark.parametrize("source", ["ledger", "done"])
def test_duplicate_rejected(workspace, monkeypatch, capsys, source):
    root, _, udb = workspace
    key = 'rl2_frac {"f": 0.2}'
    if source == "ledger":
        with closing(mg_loop.connect(udb)) as db, db:
            db.execute("INSERT INTO mg_trial (trial_id, hypothesis) VALUES (?, ?)",
                       ("older", f"Old hypothesis [tpl:{key}]"))
            db.executemany("INSERT INTO mg_trial (trial_id, ts) VALUES (?, ?)",
                           [(f"later-{i}", i) for i in range(20)])
    else:
        (root / "done/MG-AUTO-0001.json").write_text(json.dumps({"tpl_key": key}))
    prompts = mock_ask(monkeypatch, *[reply(0.2001)] * 3)
    assert run(workspace, capsys) == {"skip": "duplicate proposal"}
    assert len(prompts) == 3
    assert list((root / "queue").iterdir()) == []


def test_nonempty_queue_skips(workspace, capsys):
    root, _, _ = workspace
    (root / "queue/0001-existing.json").write_text("{}")
    assert run(workspace, capsys) == {"skip": "queue not empty"}


def test_kill_skips(workspace, capsys):
    _, state, _ = workspace
    state.mkdir()
    (state / "KILL").touch()
    assert run(workspace, capsys) == {"skip": "KILL file exists"}


def test_garbage_retries_three_times(workspace, monkeypatch, capsys):
    prompts = mock_ask(monkeypatch, "garbage", "{broken", "still garbage")
    assert run(workspace, capsys) == {"skip": "no JSON object in reply"}
    assert len(prompts) == 3


def test_dry_only_prints(workspace, monkeypatch, capsys):
    root, state, udb = workspace
    mock_ask(monkeypatch, reply(0.0))
    assert run(workspace, capsys, "--dry")["id"] == "MG-AUTO-0001"
    assert list((root / "queue").iterdir()) == []
    assert not state.exists()
    assert not udb.exists()


@pytest.mark.parametrize(("template", "params", "argv", "result", "metric"), [
    ("rl2_hparam", {"rounds": 60.0, "minleaf": 20.0, "lr": 0.1},
     ["python3", "experiments/tpl_rl2_hparam.py", "dev", "60", "20", "0.1"],
     "experiments/tpl_rl2_hparam_dev.json", "RL2 held-out session Brier (real labels)"),
    ("recall_lane", {"minlen": 4.0, "and_terms": 6.0},
     ["python3", "experiments/tpl_recall_lane.py", "dev", "4", "6"],
     "experiments/tpl_recall_lane_dev.json", "udb lane MRR@5 known-item"),
])
def test_experiment_templates(workspace, monkeypatch, capsys, template, params, argv, result, metric):
    root, _, _ = workspace
    (root / "retired.json").write_text(json.dumps({"rl2_frac": "closed"}))
    prompts = mock_ask(monkeypatch, reply(0.1),
                       json.dumps({"template": template, "params": params, "hypothesis": "Try it"}))
    spec = run(workspace, capsys, "--dry")
    assert spec["cmd"] == argv
    assert spec["result"] == result
    assert spec["target_metric"] == metric
    assert spec["timeout_s"] == 1800
    assert len(prompts) == 2
    assert "rl2_frac" not in prompts[0].split("Allowed templates")[1]
    assert "rl2_frac" in mg_propose.TEMPLATES


@pytest.mark.parametrize(("template", "params", "key", "value"), [
    ("rl2_hparam", {"rounds": 60, "minleaf": 20, "lr": 0.1}, "rounds", 60.1),
    ("rl2_hparam", {"rounds": 60, "minleaf": 20, "lr": 0.1}, "minleaf", 20.1),
    ("recall_lane", {"minlen": 4, "and_terms": 6}, "minlen", 4.1),
    ("recall_lane", {"minlen": 4, "and_terms": 6}, "and_terms", 5.9),
])
def test_integer_parameters_reject_fractional_values(template, params, key, value):
    params[key] = value
    proposal = json.dumps({"template": template, "params": params, "hypothesis": "Try it"})
    with pytest.raises(ValueError, match=f"{key} must be an integer"):
        mg_propose.parse(proposal)
