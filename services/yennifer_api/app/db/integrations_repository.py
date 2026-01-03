"""
Repository for integration management.

Handles CRUD operations for user integrations and scopes.
Integration definitions (integrations, integration_scopes) are seed data.
User preferences (user_integrations, user_integration_scopes) are per-user.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class IntegrationsRepository:
    """Repository for managing integrations and user integration settings."""
    
    def __init__(self, pool: asyncpg.Pool):
        """Initialize the repository with a database connection pool."""
        self.pool = pool
    
    # =========================================================================
    # Integration Definitions (Read-only seed data)
    # =========================================================================
    
    async def get_all_integrations(
        self,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get all available integrations.
        
        Args:
            active_only: If True, only return active integrations
            
        Returns:
            List of integration definitions
        """
        async with self.pool.acquire() as conn:
            if active_only:
                rows = await conn.fetch("""
                    SELECT id, provider, name, description, capability_summary,
                           icon_url, is_active, display_order, created_at
                    FROM integrations
                    WHERE is_active = TRUE
                    ORDER BY display_order
                """)
            else:
                rows = await conn.fetch("""
                    SELECT id, provider, name, description, capability_summary,
                           icon_url, is_active, display_order, created_at
                    FROM integrations
                    ORDER BY display_order
                """)
            
            return [dict(row) for row in rows]
    
    async def get_integration(self, integration_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single integration by ID.
        
        Args:
            integration_id: Integration identifier (e.g., 'gmail')
            
        Returns:
            Integration definition or None if not found
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, provider, name, description, capability_summary,
                       icon_url, is_active, display_order, created_at
                FROM integrations
                WHERE id = $1
            """, integration_id)
            
            return dict(row) if row else None
    
    async def get_integration_scopes(
        self, 
        integration_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all scopes for an integration.
        
        Args:
            integration_id: Integration identifier
            
        Returns:
            List of scope definitions
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, integration_id, scope_uri, name, description,
                       is_required, display_order
                FROM integration_scopes
                WHERE integration_id = $1
                ORDER BY display_order
            """, integration_id)
            
            return [dict(row) for row in rows]
    
    async def get_all_scopes(self) -> List[Dict[str, Any]]:
        """Get all scope definitions across all integrations."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT s.id, s.integration_id, s.scope_uri, s.name, s.description,
                       s.is_required, s.display_order, i.provider
                FROM integration_scopes s
                JOIN integrations i ON s.integration_id = i.id
                WHERE i.is_active = TRUE
                ORDER BY i.display_order, s.display_order
            """)
            
            return [dict(row) for row in rows]
    
    # =========================================================================
    # User Integration Settings
    # =========================================================================
    
    async def get_user_integrations(
        self,
        user_id: UUID,
        enabled_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get user's integration settings with integration details.
        
        Args:
            user_id: User's UUID
            enabled_only: If True, only return enabled integrations
            
        Returns:
            List of integrations with user's enabled status
        """
        async with self.pool.acquire() as conn:
            # Get all active integrations with user's settings
            rows = await conn.fetch("""
                SELECT 
                    i.id, i.provider, i.name, i.description, i.capability_summary,
                    i.icon_url, i.display_order,
                    COALESCE(ui.is_enabled, FALSE) as is_enabled,
                    ui.enabled_at,
                    ui.disabled_at
                FROM integrations i
                LEFT JOIN user_integrations ui ON i.id = ui.integration_id AND ui.user_id = $1
                WHERE i.is_active = TRUE
                ORDER BY i.display_order
            """, user_id)
            
            result = [dict(row) for row in rows]
            
            if enabled_only:
                result = [r for r in result if r["is_enabled"]]
            
            return result
    
    async def get_user_integration(
        self,
        user_id: UUID,
        integration_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a single integration with user's settings and all scopes.
        
        Args:
            user_id: User's UUID
            integration_id: Integration identifier
            
        Returns:
            Integration with user settings and scopes, or None
        """
        async with self.pool.acquire() as conn:
            # Get integration with user settings
            integration_row = await conn.fetchrow("""
                SELECT 
                    i.id, i.provider, i.name, i.description, i.capability_summary,
                    i.icon_url, i.display_order,
                    COALESCE(ui.is_enabled, FALSE) as is_enabled,
                    ui.enabled_at,
                    ui.disabled_at
                FROM integrations i
                LEFT JOIN user_integrations ui ON i.id = ui.integration_id AND ui.user_id = $1
                WHERE i.id = $2 AND i.is_active = TRUE
            """, user_id, integration_id)
            
            if not integration_row:
                return None
            
            integration = dict(integration_row)
            
            # Get scopes with user settings
            scope_rows = await conn.fetch("""
                SELECT 
                    s.id, s.scope_uri, s.name, s.description, s.is_required, s.display_order,
                    COALESCE(us.is_enabled, FALSE) as is_enabled,
                    COALESCE(us.is_granted, FALSE) as is_granted,
                    us.granted_at
                FROM integration_scopes s
                LEFT JOIN user_integration_scopes us ON s.id = us.scope_id AND us.user_id = $1
                WHERE s.integration_id = $2
                ORDER BY s.display_order
            """, user_id, integration_id)
            
            integration["scopes"] = [dict(row) for row in scope_rows]
            
            return integration
    
    async def enable_integration(
        self,
        user_id: UUID,
        integration_id: str,
        enable_required_scopes: bool = True
    ) -> Dict[str, Any]:
        """
        Enable an integration for a user.
        
        Args:
            user_id: User's UUID
            integration_id: Integration identifier
            enable_required_scopes: If True, also enable all required scopes
            
        Returns:
            Updated integration settings
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Upsert user_integrations
                await conn.execute("""
                    INSERT INTO user_integrations (user_id, integration_id, is_enabled, enabled_at)
                    VALUES ($1, $2, TRUE, NOW())
                    ON CONFLICT (user_id, integration_id)
                    DO UPDATE SET
                        is_enabled = TRUE,
                        enabled_at = NOW(),
                        disabled_at = NULL,
                        updated_at = NOW()
                """, user_id, integration_id)
                
                # If enabling required scopes, upsert them too
                if enable_required_scopes:
                    await conn.execute("""
                        INSERT INTO user_integration_scopes (user_id, scope_id, is_enabled)
                        SELECT $1, id, TRUE
                        FROM integration_scopes
                        WHERE integration_id = $2 AND is_required = TRUE
                        ON CONFLICT (user_id, scope_id)
                        DO UPDATE SET
                            is_enabled = TRUE,
                            updated_at = NOW()
                    """, user_id, integration_id)
                
                logger.info(f"Enabled integration {integration_id} for user {user_id}")
        
        return await self.get_user_integration(user_id, integration_id)
    
    async def disable_integration(
        self,
        user_id: UUID,
        integration_id: str,
        disable_all_scopes: bool = True
    ) -> Dict[str, Any]:
        """
        Disable an integration for a user (local only, keeps OAuth token).
        
        Args:
            user_id: User's UUID
            integration_id: Integration identifier
            disable_all_scopes: If True, also disable all scopes
            
        Returns:
            Updated integration settings
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Update user_integrations
                await conn.execute("""
                    INSERT INTO user_integrations (user_id, integration_id, is_enabled, disabled_at)
                    VALUES ($1, $2, FALSE, NOW())
                    ON CONFLICT (user_id, integration_id)
                    DO UPDATE SET
                        is_enabled = FALSE,
                        disabled_at = NOW(),
                        updated_at = NOW()
                """, user_id, integration_id)
                
                # Optionally disable all scopes
                if disable_all_scopes:
                    await conn.execute("""
                        UPDATE user_integration_scopes
                        SET is_enabled = FALSE, updated_at = NOW()
                        WHERE user_id = $1 AND scope_id IN (
                            SELECT id FROM integration_scopes WHERE integration_id = $2
                        )
                    """, user_id, integration_id)
                
                logger.info(f"Disabled integration {integration_id} for user {user_id}")
        
        return await self.get_user_integration(user_id, integration_id)
    
    # =========================================================================
    # User Scope Settings
    # =========================================================================
    
    async def enable_scope(
        self,
        user_id: UUID,
        scope_id: str
    ) -> Dict[str, Any]:
        """
        Enable a scope for a user.
        
        Note: This sets is_enabled=True but is_granted may still be False
        if OAuth consent hasn't been obtained yet.
        
        Args:
            user_id: User's UUID
            scope_id: Scope identifier (e.g., 'gmail.readonly')
            
        Returns:
            Updated scope settings
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO user_integration_scopes (user_id, scope_id, is_enabled)
                VALUES ($1, $2, TRUE)
                ON CONFLICT (user_id, scope_id)
                DO UPDATE SET
                    is_enabled = TRUE,
                    updated_at = NOW()
                RETURNING id, scope_id, is_enabled, is_granted, granted_at
            """, user_id, scope_id)
            
            logger.info(f"Enabled scope {scope_id} for user {user_id}")
            return dict(row)
    
    async def disable_scope(
        self,
        user_id: UUID,
        scope_id: str
    ) -> Dict[str, Any]:
        """
        Disable a scope for a user (local only, keeps OAuth grant).
        
        Args:
            user_id: User's UUID
            scope_id: Scope identifier
            
        Returns:
            Updated scope settings
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO user_integration_scopes (user_id, scope_id, is_enabled)
                VALUES ($1, $2, FALSE)
                ON CONFLICT (user_id, scope_id)
                DO UPDATE SET
                    is_enabled = FALSE,
                    updated_at = NOW()
                RETURNING id, scope_id, is_enabled, is_granted, granted_at
            """, user_id, scope_id)
            
            logger.info(f"Disabled scope {scope_id} for user {user_id}")
            return dict(row)
    
    async def mark_scopes_granted(
        self,
        user_id: UUID,
        scope_ids: List[str]
    ) -> int:
        """
        Mark scopes as granted after OAuth consent is obtained.
        
        Args:
            user_id: User's UUID
            scope_ids: List of scope identifiers that were granted
            
        Returns:
            Number of scopes updated
        """
        if not scope_ids:
            return 0
        
        async with self.pool.acquire() as conn:
            # Upsert all granted scopes
            result = await conn.execute("""
                INSERT INTO user_integration_scopes (user_id, scope_id, is_enabled, is_granted, granted_at)
                SELECT $1, id, TRUE, TRUE, NOW()
                FROM integration_scopes
                WHERE id = ANY($2::varchar[])
                ON CONFLICT (user_id, scope_id)
                DO UPDATE SET
                    is_granted = TRUE,
                    granted_at = NOW(),
                    updated_at = NOW()
            """, user_id, scope_ids)
            
            count = int(result.split()[-1]) if result else 0
            logger.info(f"Marked {count} scopes as granted for user {user_id}")
            return count
    
    async def get_user_enabled_scopes(
        self,
        user_id: UUID,
        granted_only: bool = True
    ) -> List[str]:
        """
        Get list of scope IDs that user has enabled (and optionally granted).
        
        Args:
            user_id: User's UUID
            granted_only: If True, only return scopes that have OAuth consent
            
        Returns:
            List of scope IDs (e.g., ['gmail.readonly', 'calendar.events'])
        """
        async with self.pool.acquire() as conn:
            if granted_only:
                rows = await conn.fetch("""
                    SELECT scope_id
                    FROM user_integration_scopes
                    WHERE user_id = $1 AND is_enabled = TRUE AND is_granted = TRUE
                """, user_id)
            else:
                rows = await conn.fetch("""
                    SELECT scope_id
                    FROM user_integration_scopes
                    WHERE user_id = $1 AND is_enabled = TRUE
                """, user_id)
            
            return [row["scope_id"] for row in rows]
    
    async def get_user_enabled_scope_uris(
        self,
        user_id: UUID,
        granted_only: bool = True
    ) -> List[str]:
        """
        Get list of OAuth scope URIs that user has enabled.
        
        Args:
            user_id: User's UUID
            granted_only: If True, only return scopes that have OAuth consent
            
        Returns:
            List of full OAuth scope URIs
        """
        async with self.pool.acquire() as conn:
            if granted_only:
                rows = await conn.fetch("""
                    SELECT s.scope_uri
                    FROM user_integration_scopes us
                    JOIN integration_scopes s ON us.scope_id = s.id
                    WHERE us.user_id = $1 AND us.is_enabled = TRUE AND us.is_granted = TRUE
                """, user_id)
            else:
                rows = await conn.fetch("""
                    SELECT s.scope_uri
                    FROM user_integration_scopes us
                    JOIN integration_scopes s ON us.scope_id = s.id
                    WHERE us.user_id = $1 AND us.is_enabled = TRUE
                """, user_id)
            
            return [row["scope_uri"] for row in rows]
    
    async def get_disabled_integrations(
        self,
        user_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Get integrations that are NOT enabled for a user.
        Used to build agent context about unavailable features.
        
        Args:
            user_id: User's UUID
            
        Returns:
            List of disabled integration definitions
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    i.id, i.provider, i.name, i.description, i.capability_summary,
                    i.icon_url
                FROM integrations i
                LEFT JOIN user_integrations ui ON i.id = ui.integration_id AND ui.user_id = $1
                WHERE i.is_active = TRUE AND (ui.is_enabled IS NULL OR ui.is_enabled = FALSE)
                ORDER BY i.display_order
            """, user_id)
            
            return [dict(row) for row in rows]
    
    async def get_scopes_needing_oauth(
        self,
        user_id: UUID,
        integration_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get scopes that user wants enabled but hasn't granted OAuth consent for.
        
        Args:
            user_id: User's UUID
            integration_id: Integration identifier
            
        Returns:
            List of scope definitions needing OAuth consent
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT s.id, s.scope_uri, s.name, s.description, s.is_required
                FROM integration_scopes s
                LEFT JOIN user_integration_scopes us ON s.id = us.scope_id AND us.user_id = $1
                WHERE s.integration_id = $2
                  AND (us.is_enabled = TRUE OR s.is_required = TRUE)
                  AND (us.is_granted IS NULL OR us.is_granted = FALSE)
            """, user_id, integration_id)
            
            return [dict(row) for row in rows]
    
    # =========================================================================
    # Scope-Based User Queries (for scheduled jobs)
    # =========================================================================
    
    async def get_users_with_scope_granted(
        self,
        scope_id: str,
        provider: str = 'google'
    ) -> List[Dict[str, Any]]:
        """
        Get users who have a specific scope granted (OAuth consent obtained).
        
        Used by scheduled jobs to filter users who have the required permissions.
        Only returns users who:
        1. Have a valid OAuth token for the provider
        2. Have the specified scope with is_granted=TRUE
        
        Args:
            scope_id: Scope identifier (e.g., 'contacts.readonly', 'calendar.readonly')
            provider: OAuth provider (default: 'google')
            
        Returns:
            List of dicts with 'id' (UUID) and 'email' for each eligible user
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT u.id, u.email
                FROM users u
                JOIN user_oauth_tokens t ON u.id = t.user_id
                JOIN user_integration_scopes us ON u.id = us.user_id
                WHERE t.provider = $1
                  AND us.scope_id = $2
                  AND us.is_granted = TRUE
            """, provider, scope_id)
            
            return [dict(row) for row in rows]
    
    async def user_has_scope_granted(
        self,
        user_id: UUID,
        scope_id: str
    ) -> bool:
        """
        Check if a specific user has a scope granted.
        
        Args:
            user_id: User's UUID
            scope_id: Scope identifier
            
        Returns:
            True if user has the scope granted, False otherwise
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT 1
                FROM user_integration_scopes
                WHERE user_id = $1
                  AND scope_id = $2
                  AND is_granted = TRUE
            """, user_id, scope_id)
            
            return row is not None
    
    # =========================================================================
    # Bulk Operations for Migration
    # =========================================================================
    
    async def enable_all_integrations_and_scopes(
        self,
        user_id: UUID,
        mark_granted: bool = True
    ) -> Dict[str, int]:
        """
        Enable all integrations and scopes for a user (for migrating existing users).
        
        Args:
            user_id: User's UUID
            mark_granted: If True, also mark all scopes as granted
            
        Returns:
            Dict with counts of integrations and scopes enabled
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Enable all integrations
                integrations_result = await conn.execute("""
                    INSERT INTO user_integrations (user_id, integration_id, is_enabled, enabled_at)
                    SELECT $1, id, TRUE, NOW()
                    FROM integrations
                    WHERE is_active = TRUE
                    ON CONFLICT (user_id, integration_id)
                    DO UPDATE SET
                        is_enabled = TRUE,
                        enabled_at = COALESCE(user_integrations.enabled_at, NOW()),
                        updated_at = NOW()
                """, user_id)
                
                # Enable and optionally grant all scopes
                if mark_granted:
                    scopes_result = await conn.execute("""
                        INSERT INTO user_integration_scopes (user_id, scope_id, is_enabled, is_granted, granted_at)
                        SELECT $1, s.id, TRUE, TRUE, NOW()
                        FROM integration_scopes s
                        JOIN integrations i ON s.integration_id = i.id
                        WHERE i.is_active = TRUE
                        ON CONFLICT (user_id, scope_id)
                        DO UPDATE SET
                            is_enabled = TRUE,
                            is_granted = TRUE,
                            granted_at = COALESCE(user_integration_scopes.granted_at, NOW()),
                            updated_at = NOW()
                    """, user_id)
                else:
                    scopes_result = await conn.execute("""
                        INSERT INTO user_integration_scopes (user_id, scope_id, is_enabled)
                        SELECT $1, s.id, TRUE
                        FROM integration_scopes s
                        JOIN integrations i ON s.integration_id = i.id
                        WHERE i.is_active = TRUE
                        ON CONFLICT (user_id, scope_id)
                        DO UPDATE SET
                            is_enabled = TRUE,
                            updated_at = NOW()
                    """, user_id)
                
                integrations_count = int(integrations_result.split()[-1]) if integrations_result else 0
                scopes_count = int(scopes_result.split()[-1]) if scopes_result else 0
                
                logger.info(
                    f"Enabled all integrations/scopes for user {user_id}: "
                    f"{integrations_count} integrations, {scopes_count} scopes"
                )
                
                return {
                    "integrations_enabled": integrations_count,
                    "scopes_enabled": scopes_count
                }

