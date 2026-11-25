# SPDX-License-Identifier: Apache-2.0
"""Guarantees of migrate_to_english.py on a miniature old/new schema pair."""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = """
CREATE TABLE ziel(id INTEGER PRIMARY KEY, titel TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('offen','erledigt')) DEFAULT 'offen');
CREATE INDEX ziel_status_idx ON ziel(status);
CREATE VIEW ziel_offen AS SELECT titel FROM ziel WHERE status='offen';
CREATE VIRTUAL TABLE ziel_fts USING fts5(titel, content='ziel', content_rowid='id');
CREATE TABLE star_konfig(schluessel TEXT PRIMARY KEY, wert TEXT);
"""
NEW = OLD.replace("ziel_status_idx", "goal_status_idx").replace("ziel_offen", "goal_open") \
    .replace("ziel_fts", "goal_fts").replace("ziel", "goal").replace("titel", "title") \
    .replace("'offen'", "'open'").replace("'erledigt'", "'done'") \
    .replace("star_konfig", "star_config").replace("schluessel", "key").replace("wert", "value")
MAP = {"tables": {"ziel": "goal", "ziel_fts": "goal_fts", "star_konfig": "star_config"},
       "columns": {"ziel": {"titel": "title"}, "star_konfig": {"schluessel": "key", "wert": "value"}},
       "indexes": {"ziel_status_idx": "goal_status_idx"}, "views": {"ziel_offen": "goal_open"},
       "triggers": {}, "value_map": {"goal": {"status": {"offen": "open", "erledigt": "done"}}},
       "config_keys": {"abruf.x": "recall.x"}, "config_key_prefixes": {}, "config_key_suffixes": {}}


def migrate(db: Path, tmp: Path) -> subprocess.CompletedProcess:
    (tmp / "new.sql").write_text(NEW, encoding="utf-8")
    (tmp / "map.json").write_text(json.dumps(MAP), encoding="utf-8")
    return subprocess.run([sys.executable, "-I", str(HERE / "migrate_to_english.py"), str(db), "--no-backup",
                           "--map", str(tmp / "map.json"), "--schema", str(tmp / "new.sql")],
                          capture_output=True, text=True, check=False)


def test_old_database_becomes_new_schema_with_data_mapped_and_rerun_is_noop(tmp_path):
    db = tmp_path / "u.db"
    con = sqlite3.connect(db)
    con.executescript(OLD)
    con.execute("INSERT INTO ziel(titel, status) VALUES ('a','offen'), ('b','erledigt')")
    con.execute("INSERT INTO ziel_fts(ziel_fts) VALUES('rebuild')")
    con.execute("INSERT INTO star_konfig VALUES ('abruf.x','1')")
    con.commit()
    con.close()
    assert migrate(db, tmp_path).returncode == 0
    con = sqlite3.connect(db)
    assert con.execute("SELECT title, status FROM goal ORDER BY id").fetchall() == [("a", "open"), ("b", "done")]
    assert con.execute("SELECT key FROM star_config").fetchall() == [("recall.x",)]
    assert con.execute("SELECT rowid FROM goal_fts WHERE goal_fts MATCH 'a'").fetchall() == [(1,)]
    assert con.execute("SELECT title FROM goal_open").fetchall() == [("a",)]
    assert "'offen'" not in con.execute("SELECT sql FROM sqlite_master WHERE name='goal'").fetchone()[0]
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
    assert {"goal_status_idx", "goal_open"} <= names and not {"ziel", "ziel_status_idx", "ziel_offen"} & names
    before = list(con.iterdump())
    con.close()
    assert migrate(db, tmp_path).returncode == 0
    assert list(sqlite3.connect(db).iterdump()) == before
