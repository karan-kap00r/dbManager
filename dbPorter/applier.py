import json, datetime
from tabulate import tabulate
from sqlalchemy.engine import Engine
from sqlalchemy import text
from .planner import plan_migration
from .executors import exec_rename_table, exec_split_column, exec_raw_operation
from .db import MIGRATION_LOG_TABLE
from .migration_loader import Migration

def apply_migration(engine: Engine, migration: Migration, rename_registry: dict, dry_run: bool = False):
    planned = plan_migration(migration, rename_registry)
    print("Planned operations:")
    print(tabulate(planned, headers="keys"))

    if dry_run:
        print("Dry-run mode; nothing applied.")
        return

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            for op in planned:
                if op["op"] == "rename_table":
                    exec_rename_table(conn, op["from"], op["to"])
                elif op["op"] == "split_column":
                    exec_split_column(conn, op["table"], op["column"], op["into"], op.get("transform"))
                elif op["op"] == "raw":
                    exec_raw_operation(conn, op)
            conn.execute(
                text(f"INSERT INTO {MIGRATION_LOG_TABLE} (version, description, applied_at, payload) VALUES (:v,:d,:a,:p)"),
                {"v": migration.version, "d": migration.description, "a": datetime.datetime.utcnow().isoformat(), "p": json.dumps(planned)}
            )
            trans.commit()
            print("✅ Migration applied successfully.")
        except Exception as e:
            trans.rollback()
            print("❌ Error applying migration:", e)
            raise
