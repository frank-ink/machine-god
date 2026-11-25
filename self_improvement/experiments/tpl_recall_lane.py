"""Measure known-item recall for the frank-brain UDB lane."""
import argparse
from contextlib import closing
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import re
from statistics import median
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "mgfixed"))
from mg.gate import paired_bootstrap

spec = importlib.util.spec_from_file_location(
    "bridge", os.path.expanduser("~/repos/github_all/frank-brain-mcp/server/bridge.py")
)
BR = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BR)
WORD = re.compile(r"[a-z]{6,}")
BASE = (4, 6)


def probes(split):
    rnd = random.Random(11)

    def typo(word):
        i = rnd.randrange(1, len(word) - 2)
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]

    with closing(BR._ro()) as c:
        c.execute("PRAGMA temp_store=MEMORY")
        rows = c.execute(
            "select m.memory_id, m.subject, m.value from durable_memory m "
            "join uu_fts_doc d on d.memory_id = m.memory_id "
            "where m.kind != 'ereignis' and length(m.value) >= 200 order by m.memory_id"
        ).fetchall()
        for mid, subject, value in rnd.sample(rows, 400):
            words = set(WORD.findall((str(subject or "") + " " + str(value or "")).lower()))
            df = BR._vocab_df(c, words)
            clean = sorted((w for w in words if df.get(w, 0) > 0), key=lambda w: (df[w], w))[:6]
            if len(clean) < 6:
                continue
            indices = rnd.sample(range(6), 2)
            noisy = [typo(w) if i in indices else w for i, w in enumerate(clean)]
            # Consume the same random draws as the original before splitting.
            if (hashlib.sha256(mid.encode()).hexdigest()[-1] < "8") == (split == "dev"):
                yield mid, clean, noisy


def lane(words, minlen, and_terms):
    terms = [w.lower() for w in words]
    if not terms:
        return []
    with closing(BR._ro()) as c:
        c.execute("PRAGMA temp_store=MEMORY")
        df = BR._vocab_df(c, terms)
        for i, term in enumerate(terms):
            if df.get(term, 0) or len(term) < minlen or not term.isalnum():
                continue
            edits = BR._vocab_df(c, BR._edits1(term))
            best = max(((count, word) for word, count in edits.items() if count > 0), default=None)
            if best:
                df[best[1]], terms[i] = best
        rows = []
        if len(terms) > 1 and and_terms >= 2:
            selected = terms
            if and_terms < len(terms):
                selected = sorted(terms, key=lambda w: (df.get(w, 0), w))[:and_terms]
            rows = BR._udb_rows(c, " AND ".join(f'"{w}"' for w in selected), 12)
        seen = {row[0] for row in rows}
        rows += [row for row in BR._udb_rows(c, " OR ".join(f'"{w}"' for w in terms), 12)
                 if row[0] not in seen]
        return [row[0] for row in rows[:12]]


def rr5(ids, mid):
    return next((1.0 / i for i, item in enumerate(ids[:5], 1) if item == mid), 0.0)


def evaluate(queries, candidate):
    scores = [{}, {}]
    p95s = [[], []]
    for rep in range(4):
        times = [[], []]
        for key, mid, words in queries:
            for arm, params in enumerate((BASE, candidate)):
                start = time.perf_counter()
                ids = lane(words, *params)
                times[arm].append((time.perf_counter() - start) * 1000)
                if rep == 0:
                    scores[arm][key] = rr5(ids, mid)
        if rep:
            for values, samples in zip(times, p95s):
                samples.append(sorted(values)[int(0.95 * len(values))])
    return *scores, *(median(samples) for samples in p95s)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("split", choices=("dev", "audit"))
    parser.add_argument("minlen", type=int)
    parser.add_argument("and_terms", type=int)
    args = parser.parse_args()
    queries = [(f"{cell}|{mid}", mid, words) for mid, clean, noisy in probes(args.split)
               for cell, words in (("clean", clean), ("P3", noisy))]
    base, cand, p95_base, p95_cand = evaluate(queries, (args.minlen, args.and_terms))
    pooled = paired_bootstrap(base, cand, n=10000, seed=0)
    cells = {}
    for cell in ("clean", "P3"):
        keys = [key for key in base if key.startswith(cell + "|")]
        cells[cell] = paired_bootstrap({k: base[k] for k in keys}, {k: cand[k] for k in keys},
                                       n=10000, seed=0)
    passed = (pooled["ci_low"] > 0 and all(bs["ci_low"] >= -0.02 for bs in cells.values())
              and p95_cand <= 1.25 * p95_base + 5)
    result = dict(PASS=passed, pooled=pooled, **cells, p95_base=p95_base, p95_cand=p95_cand,
                  params=dict(minlen=args.minlen, and_terms=args.and_terms), fit_accepted=True)
    output = json.dumps(result, indent=2)
    (HERE / f"tpl_recall_lane_{args.split}.json").write_text(output + "\n")
    print(output)


if __name__ == "__main__":
    main()
