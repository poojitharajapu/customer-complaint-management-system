"""Deterministically export complete datasets as CSV, JSON, and SQLite SQL."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.dialects import sqlite
from sqlalchemy.schema import CreateTable

from backend.models import Base
from generator.anomalies import anomalies_as_dicts
from generator.config import GENERATOR_OUTPUT_DIR
from generator.ground_truth import ground_truth_as_dicts


def _value(value: Any) -> Any:
    """Convert a model scalar into stable JSON/CSV-safe ISO or decimal text."""
    if isinstance(value, datetime):
        dt = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    if isinstance(value, date): return value.isoformat()
    if isinstance(value, Decimal): return format(value, "f")
    if isinstance(value, (str, int, float, bool)) or value is None: return value
    return str(value)


def _row(model: Any) -> dict[str, Any]:
    """Serialize mapped columns and explicit non-persisted generator metadata."""
    row = {column.name: _value(getattr(model, column.name, None)) for column in model.__table__.columns}
    # Relationship foreign keys are known before a session flushes ORM objects.
    for attr in ("customer", "product", "order", "category", "complaint", "agent", "resolved_by_agent", "sla_clock", "previous_resolution"):
        related = getattr(model, attr, None)
        fk = f"{attr}_id"
        if related is not None and fk in row: row[fk] = getattr(related, "id", None)
    if hasattr(model, "is_safety_related"): row["is_safety_related"] = bool(model.is_safety_related)
    if hasattr(model, "payment_status"): row["payment_status"] = model.payment_status
    if hasattr(model, "delivery_status"): row["delivery_status"] = model.delivery_status
    for attr in ("priority_reason",):
        if hasattr(model, attr): row[attr] = getattr(model, attr)
    return row


def dataset_tables(dataset: Any) -> dict[str, list[dict[str, Any]]]:
    """Produce stable table-like exports for every requested entity."""
    p6, p7 = dataset.phase7.phase6, dataset.phase7
    categories = {}
    for product in p6.products:
        if product.category: categories[product.category.id] = product.category
    for complaint in p6.complaints:
        if complaint.category: categories[complaint.category.id] = complaint.category
    return {
        "customers": [_row(x) for x in p6.customers],
        "products": [_row(x) for x in p6.products],
        "categories": [_row(x) for x in sorted(categories.values(), key=lambda x: x.id)],
        "priority_rules": [_row(x) for x in p6.priority_rules],
        "orders": [_row(x) for x in p6.orders],
        "order_items": [_row(x) for x in (item for order in p6.orders for item in order.items)],
        "complaints": [_row(x) for x in p6.complaints],
        "agents": [_row(x) for x in p6.agents],
        "assignments": [_row(x) for x in p6.assignments],
        "complaint_messages": [_row(x) for x in p6.messages],
        "sla_clocks": [_row(x) for x in p6.sla_clocks],
        "sla_events": [_row(x) for x in p6.sla_events],
        "resolutions": [_row(x) for x in p7.resolutions],
        "complaint_status_history": [_row(x) for x in (h for c in p6.complaints for h in c.status_history)],
        "complaint_reopen_history": [_row(x) for x in (h for c in p6.complaints for h in c.reopen_history)],
        "surveys": [_row(x) for x in p7.surveys],
        "ground_truth": ground_truth_as_dicts(dataset.ground_truth),
        "anomalies": anomalies_as_dicts(dataset.anomalies),
        "validation_summary": [dataset.validation.to_dict()],
    }


def _sql_literal(value: Any) -> str:
    """Quote values as SQLite SQL literals without interpolating model objects."""
    if value is None: return "NULL"
    if isinstance(value, bool): return "1" if value else "0"
    if isinstance(value, (int, float)): return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _csv_value(value: Any) -> Any:
    """Encode nested JSON-like values unambiguously while retaining scalar text."""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if value is None: return ""
    if isinstance(value, bool): return "true" if value else "false"
    return value


def _sql_table_map(dataset: Any) -> list[tuple[str, Any, list[dict[str, Any]]]]:
    """Map export entity collections to ORM tables in dependency order."""
    p6, p7 = dataset.phase7.phase6, dataset.phase7
    pairs = [
        ("customers", p6.customers), ("categories", sorted({x.category.id:x.category for x in p6.products + p6.complaints}.values(), key=lambda x:x.id)),
        ("priority_rules", p6.priority_rules), ("products", p6.products), ("agents", p6.agents), ("orders", p6.orders), ("order_items", [i for o in p6.orders for i in o.items]),
        ("complaints", p6.complaints), ("assignments", p6.assignments), ("complaint_messages", p6.messages),
        ("sla_clocks", p6.sla_clocks), ("sla_events", p6.sla_events), ("resolutions", p7.resolutions),
        ("complaint_status_history", [h for c in p6.complaints for h in c.status_history]),
        ("complaint_reopen_history", [h for c in p6.complaints for h in c.reopen_history]), ("surveys", p7.surveys),
    ]
    model_by_table = {table.name: table for table in Base.metadata.sorted_tables}
    return [(table_name, model_by_table[table_name], [_row(x) for x in records]) for table_name, records in pairs]


def _write_sql(dataset: Any, path: Path) -> None:
    """Write schema plus data inserts as an executable SQLite seed script."""
    lines = ["PRAGMA foreign_keys=ON;", "BEGIN TRANSACTION;"]
    for table_name, table, rows in _sql_table_map(dataset):
        lines.append(str(CreateTable(table).compile(dialect=sqlite.dialect())).strip() + ";")
        columns = [column.name for column in table.columns]
        for row in rows:
            selected = [(name, row.get(name)) for name in columns if row.get(name) is not None]
            names = ", ".join(f'"{name}"' for name, _ in selected)
            values = ", ".join(_sql_literal(value) for _, value in selected)
            lines.append(f'INSERT INTO "{table_name}" ({names}) VALUES ({values});')
    lines.extend(["COMMIT;", ""])
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def export_complete_dataset(dataset: Any, output_dir: str | Path | None = None) -> dict[str, str]:
    """Write per-entity CSV/JSON, a SQL seed, and SHA-256 manifest; return checksums."""
    root = Path(output_dir) if output_dir is not None else GENERATOR_OUTPUT_DIR
    root.mkdir(parents=True, exist_ok=True)
    tables = dataset_tables(dataset)
    files: list[Path] = []
    for name, rows in tables.items():
        json_path = root / f"{name}.json"
        json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        files.append(json_path)
        csv_path = root / f"{name}.csv"
        fields = sorted({key for row in rows for key in row})
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            if fields:
                writer.writeheader()
                writer.writerows([{key: _csv_value(value) for key, value in row.items()} for row in rows])
        files.append(csv_path)
    sql_path = root / "seed.sql"
    _write_sql(dataset, sql_path)
    files.append(sql_path)
    checksums = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files, key=lambda p:p.name)}
    checksum_path = root / "checksums.sha256.json"
    checksum_path.write_text(json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return {**checksums, checksum_path.name: hashlib.sha256(checksum_path.read_bytes()).hexdigest()}
