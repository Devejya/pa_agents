#!/usr/bin/env python3
"""
Database migration runner for User Network Service.

Usage:
    python scripts/run_migrations.py [--dry-run]

This script runs all pending SQL migrations in the migrations folder.
Migrations are tracked in the _migrations table.
"""

import asyncio
import argparse
import logging
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def get_database_url() -> str:
    """Get database URL from environment."""
    load_dotenv()
    
    # Try DATABASE_URL first, then construct from parts
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url
    
    # Construct from individual parts
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    database = os.getenv("POSTGRES_DB", "user_network")
    
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


async def get_applied_migrations(conn: asyncpg.Connection) -> set[str]:
    """Get list of already applied migrations."""
    # Check if _migrations table exists
    exists = await conn.fetchval("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = '_migrations'
        )
    """)
    
    if not exists:
        logger.info("Creating _migrations tracking table...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                applied_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        return set()
    
    # Get applied migrations
    rows = await conn.fetch("SELECT name FROM _migrations ORDER BY id")
    return {row["name"] for row in rows}


async def get_pending_migrations(migrations_dir: Path, applied: set[str]) -> list[Path]:
    """Get list of pending migration files."""
    if not migrations_dir.exists():
        logger.warning(f"Migrations directory not found: {migrations_dir}")
        return []
    
    # Get all .sql files
    migration_files = sorted(migrations_dir.glob("*.sql"))
    
    # Filter out already applied
    pending = []
    for f in migration_files:
        name = f.stem  # filename without extension
        if name not in applied:
            pending.append(f)
    
    return pending


async def run_migration(conn: asyncpg.Connection, migration_path: Path, dry_run: bool = False) -> bool:
    """Run a single migration file."""
    name = migration_path.stem
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Running migration: {name}")
    
    try:
        # Read migration SQL
        sql = migration_path.read_text()
        
        if dry_run:
            logger.info(f"  Would execute: {len(sql)} bytes of SQL")
            return True
        
        # Run migration in transaction
        async with conn.transaction():
            # Execute the migration
            await conn.execute(sql)
            
            # Record migration (might be in the migration itself, but do it anyway)
            await conn.execute(
                "INSERT INTO _migrations (name) VALUES ($1) ON CONFLICT (name) DO NOTHING",
                name
            )
        
        logger.info(f"  ✓ Migration {name} completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"  ✗ Migration {name} failed: {e}")
        return False


async def main(dry_run: bool = False):
    """Main migration runner."""
    logger.info("User Network Service - Database Migration Runner")
    logger.info("=" * 50)
    
    # Get database connection
    database_url = await get_database_url()
    logger.info(f"Connecting to database...")
    
    try:
        conn = await asyncpg.connect(database_url)
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)
    
    try:
        # Get applied migrations
        applied = await get_applied_migrations(conn)
        logger.info(f"Found {len(applied)} applied migrations")
        
        # Get pending migrations
        migrations_dir = Path(__file__).parent.parent / "src" / "db" / "migrations"
        pending = await get_pending_migrations(migrations_dir, applied)
        
        if not pending:
            logger.info("No pending migrations to run")
            return
        
        logger.info(f"Found {len(pending)} pending migrations:")
        for m in pending:
            logger.info(f"  - {m.stem}")
        
        # Run pending migrations
        logger.info("")
        success_count = 0
        fail_count = 0
        
        for migration in pending:
            if await run_migration(conn, migration, dry_run):
                success_count += 1
            else:
                fail_count += 1
                if not dry_run:
                    logger.error("Stopping due to migration failure")
                    break
        
        # Summary
        logger.info("")
        logger.info("=" * 50)
        logger.info(f"Migration Summary:")
        logger.info(f"  Successful: {success_count}")
        logger.info(f"  Failed: {fail_count}")
        logger.info(f"  Remaining: {len(pending) - success_count - fail_count}")
        
        if fail_count > 0:
            sys.exit(1)
            
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually running migrations",
    )
    args = parser.parse_args()
    
    asyncio.run(main(dry_run=args.dry_run))

