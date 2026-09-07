"""AEGIS-Marine: Database Engine & Session Factory.

Provides SQLAlchemy engine, session maker, and session context managers.
"""

from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://aegis:aegis_secure_password@localhost:5432/aegis_marine",
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI & task dependency yielding a transactional DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
