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
    """
    global _pool
    
    if _pool is not None:
        return _pool
    
    settings = get_settings()
    
    # Parse database URL
    # Format: postgresql://user:password@host:port/database
    db_url = settings.database_url
    
    logger.info(f"Connecting to database...")
    
    _pool = await asyncpg.create_pool(
        db_url,
        min_size=2,
        max_size=settings.database_pool_size,
        max_inactive_connection_lifetime=300,
    )
    
    logger.info("Database connection pool created")
    return _pool


async def get_db_pool() -> asyncpg.Pool:
    """
    Get the database connection pool.
    
    Raises RuntimeError if pool is not initialized.
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
    
    This must be called before executing queries on tables with RLS enabled.
    The RLS policies check `current_setting('app.current_user_id')` to filter
    rows by owner_user_id.
    
    Args:
        conn: asyncpg connection
        user_id: User's UUID as string
    """
    # Use set_config() which supports parameterized queries (unlike SET LOCAL)
    # Third parameter 'false' = session-level (persists for entire connection)
    # IMPORTANT: 'true' would only last for the current transaction, which with
    # autocommit means just THIS statement - the setting would be gone for the next query!
    await conn.execute(
        "SELECT set_config('app.current_user_id', $1, false)",
        str(user_id)
    )

