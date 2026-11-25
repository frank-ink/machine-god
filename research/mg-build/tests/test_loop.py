import json
import os

import pytest

from mg import ledger, loop

BAD, GOOD = "mg.retrievers:newest_first", "mg.retrievers:fts_bm25_or"


@pytest.fixture(autouse=True)
def nokill(tmp_path, monkeypatch):
    monkeypatch.setenv("MG_KILL_FILE", str(tmp_path / "KILL"))


def go(synth_db, probes, tmp_path, base, cand, **kw):
    from mg import bench_retrieval as br
    d, p, a = (br.load_probes(x) for x in probes)
    return loop.trial(synth_db, str(tmp_path / "led.db"), "h", base, cand, d, p, a, min_n=10, n_boot=300, **kw)


def test_keep_trial_end_to_end(synth_db, probes, tmp_path):
    r = go(synth_db, probes, tmp_path, BAD, GOOD)
    assert r["decision"] == "keep" and r["stage_reached"] == "audit" and set(r["stages"]) == {"dev", "promo", "audit"}
    c = ledger.connect(str(tmp_path / "led.db"))
    t = ledger.trials(c)[0]
    assert t["decision"] == "keep" and t["promo_attempted"] == 1
    assert c.execute("select count(*) from mg_prereg where trial_id=?", (r["trial_id"],)).fetchone()[0] == 1
    assert len(ledger.run_scores(c, r["trial_id"] + ":dev:cand", "mrr_at_10")) == 20


def test_reject_trial_stops_after_dev_and_never_touches_promo(synth_db, probes, tmp_path):
    r = go(synth_db, probes, tmp_path, GOOD, GOOD)
    assert r["decision"] == "reject" and r["stage_reached"] == "dev" and list(r["stages"]) == ["dev"]
    c = ledger.connect(str(tmp_path / "led.db"))
    assert ledger.trials(c)[0]["promo_attempted"] == 0
    assert c.execute("select count(*) from mg_run where run_id like '%:promo:%'").fetchone()[0] == 0


def test_promo_attempts_counted_and_refused_above_limit(synth_db, probes, tmp_path):
    for _ in range(2):
        assert go(synth_db, probes, tmp_path, BAD, GOOD, max_promo_attempts=2)["decision"] == "keep"
    with pytest.raises(loop.Refused):
        go(synth_db, probes, tmp_path, BAD, GOOD, max_promo_attempts=2)
    c = ledger.connect(str(tmp_path / "led.db"))
    ver = c.execute("select bench_version from mg_trial limit 1").fetchone()[0]
    assert ver.startswith("b-") and ledger.promo_attempts(c, ver) == 2  # budget counts per DERIVED bench_version (hash of the probe ids)
    assert ledger.trials(c)[0]["decision"] == "REFUSED_PROMO_BUDGET"


def test_live_db_guard(tmp_path, probes):
    d = tmp_path / "live"; d.mkdir(); (d / "unified.db").write_bytes(b"")
    with pytest.raises(PermissionError):
        loop.trial(str(d / "unified.db"), str(tmp_path / "led.db"), "h", BAD, GOOD, [], None, None)
    assert not os.path.exists(tmp_path / "led.db")


def test_kill_file_blocks(synth_db, probes, tmp_path, monkeypatch):
    (tmp_path / "KILL").write_text("x")
    with pytest.raises(loop.Refused):
        go(synth_db, probes, tmp_path, BAD, GOOD)
    assert not os.path.exists(tmp_path / "led.db")


def test_cli(synth_db, probes, tmp_path, capsys):
    argv = ["trial", "--hypothesis", "h", "--base-retriever", BAD, "--cand-retriever", GOOD, "--db", synth_db, "--ledger", str(tmp_path / "l.db"),
            "--probes-dev", probes[0], "--probes-promo", probes[1], "--probes-audit", probes[2]]
    assert loop.main(argv) == 0 and json.loads(capsys.readouterr().out)["decision"] in ("keep", "insufficient_evidence")
    (tmp_path / "KILL").write_text("x")
    assert loop.main(argv) == 3
