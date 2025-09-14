#!/usr/bin/env python3
"""
Setup script for dbPorter - Database Migration Tool.

This script configures the package for distribution on PyPI.
"""

from setuptools import setup, find_packages
import os

# Read the README file for long description
def read_readme():
    with open("README.md", "r", encoding="utf-8") as fh:
        return fh.read()

# Read requirements from requirements.txt
def read_requirements():
    with open("requirements.txt", "r", encoding="utf-8") as fh:
        return [line.strip() for line in fh if line.strip() and not line.startswith("#")]

# Read version from __init__.py
def read_version():
    with open("dbPorter/__init__.py", "r", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("__version__"):
                return line.split("=")[1].strip().strip('"').strip("'")
    return "0.1.0"

setup(
    name="dbporter",
    version=read_version(),
    author="Karan Kapoor",
    author_email="karankapoor0062@gmail.com",
    description="A powerful database migration tool with DAG support, automatic rollback, and schema inspection",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/karan-kap00r/dbPorter",
    project_urls={
        "Bug Reports": "",
        "Source": "https://github.com/karan-kap00r/dbPorter",
        "Documentation": "https://github.com/karan-kap00r/dbPorter/blob/main/README.md",
    },
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Database",
        "Topic :: System :: Archiving :: Backup",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "Environment :: Console",
    ],
    keywords=[
        "database", "migration", "schema", "sqlalchemy", "yaml", "dag", 
        "rollback", "postgresql", "mysql", "sqlite", "oracle", "sqlserver",
        "version-control", "database-versioning", "schema-management"
    ],
    python_requires=">=3.8",
    install_requires=read_requirements(),
    extras_require={
        "postgresql": ["psycopg2-binary>=2.9.0"],
        "mysql": ["PyMySQL>=1.0.0"],
        "sqlserver": ["pyodbc>=4.0.0"],
        "oracle": ["cx-Oracle>=8.0.0"],
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "pytest-mock>=3.10.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
            "isort>=5.12.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "dbporter=dbPorter.main:main",
            "db-porter=dbPorter.main:main",
        ],
    },
    include_package_data=True,
    package_data={
        "dbPorter": [
            "examples/*.py",
            "*.md",
            "*.txt",
        ],
    },
    zip_safe=False,
    platforms=["any"],
    license="MIT",
)
