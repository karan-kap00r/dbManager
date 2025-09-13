# dbPorter - Database Migration Tool

A powerful, flexible database migration tool built with Python that supports both YAML-based declarative migrations and Python-based programmatic migrations. This tool provides comprehensive schema management capabilities with automatic rollback support and metadata preservation.

## 🚀 Features

- **Dual Migration Support**: YAML-based declarative migrations and Python-based programmatic migrations
- **Migration Graph (DAG)**: Support for branching migrations with dependency management like Alembic
- **Automatic Rollback**: Intelligent rollback system with metadata preservation for safe reversions
- **Schema Auto-Generation**: Automatically detect and generate migrations from schema differences
- **Enhanced Metadata**: Captures column metadata for accurate rollback operations
- **Table Rename Support**: Handle table renames with mapping configuration
- **Dry-Run Capability**: Preview migration changes before applying them
- **Comprehensive Logging**: Track all applied migrations with detailed payload information
- **Multiple Database Support**: Works with any SQLAlchemy-supported database
- **Parallel Development**: Support for multiple developers working on migrations simultaneously
- **Conflict Detection**: Automatic detection and resolution of migration conflicts
- **Schema Inspection**: Comprehensive database and migration status inspection with visual indicators
- **Sync Validation**: Automatic detection of database schema sync issues

## 📋 Prerequisites

- **Python 3.8+** (Python 3.9+ recommended)
- **Core Dependencies**: SQLAlchemy, PyYAML, Typer, python-dotenv, tabulate
- **Database Driver**: Choose based on your database:
  - **SQLite**: No additional driver needed (included with Python)
  - **PostgreSQL**: `psycopg2-binary` or `psycopg2`
  - **MySQL**: `PyMySQL` or `mysqlclient`
  - **SQL Server**: `pyodbc` or `pymssql`
  - **Oracle**: `cx-Oracle`

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd dbPorter
   ```

2. **Install dependencies**
   
   **Option A: Automated installation (recommended)**
   ```bash
   # For SQLite (default)
   python install.py
   
   # For PostgreSQL
   python install.py --database postgresql
   
   # For MySQL
   python install.py --database mysql
   
   # For development
   python install.py --dev
   ```
   
   **Option B: Manual installation**
   ```bash
   # Full installation (recommended)
   pip install -r requirements.txt
   
   # Minimal installation (SQLite only)
   pip install -r requirements-minimal.txt
   
   # Development installation
   pip install -r requirements-dev.txt
   ```
   
   **Option C: Quick installation**
   ```bash
   pip install sqlalchemy pyyaml typer python-dotenv tabulate
   ```

3. **Set up database configuration (optional)**
   The tool auto-discovers database URLs from multiple sources:
   
   **Option A: Environment Variables**
   ```bash
   export DB_URL="sqlite:///your_database.db"
   # or for PostgreSQL: postgresql://user:password@localhost/dbname
   # or for MySQL: mysql://user:password@localhost/dbname
   ```
   
   **Option B: .env file**
   Create a `.env` file in the project root:
   ```env
   DB_URL=sqlite:///your_database.db
   DATABASE_URL=postgresql://user:password@localhost/dbname
   ```
   
   **Option C: Configuration files**
   The tool also looks for database URLs in:
   - `config.py` (DATABASE_URL variable)
   - `settings.py` (DB_URL variable)
   - `database.py` (database_url variable)
   
   **Option D: Default fallback**
   If no database URL is found, defaults to `sqlite:///migrate.db`

## 🏗️ Project Structure

```
dbPorter/
├── main.py                 # Entry point
├── commands.py             # CLI commands implementation
├── models.py              # SQLAlchemy metadata definitions
├── migrations/            # Migration files directory
│   ├── *.yml             # YAML migration files
│   └── *.py              # Python migration files
├── src/                  # Core migration logic
│   ├── applier.py        # Migration application logic
│   ├── db.py             # Database connection and metadata
│   ├── executors.py      # SQL operation executors
│   ├── migration_loader.py # Migration file parsing
│   └── planner.py        # Migration planning logic
└── utils/                # Utility functions
    └── utils.py          # Helper functions
```

## 🚀 Quick Start

1. **Initialize the migration system**
   ```bash
   python main.py init-db
   ```

2. **Define your schema in a models file**
   ```python
   # models.py, schema.py, database.py, or any Python file
   from sqlalchemy import Table, Column, Integer, String, MetaData
   
   metadata = MetaData()
   
   users = Table(
       "users", metadata,
       Column("id", Integer, primary_key=True),
       Column("name", String(100), nullable=False),
       Column("email", String(255), unique=True)
   )
   ```

3. **Auto-generate your first migration**
   ```bash
   python main.py autogenerate -m "Initial schema"
   ```

4. **Apply the migration**
   ```bash
   python main.py apply
   ```

## 📖 Command Reference

### Database Initialization

```bash
# Initialize migration metadata table
python main.py init-db [--db DATABASE_URL]
```

### Migration Planning

```bash
# Plan a migration (dry-run)
python main.py plan [MIGRATION_FILE] [--rename-map RENAME_MAP_FILE]

# Examples:
python main.py plan                                    # Use latest migration
python main.py plan migrations/20250101120000_add_users.yml
python main.py plan --rename-map custom_renames.yml
```

### Migration Application

```bash
# Apply migrations
python main.py apply [MIGRATION_FILE] [OPTIONS]

# Options:
#   --db DATABASE_URL        Database connection string
#   --rename-map FILE        Table rename mapping file
#   --dry-run               Show what would be done without executing
#   --latest                Use the latest migration file

# Examples:
python main.py apply                                    # Apply latest migration
python main.py apply --latest                          # Explicitly use latest
python main.py apply --dry-run                         # Preview changes
python main.py apply migrations/20250101120000_add_users.yml
```

### Migration Rollback

```bash
# Rollback the last applied migration
python main.py rollback [--db DATABASE_URL]

# Examples:
python main.py rollback
python main.py rollback --db "postgresql://user:pass@localhost/db"
```

### Auto-Generation

```bash
# Auto-generate migration from schema differences
python main.py autogenerate [--db DATABASE_URL] [-m MESSAGE]

# Examples:
python main.py autogenerate
python main.py autogenerate -m "Add user profile table"
python main.py autogenerate --db "sqlite:///mydb.db"
```

### Migration Registration

```bash
# Register existing migration with timestamp
python main.py revision MIGRATION_FILE

# Example:
python main.py revision my_migration.yml
# Creates: migrations/20250101120000_my_migration.yml
```

### Models Discovery

```bash
# Discover and validate models files
python main.py discover-models [--models-file PATH]

# Examples:
python main.py discover-models                    # Auto-discover models file
python main.py discover-models --models-file "my_schema.py"
```

### Database Discovery

```bash
# Discover and validate database configuration
python main.py discover-db [--db URL]

# Examples:
python main.py discover-db                        # Auto-discover database URL
python main.py discover-db --db "postgresql://user:pass@localhost/db"
```

### One-Time Database Configuration

**Configure once, use everywhere!** Set up your database connection once during `init-db`, and all future commands will automatically use the same configuration.

#### **Step 1: Configure Database (One Time Only)**
```bash
# PostgreSQL (most common)
python main.py init-db --host localhost --port 5432 --user myuser --password mypass --database mydb --type postgresql

# MySQL
python main.py init-db --host localhost --port 3306 --user myuser --password mypass --database mydb --type mysql

# SQLite (no credentials needed)
python main.py init-db --database myapp.db --type sqlite

# Using complete URL
python main.py init-db --db "postgresql://user:pass@localhost/db"
```

#### **Step 2: Use Commands Without Database Parameters**
```bash
# All these commands automatically use the saved configuration!
python main.py apply
python main.py rollback
python main.py autogenerate -m "Add new table"
python main.py plan
```

#### **Configuration Management**
```bash
# Show current configuration
python main.py show-config

# Reset configuration (go back to auto-discovery)
python main.py reset-config
```

**Benefits:**
- ✅ **Configure Once**: Set database connection once during `init-db`
- ✅ **Use Everywhere**: All commands automatically use saved configuration
- ✅ **Override When Needed**: Can still override with command-line arguments
- ✅ **Secure**: Credentials stored in local config file (not in code)
- ✅ **Flexible**: Easy to change configuration anytime

## 🌳 Migration Graph (DAG) System

**Advanced dependency management for complex migration scenarios!** The tool now supports Directed Acyclic Graphs (DAG) for managing migration dependencies, enabling parallel development and complex branching scenarios.

### **Key DAG Features:**

#### **1. Dependency Management**
```yaml
# Migration with dependencies
version: '20250113120000'
description: Add user authentication system
branch: feature-auth
dependencies: ['20250113100000']  # Depends on previous migration
revision_id: 'abc12345'
changes:
  - add_table:
      name: users
      columns:
        - name: id
          type: INTEGER
          primary_key: true
        - name: username
          type: VARCHAR(50)
          unique: true
```

#### **2. Branch Support**
```bash
# Create a new migration branch
python main.py create-branch feature-auth

# Create a branch from specific migration
python main.py create-branch feature-payments --base 20250113100000
```

#### **3. Parallel Development**
```bash
# Developer A works on auth branch
python main.py autogenerate -m "Add user table" --branch feature-auth

# Developer B works on payments branch  
python main.py autogenerate -m "Add payment table" --branch feature-payments

# Both can work simultaneously without conflicts
```

#### **4. Merge Branches**
```bash
# Merge two branches when ready
python main.py merge-branches feature-auth feature-payments -m "Merge auth and payments"
```

### **DAG Commands:**

| Command | Description | Example |
|---------|-------------|---------|
| `graph` | Show migration dependency graph | `python main.py graph` |
| `validate-migration` | Validate migration for conflicts | `python main.py validate-migration migrations/20250113_add_users.yml` |
| `create-branch` | Create new migration branch | `python main.py create-branch feature-auth` |
| `merge-branches` | Merge two branches | `python main.py merge-branches feature-auth feature-payments` |
| `status` | Comprehensive migration & schema status | `python main.py status` |
| `status-quick` | Quick status overview | `python main.py status-quick` |

### **DAG Workflow Example:**

#### **Scenario: Multiple Developers Working in Parallel**

```bash
# 1. Initial setup
python main.py init-db --host localhost --user myuser --password mypass --database mydb --type postgresql

# 2. Developer A creates auth branch
python main.py create-branch feature-auth
python main.py autogenerate -m "Add users table" --branch feature-auth
python main.py apply migrations/20250113120000_add_users_table.yml

# 3. Developer B creates payments branch (from same base)
python main.py create-branch feature-payments
python main.py autogenerate -m "Add payments table" --branch feature-payments
python main.py apply migrations/20250113130000_add_payments_table.yml

# 4. Check migration graph
python main.py graph
# Output:
# Migration Graph:
# ==================================================
# 
# Branch: main
# --------------------
#   20250113100000: Initial schema
#     Dependencies: none
#     Revision ID: def45678
# 
# Branch: feature-auth
# --------------------
#   20250113120000: Add users table
#     Dependencies: 20250113100000
#     Revision ID: abc12345
# 
# Branch: feature-payments
# --------------------
#   20250113130000: Add payments table
#     Dependencies: 20250113100000
#     Revision ID: ghi78901

# 5. Merge branches when ready
python main.py merge-branches feature-auth feature-payments -m "Merge auth and payments"
python main.py apply migrations/20250113140000_merge_feature_auth_feature_payments.yml
```

### **DAG Benefits:**

- ✅ **Parallel Development**: Multiple developers can work on migrations simultaneously
- ✅ **Dependency Tracking**: Clear dependency relationships between migrations
- ✅ **Conflict Detection**: Automatic detection of migration conflicts
- ✅ **Branch Management**: Easy creation and merging of migration branches
- ✅ **Graph Visualization**: Visual representation of migration dependencies
- ✅ **Cycle Detection**: Prevents circular dependencies
- ✅ **Backward Compatible**: Existing linear migrations continue to work

## 🔍 Schema Inspection Utilities

**Comprehensive database and migration status inspection!** The tool provides powerful commands to inspect your database schema and migration status with clear visual indicators.

### **Status Commands:**

#### **1. Comprehensive Status (`status`)**
```bash
# Full status report with schema validation
python main.py status

# Verbose mode with detailed information
python main.py status --verbose

# Check against specific models file
python main.py status --models-file custom_models.py

# Skip sync checking for faster execution
python main.py status --no-check-sync
```

**Output Example:**
```
🔍 Migration & Schema Status Report
============================================================

📊 MIGRATION STATUS
------------------------------
✅ Applied migrations: 6
⏳ Pending migrations: 0

🔄 DATABASE SYNC STATUS
------------------------------
Status: ⚠️ Out of Sync
  • Extra tables: migration_log

🔗 DEPENDENCY HEALTH
------------------------------
✅ DAG is valid - no cycles detected
✅ No dependency conflicts

🎯 CURRENT STATE
------------------------------
Current heads: 20250913122220, 20250913122712

📋 SUMMARY
------------------------------
✅ All migrations applied - database is up to date
⚠️ Database schema may be out of sync - consider running 'python main.py autogenerate'
```

#### **2. Quick Status (`status-quick`)**
```bash
# Quick overview for CI/CD pipelines
python main.py status-quick
```

**Output Example:**
```
✅ All migrations applied
📊 Database has 5 tables
🎯 Current heads: 20250913122220, 20250913122712
```

### **Status Indicators:**

| Indicator | Meaning | Action Required |
|-----------|---------|-----------------|
| ✅ **Applied** | Migration successfully applied to database | None |
| ⏳ **Pending** | Migration exists but not applied | Run `python main.py apply` |
| ⚠️ **Out of Sync** | Database schema differs from models | Run `python main.py autogenerate` |
| ❌ **Error** | Migration or database error | Check logs and fix issues |
| ❓ **Unknown** | Cannot determine status | Check database connection |

### **Schema Validation Features:**

- **Table Comparison**: Compares current database tables with target models
- **Missing Tables**: Identifies tables that should exist but don't
- **Extra Tables**: Identifies tables that exist but aren't in models
- **Dependency Health**: Validates migration dependency graph
- **Conflict Detection**: Identifies migration conflicts and circular dependencies
- **Branch Summary**: Shows migration status by branch

### **Use Cases:**

#### **Development Workflow:**
```bash
# Check status before starting work
python main.py status

# Quick check during development
python main.py status-quick

# Detailed inspection when debugging
python main.py status --verbose
```

#### **CI/CD Pipeline:**
```bash
# Quick status check in CI
python main.py status-quick

# Full validation in staging
python main.py status --check-sync
```

#### **Production Monitoring:**
```bash
# Monitor migration status
python main.py status --no-check-sync

# Validate against production models
python main.py status --models-file production_models.py
```

## 📝 Migration File Formats

### YAML Migrations

YAML migrations use a declarative format for schema changes:

```yaml
version: '20250101120000'
description: Add users table with indexes
changes:
- create_table:
    table: users
    columns:
    - name: id
      type: INTEGER
      nullable: false
      primary_key: true
    - name: name
      type: VARCHAR(100)
      nullable: false
    - name: email
      type: VARCHAR(255)
      nullable: true
      unique: true

- add_index:
    table: users
    name: idx_users_email
    columns: [email]

- add_column:
    table: users
    column: created_at
    type: DATETIME
    nullable: true

- drop_column:
    table: users
    column: old_field
```

### Python Migrations

Python migrations provide full programmatic control:

```python
def upgrade(engine):
    """Apply the migration."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(255) UNIQUE
            )
        """))

def downgrade(engine):
    """Rollback the migration."""
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE users"))
```

## 🔄 Supported Operations

### Table Operations
- `create_table` / `drop_table`
- `rename_table`

### Column Operations
- `add_column` / `drop_column`
- `alter_column` (type changes, nullable modifications)

### Index Operations
- `add_index` / `drop_index`

### Advanced Features
- **Metadata Preservation**: All operations store metadata for accurate rollback
- **Table Rename Mapping**: Handle table renames with `rename_map.yml`
- **Enhanced Rollback**: Automatic reversal of all supported operations
- **Schema Validation**: Compare current schema with target schema

## ⚙️ Configuration

### 🔐 Programmatic Configuration (Security-Conscious)

For organizations that prefer not to store database credentials in files, you can set the database URL programmatically:

```python
# In your application code
from dbPorter import set_database_url

# Set database URL directly in code
set_database_url("postgresql://user:password@localhost:5432/mydatabase")

# Now all migration commands will use this URL automatically
# dbporter status
# dbporter apply migrations/20250101_add_users.yml
```

**Benefits:**
- ✅ **No credential files**: Database URL not stored on disk
- ✅ **Environment variables**: Can use `os.getenv("DATABASE_URL")`
- ✅ **Application integration**: Works with existing app configuration
- ✅ **CI/CD friendly**: Perfect for automated deployments
- ✅ **Multi-tenant ready**: Dynamic database URLs per tenant

**Example with environment variables:**
```python
import os
from dbPorter import set_database_url

# From environment variable
db_url = os.getenv("DATABASE_URL")
if db_url:
    set_database_url(db_url)
else:
    raise ValueError("DATABASE_URL environment variable not set")
```

### 🔄 Configuration Priority

The tool uses the following priority order for database configuration:

1. **Command-line arguments** (highest priority)
   ```bash
   dbporter status --db "postgresql://user:pass@host:port/db"
   ```

2. **Programmatic configuration** (security-conscious)
   ```python
   from dbPorter import set_database_url
   set_database_url("postgresql://user:pass@host:port/db")
   ```

3. **Saved configuration** (traditional)
   ```bash
   dbporter init-db --host localhost --user myuser --password mypass
   ```

4. **Environment variables** (fallback)
   ```bash
   export DB_URL="postgresql://user:pass@host:port/db"
   dbporter status
   ```

5. **Auto-discovery** (lowest priority)
   - Automatically detects database from common patterns

### 📁 File-Based Configuration (Traditional)

### Environment Variables

Create a `.env` file in your project root:

```env
# Database connection
DB_URL=sqlite:///your_database.db

# For PostgreSQL
# DB_URL=postgresql://username:password@localhost:5432/database_name

# For MySQL
# DB_URL=mysql://username:password@localhost:3306/database_name
```

### Table Rename Mapping

Create `rename_map.yml` to handle table renames:

```yaml
table_renames:
  old_table_name: new_table_name
  legacy_users: users
```

## 🔒 Safety Features

- **Transaction Support**: All migrations run in database transactions
- **Rollback Capability**: Every migration can be safely rolled back
- **Metadata Preservation**: Column types, constraints, and indexes are preserved
- **Dry-Run Mode**: Preview changes before applying
- **Migration Logging**: Complete audit trail of all applied migrations

## 🐛 Troubleshooting

### Common Issues

1. **Migration not found**
   ```bash
   # Ensure migration file exists and is properly formatted
   python main.py plan migrations/your_migration.yml
   ```

2. **Database connection failed**
   ```bash
   # Check your DB_URL in .env file
   python main.py init-db --db "sqlite:///test.db"
   ```

3. **Rollback failed**
   ```bash
   # Check migration log for the last applied migration
   # Ensure database is in a consistent state
   ```

### Debug Mode

Enable verbose logging by modifying the commands to include debug output:

```python
# Add logging configuration in your migration files
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Built with [SQLAlchemy](https://www.sqlalchemy.org/) for database abstraction
- CLI powered by [Typer](https://typer.tiangolo.com/)
- YAML support via [PyYAML](https://pyyaml.org/)

---

**Need help?** Check the command help with `python main.py --help` or `python main.py [command] --help`
