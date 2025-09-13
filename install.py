#!/usr/bin/env python3
"""
Installation script for the Database Migration Tool.

This script helps users install the tool with the appropriate dependencies
based on their database choice.
"""

import sys
import subprocess
import argparse
from pathlib import Path

def run_command(cmd, description):
    """Run a command and handle errors."""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e}")
        print(f"Error output: {e.stderr}")
        return False

def install_requirements(requirements_file):
    """Install requirements from a specific file."""
    cmd = f"{sys.executable} -m pip install -r {requirements_file}"
    return run_command(cmd, f"Installing {requirements_file}")

def install_database_driver(database):
    """Install database-specific driver."""
    drivers = {
        "postgresql": "psycopg2-binary",
        "mysql": "PyMySQL",
        "sqlserver": "pyodbc",
        "oracle": "cx-Oracle"
    }
    
    if database in drivers:
        driver = drivers[database]
        cmd = f"{sys.executable} -m pip install {driver}"
        return run_command(cmd, f"Installing {driver} for {database}")
    return True

def main():
    parser = argparse.ArgumentParser(description="Install dbPorter - Database Migration Tool")
    parser.add_argument(
        "--database", 
        choices=["sqlite", "postgresql", "mysql", "sqlserver", "oracle"],
        default="sqlite",
        help="Target database type (default: sqlite)"
    )
    parser.add_argument(
        "--minimal", 
        action="store_true",
        help="Install minimal dependencies only"
    )
    parser.add_argument(
        "--dev", 
        action="store_true",
        help="Install development dependencies"
    )
    
    args = parser.parse_args()
    
    print("🚀 dbPorter - Database Migration Tool - Installation")
    print("=" * 50)
    print(f"Target database: {args.database}")
    print(f"Installation type: {'minimal' if args.minimal else 'development' if args.dev else 'full'}")
    print()
    
    # Determine requirements file
    if args.minimal:
        requirements_file = "requirements-minimal.txt"
    elif args.dev:
        requirements_file = "requirements-dev.txt"
    else:
        requirements_file = "requirements.txt"
    
    # Check if requirements file exists
    if not Path(requirements_file).exists():
        print(f"❌ Requirements file {requirements_file} not found!")
        print("Make sure you're running this script from the project root directory.")
        sys.exit(1)
    
    # Install base requirements
    if not install_requirements(requirements_file):
        print("❌ Failed to install base requirements")
        sys.exit(1)
    
    # Install database driver if needed
    if args.database != "sqlite":
        if not install_database_driver(args.database):
            print(f"⚠️ Failed to install {args.database} driver")
            print("You may need to install it manually later.")
    
    print()
    print("🎉 Installation completed!")
    print()
    print("Next steps:")
    print("1. Set up your database configuration:")
    print("   dbporter init-db")
    print()
    print("2. Create your first migration:")
    print("   dbporter autogenerate -m 'Initial schema'")
    print()
    print("3. Apply the migration:")
    print("   dbporter apply")
    print()
    print("For more information, see the README.md file.")

if __name__ == "__main__":
    main()
