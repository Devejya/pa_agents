"""
Repository for OAuth token operations.

Handles CRUD operations for encrypted OAuth tokens.

Supports two encryption modes:
1. Legacy: System-wide Fernet key (for backward compatibility)
2. Multi-tenant: Per-user DEK encrypted by KMS (for new tokens)

Migration path:
- Existing tokens remain encrypted with system key
- New tokens (after user_id is set) use per-user encryption
- Tokens can be migrated to per-user encryption via migrate_to_user_encryption()
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import asyncpg

from .crypto import encrypt_token, decrypt_token
from ..core.encryption import (
    encrypt_for_user,
    decrypt_for_user,
    decrypt_user_dek,
)

logger = logging.getLogger(__name__)


class TokenRepository:
    """Repository for managing OAuth tokens in the database."""
    
    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize the repository.
        
        Args:
            pool: Database connection pool.
        """
        self.pool = pool
    
    # =========================================================================
    # Legacy Methods (email-based, system encryption)
    # Keep for backward compatibility during transition
    # =========================================================================
    
    async def save_tokens(
        self,
        email: str,
        tokens: dict,
        provider: str = "google",
        user_id: Optional[UUID] = None,
    ) -> bool:
        """
        Save OAuth tokens for a user (legacy method).
        
        Uses system-wide encryption. For per-user encryption,
        use save_tokens_for_user() instead.
        
        Args:
            email: User's email address.
            tokens: OAuth token data (access_token, refresh_token, etc.).
            provider: OAuth provider name (default: "google").
            user_id: Optional user ID to link tokens to.
            
        Returns:
            True if saved successfully.
        """
        try:
            # Encrypt with system key (legacy)
            tokens_json = json.dumps(tokens)
            encrypted = encrypt_token(tokens_json)
            
            # Calculate expiry if available
            expires_at = None
            if "expires_in" in tokens:
                expires_at = datetime.now(timezone.utc).replace(
                    microsecond=0
                ) + timedelta(seconds=tokens["expires_in"])
            
            # Get scopes
            scopes = tokens.get("scope", "")
            
            async with self.pool.acquire() as conn:
                # Upsert token
                await conn.execute("""
                    INSERT INTO user_oauth_tokens 
                        (email, provider, encrypted_tokens, token_type, expires_at, scopes, is_valid, user_id)
                    VALUES ($1, $2, $3, $4, $5, $6, TRUE, $7)
                    ON CONFLICT (email, provider) 
                    DO UPDATE SET
                        encrypted_tokens = EXCLUDED.encrypted_tokens,
                        token_type = EXCLUDED.token_type,
                        expires_at = EXCLUDED.expires_at,
                        scopes = EXCLUDED.scopes,
                        is_valid = TRUE,
                        revoked_at = NULL,
                        revoke_reason = NULL,
                        user_id = COALESCE(EXCLUDED.user_id, user_oauth_tokens.user_id),
                        updated_at = NOW()
                """, email, provider, encrypted, tokens.get("token_type", "Bearer"),
                    expires_at, scopes, user_id)
                
            logger.info(f"Saved tokens for {email} ({provider})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save tokens for {email}: {e}")
            raise
    
    async def get_tokens(
        self,
        email: str,
        provider: str = "google",
    ) -> Optional[dict]:
        """
        Get OAuth tokens for a user (legacy method).
        
        Uses system-wide decryption. For per-user decryption,
        use get_tokens_for_user() instead.
        
        Args:
            email: User's email address.
            provider: OAuth provider name (default: "google").
            
        Returns:
            Token dictionary if found and valid, None otherwise.
        """
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT encrypted_tokens, is_valid, expires_at
                    FROM user_oauth_tokens
                    WHERE email = $1 AND provider = $2 AND is_valid = TRUE
                """, email, provider)
                
                if not row:
                    return None
                
                # Decrypt with system key (legacy)
                decrypted = decrypt_token(row["encrypted_tokens"])
                tokens = json.loads(decrypted)
                
                # Update last used timestamp
                await conn.execute("""
                    UPDATE user_oauth_tokens
                    SET last_used_at = NOW()
                    WHERE email = $1 AND provider = $2
                """, email, provider)
                
                return tokens
                
        except Exception as e:
            logger.error(f"Failed to get tokens for {email}: {e}")
            return None
    
    async def delete_tokens(
        self,
        email: str,
        provider: str = "google",
        reason: str = "user_logout",
    ) -> bool:
        """
        Mark tokens as revoked (soft delete).
        
        Args:
            email: User's email address.
            provider: OAuth provider name (default: "google").
            reason: Reason for revocation.
            
        Returns:
            True if tokens were revoked.
        """
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute("""
                    UPDATE user_oauth_tokens
                    SET is_valid = FALSE,
                        revoked_at = NOW(),
                        revoke_reason = $3
                    WHERE email = $1 AND provider = $2 AND is_valid = TRUE
                """, email, provider, reason)
                
                # Check if any rows were updated
                affected = int(result.split()[-1]) if result else 0
                
                if affected > 0:
                    logger.info(f"Revoked tokens for {email} ({provider}): {reason}")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete tokens for {email}: {e}")
            return False
    
    # =========================================================================
    # New Methods (user_id-based, per-user encryption)
    # =========================================================================
    
    async def save_tokens_for_user(
        self,
        user_id: UUID,
        tokens: dict,
        provider: str = "google",
        email: Optional[str] = None,
    ) -> bool:
        """
        Save OAuth tokens with per-user encryption.
        
        Encrypts tokens using the user's DEK from the users table.
        
        Args:
            user_id: User's UUID.
            tokens: OAuth token data (access_token, refresh_token, etc.).
            provider: OAuth provider name.
            email: User's email (optional, for backward compatibility).
            
        Returns:
            True if saved successfully.
        """
        try:
            async with self.pool.acquire() as conn:
                # Get user's DEK
                user_row = await conn.fetchrow(
                    "SELECT email, encryption_key_blob FROM users WHERE id = $1",
                    user_id
                )
                
                if not user_row:
                    logger.error(f"User {user_id} not found")
                    return False
                
                user_email = email or user_row["email"]
                user_dek = decrypt_user_dek(user_row["encryption_key_blob"])
                
                # Encrypt with user's DEK
                tokens_json = json.dumps(tokens)
                encrypted = encrypt_for_user(user_dek, tokens_json)
                
                # Calculate expiry if available
                expires_at = None
                if "expires_in" in tokens:
                    expires_at = datetime.now(timezone.utc).replace(
                        microsecond=0
                    ) + timedelta(seconds=tokens["expires_in"])
                
                scopes = tokens.get("scope", "")
                
                # Upsert token with user_id
                await conn.execute("""
                    INSERT INTO user_oauth_tokens 
                        (email, provider, encrypted_tokens, token_type, expires_at, scopes, is_valid, user_id)
                    VALUES ($1, $2, $3, $4, $5, $6, TRUE, $7)
                    ON CONFLICT (email, provider) 
                    DO UPDATE SET
                        encrypted_tokens = EXCLUDED.encrypted_tokens,
                        token_type = EXCLUDED.token_type,
                        expires_at = EXCLUDED.expires_at,
                        scopes = EXCLUDED.scopes,
                        is_valid = TRUE,
                        revoked_at = NULL,
                        revoke_reason = NULL,
                        user_id = EXCLUDED.user_id,
                        updated_at = NOW()
                """, user_email, provider, encrypted, tokens.get("token_type", "Bearer"),
                    expires_at, scopes, user_id)
                
                logger.info(f"Saved tokens for user {user_id} ({provider}) with per-user encryption")
                return True
                
        except Exception as e:
            logger.error(f"Failed to save tokens for user {user_id}: {e}")
            raise
    
    async def get_tokens_for_user(
        self,
        user_id: UUID,
        provider: str = "google",
    ) -> Optional[dict]:
        """
        Get OAuth tokens using per-user decryption.
        
        Args:
            user_id: User's UUID.
            provider: OAuth provider name.
            
        Returns:
            Token dictionary if found and valid, None otherwise.
        """
        try:
            async with self.pool.acquire() as conn:
                # Get token and user's DEK in one query
                row = await conn.fetchrow("""
                    SELECT t.encrypted_tokens, t.is_valid, t.expires_at, u.encryption_key_blob
                    FROM user_oauth_tokens t
                    JOIN users u ON t.user_id = u.id
                    WHERE t.user_id = $1 AND t.provider = $2 AND t.is_valid = TRUE
                """, user_id, provider)
                
                if not row:
                    return None
                
                # Decrypt with user's DEK
                user_dek = decrypt_user_dek(row["encryption_key_blob"])
                decrypted = decrypt_for_user(user_dek, row["encrypted_tokens"])
                tokens = json.loads(decrypted)
                
                # Update last used timestamp
                await conn.execute("""
                    UPDATE user_oauth_tokens
                    SET last_used_at = NOW()
                    WHERE user_id = $1 AND provider = $2
                """, user_id, provider)
                
                return tokens
                
        except Exception as e:
            logger.error(f"Failed to get tokens for user {user_id}: {e}")
            return None
    
    async def delete_tokens_for_user(
        self,
        user_id: UUID,
        provider: str = "google",
        reason: str = "user_logout",
    ) -> bool:
        """
        Mark tokens as revoked for a user.
        
        Args:
            user_id: User's UUID.
            provider: OAuth provider name.
            reason: Reason for revocation.
            
        Returns:
            True if tokens were revoked.
        """
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute("""
                    UPDATE user_oauth_tokens
                    SET is_valid = FALSE,
                        revoked_at = NOW(),
                        revoke_reason = $3
                    WHERE user_id = $1 AND provider = $2 AND is_valid = TRUE
                """, user_id, provider, reason)
                
                affected = int(result.split()[-1]) if result else 0
                
                if affected > 0:
                    logger.info(f"Revoked tokens for user {user_id} ({provider}): {reason}")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete tokens for user {user_id}: {e}")
            return False
    
    # =========================================================================
    # Migration Methods
    # =========================================================================
    
    async def migrate_to_user_encryption(
        self,
        email: str,
        user_id: UUID,
        provider: str = "google",
    ) -> bool:
        """
        Migrate a token from system encryption to per-user encryption.
        
        1. Reads token with system key
        2. Re-encrypts with user's DEK
        3. Updates the record
        
        Args:
            email: User's email.
            user_id: User's UUID.
            provider: OAuth provider.
            
        Returns:
            True if migration successful.
        """
        try:
            # Get tokens using legacy (system) encryption
            tokens = await self.get_tokens(email, provider)
            if not tokens:
                logger.warning(f"No tokens to migrate for {email}")
                return False
            
            # Save using per-user encryption
            success = await self.save_tokens_for_user(user_id, tokens, provider, email)
            
            if success:
                logger.info(f"Migrated tokens for {email} to per-user encryption")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to migrate tokens for {email}: {e}")
            return False
    
    async def migrate_all_user_tokens(self, user_id: UUID, email: str) -> dict:
        """
        Migrate all tokens for a user to per-user encryption.
        
        Args:
            user_id: User's UUID.
            email: User's email.
            
        Returns:
            Dict with migration results per provider.
        """
        results = {}
        
        async with self.pool.acquire() as conn:
            # Get all providers for this user
            rows = await conn.fetch("""
                SELECT DISTINCT provider 
                FROM user_oauth_tokens 
                WHERE email = $1 AND is_valid = TRUE
            """, email)
            
            for row in rows:
                provider = row["provider"]
                success = await self.migrate_to_user_encryption(email, user_id, provider)
                results[provider] = success
        
        logger.info(f"Migration results for {email}: {results}")
        return results
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    async def get_tokens_needing_refresh(
        self,
        buffer_minutes: int = 5,
    ) -> list:
        """
        Get all tokens that will expire soon and need refresh.
        
        Args:
            buffer_minutes: Minutes before expiry to consider for refresh.
            
        Returns:
            List of (email, provider, user_id) tuples needing refresh.
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT email, provider, user_id
                    FROM user_oauth_tokens
                    WHERE is_valid = TRUE
                      AND expires_at IS NOT NULL
                      AND expires_at < NOW() + INTERVAL '%s minutes'
                """ % buffer_minutes)
                
                return [(row["email"], row["provider"], row["user_id"]) for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to get tokens needing refresh: {e}")
            return []
    
    async def mark_token_invalid(
        self,
        email: str,
        provider: str = "google",
        reason: str = "token_expired",
    ) -> None:
        """
        Mark a token as invalid (e.g., after refresh failure).
        
        Args:
            email: User's email address.
            provider: OAuth provider name.
            reason: Reason for invalidation.
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE user_oauth_tokens
                    SET is_valid = FALSE,
                        revoked_at = NOW(),
                        revoke_reason = $3
                    WHERE email = $1 AND provider = $2
                """, email, provider, reason)
                
            logger.info(f"Marked tokens invalid for {email} ({provider}): {reason}")
            
        except Exception as e:
            logger.error(f"Failed to mark token invalid for {email}: {e}")
    
    async def get_all_valid_tokens(
        self,
        provider: Optional[str] = None,
    ) -> list:
        """
        Get all users with valid tokens.
        
        Args:
            provider: Filter by provider (optional).
            
        Returns:
            List of (email, user_id) tuples with valid tokens.
        """
        try:
            async with self.pool.acquire() as conn:
                if provider:
                    rows = await conn.fetch("""
                        SELECT email, user_id
                        FROM user_oauth_tokens
                        WHERE is_valid = TRUE AND provider = $1
                    """, provider)
                else:
                    rows = await conn.fetch("""
                        SELECT DISTINCT email, user_id
                        FROM user_oauth_tokens
                        WHERE is_valid = TRUE
                    """)
                
                return [(row["email"], row["user_id"]) for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to get valid tokens: {e}")
            return []
    
    async def update_tokens(
        self,
        email: str,
        new_access_token: str,
        expires_in: Optional[int] = None,
        provider: str = "google",
    ) -> bool:
        """
        Update the access token after a refresh (legacy method).
        
        Args:
            email: User's email address.
            new_access_token: New access token from refresh.
            expires_in: Token lifetime in seconds.
            provider: OAuth provider name.
            
        Returns:
            True if updated successfully.
        """
        try:
            # Get existing tokens
            tokens = await self.get_tokens(email, provider)
            if not tokens:
                return False
            
            # Update access token
            tokens["access_token"] = new_access_token
            if expires_in:
                tokens["expires_in"] = expires_in
            
            # Save updated tokens
            return await self.save_tokens(email, tokens, provider)
            
        except Exception as e:
            logger.error(f"Failed to update tokens for {email}: {e}")
            return False
    
    async def update_tokens_for_user(
        self,
        user_id: UUID,
        new_access_token: str,
        expires_in: Optional[int] = None,
        provider: str = "google",
    ) -> bool:
        """
        Update the access token after a refresh (per-user method).
        
        Args:
            user_id: User's UUID.
            new_access_token: New access token from refresh.
            expires_in: Token lifetime in seconds.
            provider: OAuth provider name.
            
        Returns:
            True if updated successfully.
        """
        try:
            # Get existing tokens
            tokens = await self.get_tokens_for_user(user_id, provider)
            if not tokens:
                return False
            
            # Update access token
            tokens["access_token"] = new_access_token
            if expires_in:
                tokens["expires_in"] = expires_in
            
            # Save updated tokens
            return await self.save_tokens_for_user(user_id, tokens, provider)
            
        except Exception as e:
            logger.error(f"Failed to update tokens for user {user_id}: {e}")
            return False
    
    async def get_tokens_without_user_id(self) -> list:
        """
        Get all tokens that don't have a user_id linked.
        
        Used for migration to identify tokens needing update.
        
        Returns:
            List of (email, provider) tuples without user_id.
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT email, provider
                    FROM user_oauth_tokens
                    WHERE user_id IS NULL AND is_valid = TRUE
                """)
                
                return [(row["email"], row["provider"]) for row in rows]
                
        except Exception as e:
            logger.error(f"Failed to get tokens without user_id: {e}")
            return []
    
    async def link_token_to_user(self, email: str, user_id: UUID) -> bool:
        """
        Link an existing token to a user (without re-encrypting).
        
        Used when a user is created after tokens already exist.
        
        Args:
            email: User's email.
            user_id: User's UUID.
            
        Returns:
            True if link was successful.
        """
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute("""
                    UPDATE user_oauth_tokens
                    SET user_id = $2, updated_at = NOW()
                    WHERE email = $1 AND user_id IS NULL
                """, email, user_id)
                
                affected = int(result.split()[-1]) if result else 0
                
                if affected > 0:
                    logger.info(f"Linked {affected} token(s) for {email} to user {user_id}")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Failed to link token to user: {e}")
            return False

