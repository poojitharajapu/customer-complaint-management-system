"""
Database Initialization Script.

Creates all database tables, enables foreign key enforcement,
and verifies schema structure.

Usage:
    python -m backend.init_db
"""

import sys
from sqlalchemy import inspect
from backend.database import engine, init_db, SQLITE_DB_PATH


def run_init() -> bool:
    """
    Runs schema creation and prints table summary.
    """
    print(f"Initializing SQLite database at: {SQLITE_DB_PATH}")
    try:
        init_db()
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        print(f"\n[SUCCESS] Successfully initialized database schema!")
        print(f"Total tables created: {len(tables)}\n")
        print("Created Tables and Columns:")
        print("-" * 50)
        for table in sorted(tables):
            columns = inspector.get_columns(table)
            foreign_keys = inspector.get_foreign_keys(table)
            print(f"- {table:28} ({len(columns):2d} columns, {len(foreign_keys):2d} foreign keys)")
        print("-" * 50)
        return True
    except Exception as e:
        print(f"\n[ERROR] Failed to initialize database: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    success = run_init()
    sys.exit(0 if success else 1)

