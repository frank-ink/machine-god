from contextlib import closing
import json
import sqlite3
import sys

import pytest

import mg_loop
import mg_watch


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "trials"
    (root / "watch").mkdir(parents=True)
    monkeypatch.setattr(mg_watch.time, "time", lambda: 1000)
    monkeypatch.setenv("MG_NO_LEHRE", "1")
    return root, tmp_path / "unified.db", tmp_path / "state"


def python(code):
    return [sys.executable, "-c", code]


def spec_file(root, trial_id, value, **overrides):
    result = f"{trial_id}-result.json"
    payload = json.dumps({"PASS": value})
    spec = dict(
        id=trial_id, due_ts=1000, result=result,
        check_cmd=python(f"from pathlib import Path; Path({result!r}).write_text({payload!r})"),
        rollback_cmd=python("from pathlib import Path; Path('rolled-back').touch()"),
    )
    path = root / "watch" / f"{trial_id}.json"
    path.write_text(json.dumps({**spec, **overrides}))
    return path


def test_confirm_and_revert_preserve_adoption(workspace, monkeypatch):
    root, udb, _ = workspace
    spec_file(root, "pass", True)
    spec_file(root, "fail", False)
    later = spec_file(root, "later", False, due_ts=1001)
    with closing(mg_loop.connect(udb)) as db:
        mg_loop.record_trial(db, {"id": "fail"}, "original", "adopted", "", {})
    lessons = []
    monkeypatch.setattr(mg_watch, "record_lehre", lambda spec, decision, path: lessons.append(
        (spec["id"], decision, path)))
    outcomes = mg_watch.tick(*workspace)["outcomes"]
    assert [result["decision"] for result in outcomes] == ["reverted", "confirmed"]
    assert later.exists()
    assert not (root.parent / "later-result.json").exists()
    assert (root.parent / "rolled-back").exists()
    assert lessons == [("fail", "reverted", root.parent / "fail-result.json")]
    assert json.loads((root / "watch/done/pass.json").read_text())["decision"] == "confirmed"
    with closing(sqlite3.connect(udb)) as db:
        assert dict(db.execute("SELECT trial_id, decision FROM mg_trial")) == {
            "fail": "adopted", "fail-WATCH": "reverted", "pass-WATCH": "confirmed",
        }


def test_pending_seven_pushes_then_expires(workspace, monkeypatch):
    root, _, _ = workspace
    source = spec_file(root, "pending", "pending")
    for i in range(8):
        due = 1000 + i * mg_watch.DAY
        monkeypatch.setattr(mg_watch.time, "time", lambda: due)
        decision = mg_watch.tick(*workspace)["outcomes"][0]["decision"]
        if i < 7:
            assert decision == "pending"
            updated = json.loads(source.read_text())
            assert updated["due_ts"] == due + mg_watch.DAY
            assert updated["pushes"] == i + 1
        else:
            assert decision == "expired"
    assert not source.exists()
    assert (root / "watch/done/pending.json").exists()
    assert not (root.parent / "rolled-back").exists()


def test_shares_loop_lock_and_kill(workspace):
    root, udb, state = workspace
    spec_file(root, "pass", True)
    with mg_loop.loop_lock(state) as acquired:
        assert acquired
        assert mg_watch.tick(*workspace)["reason"] == "loop lock held"
    (state / "KILL").touch()
    assert mg_watch.tick(*workspace)["reason"] == "KILL file exists"
    assert not udb.exists()


def test_failed_rollback_retries_without_rechecking(workspace):
    root, udb, _ = workspace
    source = spec_file(root, "retry", False, rollback_cmd=python(
        "from pathlib import Path; assert Path('ready').exists()"))
    assert mg_watch.tick(*workspace)["outcomes"][0]["decision"] == "error"
    with closing(sqlite3.connect(udb)) as db:
        assert db.execute("SELECT count(*) FROM mg_trial").fetchone()[0] == 0
    (root.parent / "ready").touch()
    result = root.parent / "retry-result.json"
    result.write_text('{"PASS": true}')
    assert mg_watch.tick(*workspace)["outcomes"][0]["decision"] == "reverted"
    assert not source.exists()
    assert json.loads(result.read_text())["PASS"] is True


def test_completed_rollback_is_not_repeated_on_ledger_retry(workspace, monkeypatch):
    root, _, _ = workspace
    source = spec_file(root, "retry", False, rollback_cmd=python(
        "with open('rollbacks', 'a') as log: log.write('once')"))

    def unavailable(*args, **kwargs):
        raise sqlite3.OperationalError("ledger unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(mg_watch, "record_trial", unavailable)
        with pytest.raises(sqlite3.OperationalError, match="ledger unavailable"):
            mg_watch.tick(*workspace)

    assert source.exists()
    assert mg_watch.tick(*workspace)["outcomes"][0]["decision"] == "reverted"
    assert (root.parent / "rollbacks").read_text() == "once"
