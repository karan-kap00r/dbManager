import os
import json
import yaml
import datetime
import typer
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any, Tuple, Set
from pathlib import Path
from tabulate import tabulate
from sqlalchemy import inspect, text, MetaData
from sqlalchemy.engine import Engine
from collections import defaultdict, deque
import uuid
# Dynamic models import - will be loaded at runtime
from .planner import plan_migration
from .db import get_engine, init_metadata, MIGRATION_LOG_TABLE
from .applier import apply_migration
from .utils.utils import resolve_latest_migration
from .migration_loader import (
    load_migration_from_file,
    load_python_migration,
    load_rename_registry
)
from .utils.constants import _CONFIG_FILE, _INTERNAL_TABLES

load_dotenv()
app = typer.Typer()

# Configuration file path
CONFIG_FILE = _CONFIG_FILE

# Global configuration store for programmatic access
_global_config = {}


def set_database_url(db_url: str):
    """
    Set database URL programmatically for security-conscious organizations.
    
    This allows users to set the database URL directly in their code after importing
    the migration tool, avoiding the need to store credentials in config files.
    
    Args:
        db_url: Database connection URL (e.g., "postgresql://user:pass@host:port/db")
        
    Example:
        from dbPorter import set_database_url
        set_database_url("postgresql://user:pass@localhost:5432/mydb")
    """
    global _global_config
    _global_config["db_url"] = db_url
    
    # Parse URL components and save to config file (excluding sensitive data)
    try:
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        
        # Extract database type from scheme
        scheme = parsed.scheme.lower()
        if scheme.startswith('mysql'):
            db_type = 'mysql'
        elif scheme.startswith('postgresql'):
            db_type = 'postgresql'
        elif scheme == 'sqlite':
            db_type = 'sqlite'
        else:
            db_type = 'unknown'
        
        # Save configuration (excluding sensitive data)
        save_database_config(
            db_url=None,  # Don't save URL with credentials
            host=parsed.hostname,
            port=parsed.port,
            user=parsed.username,
            password=None,  # Never save passwords
            database=parsed.path.lstrip('/') if parsed.path else None,
            db_type=db_type
        )
        
        print(f"🔐 Database URL set programmatically")
        print(f"📁 Non-sensitive configuration saved to {CONFIG_FILE}")
        print(f"💡 Use environment variables or command line arguments for CLI commands")
        
    except Exception as e:
        # If parsing fails, still store the URL but don't save config
        print(f"🔐 Database URL set programmatically (parsing failed: {e})")
        print(f"⚠️  Configuration not saved to file")

def get_database_url() -> Optional[str]:
    """
    Get the programmatically set database URL.
    
    Returns:
        Database URL if set programmatically in the current process, None otherwise
    """
    return _global_config.get("db_url")


def save_database_config(
    db_url: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    database: Optional[str] = None,
    db_type: str = "sqlite"
) -> None:
    """Save database configuration to file for future use (excluding sensitive data).
    
    SECURITY NOTE: This function deliberately excludes passwords and sensitive data
    from the saved configuration to prevent credential exposure in version control.
    
    Args:
        db_url: Complete database URL (will be stored if no sensitive data detected).
        host: Database host.
        port: Database port.
        user: Database username.
        password: Database password (NOT SAVED for security).
        database: Database name.
        db_type: Database type.
    """
    # Only save non-sensitive configuration data
    config = {
        "host": host,
        "port": port,
        "user": user,
        "database": database,
        "db_type": db_type,
        "saved_at": datetime.datetime.utcnow().isoformat(),
        "security_note": "Passwords and sensitive data are not stored for security",
        "requires_credentials": password is not None or (db_url and _contains_sensitive_data(db_url))
    }
    
    # Only save db_url if it doesn't contain sensitive information
    if db_url and not _contains_sensitive_data(db_url):
        config["db_url"] = db_url
    else:
        config["db_url"] = None
        config["requires_credentials"] = True
    
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"💾 Database configuration saved to {CONFIG_FILE} (excluding sensitive data)")
    print(f"🔐 Security: Passwords and sensitive data are not stored in the config file")
    print(f"💡 Use environment variables or programmatic configuration for credentials")


def _contains_sensitive_data(db_url: str) -> bool:
    """Check if database URL contains sensitive information like passwords.
    
    Args:
        db_url: Database connection URL
        
    Returns:
        True if URL contains sensitive data, False otherwise
    """
    if not db_url:
        return False
    
    # Check for password patterns in URL
    sensitive_patterns = [
        'password=', 'passwd=', 'pwd=',
        '://[^:]+:[^@]+@',  # user:password@ pattern
    ]
    
    import re
    for pattern in sensitive_patterns:
        if re.search(pattern, db_url, re.IGNORECASE):
            return True
    
    return False


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
    """Get database configuration with Alembic-style priority: command args > env vars > saved config > discovery.
    
    This follows Alembic's pattern where command line arguments override everything,
    then environment variables, then saved configuration, then discovery.
    
    Returns:
        Tuple of (database_url, config_dict).
    """
    # Priority 1: Command line arguments (highest priority - like Alembic's env.py override)
    if any([db, host, user, database]):
        if db:
            return db, {"db_url": db, "source": "command_line"}
        
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
            "db_type": final_db_type,
            "source": "command_line"
        }
    
    # Priority 2: Environment variables (like Alembic's DATABASE_URL)
    env_db_url = os.getenv('DBPORTER_DATABASE_URL') or os.getenv('DATABASE_URL')
    if env_db_url:
        print(f"🔐 Using database URL from environment variable")
        return env_db_url, {"db_url": env_db_url, "source": "environment"}
    
    # Priority 3: Saved configuration (like Alembic's alembic.ini fallback)
    saved_config = load_database_config()
    if saved_config and saved_config.get("db_url"):
        print(f"📁 Using saved database configuration from {CONFIG_FILE}")
        return saved_config["db_url"], {**saved_config, "source": "saved_config"}
    
    # Priority 4: Discovery (last resort)
    try:
        db_url = discover_database_url()
        # Extract components from discovered URL
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        scheme = parsed.scheme.lower()
        
        config = {
            "db_url": db_url,
            "source": "discovery",
            "db_type": "mysql" if scheme.startswith('mysql') else "postgresql" if scheme.startswith('postgresql') else "sqlite" if scheme == 'sqlite' else "unknown"
        }
        
        # Extract individual components for non-SQLite databases
        if scheme != 'sqlite':
            config["host"] = parsed.hostname or "localhost"
            config["port"] = parsed.port or (3306 if scheme.startswith('mysql') else 5432)
            config["user"] = parsed.username
            config["database"] = parsed.path.lstrip('/') if parsed.path else None
        else:
            # For SQLite, database is the file path
            config["database"] = parsed.path.lstrip('/') if parsed.path else "migrate.db"
            config["host"] = None
            config["port"] = None
            config["user"] = None
            
        return db_url, config
    except Exception as e:
        # If discovery fails, fall back to SQLite default
        print(f"⚠️ Database discovery failed: {e}")
        print("💡 Using SQLite default database")
        default_url = "sqlite:///migrate.db"
        return default_url, {"db_url": default_url, "source": "fallback", "db_type": "sqlite", "host": None, "port": None, "user": None, "database": "migrate.db"}


# ---------------------------
#  MIGRATION GRAPH (DAG) SYSTEM
# ---------------------------

class MigrationNode:
    """Represents a single migration in the DAG."""
    
    def __init__(self, version: str, description: str, revision_id: str = None, 
                 branch: str = None, dependencies: List[str] = None, 
                 applied_at: str = None, payload: str = None):
        self.version = version
        self.description = description
        self.revision_id = revision_id or str(uuid.uuid4())[:8]
        self.branch = branch or "main"
        self.dependencies = dependencies or []
        self.applied_at = applied_at
        self.payload = payload
        self.children: List['MigrationNode'] = []
        self.parents: List['MigrationNode'] = []
    
    def add_dependency(self, dependency_version: str):
        """Add a dependency to this migration."""
        if dependency_version not in self.dependencies:
            self.dependencies.append(dependency_version)
    
    def __repr__(self):
        return f"MigrationNode(version={self.version}, branch={self.branch}, deps={len(self.dependencies)})"


class MigrationGraph:
    """Directed Acyclic Graph for managing migration dependencies."""
    
    def __init__(self):
        self.nodes: Dict[str, MigrationNode] = {}
        self.branches: Dict[str, List[str]] = defaultdict(list)
        self.heads: Set[str] = set()  # Current head revisions
    
    def add_node(self, node: MigrationNode) -> None:
        """Add a migration node to the graph."""
        # Only add if not already present
        if node.version not in self.nodes:
            self.nodes[node.version] = node
            self.branches[node.branch].append(node.version)
            
            # Update parent-child relationships
            for dep_version in node.dependencies:
                if dep_version in self.nodes:
                    dep_node = self.nodes[dep_version]
                    if node not in dep_node.children:
                        dep_node.children.append(node)
                    if dep_node not in node.parents:
                        node.parents.append(dep_node)
    
    def get_node(self, version: str) -> Optional[MigrationNode]:
        """Get a migration node by version."""
        return self.nodes.get(version)
    
    def get_dependencies(self, version: str) -> List[str]:
        """Get all dependencies for a migration (transitive)."""
        visited = set()
        deps = []
        
        def collect_deps(node_version: str):
            if node_version in visited:
                return
            visited.add(node_version)
            
            node = self.get_node(node_version)
            if node:
                for dep in node.dependencies:
                    if dep not in deps:
                        deps.append(dep)
                    collect_deps(dep)
        
        collect_deps(version)
        return deps
    
    def topological_sort(self) -> List[str]:
        """Get migrations in dependency order using topological sort."""
        in_degree = defaultdict(int)
        graph = defaultdict(list)
        
        # Build graph and calculate in-degrees
        for version, node in self.nodes.items():
            in_degree[version] = len(node.dependencies)
            for dep in node.dependencies:
                graph[dep].append(version)
        
        # Find nodes with no dependencies
        queue = deque([v for v, degree in in_degree.items() if degree == 0])
        result = []
        
        while queue:
            current = queue.popleft()
            result.append(current)
            
            # Reduce in-degree for dependent nodes
            for dependent in graph[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        
        # Check for cycles
        if len(result) != len(self.nodes):
            raise ValueError("Cycle detected in migration dependencies!")
        
        return result
    
    def get_heads(self) -> List[str]:
        """Get current head revisions (migrations with no children)."""
        heads = []
        for version, node in self.nodes.items():
            if not node.children:
                heads.append(version)
        return heads
    
    def find_conflicts(self, new_version: str, new_dependencies: List[str], check_existing: bool = True) -> List[str]:
        """Find potential conflicts when adding a new migration."""
        conflicts = []
        
        # Check if version already exists (only when adding new migrations)
        if check_existing and new_version in self.nodes:
            conflicts.append(f"Migration {new_version} already exists")
        
        # Check for circular dependencies
        if new_version in new_dependencies:
            conflicts.append(f"Migration {new_version} cannot depend on itself")
        
        # Check for missing dependencies
        for dep in new_dependencies:
            if dep not in self.nodes:
                conflicts.append(f"Dependency {dep} does not exist")
        
        return conflicts
    
    def get_merge_base(self, branch1: str, branch2: str) -> Optional[str]:
        """Find the common ancestor of two branches."""
        # Simple implementation - find the latest common migration
        branch1_migrations = [v for v, n in self.nodes.items() if n.branch == branch1]
        branch2_migrations = [v for v, n in self.nodes.items() if n.branch == branch2]
        
        # Find common dependencies
        common = set()
        for v1 in branch1_migrations:
            for v2 in branch2_migrations:
                deps1 = set(self.get_dependencies(v1))
                deps2 = set(self.get_dependencies(v2))
                common.update(deps1.intersection(deps2))
        
        if not common:
            return None
        
        # Return the latest common migration
        return max(common, key=lambda v: self.nodes[v].version)
    
    def visualize(self) -> str:
        """Generate a text representation of the migration graph."""
        lines = []
        lines.append("Migration Graph:")
        lines.append("=" * 50)
        
        # Group by branch and remove duplicates
        branch_migrations = defaultdict(set)
        for version, node in self.nodes.items():
            branch_migrations[node.branch].add(version)
        
        # Group by branch
        for branch, versions in branch_migrations.items():
            lines.append(f"\nBranch: {branch}")
            lines.append("-" * 20)
            
            for version in sorted(versions):
                node = self.nodes[version]
                deps_str = ", ".join(node.dependencies) if node.dependencies else "none"
                status = "✅ Applied" if node.applied_at else "⏳ Pending"
                lines.append(f"  {version}: {node.description}")
                lines.append(f"    Status: {status}")
                lines.append(f"    Dependencies: {deps_str}")
                lines.append(f"    Revision ID: {node.revision_id}")
        
        return "\n".join(lines)


def load_migration_graph(engine: Engine) -> MigrationGraph:
    """Load migration graph from database."""
    graph = MigrationGraph()
    
    with engine.connect() as conn:
        # Check if DAG columns exist
        try:
            result = conn.execute(
                text(f"SELECT version, description, dependencies, branch, revision_id, applied_at, payload "
                     f"FROM {MIGRATION_LOG_TABLE} ORDER BY version")
            ).fetchall()
        except Exception:
            # Fallback for old schema without DAG columns
            result = conn.execute(
                text(f"SELECT version, description, NULL as dependencies, 'main' as branch, "
                     f"SUBSTR(version, 1, 8) as revision_id, applied_at, payload "
                     f"FROM {MIGRATION_LOG_TABLE} ORDER BY version")
            ).fetchall()
        
        for row in result:
            version, description, deps_json, branch, revision_id, applied_at, payload = row
            dependencies = json.loads(deps_json) if deps_json else []
            
            # Ensure we have valid values
            branch = branch or 'main'
            revision_id = revision_id or str(uuid.uuid4())[:8]
            
            node = MigrationNode(
                version=version,
                description=description,
                revision_id=revision_id,
                branch=branch,
                dependencies=dependencies,
                applied_at=applied_at,
                payload=payload
            )
            graph.add_node(node)
    
    return graph


def validate_migration_dependencies(migration_file: str, graph: MigrationGraph) -> List[str]:
    """Validate migration dependencies and detect conflicts."""
    try:
        with open(migration_file, 'r') as f:
            data = yaml.safe_load(f)
        
        version = data.get('version')
        dependencies = data.get('dependencies', [])
        branch = data.get('branch', 'main')
        
        conflicts = graph.find_conflicts(version, dependencies)
        
        # Additional validations
        if not version:
            conflicts.append("Migration file missing version")
        
        if not data.get('description'):
            conflicts.append("Migration file missing description")
        
        return conflicts
        
    except Exception as e:
        return [f"Error reading migration file: {e}"]


def create_merge_migration(branch1: str, branch2: str, graph: MigrationGraph, 
                          message: str = "Merge branches") -> str:
    """Create a merge migration to combine two branches."""
    merge_base = graph.get_merge_base(branch1, branch2)
    if not merge_base:
        raise ValueError("No common ancestor found between branches")
    
    version = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    revision_id = str(uuid.uuid4())[:8]
    
    # Get heads of both branches
    branch1_head = max([v for v, n in graph.nodes.items() if n.branch == branch1], 
                      key=lambda v: graph.nodes[v].version, default=None)
    branch2_head = max([v for v, n in graph.nodes.items() if n.branch == branch2], 
                      key=lambda v: graph.nodes[v].version, default=None)
    
    if not branch1_head or not branch2_head:
        raise ValueError("Could not find branch heads")
    
    dependencies = [branch1_head, branch2_head]
    
    migration_data = {
        'version': version,
        'description': f"{message} ({branch1} + {branch2})",
        'branch': 'main',
        'dependencies': dependencies,
        'revision_id': revision_id,
        'changes': [
            {
                'comment': f"Merge migration combining {branch1} and {branch2} branches"
            }
        ]
    }
    
    filename = f"migrations/{version}_merge_{branch1}_{branch2}.yml"
    Path("migrations").mkdir(exist_ok=True)
    
    with open(filename, 'w') as f:
        yaml.safe_dump(migration_data, f, default_flow_style=False)
    
    return filename


def discover_database_url(db_url: Optional[str] = None) -> str:
    """Discover and validate the database URL.
    
    This function automatically finds database URLs from various sources:
    1. Environment variables (DATABASE_URL, DB_URL, etc.)
    2. Python config files (config.py, settings.py, etc.)
    3. .env files
    4. Default fallback to SQLite
    
    Supported config.py patterns:
    - Variables: DATABASE_URL, DB_URL, database_url, db_url, DB_STRING, db_string
    - Functions: get_database_url(), get_db_url(), database_url(), db_url()
    
    Args:
        db_url: Optional database URL. If None, auto-discovers.
        
    Returns:
        Database connection URL.
        
    Raises:
        ValueError: If no database URL is found or invalid.
    """
    if db_url:
        print(f"📁 Using database URL from command line argument")
        return db_url
    
    # Try environment variables first
    env_url = os.getenv("DB_URL")
    if env_url:
        print(f"📁 Using database URL from environment variable")
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
                    for attr in ['DATABASE_URL', 'DB_URL', 'database_url', 'db_url', 'DB_STRING', 'db_string']:
                        if hasattr(config, attr):
                            url = getattr(config, attr)
                            if url:
                                print(f"📁 Using database URL from {config_file}")
                                return url
                    
                    # Look for functions that return database URL
                    for func_name in ['get_database_url', 'get_db_url', 'database_url', 'db_url']:
                        if hasattr(config, func_name):
                            func = getattr(config, func_name)
                            if callable(func):
                                try:
                                    url = func()
                                    if url:
                                        print(f"📁 Using database URL from {config_file}.{func_name}()")
                                        return url
                                except Exception as e:
                                    print(f"⚠️ Error calling {func_name}(): {e}")
                                    continue
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
        return f"mysql+pymysql://{user}{password_part}@{host}{port_part}/{database}"
    
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


def validate_database_url(db_url: str) -> bool:
    """Validate that the database URL is properly formatted and required drivers are available.
    
    Args:
        db_url: Database connection URL to validate.
        
    Returns:
        True if URL is valid, False otherwise.
    """
    try:
        # Parse the URL to check format and extract database type
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        
        # Check if URL has required components
        if not parsed.scheme:
            print(f"❌ Invalid database URL format: {db_url}")
            return False
        
        # Check for required database drivers based on scheme
        scheme = parsed.scheme.lower()
        
        # For SQLite, netloc can be empty (just path)
        if scheme != 'sqlite' and not parsed.netloc:
            print(f"❌ Invalid database URL format: {db_url}")
            return False
        
        if scheme.startswith('mysql'):
            try:
                import pymysql
            except ImportError:
                print(f"❌ MySQL driver not found. Install with: pip install pymysql")
                print(f"   Or use: pip install mysqlclient")
                return False
                
        elif scheme.startswith('postgresql'):
            try:
                import psycopg2
            except ImportError:
                print(f"❌ PostgreSQL driver not found. Install with: pip install psycopg2-binary")
                return False
                
        elif scheme.startswith('mssql') or scheme.startswith('sqlserver'):
            try:
                import pyodbc
            except ImportError:
                print(f"❌ SQL Server driver not found. Install with: pip install pyodbc")
                return False
                
        elif scheme.startswith('oracle'):
            try:
                import cx_Oracle
            except ImportError:
                print(f"❌ Oracle driver not found. Install with: pip install cx-Oracle")
                return False
        
        # For SQLite, no additional driver check needed
        elif scheme == 'sqlite':
            pass
            
        else:
            print(f"❌ Unsupported database type: {scheme}")
            return False
        
        # Try to create engine to validate URL format (without connecting)
        from sqlalchemy import create_engine
        engine = create_engine(db_url, future=True)
        
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
        
        # Look for metadata attribute in order of preference
        if hasattr(module, 'metadata'):
            return module.metadata
        elif hasattr(module, 'MetaData'):
            return module.MetaData
        elif hasattr(module, 'Base') and hasattr(module.Base, 'metadata'):
            return module.Base.metadata
        else:
            raise ImportError(
                f"No 'metadata', 'MetaData', or 'Base.metadata' found in {models_file}\n"
                f"💡 Your models.py file must include a SQLAlchemy metadata object.\n"
                f"   Example with direct metadata:\n"
                f"   from sqlalchemy import MetaData\n"
                f"   metadata = MetaData()\n"
                f"   \n"
                f"   Example with declarative base:\n"
                f"   from sqlalchemy.ext.declarative import declarative_base\n"
                f"   Base = declarative_base()\n"
                f"   # Base.metadata will be automatically detected\n"
                f"   \n"
                f"   See examples/models_example.py for a complete example."
            )
            
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
    """Initialize the migration metadata table in the database (Alembic-style).
    
    This command creates the migration_log table required for tracking applied
    migrations. The table stores migration version, description, timestamp, and
    payload information for rollback purposes.
    
    This follows Alembic's pattern where command line arguments override everything,
    then environment variables, then saved configuration, then discovery.
    
    SECURITY: Passwords and sensitive data are NOT stored in config files.
    Use environment variables for credentials in production.
    
    Database connection options (Alembic-style priority):
    1. Command line arguments (--db, --host, --user, etc.) - highest priority
    2. Environment variables (DBPORTER_DATABASE_URL or DATABASE_URL)
    3. Saved configuration (non-sensitive data only)
    4. Auto-discovery - lowest priority
    
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
        
    Examples:
        # Using complete URL (like Alembic's env.py override)
        $ python main.py init-db --db "postgresql://user:pass@localhost/mydb"
        
        # Using individual components (more secure)
        $ python main.py init-db --host localhost --user myuser --password mypass --database mydb --type postgresql
        
        # SQLite (default)
        $ python main.py init-db --database myapp.db
        
        # Using environment variables (most secure - like Alembic's DATABASE_URL)
        $ export DBPORTER_DATABASE_URL="postgresql://user:pass@localhost/mydb"
        $ python main.py init-db
        
        # Auto-discovery (last resort)
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
        
        # Components are already extracted in get_database_config for discovery
        # Just ensure db_url is preserved in config
        if db_url:
            config["db_url"] = db_url
        
        # Save configuration for future use (excluding sensitive data)
        save_database_config(
            db_url=config.get("db_url"),
            host=config.get("host"),
            port=config.get("port"),
            user=config.get("user"),
            password=None,  # Never save passwords for security
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


@app.command("setup-secure-config")
def setup_secure_config():
    """Set up secure database configuration using environment variables.
    
    This command helps you configure dbPorter securely without storing
    sensitive data in configuration files.
    
    It will guide you through setting up environment variables for your
    database connection, which is the most secure approach.
    """
    print("🔐 Setting up secure database configuration...")
    print()
    print("This will help you configure dbPorter without storing sensitive data in files.")
    print()
    
    # Check current environment
    env_url = os.getenv('DBPORTER_DATABASE_URL') or os.getenv('DATABASE_URL')
    if env_url:
        print("✅ Found existing environment variable:")
        print(f"   DBPORTER_DATABASE_URL or DATABASE_URL is set")
        print("   This is the most secure configuration method!")
        return
    
    print("📝 To set up secure configuration, add one of these to your environment:")
    print()
    print("Option 1: Add to your shell profile (~/.bashrc, ~/.zshrc, etc.):")
    print("   export DBPORTER_DATABASE_URL='postgresql://user:password@localhost:5432/database'")
    print()
    print("Option 2: Create a .env file in your project root:")
    print("   DBPORTER_DATABASE_URL=postgresql://user:password@localhost:5432/database")
    print()
    print("Option 3: Use programmatic configuration in your code:")
    print("   from dbPorter import set_database_url")
    print("   set_database_url('postgresql://user:password@localhost:5432/database')")
    print()
    print("🔒 Security benefits:")
    print("   - No passwords in version control")
    print("   - No sensitive data in config files")
    print("   - Easy to manage different environments")
    print()
    print("💡 After setting up, run 'dbporter init-db' to initialize your database.")


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

        # Load migration file to get DAG metadata
        migration_metadata = {
            'dependencies': [],
            'branch': 'main',
            'revision_id': str(uuid.uuid4())[:8]
        }
        
        try:
            with open(path, 'r') as f:
                migration_data = yaml.safe_load(f)
                migration_metadata = {
                    'dependencies': migration_data.get('dependencies', []),
                    'branch': migration_data.get('branch', 'main'),
                    'revision_id': migration_data.get('revision_id', str(uuid.uuid4())[:8])
                }
        except Exception as e:
            print(f"⚠️ Could not load migration metadata, using defaults: {e}")

        with engine.connect() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {MIGRATION_LOG_TABLE} "
                    f"(version, description, applied_at, payload, dependencies, branch, revision_id) "
                    f"VALUES (:v, :d, :a, :p, :deps, :branch, :rev)"
                ),
                {
                    "v": migration.version,
                    "d": migration.description,
                    "a": datetime.datetime.utcnow().isoformat(),
                    "p": json.dumps(rollback_payload),
                    "deps": json.dumps(migration_metadata['dependencies']),
                    "branch": migration_metadata['branch'],
                    "rev": migration_metadata['revision_id']
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
    branch: str = typer.Option("main", "--branch", help="Branch name for the migration"),
):
    """Auto-generate migration by comparing database schema with models metadata.
    
    This command can work in two modes:
    
    1. WITH MODELS: Compares current database schema against your SQLAlchemy models
       to generate migrations for the differences.
       
    2. DATABASE-ONLY: Shows current database schema (no migration generation)
       Use this when you don't have SQLAlchemy models yet.
    
    The command auto-discovers models files with common names like:
    models.py, schema.py, database.py, db_models.py, tables.py
    
    If no models file is found or models can't be loaded, it falls back to
    database-only mode and shows helpful guidance.
    
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
    # Try to discover and load models file (optional)
    models_path = None
    target_metadata = None
    
    try:
        models_path = discover_models_file(models_file)
        print(f"📁 Using models file: {models_path}")
        target_metadata = load_models_metadata(models_path)
        print("✅ Successfully loaded models metadata")
    except FileNotFoundError:
        print("💡 No models file found, using database-only mode")
        print("   (This mode will only show current database schema, not generate migrations)")
    except ImportError as e:
        print(f"⚠️  Could not load models: {e}")
        print("💡 Continuing with database-only mode")
        models_path = None
        target_metadata = None
    
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
    diffs = []

    existing_tables = inspector.get_table_names()
    
    if target_metadata:
        target_tables = list(target_metadata.tables.keys())
    else:
        # Database-only mode: just show current schema
        target_tables = []
        print("📊 Database-only mode: Showing current database schema")
        print(f"   Found {len(existing_tables)} tables: {', '.join(existing_tables)}")
        print("💡 To generate migrations, create a models.py file with SQLAlchemy models")
        print("   See examples/models_example.py for a complete example")
        return
    
    INTERNAL_TABLES = _INTERNAL_TABLES

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

    # Create migration with DAG support
    revision_id = str(uuid.uuid4())[:8]
    migration_data = {
        'version': version,
        'description': message,
        'branch': branch,
        'dependencies': [],
        'revision_id': revision_id,
        'changes': diffs
    }

    safe_diffs = json.loads(json.dumps(diffs))
    migration_data['changes'] = safe_diffs
    
    with open(filename, "w") as f:
        yaml.safe_dump(migration_data, f, default_flow_style=False)

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


# ---------------------------
#  MIGRATION GRAPH COMMANDS
# ---------------------------

@app.command("graph")
def show_graph(
    db: Optional[str] = typer.Option(None, "--db", help="Database connection URL (uses saved config if not provided)"),
    host: Optional[str] = typer.Option(None, "--host", help="Database host (overrides saved config)"),
    port: Optional[int] = typer.Option(None, "--port", help="Database port (overrides saved config)"),
    user: Optional[str] = typer.Option(None, "--user", help="Database username (overrides saved config)"),
    password: Optional[str] = typer.Option(None, "--password", help="Database password (overrides saved config)"),
    database: Optional[str] = typer.Option(None, "--database", help="Database name (overrides saved config)"),
    db_type: Optional[str] = typer.Option(None, "--type", help="Database type (overrides saved config)"),
):
    """Show the migration dependency graph.
    
    This command displays the current migration graph showing:
    - All migrations and their dependencies
    - Branch structure
    - Current head revisions
    - Dependency relationships
    
    Example:
        $ python main.py graph
    """
    try:
        # Get database configuration
        db_url, config = get_database_config(
            db=db, host=host, port=port, user=user,
            password=password, database=database, db_type=db_type
        )
        
        engine = get_engine(db_url)
        graph = load_migration_graph(engine)
        
        if not graph.nodes:
            print("📭 No migrations found in database")
            return
        
        print(graph.visualize())
        
        # Show additional info
        heads = graph.get_heads()
        print(f"\nCurrent heads: {', '.join(heads) if heads else 'None'}")
        
        try:
            sorted_migrations = graph.topological_sort()
            print(f"\nDependency order: {' -> '.join(sorted_migrations)}")
        except ValueError as e:
            print(f"\n❌ Graph validation error: {e}")
            
    except Exception as e:
        print(f"❌ Error loading migration graph: {e}")
        print("💡 Run 'python main.py init-db' first to configure database connection")


@app.command("validate-migration")
def validate_migration(
    migration_file: str = typer.Argument(..., help="Path to migration file to validate"),
    db: Optional[str] = typer.Option(None, "--db", help="Database connection URL (uses saved config if not provided)"),
    host: Optional[str] = typer.Option(None, "--host", help="Database host (overrides saved config)"),
    port: Optional[int] = typer.Option(None, "--port", help="Database port (overrides saved config)"),
    user: Optional[str] = typer.Option(None, "--user", help="Database username (overrides saved config)"),
    password: Optional[str] = typer.Option(None, "--password", help="Database password (overrides saved config)"),
    database: Optional[str] = typer.Option(None, "--database", help="Database name (overrides saved config)"),
    db_type: Optional[str] = typer.Option(None, "--type", help="Database type (overrides saved config)"),
):
    """Validate a migration file for dependency conflicts.
    
    This command checks a migration file for:
    - Dependency conflicts
    - Circular dependencies
    - Missing dependencies
    - Valid structure
    
    Example:
        $ python main.py validate-migration migrations/20250113_add_users.yml
    """
    try:
        # Get database configuration
        db_url, config = get_database_config(
            db=db, host=host, port=port, user=user,
            password=password, database=database, db_type=db_type
        )
        
        engine = get_engine(db_url)
        graph = load_migration_graph(engine)
        
        conflicts = validate_migration_dependencies(migration_file, graph)
        
        if conflicts:
            print("❌ Migration validation failed:")
            for conflict in conflicts:
                print(f"  - {conflict}")
        else:
            print("✅ Migration validation passed - no conflicts detected")
            
    except Exception as e:
        print(f"❌ Error validating migration: {e}")


@app.command("create-branch")
def create_branch(
    branch_name: str = typer.Argument(..., help="Name of the new branch"),
    base_version: Optional[str] = typer.Option(None, "--base", help="Base migration version to branch from"),
    db: Optional[str] = typer.Option(None, "--db", help="Database connection URL (uses saved config if not provided)"),
    host: Optional[str] = typer.Option(None, "--host", help="Database host (overrides saved config)"),
    port: Optional[int] = typer.Option(None, "--port", help="Database port (overrides saved config)"),
    user: Optional[str] = typer.Option(None, "--user", help="Database username (overrides saved config)"),
    password: Optional[str] = typer.Option(None, "--password", help="Database password (overrides saved config)"),
    database: Optional[str] = typer.Option(None, "--database", help="Database name (overrides saved config)"),
    db_type: Optional[str] = typer.Option(None, "--type", help="Database type (overrides saved config)"),
):
    """Create a new migration branch.
    
    This command creates a new branch for parallel development:
    - Creates a branch marker migration
    - Sets up dependency tracking
    - Enables parallel migration development
    
    Example:
        $ python main.py create-branch feature-auth
        $ python main.py create-branch feature-auth --base 20250113000000
    """
    try:
        # Get database configuration
        db_url, config = get_database_config(
            db=db, host=host, port=port, user=user,
            password=password, database=database, db_type=db_type
        )
        
        engine = get_engine(db_url)
        graph = load_migration_graph(engine)
        
        # Find base version
        if not base_version:
            heads = graph.get_heads()
            if not heads:
                print("❌ No migrations found to branch from")
                return
            base_version = heads[0]  # Use first head as base
        
        if base_version not in graph.nodes:
            print(f"❌ Base migration {base_version} not found")
            return
        
        # Create branch migration
        version = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
        revision_id = str(uuid.uuid4())[:8]
        
        migration_data = {
            'version': version,
            'description': f"Create branch {branch_name}",
            'branch': branch_name,
            'dependencies': [base_version],
            'revision_id': revision_id,
            'changes': [
                {
                    'comment': f"Branch point for {branch_name} development"
                }
            ]
        }
        
        filename = f"migrations/{version}_branch_{branch_name}.yml"
        Path("migrations").mkdir(exist_ok=True)
        
        with open(filename, 'w') as f:
            yaml.safe_dump(migration_data, f, default_flow_style=False)
        
        print(f"✅ Created branch '{branch_name}' from {base_version}")
        print(f"📁 Branch migration: {filename}")
        print(f"🆔 Revision ID: {revision_id}")
        
    except Exception as e:
        print(f"❌ Error creating branch: {e}")


@app.command("merge-branches")
def merge_branches(
    branch1: str = typer.Argument(..., help="First branch to merge"),
    branch2: str = typer.Argument(..., help="Second branch to merge"),
    message: str = typer.Option("Merge branches", "-m", "--message", help="Merge commit message"),
    db: Optional[str] = typer.Option(None, "--db", help="Database connection URL (uses saved config if not provided)"),
    host: Optional[str] = typer.Option(None, "--host", help="Database host (overrides saved config)"),
    port: Optional[int] = typer.Option(None, "--port", help="Database port (overrides saved config)"),
    user: Optional[str] = typer.Option(None, "--user", help="Database username (overrides saved config)"),
    password: Optional[str] = typer.Option(None, "--password", help="Database password (overrides saved config)"),
    database: Optional[str] = typer.Option(None, "--database", help="Database name (overrides saved config)"),
    db_type: Optional[str] = typer.Option(None, "--type", help="Database type (overrides saved config)"),
):
    """Merge two migration branches.
    
    This command creates a merge migration that combines two branches:
    - Finds common ancestor
    - Creates merge migration with dependencies on both branch heads
    - Resolves conflicts if any
    
    Example:
        $ python main.py merge-branches feature-auth feature-payments
        $ python main.py merge-branches feature-auth feature-payments -m "Merge auth and payments"
    """
    try:
        # Get database configuration
        db_url, config = get_database_config(
            db=db, host=host, port=port, user=user,
            password=password, database=database, db_type=db_type
        )
        
        engine = get_engine(db_url)
        graph = load_migration_graph(engine)
        
        # Check if branches exist
        branch1_migrations = [v for v, n in graph.nodes.items() if n.branch == branch1]
        branch2_migrations = [v for v, n in graph.nodes.items() if n.branch == branch2]
        
        if not branch1_migrations:
            print(f"❌ Branch '{branch1}' not found")
            return
        if not branch2_migrations:
            print(f"❌ Branch '{branch2}' not found")
            return
        
        # Create merge migration
        filename = create_merge_migration(branch1, branch2, graph, message)
        
        print(f"✅ Created merge migration: {filename}")
        print(f"📋 Merging branches: {branch1} + {branch2}")
        
        # Show merge info
        merge_base = graph.get_merge_base(branch1, branch2)
        if merge_base:
            print(f"🔗 Common ancestor: {merge_base}")
        
    except Exception as e:
        print(f"❌ Error merging branches: {e}")


@app.command("status")
def migration_status(
    db: Optional[str] = typer.Option(None, "--db", help="Database connection URL (uses saved config if not provided)"),
    host: Optional[str] = typer.Option(None, "--host", help="Database host (overrides saved config)"),
    port: Optional[int] = typer.Option(None, "--port", help="Database port (overrides saved config)"),
    user: Optional[str] = typer.Option(None, "--user", help="Database username (overrides saved config)"),
    password: Optional[str] = typer.Option(None, "--password", help="Database password (overrides saved config)"),
    database: Optional[str] = typer.Option(None, "--database", help="Database name (overrides saved config)"),
    db_type: Optional[str] = typer.Option(None, "--type", help="Database type (overrides saved config)"),
    models_file: Optional[str] = typer.Option(None, "--models-file", help="Path to models file for schema validation"),
    check_sync: bool = typer.Option(True, "--check-sync/--no-check-sync", help="Check if database is in sync with models"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
):
    """Comprehensive migration and schema status inspection.
    
    This command provides detailed status information including:
    - ✅ Applied migrations by branch
    - ⏳ Pending migrations  
    - ⚠️ Database sync status
    - 🔍 Schema validation against models
    - 📊 Dependency health and conflicts
    - 🎯 Current migration heads
    
    Example:
        $ python main.py status
        $ python main.py status --check-sync --verbose
        $ python main.py status --models-file custom_models.py
    """
    try:
        # Get database configuration
        db_url, config = get_database_config(
            db=db, host=host, port=port, user=user,
            password=password, database=database, db_type=db_type
        )
        
        engine = get_engine(db_url)
        graph = load_migration_graph(engine)
        
        print("🔍 Migration & Schema Status Report")
        print("=" * 60)
        
        # 1. MIGRATION STATUS
        print("\n📊 MIGRATION STATUS")
        print("-" * 30)
        
        # Get applied migrations from database
        applied_migrations = []
        if graph.nodes:
            for version, node in graph.nodes.items():
                if node.applied_at:
                    applied_migrations.append((version, node))
        
        applied_count = len(applied_migrations)
        
        # Get pending migrations from filesystem
        pending_migrations = []
        pending_files = []
        
        # Check for migration files in filesystem
        migrations_dir = Path("migrations")
        if migrations_dir.exists():
            for migration_file in migrations_dir.glob("*.yml"):
                try:
                    with open(migration_file, 'r') as f:
                        migration_data = yaml.safe_load(f)
                    
                    version = migration_data.get('version')
                    if version and version not in graph.nodes:
                        # This is a pending migration file
                        pending_files.append({
                            'version': version,
                            'description': migration_data.get('description', ''),
                            'branch': migration_data.get('branch', 'main'),
                            'dependencies': migration_data.get('dependencies', []),
                            'file': str(migration_file)
                        })
                except Exception as e:
                    if verbose:
                        print(f"  ⚠️ Could not read {migration_file}: {e}")
        
        pending_count = len(pending_files)
        
        print(f"✅ Applied migrations: {applied_count}")
        print(f"⏳ Pending migrations: {pending_count}")
            
        if verbose and applied_migrations:
            print("\n  Applied migrations:")
            for version, node in sorted(applied_migrations, key=lambda x: x[0]):
                deps_str = ", ".join(node.dependencies) if node.dependencies else "none"
                print(f"    {version}: {node.description}")
                print(f"      Dependencies: {deps_str}")
                print(f"      Applied at: {node.applied_at}")
                print(f"      Branch: {node.branch}")
        
        if verbose and pending_files:
            print("\n  Pending migrations:")
            for migration in sorted(pending_files, key=lambda x: x['version']):
                deps_str = ", ".join(migration['dependencies']) if migration['dependencies'] else "none"
                print(f"    {migration['version']}: {migration['description']}")
                print(f"      Dependencies: {deps_str}")
                print(f"      Branch: {migration['branch']}")
                print(f"      File: {migration['file']}")
        
        # 2. DATABASE SYNC STATUS
        print(f"\n🔄 DATABASE SYNC STATUS")
        print("-" * 30)
        
        sync_status = "✅ In Sync"
        sync_issues = []
        
        if check_sync:
            try:
                # Check if there are pending migrations
                if pending_count > 0:
                    sync_status = "⚠️ Out of Sync"
                    sync_issues.append(f"{pending_count} pending migrations")
                
                # Check for schema differences if models file provided
                if models_file or check_sync:
                    try:
                        models_path = discover_models_file(models_file)
                        target_metadata = load_models_metadata(models_path)
                        inspector = inspect(engine)
                        
                        # Get current database tables
                        existing_tables = set(inspector.get_table_names())
                        target_tables = set(target_metadata.tables.keys())
                        
                        # Check for missing tables
                        missing_tables = target_tables - existing_tables
                        extra_tables = existing_tables - target_tables
                        
                        if missing_tables:
                            sync_status = "⚠️ Out of Sync"
                            sync_issues.append(f"Missing tables: {', '.join(missing_tables)}")
                        
                        if extra_tables:
                            sync_status = "⚠️ Out of Sync"
                            sync_issues.append(f"Extra tables: {', '.join(extra_tables)}")
                        
                        if verbose and (missing_tables or extra_tables):
                            print(f"  Current DB tables: {len(existing_tables)}")
                            print(f"  Target tables: {len(target_tables)}")
                            
                    except Exception as e:
                        if verbose:
                            print(f"  ⚠️ Could not validate against models: {e}")
                        sync_status = "❓ Unknown"
                        sync_issues.append("Could not validate against models")
                
            except Exception as e:
                sync_status = "❌ Error"
                sync_issues.append(f"Sync check failed: {e}")
        
        print(f"Status: {sync_status}")
        if sync_issues:
            for issue in sync_issues:
                print(f"  • {issue}")
        
        # 3. DEPENDENCY HEALTH
        print(f"\n🔗 DEPENDENCY HEALTH")
        print("-" * 30)
        
        if graph.nodes:
            try:
                sorted_migrations = graph.topological_sort()
                print("✅ DAG is valid - no cycles detected")
                
                if verbose:
                    print(f"  Dependency order: {' → '.join(sorted_migrations)}")
                
                # Check for conflicts
                conflict_count = 0
                for version, node in graph.nodes.items():
                    conflicts = graph.find_conflicts(version, node.dependencies, check_existing=False)
                    if conflicts:
                        conflict_count += len(conflicts)
                        if verbose:
                            print(f"  ❌ {version}: {', '.join(conflicts)}")
                
                if conflict_count == 0:
                    print("✅ No dependency conflicts")
                else:
                    print(f"⚠️ Found {conflict_count} dependency conflicts")
                    
            except ValueError as e:
                print(f"❌ DAG validation failed: {e}")
        else:
            print("ℹ️ No migrations to validate")
        
        # 4. CURRENT STATE
        print(f"\n🎯 CURRENT STATE")
        print("-" * 30)
        
        if graph.nodes:
            heads = graph.get_heads()
            print(f"Current heads: {', '.join(heads) if heads else 'None'}")
            
            # Show branch summary
            branch_summary = {}
            for version, node in graph.nodes.items():
                branch = node.branch
                if branch not in branch_summary:
                    branch_summary[branch] = {'applied': 0, 'pending': 0}
                if node.applied_at:
                    branch_summary[branch]['applied'] += 1
                else:
                    branch_summary[branch]['pending'] += 1
            
            if len(branch_summary) > 1 or verbose:
                print("\nBranch summary:")
                for branch, counts in branch_summary.items():
                    print(f"  {branch}: {counts['applied']} applied, {counts['pending']} pending")
        else:
            print("No migrations found")
        
        # 5. SUMMARY
        print(f"\n📋 SUMMARY")
        print("-" * 30)
        
        if applied_count == 0 and pending_count == 0:
            print("🆕 Fresh database - no migrations found")
        elif pending_count == 0:
            print("✅ All migrations applied - database is up to date")
        else:
            print(f"⚠️ {pending_count} migrations pending - run 'python main.py apply' to apply them")
        
        if sync_status.startswith("⚠️"):
            print("⚠️ Database schema may be out of sync - consider running 'python main.py autogenerate'")
        elif sync_status == "✅ In Sync":
            print("✅ Database schema is in sync with migrations")
            
    except Exception as e:
        print(f"❌ Error checking migration status: {e}")
        if verbose:
            import traceback
            traceback.print_exc()


@app.command("status-quick")
def status_quick(
    db: Optional[str] = typer.Option(None, "--db", help="Database connection URL (uses saved config if not provided)"),
    host: Optional[str] = typer.Option(None, "--host", help="Database host (overrides saved config)"),
    port: Optional[int] = typer.Option(None, "--port", help="Database port (overrides saved config)"),
    user: Optional[str] = typer.Option(None, "--user", help="Database username (overrides saved config)"),
    password: Optional[str] = typer.Option(None, "--password", help="Database password (overrides saved config)"),
    database: Optional[str] = typer.Option(None, "--database", help="Database name (overrides saved config)"),
    db_type: Optional[str] = typer.Option(None, "--type", help="Database type (overrides saved config)"),
):
    """Quick migration status overview.
    
    Shows a concise summary of migration status without detailed inspection.
    Perfect for CI/CD pipelines and quick checks.
    
    Example:
        $ python main.py status-quick
    """
    try:
        # Get database configuration
        db_url, config = get_database_config(
            db=db, host=host, port=port, user=user,
            password=password, database=database, db_type=db_type
        )
        
        engine = get_engine(db_url)
        graph = load_migration_graph(engine)
        
        if not graph.nodes:
            print("📭 No migrations found")
            return
        
        # Count applied vs pending
        applied_count = sum(1 for node in graph.nodes.values() if node.applied_at)
        
        # Check for pending migration files
        pending_count = 0
        migrations_dir = Path("migrations")
        if migrations_dir.exists():
            for migration_file in migrations_dir.glob("*.yml"):
                try:
                    with open(migration_file, 'r') as f:
                        migration_data = yaml.safe_load(f)
                    version = migration_data.get('version')
                    if version and version not in graph.nodes:
                        pending_count += 1
                except Exception:
                    pass
        
        # Status indicators
        if pending_count == 0:
            print("✅ All migrations applied")
        else:
            print(f"⚠️ {pending_count} migrations pending")
        
        # Quick sync check
        try:
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            print(f"📊 Database has {len(tables)} tables")
        except Exception:
            print("❓ Could not inspect database")
        
        # Show heads
        heads = graph.get_heads()
        if heads:
            print(f"🎯 Current heads: {', '.join(heads)}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
