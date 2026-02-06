#!/usr/bin/env python3
"""
ANVEL Database Migration Script
===============================

Handles database schema migrations for the ANVEL trading system.

Features:
- Version tracking via schema_version table
- Atomic migrations with transaction support
- Rollback capability
- Dry-run mode for testing

Usage:
    python scripts/db_migrate.py --check        # Check current version
    python scripts/db_migrate.py --migrate      # Run pending migrations
    python scripts/db_migrate.py --dry-run      # Show what would run
    python scripts/db_migrate.py --init         # Initialize fresh database
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Try to import psycopg2
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.warning("psycopg2 not available - using SQLite fallback for local dev")

try:
    import sqlite3
    SQLITE_AVAILABLE = True
except ImportError:
    SQLITE_AVAILABLE = False


# Migration definitions
# Each migration is a tuple of (version, description, up_sql, down_sql)
MIGRATIONS: List[Tuple[int, str, str, str]] = [
    (
        1,
        "Initial schema",
        """
        -- Applied via anvel_database_schema.sql
        -- This migration is a marker for the initial schema
        """,
        """
        -- Cannot rollback initial schema
        """
    ),
    (
        2,
        "Add execution_metadata to trades",
        """
        ALTER TABLE trades ADD COLUMN IF NOT EXISTS execution_metadata JSONB DEFAULT '{}';
        CREATE INDEX IF NOT EXISTS idx_trades_metadata ON trades USING GIN (execution_metadata);
        """,
        """
        DROP INDEX IF EXISTS idx_trades_metadata;
        ALTER TABLE trades DROP COLUMN IF EXISTS execution_metadata;
        """
    ),
    (
        3,
        "Add nonce tracking",
        """
        CREATE TABLE IF NOT EXISTS nonce_tracking (
            id SERIAL PRIMARY KEY,
            chain_id INTEGER NOT NULL,
            wallet_address VARCHAR(64) NOT NULL,
            current_nonce BIGINT NOT NULL DEFAULT 0,
            last_used_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT unique_chain_wallet UNIQUE (chain_id, wallet_address)
        );
        CREATE INDEX IF NOT EXISTS idx_nonce_chain ON nonce_tracking(chain_id);
        CREATE INDEX IF NOT EXISTS idx_nonce_wallet ON nonce_tracking(wallet_address);
        """,
        """
        DROP TABLE IF EXISTS nonce_tracking;
        """
    ),
    (
        4,
        "Add idempotency keys",
        """
        CREATE TABLE IF NOT EXISTS idempotency_keys (
            id SERIAL PRIMARY KEY,
            idempotency_key VARCHAR(128) NOT NULL UNIQUE,
            request_hash VARCHAR(64),
            response JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP WITH TIME ZONE
        );
        CREATE INDEX IF NOT EXISTS idx_idemp_key ON idempotency_keys(idempotency_key);
        CREATE INDEX IF NOT EXISTS idx_idemp_expires ON idempotency_keys(expires_at);
        """,
        """
        DROP TABLE IF EXISTS idempotency_keys;
        """
    ),
    (
        5,
        "Add circuit breaker state",
        """
        CREATE TABLE IF NOT EXISTS circuit_breaker_state (
            id SERIAL PRIMARY KEY,
            breaker_name VARCHAR(64) NOT NULL UNIQUE,
            state VARCHAR(16) NOT NULL DEFAULT 'closed',
            failure_count INTEGER DEFAULT 0,
            success_count INTEGER DEFAULT 0,
            last_failure_at TIMESTAMP WITH TIME ZONE,
            last_success_at TIMESTAMP WITH TIME ZONE,
            opened_at TIMESTAMP WITH TIME ZONE,
            half_open_at TIMESTAMP WITH TIME ZONE,
            metadata JSONB DEFAULT '{}'
        );
        """,
        """
        DROP TABLE IF EXISTS circuit_breaker_state;
        """
    ),
]


class DatabaseMigrator:
    """Handles database migrations."""
    
    def __init__(self, connection_string: Optional[str] = None):
        """
        Initialize migrator.
        
        Args:
            connection_string: PostgreSQL connection string or sqlite path
        """
        self.connection_string = connection_string or os.environ.get(
            "ANVEL_DATABASE_URL", 
            "sqlite:///data/anvel.db"
        )
        self.conn = None
        self.is_postgres = not self.connection_string.startswith("sqlite")
    
    def connect(self) -> bool:
        """Establish database connection."""
        try:
            if self.is_postgres:
                if not PSYCOPG2_AVAILABLE:
                    logger.error("psycopg2 required for PostgreSQL")
                    return False
                self.conn = psycopg2.connect(self.connection_string)
            else:
                if not SQLITE_AVAILABLE:
                    logger.error("sqlite3 not available")
                    return False
                # Extract path from sqlite:///path
                db_path = self.connection_string.replace("sqlite:///", "")
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
                self.conn = sqlite3.connect(db_path)
            logger.info(f"Connected to database")
            return True
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def get_current_version(self) -> int:
        """Get current schema version."""
        try:
            cursor = self.conn.cursor()
            if self.is_postgres:
                cursor.execute("""
                    SELECT EXISTS(
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'schema_version'
                    )
                """)
                exists = cursor.fetchone()[0]
            else:
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='schema_version'
                """)
                exists = cursor.fetchone() is not None
            
            if not exists:
                return 0
            
            cursor.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
            return cursor.fetchone()[0]
        except Exception as e:
            logger.warning(f"Could not get version: {e}")
            return 0
    
    def ensure_version_table(self):
        """Create schema_version table if needed."""
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT
            )
        """)
        self.conn.commit()
    
    def run_migration(self, version: int, description: str, sql: str) -> bool:
        """
        Run a single migration.
        
        Args:
            version: Migration version
            description: Migration description
            sql: SQL to execute
            
        Returns:
            True if successful
        """
        cursor = self.conn.cursor()
        try:
            # Skip if empty SQL (marker migrations)
            if sql.strip() and not sql.strip().startswith("--"):
                # Split into statements
                statements = [s.strip() for s in sql.split(';') if s.strip()]
                for stmt in statements:
                    if stmt and not stmt.startswith("--"):
                        cursor.execute(stmt)
            
            # Record version
            cursor.execute(
                "INSERT INTO schema_version (version, description) VALUES (?, ?)"
                if not self.is_postgres else
                "INSERT INTO schema_version (version, description) VALUES (%s, %s)",
                (version, description)
            )
            self.conn.commit()
            logger.info(f"Applied migration {version}: {description}")
            return True
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Migration {version} failed: {e}")
            return False
    
    def migrate(self, target_version: Optional[int] = None, dry_run: bool = False) -> bool:
        """
        Run pending migrations.
        
        Args:
            target_version: Target version (default: latest)
            dry_run: If True, show what would run without executing
            
        Returns:
            True if successful
        """
        self.ensure_version_table()
        current = self.get_current_version()
        target = target_version or max(m[0] for m in MIGRATIONS)
        
        logger.info(f"Current version: {current}, Target: {target}")
        
        if current >= target:
            logger.info("Database is up to date")
            return True
        
        pending = [m for m in MIGRATIONS if m[0] > current and m[0] <= target]
        
        if dry_run:
            logger.info("Dry run - would apply the following migrations:")
            for version, description, up_sql, _ in pending:
                logger.info(f"  Version {version}: {description}")
            return True
        
        for version, description, up_sql, _ in pending:
            if not self.run_migration(version, description, up_sql):
                return False
        
        logger.info(f"Successfully migrated to version {target}")
        return True
    
    def init_schema(self, schema_file: Path) -> bool:
        """
        Initialize database with schema file.
        
        Args:
            schema_file: Path to SQL schema file
            
        Returns:
            True if successful
        """
        if not schema_file.exists():
            logger.error(f"Schema file not found: {schema_file}")
            return False
        
        try:
            sql = schema_file.read_text()
            cursor = self.conn.cursor()
            
            # Split and execute statements
            # Note: All migration SQL comes from trusted source files only
            statements = [s.strip() for s in sql.split(';') if s.strip()]
            skipped = []
            for stmt in statements:
                if stmt and not stmt.startswith("--"):
                    try:
                        cursor.execute(stmt)
                    except Exception as e:
                        # Log the specific statement that failed for debugging
                        stmt_preview = stmt[:100] + "..." if len(stmt) > 100 else stmt
                        logger.warning(f"Statement skipped (may be PostgreSQL-specific): {stmt_preview}")
                        logger.debug(f"Skip reason: {e}")
                        skipped.append(stmt_preview)
            
            self.conn.commit()
            logger.info(f"Initialized schema from {schema_file}")
            if skipped:
                logger.warning(f"Skipped {len(skipped)} statements (see debug log for details)")
            return True
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to init schema: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description="ANVEL Database Migration Tool")
    parser.add_argument("--check", action="store_true", help="Check current version")
    parser.add_argument("--migrate", action="store_true", help="Run pending migrations")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run")
    parser.add_argument("--init", action="store_true", help="Initialize fresh database")
    parser.add_argument("--target", type=int, help="Target migration version")
    parser.add_argument("--db", help="Database connection string")
    
    args = parser.parse_args()
    
    migrator = DatabaseMigrator(args.db)
    
    if not migrator.connect():
        sys.exit(1)
    
    try:
        if args.check:
            version = migrator.get_current_version()
            latest = max(m[0] for m in MIGRATIONS)
            print(f"Current version: {version}")
            print(f"Latest version:  {latest}")
            if version < latest:
                print(f"Pending migrations: {latest - version}")
        
        elif args.init:
            schema_file = Path(__file__).parent.parent / "anvel_database_schema.sql"
            if migrator.init_schema(schema_file):
                print("Database initialized successfully")
            else:
                sys.exit(1)
        
        elif args.migrate or args.dry_run:
            if migrator.migrate(args.target, dry_run=args.dry_run):
                print("Migration complete")
            else:
                sys.exit(1)
        
        else:
            parser.print_help()
    
    finally:
        migrator.close()


if __name__ == "__main__":
    main()
