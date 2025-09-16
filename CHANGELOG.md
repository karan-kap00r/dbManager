# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.15] - 2025-01-15

### Fixed
- **CRITICAL FIX**: Fixed database component extraction during discovery - individual components (host, port, user, database) are now properly extracted and saved
- **FIXED**: Database discovery now extracts all components during the discovery phase instead of relying on init-db to do it
- **FIXED**: Resolved issue where discovered URLs would save as SQLite defaults instead of the actual discovered database

### Improved
- Streamlined component extraction logic by moving it to the discovery phase
- Better separation of concerns between discovery and initialization phases
- More reliable database configuration saving for discovered URLs

## [0.1.14] - 2025-01-15

### Fixed
- **CRITICAL FIX**: Fixed database URL not being saved in migrate_config.json when discovered
- **FIXED**: Discovered database URLs now properly preserve the original URL in configuration
- **FIXED**: Enhanced database component extraction to maintain both individual components and full URL
- **FIXED**: Improved security handling for URLs with and without sensitive data

### Improved
- Better configuration saving with complete URL preservation for non-sensitive URLs
- Enhanced discovery workflow with proper URL persistence
- Improved security model for credential handling

## [0.1.13] - 2025-01-15

### Fixed
- **REPUBLISH**: Republished with latest changes and improvements
- **FIXED**: Enhanced database component extraction from discovered URLs
- **FIXED**: Improved error handling and fallback behavior for database discovery

## [0.1.12] - 2025-01-15

### Fixed
- **CRITICAL BUG FIX**: Fixed `discover_database_url()` function that had a syntax error preventing database discovery
- **FIXED**: `init-db` command now properly calls `discover_database_url()` and uses discovered database URLs
- **FIXED**: Added proper error handling in `get_database_config()` for discovery failures
- **FIXED**: Database component extraction from discovered URLs now works correctly

### Improved
- Enhanced database discovery with better component extraction (host, port, user, database)
- Improved error handling and fallback behavior for database discovery
- Better configuration saving with extracted database components from discovered URLs

## [0.1.11] - 2025-01-15

### Fixed
- **FIXED**: Database type extraction from URLs in auto-discovery
- **FIXED**: `migrate_config.json` now correctly shows `db_type` as "mysql" instead of "sqlite"
- **FIXED**: URL parsing now properly extracts database type from connection strings

### Improved
- Better database type detection for MySQL, PostgreSQL, and SQLite URLs
- More accurate configuration saving with correct database type
- Enhanced auto-discovery with proper URL parsing

## [0.1.10] - 2025-01-15

### Added
- **NEW**: Source tracking in configuration detection (command_line, environment, saved_config, discovery)
- **NEW**: Enhanced `init-db` command with Alembic-style documentation
- **NEW**: Enhanced auto-discovery with Python config file support
- **NEW**: Support for functions that return database URLs (get_database_url(), etc.)
- **NEW**: Support for multiple variable names (DATABASE_URL, DB_URL, DB_STRING, etc.)

### Changed
- **IMPROVED**: Configuration detection now follows Alembic's exact pattern
- **IMPROVED**: Better documentation comparing dbPorter to Alembic
- **IMPROVED**: More explicit priority order with source tracking
- **IMPROVED**: Enhanced command help text with Alembic-style examples

### Improved
- Configuration detection now matches Alembic's behavior exactly
- Better user experience for developers familiar with Alembic
- Cleaner command structure with direct commands (no unnecessary wrapper)
- Enhanced documentation with Alembic comparisons

## [0.1.9] - 2025-01-15

### Removed
- **REMOVED**: Programmatic configuration detection from CLI commands
- Removed persistent programmatic configuration storage (`.dbporter_programmatic.json`)
- Removed `clear_programmatic_config()` function
- Simplified `set_database_url()` to only work within the current process

### Changed
- **SIMPLIFIED**: Database configuration detection now uses 4 methods instead of 5:
  1. Command line arguments (highest priority)
  2. Environment variables (`DBPORTER_DATABASE_URL` or `DATABASE_URL`)
  3. Saved configuration (`migrate_config.json`)
  4. Auto-discovery (lowest priority)
- Updated programmatic configuration example to reflect new behavior
- `set_database_url()` now only affects the current Python process

### Improved
- Cleaner and more predictable configuration detection
- Better documentation for CLI usage patterns
- Simplified codebase with fewer edge cases

## [0.1.8] - 2025-01-15

### Fixed
- **VERIFIED FIX**: Programmatic configuration detection now working correctly
- Confirmed `set_database_url()` properly persists across different Python processes
- Verified CLI commands correctly detect programmatically set database URLs
- Enhanced error handling and user feedback for configuration detection

### Improved
- Better documentation and examples for programmatic configuration usage
- More robust cross-process configuration persistence
- Enhanced debugging capabilities for configuration issues

## [0.1.7] - 2025-01-15

### Fixed
- **CRITICAL FIX**: Resolved programmatic configuration persistence issue
- Fixed `set_database_url()` not being detected across different Python processes
- Programmatic configuration now properly persists in `.dbporter_programmatic.json`
- CLI commands now correctly detect programmatically set database URLs

### Improved
- Enhanced programmatic configuration reliability and cross-process compatibility
- Better error handling for configuration file operations
- More robust database URL detection across different execution contexts

## [0.1.6] - 2025-01-15

### Added
- Enhanced metadata detection to support `Base.metadata` from SQLAlchemy declarative base
- Automatic detection of metadata from `Base.metadata` (most common SQLAlchemy pattern)
- Support for three metadata patterns: `metadata`, `MetaData`, and `Base.metadata`
- **Persistent programmatic configuration**: `set_database_url()` now works across different Python processes
- New `clear_programmatic_config()` function to clear programmatic database configuration
- Programmatic configuration is stored in `.dbporter_programmatic.json` for persistence

### Improved
- Updated examples to show cleaner `Base.metadata` pattern as recommended approach
- Better error messages with examples for all supported metadata patterns
- More intuitive auto-migration workflow for standard SQLAlchemy applications
- **Programmatic configuration reliability**: Configuration now persists across CLI invocations and different processes
- Enhanced programmatic configuration example with verification and management functions

### Fixed
- **MAJOR FIX**: Fixed `set_database_url()` detection issue - configuration now properly persists across different Python processes
- Fixed `set_database_url()` to properly parse and save database configuration components
- Fixed config file showing null values when using programmatic database URL setting
- Database URL components (host, port, user, database, db_type) are now correctly saved to config file

## [0.1.5] - 2025-01-15

### Fixed
- Fixed `set_database_url()` to properly parse and save database configuration components
- Fixed config file showing null values when using programmatic database URL setting
- Database URL components (host, port, user, database, db_type) are now correctly saved to config file

## [0.1.4] - 2025-01-15

### Fixed
- Fixed database driver validation to provide helpful error messages when drivers are missing
- Fixed import references from `migrateDB` to `dbPorter` in example files and docstrings
- Improved error messages for missing database drivers (MySQL, PostgreSQL, etc.)
- Fixed SQLite URL validation to handle URLs without hostname components

### Improved
- Better user experience when database drivers are not installed
- Clear installation instructions in error messages
- Updated example files to use correct package imports

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
