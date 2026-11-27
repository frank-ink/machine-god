from contextlib import closing
from datetime import datetime, timezone
import json
import sqlite3
import sys
from types import ModuleType, SimpleNamespace

import pytest

import mg_fresh


NOW = datetime(2027, 1, 1, tzinfo=timezone.utc)
WORDS = "bravely crimson diamond emerald fortress glacier"


def memory_db(path, count):
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript("""
            CREATE TABLE durable_memory (memory_id, subject, value, kind, ts);
            CREATE TABLE uu_fts_doc (fts_rowid, memory_id);
            CREATE VIRTUAL TABLE uu_fts USING fts5(body);
        """)
        for i in range(count + 4):
            ts = NOW.timestamp()
            subject, kind = WORDS, "note"
            if i == count:
                ts -= 30 * mg_fresh.DAY + 1
            elif i == count + 1:
                ts += 1
            elif i == count + 2:
                kind = "ereignis"
            elif i == count + 3:
                subject = "short"
            body = (subject + " ") * 40
            db.execute("INSERT INTO durable_memory VALUES (?, ?, ?, ?, ?)",
                       (f"doc-{i}", subject, body, kind, ts))
            rowid = db.execute("INSERT INTO uu_fts VALUES (?)", (body,)).lastrowid
            db.execute("INSERT INTO uu_fts_doc VALUES (?, ?)", (rowid, f"doc-{i}"))


def test_build_paired_and_reproducible(tmp_path):
    udb = tmp_path / "db?#.sqlite"
    memory_db(udb, 32)
    original = udb.read_bytes()
    fresh = tmp_path / "fresh"
    path = mg_fresh.build(udb, fresh, NOW)
    assert path.name == "probes-202653.jsonl"
    probes = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(probes) == 60
    assert len({probe["doc_id"] for probe in probes}) == 30
    for clean, noisy in zip(probes[::2], probes[1::2]):
        assert clean == dict(doc_id=noisy["doc_id"], query=WORDS, cell="clean")
        assert int(clean["doc_id"].split("-")[1]) < 32
        assert noisy["cell"] == "P3"
        assert sum(a != b for a, b in zip(WORDS.split(), noisy["query"].split())) == 2

    before = path.read_bytes()
    mg_fresh.build(udb, fresh, NOW)
    assert path.read_bytes() == before
    assert udb.read_bytes() == original
    assert path.stat().st_mode & 0o077 == 0


def test_build_insufficient_docs(tmp_path):
    udb = tmp_path / "unified.db"
    memory_db(udb, 29)
    with pytest.raises(ValueError, match="found 29"):
        mg_fresh.build(udb, tmp_path / "fresh", NOW)
    assert not (tmp_path / "fresh").exists()


@pytest.mark.parametrize("enabled,params", [(True, (4, 6)), (False, (float("inf"), 0))])
def test_measure_uses_live_lane_and_newest_probe_file(tmp_path, monkeypatch, enabled, params):
    module = ModuleType("experiments.tpl_recall_lane")
    module.BASE = (4, 6)
    module.BR = SimpleNamespace(_recall_f_on=lambda: enabled)
    calls = []

    def lane(words, *actual):
        assert actual == params
        calls.append(words)
        return {"first": ["doc"], "second": ["other", "doc"], "miss": ["other"]}[words[0]]

    module.lane = lane
    module.rr5 = lambda ids, mid: 1 / (ids.index(mid) + 1) if mid in ids[:5] else 0.0
    monkeypatch.setitem(sys.modules, module.__name__, module)
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    (fresh / "probes-202653.jsonl").write_text("unused")
    (fresh / "probes-not-a-week.jsonl").write_text("unused")
    probes = [dict(doc_id="doc", query=f"{word} words", cell="clean") for word in ("first", "second", "miss")]
    (fresh / "probes-202701.jsonl").write_text("\n".join(map(json.dumps, probes)))
    result = mg_fresh.measure(fresh, tmp_path)
    assert calls == [["first", "words"], ["second", "words"], ["miss", "words"]]
    assert result == {"week": "202701", "n_probes": 3, "hit@1": 1 / 3, "hit@5": 2 / 3, "MRR@5": 0.5}
    assert json.loads((tmp_path / "mg_fresh_202701.json").read_text()) == result
