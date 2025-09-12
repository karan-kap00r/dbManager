import os
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Text
from sqlalchemy.engine import Engine

MIGRATION_LOG_TABLE = "migration_log"

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
    )
    meta.create_all(engine)
    print("Initialized migration metadata table.")
