"""Report Machine God trial metrics for the trailing seven days."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sqlite3
import time

from mg_propose import ledger
from mg_watch import WATCH_SUFFIX


WEEK = 7 * 24 * 3600


def held_out_delta(row):
    trial_id, _, base_ref, delta, guards_json, _, _ = row
    try:
        guards = json.loads(guards_json or "{}")
    except ValueError:
        guards = {}
    if isinstance(guards, dict):
        value = guards.get("held_out_delta")
        if type(value) in (int, float):
            return value
        if guards.get("split") in ("audit", "held-out", "held_out"):
            return delta
    if trial_id.endswith("-AUDIT") or base_ref in ("audit", "held-out", "held_out"):
        return delta
    return None


def report(udb, now):
    rows = ledger(udb, """
        SELECT trial_id, hypothesis, base_ref, delta, guards_json, decision, ts
        FROM mg_trial WHERE ts BETWEEN ? AND ? ORDER BY ts, trial_id
    """, (now - WEEK, now))
    watches = [row for row in rows if row[2] == "watch"]
    trials = [row for row in rows if row[2] != "watch"]
    adopted = [row for row in trials if row[5] == "adopted"]
    reverted = {row[0] for row in trials if row[5] == "reverted"}
    reverted.update(row[0].removesuffix(WATCH_SUFFIX) for row in watches if row[5] == "reverted")
    attempts = {row[0] for row in adopted} | reverted

    hours = (trials[-1][6] - trials[0][6]) / 3600 if len(trials) >= 2 else 0.0
    deltas = [delta for row in adopted if (delta := held_out_delta(row)) is not None]
    templates = Counter()
    for row in trials:
        marker = re.search(r"\[tpl:([^\s\]]+)", row[1] or "")
        templates[marker[1] if marker else "unknown"] += 1

    return {
        "trials_per_7_days": len(trials),
        "acceptance_rate": len(adopted) / len(trials) if trials else None,
        "revert_rate": len(reverted) / len(attempts) if attempts else None,
        "held_out_delta_per_compute_hour": sum(deltas) / hours if hours and (deltas or not adopted) else None,
        "adoptions_with_held_out_delta": len(deltas),
        "compute_hours": hours,
        "compute_hours_source": "sum of gaps between trial completion timestamps in the window, including idle time",
        "per_template_counts": dict(templates),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--udb", type=Path, default=Path.home() / ".local/share/agentzero/unified.db")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(report(args.udb.expanduser(), time.time()), indent=2))
    except sqlite3.Error as exc:
        parser.exit(1, f"{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
