import hashlib
import json
import math
import os
import random
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys
import time
import zlib
from collections import Counter
from contextlib import closing
from itertools import groupby
from pathlib import Path

LIVE = Path("~/.claude/star/rl2").expanduser()
STATE = Path("~/.cache/machine-god/rl2").expanduser()
COPY = str(STATE / "rl2.db")
MODULES = os.path.expanduser("~/.claude/star/modules/rl2")
EXPERIMENTS = Path("~/repos/github_all/machine-god/experiments").expanduser()
CELLS = ("clean", "p3")
sys.path.insert(0, str(EXPERIMENTS / "mgfixed"))
sys.path.insert(0, MODULES)
os.environ["RL2_DB"] = COPY
import rl2_core as K
from mg.gate import paired_bootstrap


def split_of(doc_id):
    digit = hashlib.sha256(str(doc_id).encode()).hexdigest()[-1]
    return "train" if digit <= "a" else "promo" if digit <= "c" else "audit"


def build():
    STATE.mkdir(parents=True, exist_ok=True)
    uri = (LIVE / "rl2.db").as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as source, closing(sqlite3.connect(COPY)) as c:
        source.backup(c)
        with closing(sqlite3.connect(str(STATE / "rl2_base.db"))) as base:
            source.backup(base)  # pristine: old model is scored here (fit halves dbias in COPY)
        for name in ("net.bin", "judged.jsonl", "sem_crossfit.json"):
            if (LIVE / name).exists():
                shutil.copy(LIVE / name, STATE)
        docs = [(doc_id, set(re.findall(r"[a-z]{6,}", (title + " " + body).lower())))
                for doc_id, title, body in c.execute("SELECT id, title, body FROM docs ORDER BY id")]
    df = Counter(word for _, words in docs for word in words)
    rnd = random.Random(21)
    with (STATE / "probes.jsonl").open("w", encoding="utf-8") as out:
        for doc_id, words in docs:
            if len(words) < 6:
                continue
            clean = sorted(words, key=lambda w: (df[w], w))[:6]
            p3 = clean.copy()
            for pos in rnd.sample(range(6), 2):
                w = p3[pos]
                i = rnd.randrange(1, len(w) - 2)
                p3[pos] = w[:i] + w[i + 1] + w[i] + w[i + 2:]
            print(json.dumps(dict(doc_id=doc_id, split=split_of(doc_id), clean=clean, p3=p3)), file=out)


def read_rows(name):
    with (STATE / name).open(encoding="utf-8") as rows:
        yield from map(json.loads, rows)


def rank(c, model, words):
    q = K.q_prompt(" ".join(words))
    if not q:
        return []
    hits, _ = K.search(c, q)
    K.score_hits(c, model, hits, q)
    return hits


def nonblind(sid):
    """17v/18b: synthetic rows must stay out of RL2's blind fold (crc32 % 5 == 0), so its acceptance test sees real labels only"""
    k = 0
    while zlib.crc32((sid + (f"-t{k}" if k else "")).encode()) % 5 == 0:
        k += 1
    return sid + (f"-t{k}" if k else "")


def train(c):
    model = K.Model.load(c)
    with c:
        for probe in read_rows("probes.jsonl"):
            if probe["split"] != "train":
                continue
            target = probe["doc_id"]
            for cell in CELLS:
                ts = time.time()
                hits = rank(c, model, probe[cell])
                c.executemany(
                    "INSERT INTO explicit_rows(ts,session,ev,doc_id,feat,y,wt,src,ctx) "
                    "VALUES(?,?,'prompt',?,?,?,1.0,'mg_knownitem','')",
                    ((ts, nonblind("mgki-%d" % target), h["id"], json.dumps(h["feat"]), float(h["id"] == target))
                     for i, h in enumerate(hits) if i < 10 or h["id"] == target),
                )
    with c:
        c.execute("INSERT OR REPLACE INTO model(k,v) SELECT 'mg_old',v FROM model WHERE k='current'")
    env = dict(os.environ, RL2_DB=COPY, RL2_STATE_DIR=str(STATE), RL2_NOSYNC="1")
    result = subprocess.run([sys.executable, os.path.join(MODULES, "rl2_judge.py"), "fit"],
                            env=env, stdout=subprocess.PIPE, text=True)
    (STATE / "fit.log").write_text(result.stdout, encoding="utf-8")
    print(result.stdout, end="")
    result.check_returncode()


def mann_whitney(pairs):
    negatives = wins = positives = 0
    for _, group in groupby(sorted(pairs), key=lambda pair: pair[0]):
        labels = [label for _, label in group]
        pos = sum(labels)
        neg = len(labels) - pos
        wins += pos * (negatives + neg / 2)
        positives += pos
        negatives += neg
    return wins / (positives * negatives)


def measure(c, model, queries):
    rr = {key: next((1 / (i + 1) for i, hit in enumerate(rank(c, model, words)[:5])
                    if hit["id"] == doc_id), 0.0) for key, doc_id, words in queries}
    p95s = []
    for _ in range(5):
        timings = []
        for _, _, words in queries:
            start = time.perf_counter()
            rank(c, model, words)
            timings.append(1000 * (time.perf_counter() - start))
        p95s.append(sorted(timings)[math.ceil(0.95 * len(timings)) - 1])
    return rr, statistics.median(p95s)


def evaluate(c, split):
    base = sqlite3.connect((STATE / "rl2_base.db").as_uri() + "?mode=ro", uri=True)
    old, new = K.Model.load(base), K.Model.load(c)
    queries = [(f"{cell}|{p['doc_id']}", p["doc_id"], p[cell])
               for p in read_rows("probes.jsonl") if p["split"] == split for cell in CELLS]
    old_rr, p95_old = measure(base, old, queries)
    new_rr, p95_new = measure(c, new, queries)
    report = {"pooled": paired_bootstrap(old_rr, new_rr, n=10000, seed=0)}
    for cell in CELLS:
        keys = [key for key in old_rr if key.startswith(cell + "|")]
        report[cell] = paired_bootstrap({k: old_rr[k] for k in keys}, {k: new_rr[k] for k in keys},
                                        n=10000, seed=0)
    judged = [r for r in read_rows("judged.jsonl") if split_of(r["doc"]) != "train"]
    auc = getattr(K, "auc", mann_whitney)
    auc_old, auc_new = (auc([(m.logit(r["feat"]), r["j"] >= 2) for r in judged]) for m in (old, new))
    report.update(split=split, auc_old=auc_old, auc_new=auc_new, p95_old_ms=p95_old, p95_new_ms=p95_new)
    report["PASS"] = (report["pooled"]["ci_low"] >= 0.02 and report["clean"]["ci_low"] >= -0.02
                      and report["p3"]["ci_low"] >= -0.02 and auc_new >= auc_old - 0.01
                      and p95_new <= 1.25 * p95_old)
    output = json.dumps(report, indent=2)
    (EXPERIMENTS / f"rl2_001_{split}.json").write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    if (args := sys.argv[1:]) == ["build"]:
        build()
    elif args == ["train"] or args in (["eval", "promo"], ["eval", "audit"]):
        with closing(sqlite3.connect(Path(COPY).as_uri() + "?mode=rw", uri=True)) as c:
            train(c) if args == ["train"] else evaluate(c, args[1])
    else:
        sys.exit("Usage: rl2_001_knownitem.py build | train | eval {promo,audit}")
