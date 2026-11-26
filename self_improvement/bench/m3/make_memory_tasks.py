"""Build the private weekly M3 recall task set from recorded actions."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re
import sqlite3
import tempfile

from m3_run import REPO, data_dir


TOKEN = re.compile(r"(?<![\w.])(?:[0-9]+\.[0-9]+|[0-9a-fA-F]{7,16})(?!\w|\.[0-9])")


def build_tasks(database, now):
    cutoff = (now - timedelta(days=2)).timestamp()
    candidates = {}
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

    eligible = sorted((description, next(iter(tokens)))
                      for description, tokens in candidates.items() if len(tokens) == 1)
    if len(eligible) < 15:
        raise ValueError(f"Need 15 eligible memory actions, found {len(eligible)}")
    week = now.strftime("%G-W%V")
    return [memory_task(description, token)
            for description, token in random.Random(week).sample(eligible, 15)]


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
            for task in tasks:
                stream.write(json.dumps(task, ensure_ascii=False) + "\n")
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    database = Path.home() / ".local/share/agentzero/unified.db"
    output = data_dir() / "tasks_memory.jsonl"
    try:
        write_tasks(build_tasks(database, datetime.now(timezone.utc)), output)
    except (OSError, sqlite3.Error, ValueError) as error:
        raise SystemExit(str(error)) from None
    print(output)


if __name__ == "__main__":
    main()
