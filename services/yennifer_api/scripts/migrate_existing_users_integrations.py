#!/usr/bin/env python3
"""
Migration script for existing users with OAuth tokens.

This script enables all integrations and scopes for existing users who already
have Google OAuth tokens (from before the incremental OAuth feature).

Usage:
    cd services/yennifer_api
    source venv/bin/activate
    python scripts/migrate_existing_users_integrations.py [--dry-run]
"""

import asyncio
import argparse
import logging
import sys
from uuid import UUID

# Add the app directory to the path
sys.path.insert(0, '.')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def migrate_users(dry_run: bool = False):
    """Migrate existing users with OAuth tokens to have all integrations enabled."""
    
    # Import here to ensure settings are loaded
    from app.db.connection import init_db, close_db, get_db_pool
    from app.db.integrations_repository import IntegrationsRepository
    
    await init_db()
    pool = await get_db_pool()
    integrations_repo = IntegrationsRepository(pool)
    
    try:
        # Get all users with Google OAuth tokens
        async with pool.acquire() as conn:
            users_with_tokens = await conn.fetch("""
                SELECT DISTINCT user_id, email
                FROM user_oauth_tokens
                WHERE user_id IS NOT NULL AND provider = 'google'
            """)
        
        logger.info(f"Found {len(users_with_tokens)} users with Google OAuth tokens")
        
        if not users_with_tokens:
            logger.info("No users to migrate")
            return
        
        migrated_count = 0
        skipped_count = 0
        error_count = 0
        
        for row in users_with_tokens:
            user_id = row['user_id']
            email = row['email']
            
            try:
                # Check if user already has integrations enabled
                user_integrations = await integrations_repo.get_user_integrations(
                    user_id, 
                    enabled_only=True
                )
                
                if user_integrations:
                    logger.debug(f"User {email} already has {len(user_integrations)} integrations enabled")
                    skipped_count += 1
                    continue
                
                if dry_run:
                    logger.info(f"[DRY RUN] Would enable all integrations for {email}")
                    migrated_count += 1
                    continue
                
                # Enable all integrations and scopes
                result = await integrations_repo.enable_all_integrations_and_scopes(
                    user_id,
                    mark_granted=True  # They already have OAuth consent
                )
                
                logger.info(
                    f"Migrated {email}: "
                    f"{result['integrations_enabled']} integrations, "
                    f"{result['scopes_enabled']} scopes"
                )
                migrated_count += 1
                
            except Exception as e:
                logger.error(f"Error migrating {email}: {e}")
                error_count += 1
        
        logger.info(f"\n{'=' * 50}")
        logger.info(f"Migration complete{' (DRY RUN)' if dry_run else ''}:")
        logger.info(f"  - Migrated: {migrated_count}")
        logger.info(f"  - Skipped (already migrated): {skipped_count}")
        logger.info(f"  - Errors: {error_count}")
        
    finally:
        await close_db()


def main():
    parser = argparse.ArgumentParser(
        description='Migrate existing users to have all integrations enabled'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be migrated without making changes'
    )
    
    args = parser.parse_args()
    
    if args.dry_run:
        logger.info("Running in DRY RUN mode - no changes will be made")
    
    asyncio.run(migrate_users(dry_run=args.dry_run))


if __name__ == '__main__':
    main()

