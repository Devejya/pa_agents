"""
Token Migration Job

Migrates existing OAuth tokens to:
1. Link to user_id (if user exists)
2. Re-encrypt with per-user DEK (optional, for full multi-tenant security)

This job can be run:
- Manually via API endpoint
- As a one-time migration task

Safety:
- Non-destructive: keeps original tokens, updates in place
- Idempotent: safe to run multiple times
- Logs all actions for audit
"""

import logging
from datetime import datetime
from typing import Optional

from ..db import get_db_pool
from ..db.token_repository import TokenRepository
from ..db.user_repository import UserRepository

logger = logging.getLogger(__name__)


async def link_tokens_to_users() -> dict:
    """
    Link existing tokens to users by matching email.
    
    This is Step 1 of migration - just establishes the user_id foreign key
    without re-encrypting tokens.
    
    Returns:
        Dict with migration statistics.
    """
    stats = {
        "started_at": datetime.utcnow().isoformat(),
        "tokens_found": 0,
        "tokens_linked": 0,
        "tokens_skipped": 0,  # No matching user
        "errors": [],
    }
    
    try:
        pool = await get_db_pool()
        token_repo = TokenRepository(pool)
        user_repo = UserRepository(pool)
        
        # Get all tokens without user_id
        orphan_tokens = await token_repo.get_tokens_without_user_id()
        stats["tokens_found"] = len(orphan_tokens)
        
        logger.info(f"Found {len(orphan_tokens)} tokens without user_id")
        
        for email, provider in orphan_tokens:
            try:
                # Find user by email
                user = await user_repo.get_user_by_email(email)
                
                if user:
                    # Link token to user
                    success = await token_repo.link_token_to_user(email, user["id"])
                    if success:
                        stats["tokens_linked"] += 1
                        logger.info(f"Linked {email}/{provider} to user {user['id']}")
                    else:
                        stats["tokens_skipped"] += 1
                else:
                    stats["tokens_skipped"] += 1
                    logger.debug(f"No user found for {email}, skipping")
                    
            except Exception as e:
                stats["errors"].append({"email": email, "provider": provider, "error": str(e)})
                logger.error(f"Error linking token for {email}: {e}")
        
        stats["completed_at"] = datetime.utcnow().isoformat()
        stats["success"] = True
        
    except Exception as e:
        stats["success"] = False
        stats["error"] = str(e)
        logger.error(f"Token linking migration failed: {e}")
    
    return stats


async def migrate_tokens_to_per_user_encryption(
    email_filter: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """
    Re-encrypt tokens with per-user DEK.
    
    This is Step 2 of migration - takes tokens encrypted with system key
    and re-encrypts them with the user's individual DEK.
    
    Args:
        email_filter: Only migrate tokens for this email (optional).
        dry_run: If True, only report what would be done.
        
    Returns:
        Dict with migration statistics.
    """
    stats = {
        "started_at": datetime.utcnow().isoformat(),
        "dry_run": dry_run,
        "tokens_found": 0,
        "tokens_migrated": 0,
        "tokens_skipped": 0,  # Already migrated or no user
        "errors": [],
    }
    
    try:
        pool = await get_db_pool()
        token_repo = TokenRepository(pool)
        user_repo = UserRepository(pool)
        
        async with pool.acquire() as conn:
            # Get all valid tokens with user_id
            if email_filter:
                rows = await conn.fetch("""
                    SELECT t.email, t.provider, t.user_id
                    FROM user_oauth_tokens t
                    WHERE t.email = $1 AND t.is_valid = TRUE AND t.user_id IS NOT NULL
                """, email_filter)
            else:
                rows = await conn.fetch("""
                    SELECT t.email, t.provider, t.user_id
                    FROM user_oauth_tokens t
                    WHERE t.is_valid = TRUE AND t.user_id IS NOT NULL
                """)
            
            stats["tokens_found"] = len(rows)
            logger.info(f"Found {len(rows)} tokens to potentially migrate")
            
            for row in rows:
                email = row["email"]
                provider = row["provider"]
                user_id = row["user_id"]
                
                try:
                    if dry_run:
                        logger.info(f"[DRY RUN] Would migrate {email}/{provider}")
                        stats["tokens_migrated"] += 1
                    else:
                        # Migrate: read with system key, write with user DEK
                        success = await token_repo.migrate_to_user_encryption(
                            email, user_id, provider
                        )
                        
                        if success:
                            stats["tokens_migrated"] += 1
                            logger.info(f"Migrated {email}/{provider} to per-user encryption")
                        else:
                            stats["tokens_skipped"] += 1
                            
                except Exception as e:
                    stats["errors"].append({
                        "email": email,
                        "provider": provider,
                        "error": str(e)
                    })
                    logger.error(f"Error migrating token for {email}: {e}")
        
        stats["completed_at"] = datetime.utcnow().isoformat()
        stats["success"] = True
        
    except Exception as e:
        stats["success"] = False
        stats["error"] = str(e)
        logger.error(f"Token encryption migration failed: {e}")
    
    return stats


async def run_full_migration(dry_run: bool = False) -> dict:
    """
    Run the complete token migration:
    1. Link tokens to users
    2. Re-encrypt with per-user DEK
    
    Args:
        dry_run: If True, only report what would be done.
        
    Returns:
        Combined migration statistics.
    """
    logger.info(f"Starting full token migration (dry_run={dry_run})")
    
    results = {
        "started_at": datetime.utcnow().isoformat(),
        "dry_run": dry_run,
        "phase1_link": None,
        "phase2_encrypt": None,
    }
    
    # Phase 1: Link tokens to users
    logger.info("Phase 1: Linking tokens to users...")
    if not dry_run:
        results["phase1_link"] = await link_tokens_to_users()
    else:
        results["phase1_link"] = {"dry_run": True, "skipped": True}
    
    # Phase 2: Re-encrypt with per-user DEK
    logger.info("Phase 2: Re-encrypting with per-user DEK...")
    results["phase2_encrypt"] = await migrate_tokens_to_per_user_encryption(dry_run=dry_run)
    
    results["completed_at"] = datetime.utcnow().isoformat()
    results["success"] = (
        results["phase1_link"].get("success", True) and 
        results["phase2_encrypt"].get("success", True)
    )
    
    logger.info(f"Token migration completed: {results}")
    
    return results


async def get_migration_status() -> dict:
    """
    Get the current status of token migration.
    
    Returns:
        Dict with counts of migrated vs unmigrated tokens.
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            # Count tokens by migration status
            stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) FILTER (WHERE is_valid = TRUE) as total_valid,
                    COUNT(*) FILTER (WHERE is_valid = TRUE AND user_id IS NOT NULL) as linked_to_user,
                    COUNT(*) FILTER (WHERE is_valid = TRUE AND user_id IS NULL) as not_linked,
                    COUNT(*) FILTER (WHERE is_valid = FALSE) as revoked
                FROM user_oauth_tokens
            """)
            
            return {
                "total_valid_tokens": stats["total_valid"],
                "linked_to_user": stats["linked_to_user"],
                "not_linked": stats["not_linked"],
                "revoked_tokens": stats["revoked"],
                "migration_complete": stats["not_linked"] == 0,
            }
            
    except Exception as e:
        logger.error(f"Failed to get migration status: {e}")
        return {"error": str(e)}


