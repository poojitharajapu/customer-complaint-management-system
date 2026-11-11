"""Add the missing Customer ``is_vulnerable`` column to SQLite.

Run from the project root with a verified backup created before migration:

    python -m backend.migrations.add_customer_is_vulnerable data/backups/backup.db

The migration changes only the ``customers`` table and refuses to proceed if
the supplied backup does not match the current database.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from backend.database import SQLITE_DB_PATH
from backend.models.customer import Customer


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


def _counts(connection: sqlite3.Connection, tables: list[str]) -> dict[str, int]:
    return {
        table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        for table in tables
    }


def _schema(connection: sqlite3.Connection, tables: list[str]) -> dict[str, str]:
    return {table: _table_sql(connection, table) for table in tables}


def _verify_backup(database: sqlite3.Connection, backup_path: Path) -> None:
    if not backup_path.is_file():
        raise RuntimeError(f"Backup file does not exist: {backup_path}")
    backup = sqlite3.connect(backup_path.as_uri() + "?mode=ro", uri=True)
    try:
        if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup failed SQLite integrity_check.")
        tables = _tables(database)
        if tables != _tables(backup):
            raise RuntimeError("Backup table list does not match the live database.")
        if _counts(database, tables) != _counts(backup, tables):
            raise RuntimeError("Backup row counts do not match the live database.")
        if _schema(database, tables) != _schema(backup, tables):
            raise RuntimeError("Backup table definitions do not match the live database.")
    finally:
        backup.close()


def migrate(database_path: Path, backup_path: Path) -> int:
    """Add the column, preserving existing customer IDs and records."""
    database = sqlite3.connect(database_path)
    try:
        if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Live database failed SQLite integrity_check.")
        if database.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Live database already contains foreign-key violations.")
        _verify_backup(database, backup_path)

        expected_columns = {column.name for column in Customer.__table__.columns}
        database_columns = {
            row[1]: row for row in database.execute('PRAGMA table_info("customers")')
        }
        missing = expected_columns - set(database_columns)
        extra = set(database_columns) - expected_columns
        if missing - {"is_vulnerable"} or extra:
            raise RuntimeError(
                "Unexpected Customer schema mismatch; "
                f"missing={sorted(missing)}, extra={sorted(extra)}."
            )
        if "is_vulnerable" in database_columns:
            return 0

        table_names = _tables(database)
        before_counts = _counts(database, table_names)
        before_ids = [row[0] for row in database.execute('SELECT id FROM customers ORDER BY id')]
        before_indexes = database.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='index' "
            "AND tbl_name='customers' ORDER BY name"
        ).fetchall()
        before_foreign_keys = database.execute('PRAGMA foreign_key_list("customers")').fetchall()

        database.execute("BEGIN IMMEDIATE")
        try:
            database.execute(
                "ALTER TABLE customers ADD COLUMN is_vulnerable BOOLEAN NOT NULL DEFAULT 0"
            )
            database.commit()
        except Exception:
            database.rollback()
            raise

        after_counts = _counts(database, table_names)
        after_ids = [row[0] for row in database.execute('SELECT id FROM customers ORDER BY id')]
        after_indexes = database.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='index' "
            "AND tbl_name='customers' ORDER BY name"
        ).fetchall()
        after_foreign_keys = database.execute('PRAGMA foreign_key_list("customers")').fetchall()
        column = database.execute(
            'PRAGMA table_info("customers")'
        ).fetchall()[-1]

        if before_counts != after_counts or before_ids != after_ids:
            raise RuntimeError("Customer rows or IDs changed during migration.")
        if before_indexes != after_indexes or before_foreign_keys != after_foreign_keys:
            raise RuntimeError("Customer indexes or foreign keys changed during migration.")
        if column[1] != "is_vulnerable" or column[2].upper() != "BOOLEAN" or column[3] != 1 or str(column[4]) != "0":
            raise RuntimeError(f"Unexpected migrated column definition: {column!r}")
        if database.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Foreign-key violations detected after migration.")
        if database.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite integrity_check failed after migration.")
        return before_counts["customers"]
    finally:
        database.close()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    try:
        count = migrate(SQLITE_DB_PATH, Path(sys.argv[1]).resolve())
    except Exception as error:
        print(f"Migration stopped: {error}", file=sys.stderr)
        return 1
    print(f"Migration completed for {SQLITE_DB_PATH}")
    print(f"Existing customer records preserved: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
