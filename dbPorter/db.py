import os
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Text
from sqlalchemy.engine import Engine
from .utils.constants import _MIGRATION_LOG_TABLE

MIGRATION_LOG_TABLE = _MIGRATION_LOG_TABLE

def get_engine(db_url: str) -> Engine:
    return create_engine(db_url, future=True)

def init_metadata(engine: Engine):
    """Create migration_log table if not exists."""
    meta = MetaData()
    Table(
        MIGRATION_LOG_TABLE,
        meta,
        Column("id", Integer, primary_key=True),
        Column("version", String(255), nullable=False),
        Column("description", String(255), nullable=True),
        Column("applied_at", String(255), nullable=False),
        Column("payload", Text, nullable=True),
        Column("dependencies", Text, nullable=True),  # JSON array of dependency versions
        Column("branch", String(255), nullable=True),  # Branch name for parallel migrations
        Column("revision_id", String(255), nullable=True),  # Unique revision ID
    )
    meta.create_all(engine)
    print("Initialized migration metadata table.")
