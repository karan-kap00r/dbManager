# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial release of dbPorter
- YAML-based declarative migrations
- Python-based programmatic migrations
- Migration Graph (DAG) support with dependency management
- Automatic rollback with metadata preservation
- Schema auto-generation from SQLAlchemy models
- Support for multiple databases (SQLite, PostgreSQL, MySQL, SQL Server, Oracle)
- Comprehensive status inspection with visual indicators
- Programmatic configuration for security-conscious organizations
- Table rename support with mapping configuration
- Dry-run capability for safe migration preview
- Conflict detection for parallel development
- Branch management and merging capabilities

### Features
- **Dual Migration Support**: Both YAML and Python migration formats
- **Advanced DAG System**: Branching migrations with dependency tracking
- **Schema Inspection**: Comprehensive database and migration status reporting
- **Security-First**: Programmatic configuration without credential files
- **Multi-Database**: Support for all major SQLAlchemy-compatible databases
- **Developer Experience**: One-time configuration, visual indicators, comprehensive CLI

## [0.1.0] - 2024-01-13

### Added
- Initial release
- Core migration functionality
- CLI interface with Typer
- SQLAlchemy integration
- YAML migration file support
- Python migration file support
- Basic rollback functionality
- Database connection management
- Migration logging and tracking

### Technical Details
- Python 3.8+ support
- SQLAlchemy 2.0+ compatibility
- Typer-based CLI interface
- YAML configuration support
- Environment variable configuration
- Auto-discovery of database connections
