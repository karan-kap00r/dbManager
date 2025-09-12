import os
import json
import yaml
import datetime
import typer
from dotenv import load_dotenv
from typing import Optional
from pathlib import Path
from tabulate import tabulate
from sqlalchemy import inspect, text, MetaData
from models import metadata
from src.planner import plan_migration
from src.db import get_engine, init_metadata, MIGRATION_LOG_TABLE
from src.applier import apply_migration
from utils.utils import resolve_latest_migration
from src.migration_loader import (
    load_migration_from_file,
    load_python_migration,
    load_rename_registry
)

load_dotenv()
app = typer.Typer()
DB_URL = os.getenv("DB_URL")


# ---------------------------
#  INIT DB
# ---------------------------
@app.command("init-db")
def init_db_command(db: str = typer.Option(DB_URL)):
    """Initialize the migration metadata table in the database.
    
    This command creates the migration_log table required for tracking applied
    migrations. The table stores migration version, description, timestamp, and
    payload information for rollback purposes.
    
    Args:
        db: Database connection URL. Defaults to DB_URL environment variable.
        
    Raises:
        Exception: If database connection fails or table creation fails.
        
    Example:
        $ python main.py init-db
        $ python main.py init-db --db "sqlite:///mydb.db"
    """
    engine = get_engine(db)
    init_metadata(engine)
    print("✅ Migration metadata initialized.")


# ---------------------------
#  REVISION
# ---------------------------
@app.command()
def revision(file: str = typer.Option(..., help="Path to migration YAML to register")):
    """Register an existing migration YAML file with a timestamped filename.
    
    This command takes an existing migration YAML file and creates a new timestamped
    version in the migrations directory. This is useful for converting manually
    created migration files into the proper timestamped format expected by the
    migration system.
    
    Args:
        file: Path to the existing migration YAML file to register.
        
    Raises:
        FileNotFoundError: If the specified file doesn't exist.
        yaml.YAMLError: If the YAML file is malformed.
        Exception: If file operations fail.
        
    Example:
        $ python main.py revision my_migration.yml
        # Creates: migrations/20250101120000_my_migration.yml
    """
    os.makedirs("migrations", exist_ok=True)
    migration = load_migration_from_file(file)

    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    out_path = os.path.join(
        "migrations", f"{timestamp}_{os.path.basename(file)}")

    with open(out_path, "w") as f:
        yaml.safe_dump(
            {
                "version": timestamp,
                "description": migration.description,
                "changes": [{a.type: a.payload} for a in migration.actions],
            },
            f,
        )

    print("📦 Revision saved to", out_path)


# ---------------------------
#  PLAN
# ---------------------------
@app.command()
def plan(path: Optional[str] = None, rename_map: str = typer.Option("rename_map.yml")):
    """Plan a migration by showing the steps that would be executed.
    
    This command performs a dry-run analysis of a migration file, showing what
    operations would be performed without actually executing them. It's useful
    for reviewing migration changes before applying them to the database.
    
    Args:
        path: Path to the migration file. If None, uses the latest migration.
        rename_map: Path to the table rename mapping file. Defaults to "rename_map.yml".
        
    Raises:
        FileNotFoundError: If migration file or rename map doesn't exist.
        yaml.YAMLError: If YAML files are malformed.
        Exception: If migration planning fails.
        
    Example:
        $ python main.py plan
        $ python main.py plan migrations/20250101120000_add_users.yml
        $ python main.py plan --rename-map custom_renames.yml
    """
    # Default to latest if no path is given
    if not path:
        path = resolve_latest_migration()
        print(f"📂 Using latest migration: {path}")
    migration = load_migration_from_file(path)
    registry = load_rename_registry(rename_map)
    steps = plan_migration(migration, registry)

    print("Planned steps:")
    print(tabulate(steps, headers="keys"))

# ---------------------------
#  APPLY
# ---------------------------


@app.command()
def apply(
    path: Optional[str] = None,
    db: str = typer.Option(DB_URL),
    rename_map: str = typer.Option("rename_map.yml"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    latest: bool = typer.Option(False, "--latest"),
):
    """Apply a migration to the database.
    
    This command executes a migration file (YAML or Python) against the target
    database. It supports both YAML-based migrations with raw SQL operations
    and Python-based migrations with custom upgrade/downgrade functions.
    
    For YAML migrations, the command:
    - Enhances operations with metadata for rollback purposes
    - Applies the migration using the planner and executor
    - Stores the enhanced payload in the migration log for rollback
    
    For Python migrations, the command:
    - Dynamically loads the Python module
    - Executes the upgrade() function
    - Stores migration metadata in the log
    
    Args:
        path: Path to the migration file. If None and latest=True, uses latest migration.
        db: Database connection URL. Defaults to DB_URL environment variable.
        rename_map: Path to the table rename mapping file. Defaults to "rename_map.yml".
        dry_run: If True, shows what would be done without executing changes.
        latest: If True, automatically uses the latest migration file.
        
    Raises:
        FileNotFoundError: If migration file or rename map doesn't exist.
        ValueError: If migration file type is unsupported.
        Exception: If migration application fails.
        
    Example:
        $ python main.py apply
        $ python main.py apply --latest
        $ python main.py apply migrations/20250101120000_add_users.yml
        $ python main.py apply --dry-run
        $ python main.py apply --db "sqlite:///mydb.db"
    """

    # Default to latest if no path is given
    if latest or not path:
        path = resolve_latest_migration()
        print(f"📂 Using latest migration: {path}")

    engine = get_engine(db)
    init_metadata(engine)

    # -----------------------------
    # YAML Migration
    # -----------------------------
    if path.endswith((".yml", ".yaml")):
        migration = load_migration_from_file(path)
        registry = load_rename_registry(rename_map)
        inspector = inspect(engine)

        enhanced_actions = []
        for action in migration.actions:
            payload = action.payload

            # Enhance drop_column with column metadata
            if "drop_column" in payload:
                tbl = payload["drop_column"]["table"]
                col = payload["drop_column"]["column"]
                existing_cols = {
                    c["name"]: c for c in inspector.get_columns(tbl)}
                if col in existing_cols:
                    col_meta = existing_cols[col]
                    payload["drop_column"]["meta"] = {
                        "type": str(col_meta["type"]),
                        "nullable": col_meta["nullable"],
                        "default": str(col_meta.get("default")),
                    }

            # Enhance drop_index with full index definition
            if "drop_index" in payload:
                tbl = payload["drop_index"]["table"]
                idx = payload["drop_index"]["name"]
                existing_idx = {
                    i["name"]: i for i in inspector.get_indexes(tbl)}
                if idx in existing_idx:
                    payload["drop_index"]["meta"] = existing_idx[idx]

            # Enhance drop_table with columns + indexes
            if "drop_table" in payload:
                tbl = payload["drop_table"]["table"]
                try:
                    # Get detailed column information
                    columns = inspector.get_columns(tbl)
                    # Get detailed index information
                    indexes = inspector.get_indexes(tbl)
                    
                    # Enhance column metadata for better rollback
                    enhanced_columns = []
                    for col in columns:
                        enhanced_col = {
                            "name": col["name"],
                            "type": str(col["type"]),
                            "nullable": col.get("nullable", True),
                            "primary_key": col.get("primary_key", False),
                            "unique": col.get("unique", False),
                            "default": str(col.get("default")) if col.get("default") is not None else None,
                        }
                        enhanced_columns.append(enhanced_col)
                    
                    payload["drop_table"]["meta"] = {
                        "columns": enhanced_columns,
                        "indexes": indexes,
                    }
                    print(f"📋 Enhanced drop_table metadata for {tbl}: {len(enhanced_columns)} columns, {len(indexes)} indexes")
                except Exception as e:
                    print(f"⚠️ Failed to enhance drop_table metadata for {tbl}: {e}")
                    # Fallback to basic metadata
                    payload["drop_table"]["meta"] = {
                        "columns": inspector.get_columns(tbl),
                        "indexes": inspector.get_indexes(tbl),
                    }

            enhanced_actions.append(action)

        # Replace actions with enriched versions
        migration.actions = enhanced_actions

        if dry_run:
            print("📝 Dry-run: would apply migration with enriched metadata")
            for act in enhanced_actions:
                print(act.payload)
            return

        # Actually apply migration
        apply_migration(engine, migration, registry, dry_run=False)

        # ✅ Persist enriched payload to migration log for rollback
        # Store the original YAML structure with enhanced metadata for proper rollback
        rollback_payload = []
        for action in enhanced_actions:
            print(action, "---action: ", action.payload)
            # Reconstruct the original YAML structure with enhanced metadata
            if action.type == "drop_column":
                rollback_payload.append({
                    "drop_column": {
                        "table": action.payload["table"],
                        "column": action.payload["column"],
                        "meta": action.payload.get("meta", {})
                    }
                })
            elif action.type == "drop_index":
                rollback_payload.append({
                    "drop_index": {
                        "table": action.payload["table"],
                        "name": action.payload["name"],
                        "meta": action.payload.get("meta", {})
                    }
                })
            elif action.type == "drop_table":
                rollback_payload.append({
                    "drop_table": {
                        "table": action.payload["table"]
                    }
                })
            elif action.type == "rename_table":
                rollback_payload.append({
                    "rename_table": {
                        "from": action.payload["from"],
                        "to": action.payload["to"]
                    }
                })
            elif action.type == "add_column":
                rollback_payload.append({
                    "add_column": {
                        "table": action.payload["table"],
                        "column": action.payload["column"],
                        "type": action.payload["type"],
                        "meta": action.payload.get("meta", {})
                    }
                })
            elif action.type == "add_index":
                rollback_payload.append({
                    "add_index": {
                        "table": action.payload["table"],
                        "name": action.payload["name"],
                        "columns": action.payload["columns"],
                        "meta": action.payload.get("meta", {})
                    }
                })
            elif action.type == "alter_column":
                rollback_payload.append({
                    "alter_column": {
                        "table": action.payload["table"],
                        "column": action.payload["column"],
                        "from": action.payload["from"],
                        "to": action.payload["to"],
                        "meta": action.payload.get("meta", {})
                    }
                })
            else:
                # For other operations, store as-is
                rollback_payload.append({action.type: action.payload})

        with engine.connect() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {MIGRATION_LOG_TABLE} "
                    f"(version, description, applied_at, payload) "
                    f"VALUES (:v, :d, :a, :p)"
                ),
                {
                    "v": migration.version,
                    "d": migration.description,
                    "a": datetime.datetime.utcnow().isoformat(),
                    "p": json.dumps(rollback_payload),
                },
            )
            conn.commit()

    # -----------------------------
    # Python Migration
    # -----------------------------
    elif path.endswith(".py"):
        upgrade, _ = load_python_migration(path)
        if dry_run:
            print(f"📝 Dry-run: would run upgrade() from {path}")
        else:
            with engine.connect() as conn:
                trans = conn.begin()
                try:
                    upgrade(engine)
                    conn.execute(
                        text(
                            f"INSERT INTO {MIGRATION_LOG_TABLE} "
                            f"(version, description, applied_at, payload) "
                            f"VALUES (:v, :d, :a, :p)"
                        ),
                        {
                            "v": os.path.basename(path),
                            "d": "Python migration",
                            "a": datetime.datetime.utcnow().isoformat(),
                            "p": json.dumps({"type": "python", "file": path}),
                        },
                    )
                    trans.commit()
                    print("✅ Python migration applied successfully.")
                except Exception as e:
                    trans.rollback()
                    print("❌ Error applying Python migration:", e)
                    raise

    else:
        raise ValueError("Unsupported migration file type. Use .yml or .py")


# ---------------------------
#  ROLLBACK
# ---------------------------
@app.command()
def rollback(db: str = typer.Option(DB_URL)):
    """Rollback the last applied migration.
    
    This command reverses the most recently applied migration by:
    - Retrieving the last migration from the migration log
    - Reversing all operations in the migration (e.g., drop_column -> add_column)
    - Removing the migration record from the log
    
    Supported rollback operations:
    - drop_column -> add_column (with original metadata)
    - drop_index -> add_index (with original column definitions)
    - drop_table -> create_table (with original schema)
    - rename_table -> reverse rename
    - add_column -> drop_column
    - add_index -> drop_index
    - alter_column -> revert to original state
    - Python migrations -> execute downgrade() function
    
    Args:
        db: Database connection URL. Defaults to DB_URL environment variable.
        
    Raises:
        Exception: If no migrations to rollback or rollback operations fail.
        
    Example:
        $ python main.py rollback
        $ python main.py rollback --db "sqlite:///mydb.db"
    """
    engine = get_engine(db)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT id, version, payload "
                f"FROM {MIGRATION_LOG_TABLE} "
                f"ORDER BY id DESC LIMIT 1"
            )
        ).fetchall()

        if not rows:
            print("⚠️ No migrations to rollback")
            return
        print("rows: ", rows)
        row = rows[0]
        payload = json.loads(row[2])
        print("payload: ", payload)
        print("Rolling back last migration:", row[1])

        if isinstance(payload, dict) and payload.get("type") == "python":
            print("Rolling back python migration")
            _, downgrade = load_python_migration(payload["file"])
            if downgrade:
                downgrade(engine)
        else:
            print("Rolling back raw operations")
            # Reverse operations
            for op in reversed(payload):
                print("1-op: ", op)
                if "drop_column" in op:
                    tbl = op["drop_column"]["table"]
                    col = op["drop_column"]["column"]
                    meta = op["drop_column"].get("meta", {})
                    print(tbl, col, meta)
                    try:
                        conn.execute(
                            text(
                                f"ALTER TABLE {tbl} ADD COLUMN {col} {meta.get('type', 'VARCHAR(255)')}"
                            )
                        )
                        print(f"↩️ Restored column {col} on {tbl}")
                    except Exception as e:
                        print("⚠️ Rollback column restore failed:", e)

                elif "drop_index" in op:
                    tbl = op["drop_index"]["table"]
                    idx = op["drop_index"]["name"]
                    meta = op["drop_index"].get("meta", {})
                    try:
                        cols = ", ".join(meta.get("column_names", []))
                        conn.execute(
                            text(f"CREATE INDEX {idx} ON {tbl} ({cols})")
                        )
                        print(f"↩️ Restored index {idx} on {tbl}")
                    except Exception as e:
                        print("⚠️ Rollback index restore failed:", e)

                elif "drop_table" in op:
                    tbl = op["drop_table"]["table"]
                    meta = op["drop_table"].get("meta", {})
                    try:
                        # Recreate table with proper column definitions
                        cols_sql = []
                        for c in meta.get("columns", []):
                            col_def = f"{c['name']} {c['type']}"
                            
                            # Add constraints
                            if not c.get("nullable", True):
                                col_def += " NOT NULL"
                            if c.get("primary_key", False):
                                col_def += " PRIMARY KEY"
                            if c.get("unique", False):
                                col_def += " UNIQUE"
                            if c.get("default") is not None:
                                default_val = c.get("default")
                                if isinstance(default_val, str) and default_val.upper() not in ["NULL", "CURRENT_TIMESTAMP"]:
                                    col_def += f" DEFAULT '{default_val}'"
                                elif not isinstance(default_val, str):
                                    col_def += f" DEFAULT {default_val}"
                            
                            cols_sql.append(col_def)
                        
                        # Create the table
                        conn.execute(
                            text(f"CREATE TABLE {tbl} ({', '.join(cols_sql)})")
                        )
                        
                        # Recreate indexes
                        for idx in meta.get("indexes", []):
                            try:
                                idx_name = idx.get("name")
                                idx_columns = idx.get("column_names", [])
                                if idx_name and idx_columns and idx_name != "PRIMARY":  # Skip primary key index
                                    cols_str = ", ".join(idx_columns)
                                    conn.execute(
                                        text(f"CREATE INDEX {idx_name} ON {tbl} ({cols_str})")
                                    )
                            except Exception as idx_e:
                                print(f"⚠️ Failed to recreate index {idx.get('name', 'unknown')}: {idx_e}")
                        
                        print(f"↩️ Restored table {tbl} with {len(cols_sql)} columns and {len(meta.get('indexes', []))} indexes")
                    except Exception as e:
                        print("⚠️ Rollback table restore failed:", e)

                elif "rename_table" in op:
                    try:
                        conn.execute(
                            text(
                                f"ALTER TABLE {op['to']} RENAME TO {op['from']};"
                            )
                        )
                        print(f"↩️ Renamed {op['to']} back to {op['from']}")
                    except Exception as e:
                        print("⚠️ Rollback rename failed:", e)

                elif "add_column" in op:
                    tbl = op["add_column"]["table"]
                    col = op["add_column"]["column"]
                    try:
                        conn.execute(
                            text(f"ALTER TABLE {tbl} DROP COLUMN {col}")
                        )
                        print(f"↩️ Dropped column {col} from {tbl}")
                    except Exception as e:
                        print("⚠️ Rollback add_column failed:", e)

                elif "add_index" in op:
                    tbl = op["add_index"]["table"]
                    idx = op["add_index"]["name"]
                    try:
                        conn.execute(
                            text(f"DROP INDEX {idx} ON {tbl}")
                        )
                        print(f"↩️ Dropped index {idx} from {tbl}")
                    except Exception as e:
                        print("⚠️ Rollback add_index failed:", e)

                elif "alter_column" in op:
                    tbl = op["alter_column"]["table"]
                    col = op["alter_column"]["column"]
                    from_meta = op["alter_column"]["from"]
                    try:
                        # Revert column to original state
                        conn.execute(
                            text(
                                f"ALTER TABLE {tbl} MODIFY COLUMN {col} {from_meta['type']}"
                            )
                        )
                        print(f"↩️ Reverted column {col} in {tbl}")
                    except Exception as e:
                        print("⚠️ Rollback alter_column failed:", e)

        conn.execute(
            text(f"DELETE FROM {MIGRATION_LOG_TABLE} WHERE id = :id"), {
                "id": row[0]}
        )
        print("✅ Rollback successful.")


# ---------------------------
#  AUTOGENERATE
# ---------------------------
@app.command()
def autogenerate(
    db: str = typer.Option(DB_URL),
    message: str = typer.Option("auto migration", "-m", "--message"),
):
    """Auto-generate migration by comparing database schema with models.py metadata.
    
    This command analyzes the current database schema and compares it against
    the target schema defined in models.py to automatically generate a migration
    file containing the necessary changes.
    
    The command detects and generates operations for:
    - Table additions and removals
    - Column additions, removals, and modifications
    - Index additions and removals
    - Column type changes and nullable modifications
    
    Generated migrations include enhanced metadata for proper rollback support.
    
    Args:
        db: Database connection URL. Defaults to DB_URL environment variable.
        message: Description for the generated migration. Defaults to "auto migration".
        
    Raises:
        Exception: If database connection fails or schema inspection fails.
        
    Example:
        $ python main.py autogenerate
        $ python main.py autogenerate -m "Add user profile table"
        $ python main.py autogenerate --db "sqlite:///mydb.db" -m "Update schema"
    """
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
            diffs.append(
                {
                    "create_table": {
                        "table": table,
                        "columns": [
                            {
                                "name": c.name,
                                "type": str(c.type),
                                "nullable": c.nullable,
                                "primary_key": c.primary_key,
                                "default": str(c.default) if c.default is not None else None,
                            }
                            for c in target_metadata.tables[table].columns
                        ],
                    }
                }
            )
    for table in existing_tables:
        if table not in target_tables and table not in INTERNAL_TABLES:
            diffs.append({"drop_table": {"table": table}})

    # Columns
    for table in target_tables:
        if table not in existing_tables:
            continue
        existing_cols = {col["name"]                         : col for col in inspector.get_columns(table)}
        target_cols = {
            col.name: col for col in target_metadata.tables[table].columns}

        # Added columns
        for col in target_cols:
            if col not in existing_cols:
                diffs.append(
                    {
                        "add_column": {
                            "table": table,
                            "column": col,
                            "type": str(target_cols[col].type),
                            "nullable": bool(target_cols[col].nullable),
                        }
                    }
                )

        # Dropped columns (💡 now with meta info)
        for col in existing_cols:
            if col not in target_cols:
                col_meta = existing_cols[col]
                diffs.append(
                    {
                        "drop_column": {
                            "table": table,
                            "column": col,
                            "meta": {
                                "type": str(col_meta["type"]),
                                "nullable": col_meta["nullable"],
                                "default": str(col_meta.get("default")),
                            },
                        }
                    }
                )

        # Altered columns
        for col, target_col in target_cols.items():
            if col in existing_cols:
                existing = existing_cols[col]
                if str(existing["type"]) != str(target_col.type) or existing["nullable"] != target_col.nullable:
                    diffs.append(
                        {
                            "alter_column": {
                                "table": table,
                                "column": col,
                                "from": {"type": str(existing["type"]), "nullable": bool(existing["nullable"])},
                                "to": {"type": str(target_col.type), "nullable": bool(target_col.nullable)},
                            }
                        }
                    )

    # Indexes
    for table in target_tables:
        if table not in existing_tables:
            continue
        existing_indexes = {idx["name"]                            : idx for idx in inspector.get_indexes(table)}
        target_indexes = {
            idx.name: idx for idx in target_metadata.tables[table].indexes}

        # Added indexes
        for idx_name, idx in target_indexes.items():
            if idx_name not in existing_indexes:
                diffs.append(
                    {
                        "add_index": {
                            "table": table,
                            "name": idx_name,
                            "columns": [str(c.name) for c in idx.columns],
                        }
                    }
                )

        # Dropped indexes
        for idx in existing_indexes:
            if idx not in target_indexes:
                diffs.append({"drop_index": {"table": table, "name": idx}})

    if not diffs:
        print("✅ No changes detected. Database is up-to-date.")
        return

    version = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"migrations/{version}_{message.replace(' ', '_')}.yml"
    Path("migrations").mkdir(exist_ok=True)

    safe_diffs = json.loads(json.dumps(diffs))
    with open(filename, "w") as f:
        yaml.safe_dump(
            {"version": version, "description": message, "changes": safe_diffs},
            f,
            sort_keys=False,
        )

    print(f"📦 New migration written: {filename}")
