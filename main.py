"""
DB Migrate - Starter (with .env support)
"""

from __future__ import annotations
import os
import json
import yaml
import datetime
import importlib.util
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from models import metadata
import typer
from tabulate import tabulate
from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    Integer,
    String,
    Text,
    text,
    inspect,
)
from sqlalchemy.engine import Engine, Connection
from dotenv import load_dotenv

# -------------------------------------------------------------------
# Setup
# -------------------------------------------------------------------

load_dotenv()  # Load .env file
DB_URL = os.getenv("DB_URL", None)

app = typer.Typer(help="DB Migrate - starter CLI")

MIGRATION_LOG_TABLE = "migration_log"

# -------------------------------------------------------------------
# DB Helpers
# -------------------------------------------------------------------

def get_engine(db_url: str) -> Engine:
    return create_engine(db_url, future=True)

def init_metadata(engine: Engine):
    """Create migration_log table if not exists."""
    meta = MetaData()
    migration_log = Table(
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

# -------------------------------------------------------------------
# Migration parsing
# -------------------------------------------------------------------

@dataclass
class MigrationAction:
    type: str
    payload: Dict[str, Any]

@dataclass
class Migration:
    version: str
    description: str
    actions: List[MigrationAction]

def load_migration_from_file(path: str) -> Migration:
    with open(path, "r") as f:
        raw = yaml.safe_load(f)
    version = str(raw.get("version") or datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S"))
    desc = raw.get("description", "")
    actions_raw = raw.get("changes", [])
    actions = [MigrationAction(a_type, payload) for d in actions_raw for a_type, payload in d.items()]
    return Migration(version=version, description=desc, actions=actions)

def load_rename_registry(path: str) -> Dict[str, str]:
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        raw = yaml.safe_load(f)
    return raw.get("table_renames", {})

# -------------------------------------------------------------------
# Planner
# -------------------------------------------------------------------

def plan_migration(migration: Migration, rename_registry: Dict[str, str]) -> List[Dict[str, Any]]:
    planned = []
    for act in migration.actions:
        if act.type == "rename_table":
            src = act.payload["from"]
            dst = act.payload["to"]
            if rename_registry.get(src) == dst or True:
                planned.append({"op": "rename_table", "from": src, "to": dst})
        elif act.type == "split_column":
            planned.append({"op": "split_column", **act.payload})
        else:
            planned.append({"op": "raw", "type": act.type, "payload": act.payload})
    return planned

# -------------------------------------------------------------------
# Executors
# -------------------------------------------------------------------

def exec_rename_table(conn: Connection, frm: str, to: str):
    sql = f"ALTER TABLE {frm} RENAME TO {to};"
    conn.execute(text(sql))

def exec_split_column(conn: Connection, table: str, column: str, into: List[str], transform: Optional[str]):
    for c in into:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {c} TEXT;"))
    rows = conn.execute(text(f"SELECT rowid, {column} FROM {table};")).fetchall()
    for r in rows:
        rowid, val = r
        try:
            if transform:
                func = eval("lambda val: %s" % transform)  # ⚠️ prototype only
                parts = func(val)
            else:
                parts = [val, None]
            if not isinstance(parts, (list, tuple)):
                parts = [parts]
        except Exception:
            parts = [None] * len(into)
        set_clause = ",".join([f"{col} = :v{i}" for i, col in enumerate(into)])
        params = {f"v{i}": parts[i] if i < len(parts) else None for i in range(len(into))}
        params["rowid"] = rowid
        conn.execute(text(f"UPDATE {table} SET {set_clause} WHERE rowid = :rowid"), params)

def exec_raw_operation(conn: Connection, raw: Dict[str, Any]):
    op_type = raw.get("type")
    payload = raw.get("payload")

    if op_type == "create_table":
        table_name = payload["table"]
        columns = payload.get("columns", [])
        cols_sql = []
        for col in columns:
            col_def = f"{col['name']} {col['type']}"
            if not col.get("nullable", True):
                col_def += " NOT NULL"
            if col.get("primary_key", False):
                col_def += " PRIMARY KEY"
            if col.get("default") is not None:
                col_def += f" DEFAULT {col['default']}"
            cols_sql.append(col_def)
        sql = f"CREATE TABLE {table_name} ({', '.join(cols_sql)});"
        print(f"Executing SQL: {sql}")
        conn.execute(text(sql))

    elif op_type == "drop_table":
        table_name = payload["table"]
        sql = f"DROP TABLE IF EXISTS {table_name};"
        print(f"Executing SQL: {sql}")
        conn.execute(text(sql))

    elif op_type == "add_column":
        table = payload["table"]
        col_name = payload["column"]
        col_type = payload["type"]
        nullable = "NULL" if payload.get("nullable", True) else "NOT NULL"
        sql = f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type} {nullable};"
        print(f"Executing SQL: {sql}")
        conn.execute(text(sql))

    elif op_type == "drop_column":
        table = payload["table"]
        col_name = payload["column"]
        sql = f"ALTER TABLE {table} DROP COLUMN {col_name};"
        print(f"Executing SQL: {sql}")
        conn.execute(text(sql))

    elif op_type == "alter_column":
        table = payload["table"]
        col = payload["column"]
        to_type = payload["to"]["type"]
        nullable = "NULL" if payload["to"].get("nullable", True) else "NOT NULL"
        sql = f"ALTER TABLE {table} ALTER COLUMN {col} TYPE {to_type};"
        print(f"Executing SQL: {sql}")
        conn.execute(text(sql))
        sql_null = f"ALTER TABLE {table} ALTER COLUMN {col} SET {nullable};"
        print(f"Executing SQL: {sql_null}")
        conn.execute(text(sql_null))

    elif op_type == "add_index":
        table = payload["table"]
        idx_name = payload["name"]
        cols = ", ".join(payload["columns"])
        sql = f"CREATE INDEX {idx_name} ON {table} ({cols});"
        print(f"Executing SQL: {sql}")
        conn.execute(text(sql))

    elif op_type == "drop_index":
        idx_name = payload["name"]
        sql = f"DROP INDEX IF EXISTS {idx_name};"
        print(f"Executing SQL: {sql}")
        conn.execute(text(sql))

    else:
        print("⚠️ Unknown raw operation:", op_type)

# -------------------------------------------------------------------
# High-level Apply
# -------------------------------------------------------------------

def apply_migration(engine: Engine, migration: Migration, rename_registry: Dict[str,str], dry_run: bool = False):
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
            print("Migration applied successfully.")
        except Exception as e:
            trans.rollback()
            print("Error applying migration:", e)
            raise

def load_python_migration(path: str):
    spec = importlib.util.spec_from_file_location("migration_module", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    upgrade = getattr(module, "upgrade", None)
    downgrade = getattr(module, "downgrade", None)
    if not upgrade:
        raise ValueError(f"No upgrade() function found in {path}")
    return upgrade, downgrade

# -------------------------------------------------------------------
# CLI Commands
# -------------------------------------------------------------------

@app.command("init-db")
def init_db_command(db: str = typer.Option(DB_URL, help="Database URL")):
    engine = get_engine(db)
    init_metadata(engine)

@app.command()
def revision(file: str = typer.Option(..., help="Path to migration YAML to register")):
    os.makedirs("migrations", exist_ok=True)
    migration = load_migration_from_file(file)
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    out_path = os.path.join("migrations", f"{timestamp}_{os.path.basename(file)}")
    with open(out_path, "w") as f:
        yaml.safe_dump({
            "version": timestamp,
            "description": migration.description,
            "changes": [{a.type: a.payload} for a in migration.actions]
        }, f)
    print("Revision saved to", out_path)

@app.command()
def plan(path: str, rename_map: str = typer.Option("rename_map.yml")):
    migration = load_migration_from_file(path)
    registry = load_rename_registry(rename_map)
    plan = plan_migration(migration, registry)
    print("Planned steps:")
    print(tabulate(plan, headers="keys"))

@app.command()
def apply(
    path: Optional[str] = None,
    db: str = typer.Option(DB_URL),
    rename_map: str = typer.Option("rename_map.yml"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    latest: bool = typer.Option(False, "--latest"),
):
    def resolve_latest_migration() -> str:
        migrations_dir = "migrations"
        if not os.path.exists(migrations_dir):
            raise FileNotFoundError("No migrations directory found.")
        files = [f for f in os.listdir(migrations_dir) if f.endswith((".yml", ".yaml", ".py"))]
        if not files:
            raise FileNotFoundError("No migration files found in migrations/ directory.")
        files.sort()
        return os.path.join(migrations_dir, files[-1])

    if latest or not path:
        path = resolve_latest_migration()
        print(f"Using latest migration: {path}")

    engine = get_engine(db)
    init_metadata(engine)

    if path.endswith((".yml", ".yaml")):
        migration = load_migration_from_file(path)
        registry = load_rename_registry(rename_map)
        apply_migration(engine, migration, registry, dry_run=dry_run)
    elif path.endswith(".py"):
        upgrade, _ = load_python_migration(path)
        if dry_run:
            print(f"Dry-run: would run upgrade() from {path}")
        else:
            with engine.connect() as conn:
                trans = conn.begin()
                try:
                    upgrade(engine)
                    conn.execute(
                        text(f"INSERT INTO {MIGRATION_LOG_TABLE} (version, description, applied_at, payload) VALUES (:v, :d, :a, :p)"),
                        {"v": os.path.basename(path), "d": "Python migration", "a": datetime.datetime.utcnow().isoformat(), "p": json.dumps({"type":"python","file":path})},
                    )
                    trans.commit()
                    print("Python migration applied successfully.")
                except Exception as e:
                    trans.rollback()
                    print("Error applying Python migration:", e)
                    raise
    else:
        raise ValueError("Unsupported migration file type. Use .yml or .py")

@app.command()
def rollback(db: str = typer.Option(DB_URL)):
    engine = get_engine(db)
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT id, version, payload FROM {MIGRATION_LOG_TABLE} ORDER BY id DESC LIMIT 1")).fetchall()
        if not rows:
            print("No migrations to rollback")
            return
        row = rows[0]
        payload = json.loads(row[2])
        print("Last migration:", row[1])
        if isinstance(payload, dict) and payload.get("type") == "python":
            _, downgrade = load_python_migration(payload["file"])
            if downgrade:
                downgrade(engine)
        else:
            for op in reversed(payload):
                if op["op"] == "rename_table":
                    try:
                        conn.execute(text(f"ALTER TABLE {op['to']} RENAME TO {op['from']};"))
                    except Exception as e:
                        print("Rollback failed", e)
        conn.execute(text(f"DELETE FROM {MIGRATION_LOG_TABLE} WHERE id = :id"), {"id": row[0]})
        print("Rollback successful.")

@app.command()
def autogeneration(db: str = typer.Option(DB_URL), message: str = typer.Option("auto migration", "--message", "-m")):
    engine = get_engine(db)
    inspector = inspect(engine)
    target_metadata: MetaData = metadata
    diffs = []
    existing_tables = inspector.get_table_names()
    target_tables = list(target_metadata.tables.keys())
    INTERNAL_TABLES = {MIGRATION_LOG_TABLE}

    # Tables
    for table in target_tables:
        if table not in existing_tables and table not in INTERNAL_TABLES:
            diffs.append({"create_table":{"table":table,"columns":[{"name":c.name,"type":str(c.type),"nullable":c.nullable,"primary_key":c.primary_key,"default":c.default} for c in target_metadata.tables[table].columns]}})
    for table in existing_tables:
        if table not in target_tables and table not in INTERNAL_TABLES:
            diffs.append({"drop_table":{"table":table}})

    # Columns
    for table in target_tables:
        if table not in existing_tables:
            continue
        existing_cols = {col["name"]: col for col in inspector.get_columns(table)}
        target_cols = {col.name: col for col in target_metadata.tables[table].columns}
        for col in target_cols:
            if col not in existing_cols:
                diffs.append({"add_column":{"table":table,"column":col,"type":str(target_cols[col].type),"nullable":bool(target_cols[col].nullable)}})
        for col in existing_cols:
            if col not in target_cols:
                diffs.append({"drop_column":{"table":table,"column":col}})
        for col, target_col in target_cols.items():
            if col in existing_cols:
                existing = existing_cols[col]
                if str(existing["type"]) != str(target_col.type) or existing["nullable"] != target_col.nullable:
                    diffs.append({"alter_column":{"table":table,"column":col,"from":{"type":str(existing["type"]),"nullable":bool(existing["nullable"])},"to":{"type":str(target_col.type),"nullable":bool(target_col.nullable)}}})

    # Indexes
    for table in target_tables:
        if table not in existing_tables:
            continue
        existing_indexes = {idx["name"]: idx for idx in inspector.get_indexes(table)}
        target_indexes = {idx.name: idx for idx in target_metadata.tables[table].indexes}
        for idx_name, idx in target_indexes.items():
            if idx_name not in existing_indexes:
                diffs.append({"add_index":{"table":table,"name":idx_name,"columns":[str(c.name) for c in idx.columns]}})
        for idx in existing_indexes:
            if idx not in target_indexes:
                diffs.append({"drop_index":{"table":table,"name":idx}})

    if not diffs:
        print("✅ No changes detected. Database is up-to-date.")
        return

    version = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"migrations/{version}_{message.replace(' ','_')}.yml"
    os.makedirs("migrations", exist_ok=True)
    safe_diffs = json.loads(json.dumps(diffs))
    with open(filename, "w") as f:
        yaml.safe_dump({"version":version,"description":message,"changes":safe_diffs}, f, sort_keys=False)
    print(f"📦 New migration written: {filename}")

# -------------------------------------------------------------------
# Bootstrap
# -------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs("migrations", exist_ok=True)
    app()
