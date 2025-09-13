#!/usr/bin/env python3
"""
Main entry point for dbPorter - Database Migration Tool.

This module provides the CLI interface for the migration tool.
"""

import os
import typer
from .commands import app  # Typer app from commands.py

def main():
    """Main entry point for the CLI."""
    os.makedirs("migrations", exist_ok=True)
    app()

if __name__ == "__main__":
    main()
