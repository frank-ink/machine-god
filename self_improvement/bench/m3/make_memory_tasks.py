"""Build the private weekly M3 recall task set from recorded actions."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import zlib
import json
import os
from pathlib import Path
import random
import re
import sqlite3
import tempfile

from m3_run import REPO, data_dir


TOKEN = re.compile(r"(?<![\w.])(?:[0-9]+\.[0-9]+|[0-9a-fA-F]{7,16})(?!\w|\.[0-9])")


def build_tasks(database, now, n=15, seed=None, exclude=()):
    cutoff = (now - timedelta(days=2)).timestamp()
    candidates, rows_by = {}, {}
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute(
            """SELECT value FROM durable_memory
               WHERE kind = 'tat' AND provenance = 'merke.py' AND ts < ?
               ORDER BY memory_id""",
            (cutoff,),
        )
        for (value,) in rows:
            parts = value.split(" | ", 2) if value else []
            if len(parts) != 3:
                continue
            was, result, evidence = parts
            tokens = {match.group() for match in TOKEN.finditer(result + " " + evidence)}
            if len(tokens) != 1:
                continue
            token = tokens.pop()
            description = re.sub(re.escape(token), "", was, flags=re.IGNORECASE).strip()
            if description:
                candidates.setdefault(description, set()).add(token)
                rows_by[description] = value

    eligible = sorted((description, next(iter(tokens)))
                      for description, tokens in candidates.items() if len(tokens) == 1
                      and memory_task(description, "0")["id"] not in exclude)
    if len(eligible) < n:
        raise ValueError(f"Need {n} eligible memory actions, found {len(eligible)}")
    week = now.strftime("%G-W%V")
    return [dict(memory_task(description, token), oracle=rows_by[description])   # oracle: the stored row, M3-002 oracle arms only
            for description, token in random.Random(seed or week).sample(eligible, n)]


def memory_task(description, token):
    task_id = hashlib.sha256(description.encode("utf-8")).hexdigest()[:24]
    return {
        "id": f"memory-{task_id}",
        "prompt": (
            "Recall the recorded action below from memory. Recover the distinctive "
            "hex string or decimal from its Ergebnis or Beleg. In the working directory, "
            "create answer.txt containing exactly that token without a newline.\n\n"
            + description
        ),
        "seed": {},
        "check": (
            "from pathlib import Path\n"
            f"raise SystemExit(Path('answer.txt').read_bytes() != {token.encode('ascii')!r})\n"
        ),
    }


def write_tasks(tasks, output):
    output = output.resolve()
    if output.is_relative_to(REPO):
        raise ValueError("Memory tasks must be stored outside the repository")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            for task in tasks:   # obfuscated so a plain-text search cannot find descriptions or answers (DESIGN 21a)
                stream.write("z:" + base64.b64encode(zlib.compress(json.dumps(task).encode())).decode() + "\n")
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=15)
    parser.add_argument("--seed")
    parser.add_argument("--out", default="tasks_memory.jsonl", help="file name inside the private data dir")
    parser.add_argument("--exclude", default="", help="comma list of task files in the private data dir whose tasks are skipped")
    args = parser.parse_args()
    from m3_run import read_jsonl
    exclude = {task["id"] for name in filter(None, args.exclude.split(",")) for task in read_jsonl(data_dir() / Path(name).name)}
    database = Path.home() / ".local/share/agentzero/unified.db"
    output = data_dir() / Path(args.out).name
    try:
        write_tasks(build_tasks(database, datetime.now(timezone.utc), args.n, args.seed, exclude), output)
    except (OSError, sqlite3.Error, ValueError) as error:
        raise SystemExit(str(error)) from None
    print(output)


if __name__ == "__main__":
    main()
