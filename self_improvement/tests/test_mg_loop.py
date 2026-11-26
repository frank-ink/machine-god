import hashlib
import json
import sqlite3
import sys
import time

import pytest

import mg_loop


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "trials"
    (root / "queue").mkdir(parents=True)
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("MG_STATE", str(state))
    monkeypatch.setenv("MG_NO_LEHRE", "1")
    monkeypatch.setenv("MG_MAX_LOAD", "14")
    monkeypatch.setattr(mg_loop.os, "getloadavg", lambda: (0, 0, 0))
    monkeypatch.setattr(mg_loop, "available_kib", lambda: 4 * 1024 * 1024)
    return root, state, tmp_path / "unified.db"


def python(code):
    return [sys.executable, "-c", code]


def write_result(path, data):
    return python(f"from pathlib import Path; Path({path!r}).write_text({json.dumps(data)!r})")


def enqueue(workspace, passed=True, **overrides):
    root, _, _ = workspace
    spec = {
        "id": "trial-1", "hypothesis": "A change helps", "proposer": "pytest",
        "target_metric": "recall", "result": "result.json", "timeout_s": 5,
        "cmd": write_result("result.json", {"PASS": passed, "pooled": {
            "delta": 0.2, "ci_low": 0.1, "ci_high": 0.3,
        }}),
        **overrides,
    }
    source = root / "queue" / "001.json"
    source.write_text(json.dumps(spec))
    return source


def tick(workspace, capsys, *options):
    root, _, udb = workspace
    assert mg_loop.main(["tick", "--root", str(root), "--udb", str(udb), *options]) == 0
    return json.loads(capsys.readouterr().out)


def completed(workspace, capsys, decision):
    assert tick(workspace, capsys)["decision"] == decision
    root, _, udb = workspace
    assert list((root / "queue").iterdir()) == []
    assert json.loads((root / "done/trial-1.json").read_text())["decision"] == decision
    assert mg_loop.main(["status", "--udb", str(udb)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["counts"] == {decision: 1}
    assert status["last_5"][0]["decision"] == decision
    return status["last_5"][0]


def test_pass_without_adopt(workspace, capsys):
    source = enqueue(workspace)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    row = completed(workspace, capsys, "pass")
    assert row["patch_sha256"] == digest
    assert row["base_ref"] == "spec"
    assert (row["delta"], row["ci_low"], row["ci_high"]) == (0.2, 0.1, 0.3)
    assert json.loads(row["guards_json"])["PASS"] is True
    assert (workspace[0] / "logs/trial-1.log").is_file()


def test_reject(workspace, capsys):
    enqueue(workspace, passed=False)
    row = completed(workspace, capsys, "reject")
    assert json.loads(row["guards_json"])["PASS"] is False


def test_refuse_forbidden_path(workspace, capsys):
    enqueue(workspace, rollback=["echo", ".claude/hooks/example"])
    row = completed(workspace, capsys, "refused")
    assert ".claude/hooks" in row["reason"]
    assert not (workspace[0].parent / "result.json").exists()


def test_remeasure_failure_rolls_back(workspace, capsys):
    enqueue(
        workspace,
        adopt=python("from pathlib import Path; Path('adopted').touch()"),
        remeasure=write_result("remeasure.json", {"PASS": False}),
        remeasure_result="remeasure.json",
        rollback=python("from pathlib import Path; Path('adopted').unlink(); Path('rolled_back').touch()"),
    )
    completed(workspace, capsys, "reverted")
    directory = workspace[0].parent
    assert (directory / "rolled_back").exists()
    assert not (directory / "adopted").exists()


def test_kill_skips(workspace, capsys):
    source = enqueue(workspace)
    (workspace[1] / "KILL").touch()
    assert tick(workspace, capsys) == {"decision": "skip", "reason": "KILL file exists"}
    assert source.exists()
    assert not workspace[2].exists()


def test_self_stop(workspace, capsys):
    source = enqueue(workspace)
    with sqlite3.connect(workspace[2]) as db:
        db.execute(mg_loop.SCHEMA)
        db.executemany(
            "INSERT INTO mg_trial (trial_id, decision, ts) VALUES (?, 'reverted', ?)",
            [(str(i), time.time()) for i in range(3)],
        )
    summary = tick(workspace, capsys)
    assert summary["decision"] == "skip"
    assert "self-stop" in summary["reason"]
    assert source.exists()


def test_timeout(workspace, capsys):
    enqueue(workspace, cmd=python("import time; time.sleep(10)"), timeout_s=0.1)
    row = completed(workspace, capsys, "error")
    assert "timed out" in row["reason"]


def test_dry_keeps_trial_queued(workspace, capsys):
    source = enqueue(workspace)
    assert tick(workspace, capsys, "--dry")["decision"] == "dry"
    assert source.exists()
    assert not (workspace[0].parent / "result.json").exists()
    with sqlite3.connect(workspace[2]) as db:
        assert db.execute("SELECT count(*) FROM mg_trial").fetchone()[0] == 0


def test_dev_pass_enqueues_one_audit(tmp_path, monkeypatch):
    import json, sys, subprocess
    monkeypatch.setenv("MG_NO_LEHRE", "1"); monkeypatch.setenv("MG_STATE", str(tmp_path / "state"))
    root = tmp_path / "trials"; (root / "queue").mkdir(parents=True)
    monkeypatch.setattr(mg_loop.os, "getloadavg", lambda: (0, 0, 0))                 # host load must not decide a unit test
    monkeypatch.setattr(mg_loop, "available_kib", lambda: 4 * 1024 * 1024)
    res = tmp_path / "r.json"
    cmd = [sys.executable, "-c", f"open({str(res)!r},'w').write('{{\"PASS\": true}}')"]
    spec = {"id": "T1", "hypothesis": "h", "proposer": "p", "target_metric": "m", "cmd": cmd, "result": str(res),
            "audit": {"cmd": cmd, "result": str(res)}}
    (root / "queue" / "0001-t.json").write_text(json.dumps(spec))
    run = lambda: subprocess.run([sys.executable, "mg_loop.py", "tick", "--root", str(root), "--udb", str(tmp_path / "u.db")],
                                 cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent), capture_output=True, text=True)
    run()
    q = list((root / "queue").glob("*.json"))
    assert [p.name for p in q] == ["0001-t-audit.json"] and json.loads(q[0].read_text())["is_audit"] is True
    run()
    assert list((root / "queue").glob("*.json")) == []
