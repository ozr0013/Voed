"""SQLAlchemy engine + session setup (SQLite, local file)."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

engine = create_engine(
    settings.db_url,
    connect_args={"check_same_thread": False},  # FastAPI uses threads
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    # Import models so they register on Base.metadata before create_all.
    from . import models  # noqa: F401

    Base.metadata.create_all(engine)
    _migrate()


# Lightweight, additive migrations for the local SQLite file. `create_all` only
# creates missing tables — it never adds columns to existing ones — so newly
# introduced nullable columns are backfilled here for databases created before
# the column existed. (SQLite supports ADD COLUMN.)
_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "projects": {"muted_ranges": "JSON"},
}


def _migrate() -> None:
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    for table, columns in _ADDITIVE_COLUMNS.items():
        if table not in existing_tables:
            continue
        have = {c["name"] for c in insp.get_columns(table)}
        for name, sql_type in columns.items():
            if name not in have:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
