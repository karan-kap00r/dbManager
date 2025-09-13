#!/usr/bin/env python3
"""
Example: Programmatic Database Configuration

This example shows how to use the migration tool with programmatic configuration
for security-conscious organizations that don't want to store credentials in files.
"""

import os
import sys

# Add the parent directory to the path so we can import the migration tool
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from migrateDB import set_database_url

def main():
    """
    Example of setting database URL programmatically.
    
    This approach is ideal for:
    - Security-conscious organizations
    - CI/CD environments where credentials are in environment variables
    - Applications that already have database configuration
    - Multi-tenant applications with dynamic database URLs
    """
    
    # Method 1: Direct URL (most common)
    db_url = "postgresql://user:password@localhost:5432/mydatabase"
    set_database_url(db_url)
    
    # Method 2: From environment variables (recommended for production)
    # db_url = os.getenv("DATABASE_URL")
    # if db_url:
    #     set_database_url(db_url)
    # else:
    #     raise ValueError("DATABASE_URL environment variable not set")
    
    # Method 3: From application configuration
    # from myapp.config import get_database_url
    # db_url = get_database_url()
    # set_database_url(db_url)
    
    # Method 4: Dynamic construction
    # host = os.getenv("DB_HOST", "localhost")
    # port = os.getenv("DB_PORT", "5432")
    # user = os.getenv("DB_USER")
    # password = os.getenv("DB_PASSWORD")
    # database = os.getenv("DB_NAME")
    # 
    # if all([user, password, database]):
    #     db_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    #     set_database_url(db_url)
    # else:
    #     raise ValueError("Required database environment variables not set")
    
    print("✅ Database URL set programmatically!")
    print("Now you can run migration commands without specifying database credentials:")
    print("  python main.py status")
    print("  python main.py apply migrations/20250101_add_users.yml")
    print("  python main.py autogenerate -m 'Add new table'")

if __name__ == "__main__":
    main()
