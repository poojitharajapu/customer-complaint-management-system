"""Shared FastAPI dependencies."""

from collections.abc import Generator
from sqlalchemy.orm import Session
from backend.database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Yield one rollback-safe SQLAlchemy session per request."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
