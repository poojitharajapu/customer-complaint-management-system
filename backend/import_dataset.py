"""Explicit transactional importer for previously validated Phase 8 SQL exports."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from backend.database import SQLITE_DB_PATH


TABLE_ORDER = (
    "customers", "categories", "priority_rules", "products", "agents", "orders", "order_items",
    "complaints", "assignments", "complaint_messages", "sla_clocks", "sla_events", "resolutions",
    "complaint_status_history", "complaint_reopen_history", "surveys",
)


def import_dataset(input_dir: str | Path, database_path: str | Path, *, confirmed: bool = False) -> dict[str, int]:
    """Validate in isolation, then copy all rows atomically into an empty initialized DB."""
    if not confirmed:
        raise ValueError("Import requires explicit confirmation (--confirm).")
    source_dir, target_path = Path(input_dir), Path(database_path)
    summary_path, sql_path = source_dir / "validation_summary.json", source_dir / "seed.sql"
    if not summary_path.is_file() or not sql_path.is_file():
        raise ValueError("Input must contain validation_summary.json and seed.sql.")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if isinstance(summary, list):
        summary = summary[0] if summary else {}
    if summary.get("failed_checks") != 0:
        raise ValueError("Refusing to import a dataset whose validation report has failures.")

    source = sqlite3.connect(":memory:")
    source.execute("PRAGMA foreign_keys=ON")
    source.executescript(sql_path.read_text(encoding="utf-8"))
    if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        source.close(); raise ValueError("Generated SQL export failed SQLite integrity_check.")
    if source.execute("PRAGMA foreign_key_check").fetchall():
        source.close(); raise ValueError("Generated SQL export contains foreign-key violations.")

    if not target_path.exists():
        source.close(); raise FileNotFoundError(f"Target database does not exist: {target_path}. Initialize it explicitly first.")
    target = sqlite3.connect(target_path, timeout=30)
    counts: dict[str, int] = {}
    try:
        target.execute("PRAGMA foreign_keys=ON")
        target.execute("PRAGMA busy_timeout=5000")
        target.execute("BEGIN IMMEDIATE")
        target_tables = {row[0] for row in target.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = [name for name in TABLE_ORDER if name not in target_tables]
        if missing:
            raise ValueError(f"Target schema is missing tables: {', '.join(missing)}. Run the explicit database initializer first.")
        occupied = [name for name in TABLE_ORDER if target.execute(f'SELECT 1 FROM "{name}" LIMIT 1').fetchone()]
        if occupied:
            raise ValueError(f"Import target is not empty; refusing possible duplicate or mixed import ({', '.join(occupied[:5])}).")

        for table in TABLE_ORDER:
            source_columns = [x[1] for x in source.execute(f'PRAGMA table_info("{table}")')]
            target_columns = {x[1] for x in target.execute(f'PRAGMA table_info("{table}")')}
            columns = [name for name in source_columns if name in target_columns]
            if len(columns) != len(source_columns):
                raise ValueError(f"Target table {table} does not match the generated model schema.")
            rows = source.execute(f'SELECT {", ".join(chr(34)+c+chr(34) for c in columns)} FROM "{table}"').fetchall()
            if rows:
                marks = ", ".join("?" for _ in columns)
                names = ", ".join(f'"{x}"' for x in columns)
                target.executemany(f'INSERT INTO "{table}" ({names}) VALUES ({marks})', rows)
            counts[table] = len(rows)
        if target.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Imported rows failed foreign_key_check.")
        target.commit()
    except Exception:
        target.rollback()
        raise
    finally:
        source.close(); target.close()
    return counts


def main() -> int:
    """Expose the import only as an explicit command with a confirmation switch."""
    parser = argparse.ArgumentParser(description="Import a validated Phase 8 dataset transactionally.")
    parser.add_argument("--input", default="data/generated", help="Directory containing the Phase 8 export.")
    parser.add_argument("--database", default=str(SQLITE_DB_PATH), help="Initialized target SQLite database.")
    parser.add_argument("--confirm", action="store_true", help="Confirm that the selected empty database may receive this dataset.")
    args = parser.parse_args()
    counts = import_dataset(args.input, args.database, confirmed=args.confirm)
    print(f"Imported {sum(counts.values())} records in one transaction:")
    for table, count in counts.items(): print(f"  {table}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
