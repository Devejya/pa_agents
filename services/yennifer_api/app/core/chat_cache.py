"""
Redis Cache Layer for Hot Chat Messages.

Provides fast access to recent chat messages (< 7 days old).
Messages are stored in Redis with user-scoped keys and TTL.

Key format: chat:{user_id}:session:{session_id}:messages
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

from .config import get_settings

logger = logging.getLogger(__name__)


class ChatCache:
    """Redis cache for hot chat messages."""
    
    # Default TTL: 7 days
    DEFAULT_TTL = 7 * 24 * 60 * 60  # seconds
    
    # Max messages per session in cache
    MAX_MESSAGES_CACHED = 100
    
    def __init__(self, redis_url: Optional[str] = None):
        """
        Initialize the cache.
        
        Args:
            redis_url: Redis connection URL. If None, uses settings.
        """
        self._client: Optional[redis.Redis] = None
        self._redis_url = redis_url
        self._enabled = True
        
    async def _get_client(self) -> Optional[redis.Redis]:
        """Get or create Redis client."""
        if not self._enabled:
            return None
            
        if redis is None:
            logger.warning("Redis library not installed, cache disabled")
            self._enabled = False
            return None
            
        if self._client is None:
            try:
                settings = get_settings()
                url = self._redis_url or getattr(settings, 'redis_url', None)
                
                if not url:
                    logger.info("No Redis URL configured, cache disabled")
                    self._enabled = False
                    return None
                
                self._client = redis.from_url(
                    url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                
                # Test connection
                await self._client.ping()
                logger.info("Redis cache connected")
                
            except Exception as e:
                logger.warning(f"Redis connection failed, cache disabled: {e}")
                self._enabled = False
                self._client = None
                
        return self._client
    
    def _session_key(self, user_id: UUID, session_id: UUID) -> str:
        """Generate Redis key for a session's messages."""
        return f"chat:{user_id}:session:{session_id}:messages"
    
    def _user_sessions_key(self, user_id: UUID) -> str:
        """Generate Redis key for user's session list."""
        return f"chat:{user_id}:sessions"
    
    async def cache_message(
        self,
        user_id: UUID,
        session_id: UUID,
        message: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Cache a chat message.
        
        Args:
            user_id: User's UUID.
            session_id: Session UUID.
            message: Message dict with id, role, content, created_at.
            ttl: Optional TTL in seconds.
            
        Returns:
            True if cached successfully.
        """
        client = await self._get_client()
        if not client:
            return False
            
        try:
            key = self._session_key(user_id, session_id)
            
            # Serialize message
            message_json = json.dumps({
                "id": str(message.get("id")),
                "role": message.get("role"),
                "content": message.get("content"),  # Already decrypted
                "created_at": message.get("created_at"),
                "model": message.get("model"),
            })
            
            # Add to sorted set with timestamp score
            created_at = message.get("created_at")
            if isinstance(created_at, str):
                score = datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
            else:
                score = datetime.now().timestamp()
            
            await client.zadd(key, {message_json: score})
            
            # Trim to max messages
            await client.zremrangebyrank(key, 0, -self.MAX_MESSAGES_CACHED - 1)
            
            # Set TTL
            await client.expire(key, ttl or self.DEFAULT_TTL)
            
            # Track session in user's session list
            sessions_key = self._user_sessions_key(user_id)
            await client.sadd(sessions_key, str(session_id))
            await client.expire(sessions_key, ttl or self.DEFAULT_TTL)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache message: {e}")
            return False
    
    async def get_session_messages(
        self,
        user_id: UUID,
        session_id: UUID,
        limit: int = 100,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get cached messages for a session.
        
        Args:
            user_id: User's UUID.
            session_id: Session UUID.
            limit: Maximum messages to return.
            
        Returns:
            List of message dicts, or None if not cached.
        """
        client = await self._get_client()
        if not client:
            return None
            
        try:
            key = self._session_key(user_id, session_id)
            
            # Check if key exists
            if not await client.exists(key):
                return None
            
            # Get messages ordered by score (timestamp)
            messages_json = await client.zrange(key, 0, limit - 1)
            
            messages = []
            for msg_json in messages_json:
                try:
                    msg = json.loads(msg_json)
                    messages.append(msg)
                except json.JSONDecodeError:
                    continue
            
            return messages
            
        except Exception as e:
            logger.error(f"Failed to get cached messages: {e}")
            return None
    
    async def invalidate_session(
        self,
        user_id: UUID,
        session_id: UUID,
    ) -> bool:
        """
        Remove a session's messages from cache.
        
        Args:
            user_id: User's UUID.
            session_id: Session UUID.
            
        Returns:
            True if invalidated.
        """
        client = await self._get_client()
        if not client:
            return False
            
        try:
            key = self._session_key(user_id, session_id)
            await client.delete(key)
            
            # Remove from user's session list
            sessions_key = self._user_sessions_key(user_id)
            await client.srem(sessions_key, str(session_id))
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to invalidate session cache: {e}")
            return False
    
    async def get_user_cached_sessions(
        self,
        user_id: UUID,
    ) -> List[str]:
        """
        Get list of cached session IDs for a user.
        
        Args:
            user_id: User's UUID.
            
        Returns:
            List of session ID strings.
        """
        client = await self._get_client()
        if not client:
            return []
            
        try:
            sessions_key = self._user_sessions_key(user_id)
            sessions = await client.smembers(sessions_key)
            return list(sessions)
            
        except Exception as e:
            logger.error(f"Failed to get cached sessions: {e}")
            return []
    
    async def warm_cache(
        self,
        user_id: UUID,
        session_id: UUID,
        messages: List[Dict[str, Any]],
    ) -> bool:
        """
        Populate cache from database.
        
        Used when cache miss occurs - load from PostgreSQL and cache.
        
        Args:
            user_id: User's UUID.
            session_id: Session UUID.
            messages: List of message dicts from database.
            
        Returns:
            True if cache warmed successfully.
        """
        client = await self._get_client()
        if not client:
            return False
            
        try:
            key = self._session_key(user_id, session_id)
            
            # Clear existing
            await client.delete(key)
            
            # Add all messages
            for msg in messages:
                await self.cache_message(user_id, session_id, msg)
            
            logger.debug(f"Warmed cache with {len(messages)} messages for session {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to warm cache: {e}")
            return False
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
    
    @property
    def is_enabled(self) -> bool:
        """Check if cache is enabled."""
        return self._enabled


# Global cache instance
_cache: Optional[ChatCache] = None


def get_chat_cache() -> ChatCache:
    """Get the global chat cache instance."""
    global _cache
    if _cache is None:
        _cache = ChatCache()
    return _cache


async def close_chat_cache() -> None:
    """Close the global chat cache."""
    global _cache
    if _cache:
        await _cache.close()
        _cache = None


