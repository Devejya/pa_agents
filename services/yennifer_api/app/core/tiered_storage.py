"""
Tiered Storage Manager for Chat Messages.

Coordinates three storage tiers:
- Hot (Redis): Recent messages < 7 days, <1ms access
- Warm (PostgreSQL): Messages 7-365 days, ~10ms access
- Cold (S3/Glacier): Messages > 365 days, archived

Read path:
1. Check hot cache (Redis)
2. If miss, check warm store (PostgreSQL)
3. If archived, check cold store (S3)

Write path:
1. Write to warm store (PostgreSQL)
2. Async populate hot cache (Redis)

Migration:
- Background job moves old messages to cold storage
- Another job evicts old entries from hot cache
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from .chat_cache import ChatCache, get_chat_cache
from .chat_archive import ChatArchive, get_chat_archive
from .encryption import decrypt_user_dek
from ..db import get_db_pool, ChatRepository

logger = logging.getLogger(__name__)


class TieredStorageManager:
    """Manages chat storage across hot, warm, and cold tiers."""
    
    # Tier boundaries
    HOT_TIER_DAYS = 7          # Messages < 7 days in Redis
    ARCHIVE_AFTER_DAYS = 365   # Messages > 365 days archived to S3
    
    def __init__(
        self,
        cache: Optional[ChatCache] = None,
        archive: Optional[ChatArchive] = None,
    ):
        """
        Initialize the manager.
        
        Args:
            cache: Redis cache instance (or uses global).
            archive: S3 archive instance (or uses global).
        """
        self._cache = cache
        self._archive = archive
    
    @property
    def cache(self) -> ChatCache:
        """Get chat cache."""
        return self._cache or get_chat_cache()
    
    @property
    def archive(self) -> ChatArchive:
        """Get chat archive."""
        return self._archive or get_chat_archive()
    
    async def add_message(
        self,
        user_id: UUID,
        session_id: UUID,
        role: str,
        content: str,
        tool_calls: Optional[List[Dict]] = None,
        tokens_used: Optional[int] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add a message with tiered storage.
        
        Writes to warm store (PostgreSQL) and hot cache (Redis).
        
        Args:
            user_id: User's UUID.
            session_id: Session UUID.
            role: Message role.
            content: Message content.
            tool_calls: Optional tool calls.
            tokens_used: Optional token count.
            model: Optional model name.
            
        Returns:
            Message dict.
        """
        # Write to warm store (PostgreSQL)
        pool = await get_db_pool()
        chat_repo = ChatRepository(pool)
        
        message = await chat_repo.add_message(
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            tokens_used=tokens_used,
            model=model,
        )
        
        # Also cache in hot tier (async, don't block)
        try:
            await self.cache.cache_message(user_id, session_id, message)
        except Exception as e:
            logger.debug(f"Failed to cache message (non-critical): {e}")
        
        return message
    
    async def get_session_messages(
        self,
        user_id: UUID,
        session_id: UUID,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get messages with tiered read.
        
        1. Check hot cache (Redis)
        2. Fall back to warm store (PostgreSQL)
        3. Warm the cache on miss
        
        Args:
            user_id: User's UUID.
            session_id: Session UUID.
            limit: Maximum messages.
            
        Returns:
            List of message dicts.
        """
        # Try hot cache first
        cached_messages = await self.cache.get_session_messages(
            user_id, session_id, limit
        )
        
        if cached_messages is not None:
            logger.debug(f"Cache hit for session {session_id}")
            return cached_messages
        
        # Cache miss - read from warm store
        logger.debug(f"Cache miss for session {session_id}, reading from PostgreSQL")
        
        pool = await get_db_pool()
        chat_repo = ChatRepository(pool)
        
        messages = await chat_repo.get_session_messages(
            user_id=user_id,
            session_id=session_id,
            limit=limit,
        )
        
        # Warm the cache
        if messages:
            try:
                await self.cache.warm_cache(user_id, session_id, messages)
            except Exception as e:
                logger.debug(f"Failed to warm cache (non-critical): {e}")
        
        return messages
    
    async def get_archived_session(
        self,
        user_id: UUID,
        session_id: UUID,
        year: int,
        month: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a session from cold storage.
        
        Args:
            user_id: User's UUID.
            session_id: Session UUID.
            year: Archive year.
            month: Archive month.
            
        Returns:
            Archive data or None.
        """
        if not self.archive.is_enabled:
            return None
        
        # Get user's DEK
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT encryption_key_blob FROM users WHERE id = $1",
                user_id
            )
            if not row:
                return None
            
            user_dek = decrypt_user_dek(row["encryption_key_blob"])
        
        return await self.archive.retrieve_session(
            user_id, session_id, year, month, user_dek
        )
    
    async def archive_old_sessions(
        self,
        user_id: UUID,
        days_old: int = None,
    ) -> Dict[str, Any]:
        """
        Archive old sessions to cold storage.
        
        Args:
            user_id: User's UUID.
            days_old: Archive sessions older than this (default: ARCHIVE_AFTER_DAYS).
            
        Returns:
            Dict with archive results.
        """
        if not self.archive.is_enabled:
            return {"archived": 0, "skipped": "archive_disabled"}
        
        days_old = days_old or self.ARCHIVE_AFTER_DAYS
        cutoff = datetime.utcnow() - timedelta(days=days_old)
        
        pool = await get_db_pool()
        chat_repo = ChatRepository(pool)
        
        # Get user's DEK
        async with pool.acquire() as conn:
            await conn.execute("SET app.current_user_id = $1", str(user_id))
            
            row = await conn.fetchrow(
                "SELECT encryption_key_blob FROM users WHERE id = $1",
                user_id
            )
            if not row:
                return {"archived": 0, "error": "user_not_found"}
            
            user_dek = decrypt_user_dek(row["encryption_key_blob"])
            
            # Find sessions to archive
            old_sessions = await conn.fetch("""
                SELECT id, title, created_at, last_message_at, message_count
                FROM chat_sessions
                WHERE is_active = true
                  AND (last_message_at < $1 OR (last_message_at IS NULL AND created_at < $1))
                ORDER BY created_at
            """, cutoff)
        
        results = {
            "archived": 0,
            "failed": 0,
            "errors": [],
        }
        
        for session in old_sessions:
            session_id = session["id"]
            
            try:
                # Get messages
                messages = await chat_repo.get_session_messages(
                    user_id, session_id, limit=10000
                )
                
                if not messages:
                    continue
                
                # Archive to S3
                success = await self.archive.archive_session(
                    user_id=user_id,
                    session_id=session_id,
                    messages=messages,
                    user_dek=user_dek,
                    session_metadata={
                        "title": session["title"],
                        "created_at": session["created_at"].isoformat() if session["created_at"] else None,
                    },
                )
                
                if success:
                    # Mark session as archived (deactivate)
                    await chat_repo.deactivate_session(user_id, session_id)
                    results["archived"] += 1
                else:
                    results["failed"] += 1
                    results["errors"].append(f"Failed to archive session {session_id}")
                    
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Error archiving {session_id}: {str(e)}")
        
        return results
    
    async def get_storage_stats(
        self,
        user_id: UUID,
    ) -> Dict[str, Any]:
        """
        Get storage statistics for a user.
        
        Args:
            user_id: User's UUID.
            
        Returns:
            Dict with stats per tier.
        """
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            await conn.execute("SET app.current_user_id = $1", str(user_id))
            
            # Warm tier stats (PostgreSQL)
            warm_stats = await conn.fetchrow("""
                SELECT 
                    COUNT(DISTINCT s.id) as session_count,
                    COALESCE(SUM(s.message_count), 0) as message_count
                FROM chat_sessions s
                WHERE s.is_active = true
            """)
        
        # Hot tier stats (Redis)
        hot_sessions = await self.cache.get_user_cached_sessions(user_id)
        
        # Cold tier stats (S3)
        cold_archives = []
        if self.archive.is_enabled:
            cold_archives = await self.archive.list_user_archives(user_id)
        
        return {
            "hot_tier": {
                "enabled": self.cache.is_enabled,
                "cached_sessions": len(hot_sessions),
            },
            "warm_tier": {
                "session_count": warm_stats["session_count"] if warm_stats else 0,
                "message_count": warm_stats["message_count"] if warm_stats else 0,
            },
            "cold_tier": {
                "enabled": self.archive.is_enabled,
                "archive_count": len(cold_archives),
                "archives": cold_archives[:10],  # Limit for response size
            },
        }
    
    async def clear_session_cache(
        self,
        user_id: UUID,
        session_id: UUID,
    ) -> bool:
        """
        Clear a session from hot cache.
        
        Args:
            user_id: User's UUID.
            session_id: Session UUID.
            
        Returns:
            True if cleared.
        """
        return await self.cache.invalidate_session(user_id, session_id)


# Global manager instance
_manager: Optional[TieredStorageManager] = None


def get_tiered_storage() -> TieredStorageManager:
    """Get the global tiered storage manager."""
    global _manager
    if _manager is None:
        _manager = TieredStorageManager()
    return _manager


