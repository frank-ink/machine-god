"""Run one queued Machine God trial at a time."""
import argparse
from contextlib import closing, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time


FORBIDDEN = (
    ".claude/hooks", "frank_vault", ".last-resort", "keys.env", "binance",
    "CLAUDE.md", "mg_loop.py", "mgfixed/mg/gate.py", "rm -rf",
)
COMMANDS = ("cmd", "adopt", "rollback", "remeasure")
SCHEMA = """CREATE TABLE IF NOT EXISTS mg_trial (
    trial_id TEXT PRIMARY KEY, hypothesis TEXT, patch_sha256 TEXT, proposer TEXT,
    base_ref TEXT, target_metric TEXT, delta REAL, ci_low REAL, ci_high REAL,
    guards_json TEXT, decision TEXT, reason TEXT, ts REAL
)"""

def connect(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    with db:
        db.execute(SCHEMA)
    return db

def available_kib():
    with open("/proc/meminfo") as meminfo:
        for line in meminfo:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1])
    raise OSError("MemAvailable missing from /proc/meminfo")

def read_result(path, result):
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object")
    result.update(data)
    if type(result.get("PASS")) is not bool:
        raise ValueError(f"{path}: expected boolean PASS")
    return result["PASS"]

def execute_trial(spec, root, result_path, result):
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    timeout = spec.get("timeout_s", 7200)
    with (logs / f"{spec['id']}.log").open("wb") as log:
        def run(command):
            subprocess.run(
                spec[command], cwd=root.parent, stdout=log,
                stderr=subprocess.STDOUT, timeout=timeout, check=True,
            )

        try:
            run("cmd")
            if not read_result(result_path, result):
                return "reject", "PASS is false"
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            return "error", str(exc)

        if not spec.get("adopt"):
            return "pass", ""

        try:
            run("adopt")
            if spec.get("remeasure") and not read_result(
                root.parent / spec["remeasure_result"], {}
            ):
                raise ValueError("remeasure PASS is false")
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            reason = str(exc)
            if spec.get("rollback"):
                try:
                    run("rollback")
                except (OSError, ValueError, subprocess.SubprocessError) as rollback_exc:
                    reason += f" | rollback failed: {rollback_exc}"
            else:
                reason += " | no rollback configured"
            return "reverted", reason
        return "adopted", ""


def record_lehre(spec, decision, result_path):
    if os.environ.get("MG_NO_LEHRE") == "1" or not result_path.is_file():
        return
    try:
        digest = hashlib.sha256(result_path.read_bytes()).hexdigest()
        subprocess.run(
            [
                "python3", str(Path.home() / ".claude/star/stern.py"), "lehre",
                "--aussage", f"MG trial {spec['id']}: {spec['hypothesis']} rejected ({decision})",
                "--gilt-fuer", "machine-god", "--beleg", f"datei:{result_path}:{digest}",
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def finish(source, root, spec, decision):
    done = root / "done"
    done.mkdir(exist_ok=True)
    destination = done / f"{spec['id']}.json"
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps({**spec, "decision": decision}) + "\n")
    temporary.replace(destination)
    source.unlink()


def record_trial(db, spec, digest, decision, reason, result, base_ref="spec"):
    pooled = result.get("pooled")
    metrics = pooled if isinstance(pooled, dict) else result
    with db:
        db.execute(
            "INSERT INTO mg_trial VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                spec["id"], spec.get("hypothesis", ""), digest, spec.get("proposer"), base_ref,
                spec.get("target_metric"), metrics.get("delta"), metrics.get("ci_low"),
                metrics.get("ci_high"), json.dumps(result)[:4000], decision, reason, time.time(),
            ),
        )


def process(source, root, db, dry):
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    spec = json.loads(raw)
    trial_id = spec["id"]
    if not isinstance(trial_id, str) or trial_id in ("", ".", "..") or "/" in trial_id:
        raise ValueError("trial id must be a single filename component")
    argv = [arg for key in COMMANDS for arg in (spec.get(key) or [])]
    frozen_text = [raw.decode("utf-8-sig"), json.dumps(spec, ensure_ascii=False), *argv]
    forbidden = next((word for word in FORBIDDEN if any(word in s for s in frozen_text)), None)
    reason = f"forbidden substring: {forbidden}" if forbidden else ""
    if dry:
        return {"trial_id": trial_id, "decision": "refused" if forbidden else "dry",
                "reason": reason, "dry": True}

    existing = db.execute(
        "SELECT patch_sha256, decision, reason FROM mg_trial WHERE trial_id = ?", (trial_id,)
    ).fetchone()
    if existing:
        if existing["patch_sha256"] != digest:
            return {"trial_id": trial_id, "decision": "skip", "reason": "duplicate trial id"}
        finish(source, root, spec, existing["decision"])
        return {"trial_id": trial_id, "decision": existing["decision"], "reason": existing["reason"]}

    result = {}
    if forbidden:
        decision = "refused"
    else:
        result_path = root.parent / spec["result"]
        decision, reason = execute_trial(spec, root, result_path, result)
    record_trial(db, spec, digest, decision, reason, result)
    if decision in ("reject", "error", "reverted"):
        record_lehre(spec, decision, result_path)
    if decision == "pass" and spec.get("audit") and not spec.get("is_audit"):   # dev pass earns ONE audit look (DESIGN 18c)
        audit = {**spec, "id": f"{trial_id}-AUDIT", "cmd": spec["audit"]["cmd"], "result": spec["audit"]["result"],
                 "is_audit": True, "hypothesis": f"audit look for {trial_id}: {spec.get('hypothesis', '')}"}
        audit.pop("audit")
        (root / "queue" / f"{source.stem}-audit.json").write_text(json.dumps(audit) + "\n")
    finish(source, root, spec, decision)
    return {"trial_id": trial_id, "decision": decision, "reason": reason}


def skipped(reason):
    return {"decision": "skip", "reason": reason}


@contextmanager
def loop_lock(state):
    state.mkdir(parents=True, exist_ok=True)
    with (state / "loop.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
        else:
            yield True


def killed(state):
    return (state / "KILL").exists()


def tick(root, udb, state, dry):
    if killed(state):
        return skipped("KILL file exists")
    if os.getloadavg()[0] > float(os.getenv("MG_MAX_LOAD", "14")):
        return skipped("load above MG_MAX_LOAD")
    if available_kib() < 3 * 1024 * 1024:
        return skipped("MemAvailable below 3 GiB")
    with loop_lock(state) as acquired:
        if not acquired:
            return skipped("loop lock held")
        with closing(connect(udb)) as db:
            reverted = db.execute(
                "SELECT count(*) FROM mg_trial WHERE decision = 'reverted' AND ts >= ?",
                (time.time() - 7 * 24 * 3600,),
            ).fetchone()[0]
            if reverted >= 3:
                return skipped("self-stop: 3 reverts in 7 days")
            source = min((root / "queue").glob("*.json"), default=None)
            return process(source, root, db, dry) if source else skipped("queue empty")


def status(udb):
    with closing(connect(udb)) as db:
        counts = dict(db.execute("SELECT decision, count(*) FROM mg_trial GROUP BY decision"))
        latest = db.execute("SELECT * FROM mg_trial ORDER BY ts DESC, trial_id LIMIT 5")
        return {"counts": counts, "last_5": [dict(row) for row in latest]}


def main(argv=None):
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    tick_parser = commands.add_parser("tick")
    status_parser = commands.add_parser("status")
    home = Path.home()
    for command in (tick_parser, status_parser):
        command.add_argument("--udb", type=Path, default=home / ".local/share/agentzero/unified.db")
    tick_parser.add_argument("--root", type=Path, default=home / "repos/github_all/machine-god/trials")
    tick_parser.add_argument("--dry", action="store_true")
    args = parser.parse_args(argv)
    udb = args.udb.expanduser()
    if args.command == "tick":
        state = Path(os.getenv("MG_STATE", str(home / ".local/share/machine-god"))).expanduser()
        summary = tick(args.root.expanduser().resolve(), udb, state, args.dry)
    else:
        summary = status(udb)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
