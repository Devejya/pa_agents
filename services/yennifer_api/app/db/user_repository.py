"""
Repository for User operations.

Handles CRUD operations for users and user identities.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg

from ..core.encryption import (
    generate_user_dek,
    decrypt_user_dek,
    encrypt_for_user,
    decrypt_for_user,
    hash_provider_id,
)

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository for managing users and identities in the database."""
    
    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize the repository.
        
        Args:
            pool: Database connection pool.
        """
        self.pool = pool
    
    async def get_user_by_id(self, user_id: UUID) -> Optional[dict]:
        """
        Get a user by their ID.
        
        Args:
            user_id: User's UUID.
            
        Returns:
            User record if found, None otherwise.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1",
                user_id
            )
            return dict(row) if row else None
    
    async def get_user_by_email(self, email: str) -> Optional[dict]:
        """
        Get a user by their email.
        
        Args:
            email: User's email address.
            
        Returns:
            User record if found, None otherwise.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE email = $1",
                email.lower()
            )
            return dict(row) if row else None
    
    async def find_user_by_oauth(
        self,
        provider: str,
        provider_user_id: str,
    ) -> Optional[dict]:
        """
        Find a user by their OAuth identity.
        
        Used during OAuth callback to check if user exists.
        
        Args:
            provider: OAuth provider (e.g., 'google', 'apple').
            provider_user_id: Provider's user ID (e.g., Google's 'sub' claim).
            
        Returns:
            User record if found, None otherwise.
        """
        provider_hash = hash_provider_id(provider, provider_user_id)
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT u.* 
                FROM users u
                JOIN user_identities ui ON u.id = ui.user_id
                WHERE ui.provider = $1 AND ui.provider_user_id_hash = $2
            """, provider, provider_hash)
            
            return dict(row) if row else None
    
    async def create_user(
        self,
        email: str,
        provider: str,
        provider_user_id: str,
        provider_email: Optional[str] = None,
        timezone: str = "UTC",
    ) -> dict:
        """
        Create a new user with their OAuth identity.
        
        Generates a new DEK for the user and stores it encrypted.
        
        Args:
            email: User's primary email.
            provider: OAuth provider.
            provider_user_id: Provider's user ID.
            provider_email: Email from OAuth provider (may differ from primary).
            timezone: User's timezone.
            
        Returns:
            Created user record with id, email, etc.
            
        Raises:
            Exception: If user creation fails.
        """
        # Generate DEK for new user
        plaintext_dek, encrypted_dek_blob = generate_user_dek()
        
        # Hash provider ID for storage
        provider_hash = hash_provider_id(provider, provider_user_id)
        
        # Encrypt provider email with user's DEK (if provided)
        email_encrypted = None
        if provider_email:
            email_encrypted = encrypt_for_user(plaintext_dek, provider_email)
        
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Create user
                user_row = await conn.fetchrow("""
                    INSERT INTO users (email, encryption_key_blob, timezone)
                    VALUES ($1, $2, $3)
                    RETURNING id, email, timezone, created_at, updated_at
                """, email.lower(), encrypted_dek_blob, timezone)
                
                user_id = user_row["id"]
                
                # Create identity
                await conn.execute("""
                    INSERT INTO user_identities (user_id, provider, provider_user_id_hash, email_encrypted)
                    VALUES ($1, $2, $3, $4)
                """, user_id, provider, provider_hash, email_encrypted)
                
                logger.info(f"Created new user {user_id} for {email} via {provider}")
                
                return dict(user_row)
    
    async def add_identity(
        self,
        user_id: UUID,
        provider: str,
        provider_user_id: str,
        provider_email: Optional[str] = None,
    ) -> bool:
        """
        Add an OAuth identity to an existing user.
        
        Used when linking additional OAuth providers.
        
        Args:
            user_id: User's UUID.
            provider: OAuth provider.
            provider_user_id: Provider's user ID.
            provider_email: Email from OAuth provider.
            
        Returns:
            True if identity was added.
        """
        provider_hash = hash_provider_id(provider, provider_user_id)
        
        # Get user's DEK to encrypt provider email
        user = await self.get_user_by_id(user_id)
        if not user:
            return False
        
        email_encrypted = None
        if provider_email:
            plaintext_dek = decrypt_user_dek(user["encryption_key_blob"])
            email_encrypted = encrypt_for_user(plaintext_dek, provider_email)
        
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO user_identities (user_id, provider, provider_user_id_hash, email_encrypted)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (provider, provider_user_id_hash) DO NOTHING
                """, user_id, provider, provider_hash, email_encrypted)
                
            logger.info(f"Added {provider} identity for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add identity for user {user_id}: {e}")
            return False
    
    async def get_user_dek(self, user_id: UUID) -> Optional[bytes]:
        """
        Get a user's decrypted DEK.
        
        Args:
            user_id: User's UUID.
            
        Returns:
            Decrypted DEK bytes if found, None otherwise.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT encryption_key_blob FROM users WHERE id = $1",
                user_id
            )
            
            if not row:
                return None
            
            return decrypt_user_dek(row["encryption_key_blob"])
    
    async def update_user_settings(
        self,
        user_id: UUID,
        settings: dict,
    ) -> bool:
        """
        Update user settings (encrypted).
        
        Args:
            user_id: User's UUID.
            settings: Settings dictionary to store.
            
        Returns:
            True if updated successfully.
        """
        import json
        
        # Get user's DEK
        dek = await self.get_user_dek(user_id)
        if not dek:
            return False
        
        # Encrypt settings
        settings_json = json.dumps(settings)
        settings_encrypted = encrypt_for_user(dek, settings_json)
        
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE users
                    SET settings_encrypted = $1, updated_at = NOW()
                    WHERE id = $2
                """, settings_encrypted, user_id)
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to update settings for user {user_id}: {e}")
            return False
    
    async def get_user_settings(self, user_id: UUID) -> Optional[dict]:
        """
        Get user settings (decrypted).
        
        Args:
            user_id: User's UUID.
            
        Returns:
            Settings dictionary if found, None otherwise.
        """
        import json
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT encryption_key_blob, settings_encrypted FROM users WHERE id = $1",
                user_id
            )
            
            if not row or not row["settings_encrypted"]:
                return None
            
            # Decrypt settings
            dek = decrypt_user_dek(row["encryption_key_blob"])
            settings_json = decrypt_for_user(dek, row["settings_encrypted"])
            
            return json.loads(settings_json)
    
    async def update_user_timezone(self, user_id: UUID, timezone: str) -> bool:
        """
        Update user's timezone.
        
        Args:
            user_id: User's UUID.
            timezone: IANA timezone string.
            
        Returns:
            True if updated successfully.
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE users
                    SET timezone = $1, updated_at = NOW()
                    WHERE id = $2
                """, timezone, user_id)
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to update timezone for user {user_id}: {e}")
            return False
    
    async def link_oauth_tokens_to_user(self, email: str, user_id: UUID) -> bool:
        """
        Link existing OAuth tokens to a user.
        
        Called after user creation to associate existing tokens.
        
        Args:
            email: User's email.
            user_id: User's UUID.
            
        Returns:
            True if tokens were linked.
        """
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute("""
                    UPDATE user_oauth_tokens
                    SET user_id = $1
                    WHERE email = $2 AND user_id IS NULL
                """, user_id, email.lower())
                
                affected = int(result.split()[-1]) if result else 0
                if affected > 0:
                    logger.info(f"Linked {affected} OAuth tokens to user {user_id}")
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to link OAuth tokens: {e}")
            return False
    
    async def delete_user(self, user_id: UUID) -> bool:
        """
        Delete a user and all associated data.
        
        This will cascade delete identities and tokens.
        
        Args:
            user_id: User's UUID.
            
        Returns:
            True if user was deleted.
        """
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM users WHERE id = $1",
                    user_id
                )
                
                affected = int(result.split()[-1]) if result else 0
                if affected > 0:
                    logger.info(f"Deleted user {user_id}")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete user {user_id}: {e}")
            return False


