"""
Database connection management using asyncpg.
"""

import logging
from typing import Optional

import asyncpg

from ..core.config import get_settings

logger = logging.getLogger(__name__)

# Global connection pool
_pool: Optional[asyncpg.Pool] = None


async def init_db() -> asyncpg.Pool:
    """
    Initialize database connection pool.
    
    Call this on application startup.
    
    Returns:
        The database connection pool.
    """
    global _pool
    
    if _pool is not None:
        return _pool
    
    settings = get_settings()
    db_url = settings.database_url
    
    logger.info("Connecting to database...")
    
    try:
        _pool = await asyncpg.create_pool(
            db_url,
            min_size=2,
            max_size=settings.database_pool_size,
            max_inactive_connection_lifetime=300,
        )
        logger.info("Database connection pool created")
        
        # Run migrations on startup (for development)
        if settings.environment == "development":
            await _run_migrations()
            
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise
    
    return _pool


async def _run_migrations() -> None:
    """
    Run pending database migrations.
    
    This is a simplified migration runner for development.
    In production, use a proper migration tool.
    """
    global _pool
    if _pool is None:
        return
        
    from pathlib import Path
    
    migrations_dir = Path(__file__).parent / "migrations"
    if not migrations_dir.exists():
        return
    
    async with _pool.acquire() as conn:
        # Create migrations tracking table if not exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                name VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
        # Get applied migrations
        applied = await conn.fetch("SELECT name FROM _migrations")
        applied_names = {row["name"] for row in applied}
        
        # Find and apply new migrations
        migration_files = sorted(migrations_dir.glob("*.sql"))
        
        for migration_file in migration_files:
            if migration_file.name in applied_names:
                continue
                
            logger.info(f"Applying migration: {migration_file.name}")
            
            try:
                sql = migration_file.read_text()
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO _migrations (name) VALUES ($1)",
                    migration_file.name
                )
                logger.info(f"Applied migration: {migration_file.name}")
            except Exception as e:
                logger.error(f"Failed to apply migration {migration_file.name}: {e}")
                raise


async def get_db_pool() -> asyncpg.Pool:
    """
    Get the database connection pool.
    
    Raises:
        RuntimeError: If pool is not initialized.
    """
    global _pool
    
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_db() first.")
    
    return _pool


async def close_db() -> None:
    """
    Close database connection pool.
    
    Call this on application shutdown.
    """
    global _pool
    
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")


async def set_rls_user(conn, user_id: str) -> None:
    """
    Set the current user ID for Row-Level Security policies.
    
    Call this before executing queries that need RLS filtering.
    
    Args:
        conn: asyncpg connection
        user_id: User's UUID as string
    """
    await conn.execute(
        "SET LOCAL app.current_user_id = $1",
        user_id
    )


class RLSConnection:
    """
    Context manager for database connections with RLS user set.
    
    Usage:
        async with RLSConnection(user_id) as conn:
            rows = await conn.fetch("SELECT * FROM persons")
            # RLS policy will automatically filter to user's data
    """
    
    def __init__(self, user_id: str):
        """
        Initialize RLS connection.
        
        Args:
            user_id: User's UUID as string
        """
        self.user_id = user_id
        self.conn = None
    
    async def __aenter__(self):
        pool = await get_db_pool()
        self.conn = await pool.acquire()
        
        # Set RLS user for this connection
        await set_rls_user(self.conn, self.user_id)
        
        return self.conn
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            pool = await get_db_pool()
            await pool.release(self.conn)
        return False

