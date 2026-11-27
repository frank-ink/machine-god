from contextlib import closing
import sqlite3

import pytest

import mg_loop
import mg_report


def test_report_window_and_held_out_gain(tmp_path):
    path = tmp_path / "unified.db"
    now = 1_000_000
    rows = [
        ("old", "", "spec", 1.0, None, "adopted", now - mg_report.WEEK - 1),
        ("a", "[tpl:recall_lane {}]", "spec", 0.9, None, "pass", now - 7200),
        ("a-AUDIT", "[tpl:recall_lane {}]", "spec", 0.1, None, "adopted", now - 3600),
        ("b", "[tpl:rl2_hparam {}]", "spec", 1.0, '{"held_out_delta": 0.2}', "adopted", now),
        ("c", "", "spec", 1.0, None, "adopted", now),
        ("a-AUDIT-WATCH", "", "watch", 10.0, None, "reverted", now),
        ("b-WATCH", "", "watch", None, None, "confirmed", now),
    ]
    with closing(mg_loop.connect(path)) as db, db:
        db.executemany(
            "INSERT INTO mg_trial (trial_id, hypothesis, base_ref, delta, guards_json, decision, ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)", rows,
        )
    before = path.read_bytes()
    result = mg_report.report(path, now)
    assert result["trials_per_7_days"] == 4
    assert result["acceptance_rate"] == 0.75
    assert result["revert_rate"] == 1 / 3
    assert result["compute_hours"] == 2
    assert result["held_out_delta_per_compute_hour"] == pytest.approx(0.15)
    assert result["adoptions_with_held_out_delta"] == 2
    assert result["per_template_counts"] == {"recall_lane": 2, "rl2_hparam": 1, "unknown": 1}
    assert path.read_bytes() == before


def test_report_missing_ledger(tmp_path):
    path = tmp_path / "absent.db"
    result = mg_report.report(path, 1_000_000)
    assert result["trials_per_7_days"] == 0
    assert result["acceptance_rate"] is None
    assert result["revert_rate"] is None
    assert result["held_out_delta_per_compute_hour"] is None
    assert not path.exists()
