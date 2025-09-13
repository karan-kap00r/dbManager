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
# Dynamic models import - will be loaded at runtime
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

# Configuration file path
CONFIG_FILE = "migrate_config.json"


def save_database_config(
    db_url: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    database: Optional[str] = None,
    db_type: str = "sqlite"
) -> None:
    """Save database configuration to file for future use.
    
    Args:
        db_url: Complete database URL.
        host: Database host.
        port: Database port.
        user: Database username.
        password: Database password.
        database: Database name.
        db_type: Database type.
    """
    config = {
        "db_url": db_url,
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
        "db_type": db_type,
        "saved_at": datetime.datetime.utcnow().isoformat()
    }
    
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"💾 Database configuration saved to {CONFIG_FILE}")


def load_database_config() -> Optional[dict]:
    """Load database configuration from file.
    
    Returns:
        Database configuration dict or None if not found.
    """
    if not os.path.exists(CONFIG_FILE):
        return None
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        return config
    except Exception as e:
        print(f"⚠️ Could not load configuration from {CONFIG_FILE}: {e}")
        return None


def get_database_config(
    db: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    database: Optional[str] = None,
    db_type: Optional[str] = None
) -> tuple[str, dict]:
    """Get database configuration with priority: command args > saved config > discovery.
    
    Returns:
        Tuple of (database_url, config_dict).
    """
    # If any command-line arguments provided, use them
    if any([db, host, user, database]):
        if db:
            return db, {"db_url": db}
        
        # Build from components
        final_db_type = db_type or "sqlite"
        db_url = build_database_url(
            db_url=db, host=host, port=port, user=user,
            password=password, database=database, db_type=final_db_type
        )
        return db_url, {
            "db_url": db_url,
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
            "db_type": final_db_type
        }
    
    # Try to load saved configuration
    saved_config = load_database_config()
    if saved_config and saved_config.get("db_url"):
        print(f"📁 Using saved database configuration from {CONFIG_FILE}")
        return saved_config["db_url"], saved_config
    
    # Fall back to discovery
    db_url = discover_database_url()
    return db_url, {"db_url": db_url}


def discover_database_url(db_url: Optional[str] = None) -> str:
    """Discover and validate the database URL.
    
    Args:
        db_url: Optional database URL. If None, auto-discovers.
        
    Returns:
        Database connection URL.
        
    Raises:
        ValueError: If no database URL is found or invalid.
    """
    if db_url:
        return db_url
    
    # Try environment variables first
    env_url = os.getenv("DB_URL")
    if env_url:
        return env_url
    
    # Try common environment variable names
    common_env_vars = [
        "DATABASE_URL",
        "DB_CONNECTION_STRING", 
        "DATABASE_CONNECTION_STRING",
        "SQLALCHEMY_DATABASE_URI",
        "POSTGRES_URL",
        "MYSQL_URL",
        "SQLITE_URL"
    ]
    
    for env_var in common_env_vars:
        url = os.getenv(env_var)
        if url:
            print(f"📁 Using database URL from {env_var}")
            return url
    
    # Try to find database configuration files
    config_files = [
        ".env",
        "config.py",
        "settings.py", 
        "database.py",
        "db_config.py"
    ]
    
    for config_file in config_files:
        if os.path.exists(config_file):
            try:
                if config_file.endswith('.py'):
                    # Try to load Python config file
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("config", config_file)
                    config = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(config)
                    
                    # Look for common database URL attributes
                    for attr in ['DATABASE_URL', 'DB_URL', 'database_url', 'db_url']:
                        if hasattr(config, attr):
                            url = getattr(config, attr)
                            if url:
                                print(f"📁 Using database URL from {config_file}")
                                return url
                else:
                    # Try to parse .env file manually
                    with open(config_file, 'r') as f:
                        for line in f:
                            if line.strip().startswith('DB_URL=') or line.strip().startswith('DATABASE_URL='):
                                url = line.split('=', 1)[1].strip().strip('"\'')
                                if url:
                                    print(f"📁 Using database URL from {config_file}")
                                    return url
            except Exception as e:
                print(f"⚠️ Could not load {config_file}: {e}")
                continue
    
    # Default fallback
    default_url = "sqlite:///migrate.db"
    print(f"⚠️ No database URL found, using default: {default_url}")
    print("💡 Set DB_URL environment variable or use --db option to specify database")
    return default_url


def build_database_url(
    db_url: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    database: Optional[str] = None,
    db_type: str = "sqlite"
) -> str:
    """Build database URL from individual components or use provided URL.
    
    Args:
        db_url: Complete database URL (takes precedence if provided).
        host: Database host.
        port: Database port.
        user: Database username.
        password: Database password.
        database: Database name.
        db_type: Database type (sqlite, postgresql, mysql).
        
    Returns:
        Complete database connection URL.
    """
    if db_url:
        return db_url
    
    if db_type == "sqlite":
        if database:
            return f"sqlite:///{database}"
        return "sqlite:///migrate.db"
    
    elif db_type == "postgresql":
        if not all([host, user, database]):
            raise ValueError("PostgreSQL requires --host, --user, and --database")
        
        password_part = f":{password}" if password else ""
        port_part = f":{port}" if port else ""
        return f"postgresql://{user}{password_part}@{host}{port_part}/{database}"
    
    elif db_type == "mysql":
        if not all([host, user, database]):
            raise ValueError("MySQL requires --host, --user, and --database")
        
        password_part = f":{password}" if password else ""
        port_part = f":{port}" if port else ":3306"
        return f"mysql://{user}{password_part}@{host}{port_part}/{database}"
    
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


def validate_database_url(db_url: str) -> bool:
    """Validate that the database URL is properly formatted.
    
    Args:
        db_url: Database connection URL to validate.
        
    Returns:
        True if URL is valid, False otherwise.
    """
    try:
        from sqlalchemy import create_engine
        # Try to create engine to validate URL
        engine = create_engine(db_url, future=True)
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"❌ Invalid database URL: {e}")
        return False


def discover_models_file(models_file: Optional[str] = None) -> str:
    """Discover and validate the models file.
    
    Args:
        models_file: Optional path to models file. If None, auto-discovers.
        
    Returns:
        Path to the models file.
        
    Raises:
        FileNotFoundError: If no models file is found.
        ImportError: If models file cannot be imported or lacks metadata.
    """
    if models_file:
        if not os.path.exists(models_file):
            raise FileNotFoundError(f"Models file not found: {models_file}")
        return models_file
    
    # Auto-discovery: look for common models file names
    possible_names = [
        "models.py",
        "schema.py", 
        "database.py",
        "db_models.py",
        "tables.py",
        "models/schema.py",
        "app/models.py",
        "src/models.py"
    ]
    
    for name in possible_names:
        if os.path.exists(name):
            return name
    
    raise FileNotFoundError(
        "No models file found. Tried: " + ", ".join(possible_names) + 
        "\nUse --models-file to specify the path to your models file."
    )


def load_models_metadata(models_file: str) -> MetaData:
    """Load metadata from the models file.
    
    Args:
        models_file: Path to the models file.
        
    Returns:
        SQLAlchemy MetaData object.
        
    Raises:
        ImportError: If the file cannot be imported or lacks metadata.
    """
    try:
        # Add current directory to Python path
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(models_file)))
        
        # Import the module
        module_name = os.path.splitext(os.path.basename(models_file))[0]
        module = __import__(module_name)
        
        # Look for metadata attribute
        if hasattr(module, 'metadata'):
            return module.metadata
        elif hasattr(module, 'MetaData'):
            return module.MetaData
        else:
            raise ImportError(f"No 'metadata' or 'MetaData' found in {models_file}")
            
    except Exception as e:
        raise ImportError(f"Failed to load models from {models_file}: {e}")


# ---------------------------
#  INIT DB
# ---------------------------
@app.command("init-db")
def init_db_command(
    db: Optional[str] = typer.Option(None, "--db", help="Database connection URL (auto-discovered if not provided)"),
    host: Optional[str] = typer.Option(None, "--host", help="Database host (e.g., localhost)"),
    port: Optional[int] = typer.Option(None, "--port", help="Database port (e.g., 5432 for PostgreSQL)"),
    user: Optional[str] = typer.Option(None, "--user", help="Database username"),
    password: Optional[str] = typer.Option(None, "--password", help="Database password"),
    database: Optional[str] = typer.Option(None, "--database", help="Database name"),
    db_type: Optional[str] = typer.Option("sqlite", "--type", help="Database type: sqlite, postgresql, mysql"),
):
    """Initialize the migration metadata table in the database.
    
    This command creates the migration_log table required for tracking applied
    migrations. The table stores migration version, description, timestamp, and
    payload information for rollback purposes.
    
    Database connection options:
    1. Use --db for complete URL: --db "postgresql://user:pass@localhost/db"
    2. Use individual components: --host localhost --user myuser --database mydb --type postgresql
    3. Auto-discovery from environment/config files
    
    Args:
        db: Complete database connection URL (takes precedence).
        host: Database host (e.g., localhost).
        port: Database port (e.g., 5432 for PostgreSQL).
        user: Database username.
        password: Database password.
        database: Database name.
        db_type: Database type (sqlite, postgresql, mysql).
        
    Raises:
        Exception: If database connection fails or table creation fails.
        
    Example:
        # Using complete URL
        $ python main.py init-db --db "postgresql://user:pass@localhost/mydb"
        
        # Using individual components (more secure)
        $ python main.py init-db --host localhost --user myuser --password mypass --database mydb --type postgresql
        
        # SQLite (default)
        $ python main.py init-db --database myapp.db
        
        # Auto-discovery
        $ python main.py init-db
    """
    try:
        # Get database configuration
        db_url, config = get_database_config(
            db=db, host=host, port=port, user=user,
            password=password, database=database, db_type=db_type
        )
        
        if not validate_database_url(db_url):
            raise ValueError(f"Invalid database URL: {db_url}")
        
        # Save configuration for future use
        save_database_config(
            db_url=config.get("db_url"),
            host=config.get("host"),
            port=config.get("port"),
            user=config.get("user"),
            password=config.get("password"),
            database=config.get("database"),
            db_type=config.get("db_type", "sqlite")
        )
            
        engine = get_engine(db_url)
    except Exception as e:
        print(f"❌ Database configuration error: {e}")
        print("💡 Use --help to see all database connection options")
        raise
    init_metadata(engine)
    print("✅ Migration metadata initialized.")
    print("💾 Database configuration saved - future commands will use these settings automatically!")


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
    db: Optional[str] = typer.Option(None, "--db", help="Database connection URL (auto-discovered if not provided)"),
    host: Optional[str] = typer.Option(None, "--host", help="Database host (e.g., localhost)"),
    port: Optional[int] = typer.Option(None, "--port", help="Database port (e.g., 5432 for PostgreSQL)"),
    user: Optional[str] = typer.Option(None, "--user", help="Database username"),
    password: Optional[str] = typer.Option(None, "--password", help="Database password"),
    database: Optional[str] = typer.Option(None, "--database", help="Database name"),
    db_type: Optional[str] = typer.Option("sqlite", "--type", help="Database type: sqlite, postgresql, mysql"),
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

    try:
        # Get database configuration (uses saved config if no args provided)
        db_url, config = get_database_config(
            db=db, host=host, port=port, user=user,
            password=password, database=database, db_type=db_type
        )
        
        if not validate_database_url(db_url):
            raise ValueError(f"Invalid database URL: {db_url}")
            
        engine = get_engine(db_url)
    except Exception as e:
        print(f"❌ Database configuration error: {e}")
        print("💡 Run 'python main.py init-db' first to configure database connection")
        raise
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
                        "table": action.payload["table"],
                        "meta": action.payload.get("meta", {})
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
def rollback(
    db: Optional[str] = typer.Option(None, "--db", help="Database connection URL (uses saved config if not provided)"),
    host: Optional[str] = typer.Option(None, "--host", help="Database host (overrides saved config)"),
    port: Optional[int] = typer.Option(None, "--port", help="Database port (overrides saved config)"),
    user: Optional[str] = typer.Option(None, "--user", help="Database username (overrides saved config)"),
    password: Optional[str] = typer.Option(None, "--password", help="Database password (overrides saved config)"),
    database: Optional[str] = typer.Option(None, "--database", help="Database name (overrides saved config)"),
    db_type: Optional[str] = typer.Option(None, "--type", help="Database type (overrides saved config)"),
):
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
    try:
        # Get database configuration (uses saved config if no args provided)
        db_url, config = get_database_config(
            db=db, host=host, port=port, user=user,
            password=password, database=database, db_type=db_type
        )
        
        if not validate_database_url(db_url):
            raise ValueError(f"Invalid database URL: {db_url}")
            
        engine = get_engine(db_url)
    except Exception as e:
        print(f"❌ Database configuration error: {e}")
        print("💡 Run 'python main.py init-db' first to configure database connection")
        raise

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
    db: Optional[str] = typer.Option(None, "--db", help="Database connection URL (uses saved config if not provided)"),
    host: Optional[str] = typer.Option(None, "--host", help="Database host (overrides saved config)"),
    port: Optional[int] = typer.Option(None, "--port", help="Database port (overrides saved config)"),
    user: Optional[str] = typer.Option(None, "--user", help="Database username (overrides saved config)"),
    password: Optional[str] = typer.Option(None, "--password", help="Database password (overrides saved config)"),
    database: Optional[str] = typer.Option(None, "--database", help="Database name (overrides saved config)"),
    db_type: Optional[str] = typer.Option(None, "--type", help="Database type (overrides saved config)"),
    message: str = typer.Option("auto migration", "-m", "--message"),
    models_file: Optional[str] = typer.Option(None, "--models-file", help="Path to models file (auto-discovered if not provided)"),
):
    """Auto-generate migration by comparing database schema with models metadata.
    
    This command analyzes the current database schema and compares it against
    the target schema defined in your models file to automatically generate a migration
    file containing the necessary changes.
    
    The command auto-discovers models files with common names like:
    models.py, schema.py, database.py, db_models.py, tables.py
    
    The command detects and generates operations for:
    - Table additions and removals
    - Column additions, removals, and modifications
    - Index additions and removals
    - Column type changes and nullable modifications
    
    Generated migrations include enhanced metadata for proper rollback support.
    
    Args:
        db: Database connection URL. Defaults to DB_URL environment variable.
        message: Description for the generated migration. Defaults to "auto migration".
        models_file: Path to models file. Auto-discovered if not provided.
        
    Raises:
        FileNotFoundError: If no models file is found.
        ImportError: If models file cannot be imported or lacks metadata.
        Exception: If database connection fails or schema inspection fails.
        
    Example:
        $ python main.py autogenerate
        $ python main.py autogenerate -m "Add user profile table"
        $ python main.py autogenerate --models-file "my_schema.py"
        $ python main.py autogenerate --db "sqlite:///mydb.db" -m "Update schema"
    """
    # Discover and load models file
    models_path = discover_models_file(models_file)
    print(f"📁 Using models file: {models_path}")
    
    try:
        # Get database configuration (uses saved config if no args provided)
        db_url, config = get_database_config(
            db=db, host=host, port=port, user=user,
            password=password, database=database, db_type=db_type
        )
        
        if not validate_database_url(db_url):
            raise ValueError(f"Invalid database URL: {db_url}")
            
        engine = get_engine(db_url)
    except Exception as e:
        print(f"❌ Database configuration error: {e}")
        print("💡 Run 'python main.py init-db' first to configure database connection")
        raise
    inspector = inspect(engine)
    target_metadata: MetaData = load_models_metadata(models_path)
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
            print("table: ", table)
            try:
                # Capture table metadata from existing database before dropping
                columns = inspector.get_columns(table)
                indexes = inspector.get_indexes(table)
                
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
                
                diffs.append({
                    "drop_table": {
                        "table": table,
                        "meta": {
                            "columns": enhanced_columns,
                            "indexes": indexes,
                        }
                    }
                })
                print(f"📋 Captured metadata for {table}: {len(enhanced_columns)} columns, {len(indexes)} indexes")
            except Exception as e:
                print(f"⚠️ Failed to capture metadata for {table}: {e}")
                # Fallback to basic drop_table without metadata
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
                try:
                    # Capture index metadata from existing database before dropping
                    index_info = existing_indexes[idx]
                    diffs.append({
                        "drop_index": {
                            "table": table,
                            "name": idx,
                            "meta": index_info
                        }
                    })
                    print(f"📋 Captured metadata for index {idx} on {table}")
                except Exception as e:
                    print(f"⚠️ Failed to capture metadata for index {idx} on {table}: {e}")
                    # Fallback to basic drop_index without metadata
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


# ---------------------------
#  DISCOVER MODELS
# ---------------------------
@app.command("discover-models")
def discover_models(
    models_file: Optional[str] = typer.Option(None, "--models-file", help="Path to models file (auto-discovered if not provided)"),
):
    """Discover and validate models files in your project.
    
    This command helps you find and validate your models files, showing
    which files contain SQLAlchemy metadata that can be used for migrations.
    
    Args:
        models_file: Path to models file. Auto-discovered if not provided.
        
    Example:
        $ python main.py discover-models
        $ python main.py discover-models --models-file "my_schema.py"
    """
    try:
        models_path = discover_models_file(models_file)
        print(f"✅ Found models file: {models_path}")
        
        # Validate the models file
        metadata = load_models_metadata(models_path)
        table_count = len(metadata.tables)
        
        print(f"📊 Models file contains {table_count} tables:")
        for table_name in metadata.tables.keys():
            table = metadata.tables[table_name]
            column_count = len(table.columns)
            index_count = len(table.indexes)
            print(f"  - {table_name}: {column_count} columns, {index_count} indexes")
            
        print(f"\n✅ Models file is valid and ready for migrations!")
        
    except FileNotFoundError as e:
        print(f"❌ {e}")
        print("\n💡 Common solutions:")
        print("  1. Create a models.py file with your SQLAlchemy metadata")
        print("  2. Use --models-file to specify the path to your models file")
        print("  3. Rename your schema file to one of: models.py, schema.py, database.py")
        
    except ImportError as e:
        print(f"❌ {e}")
        print("\n💡 Make sure your models file contains:")
        print("  - A 'metadata' variable with SQLAlchemy MetaData")
        print("  - Table definitions using SQLAlchemy")
        print("  - Example: metadata = MetaData()")


# ---------------------------
#  DISCOVER DATABASE
# ---------------------------
@app.command("discover-db")
def discover_database(
    db: Optional[str] = typer.Option(None, "--db", help="Database connection URL (auto-discovered if not provided)"),
):
    """Discover and validate database configuration.
    
    This command helps you find and validate your database configuration,
    showing which database URL will be used for migrations.
    
    Args:
        db: Database connection URL. Auto-discovered if not provided.
        
    Example:
        $ python main.py discover-db
        $ python main.py discover-db --db "postgresql://user:pass@localhost/db"
    """
    try:
        db_url = discover_database_url(db)
        print(f"✅ Found database URL: {db_url}")
        
        # Validate the database URL
        if validate_database_url(db_url):
            print("✅ Database URL is valid and connection successful!")
            
            # Test basic database operations
            engine = get_engine(db_url)
            with engine.connect() as conn:
                # Get database info
                result = conn.execute(text("SELECT 1 as test"))
                test_value = result.fetchone()[0]
                print(f"📊 Database connection test: {test_value}")
                
                # Try to get table count (if migration_log exists)
                try:
                    result = conn.execute(text("SELECT COUNT(*) FROM migration_log"))
                    migration_count = result.fetchone()[0]
                    print(f"📋 Migration log contains {migration_count} entries")
                except Exception:
                    print("📋 Migration log not yet initialized (run 'python main.py init-db')")
                    
        else:
            print("❌ Database URL is invalid or connection failed")
            
    except Exception as e:
        print(f"❌ Database discovery failed: {e}")
        print("\n💡 Common solutions:")
        print("  1. Set DB_URL environment variable")
        print("  2. Create a .env file with DATABASE_URL=...")
        print("  3. Use --db option to specify database URL")
        print("  4. Check that your database server is running")


# ---------------------------
#  SHOW CONFIG
# ---------------------------
@app.command("show-config")
def show_config():
    """Show current database configuration.
    
    This command displays the saved database configuration that will be used
    for all migration commands.
    
    Example:
        $ python main.py show-config
    """
    config = load_database_config()
    if not config:
        print("❌ No database configuration found.")
        print("💡 Run 'python main.py init-db' first to configure database connection")
        return
    
    print("📋 Current Database Configuration:")
    print(f"  Database URL: {config.get('db_url', 'Not set')}")
    print(f"  Host: {config.get('host', 'Not set')}")
    print(f"  Port: {config.get('port', 'Not set')}")
    print(f"  User: {config.get('user', 'Not set')}")
    print(f"  Database: {config.get('database', 'Not set')}")
    print(f"  Type: {config.get('db_type', 'Not set')}")
    print(f"  Saved at: {config.get('saved_at', 'Unknown')}")
    
    # Test the configuration
    try:
        db_url = config.get('db_url')
        if db_url and validate_database_url(db_url):
            print("✅ Configuration is valid and database is accessible")
        else:
            print("❌ Configuration is invalid or database is not accessible")
    except Exception as e:
        print(f"❌ Error testing configuration: {e}")


# ---------------------------
#  RESET CONFIG
# ---------------------------
@app.command("reset-config")
def reset_config():
    """Reset database configuration.
    
    This command removes the saved database configuration file,
    forcing the tool to use auto-discovery or command-line arguments.
    
    Example:
        $ python main.py reset-config
    """
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)
        print(f"🗑️  Removed configuration file: {CONFIG_FILE}")
        print("💡 Database configuration reset - tool will use auto-discovery for future commands")
    else:
        print("ℹ️  No configuration file found - nothing to reset")
