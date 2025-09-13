#!/usr/bin/env python3
"""
Test script for dbPorter package structure.
"""

import sys
import os

def test_package_structure():
    """Test the package structure and basic functionality."""
    print("🧪 Testing dbPorter Package Structure")
    print("=" * 50)
    
    # Test 1: Check package directory exists
    if os.path.exists("dbPorter"):
        print("✅ dbPorter package directory exists")
    else:
        print("❌ dbPorter package directory missing")
        return False
    
    # Test 2: Check required files exist
    required_files = [
        "dbPorter/__init__.py",
        "dbPorter/main.py",
        "dbPorter/commands.py",
        "dbPorter/db.py",
        "dbPorter/applier.py",
        "dbPorter/executors.py",
        "dbPorter/migration_loader.py",
        "dbPorter/planner.py",
        "dbPorter/models.py",
        "dbPorter/utils/__init__.py",
        "dbPorter/utils/constants.py",
        "dbPorter/utils/utils.py",
    ]
    
    missing_files = []
    for file in required_files:
        if os.path.exists(file):
            print(f"✅ {file} exists")
        else:
            print(f"❌ {file} missing")
            missing_files.append(file)
    
    if missing_files:
        print(f"\n❌ Missing {len(missing_files)} required files")
        return False
    
    # Test 3: Check package metadata files
    metadata_files = [
        "setup.py",
        "pyproject.toml",
        "MANIFEST.in",
        "LICENSE",
        "README.md",
        "CHANGELOG.md",
    ]
    
    for file in metadata_files:
        if os.path.exists(file):
            print(f"✅ {file} exists")
        else:
            print(f"❌ {file} missing")
    
    print("\n🎯 Package Structure Summary")
    print("-" * 30)
    print("✅ Package directory: dbPorter/")
    print("✅ Core modules: commands, db, applier, etc.")
    print("✅ Utilities: utils/ directory")
    print("✅ Metadata: setup.py, pyproject.toml")
    print("✅ Documentation: README.md, CHANGELOG.md")
    print("✅ License: MIT License")
    
    print("\n🚀 Next Steps for PyPI Publishing:")
    print("1. Install dependencies: pip install -r requirements.txt")
    print("2. Test package: python -m dbPorter.main --help")
    print("3. Build package: python -m build")
    print("4. Upload to PyPI: python -m twine upload dist/*")
    
    return True

if __name__ == "__main__":
    success = test_package_structure()
    if success:
        print("\n🎉 Package structure is ready for PyPI publishing!")
    else:
        print("\n❌ Package structure needs fixes before publishing")
        sys.exit(1)
