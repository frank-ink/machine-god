"""Run M3 tasks and summarize task success and M8 calibration."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
from statistics import mean
import subprocess
import time
from uuid import uuid4


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ARMS = {"on": "with memory/organs", "off": "without memory/organs"}
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
FLOAT = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


def data_dir():
    return Path.home() / ".local/share/machine-god/m3"


def cache_dir():
    return Path.home() / ".cache/machine-god/m3"


def read_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def load_tasks():
    sources = {"code": HERE / "tasks_code.jsonl", "memory": data_dir() / "tasks_memory.jsonl"}
    seen = set()
    for kind, path in sources.items():
        if kind == "memory" and not path.exists():
            continue
        for task in read_jsonl(path):
            task_id = task["id"]
            if not IDENTIFIER.fullmatch(task_id) or task_id in seen:
                raise ValueError(f"Invalid or duplicate task ID: {task_id!r}")
            seen.add(task_id)
            for name in task["seed"]:
                if not name or Path(name).name != name or name in {".", "..", "check.py"}:
                    raise ValueError(f"Invalid seed filename in task {task_id}")
            yield dict(task, kind=kind)


def probability(prompt, arm, directory):
    ask = os.environ.get("M3_ASK", str(Path.home() / ".config/frank_vault/ask.sh"))
    question = (
        f"Estimate the probability that frank-agent will pass this task when run "
        f"{ARMS[arm]}. Answer only a number between 0 and 1.\n\n{prompt}"
    )
    try:
        result = subprocess.run(
            ["bash", ask, question], cwd=directory, timeout=120,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, text=True, errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0.5, False
    match = FLOAT.search(result.stdout)
    if result.returncode == 0 and match:
        value = float(match.group())
        if 0 <= value <= 1:
            return value, True
    return 0.5, False


def run_command(command, directory, timeout, env=None):
    try:
        return subprocess.run(
            command, cwd=directory, env=env, timeout=timeout,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode
    except subprocess.TimeoutExpired:
        return 124
    except OSError:
        return 127


def run_pair(run_id, task, arm):
    base = cache_dir() / run_id
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = base / f"{task['id']}-{arm}"
    if directory.exists():
        # Keep the interrupted attempt for inspection and retry from clean seed files.
        directory.rename(base / f".interrupted-{uuid4().hex}")
    directory.mkdir(mode=0o700)
    for name, content in task["seed"].items():
        (directory / name).write_text(content, encoding="utf-8")

    p, parse_ok = probability(task["prompt"], arm, directory)
    env = os.environ.copy()
    if arm == "off":
        env["FRANK_AGENT_ORGANS"] = "0"
    started = time.monotonic()
    agent_rc = run_command(
        [env.get("M3_AGENT", "frank-agent"), "-C", str(directory), task["prompt"]],
        directory, timeout=600, env=env,
    )
    wall_s = time.monotonic() - started

    # Stage the trusted checker only after the agent exits.
    checker = directory / "check.py"
    if checker.is_dir() and not checker.is_symlink():
        checker.rename(directory / f".agent-check-{uuid4().hex}")
    else:
        checker.unlink(missing_ok=True)
    try:
        checker.touch(mode=0o600, exist_ok=False)
        checker.write_text(task["check"], encoding="utf-8")
        check_env = os.environ.copy()
        check_env.pop("PYTHONOPTIMIZE", None)
        passed = run_command(["python3", "check.py"], directory, timeout=60, env=check_env) == 0
    finally:
        checker.unlink(missing_ok=True)
    return {
        "task_id": task["id"], "kind": task["kind"], "arm": arm,
        "p": p, "parse_ok": parse_ok, "passed": passed, "wall_s": wall_s,
        "agent_rc": agent_rc,
    }


def run(run_id, limit, workers):
    tasks = list(load_tasks())[:limit]
    target = data_dir() / f"{run_id}.jsonl"
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with os.fdopen(os.open(target, os.O_CREAT | os.O_APPEND | os.O_RDWR, 0o600),
                   "a+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        completed = set()
        while True:
            offset = stream.tell()
            line = stream.readline()
            if not line:
                break
            if not line.endswith(b"\n"):
                # An interrupted append does not mark this pair as complete.
                stream.truncate(offset)
                break
            row = json.loads(line)
            completed.add((row["task_id"], row["arm"]))
        jobs = [(task, arm) for task in tasks for arm in ARMS
                if (task["id"], arm) not in completed]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(run_pair, run_id, task, arm) for task, arm in jobs]
            for future in as_completed(futures):
                stream.write((json.dumps(future.result()) + "\n").encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())


def metrics(rows):
    return {
        "n": len(rows),
        "pass_rate": mean(row["passed"] for row in rows) if rows else None,
        "brier_score": mean((row["p"] - row["passed"]) ** 2 for row in rows) if rows else None,
        "mean_wall_s": mean(row["wall_s"] for row in rows) if rows else None,
    }


def summarize(run_id):
    rows = read_jsonl(data_dir() / f"{run_id}.jsonl")
    arms = {arm: [row for row in rows if row["arm"] == arm] for arm in ARMS}
    scores = {arm: {row["task_id"]: int(row["passed"]) for row in group}
              for arm, group in arms.items()}
    paired_ids = scores["off"].keys() & scores["on"].keys()
    delta = None
    if paired_ids:
        gate_path = REPO / "experiments/mgfixed/mg/gate.py"
        spec = importlib.util.spec_from_file_location("m3_gate", gate_path)
        gate = importlib.util.module_from_spec(spec)
        # Load without creating bytecode under experiments/.
        exec(compile(gate_path.read_bytes(), str(gate_path), "exec"), gate.__dict__)
        delta = gate.paired_bootstrap(
            {task_id: scores["off"][task_id] for task_id in paired_ids},
            {task_id: scores["on"][task_id] for task_id in paired_ids},
            n=10000, seed=0,
        )
    summary = {
        "by_arm": {arm: metrics(group) for arm, group in arms.items()},
        "by_kind": {
            kind: {arm: metrics([row for row in group if row["kind"] == kind])
                   for arm, group in arms.items()}
            for kind in ("code", "memory")
        },
        "real_task_memory_delta": delta,
    }
    output = REPO / "experiments" / f"m3_{run_id}.json"
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--run-id", help="Resume an existing run ID")
    run_parser.add_argument("--limit", type=int)
    run_parser.add_argument("--workers", type=int, default=3)
    summary_parser = commands.add_parser("summary")
    summary_parser.add_argument("run_id")
    args = parser.parse_args()
    run_id = args.run_id
    if run_id is None:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    if not IDENTIFIER.fullmatch(run_id):
        parser.error("invalid run ID")
    if args.command == "run":
        if args.workers < 1 or (args.limit is not None and args.limit < 1):
            parser.error("--workers and --limit must be positive")
        print(run_id, flush=True)
        run(run_id, args.limit, args.workers)
    else:
        print(summarize(run_id))


if __name__ == "__main__":
    main()
