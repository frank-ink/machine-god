# SPDX-License-Identifier: Apache-2.0
"""Migrate an existing unified.db from the German schema names to the English ones.

Reads the old->new map `docs/zero/rename_map.json` (sections `tables`, `columns`,
`indexes`, `views`, `triggers`, `value_map`, `config_keys`, `config_key_prefixes`,
`config_key_suffixes`) and the target schema file(s) (`schema.sql`, plugin
`schema_empty.sql`). Idempotent: every step checks the current state first, so a
second run (or a run on a database that is already English) changes nothing.

Order of operations (all inside one transaction):
  1. drop views / triggers / indexes that exist under an old or new name
     (they are recreated from the target schema in step 6)
  2. rename columns (old table name or new table name, whichever exists)
  3. rename tables (FTS5 shadow tables follow their virtual table)
  4. rebuild tables whose CHECK/DEFAULT string literals differ from the target
     schema (SQLite cannot alter CHECK), mapping enum values on the way
  5. UPDATE enum values in tables that were not rebuilt; rename config keys
  6. recreate indexes / views / triggers from the target schema

A backup (SQLite online-backup API) is written next to the database before any
change unless `--no-backup` is given. `--emit-sql FILE` runs the migration on an
in-memory COPY of the database and writes the exact statement sequence to FILE;
the original is not touched.

Not migratable: JSON payload keys stored inside text blobs (e.g. durable_memory
payloads) and free-text values; see docs/zero/RENAME_MAP.md section "Not migrated".
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

DEFAULT_MAP = Path(__file__).resolve().parents[2] / "docs" / "zero" / "rename_map.json"
DEFAULT_SCHEMA = Path(__file__).resolve().parent / "schema.sql"


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def strip_comments(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def literals(sql: str) -> list[str]:
    return re.findall(r"'((?:[^']|'')*)'", strip_comments(sql))


class Migrator:
    def __init__(self, con: sqlite3.Connection, mapping: dict, targets: sqlite3.Connection):
        self.con = con
        self.map = mapping
        self.targets = targets
        self.emit = False
        self.log: list[str] = []
        self.warnings: list[str] = []

    # -- helpers -------------------------------------------------------
    def run(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        self.log.append(sql.rstrip(";") + ";" if not params else f"{sql};  -- {params!r}")
        return self.con.execute(sql, params)

    def has_rows(self, sql: str) -> bool:
        """With --emit-sql every UPDATE is emitted (the script must work on any database); live runs skip no-ops."""
        return self.emit or self.con.execute(f"SELECT EXISTS({sql})").fetchone()[0] == 1

    def objects(self, kind: str) -> dict[str, str | None]:
        return {r[0]: r[1] for r in self.con.execute("SELECT name, sql FROM sqlite_master WHERE type=?", (kind,))}

    def tables(self) -> dict[str, str | None]:
        return self.objects("table")

    def columns(self, table: str) -> list[str]:
        return [r[1] for r in self.con.execute(f"PRAGMA table_info({q(table)})")]

    def is_virtual(self, sql: str | None) -> bool:
        return bool(sql) and sql.lstrip().upper().startswith("CREATE VIRTUAL")

    def target_sql(self, kind: str, name: str) -> str | None:
        row = self.targets.execute("SELECT sql FROM sqlite_master WHERE type=? AND name=?", (kind, name)).fetchone()
        return row[0] if row else None

    def columns_of_target(self, table: str) -> list[str]:
        return [r[1] for r in self.targets.execute(f"PRAGMA table_info({q(table)})")]

    # -- steps ---------------------------------------------------------
    def drop_dependents(self) -> None:
        """Drop old-named indexes/views/triggers, and views/triggers whose text differs from the target."""
        for kind, key in (("view", "views"), ("trigger", "triggers"), ("index", "indexes")):
            renamed = self.map.get(key, {})
            existing = self.objects(kind)
            for name, sql in sorted(existing.items()):
                if sql is None:  # automatic index
                    continue
                stale = name in renamed
                if kind != "index" and not stale:
                    target = self.target_sql(kind, name)
                    stale = target is not None and " ".join(target.split()) != " ".join(sql.split())
                if stale:
                    self.run(f"DROP {kind.upper()} IF EXISTS {q(name)}")

    def rename_columns(self) -> None:
        tables = self.tables()
        for old_table, cols in self.map["columns"].items():
            new_table = self.map["tables"].get(old_table, old_table)
            table = old_table if old_table in tables else new_table if new_table in tables else None
            if table is None or self.is_virtual(tables[table]) or self.is_shadow(table):
                continue
            present = self.columns(table)
            for old, new in cols.items():
                if old != new and old in present and new not in present:
                    self.run(f"ALTER TABLE {q(table)} RENAME COLUMN {q(old)} TO {q(new)}")
                    present = self.columns(table)

    def rename_tables(self) -> None:
        for old, new in self.map["tables"].items():
            tables = self.tables()
            if old != new and old in tables and new not in tables:
                self.run(f"ALTER TABLE {q(old)} RENAME TO {q(new)}")

    def is_shadow(self, table: str) -> bool:
        """True for the backing tables of a virtual (FTS5) table; SQLite owns those."""
        return any(self.is_virtual(sql) and table.startswith(name + "_") for name, sql in self.tables().items())

    def needs_rebuild(self, table: str, sql: str | None) -> str | None:
        """Target CREATE TABLE text if the string literals (CHECK / DEFAULT) differ, else None."""
        if not sql or self.is_virtual(sql) or self.is_shadow(table):
            return None
        target = self.target_sql("table", table)
        if target is None or literals(sql) == literals(target):
            return None
        extra = set(self.columns(table)) - set(self.columns_of_target(table))
        if extra:
            self.warnings.append(f"{table}: not rebuilt, live columns not in target schema: {sorted(extra)}")
            return None
        return target

    def case_expr(self, table: str, col: str) -> str:
        values = self.map.get("value_map", {}).get(table, {}).get(col)
        if not values:
            return q(col)
        whens = " ".join(f"WHEN {lit(o)} THEN {lit(n)}" for o, n in values.items())
        return f"CASE {q(col)} {whens} ELSE {q(col)} END"

    def rebuild(self, table: str, target_sql: str) -> None:
        tmp = f"{table}__en_new"
        create = re.sub(r"(?i)^(\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)\"?%s\"?" % re.escape(table),
                        lambda m: f"{m.group(1)}{q(tmp)}", target_sql, count=1)
        live = set(self.columns(table))
        cols = [c for c in self.columns_of_target(table) if c in live]
        select = ", ".join(self.case_expr(table, c) for c in cols)
        before = self.con.execute(f"SELECT COUNT(*) FROM {q(table)}").fetchone()[0]
        self.run("PRAGMA legacy_alter_table=ON")
        self.run(create)
        self.run(f"INSERT INTO {q(tmp)} ({', '.join(q(c) for c in cols)}) SELECT {select} FROM {q(table)}")
        after = self.con.execute(f"SELECT COUNT(*) FROM {q(tmp)}").fetchone()[0]
        if before != after:
            raise RuntimeError(f"{table}: row count {before} -> {after}")
        self.run(f"DROP TABLE {q(table)}")
        self.run(f"ALTER TABLE {q(tmp)} RENAME TO {q(table)}")
        self.run("PRAGMA legacy_alter_table=OFF")

    def rebuild_virtual(self, table: str, target_sql: str) -> None:
        """FTS5 column / content-table changes cannot be ALTERed: recreate and refill."""
        keep = f"{table}__en_keep"
        external = "content=" in target_sql.replace(" ", "")
        if not external:
            self.run(f"CREATE TEMP TABLE {q(keep)} AS SELECT rowid AS rid, * FROM {q(table)}")
        self.run(f"DROP TABLE {q(table)}")
        self.run(target_sql)
        if external:
            self.run(f"INSERT INTO {q(table)}({q(table)}) VALUES('rebuild')")
        else:
            cols = ", ".join(q(c) for c in self.columns_of_target(table))
            self.run(f"INSERT INTO {q(table)}(rowid, {cols}) SELECT * FROM {q(keep)}")
            self.run(f"DROP TABLE {q(keep)}")

    def virtual_changes(self) -> None:
        for table, sql in list(self.tables().items()):
            if not self.is_virtual(sql):
                continue
            target = self.target_sql("table", table)
            if target and " ".join(target.split()) != " ".join(sql.split()):
                self.rebuild_virtual(table, target)

    def rebuild_and_values(self) -> None:
        self.virtual_changes()
        rebuilt: set[str] = set()
        for table, sql in list(self.tables().items()):
            target = self.needs_rebuild(table, sql)
            if target:
                self.rebuild(table, target)
                rebuilt.add(table)
        tables = self.tables()
        for table, cols in self.map.get("value_map", {}).items():
            if table in rebuilt or table not in tables or self.is_virtual(tables[table]):
                continue
            present = self.columns(table)
            for col, values in cols.items():
                if col not in present:
                    continue
                for old, new in values.items():
                    if self.has_rows(f"SELECT 1 FROM {q(table)} WHERE {q(col)}={lit(old)}"):
                        self.run(f"UPDATE {q(table)} SET {q(col)}={lit(new)} WHERE {q(col)}={lit(old)}")

    def config_keys(self) -> None:
        table = "star_config"
        if table not in self.tables() or "key" not in self.columns(table):
            return
        for old, new in self.map.get("config_keys", {}).items():
            if self.emit or (self.con.execute(f"SELECT 1 FROM {q(table)} WHERE key=?", (old,)).fetchone() and
                             not self.con.execute(f"SELECT 1 FROM {q(table)} WHERE key=?", (new,)).fetchone()):
                self.run(f"UPDATE {q(table)} SET key={lit(new)} WHERE key={lit(old)}")
        for old, new in self.map.get("config_key_prefixes", {}).items():
            if self.has_rows(f"SELECT 1 FROM {q(table)} WHERE substr(key, 1, {len(old)})={lit(old)}"):
                self.run(f"UPDATE {q(table)} SET key={lit(new)} || substr(key, {len(old) + 1}) "
                         f"WHERE substr(key, 1, {len(old)})={lit(old)}")
        for old, new in self.map.get("config_key_suffixes", {}).items():
            if self.has_rows(f"SELECT 1 FROM {q(table)} WHERE substr(key, -{len(old)})={lit(old)}"):
                    self.run(f"UPDATE {q(table)} SET key=substr(key, 1, length(key)-{len(old)}) || {lit(new)} "
                         f"WHERE substr(key, -{len(old)})={lit(old)}")

    def recreate(self) -> None:
        tables = self.tables()
        for kind in ("index", "view", "trigger"):
            existing = self.objects(kind)
            for name, tbl, sql in self.targets.execute(
                    "SELECT name, tbl_name, sql FROM sqlite_master WHERE type=? AND sql IS NOT NULL ORDER BY rowid",
                    (kind,)).fetchall():
                if name in existing or (tbl not in tables and kind != "view"):
                    continue
                self.run("SAVEPOINT en_obj")
                try:
                    self.run(sql)
                except sqlite3.Error as exc:
                    self.run("ROLLBACK TO en_obj")
                    self.warnings.append(f"{kind} {name}: {exc}")
                self.run("RELEASE en_obj")

    def migrate(self) -> None:
        self.run("PRAGMA foreign_keys=OFF")
        self.run("BEGIN")
        fk_before = len(self.con.execute("PRAGMA foreign_key_check").fetchall())
        try:
            self.drop_dependents()
            self.rename_columns()
            self.rename_tables()
            self.rebuild_and_values()
            self.config_keys()
            self.recreate()
            bad = self.con.execute("PRAGMA foreign_key_check").fetchall()
            if len(bad) > fk_before:  # violations that already existed are not ours to fix
                raise RuntimeError(f"foreign_key_check: {fk_before} -> {len(bad)} violations: {bad[:5]}")
            self.run("COMMIT")
        except Exception:
            self.con.execute("ROLLBACK")
            raise


def load_targets(paths: list[Path]) -> sqlite3.Connection:
    targets = sqlite3.connect(":memory:")
    for path in paths:
        scratch = sqlite3.connect(":memory:")
        scratch.executescript(path.read_text(encoding="utf-8"))
        for name, sql in scratch.execute("SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY rowid"):
            if not targets.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone():
                targets.execute(sql)  # first schema file that defines an object wins
        scratch.close()
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("db", help="path of the database to migrate")
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--schema", type=Path, action="append", help="target schema file (repeatable)")
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("--emit-sql", type=Path, help="run on an in-memory copy and write the statements here")
    args = parser.parse_args(argv)

    mapping = json.loads(args.map.read_text(encoding="utf-8"))
    targets = load_targets(args.schema or [DEFAULT_SCHEMA])
    src = sqlite3.connect(args.db)
    src.isolation_level = None

    if args.emit_sql:
        work = sqlite3.connect(":memory:")
        work.isolation_level = None
        src.backup(work)
        src.close()
    else:
        if not args.no_backup:
            backup = f"{args.db}.pre-english-{time.strftime('%Y%m%dT%H%M%S')}"
            dest = sqlite3.connect(backup)
            src.backup(dest)
            dest.close()
            print(f"backup: {backup}")
        work = src

    migrator = Migrator(work, mapping, targets)
    migrator.emit = bool(args.emit_sql)
    migrator.migrate()
    for warning in migrator.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if args.emit_sql:
        args.emit_sql.write_text("-- generated by migrate_to_english.py --emit-sql from a database holding the complete old schema.\n"
                                 "-- Reference log: not guarded against re-runs; use migrate_to_english.py itself for idempotent migration.\n" + "\n".join(migrator.log) + "\n",
                                 encoding="utf-8")
    print(f"statements: {len(migrator.log)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
