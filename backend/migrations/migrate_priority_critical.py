"""Safely replace the persisted ``Urgent`` priority with ``Critical``.

Run from the project root with the path to a verified pre-migration backup:

    python -m backend.migrations.migrate_priority_critical data/backups/backup.db

The migration requires the backup to have the same table names, row counts,
and table definitions as the target database before it starts.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from backend.database import SQLITE_DB_PATH


TARGETS = {
    "categories": "default_priority",
    "complaints": "priority",
    "priority_rules": "target_priority",
}
PRIORITY_CHECKS = {
    "categories": "chk_category_default_priority",
    "complaints": "chk_complaint_priority",
    "priority_rules": "chk_priority_rule_target",
}


def _tables(connection: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def _table_sql(connection: sqlite3.Connection, table: str) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if row is None or row[0] is None:
        raise RuntimeError(f"Required table {table!r} is missing.")
    return row[0]


def _row_counts(connection: sqlite3.Connection, tables: list[str]) -> dict[str, int]:
    return {
        table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        for table in tables
    }


def _index_sql(connection: sqlite3.Connection, table: str) -> list[str]:
    return [
        row[0]
        for row in connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? "
            "AND sql IS NOT NULL ORDER BY name",
            (table,),
        )
    ]


def _check_backup(database: sqlite3.Connection, backup_path: Path) -> None:
    if not backup_path.is_file():
        raise RuntimeError(f"Backup file does not exist: {backup_path}")
    backup = sqlite3.connect(backup_path.as_uri() + "?mode=ro", uri=True)
    try:
        if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup failed SQLite integrity_check.")
        tables = _tables(database)
        if tables != _tables(backup):
            raise RuntimeError("Backup table list does not match the live database.")
        if _row_counts(database, tables) != _row_counts(backup, tables):
            raise RuntimeError("Backup row counts do not match the live database.")
        for table in tables:
            if _table_sql(database, table) != _table_sql(backup, table):
                raise RuntimeError(f"Backup schema for {table!r} does not match.")
    finally:
        backup.close()


def migrate(database_path: Path, backup_path: Path) -> dict[str, int]:
    """Rebuild the three constrained tables transactionally and return counts."""
    database = sqlite3.connect(database_path)
    database.row_factory = sqlite3.Row
    try:
        if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Live database failed SQLite integrity_check.")
        if database.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Live database already contains foreign-key violations.")
        _check_backup(database, backup_path)

        before_counts = _row_counts(database, _tables(database))
        migrated_counts: dict[str, int] = {}
        # SQLite requires foreign-key enforcement to be disabled before a rebuild.
        database.execute("PRAGMA foreign_keys=OFF")
        database.execute("BEGIN IMMEDIATE")
        try:
            for table, priority_column in TARGETS.items():
                original_sql = _table_sql(database, table)
                constraint = PRIORITY_CHECKS[table]
                already_updated = (
                    "Critical" in original_sql and "Urgent" not in original_sql
                )
                if already_updated:
                    migrated_counts[table] = 0
                    continue
                if "Urgent" not in original_sql or constraint not in original_sql:
                    raise RuntimeError(
                        f"Unexpected priority constraint in {table}; refusing to rebuild."
                    )

                columns = [row[1] for row in database.execute(f'PRAGMA table_info("{table}")')]
                if not columns or priority_column not in columns:
                    raise RuntimeError(f"Unexpected columns in {table}; refusing to rebuild.")
                column_sql = ", ".join(f'"{name}"' for name in columns)
                copy_expressions = [
                    f'CASE WHEN "{name}" = \'Urgent\' THEN \'Critical\' ELSE "{name}" END'
                    if name == priority_column
                    else f'"{name}"'
                    for name in columns
                ]
                original_indexes = _index_sql(database, table)
                temporary_table = f"__critical_migration_{table}"
                temporary_sql = original_sql.replace(
                    f"CREATE TABLE {table}", f"CREATE TABLE {temporary_table}", 1
                )
                if temporary_sql == original_sql:
                    raise RuntimeError(f"Could not safely rewrite CREATE TABLE for {table}.")
                temporary_sql = temporary_sql.replace("'Urgent'", "'Critical'")
                old_count = database.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                urgent_count = database.execute(
                    f'SELECT COUNT(*) FROM "{table}" WHERE "{priority_column}" = \'Urgent\''
                ).fetchone()[0]

                database.execute(temporary_sql)
                database.execute(
                    f'INSERT INTO "{temporary_table}" ({column_sql}) '
                    f'SELECT {", ".join(copy_expressions)} FROM "{table}"'
                )
                new_count = database.execute(
                    f'SELECT COUNT(*) FROM "{temporary_table}"'
                ).fetchone()[0]
                if old_count != new_count:
                    raise RuntimeError(f"Row count changed while rebuilding {table}.")
                database.execute(f'DROP TABLE "{table}"')
                database.execute(f'ALTER TABLE "{temporary_table}" RENAME TO "{table}"')
                for index_statement in original_indexes:
                    database.execute(index_statement)
                migrated_counts[table] = urgent_count

            violations = database.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError(f"Foreign-key violations after rebuild: {violations!r}")
            if before_counts != _row_counts(database, _tables(database)):
                raise RuntimeError("Table row counts changed during migration.")
            database.commit()
        except Exception:
            database.rollback()
            raise
        finally:
            database.execute("PRAGMA foreign_keys=ON")

        if database.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise RuntimeError("Could not re-enable foreign-key enforcement.")
        return migrated_counts
    finally:
        database.close()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    try:
        counts = migrate(SQLITE_DB_PATH, Path(sys.argv[1]).resolve())
    except Exception as error:
        print(f"Migration stopped: {error}", file=sys.stderr)
        return 1
    print(f"Migration completed for {SQLITE_DB_PATH}")
    print(f"Critical priority rows by table: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
