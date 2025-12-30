"""
Repository for OAuth token operations.

Handles CRUD operations for encrypted OAuth tokens.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import asyncpg

from .crypto import encrypt_token, decrypt_token

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
    
    async def save_tokens(
        self,
        email: str,
        tokens: dict,
        provider: str = "google",
    ) -> bool:
        """
        Save OAuth tokens for a user.
        
        Encrypts and stores the tokens. Updates if exists, inserts if new.
        
        Args:
            email: User's email address.
            tokens: OAuth token data (access_token, refresh_token, etc.).
            provider: OAuth provider name (default: "google").
            
        Returns:
            True if saved successfully.
        """
        try:
            # Encrypt the tokens
            tokens_json = json.dumps(tokens)
            encrypted = encrypt_token(tokens_json)
            
            # Calculate expiry if available
            expires_at = None
            if "expires_in" in tokens:
                expires_at = datetime.now(timezone.utc).replace(
                    microsecond=0
                ) + __import__("datetime").timedelta(seconds=tokens["expires_in"])
            
            # Get scopes
            scopes = tokens.get("scope", "")
            
            async with self.pool.acquire() as conn:
                # Upsert token
                await conn.execute("""
                    INSERT INTO user_oauth_tokens 
                        (email, provider, encrypted_tokens, token_type, expires_at, scopes, is_valid)
                    VALUES ($1, $2, $3, $4, $5, $6, TRUE)
                    ON CONFLICT (email, provider) 
                    DO UPDATE SET
                        encrypted_tokens = EXCLUDED.encrypted_tokens,
                        token_type = EXCLUDED.token_type,
                        expires_at = EXCLUDED.expires_at,
                        scopes = EXCLUDED.scopes,
                        is_valid = TRUE,
                        revoked_at = NULL,
                        revoke_reason = NULL,
                        updated_at = NOW()
                """, email, provider, encrypted, tokens.get("token_type", "Bearer"),
                    expires_at, scopes)
                
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
        Get OAuth tokens for a user.
        
        Retrieves and decrypts the tokens.
        
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
                
                # Decrypt tokens
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
    
    async def get_tokens_needing_refresh(
        self,
        buffer_minutes: int = 5,
    ) -> list:
        """
        Get all tokens that will expire soon and need refresh.
        
        Args:
            buffer_minutes: Minutes before expiry to consider for refresh.
            
        Returns:
            List of (email, provider) tuples needing refresh.
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT email, provider
                    FROM user_oauth_tokens
                    WHERE is_valid = TRUE
                      AND expires_at IS NOT NULL
                      AND expires_at < NOW() + INTERVAL '%s minutes'
                """ % buffer_minutes)
                
                return [(row["email"], row["provider"]) for row in rows]
                
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
        
        Useful for batch operations like contact sync.
        
        Args:
            provider: Filter by provider (optional).
            
        Returns:
            List of email addresses with valid tokens.
        """
        try:
            async with self.pool.acquire() as conn:
                if provider:
                    rows = await conn.fetch("""
                        SELECT email
                        FROM user_oauth_tokens
                        WHERE is_valid = TRUE AND provider = $1
                    """, provider)
                else:
                    rows = await conn.fetch("""
                        SELECT DISTINCT email
                        FROM user_oauth_tokens
                        WHERE is_valid = TRUE
                    """)
                
                return [row["email"] for row in rows]
                
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
        Update the access token after a refresh.
        
        Preserves the refresh token and other data.
        
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

