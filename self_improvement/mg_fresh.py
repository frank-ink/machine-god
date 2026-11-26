"""Build weekly known-item probes and measure the live UDB lane."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import re
import sqlite3
from tempfile import NamedTemporaryFile


HERE = Path(__file__).resolve().parent
WORD = re.compile(r"[a-z]{6,}")
WEEKLY_FILE = re.compile(r"probes-([0-9]{6})\.jsonl")
DAY = 24 * 3600


def build(udb, fresh, now):
    year, week, _ = now.isocalendar()
    rnd = random.Random(week)
    probes = []
    with closing(sqlite3.connect(udb.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA temp_store=MEMORY")
        db.execute("CREATE VIRTUAL TABLE temp.v USING fts5vocab(main, uu_fts, row)")
        rows = db.execute(
            "SELECT m.memory_id, m.subject, m.value FROM durable_memory m "
            "WHERE m.kind != 'ereignis' AND length(m.value) >= 200 AND m.ts BETWEEN ? AND ? "
            "AND EXISTS (SELECT 1 FROM uu_fts_doc d WHERE d.memory_id = m.memory_id) "
            "ORDER BY m.memory_id", (now.timestamp() - 30 * DAY, now.timestamp()),
        ).fetchall()

        def typo(word):
            i = rnd.randrange(1, len(word) - 2)
            return word[:i] + word[i + 1] + word[i] + word[i + 2:]

        first = rnd.sample(rows, min(30, len(rows)))
        picked = {row[0] for row in first}
        remaining = [row for row in rows if row[0] not in picked]
        for batch in (first, remaining):
            if batch is not first:
                rnd.shuffle(batch)
            for mid, subject, value in batch:
                words = sorted(set(WORD.findall((str(subject or "") + " " + str(value or "")).lower())))
                df = {}
                for i in range(0, len(words), 900):
                    terms = words[i:i + 900]
                    placeholders = ",".join("?" for _ in terms)
                    df.update(db.execute(f"SELECT term, doc FROM temp.v WHERE term IN ({placeholders})", terms))
                clean = sorted((w for w in words if df.get(w, 0) > 0), key=lambda w: (df[w], w))[:6]
                if len(clean) < 6:
                    continue
                indices = rnd.sample(range(6), 2)
                noisy = [typo(w) if i in indices else w for i, w in enumerate(clean)]
                probes.extend(dict(doc_id=mid, query=" ".join(words), cell=cell)
                              for cell, words in (("clean", clean), ("P3", noisy)))
                if len(probes) == 60:
                    break
            if len(probes) == 60:
                break

    if len(probes) != 60:
        raise ValueError(f"need 30 eligible documents with six indexed words, found {len(probes) // 2}")
    fresh.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = fresh / f"probes-{year:04d}{week:02d}.jsonl"
    with NamedTemporaryFile(mode="w", dir=fresh, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.writelines(json.dumps(probe) + "\n" for probe in probes)
            output.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return path


def measure(fresh, output_dir):
    source = max((p for p in fresh.glob("probes-*.jsonl") if WEEKLY_FILE.fullmatch(p.name)), default=None)
    if source is None:
        raise ValueError(f"no weekly probe files in {fresh}")
    probes = [json.loads(line) for line in source.read_text().splitlines()]
    if not probes:
        raise ValueError(f"{source}: no probes to measure")

    from experiments import tpl_recall_lane as recall

    # The live fallback uses OR only, without spelling correction.
    params = recall.BASE if recall.BR._recall_f_on() else (float("inf"), 0)
    ranks = [recall.rr5(recall.lane(p["query"].split(), *params), p["doc_id"]) for p in probes]
    week = WEEKLY_FILE.fullmatch(source.name)[1]
    result = {
        "week": week, "n_probes": len(ranks),
        "hit@1": sum(rank == 1 for rank in ranks) / len(ranks),
        "hit@5": sum(rank > 0 for rank in ranks) / len(ranks),
        "MRR@5": sum(ranks) / len(ranks),
    }
    (output_dir / f"mg_fresh_{week}.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main(argv=None):
    home = Path.home()
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build")
    measure_parser = commands.add_parser("measure")
    for command in (build_parser, measure_parser):
        command.add_argument("--fresh", type=Path, default=home / ".local/share/machine-god/fresh")
    build_parser.add_argument("--udb", type=Path, default=home / ".local/share/agentzero/unified.db")
    measure_parser.add_argument("--experiments", type=Path, default=HERE / "experiments")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            print(build(args.udb, args.fresh, datetime.now(timezone.utc)))
        else:
            print(json.dumps(measure(args.fresh, args.experiments)))
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
