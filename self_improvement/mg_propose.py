"""Propose one allowlisted Machine God trial through the free pool."""
import argparse
from contextlib import closing
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
from tempfile import NamedTemporaryFile

TEMPLATES = {
    "rl2_frac": {
        "argv": ["python3", "experiments/rl2_002_frac.py", "sweep", "{f}"],
        "params": {"f": (0.0, 0.5)},
        "result": "experiments/rl2_003_result.json",
        "timeout_s": 5400,
        "metric": "dev MRR@5 + real-label AUC",
    },
    "rl2_hparam": {
        "argv": ["python3", "experiments/tpl_rl2_hparam.py", "dev", "{rounds}", "{minleaf}", "{lr}"],
        "params": {"rounds": (20, 300), "minleaf": (5, 80), "lr": (0.03, 0.3)},
        "result": "experiments/tpl_rl2_hparam_dev.json",
        "timeout_s": 1800,
        "metric": "RL2 held-out session Brier (real labels)",
    },
    "recall_lane": {
        "argv": ["python3", "experiments/tpl_recall_lane.py", "dev", "{minlen}", "{and_terms}"],
        "params": {"minlen": (3, 6), "and_terms": (2, 6)},
        "result": "experiments/tpl_recall_lane_dev.json",
        "timeout_s": 1800,
        "metric": "udb lane MRR@5 known-item",
    },
}

INTEGER_PARAMS = {"rounds", "minleaf", "minlen", "and_terms"}

def ask(prompt):
    last = None
    for mode in (["-s"], []):            # strong model first; on pool timeout/error fall back to the plain free chain
        try:
            return subprocess.run(
                ["bash", os.path.expanduser("~/.config/frank_vault/ask.sh"), *mode, prompt],
                timeout=120, capture_output=True, text=True, check=True,
            ).stdout
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
            last = exc
    raise last

def ledger(path, query, params=()):
    if not path.exists():
        return []
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name = 'mg_trial'").fetchone():
            return []
        return db.execute(query, params).fetchall()

def parse(reply, templates=TEMPLATES):
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", reply):
        try:
            proposal, _ = decoder.raw_decode(reply, match.start())
        except json.JSONDecodeError:
            continue
        break
    else:
        raise ValueError("no JSON object in reply")
    name = proposal.get("template")
    if not isinstance(name, str) or name not in templates:
        raise ValueError("unknown template")
    template = templates[name]
    params, hypothesis = proposal.get("params"), proposal.get("hypothesis")
    if not isinstance(params, dict) or params.keys() != template["params"].keys():
        raise ValueError("incorrect parameter keys")
    for key, (low, high) in template["params"].items():
        value = params[key]
        if type(value) not in (int, float) or not low <= value <= high:
            raise ValueError(f"invalid parameter: {key}")
        if key in INTEGER_PARAMS:
            if round(value) != value:
                raise ValueError(f"invalid parameter: {key} must be an integer")
            params[key] = round(value)
        else:
            params[key] = round(float(value), 3) or 0.0
    if not isinstance(hypothesis, str) or len(hypothesis) > 200:
        raise ValueError("invalid hypothesis")
    return name, template, params, hypothesis


def build(root, udb, proposal):
    name, template, params, hypothesis = proposal
    key = f"{name} {json.dumps(params, sort_keys=True)}"
    marker = f"[tpl:{key}]"
    if ledger(udb, "SELECT 1 FROM mg_trial WHERE instr(hypothesis, ?) > 0 LIMIT 1", (marker,)):
        raise ValueError("duplicate proposal")
    for path in (root / "done").glob("*.json"):
        completed = json.loads(path.read_text())
        if isinstance(completed, dict) and completed.get("tpl_key") == key:
            raise ValueError("duplicate proposal")
    numbers = (
        int(match[1]) for directory in ("queue", "done")
        for path in (root / directory).glob("*.json")
        if (match := re.match(r"^(?:MG-AUTO-)?([0-9]+)(?:-|\.json$)", path.name))
    )
    number = f"{max(numbers, default=0) + 1:04d}"
    return f"{number}-auto-{name}.json", {
        "id": f"MG-AUTO-{number}", "hypothesis": f"{hypothesis} {marker}",
        "proposer": "free-pool", "target_metric": template["metric"],
        "cmd": [arg.format(**params) for arg in template["argv"]],
        "result": template["result"], "timeout_s": template["timeout_s"], "tpl_key": key,
        **({"audit": {"cmd": [("audit" if a == "dev" else a.format(**params)) for a in template["argv"]],
                      "result": template["result"].replace("_dev.json", "_audit.json")}}
           if "dev" in template["argv"] else {}),
    }


def skip_reason(queue, state):
    if any(queue.glob("*.json")):
        return "queue not empty"
    if (state / "KILL").exists():
        return "KILL file exists"


def propose(root, udb, state, dry):
    queue = root / "queue"
    if reason := skip_reason(queue, state):
        return {"skip": reason}
    retired = json.loads((root / "retired.json").read_text()) if (root / "retired.json").is_file() else {}
    templates = {name: template for name, template in TEMPLATES.items() if name not in retired}
    if not templates:
        return {"skip": "no open templates (all retired); a new reviewed template is needed"}
    query = ("SELECT trial_id, hypothesis, decision, round(delta, 4), round(ci_low, 4), "
             "round(json_extract(guards_json, '$.auc_old'), 4), round(json_extract(guards_json, '$.auc_new'), 4), json_extract(guards_json, '$.fit_accepted') "
             "FROM mg_trial ORDER BY ts DESC, trial_id LIMIT 20")
    try:
        rows = ledger(udb, query)
    except (OSError, sqlite3.Error) as exc:
        return {"skip": str(exc)}
    summary = "\n".join(json.dumps(row, separators=(",", ":")) for row in rows)
    ranges = {name: template["params"] for name, template in templates.items()}
    prompt = (f"Recent ledger rows (trial_id, hypothesis, decision, delta, ci_low, auc_old, auc_new, fit_accepted: 0 = RL2's own gate refused the refit, nothing measured):\n{summary}\n"
              f"Retired templates (NEVER propose these): {sorted(retired)}. "
              "Goal: pick ONE allowed template and parameters (never its baseline) that you expect to beat that template's "
              "baseline on the dev split (ci_low > 0) without hurting its guards. Prefer templates and parameters not yet "
              "in the ledger (rows are tagged [tpl:name params]); explore before refining.\n"
              f"Allowed templates and parameter ranges: {json.dumps(ranges)}\n"
              "Parameters rounds, minleaf, minlen, and and_terms require integer values.\n"
              'Reply with ONE line of JSON: {"template": "...", "params": {}, '
              '"hypothesis": "<=200 chars"}')
    for _ in range(3):
        try:
            proposal = parse(ask(prompt), templates)
            if dry:
                return build(root, udb, proposal)[1]
            state.mkdir(parents=True, exist_ok=True)
            with (state / "loop.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if reason := skip_reason(queue, state):
                    return {"skip": reason}
                filename, spec = build(root, udb, proposal)
                queue.mkdir(parents=True, exist_ok=True)
                temporary = NamedTemporaryFile(mode="w", dir=queue, delete=False)
                temp_path = Path(temporary.name)
                try:
                    with temporary:
                        temporary.write(json.dumps(spec) + "\n")
                    temp_path.replace(queue / filename)
                finally:
                    temp_path.unlink(missing_ok=True)
                return spec
        except (ValueError, OSError, sqlite3.Error, subprocess.SubprocessError) as exc:
            reason = str(exc)
    return {"skip": reason}


def main(argv=None):
    home = Path.home()
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=home / "repos/github_all/machine-god/trials")
    parser.add_argument("--udb", type=Path, default=home / ".local/share/agentzero/unified.db")
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args(argv)
    state = Path(os.getenv("MG_STATE", str(home / ".local/share/machine-god"))).expanduser()
    print(json.dumps(propose(args.root.expanduser().resolve(), args.udb.expanduser(), state, args.dry)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
