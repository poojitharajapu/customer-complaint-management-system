"""Transactional dataset import tests against an isolated initialized SQLite file."""

from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import create_engine

from backend.import_dataset import import_dataset
from backend.models import Base
from generator.export import export_complete_dataset
from generator.phase8 import generate_complete_dataset


def test_import_is_explicit_transactional_and_rejects_second_import(tmp_path: Path):
    exported = tmp_path / "export"
    export_complete_dataset(generate_complete_dataset("starter"), exported)
    target = tmp_path / "target.db"
    engine = create_engine(f"sqlite:///{target.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()

    with pytest.raises(ValueError, match="confirmation"):
        import_dataset(exported, target, confirmed=False)
    imported = import_dataset(exported, target, confirmed=True)
    assert imported["customers"] == 50
    assert imported["complaints"] == 20
    connection = sqlite3.connect(target)
    assert connection.execute("SELECT COUNT(*) FROM complaints").fetchone()[0] == 20
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    connection.close()

    with pytest.raises(ValueError, match="not empty"):
        import_dataset(exported, target, confirmed=True)
    connection = sqlite3.connect(target)
    assert connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 50
    connection.close()
