"""
Repository for Chat operations.

Handles CRUD operations for chat sessions and messages with per-user encryption.
All message content is encrypted using the user's DEK before storage.
"""

import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

import asyncpg

from ..core.encryption import (
    encrypt_for_user,
    decrypt_for_user,
    decrypt_user_dek,
)

logger = logging.getLogger(__name__)


class ChatRepository:
    """Repository for managing chat sessions and messages."""
    
    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize the repository.
        
        Args:
            pool: Database connection pool.
        """
        self.pool = pool
    
    # =========================================================================
    # Session Management
    # =========================================================================
    
    async def create_session(
        self,
        user_id: UUID,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new chat session for a user.
        
        Args:
            user_id: The user's UUID.
            title: Optional session title.
            
        Returns:
            Dict with session data.
        """
        try:
            async with self.pool.acquire() as conn:
                # Set RLS context
                await conn.execute(
                    "SELECT set_config('app.current_user_id', $1, false)",
                    str(user_id)
                )
                
                row = await conn.fetchrow("""
                    INSERT INTO chat_sessions (user_id, title)
                    VALUES ($1, $2)
                    RETURNING id, user_id, title, is_active, created_at, message_count
                """, user_id, title)
                
                logger.info(f"Created chat session {row['id']} for user {user_id}")
                
                return {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "title": row["title"],
                    "is_active": row["is_active"],
                    "created_at": row["created_at"].isoformat(),
                    "message_count": row["message_count"],
                }
                
        except Exception as e:
            logger.error(f"Failed to create session for user {user_id}: {e}")
            raise
    
    async def get_session(
        self,
        user_id: UUID,
        session_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a specific chat session.
        
        Args:
            user_id: The user's UUID (for RLS).
            session_id: The session UUID.
            
        Returns:
            Session dict or None if not found.
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "SELECT set_config('app.current_user_id', $1, false)",
                    str(user_id)
                )
                
                row = await conn.fetchrow("""
                    SELECT id, user_id, title, is_active, created_at, updated_at,
                           last_message_at, message_count
                    FROM chat_sessions
                    WHERE id = $1
                """, session_id)
                
                if not row:
                    return None
                
                return {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "title": row["title"],
                    "is_active": row["is_active"],
                    "created_at": row["created_at"].isoformat(),
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                    "last_message_at": row["last_message_at"].isoformat() if row["last_message_at"] else None,
                    "message_count": row["message_count"],
                }
                
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return None
    
    async def get_user_sessions(
        self,
        user_id: UUID,
        include_inactive: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Get all chat sessions for a user.
        
        Args:
            user_id: The user's UUID.
            include_inactive: Whether to include inactive sessions.
            limit: Maximum number of sessions to return.
            offset: Number of sessions to skip.
            
        Returns:
            List of session dicts.
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "SELECT set_config('app.current_user_id', $1, false)",
                    str(user_id)
                )
                
                if include_inactive:
                    rows = await conn.fetch("""
                        SELECT id, user_id, title, is_active, created_at, updated_at,
                               last_message_at, message_count
                        FROM chat_sessions
                        ORDER BY COALESCE(last_message_at, created_at) DESC
                        LIMIT $1 OFFSET $2
                    """, limit, offset)
                else:
                    rows = await conn.fetch("""
                        SELECT id, user_id, title, is_active, created_at, updated_at,
                               last_message_at, message_count
                        FROM chat_sessions
                        WHERE is_active = true
                        ORDER BY COALESCE(last_message_at, created_at) DESC
                        LIMIT $1 OFFSET $2
                    """, limit, offset)
                
                return [
                    {
                        "id": row["id"],
                        "user_id": row["user_id"],
                        "title": row["title"],
                        "is_active": row["is_active"],
                        "created_at": row["created_at"].isoformat(),
                        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                        "last_message_at": row["last_message_at"].isoformat() if row["last_message_at"] else None,
                        "message_count": row["message_count"],
                    }
                    for row in rows
                ]
                
        except Exception as e:
            logger.error(f"Failed to get sessions for user {user_id}: {e}")
            return []
    
    async def update_session_title(
        self,
        user_id: UUID,
        session_id: UUID,
        title: str,
    ) -> bool:
        """
        Update a session's title.
        
        Args:
            user_id: The user's UUID.
            session_id: The session UUID.
            title: New title.
            
        Returns:
            True if updated successfully.
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "SELECT set_config('app.current_user_id', $1, false)",
                    str(user_id)
                )
                
                result = await conn.execute("""
                    UPDATE chat_sessions
                    SET title = $2
                    WHERE id = $1
                """, session_id, title)
                
                affected = int(result.split()[-1]) if result else 0
                return affected > 0
                
        except Exception as e:
            logger.error(f"Failed to update session {session_id}: {e}")
            return False
    
    async def deactivate_session(
        self,
        user_id: UUID,
        session_id: UUID,
    ) -> bool:
        """
        Deactivate a chat session (soft delete).
        
        Args:
            user_id: The user's UUID.
            session_id: The session UUID.
            
        Returns:
            True if deactivated successfully.
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "SELECT set_config('app.current_user_id', $1, false)",
                    str(user_id)
                )
                
                result = await conn.execute("""
                    UPDATE chat_sessions
                    SET is_active = false
                    WHERE id = $1
                """, session_id)
                
                affected = int(result.split()[-1]) if result else 0
                return affected > 0
                
        except Exception as e:
            logger.error(f"Failed to deactivate session {session_id}: {e}")
            return False
    
    async def get_or_create_active_session(
        self,
        user_id: UUID,
    ) -> Dict[str, Any]:
        """
        Get the most recent active session or create a new one.
        
        This is useful for single-session implementations.
        
        Args:
            user_id: The user's UUID.
            
        Returns:
            Session dict.
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "SELECT set_config('app.current_user_id', $1, false)",
                    str(user_id)
                )
                
                # Try to find an active session
                row = await conn.fetchrow("""
                    SELECT id, user_id, title, is_active, created_at, updated_at,
                           last_message_at, message_count
                    FROM chat_sessions
                    WHERE is_active = true
                    ORDER BY COALESCE(last_message_at, created_at) DESC
                    LIMIT 1
                """)
                
                if row:
                    return {
                        "id": row["id"],
                        "user_id": row["user_id"],
                        "title": row["title"],
                        "is_active": row["is_active"],
                        "created_at": row["created_at"].isoformat(),
                        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                        "last_message_at": row["last_message_at"].isoformat() if row["last_message_at"] else None,
                        "message_count": row["message_count"],
                    }
                
                # No active session, create one
                return await self.create_session(user_id)
                
        except Exception as e:
            logger.error(f"Failed to get/create session for user {user_id}: {e}")
            raise
    
    # =========================================================================
    # Message Management
    # =========================================================================
    
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
        Add a message to a session with encryption.
        
        Args:
            user_id: The user's UUID.
            session_id: The session UUID.
            role: Message role ('user', 'assistant', 'system').
            content: Message content (will be encrypted).
            tool_calls: Optional list of tool calls (will be encrypted).
            tokens_used: Optional token count.
            model: Optional model name.
            
        Returns:
            Dict with message data (content decrypted).
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "SELECT set_config('app.current_user_id', $1, false)",
                    str(user_id)
                )
                
                # Get user's DEK
                user_row = await conn.fetchrow(
                    "SELECT encryption_key_blob FROM users WHERE id = $1",
                    user_id
                )
                
                if not user_row:
                    raise ValueError(f"User {user_id} not found")
                
                user_dek = decrypt_user_dek(user_row["encryption_key_blob"])
                
                # Encrypt content
                content_encrypted = encrypt_for_user(user_dek, content)
                
                # Encrypt tool calls if present
                tool_calls_encrypted = None
                if tool_calls:
                    tool_calls_json = json.dumps(tool_calls)
                    tool_calls_encrypted = encrypt_for_user(user_dek, tool_calls_json)
                
                # Insert message
                row = await conn.fetchrow("""
                    INSERT INTO chat_messages 
                        (session_id, user_id, role, content_encrypted, tool_calls_encrypted, 
                         tokens_used, model)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id, session_id, user_id, role, created_at, tokens_used, model
                """, session_id, user_id, role, content_encrypted, tool_calls_encrypted,
                    tokens_used, model)
                
                logger.debug(f"Added {role} message to session {session_id}")
                
                return {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "user_id": row["user_id"],
                    "role": row["role"],
                    "content": content,  # Return decrypted
                    "tool_calls": tool_calls,
                    "tokens_used": row["tokens_used"],
                    "model": row["model"],
                    "created_at": row["created_at"].isoformat(),
                }
                
        except Exception as e:
            logger.error(f"Failed to add message to session {session_id}: {e}")
            raise
    
    async def get_session_messages(
        self,
        user_id: UUID,
        session_id: UUID,
        limit: int = 100,
        before_id: Optional[UUID] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get messages for a session with decryption.
        
        Args:
            user_id: The user's UUID.
            session_id: The session UUID.
            limit: Maximum number of messages.
            before_id: Get messages before this message ID (for pagination).
            
        Returns:
            List of message dicts with decrypted content.
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "SELECT set_config('app.current_user_id', $1, false)",
                    str(user_id)
                )
                
                # Get user's DEK
                user_row = await conn.fetchrow(
                    "SELECT encryption_key_blob FROM users WHERE id = $1",
                    user_id
                )
                
                if not user_row:
                    return []
                
                user_dek = decrypt_user_dek(user_row["encryption_key_blob"])
                
                # Build query
                if before_id:
                    rows = await conn.fetch("""
                        SELECT id, session_id, user_id, role, content_encrypted,
                               tool_calls_encrypted, tokens_used, model, created_at
                        FROM chat_messages
                        WHERE session_id = $1 AND id < $2
                        ORDER BY created_at DESC
                        LIMIT $3
                    """, session_id, before_id, limit)
                else:
                    rows = await conn.fetch("""
                        SELECT id, session_id, user_id, role, content_encrypted,
                               tool_calls_encrypted, tokens_used, model, created_at
                        FROM chat_messages
                        WHERE session_id = $1
                        ORDER BY created_at ASC
                        LIMIT $2
                    """, session_id, limit)
                
                messages = []
                for row in rows:
                    # Decrypt content
                    content = decrypt_for_user(user_dek, row["content_encrypted"])
                    
                    # Decrypt tool calls if present
                    tool_calls = None
                    if row["tool_calls_encrypted"]:
                        tool_calls_json = decrypt_for_user(user_dek, row["tool_calls_encrypted"])
                        tool_calls = json.loads(tool_calls_json)
                    
                    messages.append({
                        "id": row["id"],
                        "session_id": row["session_id"],
                        "user_id": row["user_id"],
                        "role": row["role"],
                        "content": content,
                        "tool_calls": tool_calls,
                        "tokens_used": row["tokens_used"],
                        "model": row["model"],
                        "created_at": row["created_at"].isoformat(),
                    })
                
                return messages
                
        except Exception as e:
            logger.error(f"Failed to get messages for session {session_id}: {e}")
            return []
    
    async def get_recent_messages_for_context(
        self,
        user_id: UUID,
        session_id: UUID,
        limit: int = 20,
    ) -> List[Dict[str, str]]:
        """
        Get recent messages in a format suitable for LLM context.
        
        Args:
            user_id: The user's UUID.
            session_id: The session UUID.
            limit: Maximum number of messages.
            
        Returns:
            List of {"role": ..., "content": ...} dicts.
        """
        messages = await self.get_session_messages(user_id, session_id, limit)
        
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in messages
        ]
    
    async def delete_session_messages(
        self,
        user_id: UUID,
        session_id: UUID,
    ) -> int:
        """
        Delete all messages in a session.
        
        Args:
            user_id: The user's UUID.
            session_id: The session UUID.
            
        Returns:
            Number of messages deleted.
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "SELECT set_config('app.current_user_id', $1, false)",
                    str(user_id)
                )
                
                result = await conn.execute("""
                    DELETE FROM chat_messages
                    WHERE session_id = $1
                """, session_id)
                
                affected = int(result.split()[-1]) if result else 0
                
                # Reset session message count
                await conn.execute("""
                    UPDATE chat_sessions
                    SET message_count = 0, last_message_at = NULL
                    WHERE id = $1
                """, session_id)
                
                logger.info(f"Deleted {affected} messages from session {session_id}")
                return affected
                
        except Exception as e:
            logger.error(f"Failed to delete messages from session {session_id}: {e}")
            return 0
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    async def get_user_message_count(
        self,
        user_id: UUID,
    ) -> int:
        """
        Get total message count for a user.
        
        Args:
            user_id: The user's UUID.
            
        Returns:
            Total number of messages.
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "SELECT set_config('app.current_user_id', $1, false)",
                    str(user_id)
                )
                
                row = await conn.fetchrow("""
                    SELECT COALESCE(SUM(message_count), 0) as total
                    FROM chat_sessions
                """)
                
                return row["total"] if row else 0
                
        except Exception as e:
            logger.error(f"Failed to get message count for user {user_id}: {e}")
            return 0
    
    async def auto_title_session(
        self,
        user_id: UUID,
        session_id: UUID,
    ) -> Optional[str]:
        """
        Generate a title for a session based on the first user message.
        
        Args:
            user_id: The user's UUID.
            session_id: The session UUID.
            
        Returns:
            Generated title or None.
        """
        try:
            messages = await self.get_session_messages(user_id, session_id, limit=1)
            
            if not messages:
                return None
            
            first_message = messages[0]
            if first_message["role"] != "user":
                return None
            
            # Truncate to first 50 chars
            content = first_message["content"]
            if len(content) > 50:
                title = content[:47] + "..."
            else:
                title = content
            
            # Update the session
            await self.update_session_title(user_id, session_id, title)
            
            return title
            
        except Exception as e:
            logger.error(f"Failed to auto-title session {session_id}: {e}")
            return None


