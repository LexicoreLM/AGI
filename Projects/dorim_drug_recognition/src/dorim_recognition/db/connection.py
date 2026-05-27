"""Database connection helpers.

We use psycopg v3 directly for the heavy ingestion / matching paths (COPY,
batched executemany) and SQLAlchemy 2.x for the API layer where ergonomics
matter more than throughput.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from dorim_recognition.core.config import get_settings


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Lazily build a SQLAlchemy engine. Pool sized for a small web service."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.sqlalchemy_url,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            future=True,
        )
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


@contextmanager
def raw_connection(*, autocommit: bool = False) -> Iterator[psycopg.Connection]:
    """Yield a raw psycopg connection. Always returns dict rows by default."""
    settings = get_settings()
    with psycopg.connect(settings.psycopg_url, autocommit=autocommit, row_factory=dict_row) as conn:
        yield conn
