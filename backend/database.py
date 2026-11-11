"""
Database configuration and session management module.

Configures SQLite with SQLAlchemy 2.0, enforcing strict foreign key constraints
via SQLite PRAGMA and providing session dependencies for FastAPI.
"""

import sqlite3
from typing import Generator
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session

from backend.config import DATA_DIR, DATABASE_URL
from backend.models.base import Base

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)
SQLITE_DB_PATH = DATA_DIR / "complaints.db"

# Create SQLAlchemy Engine
# check_same_thread=False allows FastAPI multi-threaded request workers to use the DB
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)


# CRITICAL: SQLite does NOT enforce foreign keys by default.
# This listener activates foreign key validation on every SQLite connection.
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """
    Enforces SQLite foreign key constraints and sets WAL (Write-Ahead Logging) mode
    for improved concurrent read/write performance.
    """
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        database_path = cursor.execute("PRAGMA database_list").fetchone()[2]
        if database_path:
            cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


# Session factory for generating database sessions
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a transactional database session per request.
    Automatically closes the session after request completion.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """
    Initializes the database schema by creating all tables defined in models.
    """
    # Import all models to ensure they are registered with Base.metadata
    import backend.models  # noqa: F401
    Base.metadata.create_all(bind=engine)


def check_database_ready(session: Session) -> None:
    """Raise when the configured database cannot execute a simple readiness query."""
    session.execute(text("SELECT 1"))


def get_db_connection() -> sqlite3.Connection:
    """
    Raw SQLite connection helper for legacy/direct query support.
    Configured with foreign keys enabled and Row factory.
    """
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn
