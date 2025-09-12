# Database Migration Tool

A powerful, flexible database migration tool built with Python that supports both YAML-based declarative migrations and Python-based programmatic migrations. This tool provides comprehensive schema management capabilities with automatic rollback support and metadata preservation.

## 🚀 Features

- **Dual Migration Support**: YAML-based declarative migrations and Python-based programmatic migrations
- **Automatic Rollback**: Intelligent rollback system with metadata preservation for safe reversions
- **Schema Auto-Generation**: Automatically detect and generate migrations from schema differences
- **Enhanced Metadata**: Captures column metadata for accurate rollback operations
- **Table Rename Support**: Handle table renames with mapping configuration
- **Dry-Run Capability**: Preview migration changes before applying them
- **Comprehensive Logging**: Track all applied migrations with detailed payload information
- **Multiple Database Support**: Works with any SQLAlchemy-supported database

## 📋 Prerequisites

- Python 3.8+
- SQLAlchemy
- PyYAML
- Typer
- python-dotenv

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd migrateDB
   ```

2. **Install dependencies**
   ```bash
   pip install sqlalchemy pyyaml typer python-dotenv tabulate
   ```

3. **Set up environment variables**
   Create a `.env` file in the project root:
   ```env
   DB_URL=sqlite:///your_database.db
   # or for PostgreSQL: postgresql://user:password@localhost/dbname
   # or for MySQL: mysql://user:password@localhost/dbname
   ```

## 🏗️ Project Structure

```
migrateDB/
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

2. **Define your schema in `models.py`**
   ```python
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
