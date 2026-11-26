import datetime
import json
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys

import pytest


M3 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(M3))
import m3_run
import make_memory_tasks

CODE_TASKS = m3_run.read_jsonl(M3 / "tasks_code.jsonl")


def check_task(task, directory):
    return subprocess.run(
        [sys.executable, "check.py"], cwd=directory, capture_output=True, timeout=10,
    )


@pytest.mark.parametrize("task", CODE_TASKS, ids=lambda task: task["id"])
def test_code_checker(task, tmp_path):
    (tmp_path / "check.py").write_text(task["check"], encoding="utf-8")
    assert check_task(task, tmp_path).returncode != 0
    for filename, content in task["seed"].items():
        (tmp_path / filename).write_text(content, encoding="utf-8")
    assert check_task(task, tmp_path).returncode != 0
    filename = task["prompt"].split("create or update ", 1)[1].split(". ", 1)[0]
    shutil.copyfile(M3 / "tests/solutions" / filename, tmp_path / filename)
    result = check_task(task, tmp_path)
    assert result.returncode == 0, result.stderr.decode()


def test_memory_task_generation(tmp_path):
    database = tmp_path / "unified.db"
    now = datetime.datetime(2026, 11, 26, tzinfo=datetime.timezone.utc)
    cutoff = (now - datetime.timedelta(days=2)).timestamp()
    rows = []
    for number in range(30):
        token = f"0.{6194 + number}" if number % 2 else f"dead{number:04x}"
        rows.append((str(number), "tat", f"Action {number} ({token}) | result {token} | logged",
                     "merke.py", cutoff - 1))
    rows += [
        ("recent", "tat", "Recent | 0.6194 | log", "merke.py", cutoff),
        ("foreign", "tat", "Foreign | 0.6194 | log", "another", cutoff - 1),
        ("other", "fact", "Other | 0.6194 | log", "merke.py", cutoff - 1),
        ("multi", "tat", "Ambiguous | deadbeef | cafebabe", "merke.py", cutoff - 1),
        ("long", "tat", "Long | 0123456789abcdef1 | log", "merke.py", cutoff - 1),
        ("text", "tat", "Plain | complete | log", "merke.py", cutoff - 1),
    ]
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE durable_memory (memory_id, kind, value, provenance, ts)")
        connection.executemany("INSERT INTO durable_memory VALUES (?,?,?,?,?)", rows)
    before = database.read_bytes()
    tasks = make_memory_tasks.build_tasks(database, now)
    assert database.read_bytes() == before
    assert len(tasks) == 15
    assert len({task["id"] for task in tasks}) == 15
    assert tasks == make_memory_tasks.build_tasks(database, now)
    assert tasks != make_memory_tasks.build_tasks(database, now + datetime.timedelta(days=7))

    output = tmp_path / "private" / "tasks_memory.jsonl"
    make_memory_tasks.write_tasks(tasks, output)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert m3_run.read_jsonl(output) == tasks

    for task in tasks:
        description = task["prompt"].split("\n\n")[1]
        assert description.startswith("Action ")
        number = int(description.split()[1])
        token = f"0.{6194 + number}" if number % 2 else f"dead{number:04x}"
        assert token not in task["prompt"]
        (tmp_path / "check.py").write_text(task["check"], encoding="utf-8")
        answer = tmp_path / "answer.txt"
        answer.write_text(token + "\n", encoding="utf-8")
        assert check_task(task, tmp_path).returncode != 0
        answer.write_text(token, encoding="utf-8")
        assert check_task(task, tmp_path).returncode == 0


def test_run_resume_and_summary(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("FRANK_AGENT_ORGANS", raising=False)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    monkeypatch.setenv("PATH", str(fake_bin) + ":" + m3_run.os.environ["PATH"])
    monkeypatch.setenv("M3_AGENT", "fake-agent")
    monkeypatch.setenv("M3_ASK", "fake-ask")
    agent = fake_bin / "fake-agent"
    agent.write_text(
        '#!/bin/bash\n'
        'set -eu\n'
        '[[ "$1" == "-C" && "$2" == "$PWD" && "$3" == "Create answer.txt" ]]\n'
        '[[ -f asked && ! -e check.py && ! -e stale ]]\n'
        'printf "%s" "${FRANK_AGENT_ORGANS-on}" > arm\n'
        'if [[ "${FRANK_AGENT_ORGANS-on}" == "0" ]]; then exit 9; fi\n'
        'cp seed.txt answer.txt\n',
        encoding="utf-8",
    )
    agent.chmod(0o700)
    (fake_bin / "fake-ask").write_text(
        'set -eu\n'
        '[[ "$1" == *"Create answer.txt"* && "$1" == *"between 0 and 1"* ]]\n'
        '[[ -f seed.txt && ! -e check.py && ! -e asked ]]\n'
        'touch asked\n'
        'if [[ "$1" == *"without memory/organs"* ]]; then echo unknown;\n'
        'elif [[ "$1" == *"with memory/organs"* ]]; then echo ".75 estimated";\n'
        'else exit 1; fi\n',
        encoding="utf-8",
    )
    suite = tmp_path / "suite"
    suite.mkdir()
    monkeypatch.setattr(m3_run, "HERE", suite)
    code = {
        "id": "synthetic-code",
        "prompt": "Create answer.txt",
        "seed": {"seed.txt": "secret-fixture"},
        "check": 'from pathlib import Path\nassert Path("answer.txt").read_text() == "secret-fixture"\n',
    }
    (suite / "tasks_code.jsonl").write_text(json.dumps(code) + "\n", encoding="utf-8")
    memory = dict(code, id="synthetic-memory")
    make_memory_tasks.write_tasks([memory], m3_run.data_dir() / "tasks_memory.jsonl")
    interrupted = m3_run.cache_dir() / "trial" / "synthetic-code-off"
    interrupted.mkdir(parents=True)
    (interrupted / "stale").touch()

    m3_run.run("trial", limit=1, workers=2)
    log = m3_run.data_dir() / "trial.jsonl"
    finished = log.read_bytes()
    assert len(finished.splitlines()) == 2
    with log.open("ab") as stream:
        stream.write(b'{"task_id":')
    m3_run.run("trial", limit=None, workers=3)
    assert log.read_bytes().startswith(finished)
    rows = m3_run.read_jsonl(log)
    assert len(rows) == 4
    for row in rows:
        on = row["arm"] == "on"
        assert row["p"] == (0.75 if on else 0.5)
        assert row["parse_ok"] is on
        assert row["passed"] is on
        assert row["agent_rc"] == (0 if on else 9)
        assert row["wall_s"] >= 0
        directory = m3_run.cache_dir() / "trial" / f"{row['task_id']}-{row['arm']}"
        assert (directory / "arm").read_text() == ("on" if on else "0")
        assert not (directory / "check.py").exists()
    assert not (interrupted / "stale").exists()
    full_log = log.read_bytes()
    m3_run.run("trial", limit=None, workers=3)
    assert log.read_bytes() == full_log

    repo = tmp_path / "repo"
    gate_path = repo / "experiments/mgfixed/mg/gate.py"
    gate_path.parent.mkdir(parents=True)
    shutil.copyfile(m3_run.REPO / "experiments/mgfixed/mg/gate.py", gate_path)
    monkeypatch.setattr(m3_run, "REPO", repo)
    summary_path = m3_run.summarize("trial")
    summary_text = summary_path.read_text()
    for private in ("secret-fixture", "synthetic-code", "synthetic-memory", "Create answer.txt"):
        assert private not in summary_text
    summary = json.loads(summary_text)
    assert summary["by_arm"]["on"]["pass_rate"] == 1
    assert summary["by_arm"]["off"]["pass_rate"] == 0
    assert summary["by_arm"]["on"]["brier_score"] == 0.0625
    assert summary["by_arm"]["off"]["brier_score"] == 0.25
    assert summary["by_kind"]["code"]["off"]["pass_rate"] == 0
    assert summary["by_kind"]["memory"]["on"]["pass_rate"] == 1
    assert summary["real_task_memory_delta"] == dict(delta=1, ci_low=1, ci_high=1, n_items=2)


def test_code_suite_shape():
    assert len(CODE_TASKS) == 15
    assert len({task["id"] for task in CODE_TASKS}) == 15
    for task in CODE_TASKS:
        assert task.keys() == {"id", "prompt", "seed", "check"}
