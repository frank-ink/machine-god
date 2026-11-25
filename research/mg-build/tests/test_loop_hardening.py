import json
import os
import sys

import pytest

from mg import ledger, loop
from mg import bench_retrieval as br

BAD, GOOD = "mg.retrievers:newest_first", "mg.retrievers:fts_bm25_or"


def go(synth_db, probes, tmp_path, base, cand, **kw):
    d, p, a = (br.load_probes(x) for x in probes)
    return loop.trial(synth_db, str(tmp_path / "led.db"), "h", base, cand, d, p, a, min_n=10, n_boot=300, **kw)


def test_kill_file_created_between_dev_and_promo(synth_db, probes, tmp_path, monkeypatch):
    """Kill file created by candidate retriever on its 20th call (during dev) -> Refused before promo."""
    kill_path = str(tmp_path / "KILL")
    retriever_code = (
        "from mg.retrievers import fts_bm25_or\n"
        "_n = 0\n"
        "\n"
        "def retrieve(conn, query, k):\n"
        "    global _n\n"
        "    _n += 1\n"
        "    if _n == 20:\n"
        "        open(%r, 'w').write('kill')\n"
        "    return fts_bm25_or(conn, query, k)\n"
    ) % kill_path
    mod_path = tmp_path / "custom_retriever.py"
    mod_path.write_text(retriever_code)
    monkeypatch.syspath_prepend(str(tmp_path))

    monkeypatch.setattr(loop, "KILL", kill_path)
    monkeypatch.delenv("MG_KILL_FILE", raising=False)

    d, p, a = (br.load_probes(x) for x in probes)
    with pytest.raises(loop.Refused) as exc:
        loop.trial(synth_db, str(tmp_path / "led.db"), "h", BAD, "custom_retriever:retrieve", d, p, a,
                   min_n=10, n_boot=300)

    assert "kill file present" in str(exc.value)

    c = ledger.connect(str(tmp_path / "led.db"))
    trials = ledger.trials(c)
    assert len(trials) == 1
    assert trials[0]["decision"] == "ABORTED"
    promo_runs = c.execute("select count(*) from mg_run where run_id like '%:promo:%'").fetchone()[0]
    assert promo_runs == 0


def test_mg_kill_file_semantics(synth_db, probes, tmp_path, monkeypatch):
    """MG_KILL_FILE semantics: nonexistent doesn't disable default; existing alone kills; dead symlink counts."""
    default_kill = tmp_path / "default_KILL"
    monkeypatch.setattr(loop, "KILL", str(default_kill))

    # 1. MG_KILL_FILE pointing to nonexistent path does NOT disable default KILL
    nonexistent = tmp_path / "nonexistent_KILL"
    monkeypatch.setenv("MG_KILL_FILE", str(nonexistent))
    default_kill.write_text("x")

    with pytest.raises(loop.Refused) as exc:
        go(synth_db, probes, tmp_path, BAD, GOOD)
    assert "kill file present" in str(exc.value)
    assert str(default_kill) in str(exc.value)

    default_kill.unlink()
    nonexistent.unlink(missing_ok=True)

    # 2. MG_KILL_FILE existing alone also kills (add semantics)
    env_kill = tmp_path / "env_KILL"
    monkeypatch.setenv("MG_KILL_FILE", str(env_kill))
    env_kill.write_text("x")

    with pytest.raises(loop.Refused) as exc:
        go(synth_db, probes, tmp_path, BAD, GOOD)
    assert "kill file present" in str(exc.value)
    assert str(env_kill) in str(exc.value)

    env_kill.unlink()
    monkeypatch.delenv("MG_KILL_FILE", raising=False)

    # 3. Dead symlink at default KILL counts (os.path.lexists)
    dead_target = tmp_path / "dead_target"
    dead_link = tmp_path / "dead_KILL"
    os.symlink(str(dead_target), str(dead_link))
    monkeypatch.setattr(loop, "KILL", str(dead_link))

    with pytest.raises(loop.Refused) as exc:
        go(synth_db, probes, tmp_path, BAD, GOOD)
    assert "kill file present" in str(exc.value)
    assert str(dead_link) in str(exc.value)


def test_promo_budget_not_resettable_by_renaming_bench_version(synth_db, probes, tmp_path, monkeypatch):
    """Budget counted per derived bench_version (hash of probe ids), not label."""
    monkeypatch.setattr(loop, "KILL", str(tmp_path / "KILL"))
    monkeypatch.delenv("MG_KILL_FILE", raising=False)

    d, p, a = (br.load_probes(x) for x in probes)

    # First trial with label 'v0' succeeds in reaching promo
    r1 = loop.trial(synth_db, str(tmp_path / "led.db"), "h", BAD, GOOD, d, p, a,
                    bench_version="v0", min_n=10, n_boot=300, max_promo_attempts=1)
    assert r1["decision"] == "keep"

    # Second trial with label 'other' but SAME probe ids -> same derived bench_version
    with pytest.raises(loop.PromoBudgetRefused) as exc:
        loop.trial(synth_db, str(tmp_path / "led.db"), "h", BAD, GOOD, d, p, a,
                   bench_version="other", min_n=10, n_boot=300, max_promo_attempts=1)

    assert exc.value.decision == "REFUSED_PROMO_BUDGET"

    c = ledger.connect(str(tmp_path / "led.db"))
    trials = ledger.trials(c)
    assert len(trials) == 2
    assert trials[0]["decision"] == "REFUSED_PROMO_BUDGET"
    assert trials[1]["decision"] == "keep"


def test_overlapping_item_id_refused_before_ledger_row(synth_db, probes, tmp_path, monkeypatch):
    """Overlapping item_id between dev and promo -> Refused, mg_trial count 0."""
    monkeypatch.setattr(loop, "KILL", str(tmp_path / "KILL"))
    monkeypatch.delenv("MG_KILL_FILE", raising=False)

    d = br.load_probes(probes[0])
    p = br.load_probes(probes[1])
    a = br.load_probes(probes[2])

    p_overlap = p.copy()
    p_overlap[0] = d[0]

    with pytest.raises(loop.Refused) as exc:
        loop.trial(synth_db, str(tmp_path / "led.db"), "h", BAD, GOOD, d, p_overlap, a, min_n=10, n_boot=300)

    assert "item_id" in str(exc.value) and "appears in both" in str(exc.value)

    c = ledger.connect(str(tmp_path / "led.db"))
    trials = ledger.trials(c)
    assert len(trials) == 0


def test_same_query_expect_different_item_ids_refused(synth_db, probes, tmp_path, monkeypatch):
    """Same (query, expect_doc_id) under different item_ids in dev and promo -> Refused."""
    monkeypatch.setattr(loop, "KILL", str(tmp_path / "KILL"))
    monkeypatch.delenv("MG_KILL_FILE", raising=False)

    d = br.load_probes(probes[0])
    p = br.load_probes(probes[1])
    a = br.load_probes(probes[2])

    p_overlap = p.copy()
    p_overlap[0] = {"item_id": "different_id", "query": d[0]["query"], "expect_doc_id": d[0]["expect_doc_id"]}

    with pytest.raises(loop.Refused) as exc:
        loop.trial(synth_db, str(tmp_path / "led.db"), "h", BAD, GOOD, d, p_overlap, a, min_n=10, n_boot=300)

    assert "(query, expect) pair appears in both" in str(exc.value)

    c = ledger.connect(str(tmp_path / "led.db"))
    trials = ledger.trials(c)
    assert len(trials) == 0


def test_duplicate_item_id_inside_split_refused(synth_db, probes, tmp_path, monkeypatch):
    """Duplicate item_id inside one split -> Refused."""
    monkeypatch.setattr(loop, "KILL", str(tmp_path / "KILL"))
    monkeypatch.delenv("MG_KILL_FILE", raising=False)

    d = br.load_probes(probes[0])
    p = br.load_probes(probes[1])
    a = br.load_probes(probes[2])

    d_dup = d.copy()
    d_dup[1] = d_dup[0].copy()

    with pytest.raises(loop.Refused) as exc:
        loop.trial(synth_db, str(tmp_path / "led.db"), "h", BAD, GOOD, d_dup, p, a, min_n=10, n_boot=300)

    assert "duplicate item_id in dev" in str(exc.value)

    c = ledger.connect(str(tmp_path / "led.db"))
    trials = ledger.trials(c)
    assert len(trials) == 0


def test_candidate_crash_propagates_and_writes_aborted_row(synth_db, probes, tmp_path, monkeypatch):
    """Candidate retriever raising RuntimeError -> RuntimeError propagates AND mg_trial row ABORTED with error text."""
    monkeypatch.setattr(loop, "KILL", str(tmp_path / "KILL"))
    monkeypatch.delenv("MG_KILL_FILE", raising=False)

    retriever_code = (
        "def retrieve(conn, query, k):\n"
        "    raise RuntimeError(\"boom from candidate\")\n"
    )
    mod_path = tmp_path / "crash_retriever.py"
    mod_path.write_text(retriever_code)
    monkeypatch.syspath_prepend(str(tmp_path))

    d, p, a = (br.load_probes(x) for x in probes)
    with pytest.raises(RuntimeError) as exc:
        loop.trial(synth_db, str(tmp_path / "led.db"), "h", BAD, "crash_retriever:retrieve", d, p, a,
                   min_n=10, n_boot=300)

    assert "boom from candidate" in str(exc.value)

    c = ledger.connect(str(tmp_path / "led.db"))
    trials = ledger.trials(c)
    assert len(trials) == 1
    assert trials[0]["decision"] == "ABORTED"
    detail = json.loads(trials[0]["detail"])
    assert "error" in detail
    assert "boom from candidate" in detail["error"]


def test_hit5_hard_guard_rejects_empty_candidate(synth_db, probes, tmp_path, monkeypatch):
    """Candidate returning [] for every query vs base GOOD -> decision 'reject' with guard 'hit5'."""
    monkeypatch.setattr(loop, "KILL", str(tmp_path / "KILL"))
    monkeypatch.delenv("MG_KILL_FILE", raising=False)

    retriever_code = (
        "def retrieve(conn, query, k):\n"
        "    return []\n"
    )
    mod_path = tmp_path / "empty_retriever.py"
    mod_path.write_text(retriever_code)
    monkeypatch.syspath_prepend(str(tmp_path))

    d, p, a = (br.load_probes(x) for x in probes)
    r = loop.trial(synth_db, str(tmp_path / "led.db"), "h", GOOD, "empty_retriever:retrieve", d, p, a,
                   min_n=10, n_boot=300)

    assert r["decision"] == "reject"
    assert r["stage_reached"] == "dev"
    # check that hit5 guard is present in the list of guards
    guards = r["stages"]["dev"]["guards"]
    assert any(g["name"] == "hit5" for g in guards)
    hit5_guard = next(g for g in guards if g["name"] == "hit5")
    assert hit5_guard["kind"] == "hard"
    assert hit5_guard["direction"] == "higher"
    assert hit5_guard["cand"] == 0.0
    assert hit5_guard["base"] > 0.0

    c = ledger.connect(str(tmp_path / "led.db"))
    trials = ledger.trials(c)
    assert len(trials) == 1
    detail = json.loads(trials[0]["detail"])
    assert "seed" in detail
    assert "n_boot" in detail
    assert "bench_version_label" in detail
    assert "derived_bench_version" in detail
    assert detail["derived_bench_version"].startswith("b-")


def test_budget_s_exceeded_via_monotonic_mock(synth_db, probes, tmp_path, monkeypatch):
    """Monkeypatch time.monotonic to jump by 1000s -> Refused('budget exceeded') and ABORTED row."""
    monkeypatch.setattr(loop, "KILL", str(tmp_path / "KILL"))
    monkeypatch.delenv("MG_KILL_FILE", raising=False)

    counter = {"val": 0.0}

    def mock_monotonic():
        counter["val"] += 1000.0
        return counter["val"]

    monkeypatch.setattr(loop.time, "monotonic", mock_monotonic)

    d, p, a = (br.load_probes(x) for x in probes)
    with pytest.raises(loop.Refused) as exc:
        loop.trial(synth_db, str(tmp_path / "led.db"), "h", BAD, GOOD, d, p, a,
                   min_n=10, n_boot=300, budget_s=10.0)

    assert "budget exceeded" in str(exc.value)

    c = ledger.connect(str(tmp_path / "led.db"))
    trials = ledger.trials(c)
    assert len(trials) == 1
    assert trials[0]["decision"] == "ABORTED"
    detail = json.loads(trials[0]["detail"])
    assert "error" in detail
    assert "budget exceeded" in detail["error"]


def test_cli_kill_file_returns_3(synth_db, probes, tmp_path, monkeypatch, capsys):
    """CLI main() returns 3 with {"refused": ...} when kill file exists."""
    monkeypatch.setattr(loop, "KILL", str(tmp_path / "KILL"))
    monkeypatch.delenv("MG_KILL_FILE", raising=False)

    (tmp_path / "KILL").write_text("x")

    argv = ["trial", "--hypothesis", "h", "--base-retriever", BAD, "--cand-retriever", GOOD,
            "--db", synth_db, "--ledger", str(tmp_path / "l.db"),
            "--probes-dev", probes[0], "--probes-promo", probes[1], "--probes-audit", probes[2]]

    ret = loop.main(argv)
    assert ret == 3
    out = json.loads(capsys.readouterr().out)
    assert "refused" in out
    assert "kill file present" in out["refused"]


def test_cli_invalid_json_probes_returns_2(synth_db, probes, tmp_path, monkeypatch, capsys):
    """CLI main() returns 2 with {"error": ...} when probes file contains invalid JSON."""
    monkeypatch.setattr(loop, "KILL", str(tmp_path / "KILL"))
    monkeypatch.delenv("MG_KILL_FILE", raising=False)

    bad_probes = tmp_path / "bad.jsonl"
    bad_probes.write_text("not valid json\n")

    argv = ["trial", "--hypothesis", "h", "--base-retriever", BAD, "--cand-retriever", GOOD,
            "--db", synth_db, "--ledger", str(tmp_path / "l.db"),
            "--probes-dev", str(bad_probes), "--probes-promo", probes[1], "--probes-audit", probes[2]]

    ret = loop.main(argv)
    assert ret == 2
    out = json.loads(capsys.readouterr().out)
    assert "error" in out
