"""
dbPorter - Database Migration Tool

A powerful, flexible database migration tool built with Python that supports 
both YAML-based declarative migrations and Python-based programmatic migrations.

This tool provides comprehensive schema management capabilities with automatic 
rollback support and metadata preservation.
"""

__version__ = "0.1.11"
__author__ = "Karan Kapoor"
__email__ = "karan.kapoor@gmail.com"
__description__ = "A powerful database migration tool with DAG support, automatic rollback, and schema inspection"

# Import the main functions for programmatic access
from .commands import set_database_url, get_database_url

# Import core classes and functions
from .migration_loader import Migration, MigrationAction
from .db import get_engine, init_metadata, MIGRATION_LOG_TABLE
from .applier import apply_migration
from .planner import plan_migration

__all__ = [
    # Version info
    "__version__",
    "__author__", 
    "__email__",
    "__description__",
    
    # Configuration functions
    "set_database_url",
    "get_database_url",
    
    # Core classes
    "Migration",
    "MigrationAction",
    
    # Core functions
    "get_engine",
    "init_metadata", 
    "apply_migration",
    "plan_migration",
    
    # Constants
    "MIGRATION_LOG_TABLE",
]
