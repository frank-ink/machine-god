"""Check due adoptions and roll back failed live measurements."""
import argparse
from contextlib import closing
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

from mg_loop import FORBIDDEN, connect, finish, killed, loop_lock, record_lehre, record_trial, skipped


DAY = 24 * 3600
WATCH_SUFFIX = "-WATCH"


def save(source, spec):
    temporary = source.with_suffix(".tmp")
    temporary.write_text(json.dumps(spec) + "\n")
    temporary.replace(source)


def process(source, root, db, now):
    raw = source.read_bytes()
    spec = json.loads(raw)
    trial_id = spec["id"]
    if not isinstance(trial_id, str) or trial_id in ("", ".", "..") or "/" in trial_id:
        raise ValueError("watch id must be a single filename component")
    due = spec["due_ts"]
    if type(due) not in (int, float) or not math.isfinite(due):
        raise ValueError("due_ts must be a Unix timestamp")
    if due > now:
        return None

    ledger_id = trial_id + WATCH_SUFFIX
    existing = db.execute(
        "SELECT decision, reason, base_ref FROM mg_trial WHERE trial_id = ?",
        (ledger_id,),
    ).fetchone()
    if existing:
        decision, reason, base_ref = existing
        if base_ref != "watch":
            raise ValueError(f"watch ledger id is already in use: {ledger_id}")
    else:
        for key in ("check_cmd", "rollback_cmd"):
            command = spec[key]
            if not isinstance(command, list) or not command or not all(isinstance(arg, str) for arg in command):
                raise ValueError(f"{key} must be a nonempty argv list")
        frozen = [str(spec["result"]), *spec["check_cmd"], *spec["rollback_cmd"]]
        forbidden = next((word for word in FORBIDDEN if any(word in item for item in frozen)), None)
        if forbidden:
            raise ValueError(f"forbidden substring: {forbidden}")
        timeout = spec.get("timeout_s", 7200)
        result_path = root.parent / spec["result"]
        result = spec.get("rollback_result")
        if result is None:
            subprocess.run(spec["check_cmd"], cwd=root.parent, timeout=timeout, check=True)
            result = json.loads(result_path.read_text())

        passed = result.get("PASS") if isinstance(result, dict) else None
        reason = ""
        if passed is True:
            decision = "confirmed"
        elif passed == "pending":
            pushes = spec.get("pushes", 0)
            if pushes < 7:
                save(source, {**spec, "due_ts": due + DAY, "pushes": pushes + 1})
                return {"trial_id": trial_id, "decision": "pending"}
            decision, reason = "expired", "PASS still pending after 7 pushes"
        elif passed is False:
            if "rollback_result" not in spec:
                spec["rollback_result"] = result
                save(source, spec)
            if not spec.get("rollback_completed"):
                subprocess.run(spec["rollback_cmd"], cwd=root.parent, timeout=timeout, check=True)
                spec["rollback_completed"] = True
                save(source, spec)
            decision, reason = "reverted", "PASS is false"
        else:
            raise ValueError(f"{result_path}: expected PASS true, false, or pending")

        entry = {**spec, "id": ledger_id, "hypothesis": spec.get("hypothesis", f"Live adoption check for {trial_id}")}
        record_trial(db, entry, hashlib.sha256(raw).hexdigest(), decision, reason, result, base_ref="watch")
        if decision == "reverted":
            record_lehre({**entry, "id": trial_id}, decision, result_path)

    archived = {key: value for key, value in spec.items()
                if key not in ("rollback_result", "rollback_completed")}
    finish(source, root / "watch", archived, decision)
    return {"trial_id": trial_id, "decision": decision, "reason": reason}


def tick(root, udb, state):
    if killed(state):
        return skipped("KILL file exists")
    with loop_lock(state) as acquired:
        if not acquired:
            return skipped("loop lock held")
        if killed(state):
            return skipped("KILL file exists")
        sources = sorted((root / "watch").glob("*.json"))
        if not sources:
            return skipped("watch empty")
        outcomes = []
        now = time.time()
        with closing(connect(udb)) as db:
            for source in sources:
                if killed(state):
                    break
                try:
                    outcome = process(source, root, db, now)
                except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
                    outcome = {"spec": source.name, "decision": "error", "reason": str(exc)}
                if outcome is not None:
                    outcomes.append(outcome)
        return {"outcomes": outcomes}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    home = Path.home()
    tick_parser = parser.add_subparsers(dest="command", required=True).add_parser("tick")
    tick_parser.add_argument("--root", type=Path, default=home / "repos/github_all/machine-god/trials")
    tick_parser.add_argument("--udb", type=Path, default=home / ".local/share/agentzero/unified.db")
    args = parser.parse_args(argv)
    state = Path(os.getenv("MG_STATE", str(home / ".local/share/machine-god"))).expanduser()
    summary = tick(args.root.expanduser().resolve(), args.udb.expanduser(), state)
    print(json.dumps(summary))
    return int(any(item["decision"] == "error" for item in summary.get("outcomes", [])))


if __name__ == "__main__":
    raise SystemExit(main())
